from __future__ import annotations

from pathlib import Path

from pentestagent.agents.pa_agent.ctf_state import (
    Artifact,
    CTFState,
    FlagRecord,
    Hypothesis,
    ExplorationItem,
    Observation,
)
from pentestagent.knowledge.blackboard import project_blackboard
from pentestagent.knowledge.session_context import SessionContextView
from pentestagent.harness.checkpoint_store import CheckpointStore


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
