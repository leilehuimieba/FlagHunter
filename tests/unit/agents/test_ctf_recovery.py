from __future__ import annotations

from flaghunter.agents.pa_agent.ctf_state import CTFState, Hypothesis
from flaghunter.agents.pa_agent.hypothesis_engine import HypothesisEngine
from flaghunter.agents.pa_agent.recovery import RecoveryController, is_repertoire_miss


def _state_with_xss_and_web_hypotheses() -> CTFState:
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="xss")
    state.hypotheses = [
        Hypothesis(
            id="xss_admin_bot_sid",
            kind="xss_admin_bot_sid",
            description="xss path",
            confidence=0.8,
            supporting_observations=["/visit", "/admin"],
            counter_evidence=[],
            next_experiments=["payload"],
        ),
        Hypothesis(
            id="backup_source_leak",
            kind="backup_source_leak",
            description="backup path",
            confidence=0.6,
            supporting_observations=["backup"],
            counter_evidence=[],
            next_experiments=["fetch zip"],
        ),
    ]
    return state


def test_recovery_switches_to_next_chain_when_tools_missing():
    state = _state_with_xss_and_web_hypotheses()
    controller = RecoveryController(HypothesisEngine())

    decision = controller.on_missing_tools(
        state,
        current_chain="xss",
        missing_tools=["http_request"],
        used_chains=["xss"],
    )

    assert decision.should_stop is False
    assert decision.action == "switch_chain"
    assert decision.next_chain_order[0] == "web"


def test_recovery_stops_on_runtime_flag_pending_verification():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="sqli")
    state.add_flag(
        "flag{runtime_only}",
        level="runtime",
        evidence_source="http-response",
        rationale="echoed by target",
    )
    controller = RecoveryController(HypothesisEngine())

    decision = controller.finalize(
        state,
        used_chains=["sqli"],
        no_progress_count=0,
    )

    assert decision.should_stop is True
    assert decision.action == "wait_for_verification"
    assert "runtime flag" in decision.reason


def test_recovery_stops_on_source_only_candidate_without_alternative():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_flag(
        "Syc{candidate_only}",
        level="candidate",
        evidence_source="source-leak",
        rationale="found in source",
        requires_followup=True,
    )
    controller = RecoveryController(HypothesisEngine())

    decision = controller.finalize(
        state,
        used_chains=["web"],
        no_progress_count=1,
    )

    assert decision.should_stop is True
    assert decision.action == "stop_candidate_only"
    assert "source-only candidate flag" in decision.reason
    # candidate flag found → NOT a clean repertoire miss (we got something).
    assert state.repertoire_miss is False


def test_finalize_sets_repertoire_miss_on_generic_giveup():
    # give-up 点法: a run that converges to the generic stop without any flag means
    # the closed repertoire was exhausted unsuccessfully → mark the gap so the ④
    # radar (CLI entry) can capture it as an accumulable candidate.
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    assert state.repertoire_miss is False
    controller = RecoveryController(HypothesisEngine())

    decision = controller.finalize(state, used_chains=["web"], no_progress_count=0)

    assert decision.should_stop is True
    assert decision.action == "stop_generic"
    assert state.repertoire_miss is True


def test_finalize_sets_repertoire_miss_on_no_progress_giveup():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    controller = RecoveryController(HypothesisEngine())

    decision = controller.finalize(state, used_chains=["web"], no_progress_count=3)

    assert decision.action == "stop_no_progress"
    assert state.repertoire_miss is True


def test_finalize_does_not_mark_miss_when_runtime_flag_found():
    # A runtime flag pending verification is a (near-)solve, never a repertoire miss.
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="sqli")
    state.add_flag(
        "flag{runtime_only}",
        level="runtime",
        evidence_source="http-response",
        rationale="echoed by target",
    )
    controller = RecoveryController(HypothesisEngine())

    decision = controller.finalize(state, used_chains=["sqli"], no_progress_count=0)

    assert decision.action == "wait_for_verification"
    assert state.repertoire_miss is False


def _fresh_miss_state(**flags) -> CTFState:
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    if flags.get("runtime"):
        state.add_flag("flag{rt}", level="runtime", evidence_source="resp", rationale="echoed")
    if flags.get("candidate"):
        state.add_flag("flag{cand}", level="candidate", evidence_source="src", rationale="grep")
    return state


