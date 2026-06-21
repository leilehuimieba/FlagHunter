"""Progress-delta tracking, object-ified (L3b, cut A).

The progress-delta logic — snapshotting flag counts and grading turn-to-turn
deltas into a hypothesis signal — is now an independent ``ProgressTracker``
object that can be unit-tested completely detached from
``CTFTaskDispatcher``.  It deliberately takes ``state`` as an explicit
per-call parameter (never an eagerly-held reference): on the resume path the
dispatcher rebinds ``self.state`` to a fresh object, so the tracker must read
whatever ``state`` is current at call time.

``ProgressTrackerMixin`` is retained as a thin delegation shell (its
``__module__`` is anchored by tests and the dispatcher still mixes it into the
MRO at ``ctf_dispatcher.py``).  Both shell methods forward to the
dispatcher-held ``self._progress`` instance, passing ``self.state`` through.
Behaviour is byte-for-byte identical to the previous inline implementation,
including the ``chain_outcome.progress`` short-circuit to ``"none"``.
"""

from __future__ import annotations


class ProgressTracker:
    """Snapshot flag counts and grade turn deltas into a hypothesis signal.

    Stateless w.r.t. ``state``: every method receives ``state`` explicitly so
    the same tracker instance survives a dispatcher ``state`` rebind (resume).
    """

    def snapshot_flag_counts(self, state) -> dict[str, int]:
        if state is None:
            return {}
        return {
            "candidate": len(state.candidate_flags),
            "runtime": len(state.runtime_flags),
            "verified": len(state.verified_flags),
            "rejected": len(state.rejected_flags),
            "uniform_failure_surface": len(
                [
                    obs
                    for obs in state.observations
                    if obs.kind == "uniform_failure_surface"
                ]
            ),
        }

    def derive_progress_delta(
        self,
        state,
        before_state: dict[str, int],
        chain_outcome=None,
    ) -> str:
        """Compute progress signal for the hypothesis engine.

        ``chain_outcome`` is the ``_ChainOutcome`` returned by the chain
        executor.  When the chain as a whole made real progress (e.g. a hint
        file was successfully read) but a *sibling* sub-strategy recorded a
        ``uniform_failure_surface`` observation, we must not let that sibling
        penalty override the chain-level progress signal.  In that case we
        return ``"none"`` rather than ``"rejected"`` so the hypothesis is not
        prematurely exhausted.
        """
        if state is None:
            return "none"
        after = self.snapshot_flag_counts(state)
        if after.get("verified", 0) > before_state.get("verified", 0):
            return "terminal"
        if after.get("runtime", 0) > before_state.get("runtime", 0):
            return "strong"
        if after.get("uniform_failure_surface", 0) > before_state.get("uniform_failure_surface", 0):
            # A sub-strategy got blocked, but only mark "rejected" when the
            # chain as a whole also made *no* progress.  If the chain outcome
            # reports progress (e.g. hint_chain_followup read the hints file
            # before ssti_via_render_parameter hit "ORZ"), return "none" so
            # the active hypothesis stays alive and the agent can continue.
            if chain_outcome is not None and chain_outcome.progress:
                return "none"
            return "rejected"
        if after.get("candidate", 0) > before_state.get("candidate", 0):
            return "weak"
        return "none"


class ProgressTrackerMixin:
    """Thin delegation shell forwarding to the dispatcher's ``ProgressTracker``."""

    def _snapshot_flag_counts(self) -> dict[str, int]:
        return self._progress.snapshot_flag_counts(self.state)

    def _derive_progress_delta(
        self,
        before_state: dict[str, int],
        chain_outcome=None,
    ) -> str:
        return self._progress.derive_progress_delta(
            self.state, before_state, chain_outcome=chain_outcome
        )
