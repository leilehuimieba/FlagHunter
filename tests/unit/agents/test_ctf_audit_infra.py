from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from flaghunter.agents.pa_agent.audit_infra import RuntimeAuditedActions
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
