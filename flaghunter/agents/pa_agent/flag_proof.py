"""Flag-proof hydration / wrong-flag feedback mixin extracted from ctf_dispatcher.py.

P5 / Workstream A: the contiguous flag-proof helper cluster (5 methods,
_record_wrong_flag_feedback .. _format_reproduction_steps) is physically moved
out of CTFTaskDispatcher into a behaviour-preserving mixin. Method bodies are
identical; self.* (state, hypothesis_engine, _store_note, _pending_wrong_flag_
feedback, _current_fingerprint) resolves at runtime against the dispatcher that
mixes this in, so call sites are unchanged. The entry-point _observe_flag stays
in the dispatcher and still reaches these via MRO. Pure code relocation, near-
zero risk.
"""

from __future__ import annotations

from typing import Any

from .ctf_state import FlagProof


class FlagProofMixin:
    """Wrong-flag feedback recording and FlagProof hydration / reproduction steps."""

    async def _record_wrong_flag_feedback(
        self,
        flag: str,
        rationale: str,
        *,
        proof: FlagProof | None = None,
    ) -> None:
        normalized = str(flag or "").strip()
        if not normalized or self.state is None:
            return
        for existing in self._pending_wrong_flag_feedback:
            if existing.get("flag") == normalized:
                return
        self._pending_wrong_flag_feedback.append(
            {
                "flag": normalized,
                "rationale": str(rationale or "").strip(),
                "evidence_source": str(getattr(proof, "evidence_source", None) or "").strip(),
                "recoverable": str(
                    str(getattr(proof, "evidence_source", None) or "").strip().lower()
                    in {"source-only", "source_only"}
                    or "source-only" in str(rationale or "").lower()
                    or "source_only" in str(rationale or "").lower()
                ).lower(),
            }
        )
        self.state.meta_reasonings.append(
            {
                "type": "wrong_flag_feedback_pending",
                "flag": normalized,
                "rationale": str(rationale or "").strip(),
            }
        )
        self.state.record_weak_decision(
            f"wrong flag feedback: {normalized}"
        )
        self.hypothesis_engine.apply_wrong_flag_feedback(
            self.state,
            flag=normalized,
            rationale=str(rationale or "").strip(),
            proof=proof,
        )
        self.state.add_observation(
            "wrong_flag_feedback",
            normalized,
            source="platform-submit",
            metadata={
                "rationale": str(rationale or "").strip(),
                "strategy_kind": getattr(proof, "strategy_kind", None),
                "hypothesis_id": getattr(proof, "hypothesis_id", None),
                "evidence_source": getattr(proof, "evidence_source", None),
            },
        )
        self.state.retrospectives.append(
            {
                "id": f"retro_wrong_flag_pending_{len(self.state.retrospectives) + 1}",
                "trigger": "wrong_flag_feedback",
                "failure_root_cause": f"platform rejected previously extracted flag: {normalized}",
                "learned_rule": "提交失败的 runtime flag 不能视为成功，必须自动回到 memory audit 并继续深挖。",
                "strategy_memory_update": True,
            }
        )

        # Phase 7 §2: 规则驱动 verbal reflection（无 LLM）
        _evidence_source = str(getattr(proof, "evidence_source", None) or "unknown")
        _refl_entry = self.recovery_controller.verbal_reflection(
            self.state, normalized, _evidence_source
        )
        reflection_entry_id = await self.strategy_memory.write_reflection(
            wrong_flag=normalized,
            evidence_source=_evidence_source,
            reflection_text=_refl_entry.get("reflection", ""),
            challenge_url=self.state.target,
            fingerprint=self._current_fingerprint,
        )
        self.state.meta_reasonings.append(
            {
                "type": "strategy_memory_reflection_written",
                "entry_id": reflection_entry_id,
                "wrong_flag": normalized,
                "evidence_source": _evidence_source,
            }
        )

    def _hydrate_flag_proof(
        self,
        proof: FlagProof,
        *,
        strategy_kind: str | None,
        evidence_source: str,
        evidence_url: str,
        evidence_snippet: str,
    ) -> None:
        if self.state is None:
            return
        if proof.reproduction_steps and proof.related_observations:
            return

        related = self._recent_relevant_observations(
            strategy_kind=strategy_kind,
            evidence_source=evidence_source,
            evidence_url=evidence_url,
        )
        if not proof.related_observations:
            proof.related_observations = [
                self._observation_reference(obs) for obs in related
            ]
        if not proof.reproduction_steps:
            proof.reproduction_steps = self._format_reproduction_steps(
                related,
                evidence_url=evidence_url,
                evidence_snippet=evidence_snippet,
            )

    def _recent_relevant_observations(
        self,
        *,
        strategy_kind: str | None,
        evidence_source: str,
        evidence_url: str,
        limit: int = 5,
    ) -> list[Any]:
        if self.state is None:
            return []
        normalized_strategy = str(strategy_kind or "").strip()
        normalized_url = str(evidence_url or "").strip()
        selected: list[Any] = []
        fallback: list[Any] = []
        for obs in reversed(list(self.state.observations)):
            meta = obs.metadata if isinstance(obs.metadata, dict) else {}
            obs_url = str(meta.get("final_url") or meta.get("url") or "").strip()
            obs_strategy = str(meta.get("strategy_kind") or "").strip()
            relevant = False
            if normalized_strategy and (
                obs_strategy == normalized_strategy or obs.source == normalized_strategy
            ):
                relevant = True
            elif normalized_url and obs_url and obs_url == normalized_url:
                relevant = True
            elif str(obs.source or "").strip() == str(evidence_source or "").strip():
                relevant = True
            if relevant:
                selected.append(obs)
            elif obs.kind in {
                "ssti_probe_hit",
                "ssti_engine_identified",
                "cookie_secret_leaked",
                "hash_reconstruction_response",
                "file_read_response",
                "http_response",
                "recon_url",
            }:
                fallback.append(obs)
            if len(selected) >= limit:
                break
        if len(selected) < limit:
            for obs in fallback:
                if obs in selected:
                    continue
                selected.append(obs)
                if len(selected) >= limit:
                    break
        return list(reversed(selected[:limit]))

    def _observation_reference(self, observation: Any) -> str:
        value = str(getattr(observation, "value", "") or "").strip()
        value_snippet = value[:60] + ("…" if len(value) > 60 else "")
        source = str(getattr(observation, "source", "") or "").strip()
        base = str(getattr(observation, "kind", "") or "").strip()
        if source:
            base = f"{base}@{source}"
        if value_snippet:
            base = f"{base}:{value_snippet}"
        return base

    def _format_reproduction_steps(
        self,
        observations: list[Any],
        *,
        evidence_url: str,
        evidence_snippet: str,
    ) -> list[str]:
        steps: list[str] = []
        for index, obs in enumerate(observations, start=1):
            meta = obs.metadata if isinstance(obs.metadata, dict) else {}
            url = str(meta.get("final_url") or meta.get("url") or "").strip()
            payload = str(meta.get("payload") or "").strip()
            if url and payload:
                steps.append(f"{index}. 请求 `{url}` 并发送 payload `{payload}`")
                continue
            if url:
                steps.append(f"{index}. 请求 `{url}`，观察 `{obs.kind}`")
                continue
            value = str(obs.value or "").strip()
            snippet = value[:90] + ("…" if len(value) > 90 else "")
            steps.append(f"{index}. 观察 `{obs.kind}`：{snippet or '无额外输出'}")
        final_step = evidence_snippet[:120] + ("…" if len(evidence_snippet) > 120 else "")
        if evidence_url:
            steps.append(
                f"{len(steps) + 1}. 在 `{evidence_url}` 的运行时响应中提取 flag 证据：{final_step}"
            )
        elif final_step:
            steps.append(
                f"{len(steps) + 1}. 从最终运行时证据中提取 flag：{final_step}"
            )
        return steps
