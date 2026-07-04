"""Build neutral challenge run snapshots from injected read ports."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from flaghunter.domain.challenge.contracts.read_models import (
    ChallengeRunSnapshot,
    ReadModelRef,
)
from flaghunter.ports.audit_store import ReadModelStorePort
from flaghunter.ports.state_store import StateStorePort


class BuildChallengeRunSnapshot:
    def __init__(
        self,
        *,
        state_store: StateStorePort | None = None,
        read_model_store: ReadModelStorePort | None = None,
    ) -> None:
        self._state_store = state_store
        self._read_model_store = read_model_store

    def build(self, *, run_id: str, challenge_id: str) -> ChallengeRunSnapshot:
        snapshot = self._load_snapshot(run_id=run_id, challenge_id=challenge_id)
        listed_refs = self._list_read_model_refs(run_id=run_id)
        if not listed_refs:
            return snapshot
        return replace(
            snapshot,
            read_models=self._merge_read_model_refs(snapshot.read_models, listed_refs),
        )

    def _load_snapshot(self, *, run_id: str, challenge_id: str) -> ChallengeRunSnapshot:
        payload = None
        if self._state_store is not None:
            payload = self._state_store.load_snapshot(run_id)
        if not payload:
            return ChallengeRunSnapshot(run_id=run_id, challenge_id=challenge_id)
        normalized = _with_requested_ids(payload, run_id=run_id, challenge_id=challenge_id)
        return ChallengeRunSnapshot.from_dict(normalized)

    def _list_read_model_refs(self, *, run_id: str) -> list[ReadModelRef]:
        if self._read_model_store is None:
            return []
        refs: list[ReadModelRef] = []
        for item in self._read_model_store.list_read_models():
            if not isinstance(item, Mapping):
                continue
            if "modelId" not in item or "modelType" not in item:
                continue
            ref = ReadModelRef.from_dict(item)
            if ref.run_id not in (None, run_id):
                continue
            refs.append(ref)
        return refs

    def _merge_read_model_refs(
        self,
        existing: list[ReadModelRef],
        listed: list[ReadModelRef],
    ) -> list[ReadModelRef]:
        merged = list(existing)
        seen = {(ref.model_id, ref.model_type, ref.run_id, ref.version) for ref in merged}
        for ref in listed:
            key = (ref.model_id, ref.model_type, ref.run_id, ref.version)
            if key in seen:
                continue
            seen.add(key)
            merged.append(ref)
        return merged


def _with_requested_ids(
    payload: Mapping[str, Any],
    *,
    run_id: str,
    challenge_id: str,
) -> dict[str, Any]:
    normalized = dict(payload)
    if not normalized.get("runId"):
        normalized["runId"] = run_id
    if not normalized.get("challengeId"):
        normalized["challengeId"] = challenge_id
    return normalized
