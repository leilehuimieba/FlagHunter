from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.chains.base import _ChainOutcome
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.ctf_state import CTFState


class _Runtime:
    environment = None


class _BridgeCoordinator:
    def _prepare_chain_iteration_contract(
        self,
        _dispatcher,
        *,
        chain_name,
        target,
        page_features,
        hint,
        chain_order,
    ):
        return {
            "active_hypothesis": SimpleNamespace(
                id="hyp-1",
                kind="web",
                description="probe token=hypothesis-token",
            ),
            "strategy": SimpleNamespace(
                kind="strategy token=strategy-token",
                chain_name=chain_name,
                precondition_description="precondition password=strategy-password",
                minimal_experiment="minimal secret=strategy-secret",
            ),
            "experiment": SimpleNamespace(id="exp-1"),
        }

    async def _apply_wrong_flag_early_stop_contract(self, *args, **kwargs):
        return None

    async def _apply_terminal_success_contract(self, *args, **kwargs):
        return None

    def _apply_progress_evaluation_contract(self, *args, **kwargs):
        return {
            "progress_delta": "weak",
            "effective_progress": True,
            "no_progress_rounds": 0,
        }

    async def _apply_after_chain_recovery_contract(
        self,
        _dispatcher,
        *,
        chain_name,
        chain_index,
        chain_order,
        result,
        target,
        active_hypothesis,
        effective_progress,
        no_progress_rounds,
    ):
        return {
            "continue_loop": False,
            "chain_order": list(chain_order),
            "next_chain_index": chain_index + 1,
            "final_result": None,
            "no_progress_rounds": no_progress_rounds,
        }

    async def _apply_final_recovery_contract(
        self,
        _dispatcher,
        *,
        result,
        target,
        detected_type,
        no_progress_rounds,
    ):
        return result


@pytest.mark.asyncio
async def test_p3d_dispatcher_records_solve_node_brief_and_receipt(monkeypatch):
    dispatcher = CTFTaskDispatcher(runtime=_Runtime(), progress_callback=None)
    dispatcher.coordinator = _BridgeCoordinator()  # type: ignore[assignment]
    dispatcher.state = CTFState(target="http://ctf.local", goal="get flag")

    async def _fake_execute_chain(**_kwargs):
        return _ChainOutcome(progress=True, reason="done token=outcome-token")

    monkeypatch.setattr(dispatcher, "_execute_chain", _fake_execute_chain)

    result = await dispatcher._run_solve_loop(
        target="http://ctf.local",
        hint="hint password=hint-password",
        page_features={"url": "http://ctf.local/?token=page-token"},
        detected_type="web",
        chain_order=["web"],
    )

    state = dispatcher.state
    snapshot_text = repr(state.to_snapshot())

    assert result.success is False
    assert state.solve_node_graph.to_dict()["summary"]["nodeCount"] == 1
    assert len(state.task_briefs_by_id) == 1
    assert len(state.solve_node_receipts_by_id) == 1

    node = next(iter(state.solve_node_graph.nodes_by_id.values()))
    brief = next(iter(state.task_briefs_by_id.values()))
    receipt = next(iter(state.solve_node_receipts_by_id.values()))

    assert brief.node_id == node.id
    assert receipt.node_id == node.id
    assert receipt.input_brief_id == brief.id
    assert receipt.status == "completed"
    assert receipt.trace_ids == []
    assert state.claims_by_id == {}
    assert state.verified_flags == []
    for leaked in (
        "strategy-token",
        "strategy-password",
        "strategy-secret",
        "hypothesis-token",
        "outcome-token",
        "hint-password",
        "page-token",
    ):
        assert leaked not in snapshot_text
    assert "<redacted>" in snapshot_text


