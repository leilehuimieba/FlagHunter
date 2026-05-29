from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any

import pytest


def _resolve_mode_contract(payload: Mapping[str, Any], *, source_task: Mapping[str, Any] | None = None) -> dict[str, Any]:
    try:
        mode_router = importlib.import_module("pentestagent.interface.mode_router")
    except ModuleNotFoundError as exc:
        pytest.fail(f"expected pentestagent.interface.mode_router module to exist: {exc}")

    resolve = getattr(mode_router, "resolve_mode_contract", None)
    if not callable(resolve):
        pytest.fail("expected pentestagent.interface.mode_router.resolve_mode_contract to be callable")

    try:
        contract = resolve(payload, source_task=source_task)
    except TypeError as exc:
        pytest.fail(f"resolve_mode_contract should accept payload and source_task keyword args: {exc}")

    assert isinstance(contract, dict)
    return contract


def test_resolve_mode_contract_prefers_explicit_ctf_mode():
    contract = _resolve_mode_contract({"mode": "ctf", "ctfType": "web"})

    assert contract["mode"] == "ctf"
    assert contract["modeSubtype"] == "web"
    assert contract["goalStyle"] == "flag"


def test_resolve_mode_contract_prefers_explicit_pentest_mode_over_ctf_type():
    contract = _resolve_mode_contract({"mode": "pentest", "ctfType": "web"})

    assert contract["mode"] == "pentest"
    assert contract["goalStyle"] == "evidence"


def test_resolve_mode_contract_maps_auto_with_ctf_type_to_ctf():
    contract = _resolve_mode_contract({"mode": "auto", "ctfType": "web"})

    assert contract["mode"] == "ctf"
    assert contract["modeSubtype"] == "web"
    assert contract["goalStyle"] == "flag"


def test_resolve_mode_contract_defaults_to_pentest_without_mode_or_ctf_type():
    contract = _resolve_mode_contract({"target": "http://example.test"})

    assert contract["mode"] == "pentest"
    assert contract["goalStyle"] == "evidence"


def test_resolve_mode_contract_inherits_source_task_for_retry_or_replay():
    contract = _resolve_mode_contract(
        {},
        source_task={
            "mode": "ctf",
            "modeSubtype": "web",
            "goalStyle": "flag",
            "ctfType": "crypto",
        },
    )

    assert contract["mode"] == "ctf"
    assert contract["modeSubtype"] == "web"
    assert contract["goalStyle"] == "flag"


def test_resolve_mode_contract_keeps_source_task_mode_during_continue():
    contract = _resolve_mode_contract(
        {"mode": "auto", "ctfType": "crypto"},
        source_task={
            "mode": "ctf",
            "modeSubtype": "web",
            "goalStyle": "flag",
        },
    )

    assert contract["mode"] == "ctf"
    assert contract["modeSubtype"] == "web"
    assert contract["goalStyle"] == "flag"