def test_is_repertoire_miss_agrees_with_finalize_across_shapes():
    # Pin the shared predicate against finalize's give-up 点法 so the blackboard-loop
    # path (which uses is_repertoire_miss directly, never reaching finalize) can never
    # drift on what counts as a miss. Run finalize on a fresh state, compare its mutated
    # repertoire_miss to the predicate on an identical fresh state.
    for label, flags in [
        ("no flags → miss", {}),
        ("runtime only → not miss", {"runtime": True}),
        ("candidate only → not miss", {"candidate": True}),
    ]:
        controller = RecoveryController(HypothesisEngine())
        via_finalize = _fresh_miss_state(**flags)
        controller.finalize(via_finalize, used_chains=["web"], no_progress_count=0)
        via_predicate = is_repertoire_miss(_fresh_miss_state(**flags))
        assert via_finalize.repertoire_miss == via_predicate, label


def test_is_repertoire_miss_true_on_clean_giveup():
    assert is_repertoire_miss(_fresh_miss_state()) is True


def test_is_repertoire_miss_false_when_any_flag_found():
    assert is_repertoire_miss(_fresh_miss_state(runtime=True)) is False
    assert is_repertoire_miss(_fresh_miss_state(candidate=True)) is False


def test_recovery_switches_after_exhausted_hypothesis():
    state = _state_with_xss_and_web_hypotheses()
    state.hypotheses[0].status = "exhausted"
    controller = RecoveryController(HypothesisEngine())

    decision = controller.after_chain(
        state,
        current_chain="xss",
        active_hypothesis=state.hypotheses[0],
        outcome_progress=False,
        no_progress_count=3,
        used_chains=["xss"],
    )

    assert decision.should_stop is False
    assert decision.action == "switch_chain"
    assert decision.next_chain_order[0] == "web"


def test_recovery_prioritizes_exploration_agenda_before_switching_hypothesis():
    state = _state_with_xss_and_web_hypotheses()
    state.add_exploration_item(
        "/hints.txt",
        discovery_source="link_href",
        hint_strength=2,
    )
    state.add_exploration_item(
        "/file?filename=/flag.txt&filehash=deadbeef",
        discovery_source="response_body",
        hint_strength=1,
    )
    controller = RecoveryController(HypothesisEngine())

    decision = controller.after_chain(
        state,
        current_chain="xss",
        active_hypothesis=state.hypotheses[0],
        outcome_progress=False,
        no_progress_count=3,
        used_chains=["xss"],
    )

    assert decision.should_stop is False
    assert decision.action == "explore_agenda"
    assert [item.url_or_path for item in decision.exploration_items] == [
        "/file?filename=/flag.txt&filehash=deadbeef",
        "/hints.txt",
    ]


def test_recovery_explores_agenda_after_progress_to_close_loop():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.hypotheses = [
        Hypothesis(
            id="hint_chain_followup",
            kind="hint_chain_followup",
            description="hint path",
            confidence=0.8,
            supporting_observations=["/hints.txt"],
            counter_evidence=[],
            next_experiments=["read hinted links"],
        )
    ]
    state.add_exploration_item(
        "/a",
        discovery_source="link_href",
        hint_strength=2,
    )
    controller = RecoveryController(HypothesisEngine())

    decision = controller.after_chain(
        state,
        current_chain="web",
        active_hypothesis=state.hypotheses[0],
        outcome_progress=True,
        no_progress_count=0,
        used_chains=["web"],
    )

    assert decision.should_stop is False
    assert decision.action == "explore_agenda"
    assert [item.url_or_path for item in decision.exploration_items] == ["/a"]


def test_recovery_stops_after_uniform_failure_surface_when_agenda_exhausted():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "uniform_failure_surface",
        "200:orz",
        source="ssti_via_render_parameter",
        metadata={
            "strategy_kind": "ssti_via_render_parameter",
            "reason": "render parameter surface returned uniform blocked responses",
        },
    )
    controller = RecoveryController(HypothesisEngine())

    decision = controller.after_chain(
        state,
        current_chain="web",
        active_hypothesis=None,
        outcome_progress=False,
        no_progress_count=1,
        used_chains=["web"],
    )

    assert decision.should_stop is True
    assert decision.action == "stop_blocked_surface"
    assert "统一失败回显" in decision.reason


def test_recovery_waits_for_provider_recovery_when_all_providers_down():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.capabilities = {"provider_count": 2}
    controller = RecoveryController(HypothesisEngine())

    decision = controller.wait_for_provider_recovery(
        state,
        reason="all providers reported DOWN",
    )

    assert decision.should_stop is True
    assert decision.action == "wait_for_provider_recovery"
    assert "provider 全部不可用" in decision.reason
    assert any("/providers" in item for item in decision.suggested_actions)
