from __future__ import annotations

from pentestagent.agents.pa_agent.capability_registry import CapabilityImplementation
from pentestagent.agents.pa_agent.ctf_state import CTFState, Hypothesis
from pentestagent.agents.pa_agent.reasoning import (
    ALLOWED_FAILURE_NEXT_ACTIONS,
    PreActionReasoning,
    ReasoningDecision,
    ReasoningLayer,
)
from pentestagent.agents.pa_agent.strategy_registry import StrategyDefinition


async def _noop_execute(context):
    return context


def _always_true(context):
    return True


def test_reasoning_layer_generates_pre_action_reasoning_with_degradation():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="sqli")
    state.hypotheses = [
        Hypothesis(
            id="auth_form_sqli",
            kind="auth_form_sqli",
            description="test",
            confidence=0.8,
            supporting_observations=["obs:recon"],
        )
    ]
    layer = ReasoningLayer()
    strategy = StrategyDefinition(
        kind="auth_form_sqli",
        chain_name="sqli",
        precondition_description="",
        minimal_experiment="",
        success_signal="看到登录成功提示",
        failure_signal="看到错误提示",
        escalation_condition="",
        precondition=_always_true,
        execute=_noop_execute,
    )
    degraded_choice = CapabilityImplementation(
        method="manual_payload_via_requests",
        cost=4,
        quality="medium",
        available=True,
    )

    experiment = layer.plan_chain_execution(
        state,
        chain_name="sqli",
        hypothesis=state.hypotheses[0],
        strategy=strategy,
        capability_primitive="sql_injection_test",
        capability_choice=degraded_choice,
        alternatives=["web"],
    )

    assert experiment.inputs["degraded"] is True
    assert state.pre_action_reasonings
    assert "quality=medium" in state.pre_action_reasonings[0]["action_rationale"]
    assert (
        state.pre_action_reasonings[0]["failure_next_action"]
        in ALLOWED_FAILURE_NEXT_ACTIONS
    )


def test_reasoning_layer_generates_stop_report_with_next_steps():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.add_flag(
        "flag{candidate}",
        level="candidate",
        evidence_source="source-leak",
        rationale="candidate only",
    )
    layer = ReasoningLayer()

    report = layer.generate_stop_report(
        state,
        reason="检测到 source-only candidate flag",
        missing_capabilities=[],
    )

    assert report.reason == "candidate_only"
    assert report.user_next_steps
    assert isinstance(report.recommended_memory_actions, list)
    assert state.stop_report is not None


def test_reasoning_layer_records_retrospective_with_learned_rule():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.add_flag(
        "flag{runtime_pending}",
        level="runtime",
        evidence_source="http-response",
        rationale="pending",
    )
    layer = ReasoningLayer()
    layer.plan_chain_execution(
        state,
        chain_name="sqli",
        hypothesis=None,
        strategy=None,
        capability_primitive="sql_injection_test",
        capability_choice=None,
        alternatives=[],
    )

    retrospective = layer.record_retrospective(
        state,
        trigger="stop",
        reason="runtime flag but no verification",
    )

    assert retrospective.learned_rule is not None
    assert state.retrospectives


def test_reasoning_layer_records_surprise_when_none_progress_has_unexpected_signal():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    layer = ReasoningLayer()
    experiment = layer.plan_chain_execution(
        state,
        chain_name="web",
        hypothesis=None,
        strategy=None,
        capability_primitive="source_download",
        capability_choice=None,
        alternatives=[],
    )

    outcome = layer.evaluate_experiment_result(
        state,
        experiment_id=experiment.id,
        progress_delta="none",
        observed_signal="发现了未知回显 portal signature",
    )

    assert outcome == "surprise"
    assert len(state.surprises) == 1
    assert state.surprises[0]["actual_result_summary"] == "发现了未知回显 portal signature"


def test_reasoning_layer_stop_report_includes_memory_actions():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.meta_reasonings.append(
        {
            "type": "strategy_memory_outcome_audit",
            "matched_entry_ids": ["mem_1"],
            "suggested_mute_entry_ids": ["mem_1"],
            "auto_muted_entry_ids": ["mem_2"],
            "rollback_candidate_entry_ids": ["mem_2"],
        }
    )
    layer = ReasoningLayer()

    report = layer.generate_stop_report(
        state,
        reason="未命中 flag；已按收敛规则停止并记录缺口",
        missing_capabilities=[],
    )

    joined = " ".join(report.recommended_memory_actions + report.user_next_steps)
    assert report.memory_focus_entry_ids == ["mem_1"]
    assert "/ctf memory panel filter=audit sort=correlation" in report.memory_quick_commands
    assert "/ctf memory show mem_1" in report.memory_quick_commands
    assert "/ctf memory mute mem_1" in report.memory_quick_commands
    assert "/ctf memory rollback mem_2" in report.memory_quick_commands
    assert "/ctf memory mute mem_1" in joined
    assert "/ctf memory rollback mem_2" in joined


