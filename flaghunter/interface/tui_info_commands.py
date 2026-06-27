"""Info / diagnostics display commands mixed into FlagHunterTUI (债池五波·TUI 刀 19, god-class).

Extracted from tui.py. The read-only display commands behind /sysprompt, /memory,
/tokens, /notes, and /graph: ``_show_system_prompt`` / ``_show_memory_stats`` /
``_show_token_stats`` / ``_show_notes`` / ``_handle_notes_command`` /
``_handle_graph_command``. They mount diagnostics panels and emit via stay-behind
helpers (``self._add_system``) resolved at runtime through the FlagHunterTUI instance
MRO. Module-level deps: ``logging`` / ``time`` / ``Path`` / ``ScrollableContainer`` and
the ``MemoryDiagnostics`` / ``TokenDiagnostics`` panels (tui_diagnostics, 刀5); notify /
uuid / notes / ShadowGraph backends are lazy inside the bodies. No decorators.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from textual.containers import ScrollableContainer

from .tui_diagnostics import MemoryDiagnostics, TokenDiagnostics


class InfoCommandMixin:
    """/sysprompt /memory /tokens /notes /graph display commands for FlagHunterTUI."""

    def _show_system_prompt(self) -> None:
        """Display the current system prompt"""
        if self.agent:
            prompt = self.agent.get_system_prompt(self._mode)
            self._add_system(f"=== System Prompt ===\n{prompt}")
        else:
            self._add_system("Agent not initialized")

    def _show_memory_stats(self) -> None:
        """Mount a live memory diagnostics widget into the chat area."""
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to query chat-scroll for memory diagnostics: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: memory diagnostics unavailable: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about memory diagnostics availability: %s",
                    ne,
                )
            self._add_system("Agent not initialized")
            return
        # Mount a new diagnostics panel with a unique ID and scroll into view
        try:
            import uuid

            panel_id = f"memory-diagnostics-{uuid.uuid4().hex}"
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to generate memory diagnostics panel id: %s", e
            )
            panel_id = None

        widget = MemoryDiagnostics(id=panel_id)
        scroll.mount(widget)
        try:
            scroll.scroll_end(animate=False)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to scroll to memory diagnostics panel: %s", e
            )
            try:
                from .notifier import notify

                notify(
                    "warning", f"TUI: failed to scroll to memory diagnostics panel: {e}"
                )
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about scroll failure: %s", ne
                )

    def _show_token_stats(self) -> None:
        """Mount a live token diagnostics widget into the chat area."""
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to query chat-scroll for token diagnostics: %s", e
            )
            try:
                from ..interface.notifier import notify

                notify("warning", f"TUI: token diagnostics unavailable: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about token diagnostics availability: %s",
                    ne,
                )
            self._add_system("Agent not initialized")
            return
        # Mount a new diagnostics panel with a unique ID and scroll into view
        try:
            import uuid

            panel_id = f"token-diagnostics-{uuid.uuid4().hex}"
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to generate token diagnostics panel id: %s", e
            )
            try:
                from ..interface.notifier import notify

                notify(
                    "warning",
                    f"TUI: failed to generate token diagnostics panel id: {e}",
                )
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about token diagnostics panel id generation failure: %s",
                    ne,
                )
            panel_id = None

        widget = TokenDiagnostics(id=panel_id)
        scroll.mount(widget)
        try:
            scroll.scroll_end(animate=False)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to scroll to token diagnostics panel: %s", e
            )
            try:
                from ..interface.notifier import notify

                notify(
                    "warning", f"TUI: failed to scroll to token diagnostics panel: {e}"
                )
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about token diagnostics scroll failure: %s",
                    ne,
                )

    async def _show_notes(self) -> None:
        """Display saved notes"""
        from ..tools.notes import get_all_notes
        from ..workspaces.utils import get_loot_file

        notes = await get_all_notes()
        if not notes:
            self._add_system(
                "=== Notes ===\nNo notes saved.\n\nThe AI can save key findings using the notes tool."
            )
            return

        lines = [f"=== Notes ({len(notes)} entries) ==="]
        for key, value in notes.items():
            if isinstance(value, dict):
                category = value.get("category", "info")
                confidence = value.get("confidence", "medium")
                content = str(value.get("content", ""))
                header = f"{key} [{category}/{confidence}]:"

                # Show full value, indent multi-line content
                if "\n" in content:
                    indented = content.replace("\n", "\n    ")
                    lines.append(f"\n{header}\n    {indented}")
                else:
                    lines.append(f"{header} {content}")
            else:
                content = str(value)
                if "\n" in content:
                    indented = content.replace("\n", "\n    ")
                    lines.append(f"\n{key}\n    {indented}")
                else:
                    lines.append(f"{key}: {content}")
            lines.append(f"  -> 输入 /notes delete {key} 删除")
            lines.append(f"  -> 输入 /notes archive {key} 归档")
        notes_path = get_loot_file("notes.json")
        archive_path = notes_path.parent / "notes_archive.json"
        reports_dir = notes_path.parent / "reports"
        lines.append(f"\nFile: {notes_path.as_posix()}")
        lines.append(f"Archive: {archive_path.as_posix()}")
        lines.append(f"Reports: {reports_dir.as_posix()}/")

        self._add_system("\n".join(lines))

    async def _handle_notes_command(self, cmd: str) -> None:
        """Handle /notes and lightweight note maintenance actions."""
        from ..tools.notes import notes as notes_tool

        rest = cmd[len("/notes") :].strip()
        if not rest:
            await self._show_notes()
            return

        parts = rest.split(maxsplit=1)
        action = parts[0].lower()
        if action not in {"delete", "archive"}:
            self._add_system(
                "Usage: /notes\n"
                "       /notes delete <key>\n"
                "       /notes archive <key>"
            )
            return

        key = parts[1].strip() if len(parts) > 1 else ""
        if not key:
            self._add_system(f"Usage: /notes {action} <key>")
            return

        result = await notes_tool({"action": action, "key": key}, runtime=None)
        self._add_system(f"[notes] {result}")
        if not result.startswith("Error:") and "not found" not in result.lower():
            await self._show_notes()

    async def _handle_graph_command(self) -> None:
        from flaghunter.knowledge.graph import ShadowGraph
        from flaghunter.tools.notes import get_all_notes

        notes = await get_all_notes()
        if not notes:
            self._add_system("No notes yet. Run a task first.")
            return

        graph = ShadowGraph()
        graph.update_from_notes(notes)

        if graph.graph.number_of_nodes() == 0:
            self._add_system(
                "Graph empty — notes don't contain host/service/credential data yet."
            )
            return

        mermaid = graph.to_mermaid()
        stats = graph.export_summary()

        self._add_system(
            f"Attack Path Graph ({graph.graph.number_of_nodes()} nodes, "
            f"{graph.graph.number_of_edges()} edges)\n\n"
            f"```mermaid\n{mermaid}\n```\n\n"
            f"Summary:\n{stats}"
        )

        out = Path("reports") / f"graph_{int(time.time())}.mmd"
        out.parent.mkdir(exist_ok=True)
        out.write_text(mermaid, encoding="utf-8")
        self._add_system(f"Saved to {out}")
