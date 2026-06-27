"""CTF flag verify/override/reject feedback mixed into FlagHunterTUI (债池五波·TUI 刀 16, god-class).

Extracted from tui.py. The user-driven CTF flag-correction feature: apply a user hint,
mark the last flag verified / rejected, rebuild the override / wrong-flag stop reports,
and the ``_apply_ctf_override_flag`` / async ``_apply_ctf_wrong_flag_feedback`` drivers.
Members call each other plus stay-behind helpers (``self._add_*`` / ``_render_last_ctf_*``)
resolved at runtime through the FlagHunterTUI instance MRO; stay-behind callers in the
command parsers (``await self._apply_ctf_wrong_flag_feedback``) resolve the same way.
Only ``Any`` is a module-level dep; CTFState / ReasoningLayer / StrategyMemoryStore are
lazy inside the bodies. No decorators.
"""

from __future__ import annotations

from typing import Any


class CtfApplyMixin:
    """CTF flag verify/override/reject feedback for FlagHunterTUI."""

    def _apply_ctf_user_hint(self, user_hint: str) -> str:
        state = getattr(self, "_last_ctf_state", None)
        last_ctx = getattr(self, "_last_ctf_context", None) or {}
        merged_hint = self._merge_ctf_hint_text(last_ctx.get("hint", ""), user_hint)
        if last_ctx:
            last_ctx["hint"] = merged_hint
            self._last_ctf_context = last_ctx

        if not isinstance(state, dict):
            return merged_hint

        observations = list(state.get("observations") or [])
        observations.append(
            {
                "kind": "user_hint",
                "value": user_hint,
                "source": "operator",
                "metadata": {"priority": "high"},
            }
        )
        state["observations"] = observations

        meta_reasonings = list(state.get("meta_reasonings") or [])
        meta_reasonings.append(
            {
                "type": "user_hint",
                "hint": user_hint,
                "priority": "high",
            }
        )
        state["meta_reasonings"] = meta_reasonings

        stop_report = dict(state.get("stop_report") or {})
        next_steps = list(stop_report.get("user_next_steps") or [])
        next_steps.insert(0, f"已接收用户 hint：{user_hint}")
        deduped_steps: list[str] = []
        seen_steps: set[str] = set()
        for step in next_steps:
            normalized = str(step).strip()
            if not normalized or normalized in seen_steps:
                continue
            seen_steps.add(normalized)
            deduped_steps.append(normalized)
        stop_report["user_next_steps"] = deduped_steps
        state["stop_report"] = stop_report
        return merged_hint

    def _mark_last_ctf_flag_verified(self, override_flag: str) -> None:
        state = getattr(self, "_last_ctf_state", None)
        if not isinstance(state, dict):
            return

        normalized = str(override_flag or "").strip()
        if not normalized:
            return

        for bucket_name in ("candidate_flags", "runtime_flags", "verified_flags", "rejected_flags"):
            bucket = list(state.get(bucket_name) or [])
            state[bucket_name] = [
                item for item in bucket if self._ctf_state_flag_value(item) != normalized
            ]

        verified_bucket = list(state.get("verified_flags") or [])
        verified_bucket.append(
            {
                "value": normalized,
                "level": "verified",
                "evidence_source": "user-override",
                "rationale": "flag explicitly promoted by user override",
                "confidence": 1.0,
                "requires_followup": False,
                "metadata": {"manual_override": True},
            }
        )
        state["verified_flags"] = verified_bucket

    def _rebuild_override_stop_report(self, override_flag: str) -> dict[str, Any]:
        state = getattr(self, "_last_ctf_state", None) or {}
        last_ctx = getattr(self, "_last_ctf_context", None) or {}

        try:
            from ..agents.pa_agent.ctf_state import CTFState
            from ..agents.pa_agent.reasoning import ReasoningLayer

            temp_state = CTFState(
                target=str(state.get("target") or last_ctx.get("url") or ""),
                goal=str(last_ctx.get("goal") or "拿到flag"),
                detected_type=state.get("detected_type"),
            )
            for bucket_name, level in (
                ("candidate_flags", "candidate"),
                ("runtime_flags", "runtime"),
                ("verified_flags", "verified"),
                ("rejected_flags", "rejected"),
            ):
                for item in state.get(bucket_name) or []:
                    value = self._ctf_state_flag_value(item)
                    if not value:
                        continue
                    temp_state.add_flag(
                        value,
                        level=level,  # type: ignore[arg-type]
                        evidence_source="restored-state",
                        rationale="rebuilt from persisted ctf state",
                    )
            temp_state.meta_reasonings = list(state.get("meta_reasonings") or [])
            report = ReasoningLayer().generate_stop_report(
                temp_state,
                reason="flag_verified",
                missing_capabilities=[],
            ).to_dict()
        except Exception:
            report = {
                "reason": "flag_verified",
                "candidate_flags": [],
                "runtime_flags": [],
                "verified_flags": [override_flag],
                "rejected_flags": [],
                "strongest_remaining_hypothesis": None,
                "why_not_pursued": "operator override promoted a flag to verified",
                "missing_capabilities": [],
                "degradation_events": [],
                "surprises": list(state.get("surprises") or []),
                "recommended_memory_actions": [],
                "user_next_steps": [
                    "该 flag 已由用户 override 为 verified；如平台仍拒绝，请立刻执行 `/ctf wrong <flag>`。",
                ],
            }

        previous = state.get("stop_report") or {}
        if not report.get("strongest_remaining_hypothesis"):
            report["strongest_remaining_hypothesis"] = previous.get(
                "strongest_remaining_hypothesis"
            )
        user_steps = list(report.get("user_next_steps") or [])
        user_steps.insert(
            0,
            f"该 flag 已由用户 override 为 verified：{override_flag}",
        )
        report["user_next_steps"] = [
            step
            for idx, step in enumerate(user_steps)
            if str(step).strip() and step not in user_steps[:idx]
        ]
        return report

    def _apply_ctf_override_flag(self, override_flag: str) -> str:
        state = getattr(self, "_last_ctf_state", None)
        if not isinstance(state, dict):
            return (
                f"[CTF override]\n"
                f"- verified_flag: {override_flag}\n"
                "- 当前还没有上一轮 /ctf 状态；已仅持久化 override flag。"
            )

        self._mark_last_ctf_flag_verified(override_flag)
        meta_reasonings = list(state.get("meta_reasonings") or [])
        meta_reasonings.append(
            {
                "type": "user_flag_override",
                "flag": override_flag,
                "decision": "verified",
                "source": "operator",
            }
        )
        state["meta_reasonings"] = meta_reasonings
        state["stop_report"] = self._rebuild_override_stop_report(override_flag)

        last_result = getattr(self, "_last_ctf_result", None)
        try:
            if last_result is not None:
                setattr(last_result, "success", True)
                setattr(last_result, "flag", override_flag)
                setattr(last_result, "reason", "flag_verified")
        except Exception:
            pass

        report = state.get("stop_report") or {}
        lines = [
            "[CTF override]",
            f"- verified_flag: {override_flag}",
            f"- reason: {report.get('reason') or 'flag_verified'}",
            f"- strongest_remaining_hypothesis: {report.get('strongest_remaining_hypothesis') or 'n/a'}",
            f"- user_next_steps: {' | '.join(report.get('user_next_steps') or []) or 'none'}",
        ]
        return "\n".join(lines)

    def _mark_last_ctf_flag_rejected(self, wrong_flag: str) -> None:
        state = getattr(self, "_last_ctf_state", None)
        if not isinstance(state, dict):
            return

        normalized = str(wrong_flag or "").strip()
        if not normalized:
            return

        for bucket_name in ("candidate_flags", "runtime_flags", "verified_flags", "rejected_flags"):
            bucket = list(state.get(bucket_name) or [])
            state[bucket_name] = [
                item for item in bucket if self._ctf_state_flag_value(item) != normalized
            ]

        rejected_bucket = list(state.get("rejected_flags") or [])
        rejected_bucket.append(
            {
                "value": normalized,
                "level": "rejected",
                "evidence_source": "user-feedback",
                "rationale": "flag explicitly rejected by user feedback",
                "confidence": 1.0,
                "requires_followup": False,
                "metadata": {},
            }
        )
        state["rejected_flags"] = rejected_bucket

    def _rebuild_wrong_flag_stop_report(self, wrong_flag: str) -> dict[str, Any]:
        state = getattr(self, "_last_ctf_state", None) or {}
        last_ctx = getattr(self, "_last_ctf_context", None) or {}

        try:
            from ..agents.pa_agent.ctf_state import CTFState
            from ..agents.pa_agent.reasoning import ReasoningLayer

            temp_state = CTFState(
                target=str(state.get("target") or last_ctx.get("url") or ""),
                goal=str(last_ctx.get("goal") or "拿到flag"),
                detected_type=state.get("detected_type"),
            )
            for bucket_name, level in (
                ("candidate_flags", "candidate"),
                ("runtime_flags", "runtime"),
                ("verified_flags", "verified"),
                ("rejected_flags", "rejected"),
            ):
                for item in state.get(bucket_name) or []:
                    value = self._ctf_state_flag_value(item)
                    if not value:
                        continue
                    temp_state.add_flag(
                        value,
                        level=level,  # type: ignore[arg-type]
                        evidence_source="restored-state",
                        rationale="rebuilt from persisted ctf state",
                    )
            temp_state.meta_reasonings = list(state.get("meta_reasonings") or [])
            report = ReasoningLayer().generate_stop_report(
                temp_state,
                reason=f"wrong flag feedback: {wrong_flag}",
                missing_capabilities=[],
            ).to_dict()
        except Exception:
            report = {
                "reason": "wrong_flag_feedback",
                "candidate_flags": [],
                "runtime_flags": [],
                "verified_flags": [],
                "rejected_flags": [wrong_flag],
                "strongest_remaining_hypothesis": None,
                "why_not_pursued": None,
                "missing_capabilities": [],
                "degradation_events": [],
                "surprises": list(state.get("surprises") or []),
                "recommended_memory_actions": [
                    "执行 `/ctf memory audit 0.60 sort=correlation`，优先检查错误 flag 后相关性最低的记忆条目。"
                ],
                "user_next_steps": [
                    "已确认前一个 flag 错误；不要再把它视为成功终点。",
                    "优先沿最近一次 runtime-backed 原语继续深挖。",
                ],
            }

        previous = state.get("stop_report") or {}
        if not report.get("strongest_remaining_hypothesis"):
            report["strongest_remaining_hypothesis"] = previous.get(
                "strongest_remaining_hypothesis"
            )
        return report

    async def _apply_ctf_wrong_flag_feedback(self, wrong_flag: str) -> str:
        state = getattr(self, "_last_ctf_state", None)
        if not isinstance(state, dict):
            return (
                f"[CTF wrong-flag recovery]\n"
                f"- rejected_flag: {wrong_flag}\n"
                "- 当前还没有上一轮 /ctf 状态；已仅持久化 wrong flag。"
            )

        self._mark_last_ctf_flag_rejected(wrong_flag)
        meta_reasonings = list(state.get("meta_reasonings") or [])
        matched_entry_ids: list[str] = []
        session_entry_id: str | None = None
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if not matched_entry_ids and item.get("type") == "strategy_memory_outcome_audit":
                matched_entry_ids = [
                    str(entry_id).strip()
                    for entry_id in (item.get("matched_entry_ids") or [])
                    if str(entry_id).strip()
                ]
            if session_entry_id is None and item.get("type") == "strategy_memory_session_entry":
                candidate = str(item.get("entry_id") or "").strip()
                if candidate:
                    session_entry_id = candidate
            if matched_entry_ids and session_entry_id:
                break

        audit_payload: dict[str, Any] = {
            "type": "strategy_memory_wrong_flag_audit",
            "wrong_flag": wrong_flag,
            "matched_entry_ids": matched_entry_ids,
            "matched_atomic_facts": [],
            "current_atomic_facts": [],
            "memory_trace": [],
            "affected_entry_ids": [],
            "auto_muted_entry_ids": [],
            "deprecated_entry_id": None,
            "entries": [],
        }
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "strategy_memory_audit":
                audit_payload["current_atomic_facts"] = list(
                    item.get("current_atomic_facts") or []
                )
            if item.get("type") == "hypothesis_memory_adjustment":
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                matched_entry_trace = [
                    str(entry_id).strip()
                    for entry_id in (metadata.get("matched_entry_ids") or [])
                    if str(entry_id).strip()
                ]
                if matched_entry_ids and not set(matched_entry_ids) & set(matched_entry_trace):
                    continue
                trace_item = {
                    "kind": str(item.get("kind") or "").strip(),
                    "reason": str(metadata.get("reason") or "").strip(),
                    "matched_atomic_facts": list(metadata.get("matched_atomic_facts") or []),
                    "required_atomic_facts": list(metadata.get("required_atomic_facts") or []),
                    "matched_entry_ids": matched_entry_trace,
                }
                if trace_item["kind"] or trace_item["matched_atomic_facts"] or trace_item["required_atomic_facts"]:
                    audit_payload["memory_trace"].append(trace_item)
            if item.get("type") == "strategy_memory_audit":
                for matched in list(item.get("matched_entries") or []):
                    if not isinstance(matched, dict):
                        continue
                    if matched_entry_ids and str(matched.get("id") or "").strip() not in matched_entry_ids:
                        continue
                    audit_payload["matched_atomic_facts"].extend(
                        str(fact).strip()
                        for fact in (matched.get("atomic_facts") or [])
                        if str(fact).strip()
                    )
        audit_payload["matched_atomic_facts"] = list(
            dict.fromkeys(audit_payload["matched_atomic_facts"])
        )
        try:
            from ..agents.pa_agent.strategy_memory import StrategyMemoryStore

            store = StrategyMemoryStore()
            store_audit = await store.apply_rejected_feedback(
                matched_entry_ids,
                session_entry_id=session_entry_id,
            )
            audit_payload.update(store_audit)
        except Exception as exc:
            audit_payload["error"] = str(exc)

        meta_reasonings.append(audit_payload)
        state["meta_reasonings"] = meta_reasonings
        retrospectives = list(state.get("retrospectives") or [])
        retrospectives.append(
            {
                "id": f"retro_wrong_flag_{len(retrospectives) + 1}",
                "trigger": "wrong_flag_feedback",
                "failure_root_cause": f"user rejected previously extracted flag: {wrong_flag}",
                "learned_rule": "错误 flag 反馈必须回写 memory audit，并沿最近 runtime-backed 原语继续深挖。",
                "strategy_memory_update": True,
            }
        )
        state["retrospectives"] = retrospectives
        state["stop_report"] = self._rebuild_wrong_flag_stop_report(wrong_flag)

        report = state.get("stop_report") or {}
        lines = [
            "[CTF wrong-flag recovery]",
            f"- rejected_flag: {wrong_flag}",
            f"- strongest_remaining_hypothesis: {report.get('strongest_remaining_hypothesis') or 'unknown'}",
            f"- recommended_memory_actions: {' | '.join(report.get('recommended_memory_actions') or []) or 'none'}",
            f"- user_next_steps: {' | '.join(report.get('user_next_steps') or []) or 'none'}",
        ]
        if audit_payload.get("affected_entry_ids"):
            lines.append(
                f"- affected_memory_entries: {audit_payload.get('affected_entry_ids')}"
            )
        if audit_payload.get("deprecated_entry_id"):
            lines.append(
                f"- deprecated_session_entry: {audit_payload.get('deprecated_entry_id')}"
            )
        if audit_payload.get("auto_muted_entry_ids"):
            lines.append(
                f"- auto_muted_entries: {audit_payload.get('auto_muted_entry_ids')}"
            )
        if audit_payload.get("matched_atomic_facts"):
            lines.append(
                f"- matched_atomic_facts: {audit_payload.get('matched_atomic_facts')}"
            )
        if audit_payload.get("memory_trace"):
            lines.append(
                f"- memory_trace: {audit_payload.get('memory_trace')}"
            )
        if audit_payload.get("error"):
            lines.append(f"- memory_audit_error: {audit_payload.get('error')}")
        return "\n".join(lines)
