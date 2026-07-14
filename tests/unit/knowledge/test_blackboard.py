from __future__ import annotations

from pathlib import Path

from flaghunter.agents.pa_agent.ctf_state import (
    Artifact,
    CTFState,
    FlagRecord,
    Hypothesis,
    ExplorationItem,
    Observation,
)
from flaghunter.agents.pa_agent.blackboard import project_blackboard
from flaghunter.agents.pa_agent.session_context import SessionContextView
from flaghunter.harness.checkpoint_store import CheckpointStore


def _flag(value: str, level: str = "verified", *, confidence: float = 0.9) -> FlagRecord:
    return FlagRecord(
        value=value,
        level=level,
        evidence_source="runtime",
        rationale="",
        confidence=confidence,
    )


def test_project_blackboard_empty_state_yields_empty_segments():
    board = project_blackboard(CTFState(target="t", goal="g"))
    assert board == {"facts": [], "intents": [], "hints": []}


def test_facts_collect_observations_artifacts_and_flags_including_refuted():
    state = CTFState(target="t", goal="g")
    state.observations.append(Observation(kind="recon", value="login form", source="recon"))
    state.artifacts.append(Artifact(name="backup.zip", location="/loot/backup.zip", source="probe"))
    state.verified_flags.append(_flag("flag{ok}", "verified"))
    state.runtime_flags.append(_flag("flag{rt}", "runtime", confidence=0.6))
    state.rejected_flags.append(_flag("flag{wrong}", "candidate", confidence=0.2))

    board = project_blackboard(state)
    kinds = [f["kind"] for f in board["facts"]]
    assert kinds == ["observation", "artifact", "verified_flag", "runtime_flag", "refuted_flag"]
    refuted = next(f for f in board["facts"] if f["kind"] == "refuted_flag")
    assert refuted["value"] == "flag{wrong}"


def test_intents_rank_active_first_and_keep_refuted_visible_last():
    state = CTFState(target="t", goal="g")
    state.hypotheses.append(
        Hypothesis(id="h1", kind="sqli", description="sqli", confidence=0.4, value_score=0.4)
    )
    state.hypotheses.append(
        Hypothesis(
            id="h2",
            kind="ssti",
            description="ssti",
            confidence=0.9,
            value_score=0.9,
        )
    )
    state.hypotheses.append(
        Hypothesis(
            id="h3",
            kind="lfi",
            description="lfi",
            confidence=0.8,
            status="rejected",
            value_score=0.8,
        )
    )

    board = project_blackboard(state)
    order = [(i["id"], i["refuted"]) for i in board["intents"]]
    # highest-value active first (h2), then h1, then refuted h3 last (still present)
    assert order == [("h2", False), ("h1", False), ("h3", True)]


def test_unexplored_agenda_and_candidate_flags_become_intents():
    state = CTFState(target="t", goal="g")
    state.exploration_agenda.append(
        ExplorationItem(id="e1", url_or_path="/admin", discovery_source="recon", hint_strength=5)
    )
    state.exploration_agenda.append(
        ExplorationItem(
            id="e2",
            url_or_path="/done",
            discovery_source="recon",
            hint_strength=9,
            explored=True,
        )
    )
    state.candidate_flags.append(_flag("flag{maybe}", "candidate", confidence=0.3))

    board = project_blackboard(state)
    origins = {i["origin"] for i in board["intents"]}
    assert origins == {"exploration_agenda", "candidate_flag"}
    # explored agenda item is excluded
    assert all(i["description"] != "/done" for i in board["intents"])


def test_hints_merge_passed_in_with_progress_and_stop_markers():
    state = CTFState(target="t", goal="g")
    state.last_progress_marker = "sqli:weak"
    state.stop_reason = "no_progress"
    board = project_blackboard(state, hints=["  user hint  ", "", "challengePath=/x"])
    assert board["hints"] == [
        "user hint",
        "challengePath=/x",
        "last_progress=sqli:weak",
        "stop_reason=no_progress",
    ]


def test_intent_limit_caps_after_sorting():
    state = CTFState(target="t", goal="g")
    for i in range(20):
        state.hypotheses.append(
            Hypothesis(
                id=f"h{i}",
                kind="k",
                description="d",
                confidence=i / 20.0,
                value_score=i / 20.0,
            )
        )
    board = project_blackboard(state, intent_limit=5)
    assert len(board["intents"]) == 5
    # the highest value_score survives the cap
    assert board["intents"][0]["id"] == "h19"


