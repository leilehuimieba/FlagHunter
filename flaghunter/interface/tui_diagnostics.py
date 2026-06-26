"""Status bar, memory / token diagnostics panels & resize divider (debt ledger 第五波·TUI 刀5).

Extracted from tui.py. Six status/diagnostic display widgets: the bottom
``StatusBar``, the ``MemoryDiagnostics`` / ``CTFMemoryOperationsPanel`` /
``CTFMemoryControlPanel`` strategy-memory panels, the ``TokenDiagnostics`` token
budget panel, and the ``ResizeDivider`` drag handle. Cross-package helpers
(StrategyMemoryStore, env parsing, os, notify) are imported lazily inside the
method bodies, so they travel with the code; the ``tui`` back-reference is a
string forward annotation never evaluated. AST free-name analysis confirms zero
module-level up-calls into tui.py — the cluster is down-closed. tui.py re-imports
the set so stay-behind FlagHunterTUI compose / mount paths resolve unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Button, Static, Tree


class StatusBar(Static):
    """Animated status bar"""

    status = reactive("idle")
    mode = reactive("assist")  # "assist" or "agent"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._frame = 0
        self._timer: Optional[Timer] = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.2, self._tick)

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % 4
        if self.status not in ["idle", "complete"]:
            self.refresh()

    def render(self) -> Text:
        dots = "." * (self._frame + 1)

        # Use fixed-width labels (pad dots to 4 chars so text doesn't jump)
        dots_padded = dots.ljust(4)

        # PA theme status colors (muted, ethereal)
        status_map = {
            "idle": ("Ready", "#6b6b6b"),
            "initializing": (f"Initializing{dots_padded}", "#9a9a9a"),
            "thinking": (f"Thinking{dots_padded}", "#9a9a9a"),
            "running": (f"Running{dots_padded}", "#9a9a9a"),
            "processing": (f"Processing{dots_padded}", "#9a9a9a"),
            "waiting": ("Waiting for input", "#9a9a9a"),
            "complete": ("Complete", "#4a9f6e"),
            "error": ("Error", "#9f4a4a"),
        }

        label, color = status_map.get(self.status, (self.status, "#6b6b6b"))

        text = Text()

        # Show mode (ASCII-safe symbols)
        if self.mode == "crew":
            text.append("  :: Crew ", style="#9a9a9a")
        elif self.mode == "agent":
            text.append("  >> Agent ", style="#9a9a9a")
        elif self.mode == "interact":
            text.append("  >> Interact ", style="#9a9a9a")
        elif self.mode == "mcp":
            text.append("  [MCP] ", style="#6b9a9a")
        else:
            text.append("  >> Assist ", style="#9a9a9a")

        text.append(f"| {label}", style=color)

        if self.status not in ["idle", "initializing", "complete", "error"]:
            text.append("    ESC to stop", style="#525252")

        return text


class MemoryDiagnostics(Static):
    """Live memory diagnostics widget mounted into the chat area.

    This widget polls the agent's LLM memory stats periodically and
    renders a compact, updating diagnostics panel.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._timer: Optional[Timer] = None

    def on_mount(self) -> None:
        # Refresh periodically for a lively display
        self._timer = self.set_interval(0.8, self.refresh)

    def on_unmount(self) -> None:
        if self._timer:
            self._timer.stop()

    def _bar(self, ratio: float, width: int = 20) -> str:
        filled = int(max(0, min(1.0, ratio)) * width)
        return "█" * filled + "░" * (width - filled)

    def render(self) -> Text:
        text = Text()

        try:
            app = self.app
            agent = getattr(app, "agent", None)
            if not agent or not getattr(agent, "llm", None):
                text.append("Memory Diagnostics\n", style="bold #d4d4d4")
                text.append("Agent not initialized", style="#9a9a9a")
                return text

            stats = agent.llm.get_memory_stats()
            msgs = len(agent.conversation_history)
            llm_msgs = agent._format_messages_for_llm()
            current_tokens = agent.llm.memory.get_total_tokens(llm_msgs)

            budget = stats.get("token_budget") or 1
            thresh = stats.get("summarize_threshold") or budget
            recent_keep = stats.get("recent_to_keep", 5)
            has_summary = stats.get("has_summary", False)
            summarized_count = stats.get("summarized_message_count", 0)

            # Header
            text.append("Memory Diagnostics\n", style="bold #d4d4d4")

            # Use a consistent bar width for all bars and align labels
            bar_width = 28
            labels = ["Tokens:", "Messages:", "Retention:"]
            label_width = max(len(label_text) for label_text in labels)

            # Tokens line
            ratio = current_tokens / max(1, budget)
            bar = self._bar(ratio, width=bar_width)
            label = "Tokens:".ljust(label_width)
            text.append(
                f"{label} [{bar}] {current_tokens:,} / {budget:,}\n", style="#9a9a9a"
            )

            # Messages line (scale messages to an expected max window)
            expected_msgs_max = max(1, recent_keep * 6)
            mratio = min(1.0, msgs / expected_msgs_max)
            mbar = self._bar(mratio, width=bar_width)
            label = "Messages:".ljust(label_width)
            text.append(f"{label} [{mbar}] {msgs} active\n", style="#9a9a9a")

            # Retention / recent
            k_ratio = min(1.0, recent_keep / max(1, recent_keep))
            keep_bar = self._bar(k_ratio, width=bar_width)
            label = "Retention:".ljust(label_width)
            text.append(
                f"{label} [{keep_bar}] keeping last {recent_keep}\n", style="#9a9a9a"
            )

            # Summary status
            summary_state = "active" if has_summary else "inactive"
            emoji = "ON" if has_summary else "OFF"
            text.append(f"Summary: {emoji} {summary_state}\n", style="#9a9a9a")

            # Summarized / threshold
            text.append(
                f"Summarized: {summarized_count} / {thresh:,}\n", style="#9a9a9a"
            )
            text.append(f"Threshold: {thresh:,}\n", style="#9a9a9a")

        except Exception as e:
            text.append(f"Memory diagnostics error: {e}", style="#9a9a9a")

        return text


