"""
httpx_probe — 快速存活探测与指纹获取

基于 httpx 的现代 HTTP 探测工具封装，用于：
- 快速探测大量目标存活状态
- 获取响应标题、TLS 证书、Web 服务器指纹
- 发现重定向链、技术栈识别
- CTF 快速端口服务确认

依赖：httpx (go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest)
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile

from ...runtime.runtime import Runtime
from ...tools._tool_env import find_tool
from ...tools.registry import ToolSchema, register_tool


def _build_base_args(
    ports: str | None = None,
    threads: int = 50,
    timeout: int = 5,
    retries: int = 1,
    follow_redirects: bool = True,
    max_redirects: int = 5,
    no_color: bool = True,
) -> list[str]:
    args = [
        "-json",
        "-no-color" if no_color else "",
        "-threads", str(threads),
        "-timeout", str(timeout),
        "-retries", str(retries),
    ]
    if ports:
        args += ["-ports", ports]
    if follow_redirects:
        args += ["-follow-redirects", "-max-redirects", str(max_redirects)]
    return [a for a in args if a]


def _run_httpx(targets: list[str], extra_args: list[str]) -> list[dict] | None:
    httpx_path = find_tool("httpx")
    if not httpx_path:
        return None

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(targets))
        target_file = f.name

    try:
        cmd = [httpx_path, "-l", target_file] + extra_args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None
    finally:
        try:
            os.unlink(target_file)
        except Exception:
            pass

    entries = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            entries.append(obj)
        except json.JSONDecodeError:
            pass
    return entries


def _summarize(entries: list[dict]) -> dict:
    alive = []
    dead = []
    technologies = set()
    titles = []
    tls_info = []
    status_codes = {}
    web_servers = {}

    for e in entries:
        url = e.get("url", "")
        if not url:
            continue

        status = e.get("status_code", 0)
        if status and status != 0:
            alive.append(url)
            status_codes[status] = status_codes.get(status, 0) + 1
        else:
            dead.append(url)
            continue

        title = e.get("title", "")
        if title:
            titles.append({"url": url, "title": title})

        tech = e.get("technologies", []) or e.get("tech", [])
        if isinstance(tech, list):
            for t in tech:
                technologies.add(t)

        server = e.get("webserver", "")
        if server:
            web_servers[server] = web_servers.get(server, 0) + 1

        tls = e.get("tls")
        if tls and isinstance(tls, dict):
            tls_info.append({
                "url": url,
                "subject": tls.get("subject_name", ""),
                "issuer": tls.get("issuer_name", ""),
                "not_after": tls.get("not_after", ""),
                "sans": tls.get("subject_an", []),
            })

    return {
        "alive_count": len(alive),
        "dead_count": len(dead),
        "alive": alive[:50],
        "dead": dead[:50],
        "status_codes": status_codes,
        "web_servers": web_servers,
        "technologies_found": sorted(list(technologies)),
        "page_titles": titles[:30],
        "tls_certificates": tls_info[:10],
    }


def _probe_single(
    url: str,
    include_response: bool = False,
    extract_tech: bool = True,
    timeout: int = 5,
) -> dict:
    extra_args = _build_base_args(timeout=timeout, threads=1)
    if include_response:
        extra_args.append("-content-type")
    if extract_tech:
        extra_args.append("-tech-detect")

    entries = _run_httpx([url], extra_args)
    if entries is None:
        return {
            "status": "error",
            "message": "httpx binary not found. Install: go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest",
        }

    if not entries:
        return {
            "status": "dead",
            "url": url,
            "message": "No response from target",
        }

    e = entries[0]
    status = e.get("status_code", 0)
    result = {
        "status": "alive" if status and status != 0 else "dead",
        "url": e.get("url", url),
        "final_url": e.get("final_url", ""),
        "status_code": status,
        "title": e.get("title", ""),
        "webserver": e.get("webserver", ""),
        "content_type": e.get("content_type", ""),
        "technologies": e.get("technologies", []) or e.get("tech", []),
        "content_length": e.get("content_length", 0),
        "response_time": e.get("time", ""),
        "cnames": e.get("cnames", []),
        "chain_status_codes": e.get("chain_status_codes", []),
    }

    tls = e.get("tls")
    if tls and isinstance(tls, dict):
        result["tls"] = {
            "subject": tls.get("subject_name", ""),
            "issuer": tls.get("issuer_name", ""),
            "not_before": tls.get("not_before", ""),
            "not_after": tls.get("not_after", ""),
            "sans": tls.get("subject_an", []),
        }

    if include_response:
        result["headers"] = e.get("header", {})

    return result


@register_tool(
    name="httpx_probe",
    description="Fast HTTP alive probing and fingerprinting using httpx. Supports single-target detailed inspection and batch scanning with technology detection, TLS certificate extraction, and redirect chain analysis.",
    schema=ToolSchema(
        type="object",
        properties={
            "target": {
                "type": "string",
                "description": "Target URL, domain, or comma-separated list for batch mode",
            },
            "mode": {
                "type": "string",
                "description": "single (detailed) or batch (summary stats)",
                "default": "single",
            },
            "ports": {
                "type": "string",
                "description": "Custom ports, e.g. '80,443,8080,8443,3000'",
            },
            "threads": {
                "type": "integer",
                "description": "Concurrent threads (default: 50)",
                "default": 50,
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 5)",
                "default": 5,
            },
            "retries": {
                "type": "integer",
                "description": "Retry count (default: 1)",
                "default": 1,
            },
            "include_response": {
                "type": "boolean",
                "description": "Include response headers (single mode only)",
                "default": False,
            },
            "extract_tech": {
                "type": "boolean",
                "description": "Extract technology fingerprints (default: true)",
                "default": True,
            },
            "follow_redirects": {
                "type": "boolean",
                "description": "Follow redirects (default: true)",
                "default": True,
            },
        },
        required=["target"],
    ),
    category="recon",
)
async def httpx_probe(arguments: dict, runtime: Runtime) -> str:
    target = arguments.get("target", "")
    mode = arguments.get("mode", "single")
    ports = arguments.get("ports", "")
    threads = arguments.get("threads", 50)
    timeout = arguments.get("timeout", 5)
    retries = arguments.get("retries", 1)
    include_response = arguments.get("include_response", False)
    extract_tech = arguments.get("extract_tech", True)
    follow_redirects = arguments.get("follow_redirects", True)

    targets = [t.strip() for t in target.split(",") if t.strip()]
    if not targets:
        return json.dumps({"status": "error", "message": "No target provided"}, ensure_ascii=False)

    httpx_path = find_tool("httpx")
    if not httpx_path:
        return json.dumps({
            "status": "error",
            "message": "httpx binary not found. Install: go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest",
        }, ensure_ascii=False)

    if mode == "single":
        result = _probe_single(
            targets[0],
            include_response=include_response,
            extract_tech=extract_tech,
            timeout=timeout,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif mode == "batch":
        extra_args = _build_base_args(
            ports=ports or None,
            threads=threads,
            timeout=timeout,
            retries=retries,
            follow_redirects=follow_redirects,
        )
        if extract_tech:
            extra_args.append("-tech-detect")

        entries = _run_httpx(targets, extra_args)
        if entries is None:
            return json.dumps({"status": "error", "message": "httpx execution failed"}, ensure_ascii=False)

        summary = _summarize(entries)
        summary["status"] = "ok"
        summary["targets_scanned"] = len(targets)
        return json.dumps(summary, ensure_ascii=False, indent=2)

    else:
        return json.dumps({"status": "error", "message": f"Unknown mode: {mode}. Use 'single' or 'batch'."}, ensure_ascii=False)