def test_session_context_view_builds_board_from_latest_checkpoint(tmp_path: Path):
    checkpoint_root = tmp_path / "checkpoints"
    store = CheckpointStore(checkpoint_root)
    state = CTFState(target="http://t", goal="flag")
    state.observations.append(Observation(kind="recon", value="portal", source="recon"))
    state.verified_flags.append(_flag("flag{ok}", "verified"))
    store.save_checkpoint(
        run_id="run-bb", label="dispatcher_started", state_snapshot=state.to_snapshot()
    )

    view = SessionContextView(
        ledger_root=tmp_path / "ledgers",
        artifact_root=tmp_path / "artifacts",
        checkpoint_root=checkpoint_root,
    )
    board = view.build_blackboard_view("run-bb", hints=["go"])
    assert any(f["kind"] == "verified_flag" and f["value"] == "flag{ok}" for f in board["facts"])
    assert any(f["subkind"] == "recon" for f in board["facts"])
    assert "go" in board["hints"]


def test_session_context_view_empty_when_no_checkpoint(tmp_path: Path):
    view = SessionContextView(
        ledger_root=tmp_path / "ledgers",
        artifact_root=tmp_path / "artifacts",
        checkpoint_root=tmp_path / "checkpoints",
    )
    board = view.build_blackboard_view("missing", hints=[" h "])
    assert board == {"facts": [], "intents": [], "hints": ["h"]}


def test_intents_ranked_by_directness_among_equal_value():
    state = CTFState(target="t", goal="g")
    # same value_score; A has fewer remaining steps + more evidence -> more direct
    a = Hypothesis(id="a", kind="sqli", description="direct", confidence=0.5, value_score=0.7)
    a.supporting_observations = ["o1", "o2"]
    a.next_experiments = ["e1"]
    b = Hypothesis(id="b", kind="ssti", description="far", confidence=0.5, value_score=0.7)
    b.supporting_observations = []
    b.next_experiments = ["e1", "e2", "e3"]
    state.hypotheses.extend([b, a])  # insert b first to prove sort, not insertion order

    board = project_blackboard(state)
    order = [i["id"] for i in board["intents"]]
    assert order[0] == "a"  # more direct ranks first at equal value
    a_intent = next(i for i in board["intents"] if i["id"] == "a")
    assert a_intent["directness"] == 1  # 2 supporting - 1 remaining


def test_candidate_flag_is_most_direct():
    state = CTFState(target="t", goal="g")
    state.candidate_flags.append(_flag("flag{maybe}", "candidate", confidence=0.5))
    board = project_blackboard(state)
    cand = next(i for i in board["intents"] if i["origin"] == "candidate_flag")
    assert cand["directness"] == 2


# --- attempts (negative-feedback trail) ------------------------------------


def _tool_result(tool: str, value: str) -> Observation:
    return Observation(kind="tool_result", value=value, source=tool, metadata={"tool": tool})


def _world_obs(kind: str, value: str, source: str = "chain") -> Observation:
    # A world-derived substantive observation (chain finding / artifact / endpoint /
    # signal_met) — NOT a tool_result marker and NOT brain narration (model_fact/intent).
    return Observation(kind=kind, value=value, source=source)


def test_attempts_tally_per_tool_with_progress_detection():
    from flaghunter.agents.pa_agent.blackboard import project_board

    state = CTFState(target="t", goal="g")
    state.observations.append(_tool_result("web", "progress=false reason=exhausted"))
    state.observations.append(_tool_result("web", "progress=false reason=nothing"))
    # sqli's call moved world state (a new endpoint surfaced) before its marker.
    state.observations.append(_world_obs("endpoint", "/admin"))
    state.observations.append(_tool_result("sqli", "progress=true reason=probed"))
    state.observations.append(_tool_result("lfi", "flag=flag{x}"))

    attempts = {a.tool: a for a in project_board(state).attempts}
    assert attempts["web"].count == 2 and attempts["web"].progress_count == 0
    assert attempts["web"].stalled is True
    assert attempts["sqli"].progress_count == 1 and attempts["sqli"].stalled is False
    assert attempts["lfi"].progress_count == 1  # flag= counts as progress


