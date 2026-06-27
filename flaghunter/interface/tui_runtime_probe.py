"""Runtime connectivity probe + switch mixed into FlagHunterTUI (债池五波·TUI 刀 22, god-class).

Extracted from tui.py. The runtime-backend feature: ``_schedule_runtime_probe`` /
``_switch_runtime`` swap the active tool runtime, the ``@work``
``_probe_runtime_connectivity`` background-checks reachability, and
``_format_tool_install_panel`` renders the missing-tool panel. They call stay-behind
helpers (``self._add_system`` / ``self._set_status``) resolved at runtime through the
FlagHunterTUI instance MRO. Module-level deps: ``logging`` / ``Any`` / ``Dict`` /
``cast`` / ``work``; SSHRuntime / build_runtime / has_ssh_runtime_config are lazy
inside the bodies.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, cast

from textual import work


class RuntimeProbeMixin:
    """Runtime connectivity probe + switch for FlagHunterTUI."""

    def _schedule_runtime_probe(self) -> None:
        """Kick off a background runtime probe if one is not already running."""
        if self.mcp_mode or self._runtime_probe_inflight:
            return
        _ = cast(Any, self._probe_runtime_connectivity())

    async def _switch_runtime(
        self, new_runtime: Any, new_runtime_info: Dict[str, Any], announce: str
    ) -> None:
        """Atomically switch the active runtime and refresh dependent state."""
        old_runtime = self.runtime

        self.runtime = new_runtime
        self.runtime_info = new_runtime_info
        self.use_ssh = new_runtime_info.get("selected") == "ssh"
        self.use_docker = new_runtime_info.get("selected") == "docker"

        if self.mcp_manager and self.runtime:
            self.runtime.mcp_manager = self.mcp_manager

        if self.agent is not None:
            self.agent.runtime = self.runtime

        self._update_header(target=self.target)
        self._add_system(announce)

        if old_runtime:
            try:
                await old_runtime.stop()
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed stopping previous runtime during switch: %s", e
                )

    @work(thread=False)
    async def _probe_runtime_connectivity(self) -> None:
        """Periodically probe Kali SSH reachability and hot-update runtime status."""
        if self._runtime_probe_inflight or self.mcp_mode:
            return

        self._runtime_probe_inflight = True
        probe_runtime = None

        try:
            from ..runtime.ssh_runtime import SSHRuntime
            from .initializer import build_runtime, has_ssh_runtime_config

            if not has_ssh_runtime_config():
                return

            probe_runtime = SSHRuntime()
            try:
                await probe_runtime.start()
                ssh_info = {
                    "requested": self.runtime_info.get("requested", "auto-ssh"),
                    "selected": "ssh",
                    "auto_selected": True,
                    "connected": True,
                    "host": probe_runtime.host,
                    "port": probe_runtime.port,
                    "user": probe_runtime.user,
                    "label": "SSH (auto)",
                    "status_text": (
                        f"SSH connected: {probe_runtime.user}@{probe_runtime.host}:{probe_runtime.port}"
                    ),
                    "fallback_reason": None,
                }

                if self.runtime_info.get("selected") == "ssh":
                    self.runtime_info.update(ssh_info)
                    self._update_header(target=self.target)
                    await probe_runtime.stop()
                    probe_runtime = None
                    return

                if self.runtime_info.get("requested") in ("auto", "auto-ssh"):
                    if self._is_running or self._is_initializing:
                        self.runtime_info.update(
                            {
                                "status_text": (
                                    "SSH available — will switch to SSHRuntime when idle"
                                ),
                                "host": probe_runtime.host,
                                "port": probe_runtime.port,
                                "user": probe_runtime.user,
                            }
                        )
                        self._update_header(target=self.target)
                        await probe_runtime.stop()
                        probe_runtime = None
                        return

                    await self._switch_runtime(
                        probe_runtime,
                        ssh_info,
                        "+ SSH became available — switched to SSHRuntime.",
                    )
                    probe_runtime = None
            except Exception as exc:
                selected_runtime = self.runtime_info.get("selected")
                requested_runtime = self.runtime_info.get("requested")

                if (
                    selected_runtime == "ssh"
                    and requested_runtime in ("auto", "auto-ssh")
                    and not self._is_running
                    and not self._is_initializing
                ):
                    local_runtime, local_info = await build_runtime(
                        docker=False,
                        ssh=False,
                        auto_ssh=False,
                    )
                    local_info.update(
                        {
                            "requested": requested_runtime,
                            "status_text": (
                                "SSH unavailable — fell back to LocalRuntime"
                            ),
                            "fallback_reason": str(exc),
                        }
                    )
                    await self._switch_runtime(
                        local_runtime,
                        local_info,
                        f"[!] SSH unavailable — switched to LocalRuntime: {exc}",
                    )
                    return

                if selected_runtime == "ssh":
                    self.runtime_info.update(
                        {
                            "connected": False,
                            "fallback_reason": str(exc),
                            "status_text": (
                                "SSH unavailable — retrying in background"
                                if requested_runtime in ("auto", "auto-ssh")
                                else "SSH disconnected"
                            ),
                        }
                    )
                    self._update_header(target=self.target)
                    return

                if requested_runtime in ("auto", "auto-ssh"):
                    self.runtime_info.update(
                        {
                            "connected": False,
                            "fallback_reason": str(exc),
                            "status_text": (
                                "SSH unavailable — using LocalRuntime"
                                if selected_runtime != "ssh"
                                else "SSH unavailable — retrying in background"
                            ),
                        }
                    )
                    self._update_header(target=self.target)
        finally:
            if probe_runtime is not None:
                try:
                    await probe_runtime.stop()
                except Exception:
                    pass
            self._runtime_probe_inflight = False

    def _format_tool_install_panel(self, payload: Dict[str, Any]) -> str:
        """Render a boxed warning for missing tools that need operator action."""
        tool = str(payload.get("tool", "unknown"))
        install_hint = str(
            payload.get("install_hint") or payload.get("message") or "Install manually."
        )
        size_mb = payload.get("size_mb", 0)
        size_display = f"~{size_mb} MB" if size_mb else "unknown"
        disk_free_gb = payload.get("disk_free_gb", "?")
        disk_free_pct = payload.get("disk_free_pct", "?")
        lines = [
            f"⚠ Tool Required: {tool}",
            f"Install: {install_hint}",
            f"Size: {size_display}  |  Disk free: {disk_free_gb} GB ({disk_free_pct}%)",
            "",
            "Agent will wait. Install manually, then",
            "type /retry to continue current step.",
        ]
        inner_width = max(45, max(len(line) for line in lines))
        top = "┌" + ("─" * (inner_width + 2)) + "┐"
        bottom = "└" + ("─" * (inner_width + 2)) + "┘"
        body = [f"│ {line.ljust(inner_width)} │" for line in lines]
        return "\n".join([top, *body, bottom])
