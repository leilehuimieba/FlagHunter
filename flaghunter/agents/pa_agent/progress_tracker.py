"""Progress-delta tracking mixin extracted from ctf_dispatcher.py.

P5 / eleventh cut: the contiguous progress-delta pair
``_snapshot_flag_counts`` + ``_derive_progress_delta`` (50 lines) is
physically moved out of CTFTaskDispatcher into a behaviour-preserving
mixin. Method bodies are identical; both only touch ``self.state`` (and
``_derive_progress_delta`` calls ``self._snapshot_flag_counts``), all
resolved at runtime via the MRO of the dispatcher that mixes this in, so
the call sites (dispatcher ``_snapshot_flag_counts`` at line ~462,
coordinator ``_derive_progress_delta`` at line ~1300) are unchanged. No
module-level symbols are referenced — zero imports to sink. Pure code
relocation, near-zero risk.
"""

from __future__ import annotations


class ProgressTrackerMixin:
    """Snapshot flag counts and turn count deltas into a hypothesis signal."""

    def _snapshot_flag_counts(self) -> dict[str, int]:
        if self.state is None:
            return {}
        return {
            "candidate": len(self.state.candidate_flags),
            "runtime": len(self.state.runtime_flags),
            "verified": len(self.state.verified_flags),
            "rejected": len(self.state.rejected_flags),
            "uniform_failure_surface": len(
                [
                    obs
                    for obs in self.state.observations
                    if obs.kind == "uniform_failure_surface"
                ]
            ),
        }

    def _derive_progress_delta(
        self,
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
        if self.state is None:
            return "none"
        after = self._snapshot_flag_counts()
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