def test_attempts_replayed_progress_counts_once_and_reads_as_spinning():
    # "progress=true spinning": lfi run six times, each an IDENTICAL productive-looking
    # line but no flag and no new world observation. Productive calls stay at 0 and the
    # tool reads as stalled so the brain switches instead of hammering it.
    from flaghunter.agents.pa_agent.blackboard import project_board

    state = CTFState(target="t", goal="g")
    for _ in range(6):
        state.observations.append(_tool_result("lfi", "progress=true reason=commands"))
    lfi = next(a for a in project_board(state).attempts if a.tool == "lfi")
    assert lfi.count == 6
    assert lfi.progress_count == 0  # no flag, no new world substance
    assert lfi.stalled is True


def test_attempts_varying_reason_without_substance_reads_as_spinning():
    # gap-B (LoveSQL): a spinning chain VARIES its reason text every call, so the old
    # distinct-string tally mistook it for progress and never stalled. Substance-based
    # counting ignores the reason string — with no flag and no new world observation the
    # varying-reason spin is non-productive and stalls.
    from flaghunter.agents.pa_agent.blackboard import project_board

    state = CTFState(target="t", goal="g")
    for reason in ("changed", "exhausted", "budget", "generic", "retry", "again"):
        state.observations.append(_tool_result("sqli", f"progress=true reason={reason}"))
    sqli = next(a for a in project_board(state).attempts if a.tool == "sqli")
    assert sqli.count == 6 and sqli.progress_count == 0
    assert sqli.stalled is True


def test_attempts_distinct_progress_not_flagged_spinning():
    # A tool making genuine, DIFFERENT progress each call is not spinning — each call
    # moves WORLD state (a distinct new observation), so productive calls keep pace with
    # the call count even though the reason strings alone would be indistinguishable.
    from flaghunter.agents.pa_agent.blackboard import project_board

    state = CTFState(target="t", goal="g")
    for marker in ("db=shop", "table=users", "col=password"):
        state.observations.append(_world_obs("sqli_dump", marker))
        state.observations.append(_tool_result("sqli", "progress=true reason=dump"))
    sqli = next(a for a in project_board(state).attempts if a.tool == "sqli")
    assert sqli.count == 3 and sqli.progress_count == 3
    assert sqli.stalled is False


def test_attempts_replayed_world_observation_does_not_recount():
    # A chain that re-emits the SAME world observation each call is still spinning:
    # (kind, value) dedup means the repeat introduces no NEW substance.
    from flaghunter.agents.pa_agent.blackboard import project_board

    state = CTFState(target="t", goal="g")
    for _ in range(5):
        state.observations.append(_world_obs("sqli_dump", "table=users"))  # identical
        state.observations.append(_tool_result("sqli", "progress=true reason=dump"))
    sqli = next(a for a in project_board(state).attempts if a.tool == "sqli")
    assert sqli.count == 5
    assert sqli.progress_count == 1  # only the first emission is new substance
    assert sqli.stalled is True


def test_attempts_scan_full_history_beyond_observation_limit():
    # The whole point: results age out of the FACTS window, but the tally must not.
    from flaghunter.agents.pa_agent.blackboard import project_board

    state = CTFState(target="t", goal="g")
    for _ in range(30):
        state.observations.append(_tool_result("web", "progress=false"))

    board = project_board(state, observation_limit=5)
    # FACTS truncated to the recent window, but the attempt tally sees all 30.
    assert len(board.facts) == 5
    web = next(a for a in board.attempts if a.tool == "web")
    assert web.count == 30 and web.stalled is True


def test_attempts_most_repeated_first_dead_ends_prioritised():
    from flaghunter.agents.pa_agent.blackboard import project_board

    state = CTFState(target="t", goal="g")
    for _ in range(5):
        state.observations.append(_tool_result("web", "progress=false"))
    for _ in range(2):
        state.observations.append(_tool_result("misc", "progress=false"))
    attempts = project_board(state).attempts
    assert [a.tool for a in attempts] == ["web", "misc"]


def test_attempts_not_serialised_into_to_dict():
    # Byte-identity guard: the dict read-model stays the historical three-key shape.
    state = CTFState(target="t", goal="g")
    state.observations.append(_tool_result("web", "progress=false"))
    board = project_blackboard(state)
    assert set(board) == {"facts", "intents", "hints"}
    assert "attempts" not in board
