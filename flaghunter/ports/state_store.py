"""State and claim storage boundary contracts."""

from typing import Any, Iterable, Mapping, Protocol, runtime_checkable


@runtime_checkable
class StateStorePort(Protocol):
    def load_snapshot(self, run_id: str) -> Mapping[str, Any] | None:
        ...

    def save_snapshot(
        self,
        run_id: str,
        snapshot: Mapping[str, Any],
    ) -> None:
        ...


@runtime_checkable
class ClaimStorePort(Protocol):
    def create_candidate_claim(
        self,
        kind: str,
        content: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...

    def find_claims(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        ...

    def append_evidence_trace(
        self,
        claim_id: str,
        evidence: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...
