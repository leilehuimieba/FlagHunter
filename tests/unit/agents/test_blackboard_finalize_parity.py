"""Cutover parity gate: blackboard-loop terminal verdict == chain-order terminal verdict.

Both the old chain-order harness (``_run_solve_loop``) and the new model-driven
blackboard loop (``_run_blackboard_loop``) converge on the SAME shared terminal
contract — ``RecoveryController.finalize`` (recovery.py). So "does flipping
``FLAGHUNTER_BLACKBOARD_LOOP`` to default-ON regress how a give-up is classified?"
reduces to a single question: **does the blackboard path feed ``finalize`` the same
inputs the chain-order path would?**

Two inputs matter:
  • ``used_chains`` — both derive it from the run's chain history (equivalent).
  • ``no_progress_count`` — the ONLY genuinely-derived input. The chain-order path
    maintains a real ``no_progress_rounds`` counter via ``mark_no_progress``; the
    blackboard path never runs that contract, so H2 derives an equivalent count from
    the ATTEMPTS ledger: the number of DISTINCT tools whose runs stalled
    (``BoardAttempt.stalled`` = count>=2 && (progress_count==0 || count-progress>=3)).
    If that derivation under- or over-counts, the flip would silently mislabel a
    ``stop_no_progress`` give-up as ``stop_generic`` (or vice versa), skewing session
    telemetry and cross-run learning — exactly the regression H2 fixed.

This module pins the derivation at the ``>=3`` threshold boundary and confirms the
flag/candidate/clean-miss verdicts route through the identical shared contract. It is
the deterministic (no LLM creds, no live 爆破) guard the cutover's flag-flip points to.
The per-cut mapping is already pinned in test_blackboard_loop_bypass.py; this is the
consolidated flip-readiness matrix.
"""

from __future__ import annotations

import pytest

from flaghunter.agents.pa_agent.blackboard import _project_attempts
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher, SolveResult
from flaghunter.agents.pa_agent.ctf_state import CTFState


class _FakeRuntime:
    name = "fake"


class _StopBrain:
    """Brain that immediately stops: the SEEDED state is the terminal state, so no chain
    runs and the give-up branch classifies exactly the evidence we planted."""

    async def generate(self, system_prompt, messages, *, tools=None, max_tokens=None, task_hint="default"):
        return type("R", (), {"content": '{"kind":"stop","rationale":"seeded terminal state"}'})()


def _dispatcher(monkeypatch):
    disp = CTFTaskDispatcher(runtime=_FakeRuntime(), llm=_StopBrain())
    disp.state = CTFState(target="ex.com", goal="flag")

    async def _identity(result):
        return result

    monkeypatch.setattr(disp, "_finalize_solve_result", _identity)
    monkeypatch.setattr(
        disp, "_chain_handler_map", lambda *, target, page_features, hint: {"web": (lambda: None)}
    )
    return disp


async def _run(disp) -> SolveResult:
    return await disp._run_blackboard_loop(
        target="ex.com", hint="", page_features={}, result=SolveResult(success=False)
    )


def _seed_stalled_tool(state: CTFState, tool: str, *, runs: int = 2) -> None:
    """Plant ``runs`` non-productive tool_result observations for ``tool`` so it reads as a
    stalled dead end (count>=2, progress_count==0)."""
    for _ in range(runs):
        state.add_observation(
            "tool_result",
            f"{tool}: no flag, no progress",  # neither 'flag=' nor 'progress=true' → not productive
            source=tool,
            metadata={"tool": tool},
        )


# --- the teeth: no_progress_count derivation parity at the >=3 threshold ------


@pytest.mark.asyncio
async def test_three_stalled_tools_reach_stop_no_progress(monkeypatch):
    # Three DISTINCT stalled tools → the blackboard ATTEMPTS derivation must yield
    # no_progress_count==3, crossing recovery.finalize's ``>= 3`` threshold, so the
    # give-up is classified ``stop_no_progress`` — the same branch the chain-order path
    # reaches after 3 real no-progress rounds. This is the non-circular guard: if the H2
    # derivation regressed, the count would fall short and mislabel this ``stop_generic``.
    disp = _dispatcher(monkeypatch)
    for tool in ("lfi", "sqli", "upload"):
        _seed_stalled_tool(disp.state, tool)

    # The derivation itself yields exactly 3 (the input finalize receives).
    assert sum(1 for a in _project_attempts(disp.state) if a.stalled) == 3

    result = await _run(disp)

    assert result.success is False
    # stop_no_progress reason carries the count — proves the derived 3 flowed into finalize.
    assert "连续 3 次无新信息" in result.reason
    assert "blackboard_loop:" in result.reason


@pytest.mark.asyncio
async def test_two_stalled_tools_stay_below_threshold(monkeypatch):
    # Two stalled tools → derived count 2, BELOW the >=3 threshold → the give-up must NOT
    # be ``stop_no_progress`` (it falls through to the generic give-up). Guards the other
    # side of the boundary: the derivation must not over-count and trip the branch early.
    disp = _dispatcher(monkeypatch)
    for tool in ("lfi", "sqli"):
        _seed_stalled_tool(disp.state, tool)

    assert sum(1 for a in _project_attempts(disp.state) if a.stalled) == 2

    result = await _run(disp)

    assert result.success is False
    assert "连续" not in result.reason  # not the stop_no_progress branch
    assert "已按收敛规则停止" in result.reason  # stop_generic


# --- terminal-verdict matrix: verdict routes through the shared finalize -------


@pytest.mark.asyncio
async def test_runtime_flag_is_wait_for_verification(monkeypatch):
    disp = _dispatcher(monkeypatch)
    disp.state.add_flag(
        "flag{rt}", level="runtime", evidence_source="verifier", rationale="echoed"
    )

    result = await _run(disp)

    assert result.success is False  # unverified runtime flag is not a clean win
    assert result.flag == "flag{rt}"  # surfaced, not dropped
    assert "尚未 verified" in result.reason  # wait_for_verification (shared finalize)
    assert disp.state.repertoire_miss is False  # a near-solve is not a repertoire miss


@pytest.mark.asyncio
async def test_candidate_only_flag_is_stop_candidate_only(monkeypatch):
    disp = _dispatcher(monkeypatch)
    disp.state.add_flag(
        "flag{src}", level="candidate", evidence_source="grep", rationale="in source"
    )

    result = await _run(disp)

    assert result.success is False
    assert result.flag == "flag{src}"
    assert "source-only candidate flag" in result.reason  # stop_candidate_only
    assert disp.state.repertoire_miss is False


@pytest.mark.asyncio
async def test_verified_flag_is_clean_success(monkeypatch):
    disp = _dispatcher(monkeypatch)
    disp.state.add_flag(
        "flag{ok}", level="verified", evidence_source="submit", rationale="accepted"
    )

    result = await _run(disp)

    assert result.success is True
    assert result.flag == "flag{ok}"
    assert result.reason == "blackboard_loop:verified"


@pytest.mark.asyncio
async def test_clean_giveup_is_generic_and_marks_repertoire_miss(monkeypatch):
    # No flags of any level, no stalled tally → the closed repertoire was exhausted with
    # nothing to show: stop_generic AND repertoire_miss set (via the shared is_repertoire_miss
    # predicate finalize routes through), so the CLI radar can sink the unsolved challenge.
    disp = _dispatcher(monkeypatch)

    result = await _run(disp)

    assert result.success is False
    assert "已按收敛规则停止" in result.reason  # stop_generic
    assert disp.state.repertoire_miss is True
