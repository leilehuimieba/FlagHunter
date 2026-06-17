from __future__ import annotations

from types import SimpleNamespace

import pytest

from pentestagent.cpa_modules.m1_api_hub.cost_tracker import CostTracker
from pentestagent.cpa_modules.m1_api_hub.models import ProviderConfig, ProviderState, RequestLog
from pentestagent.cpa_modules.m1_api_hub.provider_manager import ProviderManager
from pentestagent.llm.config import ModelConfig
from pentestagent.llm.llm import ErrorClass, LLM


class _FakeMemory:
    async def get_messages_with_summary(self, messages, llm_call=None):
        return list(messages)

    def clear_summary_cache(self):
        return None


class _FakeLiteLLM:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls: list[dict] = []

    async def acompletion(self, **kwargs):
        self.calls.append(dict(kwargs))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _fake_response(content: str, *, model: str = "gpt-4o"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        model=model,
    )


def _build_llm(fake_litellm: _FakeLiteLLM) -> LLM:
    llm = object.__new__(LLM)
    llm.model = "gpt-4o"
    llm.config = ModelConfig(max_retries=0, retry_delay=0.0)
    llm.rag_engine = None
    llm.memory = _FakeMemory()
    llm._litellm = fake_litellm
    return llm


async def _provider_manager_with_defaults() -> ProviderManager:
    pm = ProviderManager()
    await pm.register_provider(
        ProviderConfig(
            id="primary",
            name="Primary",
            model="gpt-4o",
            api_base="https://primary.example/v1",
            api_key="primary-key",
            priority=1,
        )
    )
    await pm.register_provider(
        ProviderConfig(
            id="backup",
            name="Backup",
            model="gpt-4o",
            api_base="https://backup.example/v1",
            api_key="backup-key",
            priority=2,
            is_backup=True,
        )
    )
    return pm


def _enable_m1(monkeypatch, pm: ProviderManager, tracker: CostTracker) -> None:
    monkeypatch.setattr("pentestagent.cpa_modules.m1_api_hub.is_m1_enabled", lambda: True)
    monkeypatch.setattr("pentestagent.cpa_modules.m1_api_hub.get_provider_manager", lambda: pm)
    monkeypatch.setattr("pentestagent.cpa_modules.m1_api_hub.get_cost_tracker", lambda: tracker)
    monkeypatch.setattr("pentestagent.cpa_modules.m1_api_hub.init_m1", lambda: None)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("429 insufficient_quota", ErrorClass.PERMANENT_DAY),
        ("401 invalid_api_key", ErrorClass.PERMANENT),
        ("context_length_exceeded", ErrorClass.LOGIC),
        ("ConnectionError: timeout while connecting", ErrorClass.TRANSIENT_NETWORK),
        ("503 server error", ErrorClass.TRANSIENT_REMOTE),
        ("429 rate limit", ErrorClass.TRANSIENT),
        ("something unexpected", ErrorClass.UNKNOWN),
    ],
)
def test_classify_error_maps_documented_error_classes(message: str, expected: ErrorClass):
    llm = _build_llm(_FakeLiteLLM([]))
    assert llm._classify_error(RuntimeError(message)) == expected


@pytest.mark.asyncio
async def test_provider_quota_exhaustion_marks_down_and_switches_to_backup(monkeypatch):
    pm = await _provider_manager_with_defaults()
    tracker = CostTracker()
    _enable_m1(monkeypatch, pm, tracker)
    llm = _build_llm(
        _FakeLiteLLM(
            [
                RuntimeError("429 insufficient_quota"),
                _fake_response("backup-ok"),
            ]
        )
    )

    response = await llm.generate(
        system_prompt="system",
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
    )

    assert response.content == "backup-ok"
    assert pm.get_status("primary").state == ProviderState.DOWN
    assert llm._litellm.calls[0]["api_key"] == "primary-key"
    assert llm._litellm.calls[1]["api_key"] == "backup-key"