class CTFMemoryOperationsPanel(Static):
    """Compact static panel for StopReport + strategy-memory actions."""

    DEFAULT_CSS = """
    CTFMemoryOperationsPanel {
        width: 100%;
        height: auto;
        background: #121212;
        border: round #3a3a3a;
        padding: 1 2;
        margin: 1 0;
    }
    """

    def __init__(self, title: str, body: str, **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._body = body

    def render(self) -> Text:
        text = Text()
        text.append(f"{self._title}\n", style="bold #d4d4d4")
        text.append(self._body, style="#9a9a9a")
        return text


class CTFMemoryControlPanel(Static):
    """Interactive strategy-memory control panel mounted in chat area."""

    DEFAULT_CSS = """
    CTFMemoryControlPanel {
        width: 100%;
        height: auto;
        background: #121212;
        border: round #3a3a3a;
        padding: 1;
        margin: 1 0;
        layout: vertical;
    }
    #ctf-memory-control-summary {
        height: auto;
        color: #9a9a9a;
        padding: 0 1 1 1;
    }
    #ctf-memory-control-toolbar {
        height: auto;
        layout: horizontal;
        padding: 0 0 1 0;
    }
    #ctf-memory-control-actions {
        height: auto;
        layout: horizontal;
        padding: 1 0 0 0;
    }
    #ctf-memory-control-main {
        height: 18;
        layout: horizontal;
    }
    #ctf-memory-control-left {
        width: 38;
        height: 100%;
        border: round #262626;
        margin-right: 1;
    }
    #ctf-memory-control-right {
        width: 1fr;
        height: 100%;
        border: round #262626;
        padding: 0 1;
    }
    #ctf-memory-control-detail {
        height: 100%;
        color: #d4d4d4;
    }
    """

    def __init__(
        self,
        tui: "FlagHunterTUI",
        *,
        filter_mode: str = "all",
        sort_by: str = "recent",
        threshold: float = 0.3,
        preferred_entry_ids: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.tui = tui
        self.filter_mode = filter_mode
        self.sort_by = sort_by
        self.threshold = threshold
        self.preferred_entry_ids = [
            str(entry_id).strip()
            for entry_id in (preferred_entry_ids or [])
            if str(entry_id).strip()
        ]
        self.entries: list[Any] = []
        self.selected_entry_id: str | None = None
        self._armed_delete_entry_id: str | None = None
        self._clear_armed = False

    def compose(self) -> ComposeResult:
        yield Static("", id="ctf-memory-control-summary")
        with Horizontal(id="ctf-memory-control-toolbar"):
            yield Button("Refresh", id="ctf-mem-refresh")
            yield Button("All", id="ctf-mem-filter-all")
            yield Button("Active", id="ctf-mem-filter-active")
            yield Button("Muted", id="ctf-mem-filter-muted")
            yield Button("Audit", id="ctf-mem-filter-audit")
            yield Button("Sort:Recent", id="ctf-mem-sort-recent")
            yield Button("Sort:Corr", id="ctf-mem-sort-correlation")
            yield Button("Sort:Applied", id="ctf-mem-sort-applied")
        with Horizontal(id="ctf-memory-control-main"):
            with Vertical(id="ctf-memory-control-left"):
                yield Tree("MEMORY", id="ctf-memory-tree")
            with Vertical(id="ctf-memory-control-right"):
                yield Static("Select an entry to view details.", id="ctf-memory-control-detail")
        with Horizontal(id="ctf-memory-control-actions"):
            yield Button("Mute", id="ctf-mem-action-mute")
            yield Button("Activate", id="ctf-mem-action-activate")
            yield Button("Rollback", id="ctf-mem-action-rollback")
            yield Button("Delete", id="ctf-mem-action-delete")
            yield Button("Export", id="ctf-mem-action-export")
            yield Button("Clear All", id="ctf-mem-action-clear")

    async def on_mount(self) -> None:
        await self.reload_panel()

    @on(Tree.NodeSelected, "#ctf-memory-tree")
    def on_memory_selected(self, event: Tree.NodeSelected) -> None:
        entry_id = event.node.data.get("entry_id") if event.node.data else None
        self.selected_entry_id = str(entry_id) if entry_id else None
        self._armed_delete_entry_id = None
        self._update_detail()
        self._update_action_buttons()

    @on(Button.Pressed, "#ctf-mem-refresh")
    async def on_refresh_pressed(self) -> None:
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-filter-all")
    async def on_filter_all(self) -> None:
        self.filter_mode = "all"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-filter-active")
    async def on_filter_active(self) -> None:
        self.filter_mode = "active"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-filter-muted")
    async def on_filter_muted(self) -> None:
        self.filter_mode = "muted"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-filter-audit")
    async def on_filter_audit(self) -> None:
        self.filter_mode = "audit"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-sort-recent")
    async def on_sort_recent(self) -> None:
        self.sort_by = "recent"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-sort-correlation")
    async def on_sort_correlation(self) -> None:
        self.sort_by = "correlation"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-sort-applied")
    async def on_sort_applied(self) -> None:
        self.sort_by = "applied"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-action-mute")
    async def on_action_mute(self) -> None:
        await self._run_selected_entry_action("mute")

    @on(Button.Pressed, "#ctf-mem-action-activate")
    async def on_action_activate(self) -> None:
        await self._run_selected_entry_action("activate")

    @on(Button.Pressed, "#ctf-mem-action-rollback")
    async def on_action_rollback(self) -> None:
        await self._run_selected_entry_action("rollback")

    @on(Button.Pressed, "#ctf-mem-action-delete")
    async def on_action_delete(self) -> None:
        if not self.selected_entry_id:
            return
        if self._armed_delete_entry_id != self.selected_entry_id:
            self._armed_delete_entry_id = self.selected_entry_id
            self.tui._add_system(
                f"[CTF memory] delete armed for {self.selected_entry_id}; click Delete again to confirm."
            )
            self._update_action_buttons()
            return
        await self._run_selected_entry_action("delete")

    @on(Button.Pressed, "#ctf-mem-action-export")
    async def on_action_export(self) -> None:
        await self._run_selected_entry_action("export")

    @on(Button.Pressed, "#ctf-mem-action-clear")
    async def on_action_clear(self) -> None:
        if not self._clear_armed:
            self._clear_armed = True
            self.tui._add_system("[CTF memory] clear armed; click Clear All again to confirm.")
            self._update_action_buttons()
            return
        await self._run_selected_entry_action("clear")

    async def reload_panel(self) -> None:
        from ..agents.pa_agent.strategy_memory import StrategyMemoryStore

        store = StrategyMemoryStore()
        stats = await store.stats(threshold=self.threshold)
        if self.filter_mode == "audit":
            self.entries = await store.audit_entries(
                threshold=self.threshold,
                sort_by=self.sort_by if self.sort_by != "recent" else "correlation",
            )
        else:
            manual_status = None if self.filter_mode == "all" else self.filter_mode
            self.entries = await store.list_entries(
                limit=50,
                manual_status=manual_status,
                sort_by=self.sort_by,
            )

        tree = self.query_one("#ctf-memory-tree", Tree)
        tree.root.remove_children()
        tree.root.show_root = False
        for entry in self.entries:
            label = (
                f"{entry.id} "
                f"[{entry.metadata.manual_status}] "
                f"applied={entry.metadata.applied_count} "
                f"corr={entry.metadata.success_correlation:.2f}"
            )
            tree.root.add(label, data={"entry_id": entry.id})

        valid_ids = {entry.id for entry in self.entries}
        if self.selected_entry_id not in valid_ids:
            self.selected_entry_id = None
            for preferred_id in self.preferred_entry_ids:
                if preferred_id in valid_ids:
                    self.selected_entry_id = preferred_id
                    break
            if self.selected_entry_id is None:
                self.selected_entry_id = self.entries[0].id if self.entries else None
        self._armed_delete_entry_id = None
        self._clear_armed = False

        summary = self.query_one("#ctf-memory-control-summary", Static)
        summary.update(
            "\n".join(
                [
                    f"view={self.filter_mode} sort={self.sort_by} threshold={self.threshold:.2f}",
                    f"stats total={stats['total']} active={stats['active']} muted={stats['muted']} deprecated={stats['deprecated']} audit_candidates={stats['audit_candidates']}",
                    self.tui._build_ctf_memory_panel_body(),
                ]
            )
        )
        self._update_detail()
        self._update_action_buttons()
        try:
            tree.focus()
        except Exception:
            pass

    def _selected_entry(self) -> Any | None:
        for entry in self.entries:
            if entry.id == self.selected_entry_id:
                return entry
        return None

    def _update_detail(self) -> None:
        detail = self.query_one("#ctf-memory-control-detail", Static)
        entry = self._selected_entry()
        if entry is None:
            detail.update("No entry selected.")
            return
        detail.update(self.tui._format_ctf_memory_entry_detail(entry))

    def _update_action_buttons(self) -> None:
        entry = self._selected_entry()
        has_entry = entry is not None
        for selector in (
            "#ctf-mem-action-mute",
            "#ctf-mem-action-activate",
            "#ctf-mem-action-rollback",
            "#ctf-mem-action-delete",
        ):
            try:
                self.query_one(selector, Button).disabled = not has_entry
            except Exception:
                pass
        try:
            delete_btn = self.query_one("#ctf-mem-action-delete", Button)
            delete_btn.label = (
                "Delete (confirm)"
                if has_entry and self._armed_delete_entry_id == self.selected_entry_id
                else "Delete"
            )
        except Exception:
            pass
        try:
            clear_btn = self.query_one("#ctf-mem-action-clear", Button)
            clear_btn.label = "Clear All (confirm)" if self._clear_armed else "Clear All"
        except Exception:
            pass

    async def _run_selected_entry_action(self, action: str) -> None:
        from ..agents.pa_agent.strategy_memory import StrategyMemoryStore

        store = StrategyMemoryStore()
        entry = self._selected_entry()
        target_id = entry.id if entry is not None else None

        if action in {"mute", "activate", "rollback", "delete"} and not target_id:
            self.tui._add_system("[CTF memory] no entry selected.")
            return

        message = ""
        if action == "mute":
            updated = await store.mute_entry(target_id or "")
            message = (
                f"[CTF memory] muted {target_id}" if updated is not None else f"[CTF memory] mute failed: {target_id}"
            )
        elif action == "activate":
            updated = await store.activate_entry(target_id or "")
            message = (
                f"[CTF memory] activated {target_id}" if updated is not None else f"[CTF memory] activate failed: {target_id}"
            )
        elif action == "rollback":
            updated = await store.rollback_mute(target_id or "")
            message = (
                f"[CTF memory] rollback applied to {target_id}" if updated is not None else f"[CTF memory] rollback failed: {target_id}"
            )
        elif action == "delete":
            deleted = await store.delete_entry(target_id or "")
            message = (
                f"[CTF memory] deleted {target_id}" if deleted else f"[CTF memory] delete failed: {target_id}"
            )
        elif action == "export":
            export_path = Path("loot") / "strategy_memory_export.json"
            exported = await store.export_entries(export_path)
            message = f"[CTF memory] exported to {exported}"
        elif action == "clear":
            count = await store.clear_entries()
            message = f"[CTF memory] cleared {count} entries"

        if message:
            self.tui._add_system(message)
        await self.reload_panel()


class TokenDiagnostics(Static):
    """Live token/cost diagnostics panel mounted into the chat area.

    Reads persisted daily usage from the token_tracker, computes cost
    using environment variables, and displays a simple ASCII progress bar.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._timer: Optional[Timer] = None

    def on_mount(self) -> None:
        # Refresh periodically for a lively display
        self._timer = self.set_interval(1.0, self.refresh)

    def on_unmount(self) -> None:
        if self._timer:
            self._timer.stop()

    def _bar(self, ratio: float, width: int = 28) -> str:
        """Block-style usage bar matching MemoryDiagnostics visuals."""
        r = max(0.0, min(1.0, ratio))
        filled = int(r * width)
        return "█" * filled + "░" * (width - filled)

    def render(self) -> Text:
        text = Text()
        try:
            import os

            # Lazy import of token_tracker (best-effort)
            try:
                from ..tools import token_tracker
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to import token_tracker: %s", e
                )
                try:
                    from ..interface.notifier import notify

                    notify("warning", f"TUI: token tracker import failed: {e}")
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about token_tracker import failure: %s",
                        e,
                    )
                token_tracker = None

            text.append("Token Usage Diagnostics\n", style="bold #d4d4d4")

            if not token_tracker:
                text.append(
                    "Token tracker not available (tools/token_tracker).\n",
                    style="#9a9a9a",
                )
                return text

            stats = token_tracker.get_stats_sync()

            # If a reset is pending (date changed), perform a reset now so daily
            # usage is accurate and visible to the user.
            reset_occurred = False
            if stats.get("reset_pending"):
                try:
                    token_tracker.record_usage_sync(0, 0)
                    stats = token_tracker.get_stats_sync()
                    reset_occurred = True
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Token tracker reset failed: %s", e
                    )
                    try:
                        from ..interface.notifier import notify

                        notify("warning", f"Token tracker reset failed: {e}")
                    except Exception as e:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about token tracker reset failure: %s",
                            e,
                        )

            # Extract values
            last_in = int(stats.get("last_input_tokens", 0) or 0)
            last_out = int(stats.get("last_output_tokens", 0) or 0)
            last_total = int(stats.get("last_total_tokens", 0) or 0)
            daily_usage = int(stats.get("daily_usage", 0) or 0)
            last_reset = stats.get("last_reset_date")
            current_date = stats.get("current_date")

            # (env parsing moved below)

            # Environment cost config
            def _parse_env(name: str):
                v = os.getenv(name)
                if v is None or v == "":
                    return None
                try:
                    return float(v)
                except Exception as e:
                    logging.getLogger(__name__).debug(
                        "Failed to parse env var %s: %s", name, e
                    )
                    return "INVALID"

            unified = _parse_env("COST_PER_MILLION")
            input_cost_per_m = _parse_env("INPUT_COST_PER_MILLION")
            output_cost_per_m = _parse_env("OUTPUT_COST_PER_MILLION")
            daily_limit = _parse_env("DAILY_TOKEN_LIMIT")

            # Determine if any env-based limits exist
            has_env_limits = any(
                v is not None
                for v in (unified, input_cost_per_m, output_cost_per_m, daily_limit)
            )

            # If nothing has been recorded yet (no tokens, no daily usage)
            # and no env limits are configured, show the concise sentinel only.
            if last_total == 0 and daily_usage == 0 and not has_env_limits:
                text.append("No token usage recorded\n", style="#9a9a9a")
                return text

            # Validate env vars
            env_errors = []
            if unified == "INVALID":
                env_errors.append("COST_PER_MILLION is not numeric")
            if input_cost_per_m == "INVALID":
                env_errors.append("INPUT_COST_PER_MILLION is not numeric")
            if output_cost_per_m == "INVALID":
                env_errors.append("OUTPUT_COST_PER_MILLION is not numeric")
            if daily_limit == "INVALID":
                env_errors.append("DAILY_TOKEN_LIMIT is not numeric")

            if env_errors:
                text.append("Environment configuration errors:\n", style="#ef4444")
                for e in env_errors:
                    text.append(f"  - {e}\n", style="#9a9a9a")
                text.append(
                    "\nSet environment variables correctly to compute costs.\n",
                    style="#9a9a9a",
                )
                return text

            # Compute costs
            if unified is not None:
                # Use unified cost for both input and output
                input_cost = (last_in / 1_000_000.0) * float(unified)
                output_cost = (last_out / 1_000_000.0) * float(unified)
            else:
                # Require per-direction costs to be present to compute
                if input_cost_per_m is None or output_cost_per_m is None:
                    text.append(
                        "Cost vars missing. Set COST_PER_MILLION or both INPUT_COST_PER_MILLION and OUTPUT_COST_PER_MILLION.\n",
                        style="#9a9a9a",
                    )
                    # Still show numeric token stats below
                    input_cost = output_cost = None
                else:
                    input_cost = (last_in / 1_000_000.0) * float(input_cost_per_m)
                    output_cost = (last_out / 1_000_000.0) * float(output_cost_per_m)

            total_cost = None
            if input_cost is not None and output_cost is not None:
                total_cost = input_cost + output_cost

            # Daily budget calculations per spec
            # Derive daily usage excluding last command (in case tracker already included it)
            daily_without_last = max(daily_usage - last_total, 0)
            new_daily_total = daily_without_last + last_total

            remaining_tokens = None
            percent_used = None
            if daily_limit is not None:
                try:
                    dl = float(daily_limit)
                    remaining_tokens = max(int(dl - new_daily_total), 0)
                    percent_used = (new_daily_total / max(1.0, dl)) * 100.0
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to compute daily limit values: %s", e
                    )
                    try:
                        from ..interface.notifier import notify

                        notify(
                            "warning", f"TUI: failed to compute daily token limit: {e}"
                        )
                    except Exception as e:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about daily limit computation failure: %s",
                            e,
                        )
                    remaining_tokens = None

            # Render structured panel with aligned labels and block bars
            bar_width = 28
            labels = [
                "Last command:",
                "Cost:",
                "Daily usage:",
                "Remaining:",
                "Usage:",
                "Last reset:",
                "Current date:",
                "Reset occurred:",
            ]
            label_width = max(len(label_text) for label_text in labels)

            # Last command tokens
            label = "Last command:".ljust(label_width)
            text.append(
                f"{label} in={last_in:,} out={last_out:,} total={last_total:,}\n",
                style="#9a9a9a",
            )

            # Cost line
            label = "Cost:".ljust(label_width)
            if input_cost is not None and output_cost is not None:
                text.append(
                    f"{label} in=${input_cost:.6f} out=${output_cost:.6f} total=${total_cost:.6f}\n",
                    style="#9a9a9a",
                )
            else:
                text.append(
                    f"{label} not computed (missing env vars)\n",
                    style="#9a9a9a",
                )

            # Daily usage
            label = "Daily usage:".ljust(label_width)
            text.append(f"{label} {new_daily_total:,}\n", style="#9a9a9a")

            # Remaining tokens
            label = "Remaining:".ljust(label_width)
            if remaining_tokens is not None:
                text.append(f"{label} {remaining_tokens:,}\n", style="#9a9a9a")
            else:
                text.append(
                    f"{label} N/A (DAILY_TOKEN_LIMIT not set)\n",
                    style="#9a9a9a",
                )

            # Usage percent + bar
            label = "Usage:".ljust(label_width)
            if percent_used is not None:
                bar = self._bar(percent_used / 100.0, width=bar_width)
                text.append(
                    f"{label} [{bar}] {percent_used:.1f}%\n",
                    style="#9a9a9a",
                )
            else:
                text.append(f"{label} N/A\n", style="#9a9a9a")

            # Dates
            label = "Last reset:".ljust(label_width)
            text.append(f"{label} {last_reset}\n", style="#9a9a9a")
            label = "Current date:".ljust(label_width)
            text.append(f"{label} {current_date}\n", style="#9a9a9a")

            # Reset occurrence
            label = "Reset occurred:".ljust(label_width)
            text.append(
                f"{label} {'Yes' if reset_occurred else 'No'}\n",
                style="#9a9a9a",
            )

        except Exception as e:
            text.append(f"Token diagnostics error: {e}\n", style="#9a9a9a")

        return text


# ----- Resize Divider -----


class ResizeDivider(Widget):
    """Draggable vertical divider between the chat area and the agents panel.

    Drag left to expand the agents panel; drag right to shrink it (giving more
    room back to the parent chat area).  Hidden when the agents panel is not
    visible.
    """

    DEFAULT_CSS = """
    ResizeDivider {
        width: 2;
        height: 100%;
        background: #1a1a1a;
        color: #3a3a3a;
        display: none;
        content-align: center middle;
    }
    ResizeDivider.visible {
        display: block;
    }
    ResizeDivider:hover {
        background: #262626;
        color: #7878b0;
    }
    ResizeDivider.dragging {
        background: #262626;
        color: #9090d0;
    }
    """

    # Each row renders this single character — a thin vertical bar.
    _CHAR_IDLE = "│"
    _CHAR_ACTIVE = "┃"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._dragging: bool = False
        self._start_x: int = 0
        self._start_width: int = 84

    def render(self) -> Text:
        char = self._CHAR_ACTIVE if self._dragging else self._CHAR_IDLE
        h = max(1, self.size.height)
        return Text("\n".join([char] * h), no_wrap=True, overflow="fold")

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._dragging = True
        self._start_x = event.screen_x
        try:
            panel = self.app.query_one("#agents-panel")
            self._start_width = panel.size.width
        except Exception:
            self._start_width = 84
        self.add_class("dragging")
        self.refresh()
        self.capture_mouse()
        event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._dragging:
            return
        # Drag left  → expand agents-panel (delta negative → new_width grows)
        # Drag right → shrink agents-panel (delta positive → new_width shrinks)
        delta = event.screen_x - self._start_x
        new_width = max(20, self._start_width - delta)
        try:
            panel = self.app.query_one("#agents-panel")
            panel.styles.width = new_width
        except Exception:
            pass
        event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._dragging:
            self._dragging = False
            self.remove_class("dragging")
            self.refresh()
            self.release_mouse()
        event.stop()