def test_p3d_partial_receipt_leaves_node_in_terminal_non_running_state():
    dispatcher = CTFTaskDispatcher(runtime=_Runtime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="get flag")
    attempt = dispatcher._record_p3_strategy_attempt_start(
        chain_name="web",
        target="http://ctf.local",
        hint="hint",
        strategy=SimpleNamespace(kind="strategy", minimal_experiment="minimal"),
        active_hypothesis=SimpleNamespace(id="hyp-1", description="desc"),
        attempt_index=0,
    )

    receipt_id = dispatcher._record_p3_strategy_attempt_receipt(
        attempt,
        status="partial",
        output_summary="no progress",
    )

    node = dispatcher.state.get_solve_node(attempt["node_id"])
    receipt = dispatcher.state.get_solve_node_receipt(receipt_id)

    assert node is not None
    assert node.status.value != "running"
    assert node.finished_at is not None
    assert receipt is not None
    assert receipt.status == "partial"


def test_p3d_dispatcher_bridge_helpers_are_best_effort_noops(monkeypatch):
    dispatcher = CTFTaskDispatcher(runtime=_Runtime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="get flag")

    def _raise_store_down(_record):
        raise RuntimeError("p3 store down")

    monkeypatch.setattr(dispatcher.state, "record_solve_node", _raise_store_down)

    attempt = dispatcher._record_p3_strategy_attempt_start(
        chain_name="web",
        target="http://ctf.local",
        hint="hint",
        strategy=SimpleNamespace(kind="strategy", minimal_experiment="minimal"),
        active_hypothesis=SimpleNamespace(id="hyp-1", description="desc"),
        attempt_index=0,
    )

    assert attempt == {}
    assert dispatcher.state.solve_node_graph.to_dict()["summary"]["nodeCount"] == 0

    monkeypatch.setattr(
        dispatcher.state,
        "record_solve_node_receipt",
        _raise_store_down,
    )
    valid_attempt = {"node_id": "node-a", "brief_id": "brief-a"}

    receipt_id = dispatcher._record_p3_strategy_attempt_receipt(
        valid_attempt,
        status="completed",
        output_summary="finished",
    )

    assert receipt_id == ""


def test_p3d_dispatcher_bridge_rolls_back_partial_start_on_brief_failure(monkeypatch):
    dispatcher = CTFTaskDispatcher(runtime=_Runtime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="get flag")

    def _raise_brief_store_down(_record):
        raise RuntimeError("brief store down")

    monkeypatch.setattr(dispatcher.state, "record_task_brief", _raise_brief_store_down)

    attempt = dispatcher._record_p3_strategy_attempt_start(
        chain_name="web",
        target="http://ctf.local",
        hint="hint",
        strategy=SimpleNamespace(kind="strategy", minimal_experiment="minimal"),
        active_hypothesis=SimpleNamespace(id="hyp-1", description="desc"),
        attempt_index=0,
    )

    assert attempt == {}
    assert dispatcher.state.solve_node_graph.to_dict()["summary"]["nodeCount"] == 0
    assert dispatcher.state.task_briefs_by_id == {}
    assert dispatcher.state.solve_node_receipts_by_id == {}


def test_p3d_dispatcher_receipt_helper_does_not_mutate_node_when_store_fails(
    monkeypatch,
):
    dispatcher = CTFTaskDispatcher(runtime=_Runtime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="get flag")
    attempt = dispatcher._record_p3_strategy_attempt_start(
        chain_name="web",
        target="http://ctf.local",
        hint="hint",
        strategy=SimpleNamespace(kind="strategy", minimal_experiment="minimal"),
        active_hypothesis=SimpleNamespace(id="hyp-1", description="desc"),
        attempt_index=0,
    )
    node = dispatcher.state.get_solve_node(attempt["node_id"])
    assert node is not None
    assert node.status.value == "running"

    def _raise_node_store_down(_record):
        raise RuntimeError("node store down")

    monkeypatch.setattr(dispatcher.state, "record_solve_node", _raise_node_store_down)

    receipt_id = dispatcher._record_p3_strategy_attempt_receipt(
        attempt,
        status="completed",
        output_summary="finished",
    )

    node_after = dispatcher.state.get_solve_node(attempt["node_id"])
    assert receipt_id == ""
    assert node_after is not None
    assert node_after.status.value == "running"
    assert node_after.finished_at is None
    assert dispatcher.state.solve_node_receipts_by_id == {}
