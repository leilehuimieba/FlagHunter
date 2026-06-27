"""CTF strategy-memory panel + subcommands mixed into FlagHunterTUI (债池五波·TUI 刀13, god-class).

Extracted from tui.py. The ``/ctf memory`` sub-feature: the subcommand dispatcher,
brief/detail entry formatters, view-arg parser, the memory panel builder/shower,
preferred-entry-id selection, and trace-line extraction. Members call each other
plus stay-behind helpers (``self._add_system`` / ``self._render_last_ctf_memory``)
resolved at runtime through the FlagHunterTUI instance MRO. ``CTFMemoryControlPanel``
(tui_diagnostics, 刀5) and ``ScrollableContainer`` are the only non-self
module-level deps; persistence backends are lazy inside the bodies.
"""

from __future__ import annotations

from typing import Any

from textual.containers import ScrollableContainer

from .tui_diagnostics import CTFMemoryControlPanel


class CtfMemoryMixin:
    """/ctf memory panel + subcommand handling for FlagHunterTUI."""

    async def _handle_ctf_memory_subcommand(self, args: list[str]) -> str:
        if not args:
            return await self._render_last_ctf_memory()

        sub = str(args[0] or "").strip().lower()
        from ..agents.pa_agent.strategy_memory import StrategyMemoryStore

        store = StrategyMemoryStore()

        if sub == "list":
            limit = 10
            status, sort_by, threshold, extras = self._parse_ctf_memory_view_args(
                args[1:],
                default_sort="recent",
                default_threshold=0.3,
            )
            for token in extras:
                if token.isdigit():
                    limit = max(1, int(token))
            try:
                entries = await store.list_entries(
                    limit=limit,
                    manual_status=status,
                    sort_by=sort_by,
                )
            except TypeError:
                entries = await store.list_entries(
                    limit=limit,
                    manual_status=status,
                )
            if not entries:
                return "[CTF memory] 暂无记忆条目。"
            lines = [
                f"[CTF memory list] count={len(entries)} filter={status or 'all'} sort={sort_by} threshold={threshold:.2f}"
            ]
            for entry in entries:
                lines.append(self._format_ctf_memory_entry_brief(entry))
            return "\n".join(lines)

        if sub == "show":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory show <id>"
            entry = await store.get_entry(args[1])
            if entry is None:
                return f"[CTF memory] 未找到条目: {args[1]}"
            return self._format_ctf_memory_entry_detail(entry)

        if sub == "mute":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory mute <id>"
            entry = await store.mute_entry(args[1])
            if entry is None:
                return f"[CTF memory] mute 失败: {args[1]}"
            return (
                f"[CTF memory] muted {entry.id}\n"
                + self._format_ctf_memory_entry_brief(entry)
            )

        if sub == "activate":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory activate <id>"
            entry = await store.activate_entry(args[1])
            if entry is None:
                return f"[CTF memory] activate 失败: {args[1]}"
            return (
                f"[CTF memory] activated {entry.id}\n"
                + self._format_ctf_memory_entry_brief(entry)
            )

        if sub == "rollback":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory rollback <id>"
            entry = await store.rollback_mute(args[1])
            if entry is None:
                return f"[CTF memory] rollback 失败: {args[1]}"
            return (
                f"[CTF memory] rollback applied to {entry.id}\n"
                + self._format_ctf_memory_entry_brief(entry)
            )

        if sub == "audit":
            _, sort_by, threshold, _ = self._parse_ctf_memory_view_args(
                args[1:],
                default_sort="correlation",
                default_threshold=0.3,
            )
            try:
                entries = await store.audit_entries(
                    threshold=threshold,
                    sort_by=sort_by,
                )
            except TypeError:
                entries = await store.audit_entries(
                    threshold=threshold,
                )
            if not entries:
                return (
                    f"[CTF memory audit] 无需关注条目（threshold={threshold:.2f}, sort={sort_by}）"
                )
            lines = [
                f"[CTF memory audit] count={len(entries)} threshold={threshold:.2f} sort={sort_by}"
            ]
            for entry in entries:
                lines.append(self._format_ctf_memory_entry_brief(entry))
            return "\n".join(lines)

        if sub == "delete":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory delete <id>"
            deleted = await store.delete_entry(args[1])
            if not deleted:
                return f"[CTF memory] delete 失败: {args[1]}"
            return f"[CTF memory] deleted {args[1]}"

        if sub == "export":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory export <path>"
            exported = await store.export_entries(args[1])
            return f"[CTF memory] exported to {exported}"

        if sub == "clear":
            if len(args) < 2 or str(args[1]).strip().lower() != "confirm":
                return "[CTF memory] Usage: /ctf memory clear confirm"
            count = await store.clear_entries()
            return f"[CTF memory] cleared {count} entries"

        if sub == "panel":
            status, sort_by, threshold, _ = self._parse_ctf_memory_view_args(
                args[1:],
                default_sort="recent",
                default_threshold=0.3,
            )
            filter_mode = status or "all"
            if any(str(token or "").strip().lower() == "audit" for token in args[1:]):
                filter_mode = "audit"
            self._show_ctf_memory_panel(
                filter_mode=filter_mode,
                sort_by=sort_by,
                threshold=threshold,
            )
            return "[CTF memory] panel mounted."

        return (
            "[CTF memory] 用法:\n"
            "- /ctf memory\n"
            "- /ctf memory list [limit] [active|muted|deprecated|filter=<...>] [sort=recent|correlation|applied|last_used]\n"
            "- /ctf memory show <id>\n"
            "- /ctf memory mute <id>\n"
            "- /ctf memory activate <id>\n"
            "- /ctf memory rollback <id>\n"
            "- /ctf memory audit [threshold] [sort=correlation|recent|applied|last_used]\n"
            "- /ctf memory delete <id>\n"
            "- /ctf memory export <path>\n"
            "- /ctf memory clear confirm\n"
            "- /ctf memory panel [filter=all|active|muted|deprecated|audit] [sort=recent|correlation|applied|last_used] [threshold=0.3]"
        )

    def _format_ctf_memory_entry_brief(self, entry: Any) -> str:
        atomic_facts = list(getattr(entry, "atomic_facts", []) or [])
        fact_summary = ", ".join(str(item) for item in atomic_facts[:3]) or "none"
        return (
            f"- {entry.id} "
            f"status={entry.metadata.manual_status} "
            f"type={entry.fingerprint.detected_type} "
            f"win={entry.winning_hypothesis_kinds} "
            f"fail={entry.failed_hypothesis_kinds} "
            f"applied={entry.metadata.applied_count} "
            f"corr={entry.metadata.success_correlation:.2f} "
            f"facts={fact_summary}"
        )

    def _format_ctf_memory_entry_detail(self, entry: Any) -> str:
        lines = [
            f"[CTF memory show] {entry.id}",
            f"- status: {entry.metadata.manual_status}",
            f"- detected_type: {entry.fingerprint.detected_type}",
            f"- tech_stack: {entry.fingerprint.tech_stack}",
            f"- auth_mechanism: {entry.fingerprint.auth_mechanism}",
            f"- winning_hypothesis_kinds: {entry.winning_hypothesis_kinds}",
            f"- failed_hypothesis_kinds: {entry.failed_hypothesis_kinds}",
            f"- winning_primitive_sequence: {entry.winning_primitive_sequence}",
            f"- atomic_facts: {getattr(entry, 'atomic_facts', []) or []}",
            f"- learned_rules: {entry.learned_rules}",
            f"- applied_count: {entry.metadata.applied_count}",
            f"- successful_applications: {entry.metadata.successful_applications}",
            f"- failed_applications: {entry.metadata.failed_applications}",
            f"- success_correlation: {entry.metadata.success_correlation:.2f}",
            f"- confidence_decay_factor: {entry.metadata.confidence_decay_factor:.2f}",
            f"- challenge_url: {entry.challenge_url}",
        ]
        lines.extend(self._ctf_memory_entry_trace_lines(str(entry.id)))
        return "\n".join(lines)

    def _parse_ctf_memory_view_args(
        self,
        tokens: list[str],
        *,
        default_sort: str,
        default_threshold: float,
    ) -> tuple[str | None, str, float, list[str]]:
        status = None
        sort_by = default_sort
        threshold = default_threshold
        extras: list[str] = []

        for raw_token in tokens:
            token = str(raw_token or "").strip()
            lowered = token.lower()
            if lowered in {"active", "muted", "deprecated"}:
                status = lowered
            elif lowered == "audit":
                status = "audit"
            elif lowered.startswith("filter="):
                candidate = lowered.split("=", 1)[1].strip()
                if candidate in {"all", "active", "muted", "deprecated", "audit"}:
                    status = None if candidate == "all" else candidate
                else:
                    extras.append(token)
            elif lowered.startswith("sort="):
                candidate = lowered.split("=", 1)[1].strip()
                if candidate in {"recent", "correlation", "applied", "last_used"}:
                    sort_by = candidate
                else:
                    extras.append(token)
            elif lowered.startswith("threshold="):
                candidate = lowered.split("=", 1)[1].strip()
                try:
                    threshold = float(candidate)
                except ValueError:
                    extras.append(token)
            else:
                try:
                    threshold = float(token)
                except ValueError:
                    extras.append(token)

        return status, sort_by, threshold, extras

    def _show_ctf_memory_panel(
        self,
        *,
        filter_mode: str = "all",
        sort_by: str = "recent",
        threshold: float = 0.3,
        preferred_entry_ids: list[str] | None = None,
    ) -> None:
        preferred_ids = [
            str(entry_id).strip()
            for entry_id in (preferred_entry_ids or self._ctf_memory_preferred_entry_ids())
            if str(entry_id).strip()
        ]
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
        except Exception:
            self._add_system(self._build_ctf_memory_panel_body())
            return
        try:
            import uuid

            panel_id = f"ctf-memory-panel-{uuid.uuid4().hex}"
        except Exception:
            panel_id = None
        widget = CTFMemoryControlPanel(
            self,
            filter_mode=filter_mode,
            sort_by=sort_by,
            threshold=threshold,
            preferred_entry_ids=preferred_ids,
            id=panel_id,
        )
        scroll.mount(widget)
        try:
            scroll.scroll_end(animate=False)
        except Exception:
            pass

    def _build_ctf_memory_panel_body(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        stop_report = state.get("stop_report") or {}
        meta_reasonings = state.get("meta_reasonings") or []
        lines: list[str] = []
        if stop_report:
            lines.extend(
                [
                    f"reason: {stop_report.get('reason', '')}",
                    f"strongest_remaining_hypothesis: {stop_report.get('strongest_remaining_hypothesis', '')}",
                    f"memory_explanations: {' | '.join(stop_report.get('memory_explanations') or []) or 'none'}",
                    f"memory_focus_entry_ids: {', '.join(stop_report.get('memory_focus_entry_ids') or []) or 'none'}",
                    f"memory_quick_commands: {' | '.join(stop_report.get('memory_quick_commands') or []) or 'none'}",
                    f"recommended_memory_actions: {' | '.join(stop_report.get('recommended_memory_actions') or []) or 'none'}",
                    f"user_next_steps: {' | '.join(stop_report.get('user_next_steps') or []) or 'none'}",
                ]
            )
        audit = None
        wrong_flag_audit = None
        for item in reversed(meta_reasonings):
            if isinstance(item, dict) and item.get("type") == "strategy_memory_outcome_audit":
                audit = item
                break
        for item in reversed(meta_reasonings):
            if isinstance(item, dict) and item.get("type") == "strategy_memory_wrong_flag_audit":
                wrong_flag_audit = item
                break
        if audit:
            lines.append(
                f"matched_entry_ids: {audit.get('matched_entry_ids') or []}"
            )
            lines.append(
                f"suggested_mute_entry_ids: {audit.get('suggested_mute_entry_ids') or []}"
            )
            lines.append(
                f"auto_muted_entry_ids: {audit.get('auto_muted_entry_ids') or []}"
            )
            lines.append(
                f"rollback_candidate_entry_ids: {audit.get('rollback_candidate_entry_ids') or []}"
            )
        if wrong_flag_audit:
            lines.append(
                f"wrong_flag: {wrong_flag_audit.get('wrong_flag') or ''}"
            )
            lines.append(
                f"affected_entry_ids: {wrong_flag_audit.get('affected_entry_ids') or []}"
            )
            lines.append(
                f"deprecated_entry_id: {wrong_flag_audit.get('deprecated_entry_id') or ''}"
            )
            lines.append(
                f"auto_muted_entry_ids: {wrong_flag_audit.get('auto_muted_entry_ids') or []}"
            )
            lines.append(
                f"matched_atomic_facts: {wrong_flag_audit.get('matched_atomic_facts') or []}"
            )
        preferred_entry_ids = self._ctf_memory_preferred_entry_ids()
        if preferred_entry_ids:
            lines.append(f"focus_entry_ids: {preferred_entry_ids}")
        if not lines:
            lines.append("No StopReport / strategy-memory audit available yet.")
        return "\n".join(lines)

    def _ctf_memory_preferred_entry_ids(self) -> list[str]:
        state = getattr(self, "_last_ctf_state", None) or {}
        meta_reasonings = state.get("meta_reasonings") or []
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "strategy_memory_wrong_flag_audit":
                ordered: list[str] = []
                for key in ("affected_entry_ids", "matched_entry_ids", "auto_muted_entry_ids"):
                    for entry_id in list(item.get(key) or []):
                        normalized = str(entry_id).strip()
                        if normalized and normalized not in ordered:
                            ordered.append(normalized)
                deprecated = str(item.get("deprecated_entry_id") or "").strip()
                if deprecated and deprecated not in ordered:
                    ordered.append(deprecated)
                if ordered:
                    return ordered
            if item.get("type") == "strategy_memory_outcome_audit":
                ordered = [
                    str(entry_id).strip()
                    for entry_id in list(item.get("matched_entry_ids") or [])
                    if str(entry_id).strip()
                ]
                if ordered:
                    return ordered
        return []

    def _ctf_memory_entry_trace_lines(self, entry_id: str) -> list[str]:
        normalized_entry_id = str(entry_id or "").strip()
        if not normalized_entry_id:
            return []
        state = getattr(self, "_last_ctf_state", None) or {}
        meta_reasonings = state.get("meta_reasonings") or []
        lines: list[str] = []
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "strategy_memory_wrong_flag_audit":
                affected = {
                    str(candidate).strip()
                    for candidate in (
                        list(item.get("affected_entry_ids") or [])
                        + list(item.get("matched_entry_ids") or [])
                        + list(item.get("auto_muted_entry_ids") or [])
                    )
                    if str(candidate).strip()
                }
                deprecated = str(item.get("deprecated_entry_id") or "").strip()
                if deprecated:
                    affected.add(deprecated)
                if normalized_entry_id in affected:
                    lines.append(
                        f"- related_wrong_flag: {item.get('wrong_flag') or ''}"
                    )
                    lines.append(
                        f"- related_atomic_facts: {item.get('matched_atomic_facts') or []}"
                    )
                    trace_items = list(item.get("memory_trace") or [])
                    if trace_items:
                        lines.append(f"- related_memory_trace: {trace_items}")
                    break
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict) or item.get("type") != "strategy_memory_audit":
                continue
            for matched in list(item.get("matched_entries") or []):
                if not isinstance(matched, dict):
                    continue
                if str(matched.get("id") or "").strip() != normalized_entry_id:
                    continue
                lines.append(
                    f"- last_similarity: {matched.get('similarity', '')}"
                )
                lines.append(
                    f"- matched_atomic_facts: {matched.get('atomic_facts') or []}"
                )
                return lines
        return lines
