"""P5 余量 — entry_kind drives SETUP-phase asset ingestion.

A source-first profile (code_audit, entry_kind="source") eagerly ingests local
source artifacts when present, without waiting for the hint-driven control
decision. CTF (entry_kind="url") keeps the hint-only gate → byte-identical.
"""

from __future__ import annotations

from types import SimpleNamespace

from flaghunter.agents.pa_agent.coordinator import CTFCoordinator
from flaghunter.agents.pa_agent.ctf_state import CTFState


def _fake_dispatcher(entry_kind: str, assets: dict):
    calls = {"ingest_assets": 0, "ingest_hints": 0}
    state = CTFState(target="http://t", goal="g")
    state.entry_kind = entry_kind

    def _ingest_assets(_target):
        calls["ingest_assets"] += 1

    def _ingest_hints():
        calls["ingest_hints"] += 1

    dispatcher = SimpleNamespace(
        _ingress_handoff=None,
        _challenge_context=assets,
        state=state,
        _ingest_local_challenge_artifacts=_ingest_assets,
        _ingest_registered_local_source_hints=_ingest_hints,
        _record_session_event=lambda *a, **k: None,
        _write_checkpoint=lambda *a, **k: None,
    )
    return dispatcher, calls


def test_source_profile_eagerly_ingests_present_assets_without_hint():
    dispatcher, calls = _fake_dispatcher("source", {"artifactPaths": ["/src/app.py"]})
    CTFCoordinator()._apply_local_asset_bootstrap_contract(
        dispatcher, target="http://t", hint=""
    )
    assert calls["ingest_assets"] == 1
    assert calls["ingest_hints"] == 1


def test_ctf_profile_does_not_ingest_without_hint():
    # Byte-identical to pre-P5: a url-entry profile waits for the hint decision.
    dispatcher, calls = _fake_dispatcher("url", {"artifactPaths": ["/src/app.py"]})
    CTFCoordinator()._apply_local_asset_bootstrap_contract(
        dispatcher, target="http://t", hint=""
    )
    assert calls["ingest_assets"] == 0


def test_source_profile_without_present_assets_does_not_ingest():
    dispatcher, calls = _fake_dispatcher("source", {})
    CTFCoordinator()._apply_local_asset_bootstrap_contract(
        dispatcher, target="http://t", hint=""
    )
    assert calls["ingest_assets"] == 0