@pytest.mark.asyncio
async def test_invalid_api_key_disables_primary_and_switches(monkeypatch):
    pm = await _provider_manager_with_defaults()
    tracker = CostTracker()
    _enable_m1(monkeypatch, pm, tracker)
    llm = _build_llm(
        _FakeLiteLLM(
            [
                RuntimeError("401 invalid_api_key"),
                _fake_response("backup-still-works"),
            ]
        )
    )

    response = await llm.generate(
        system_prompt="system",
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
    )

    assert response.content == "backup-still-works"
    assert pm.get_status("primary").state == ProviderState.DISABLED
    assert pm.get_provider("primary").enabled is False
    assert llm._litellm.calls[1]["api_key"] == "backup-key"


@pytest.mark.asyncio
async def test_budget_exhausted_blocks_new_requests(monkeypatch):
    pm = await _provider_manager_with_defaults()
    tracker = CostTracker(budget_usd=1.0)
    tracker.record(
        RequestLog(
            request_id="req-1",
            provider_id="primary",
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=100,
            response_time_ms=10,
            success=True,
            cost_usd=1.0,
        )
    )
    _enable_m1(monkeypatch, pm, tracker)
    llm = _build_llm(_FakeLiteLLM([_fake_response("should-not-run")]))

    response = await llm.generate(
        system_prompt="system",
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
    )

    assert response.finish_reason == "budget_exhausted"
    assert "budget exhausted" in (response.content or "")
    assert llm._litellm.calls == []


@pytest.mark.asyncio
async def test_all_providers_down_returns_provider_unavailable(monkeypatch):
    pm = await _provider_manager_with_defaults()
    tracker = CostTracker()
    pm.mark_provider_status("primary", ProviderState.DOWN, "quota")
    pm.mark_provider_status("backup", ProviderState.DOWN, "quota")
    _enable_m1(monkeypatch, pm, tracker)
    llm = _build_llm(_FakeLiteLLM([]))

    response = await llm.generate(
        system_prompt="system",
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
    )

    assert response.finish_reason == "provider_unavailable"
    assert "wait_for_provider_recovery" in (response.content or "")


@pytest.mark.asyncio
async def test_m1_is_lazy_initialized_when_enabled_but_not_ready(monkeypatch):
    pm = await _provider_manager_with_defaults()
    tracker = CostTracker()
    init_called = {"value": 0}

    monkeypatch.setattr("pentestagent.cpa_modules.m1_api_hub.is_m1_enabled", lambda: True)

    def _raise_uninitialized():
        raise RuntimeError("M1 API Hub 尚未初始化，请先调用 init_m1()")

    monkeypatch.setattr("pentestagent.cpa_modules.m1_api_hub.get_provider_manager", _raise_uninitialized)
    monkeypatch.setattr("pentestagent.cpa_modules.m1_api_hub.get_cost_tracker", _raise_uninitialized)

    async def _init_m1():
        init_called["value"] += 1
        monkeypatch.setattr("pentestagent.cpa_modules.m1_api_hub.get_provider_manager", lambda: pm)
        monkeypatch.setattr("pentestagent.cpa_modules.m1_api_hub.get_cost_tracker", lambda: tracker)

    monkeypatch.setattr("pentestagent.cpa_modules.m1_api_hub.init_m1", _init_m1)

    llm = _build_llm(_FakeLiteLLM([_fake_response("lazy-init-ok")]))
    response = await llm.generate(
        system_prompt="system",
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
    )

    assert response.content == "lazy-init-ok"
    assert init_called["value"] == 1


@pytest.mark.asyncio
async def test_network_failures_accumulate_until_provider_marked_down(monkeypatch):
    monkeypatch.setenv("CPA_M1_FAIL_THRESHOLD", "3")
    pm = await _provider_manager_with_defaults()
    tracker = CostTracker()
    _enable_m1(monkeypatch, pm, tracker)

    llm = _build_llm(
        _FakeLiteLLM(
            [
                TimeoutError("request timeout"),
                _fake_response("backup-1"),
                TimeoutError("request timeout"),
                _fake_response("backup-2"),
                TimeoutError("request timeout"),
                _fake_response("backup-3"),
            ]
        )
    )

    for _ in range(3):
        response = await llm.generate(
            system_prompt="system",
            messages=[{"role": "user", "content": "hello"}],
            tools=None,
        )
        assert response.content and response.content.startswith("backup-")

    primary_status = pm.get_status("primary")
    assert primary_status.consecutive_failures >= 3
    assert primary_status.state == ProviderState.DOWN
