"""P8 回灌 — emergent tool-chain hints mined into the next-action planner.

Write side: ``CTFCoordinator._apply_emergent_chain_contract`` mines the
provenance log + P7-scores it and stores ``_emergent_chain_hints`` on the
dispatcher (best-effort, no-op when cold). Read side: the planner prompt builder
surfaces those hints as advisory reuse/avoid blocks.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from flaghunter.agents.pa_agent.coordinator import CTFCoordinator
from flaghunter.agents.pa_agent.llm_executor import LLMExecutor
from flaghunter.tools import provenance


def _fake_dispatcher():
    # Only the attribute the contract writes to is needed.
    return SimpleNamespace(_emergent_chain_hints={})


def test_contract_stores_reuse_hint_from_flag_bearing_chain(tmp_path):
    provenance.set_provenance_file(tmp_path / "provenance.jsonl")
    try:
        # two runs sharing a→b, the second ending in a flag (both clean)
        provenance.record_call_sync(tool_name="a", run_id="r1")
        provenance.record_call_sync(tool_name="b", run_id="r1")
        provenance.record_call_sync(tool_name="a", run_id="r2")
        provenance.record_call_sync(tool_name="b", run_id="r2", found_flag=True)

        disp = _fake_dispatcher()
        CTFCoordinator()._apply_emergent_chain_contract(disp)

        assert "a → b" in disp._emergent_chain_hints.get("reuse", [])
    finally:
        provenance.clear()


def test_contract_stores_avoid_hint_from_erroring_chain(tmp_path):
    provenance.set_provenance_file(tmp_path / "provenance.jsonl")
    try:
        # p→q recurs across two runs and always errors, never flags
        provenance.record_call_sync(tool_name="p", run_id="r1", success=False)
        provenance.record_call_sync(tool_name="q", run_id="r1", success=False)
        provenance.record_call_sync(tool_name="p", run_id="r2", success=False)
        provenance.record_call_sync(tool_name="q", run_id="r2", success=False)

        disp = _fake_dispatcher()
        CTFCoordinator()._apply_emergent_chain_contract(disp)

        assert "p → q" in disp._emergent_chain_hints.get("avoid", [])
    finally:
        provenance.clear()


def test_contract_is_noop_on_cold_log(tmp_path):
    provenance.set_provenance_file(tmp_path / "empty.jsonl")
    try:
        disp = _fake_dispatcher()
        CTFCoordinator()._apply_emergent_chain_contract(disp)
        # left untouched → byte-identical planner prompt downstream
        assert disp._emergent_chain_hints == {}
    finally:
        provenance.clear()


def test_contract_fail_safe_swallows_mining_error(monkeypatch):
    # A mining error must never disrupt the solve — hints stay empty.
    import flaghunter.agents.pa_agent.coordinator as coord_mod

    def _boom():
        raise RuntimeError("provenance gone")

    monkeypatch.setattr(
        "flaghunter.tools.provenance.get_all_calls", _boom, raising=True
    )
    disp = _fake_dispatcher()
    coord_mod.CTFCoordinator()._apply_emergent_chain_contract(disp)
    assert disp._emergent_chain_hints == {}


def test_planner_prompt_surfaces_reuse_and_avoid_blocks():
    # Read-side wiring: the next-action prompt builder consumes the dispatcher's
    # _emergent_chain_hints and surfaces reuse + avoid advisory blocks.
    src = inspect.getsource(LLMExecutor.call_llm_for_action)
    assert "_emergent_chain_hints" in src
    assert "reuse_chains" in src and "avoid_chains" in src
    assert "LED TO A FLAG" in src  # reuse advisory
    assert "ERRORED or spun" in src  # avoid advisory
