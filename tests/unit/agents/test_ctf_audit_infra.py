from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from flaghunter.agents.pa_agent.audit_infra import AuditStore, RuntimeAuditedActions
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_AUDIT_INFRA_MODULE = "flaghunter.agents.pa_agent.audit_infra"


def test_audit_infra_methods_live_in_audit_infra_mixin():
    for name in (
        "_setup_session_ledger",
        "_setup_artifact_registry",
        "_setup_checkpoint_store",
        "_record_session_event",
        "_write_checkpoint",
        "_register_artifact_record",
        "_record_recovery_decision",
        "_resolve_registered_local_challenge_paths",
        "_resolve_registered_local_key_files",
        "_ingest_registered_local_source_hints",
        "_runtime_browser_action",
        "_runtime_proxy_action",
        "_runtime_execute_command",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _AUDIT_INFRA_MODULE


# --- RuntimeAuditedActions runs fully detached from CTFTaskDispatcher ---


def _collect():
    """A record_session_event sink that captures (event_type, payload) pairs."""
    return MagicMock()


def _event_types(rec):
    return [call.args[0] for call in rec.call_args_list]


@pytest.mark.asyncio
async def test_browser_action_emits_called_finished_and_passes_through():
    actions = RuntimeAuditedActions()
    result = {"status_code": 200}
    runtime = SimpleNamespace(browser_action=AsyncMock(return_value=result))
    rec = _collect()

    returned = await actions.browser_action(
        "navigate",
        runtime=runtime,
        record_session_event=rec,
        audit_target="http://host/",
        audit_metadata={"k": "v"},
        url="http://host/page",
    )

    assert returned is result
    # runtime called with business kwargs, audit kwargs stripped
    runtime.browser_action.assert_awaited_once_with("navigate", url="http://host/page")
    # called + finished pair, in order
    assert _event_types(rec) == ["tool_called", "tool_finished"]


@pytest.mark.asyncio
async def test_proxy_action_emits_called_finished_and_passes_through():
    actions = RuntimeAuditedActions()
    result = {"status_code": 204}
    runtime = SimpleNamespace(proxy_action=AsyncMock(return_value=result))
    rec = _collect()

    returned = await actions.proxy_action(
        "intercept",
        runtime=runtime,
        record_session_event=rec,
        audit_target="http://host/",
        audit_metadata=None,
        mode="on",
    )

    assert returned is result
    runtime.proxy_action.assert_awaited_once_with("intercept", mode="on")
    assert _event_types(rec) == ["tool_called", "tool_finished"]


@pytest.mark.asyncio
async def test_execute_command_emits_called_finished_and_passes_through():
    actions = RuntimeAuditedActions()
    result = SimpleNamespace(exit_code=0)
    runtime = SimpleNamespace(execute_command=AsyncMock(return_value=result))
    rec = _collect()

    returned = await actions.execute_command(
        "id",
        runtime=runtime,
        record_session_event=rec,
        timeout=30,
        audit_target="host",
        audit_metadata={"x": 1},
    )

    assert returned is result
    runtime.execute_command.assert_awaited_once_with("id", timeout=30)
    assert _event_types(rec) == ["tool_called", "tool_finished"]
    # command is recorded into the finished metadata payload
    finished_payload = rec.call_args_list[1].args[1]
    assert isinstance(finished_payload, dict)


@pytest.mark.asyncio
async def test_runtime_audited_actions_holds_no_self_state():
    """Per-call injection: the instance must carry no runtime / state / sink
    attributes of its own."""
    actions = RuntimeAuditedActions()
    assert vars(actions) == {}

    # two successive calls with distinct runtimes are each forwarded by value
    runtime1 = SimpleNamespace(browser_action=AsyncMock(return_value={}))
    runtime2 = SimpleNamespace(browser_action=AsyncMock(return_value={}))
    rec = _collect()

    await actions.browser_action(
        "a", runtime=runtime1, record_session_event=rec, audit_target="t"
    )
    await actions.browser_action(
        "b", runtime=runtime2, record_session_event=rec, audit_target="t"
    )

    runtime1.browser_action.assert_awaited_once_with("a")
    runtime2.browser_action.assert_awaited_once_with("b")
    assert vars(actions) == {}


# --- AuditStore runs fully detached from CTFTaskDispatcher ---


def test_audit_store_holds_no_self_state():
    """L3f-2 cut A: AuditStore is stateless — it carries no backing store,
    run id, state or sink attributes of its own."""
    store = AuditStore()
    assert vars(store) == {}

    # exercising the write path leaves the instance state empty
    store.record_session_event(MagicMock(), "run-1", "evt", {"k": "v"})
    assert vars(store) == {}


def test_build_session_ledger_returns_run_id_and_ledger(tmp_path):
    store = AuditStore()
    run_id, ledger = store.build_session_ledger(
        run_id="run-explicit", ledger_root=tmp_path / "ledgers"
    )
    assert run_id == "run-explicit"
    assert ledger is not None
    assert vars(store) == {}


def test_build_session_ledger_synthesizes_run_id_when_blank(tmp_path):
    store = AuditStore()
    run_id, ledger = store.build_session_ledger(run_id="  ", ledger_root=tmp_path)
    assert run_id.startswith("ctf-")
    assert ledger is not None


def test_build_artifact_registry_falls_back_to_ledger_run_id(tmp_path):
    store = AuditStore()
    run_id, registry = store.build_artifact_registry(
        run_id=None, fallback_run_id="run-from-ledger", registry_root=tmp_path
    )
    assert run_id == "run-from-ledger"
    assert registry is not None


def test_build_artifact_registry_synthesizes_when_no_fallback(tmp_path):
    store = AuditStore()
    run_id, _ = store.build_artifact_registry(
        run_id=None, fallback_run_id=None, registry_root=tmp_path
    )
    assert run_id.startswith("ctf-")


def test_build_checkpoint_store_falls_back_to_ledger_run_id(tmp_path):
    store = AuditStore()
    run_id, checkpoints = store.build_checkpoint_store(
        run_id="", fallback_run_id="run-from-ledger", checkpoint_root=tmp_path
    )
    assert run_id == "run-from-ledger"
    assert checkpoints is not None


def test_record_session_event_guards_noop_without_ledger():
    """The ``_session_ledger is None or not _ledger_run_id`` guard is preserved."""
    store = AuditStore()
    ledger = MagicMock()

    # no ledger -> no append
    store.record_session_event(None, "run-1", "evt", {})
    # no run id -> no append
    store.record_session_event(ledger, "", "evt", {})
    ledger.append_event.assert_not_called()

    # both present -> append
    store.record_session_event(ledger, "run-1", "evt", {"k": "v"})
    ledger.append_event.assert_called_once_with("run-1", "evt", {"k": "v"})


def test_write_checkpoint_guards_and_emits_paired_event():
    store = AuditStore()
    state = SimpleNamespace(to_snapshot=lambda: {"snap": True})
    checkpoint_store = MagicMock()
    checkpoint_store.save_checkpoint.return_value = {"checkpoint_id": "c1"}
    sink = MagicMock()

    # guard: no store / no run id / no state -> no save, no emit
    store.write_checkpoint(None, "run-1", state, sink, "label", None)
    store.write_checkpoint(checkpoint_store, "", state, sink, "label", None)
    store.write_checkpoint(checkpoint_store, "run-1", None, sink, "label", None)
    checkpoint_store.save_checkpoint.assert_not_called()
    sink.assert_not_called()

    # happy path: save_checkpoint then a single session event emission
    store.write_checkpoint(checkpoint_store, "run-1", state, sink, "started", {"m": 1})
    checkpoint_store.save_checkpoint.assert_called_once_with(
        run_id="run-1",
        label="started",
        state_snapshot={"snap": True},
        metadata={"m": 1},
    )
    assert sink.call_count == 1
    assert sink.call_args.args[0] == "checkpoint_written"


def test_register_artifact_record_guards_and_emits_paired_event():
    store = AuditStore()
    registry = MagicMock()
    registry.register_artifact.return_value = {"id": "a1"}
    sink = MagicMock()

    # guard: no registry / no run id -> no register, no emit
    store.register_artifact_record(None, "run-1", sink, kind="k", title="t")
    store.register_artifact_record(registry, "", sink, kind="k", title="t")
    registry.register_artifact.assert_not_called()
    sink.assert_not_called()

    # happy path: register then a single artifact_registered emission
    store.register_artifact_record(
        registry, "run-1", sink, kind="credential", title="ctf_flag", producer="verifier"
    )
    registry.register_artifact.assert_called_once()
    assert sink.call_count == 1
    assert sink.call_args.args[0] == "artifact_registered"


def test_record_recovery_decision_forwards_to_sink():
    store = AuditStore()
    sink = MagicMock()
    decision = SimpleNamespace(kind="retry")
    store.record_recovery_decision(sink, decision, chain_name="web")
    assert sink.call_count == 1
    assert sink.call_args.args[0] == "recovery_decision"


def test_ingest_source_hints_adds_observation_per_key_file(tmp_path):
    store = AuditStore()
    key_file = tmp_path / "secret.py"
    key_file.write_text("SECRET = 'value'", encoding="utf-8")
    state = MagicMock()

    store.ingest_registered_local_source_hints(
        state,
        lambda: [key_file],
        max_files=3,
        max_chars=400,
    )

    state.add_observation.assert_called_once()
    args, kwargs = state.add_observation.call_args
    assert args[0] == "local_challenge_source_hint"
    assert kwargs["source"] == "local_challenge_context"
    assert kwargs["metadata"]["file_name"] == "secret.py"
    assert vars(store) == {}