def test_reasoning_layer_wrong_flag_feedback_pushes_memory_audit_guidance():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.meta_reasonings.append(
        {
            "type": "hypothesis_memory_adjustment",
            "kind": "auth_form_sqli",
            "applied_adjustment": 0.12,
            "metadata": {
                "reason": "atomic_fact_supported",
                "matched_atomic_facts": ["signal:login_form", "auth:form_login"],
                "required_atomic_facts": ["signal:login_form", "auth:form_login", "type:sqli"],
                "matched_entry_ids": ["mem_1"],
            },
        }
    )
    state.meta_reasonings.append(
        {
            "type": "strategy_memory_wrong_flag_audit",
            "wrong_flag": "flag{wrong_one}",
            "affected_entry_ids": ["mem_1"],
            "auto_muted_entry_ids": ["mem_2"],
            "deprecated_entry_id": "mem_session",
            "matched_atomic_facts": ["signal:login_form", "auth:form_login"],
        }
    )
    layer = ReasoningLayer()

    report = layer.generate_stop_report(
        state,
        reason="wrong flag feedback: flag{wrong_one}",
        missing_capabilities=[],
    )

    joined = " ".join(report.recommended_memory_actions + report.user_next_steps)
    assert report.reason == "wrong_flag_feedback"
    assert report.memory_focus_entry_ids == ["mem_1", "mem_2", "mem_session"]
    assert any("原子事实" in item for item in report.memory_explanations)
    assert (
        "/ctf memory panel filter=audit sort=correlation threshold=0.60"
        in report.memory_quick_commands
    )
    assert "/ctf memory show mem_1" in report.memory_quick_commands
    assert "/ctf memory rollback mem_2" in report.memory_quick_commands
    assert "/ctf memory show mem_session" in report.memory_quick_commands
    assert "/ctf memory audit 0.60 sort=correlation" in joined
    assert "/ctf memory rollback mem_2" in joined
    assert "deprecated" in joined


def test_reasoning_layer_stop_report_includes_atomic_fact_memory_explanations():
    state = CTFState(target="http://ctf.local/login", goal="拿到flag", detected_type="sqli")
    state.meta_reasonings.extend(
        [
            {
                "type": "strategy_memory_audit",
                "current_atomic_facts": ["type:sqli", "signal:login_form", "auth:form_login"],
                "matched_entries": [
                    {
                        "id": "mem_1",
                        "atomic_facts": ["type:sqli", "signal:login_form", "auth:form_login"],
                        "winning_hypothesis_kinds": ["auth_form_sqli"],
                        "failed_hypothesis_kinds": [],
                    }
                ],
            },
            {
                "type": "hypothesis_memory_adjustment",
                "kind": "auth_form_sqli",
                "applied_adjustment": 0.15,
                "metadata": {
                    "reason": "atomic_fact_supported",
                    "matched_atomic_facts": ["signal:login_form", "auth:form_login"],
                    "required_atomic_facts": ["signal:login_form", "auth:form_login", "type:sqli"],
                    "matched_entry_ids": ["mem_1"],
                },
            },
        ]
    )
    layer = ReasoningLayer()

    report = layer.generate_stop_report(
        state,
        reason="runtime flag pending verification",
        missing_capabilities=[],
    )

    joined = " ".join(report.memory_explanations)
    assert "当前题目原子事实" in joined
    assert "历史记忆 `mem_1`" in joined
    assert "auth_form_sqli" in joined


def test_reasoning_layer_marks_already_solved_platform_stop():
    state = CTFState(target="https://ctf.example.com/challenges/42", goal="拿到flag")
    layer = ReasoningLayer()

    report = layer.generate_stop_report(
        state,
        reason="platform challenge already solved",
        missing_capabilities=[],
    )

    joined = " ".join(report.user_next_steps)
    assert report.reason == "challenge_already_solved"
    assert "已 solved" in joined


