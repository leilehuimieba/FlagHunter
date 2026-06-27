"""CTF panel renderers mixed into FlagHunterTUI (债池五波·TUI 刀 15, god-class).

Extracted from tui.py. The read-only ``_render_last_ctf_*`` text builders behind the
/ctf status panels: stop-report, reasoning trace, capabilities, status, run-queue,
strategy-memory (async), plus ``_ctf_state_flag_value`` and the flag-bucket renderer.
They read ``self`` CTF state and call stay-behind helpers, all resolved at runtime
through the FlagHunterTUI instance MRO. Only ``Any`` / ``json`` are module-level deps;
``StrategyMemoryStore`` is lazy inside ``_render_last_ctf_memory``. No decorators.
"""

from __future__ import annotations

import json
from typing import Any


class CtfRenderMixin:
    """CTF status-panel text renderers for FlagHunterTUI."""

    def _render_last_ctf_stop_report(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        if not state:
            return "[CTF StopReport]\n- unavailable: 请先执行一次 /ctf 题目。"

        stop_report = dict(state.get("stop_report") or {})
        if not stop_report:
            return "[CTF StopReport]\n- unavailable: 当前还没有 stop_report。"

        def _flag_values(field_name: str, fallback_bucket: str) -> list[str]:
            values = [
                str(item).strip()
                for item in list(stop_report.get(field_name) or [])
                if str(item).strip()
            ]
            if values:
                return values
            return [
                self._ctf_state_flag_value(item)
                for item in list(state.get(fallback_bucket) or [])
                if self._ctf_state_flag_value(item)
            ]

        lines = [
            "[CTF StopReport]",
            f"- reason: {stop_report.get('reason', '')}",
            f"- strongest_remaining_hypothesis: {stop_report.get('strongest_remaining_hypothesis', '') or 'n/a'}",
            f"- why_not_pursued: {stop_report.get('why_not_pursued', '') or 'n/a'}",
            f"- candidate_flags: {', '.join(_flag_values('candidate_flags', 'candidate_flags')) or 'none'}",
            f"- runtime_flags: {', '.join(_flag_values('runtime_flags', 'runtime_flags')) or 'none'}",
            f"- verified_flags: {', '.join(_flag_values('verified_flags', 'verified_flags')) or 'none'}",
            f"- rejected_flags: {', '.join(_flag_values('rejected_flags', 'rejected_flags')) or 'none'}",
            f"- missing_capabilities: {', '.join(stop_report.get('missing_capabilities') or []) or 'none'}",
            f"- memory_explanations: {' | '.join(stop_report.get('memory_explanations') or []) or 'none'}",
            f"- memory_focus_entry_ids: {', '.join(stop_report.get('memory_focus_entry_ids') or []) or 'none'}",
            f"- memory_quick_commands: {' | '.join(stop_report.get('memory_quick_commands') or []) or 'none'}",
            f"- recommended_memory_actions: {' | '.join(stop_report.get('recommended_memory_actions') or []) or 'none'}",
            f"- user_next_steps: {' | '.join(stop_report.get('user_next_steps') or []) or 'none'}",
        ]
        return "\n".join(lines)

    def _render_last_ctf_reasoning(self, *, mode: str = "summary", limit: int = 5) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        if not state:
            return "[CTF] 暂无 reasoning：请先执行一次 /ctf 题目。"

        pre_action_reasonings = state.get("pre_action_reasonings") or []
        stop_report = state.get("stop_report") or {}
        surprises = state.get("surprises") or []
        retrospectives = state.get("retrospectives") or []
        meta_reasonings = state.get("meta_reasonings") or []

        limit = max(1, int(limit))

        if mode == "surprises":
            if not surprises:
                return "[CTF reasoning surprises]\n- no surprises recorded"
            lines = ["[CTF reasoning surprises]"]
            for item in list(surprises)[-limit:]:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('id', 'surprise')}: {item.get('actual_result_summary', '')}"
                    )
                else:
                    lines.append(f"- {item}")
            return "\n".join(lines)

        if mode == "postmortem":
            if not retrospectives:
                return "[CTF reasoning postmortem]\n- no retrospectives recorded"
            lines = ["[CTF reasoning postmortem]"]
            for item in list(retrospectives)[-limit:]:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('id', 'retro')}: {item.get('failure_root_cause', '')}"
                    )
                else:
                    lines.append(f"- {item}")
            return "\n".join(lines)

        lines = ["[CTF reasoning]"]
        if pre_action_reasonings:
            selected = list(pre_action_reasonings)[-limit:]
            for idx, item in enumerate(selected, start=1):
                if not isinstance(item, dict):
                    lines.append(f"- reasoning[{idx}]: {item}")
                    continue
                prefix = "" if len(selected) == 1 else f"[pre_action_reasoning {idx}/{len(selected)}]"
                if prefix:
                    lines.append(prefix)
                lines.extend(
                    [
                        f"- current_belief: {item.get('current_belief', '')}",
                        f"- action_rationale: {item.get('action_rationale', '')}",
                        f"- expected_success: {item.get('expected_success_signal', '')}",
                        f"- expected_failure: {item.get('expected_failure_signal', '')}",
                    ]
                )
        if surprises:
            latest_surprise = surprises[-1]
            lines.extend(
                [
                    f"- surprises: {len(surprises)}",
                    f"- latest_surprise: {latest_surprise.get('actual_result_summary', '')}",
                ]
            )
        if stop_report:
            lines.extend(
                [
                    "[CTF stop_report]",
                    f"- reason: {stop_report.get('reason', '')}",
                    f"- strongest_remaining_hypothesis: {stop_report.get('strongest_remaining_hypothesis', '')}",
                    f"- memory_explanations: {' | '.join(stop_report.get('memory_explanations') or [])}",
                    f"- memory_focus_entry_ids: {' | '.join(stop_report.get('memory_focus_entry_ids') or [])}",
                    f"- memory_quick_commands: {' | '.join(stop_report.get('memory_quick_commands') or [])}",
                    f"- recommended_memory_actions: {' | '.join(stop_report.get('recommended_memory_actions') or [])}",
                    f"- user_next_steps: {' | '.join(stop_report.get('user_next_steps') or [])}",
                ]
            )
        lines.extend(self._render_ctf_flag_buckets(state))
        for item in reversed(meta_reasonings):
            if isinstance(item, dict) and item.get("type") == "flag_submit_attempt":
                lines.extend(
                    [
                        "[CTF submit_attempt]",
                        f"- source: {item.get('source', '')}",
                        f"- success: {item.get('success')} correct: {item.get('correct')}",
                        f"- message: {item.get('message', '') or item.get('error', '')}",
                    ]
                )
                break
        for item in reversed(meta_reasonings):
            if isinstance(item, dict) and item.get("type") == "platform_profile_snapshot":
                lines.extend(
                    [
                        "[CTF platform]",
                        f"- platform_type: {item.get('platform_type', '')}",
                        f"- challenge_id: {item.get('challenge_id', '') or 'unknown'}",
                        f"- auto_submit: {item.get('auto_submit')}",
                    ]
                )
                break
        for item in reversed(meta_reasonings):
            if isinstance(item, dict) and item.get("type") == "platform_challenge_alignment":
                lines.append(
                    f"- platform_alignment: matched={item.get('matched')} solved={item.get('already_solved')} challenge={item.get('challenge_name', '')}"
                )
                break
        if retrospectives:
            latest_retro = retrospectives[-1]
            if isinstance(latest_retro, dict):
                lines.append(
                    f"- latest_retrospective: {latest_retro.get('failure_root_cause', '')}"
                )
        return "\n".join(lines)

    def _render_last_ctf_capabilities(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        capabilities = state.get("capabilities") or {}
        primitives = capabilities.get("primitives") or {}
        if not primitives:
            return "[CTF] 暂无 capability 快照：请先执行一次 /ctf 题目。"

        lines = ["[CTF capabilities]"]
        for name, primitive in list(primitives.items())[:8]:
            best = primitive.get("best_available") or {}
            impl = best.get("method") or "none"
            quality = best.get("quality") or "n/a"
            lines.append(
                f"- {name}: implementation={impl} quality={quality}"
            )
        return "\n".join(lines)

    def _render_last_ctf_status(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        if not state:
            return "[CTF] 暂无 status：请先执行一次 /ctf 题目。"

        meta_reasonings = state.get("meta_reasonings") or []
        profile = None
        sync = None
        submit_attempt = None
        alignment = None
        submit_gate = None
        queue_snapshot = None
        autonomy_summary = None
        stop_summary = None
        queue_switch = None
        switch_carryover = None
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if profile is None and item.get("type") == "platform_profile_snapshot":
                profile = item
            if sync is None and item.get("type") == "platform_sync_snapshot":
                sync = item
            if submit_attempt is None and item.get("type") == "flag_submit_attempt":
                submit_attempt = item
            if alignment is None and item.get("type") == "platform_challenge_alignment":
                alignment = item
            if submit_gate is None and item.get("type") == "submit_gate_decision":
                submit_gate = item
            if queue_snapshot is None and item.get("type") == "platform_task_queue_snapshot":
                queue_snapshot = item
            if autonomy_summary is None and item.get("type") == "platform_autonomy_run_summary":
                autonomy_summary = item
            if stop_summary is None and item.get("type") == "platform_run_stop_summary":
                stop_summary = item
            if queue_switch is None and item.get("type") == "platform_queue_switch_decision":
                queue_switch = item
            if switch_carryover is None and item.get("type") == "platform_switch_carryover_context":
                switch_carryover = item
            if (
                profile
                and sync
                and submit_attempt
                and alignment
                and submit_gate
                and queue_snapshot
                and autonomy_summary
            ):
                break

        if queue_switch is None and switch_carryover is not None:
            queue_switch = {
                "switch_reason": switch_carryover.get("switch_reason", ""),
                "switch_source": switch_carryover.get("switch_source", ""),
                "next_challenge_id": switch_carryover.get("challenge_id", ""),
                "next_url": switch_carryover.get("current_url", ""),
                "skipped_candidates": list(switch_carryover.get("skipped_candidates") or []),
            }

        stop_report = state.get("stop_report") or {}
        lines = ["[CTF status]"]
        if profile:
            lines.extend(
                [
                    f"- platform_type: {profile.get('platform_type', '')}",
                    f"- base_url: {profile.get('base_url', '')}",
                    f"- challenge_id: {profile.get('challenge_id', '') or 'unknown'}",
                    f"- auto_submit: {profile.get('auto_submit')}",
                ]
            )
        if sync:
            lines.extend(
                [
                    "[platform sync]",
                    f"- success: {sync.get('success')}",
                    f"- challenge_count: {sync.get('challenge_count')}",
                    f"- scoreboard_keys: {sync.get('scoreboard_keys') or []}",
                    f"- sync_error: {sync.get('error') or sync.get('challenge_error') or sync.get('scoreboard_error') or ''}",
                ]
            )
        if alignment:
            lines.extend(
                [
                    "[challenge alignment]",
                    f"- matched: {alignment.get('matched')} reason={alignment.get('match_reason', '')}",
                    f"- challenge_name: {alignment.get('challenge_name', '')}",
                    f"- already_solved: {alignment.get('already_solved')}",
                    f"- confidence: {alignment.get('confidence')}",
                ]
            )
        if submit_gate:
            lines.extend(
                [
                    "[submit gate]",
                    f"- allow: {submit_gate.get('allow')} reason={submit_gate.get('reason', '')}",
                    f"- source: {submit_gate.get('evidence_source', '')}",
                ]
            )
        if queue_snapshot:
            lines.extend(
                [
                    "[platform queue]",
                    f"- total: {queue_snapshot.get('total')} unsolved: {queue_snapshot.get('unsolved_count')} solved: {queue_snapshot.get('solved_count')}",
                    f"- next: {queue_snapshot.get('next_challenge_id') or ''} {queue_snapshot.get('next_challenge_name') or ''}",
                    f"- rate_limited_until: {queue_snapshot.get('rate_limited_until')}",
                ]
            )
        if autonomy_summary:
            config = autonomy_summary.get("config") or {}
            lines.extend(
                [
                    "[autonomy runner]",
                    f"- mode: {config.get('mode', '')}",
                    f"- challenges: {autonomy_summary.get('challenge_count')} solved={autonomy_summary.get('solved_count')} blocked={autonomy_summary.get('blocked_count')} skipped={autonomy_summary.get('skipped_count')}",
                    f"- switched: {autonomy_summary.get('switched_count')} consecutive_stops={autonomy_summary.get('consecutive_stops')}",
                    f"- elapsed_seconds: {autonomy_summary.get('elapsed_seconds')} end_reason={autonomy_summary.get('end_reason', '')}",
                ]
            )
            if int(autonomy_summary.get("resume_count") or 0) > 0:
                lines.append(
                    f"- resumed: count={autonomy_summary.get('resume_count')} from_records={autonomy_summary.get('resumed_from_record_count', 0)} reason={autonomy_summary.get('resume_reason', '')}"
                )
            if autonomy_summary.get("last_switch_reason") or autonomy_summary.get(
                "last_switch_source"
            ):
                lines.append(
                    f"- last_switch: reason={autonomy_summary.get('last_switch_reason', '')} source={autonomy_summary.get('last_switch_source', '')}"
                )
        if stop_summary:
            last_record = stop_summary.get("last_record") or {}
            lines.extend(
                [
                    "[platform run stop]",
                    f"- end_reason: {stop_summary.get('end_reason', '')}",
                    f"- blocked_reasons: {stop_summary.get('blocked_reasons') or []}",
                    f"- skip_reasons: {stop_summary.get('skip_reasons') or []}",
                ]
            )
            if int(stop_summary.get("resume_count") or 0) > 0:
                lines.append(
                    f"- resume_context: count={stop_summary.get('resume_count')} reason={stop_summary.get('resume_reason', '')}"
                )
            if last_record:
                lines.append(
                    f"- last_record: {last_record.get('challenge_id', '') or 'unknown'} outcome={last_record.get('outcome', '')} reason={last_record.get('reason', '')}"
                )
        if queue_switch:
            lines.extend(
                [
                    "[queue switch]",
                    f"- reason: {queue_switch.get('switch_reason', '')}",
                    f"- source: {queue_switch.get('switch_source', '')}",
                    f"- next_challenge_id: {queue_switch.get('next_challenge_id', '')}",
                    f"- skipped_candidates: {len(queue_switch.get('skipped_candidates') or [])}",
                ]
            )
        if submit_attempt:
            lines.extend(
                [
                    "[latest submit]",
                    f"- source: {submit_attempt.get('source', '')}",
                    f"- success: {submit_attempt.get('success')} correct: {submit_attempt.get('correct')}",
                    f"- message: {submit_attempt.get('message', '') or submit_attempt.get('error', '')}",
                ]
            )
        if stop_report:
            lines.append(f"- stop_reason: {stop_report.get('reason', '')}")
        return "\n".join(lines)

    def _render_last_ctf_queue(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        if not state:
            return "[CTF] 暂无 queue：请先执行一次 /ctf 题目。"

        snapshot = None
        for item in reversed(state.get("meta_reasonings") or []):
            if isinstance(item, dict) and item.get("type") == "platform_task_queue_snapshot":
                snapshot = item
                break
        if not snapshot:
            return "[CTF queue] 暂无平台队列快照。"

        lines = [
            "[CTF queue]",
            f"- platform_type: {snapshot.get('platform_type', '')}",
            f"- total: {snapshot.get('total')} unsolved: {snapshot.get('unsolved_count')} solved: {snapshot.get('solved_count')}",
            f"- next: {snapshot.get('next_challenge_id') or ''} {snapshot.get('next_challenge_name') or ''}",
            f"- rate_limited_until: {snapshot.get('rate_limited_until')}",
        ]
        for task in list(snapshot.get("tasks") or [])[:8]:
            if not isinstance(task, dict):
                continue
            lines.append(
                f"- [{task.get('challenge_id')}] {task.get('name')} solved={task.get('solved')} score={task.get('priority_score')} reason={task.get('priority_reason')}"
            )
        return "\n".join(lines)

    async def _render_last_ctf_memory(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        meta_reasonings = state.get("meta_reasonings") or []
        lines = ["[CTF strategy_memory]"]

        audit = None
        outcome_audit = None
        wrong_feedback_audit = None
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if audit is None and item.get("type") == "strategy_memory_audit":
                audit = item
            if outcome_audit is None and item.get("type") == "strategy_memory_outcome_audit":
                outcome_audit = item
            if wrong_feedback_audit is None and item.get("type") == "strategy_memory_wrong_flag_audit":
                wrong_feedback_audit = item
            if audit and outcome_audit and wrong_feedback_audit:
                break

        if audit:
            lines.append(
                "- adjustments: "
                + json.dumps(audit.get("adjustments") or {}, ensure_ascii=False)
            )
            matched = audit.get("matched_entries") or []
            for item in matched[:3]:
                lines.append(
                    f"- match {item.get('id')}: similarity={item.get('similarity')} win={item.get('winning_hypothesis_kinds')} fail={item.get('failed_hypothesis_kinds')}"
                )
        else:
            lines.append("- adjustments: none")

        if outcome_audit:
            lines.append(
                f"- last_outcome: solved={outcome_audit.get('solved')} matched_entry_ids={outcome_audit.get('matched_entry_ids')}"
            )
        if wrong_feedback_audit:
            lines.append(
                f"- wrong_flag_feedback: rejected={wrong_feedback_audit.get('wrong_flag')} affected={wrong_feedback_audit.get('affected_entry_ids') or []}"
            )
            deprecated_entry_id = wrong_feedback_audit.get("deprecated_entry_id")
            if deprecated_entry_id:
                lines.append(f"- deprecated_session_entry: {deprecated_entry_id}")

        try:
            from ..agents.pa_agent.strategy_memory import StrategyMemoryStore

            store = StrategyMemoryStore()
            recent_entries = await store.list_entries(limit=3)
            if recent_entries:
                lines.append("[recent entries]")
                for entry in recent_entries:
                    lines.append(
                        f"- {entry.id}: type={entry.fingerprint.detected_type} win={entry.winning_hypothesis_kinds} fail={entry.failed_hypothesis_kinds} applied={entry.metadata.applied_count} corr={entry.metadata.success_correlation:.2f}"
                    )
        except Exception as exc:
            lines.append(f"- recent_entries_error: {exc}")

        return "\n".join(lines)

    def _ctf_state_flag_value(self, record: Any) -> str:
        if isinstance(record, dict):
            return str(record.get("value") or "").strip()
        return str(record or "").strip()

    def _render_ctf_flag_buckets(self, state: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        rendered = False
        for bucket_name, label in (
            ("candidate_flags", "candidate"),
            ("runtime_flags", "runtime"),
            ("verified_flags", "verified"),
            ("rejected_flags", "rejected"),
        ):
            values = [
                self._ctf_state_flag_value(item)
                for item in list(state.get(bucket_name) or [])
                if self._ctf_state_flag_value(item)
            ]
            if not values and not rendered:
                continue
            if not rendered:
                lines.append("[CTF flags]")
                rendered = True
            lines.append(f"- {label}: {', '.join(values) if values else 'none'}")
        return lines
