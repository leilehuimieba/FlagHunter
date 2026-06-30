from __future__ import annotations

from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.exploration_stages import (
    ExplorationStage,
    classify_stage,
    stage_guidance,
    stage_plan,
)


def _state() -> CTFState:
    return CTFState(target="http://ctf.local", goal="flag", detected_type="web")


def test_fresh_state_is_detect():
    assert classify_stage(_state()) is ExplorationStage.DETECT


def test_anomaly_marker_advances_to_identify():
    state = _state()
    state.add_observation(
        "llm_exploration_step",
        "response contained a Traceback (most recent call last) stack trace",
        source="llm_driven_exploration",
    )
    assert classify_stage(state) is ExplorationStage.IDENTIFY


def test_confirmed_signal_advances_to_identify():
    state = _state()
    state.add_observation(
        "llm_exploration_step",
        "arithmetic probe returned 49",
        source="llm_driven_exploration",
        metadata={"expected_signal_met": True},
    )
    assert classify_stage(state) is ExplorationStage.IDENTIFY


def test_named_engine_advances_to_exploit():
    state = _state()
    state.add_observation(
        "llm_exploration_step",
        "differential payload confirmed the Jinja2 template engine",
        source="llm_driven_exploration",
        metadata={"expected_signal_met": True},
    )
    assert classify_stage(state) is ExplorationStage.EXPLOIT


def test_classify_is_deterministic():
    state = _state()
    state.add_observation("llm_exploration_step", "twig engine fingerprinted", source="x")
    assert classify_stage(state) is classify_stage(state) is ExplorationStage.EXPLOIT


def test_stage_plan_has_goal_and_actions_for_each_stage():
    for stage in ExplorationStage:
        plan = stage_plan(stage)
        assert plan["goal"]
        assert plan["action_families"]
        assert plan["advance_when"]
        assert plan["anti_pattern"]


def test_stage_guidance_reflects_current_stage():
    detect = stage_guidance(_state())
    assert "exploration_stage=detect" in detect
    assert "do not assume a vuln class" in detect.lower()

    state = _state()
    state.add_observation("llm_exploration_step", "jinja2 confirmed", source="x")
    exploit = stage_guidance(state)
    assert "exploration_stage=exploit" in exploit
