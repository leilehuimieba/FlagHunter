"""Sidebar / header chrome mixed into FlagHunterTUI (债池五波·TUI 刀 26, god-class).

Extracted from tui.py. The sidebar + header UI chrome: ``_show_sidebar`` /
``_hide_sidebar`` mount/unmount the side panel, ``_apply_target_display`` reflects the
active target, ``_cpa_m1_status_str`` formats the CPA M1 provider status, and
``_update_header`` redraws the top header. They call stay-behind helpers
(``self._add_system`` / ``self.query_one``) resolved at runtime through the FlagHunterTUI
instance MRO. Module-level deps: ``logging`` / ``re`` / ``time`` / ``List`` / ``Optional``
/ ``ScrollableContainer`` / ``Static`` / ``SystemMessage`` (tui_message_widgets, 刀3) /
``CrewTree`` (tui_core_widgets, 刀6); os / notify / provider-manager backends are lazy
inside the bodies. No decorators.
"""

from __future__ import annotations

import logging
import re
import time
from typing import List, Optional

from textual.containers import ScrollableContainer
from textual.widgets import Static

from .tui_core_widgets import CrewTree
from .tui_message_widgets import SystemMessage


class ChromeMixin:
    """Sidebar / header chrome for FlagHunterTUI."""

    def _show_sidebar(self) -> None:
        """Show the sidebar for crew mode."""
        try:
            import time

            sidebar = self.query_one("#sidebar")
            sidebar.add_class("visible")

            chat_area = self.query_one("#chat-area")
            chat_area.add_class("with-sidebar")

            # Setup tree
            tree = self.query_one("#workers-tree", CrewTree)
            tree.root.expand()
            tree.show_root = False

            # Clear old nodes
            tree.root.remove_children()
            self._crew_worker_nodes.clear()
            self._crew_workers.clear()
            self._worker_events.clear()
            self._crew_findings_count = 0

            # Start tracking time and tokens
            self._crew_start_time = time.time()
            self._crew_tokens_used = 0

            # Start stats timer (update every second)
            if self._crew_stats_timer:
                self._crew_stats_timer.stop()
            self._crew_stats_timer = self.set_interval(1.0, self._update_crew_stats)

            # Start spinner timer for running workers (faster interval for smooth animation)
            if self._spinner_timer:
                self._spinner_timer.stop()
            self._spinner_timer = self.set_interval(0.15, self._update_spinner)

            # Add crew root node (no orchestrator - just "CREW" header)
            self._crew_orchestrator_node = tree.root.add(
                "CREW", data={"type": "crew", "id": "crew"}
            )
            if self._crew_orchestrator_node:
                try:
                    self._crew_orchestrator_node.expand()
                    tree.select_node(self._crew_orchestrator_node)
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to expand/select crew orchestrator node: %s", e
                    )
                    try:
                        from .notifier import notify

                        notify(
                            "warning", f"TUI: failed to expand crew sidebar node: {e}"
                        )
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about crew node expansion failure"
                        )
            self._viewing_worker_id = None

            # Update stats
            self._update_crew_stats()
        except Exception as e:
            self._add_system(f"[!] Sidebar error: {e}")

    def _apply_target_display(self, target: str) -> None:
        """Update or insert the Target line in the system/banner area."""
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            updated = False
            for child in scroll.children:
                if isinstance(child, SystemMessage) and "FlagHunter ready" in getattr(
                    child, "message_content", ""
                ):
                    # Replace existing Target line if present, otherwise append
                    try:
                        if "Target:" in child.message_content:
                            child.message_content = re.sub(
                                r"(?m)^\s*Target:.*$",
                                f"  Target: {target}",
                                child.message_content,
                                count=1,
                            )
                        else:
                            child.message_content = (
                                child.message_content + f"\n  Target: {target}"
                            )
                        try:
                            child.refresh()
                        except Exception as e:
                            logging.getLogger(__name__).exception(
                                "Failed to refresh child message: %s", e
                            )
                            try:
                                from flaghunter.interface.notifier import notify

                                notify(
                                    "warning", f"TUI: failed to refresh UI element: {e}"
                                )
                            except Exception:
                                logging.getLogger(__name__).exception(
                                    "Failed to notify operator about child refresh failure"
                                )
                    except Exception as e:
                        logging.getLogger(__name__).exception(
                            "Failed to update SystemMessage target line: %s", e
                        )
                        try:
                            from flaghunter.interface.notifier import notify

                            notify("warning", f"Failed to update target display: {e}")
                        except Exception:
                            logging.getLogger(__name__).exception(
                                "Failed to notify operator about target update error"
                            )
                        child.message_content = (
                            child.message_content + f"\n  Target: {target}"
                        )
                    updated = True
                    break
                if not updated:
                    try:
                        self._update_header(target=target)
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "Failed to update persistent header with target"
                        )
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed updating in-scroll target display: %s", e
            )
            # Also update the persistent header so the target is always visible
        try:
            self._update_header(target=target)
        except Exception:
            pass

    # === CPA M1 HOOK BEGIN ===
    def _cpa_m1_status_str(self) -> str:
        """Return a compact M1 provider status string for the header."""
        import os
        if os.getenv("CPA_M1_API_HUB", "true").lower() == "false":
            return ""
        try:
            from flaghunter.cpa_modules.m1_api_hub import get_provider_manager
            pm = get_provider_manager()
            providers = pm.list_providers()
            if not providers:
                return ""
            parts = []
            for p in providers[:2]:
                st = pm.get_status(p.id)
                state = st.state.value if st else "unknown"
                dot = "●" if state == "healthy" else ("◑" if state == "degraded" else "○")
                parts.append(f"{p.id} {dot}")
            return "M1: " + " | ".join(parts)
        except Exception:
            return ""
    # === CPA M1 HOOK END ===

    def _update_header(
        self, model_line: Optional[str] = None, target: Optional[str] = None
    ) -> None:
        """Compose and update the persistent header widget."""
        try:
            header = self.query_one("#header", Static)
            # Build header text from provided pieces or current state
            lines: List[str] = []
            flag_banner = getattr(self, "_flag_banner", "")
            if flag_banner:
                lines.append(f"🚩 FLAG FOUND: {flag_banner}")
            if model_line:
                lines.append(model_line)
            else:
                # try to recreate a compact model/runtime line
                runtime_str = (
                    getattr(self, "runtime_info", {}).get("label")
                    or ("Docker" if getattr(self, "use_docker", False) else "Local")
                )
                tools_count = 0
                if self.agent:
                    tools_count = len([t for t in self.agent.get_tools() if t.enabled])
                mode = getattr(self, "_mode", "")
                mode += " (use /assist for single tool execution, /agent or /crew for autonomous modes, /interact for interactive chat)"
                lines.append(
                    f"+ FlagHunter ready\n  Model: {getattr(self, 'model', '')} | Tools: {tools_count} | MCP: {getattr(self, 'mcp_server_count', '')} | RAG: {getattr(self, 'rag_doc_count', '')}\n  Runtime: {runtime_str} | Mode: {mode}"
                )
            runtime_status = getattr(self, "runtime_info", {}).get("status_text", "")
            if runtime_status:
                lines.append(f"  Runtime Status: {runtime_status}")
            # Ensure target line is present/updated
            if target is None:
                target = getattr(self, "target", "")
            if target:
                # append target on its own line
                lines.append(f"  Target: {target}")

            # === CPA M1 HOOK BEGIN ===
            m1_str = self._cpa_m1_status_str()
            if m1_str and lines:
                sub = lines[0].split("\n")
                if len(sub) >= 2:
                    sub[1] = sub[1] + f" | {m1_str}"
                    lines[0] = "\n".join(sub)
            # === CPA M1 HOOK END ===
            header.update("\n".join(lines))
        except Exception:
            pass

    def _hide_sidebar(self) -> None:
        """Hide the sidebar."""
        try:
            # Stop stats timer
            if self._crew_stats_timer:
                self._crew_stats_timer.stop()
                self._crew_stats_timer = None

            sidebar = self.query_one("#sidebar")
            sidebar.remove_class("visible")

            chat_area = self.query_one("#chat-area")
            chat_area.remove_class("with-sidebar")
        except Exception as e:
            logging.getLogger(__name__).exception("Sidebar error: %s", e)
            try:
                from .notifier import notify

                notify("warning", f"TUI: sidebar error: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about sidebar error"
                )
