"""Flag-verification entry-point mixin extracted from ctf_dispatcher.py.

P5 / tenth cut: the single flag-observation entry method ``_observe_flag``
(~105 lines) is physically moved out of CTFTaskDispatcher into a
behaviour-preserving mixin. The method body is identical; every ``self.*``
it touches (state, verifier, _active_hypothesis_context,
_active_strategy_context, _hydrate_flag_proof / _record_wrong_flag_feedback
[FlagProofMixin], _store_note [NoteStoreMixin], _record_session_event
[dispatcher]) resolves at runtime via the MRO of the dispatcher that mixes
this in, so the 30+ call sites (dispatcher / coordinator / chains /
llm_executor) are unchanged. ``build_verification_decision_event`` is imported
directly from the acyclic ``harness.audit_events`` leaf — no symbol sinking
needed. Pure code relocation, near-zero risk.
"""

from __future__ import annotations

from urllib.parse import urlparse

from ...harness.audit_events import build_verification_decision_event


class FlagObserverMixin:
    """Run a flag candidate through the verifier and persist the decision."""

    async def _observe_flag(
        self,
        flag: str,
        target: str,
        *,
        evidence_source: str,
        rationale: str = "",
        evidence_url: str = "",
        evidence_snippet: str = "",
        replayable: bool | None = None,
        hypothesis_id: str | None = None,
        strategy_kind: str | None = None,
    ):
        if self.state is None:
            return None

        active_hypothesis = hypothesis_id or getattr(self._active_hypothesis_context, "id", None)
        active_strategy = (
            strategy_kind
            or getattr(self._active_hypothesis_context, "kind", None)
            or getattr(self._active_strategy_context, "kind", None)
        )
        effective_url = str(evidence_url or target or "").strip()
        effective_snippet = str(evidence_snippet or rationale or flag or "").strip()

        verification = await self.verifier.verify_flag(
            self.state,
            flag=flag,
            evidence_source=evidence_source,
            rationale=rationale,
            evidence_url=effective_url,
            evidence_snippet=effective_snippet,
            replayable=replayable,
            hypothesis_id=active_hypothesis,
            strategy_kind=active_strategy,
        )
        if verification is not None and verification.proof is not None:
            self._hydrate_flag_proof(
                verification.proof,
                strategy_kind=active_strategy,
                evidence_source=evidence_source,
                evidence_url=effective_url,
                evidence_snippet=effective_snippet,
            )
        verification_event = build_verification_decision_event(
            decision=verification.decision,
            flag=verification.flag or "",
            evidence_source=evidence_source,
            rationale=verification.rationale or "",
            confidence=verification.confidence,
            hypothesis_id=active_hypothesis or "",
            strategy_kind=active_strategy or "",
        )
        self._record_session_event(
            str(verification_event.get("event_type") or "verification_decision"),
            dict(verification_event.get("payload") or {}),
        )

        if verification.decision == "candidate":
            await self._store_note(
                key="ctf_flag_candidate",
                value=f"candidate={verification.flag}; reason={verification.rationale}",
                category="artifact",
                target=urlparse(target).netloc or target,
                strategy_kind=active_strategy or "",
                verification_path=str((verification.metadata or {}).get("verification_path") or ""),
                artifact_producer="verifier",
                artifact_category="flag_candidate",
            )
        elif verification.decision == "runtime":
            await self._store_note(
                key="ctf_flag_runtime",
                value=f"runtime={verification.flag}; reason={verification.rationale}",
                category="artifact",
                target=urlparse(target).netloc or target,
                strategy_kind=active_strategy or "",
                verification_path=str((verification.metadata or {}).get("verification_path") or ""),
                artifact_producer="verifier",
                artifact_category="flag_runtime",
            )
        elif verification.decision == "verified":
            await self._store_note(
                key="ctf_flag",
                value=str(verification.flag or ""),
                category="artifact",
                target=urlparse(target).netloc or target,
                strategy_kind=active_strategy or "",
                verification_path=str((verification.metadata or {}).get("verification_path") or ""),
                artifact_producer="verifier",
                artifact_category="flag_verified",
            )
        elif verification.decision == "rejected":
            await self._store_note(
                key="ctf_flag_rejected",
                value=f"rejected={verification.flag}; reason={verification.rationale}",
                category="task",
                target=urlparse(target).netloc or target,
            )
            if verification.flag:
                await self._record_wrong_flag_feedback(
                    str(verification.flag),
                    verification.rationale,
                    proof=verification.proof,
                )
        return verification