def test_reasoning_layer_treats_uniform_blocked_surface_as_failure():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    layer = ReasoningLayer()
    experiment = layer.plan_chain_execution(
        state,
        chain_name="web",
        hypothesis=None,
        strategy=None,
        capability_primitive="template_probe",
        capability_choice=None,
        alternatives=[],
    )

    outcome = layer.evaluate_experiment_result(
        state,
        experiment_id=experiment.id,
        progress_delta="rejected",
        observed_signal="render parameter surface returned uniform blocked responses",
    )

    assert outcome == "failure"
    assert state.surprises == []


def test_reasoning_layer_stop_report_marks_blocked_surface_exhausted():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.add_observation(
        "uniform_failure_surface",
        "200:orz",
        source="ssti_via_render_parameter",
        metadata={
            "strategy_kind": "ssti_via_render_parameter",
            "reason": "render parameter surface returned uniform blocked responses",
        },
    )
    layer = ReasoningLayer()

    report = layer.generate_stop_report(
        state,
        reason="链路 ssti_via_render_parameter 命中统一失败回显",
        missing_capabilities=[],
    )

    joined = " ".join(report.user_next_steps)
    assert report.reason == "blocked_surface_exhausted"
    assert "统一失败回显" in (report.why_not_pursued or "")
    assert "不要继续重复同一 payload" in joined


def test_pre_action_reasoning_rejects_freeform_failure_next_action():
    try:
        PreActionReasoning(
            id="par_1",
            experiment_id="exp_1",
            created_at=0.0,
            current_belief="belief",
            belief_evidence=[],
            action_rationale="rationale",
            alternatives_rejected=[],
            expected_success_signal="success",
            success_interpretation="interpret success",
            expected_failure_signal="failure",
            failure_interpretation="interpret failure",
            failure_next_action="switch_chain",  # type: ignore[arg-type]
        )
    except ValueError as exc:
        assert "failure_next_action must be one of" in str(exc)
    else:
        raise AssertionError("PreActionReasoning should reject non-enum failure_next_action")


def test_pre_action_reasoning_blocks_vague_expected_signal():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    decision = PreActionReasoning.evaluate(
        {
            "action_type": "http_request",
            "tool_name": "http_request",
            "rationale": "check admin endpoint",
            "payload": {"url": "http://ctf.local/admin"},
            "expected_signal": "看看效果",
            "next_if_fail": "switch chain",
        },
        state,
        target="http://ctf.local",
    )

    assert isinstance(decision, ReasoningDecision)
    assert decision.approve is False
    assert "Q2 blocked" in decision.reason


def test_pre_action_reasoning_blocks_repeated_rejected_flag():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.add_flag(
        "flag{test123}",
        level="rejected",
        evidence_source="user-feedback",
        rationale="wrong flag",
        confidence=1.0,
    )

    decision = PreActionReasoning.evaluate(
        {
            "action_type": "http_request",
            "tool_name": "http_request",
            "rationale": "replay rejected flag",
            "payload": {"url": "http://ctf.local/?flag=flag{test123}"},
            "expected_signal": "200 且 body 含 accepted",
            "next_if_fail": "switch chain",
        },
        state,
        target="http://ctf.local",
    )

    assert decision.approve is False
    assert decision.repeated_reject is True


def test_pre_action_reasoning_allows_stop_action_without_capability_gate():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    class _FakeCapabilityRegistry:
        def resolve_tool_request(self, tool_name: str):
            raise AssertionError("stop action should not hit capability gate")

    decision = PreActionReasoning.evaluate(
        {
            "action_type": "stop",
            "tool_name": "llm",
            "rationale": "wait_for_provider_recovery: all providers unavailable",
            "payload": {},
            "expected_signal": "provider_unavailable",
            "next_if_fail": "switch chain",
        },
        state,
        capability_registry=_FakeCapabilityRegistry(),
        target="http://ctf.local",
    )

    assert decision.approve is True
    assert decision.reason == "approved_stop"


def test_pre_action_reasoning_blocks_install_command():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    decision = PreActionReasoning.evaluate(
        {
            "action_type": "shell",
            "tool_name": "terminal",
            "rationale": "install a tool first",
            "payload": {"command": "pip install sqlmap"},
            "expected_signal": "status 0",
            "next_if_fail": "switch chain",
        },
        state,
        target="http://ctf.local",
    )

    assert decision.approve is False
    assert "install commands" in decision.reason
