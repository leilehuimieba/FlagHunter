"""Event hook system for FlagHunter.

Fire hooks before/after tool execution, on flag detection, and on
vulnerability discovery. Third-party code can register callbacks to
intercept, modify, or enrich tool behaviour.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

_FLAG_PATTERN = re.compile(r"(?:flag|ctf|CTF|FLAG)\{[^}\r\n]{1,200}\}")
_VULN_KEYWORDS = [
    "sql injection", "xss", "rce", "lfi", "ssrf", "csrf",
    "command injection", "path traversal", "idor", "ssti",
    "xxe", "deserialization", "open redirect",
]

PreToolCallback = Callable[[str, dict[str, Any]], Any]
PostToolCallback = Callable[[str, Any, float], Any]
FlagCallback = Callable[[str, str | None], None]
VulnCallback = Callable[[str, str, str], None]


@dataclass
class HookResult:
    allow: bool = True
    reason: str = ""
    modified_args: dict[str, Any] | None = None
    enriched_result: str | None = None


class HookRunner:
    """Event hook runner — extensible interception points around tool execution."""

    def __init__(self):
        self._pre_tool_hooks: list[PreToolCallback] = []
        self._post_tool_hooks: list[PostToolCallback] = []
        self._flag_hooks: list[FlagCallback] = []
        self._vuln_hooks: list[VulnCallback] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, event: str, callback: Callable) -> None:
        """Register a hook callback for *event*.

        Valid events: ``pre_tool``, ``post_tool``, ``flag``, ``vuln``.
        """
        if event == "pre_tool":
            self._pre_tool_hooks.append(callback)
        elif event == "post_tool":
            self._post_tool_hooks.append(callback)
        elif event == "flag":
            self._flag_hooks.append(callback)
        elif event == "vuln":
            self._vuln_hooks.append(callback)
        else:
            raise ValueError(f"Unknown hook event: {event}")

    def unregister(self, event: str, callback: Callable) -> None:
        """Remove a previously registered hook callback."""
        bucket = {
            "pre_tool": self._pre_tool_hooks,
            "post_tool": self._post_tool_hooks,
            "flag": self._flag_hooks,
            "vuln": self._vuln_hooks,
        }.get(event)
        if bucket and callback in bucket:
            bucket.remove(callback)

    # ------------------------------------------------------------------
    # Fire methods
    # ------------------------------------------------------------------

    async def fire_pre_tool(self, tool_name: str, args: dict[str, Any]) -> HookResult:
        """Run all pre-tool hooks. The last non-default HookResult wins."""
        final = HookResult()
        if not self._pre_tool_hooks:
            return final
        for hook in self._pre_tool_hooks:
            try:
                result = hook(tool_name, dict(args))
                if result is not None and isinstance(result, HookResult):
                    final = result
            except Exception:
                log.exception("pre_tool hook failed for %s", tool_name)
        return final

    async def fire_post_tool(
        self, tool_name: str, result: Any, duration_ms: float
    ) -> HookResult:
        """Run all post-tool hooks. Results are merged (last wins per field)."""
        final = HookResult()
        if not self._post_tool_hooks:
            return final
        for hook in self._post_tool_hooks:
            try:
                hr = hook(tool_name, result, duration_ms)
                if hr is not None and isinstance(hr, HookResult):
                    if hr.enriched_result:
                        final.enriched_result = (
                            (final.enriched_result or "") + "\n" + hr.enriched_result
                        ).strip()
                    if not hr.allow:
                        final.allow = False
                        final.reason = hr.reason
            except Exception:
                log.exception("post_tool hook failed for %s", tool_name)
        return final

    def fire_flag_detected(self, flag_text: str, challenge_id: str | None = None) -> None:
        """Notify all flag-detection hooks."""
        for hook in self._flag_hooks:
            try:
                hook(flag_text, challenge_id)
            except Exception:
                log.exception("flag hook failed")

    def fire_vuln_found(self, vuln_type: str, target: str, evidence: str = "") -> None:
        """Notify all vulnerability-discovery hooks."""
        for hook in self._vuln_hooks:
            try:
                hook(vuln_type, target, evidence)
            except Exception:
                log.exception("vuln hook failed")

    # ------------------------------------------------------------------
    # Auto-detection helpers
    # ------------------------------------------------------------------

    def scan_for_flags(self, text: str, challenge_id: str | None = None) -> None:
        """Scan *text* for flag patterns and fire hooks for any matches."""
        flags = _FLAG_PATTERN.findall(text or "")
        for flag in flags:
            self.fire_flag_detected(flag, challenge_id)

    def scan_for_vulns(self, text: str, target: str = "") -> None:
        """Scan *text* for vulnerability keywords and fire hooks."""
        lowered = (text or "").lower()
        for kw in _VULN_KEYWORDS:
            if kw in lowered:
                self.fire_vuln_found(kw, target, text[:200])


# Global singleton
_default_hooks: HookRunner | None = None


def get_hook_runner() -> HookRunner:
    """Return the global HookRunner singleton."""
    global _default_hooks
    if _default_hooks is None:
        _default_hooks = HookRunner()
        _register_builtin_hooks(_default_hooks)
    return _default_hooks


def _register_builtin_hooks(runner: HookRunner) -> None:
    """Register built-in hooks: flag → notes, vuln → task registry."""

    def _flag_to_notes(flag_text: str, challenge_id: str | None) -> None:
        try:
            from .tools.notes import notes as notes_fn
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(notes_fn(
                    {"action": "create", "key": f"flag_{flag_text[:20]}", "value": flag_text, "category": "credential", "source": "hook"},
                    None,
                ))
        except Exception:
            pass

    def _vuln_to_registry(vuln_type: str, target: str, evidence: str) -> None:
        try:
            from .task_registry import TaskRegistry
            registry = TaskRegistry()
            tasks = registry.list_tasks()
            if tasks:
                registry.add_finding(tasks[0].task_id, {
                    "title": vuln_type,
                    "severity": "medium",
                    "target": target,
                    "evidence": evidence[:200],
                })
        except Exception:
            pass

    runner.register("flag", _flag_to_notes)
    runner.register("vuln", _vuln_to_registry)
