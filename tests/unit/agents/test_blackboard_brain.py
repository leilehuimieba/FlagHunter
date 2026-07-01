"""Slice 4 of the 黑板 pivot: the pluggable LLM Brain.

Pins the contract: render the board + tools into a prompt, parse one model reply
into a single Action (robust to fences / prose / garbage), and drive the slice-1
loop with a faked model call — no live provider.
"""

from __future__ import annotations

import pytest

from flaghunter.agents.pa_agent.blackboard_adapter import bind_seams
from flaghunter.agents.pa_agent.blackboard_brain import (
    LLMBrain,
    parse_action,
    render_user_prompt,
)
from flaghunter.agents.pa_agent.blackboard_loop import (
    Action,
    Brain,
    Budget,
    ToolSpec,
    run_blackboard_solve,
)
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.knowledge.blackboard_schema import (
    BoardAttempt,
    BoardFact,
    BoardIntent,
    BoardView,
)


def _view() -> BoardView:
    return BoardView(
        facts=[BoardFact.observation(subkind="recon", value="found /login", source="probe")],
        intents=[
            BoardIntent(
                id="h1",
                kind="sqli",
                description="login form maybe injectable",
                confidence=0.6,
                value_score=0.7,
                status="active",
                refuted=False,
                next_experiments=[],
                directness=2,
                origin="hypothesis",
            )
        ],
        hints=["challenge: blind SQLi"],
    )


# --- render_user_prompt ----------------------------------------------------


def test_render_includes_board_and_tools():
    prompt = render_user_prompt(_view(), [ToolSpec("sqli", "SQL injection probing")])
    assert "found /login" in prompt
    assert "login form maybe injectable" in prompt
    assert "challenge: blind SQLi" in prompt
    assert "sqli: SQL injection probing" in prompt


def test_render_marks_refuted_intent():
    view = _view()
    view.intents[0].refuted = True
    assert "REFUTED-already-tried" in render_user_prompt(view, [])


def test_render_handles_empty_board():
    prompt = render_user_prompt(BoardView(), [])
    assert "- (none)" in prompt


def test_render_surfaces_stalled_attempts_as_negative_feedback():
    # The fixation病: one tool run many times with no progress. The brain must SEE it.
    view = _view()
    view.attempts = [
        BoardAttempt(tool="web", count=12, progress_count=0, last_result="progress=false reason=exhausted"),
        BoardAttempt(tool="lfi", count=9, progress_count=0),
    ]
    prompt = render_user_prompt(view, [])
    assert "ATTEMPTS SO FAR" in prompt
    assert "web: 12x, NO progress" in prompt
    assert "lfi: 9x, NO progress" in prompt
    assert "reason=exhausted" in prompt


def test_render_omits_attempts_section_when_none():
    # Cold start: nothing run yet → no noisy empty section.
    assert "ATTEMPTS SO FAR" not in render_user_prompt(BoardView(), [])


def test_render_shows_progress_attempts_without_dead_end_label():
    view = BoardView(attempts=[BoardAttempt(tool="sqli", count=3, progress_count=1)])
    prompt = render_user_prompt(view, [])
    assert "sqli: 3x (1 made progress)" in prompt
    # the per-attempt dead-end label is only for zero-progress tools
    assert "NO progress" not in prompt


def test_render_surfaces_spinning_attempt_as_switch_signal():
    # progress=true spinning: run many times, few DISTINCT results — the brain must
    # read it as a switch signal, not "made progress" (the third smoke test's lfi-6x).
    view = BoardView(attempts=[BoardAttempt(tool="lfi", count=6, progress_count=1)])
    prompt = render_user_prompt(view, [])
    assert "lfi: 6x but only 1 distinct result(s) -> spinning, switch" in prompt
    # it did make *some* progress, so it is not labelled a zero-progress dead end
    assert "NO progress" not in prompt


# --- parse_action ----------------------------------------------------------


def test_parse_clean_call_tool():
    action = parse_action(
        '{"kind":"call_tool","tool":"sqli","input":{"param":"id"},'
        '"expected_signal":"root:x:","rationale":"probe id"}'
    )
    assert action.kind == "call_tool"
    assert action.tool == "sqli"
    assert action.input == {"param": "id"}
    assert action.expected_signal == "root:x:"


def test_parse_fenced_json():
    action = parse_action('```json\n{"kind":"stop","rationale":"done"}\n```')
    assert action.kind == "stop"
    assert action.rationale == "done"


def test_parse_json_embedded_in_prose():
    action = parse_action('Here is my move:\n{"kind":"write_fact","content":"it is Flask"} hope that helps')
    assert action.kind == "write_fact"
    assert action.content == "it is Flask"


def test_parse_invalid_kind_degrades_to_intent():
    action = parse_action('{"kind":"nuke","content":"x"}')
    assert action.kind == "declare_intent"
    assert action.rationale == "invalid-action-kind"


def test_parse_garbage_degrades_to_intent_without_raising():
    action = parse_action("totally not json at all")
    assert action.kind == "declare_intent"
    assert action.content == "totally not json at all"
    assert action.rationale == "unparsed-brain-response"


def test_parse_empty_degrades_to_intent():
    assert parse_action("").kind == "declare_intent"


# --- LLMBrain --------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_brain_is_brain_and_proposes_parsed_action():
    captured = {}

    async def _call(system, user):
        captured["system"] = system
        captured["user"] = user
        return '{"kind":"call_tool","tool":"web","input":{}}'

    brain = LLMBrain(call=_call)
    assert isinstance(brain, Brain)
    action = await brain.propose(_view(), [ToolSpec("web", "web route")])
    assert action.kind == "call_tool" and action.tool == "web"
    assert "found /login" in captured["user"]
    assert "decision brain" in captured["system"]


class _FakeLLM:
    """Mimics flaghunter.llm.llm.LLM.generate's relevant surface."""

    def __init__(self, content):
        self._content = content
        self.calls = []

    async def generate(self, system_prompt, messages, *, tools=None, max_tokens=None, task_hint="default"):
        self.calls.append({"system": system_prompt, "messages": messages, "task_hint": task_hint})
        return type("R", (), {"content": self._content})()


@pytest.mark.asyncio
async def test_from_llm_adapts_real_generate_surface():
    llm = _FakeLLM('{"kind":"stop","rationale":"solved"}')
    brain = LLMBrain.from_llm(llm, task_hint="ctf_blackboard")
    action = await brain.propose(BoardView(), [])
    assert action.kind == "stop"
    assert llm.calls[0]["task_hint"] == "ctf_blackboard"
    assert llm.calls[0]["messages"][0]["role"] == "user"


# --- end-to-end: brain + seams drive the loop ------------------------------


@pytest.mark.asyncio
async def test_brain_drives_loop_to_stop():
    state = CTFState(target="ex.com", goal="flag")
    replies = iter(
        [
            '{"kind":"declare_intent","content":"look at /login"}',
            '{"kind":"stop","rationale":"no more moves"}',
        ]
    )

    async def _call(system, user):
        return next(replies)

    outcome = await run_blackboard_solve(
        brain=LLMBrain(call=_call),
        hands=type("H", (), {"execute": staticmethod(lambda name, input: None)})(),
        tools=[],
        budget=Budget(max_steps=10),
        **bind_seams(state),
    )

    assert outcome.stopped == "brain_stop"
    assert any(o.kind == "model_intent" and o.value == "look at /login" for o in state.observations)
