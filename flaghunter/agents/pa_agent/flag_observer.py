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


class FlagObserver:
    """Run a flag candidate through the verifier and persist the decision.

    Object-ified (L3c, cut A): independent of ``CTFTaskDispatcher`` and
    unit-testable fully detached.  Has no ``__init__`` and holds **no** eager
    reference to ``state`` or the active hypothesis/strategy contexts — those
    are rebound every turn / on resume by the dispatcher, so they are passed
    per-call.  The verifier and the collaborator callables are likewise
    injected per-call (the shell hands over bound methods that follow the MRO).
    Behaviour is byte-for-byte identical to the previous inline implementation.
    """

    async def observe_flag(
        self,
        state,
        *,
        verifier,
        store_note,
        record_session_event,
        hydrate_flag_proof,
        record_wrong_flag_feedback,
        active_hypothesis_context,
        active_strategy_context,
        flag: str,
        target: str,
        evidence_source: str,
        rationale: str = "",
        evidence_url: str = "",
        evidence_snippet: str = "",
        replayable: bool | None = None,
        hypothesis_id: str | None = None,
        strategy_kind: str | None = None,
    ):
        if state is None:
            return None

        active_hypothesis = hypothesis_id or getattr(active_hypothesis_context, "id", None)
        active_strategy = (
            strategy_kind
            or getattr(active_hypothesis_context, "kind", None)
            or getattr(active_strategy_context, "kind", None)
        )
        effective_url = str(evidence_url or target or "").strip()
        effective_snippet = str(evidence_snippet or rationale or flag or "").strip()

        verification = await verifier.verify_flag(
            state,
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
            hydrate_flag_proof(
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
        record_session_event(
            str(verification_event.get("event_type") or "verification_decision"),
            dict(verification_event.get("payload") or {}),
        )

        if verification.decision == "candidate":
            await store_note(
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
            await store_note(
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
            await store_note(
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
            await store_note(
                key="ctf_flag_rejected",
                value=f"rejected={verification.flag}; reason={verification.rationale}",
                category="task",
                target=urlparse(target).netloc or target,
            )
            if verification.flag:
                await record_wrong_flag_feedback(
                    str(verification.flag),
                    verification.rationale,
                    proof=verification.proof,
                )
        return verification


class FlagObserverMixin:
    """Thin delegation shell forwarding to the dispatcher's ``FlagObserver``."""

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
        return await self._flag_observer.observe_flag(
            self.state,
            verifier=self.verifier,
            store_note=self._store_note,
            record_session_event=self._record_session_event,
            hydrate_flag_proof=self._hydrate_flag_proof,
            record_wrong_flag_feedback=self._record_wrong_flag_feedback,
            active_hypothesis_context=self._active_hypothesis_context,
            active_strategy_context=self._active_strategy_context,
            flag=flag,
            target=target,
            evidence_source=evidence_source,
            rationale=rationale,
            evidence_url=evidence_url,
            evidence_snippet=evidence_snippet,
            replayable=replayable,
            hypothesis_id=hypothesis_id,
            strategy_kind=strategy_kind,
        )
