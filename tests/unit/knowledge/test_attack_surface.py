"""P12 — unified attack-surface registry + reachability panel (read-only)."""

from __future__ import annotations

from types import SimpleNamespace

from flaghunter.knowledge.attack_surface import (
    CONFIRMED,
    REFUTED,
    SUSPECTED,
    SurfaceKind,
    collect_attack_surfaces,
    format_attack_surface_panel,
    reachability_score,
)


def _obs(kind, value, *, source="", metadata=None):
    return SimpleNamespace(kind=kind, value=value, source=source, metadata=metadata or {})


def _agenda(url_or_path, *, explored=False, exploration_result="", hint_strength=2,
            discovery_source="recon"):
    return SimpleNamespace(
        url_or_path=url_or_path,
        explored=explored,
        exploration_result=exploration_result,
        hint_strength=hint_strength,
        discovery_source=discovery_source,
    )


def _hyp(kind, *, description="", status="active", confidence=0.0,
         supporting_observations=None, next_experiments=None):
    return SimpleNamespace(
        kind=kind,
        description=description,
        status=status,
        confidence=confidence,
        supporting_observations=supporting_observations or [],
        next_experiments=next_experiments or [],
    )


def _state(*, observations=None, exploration_agenda=None, hypotheses=None):
    return SimpleNamespace(
        observations=observations or [],
        exploration_agenda=exploration_agenda or [],
        hypotheses=hypotheses or [],
    )


# --- reachability scoring -------------------------------------------------

def test_reachability_refuted_is_zero():
    assert reachability_score(REFUTED, 1.0, 4) == 0.0


def test_reachability_confirmed_full_confidence_is_one():
    assert reachability_score(CONFIRMED, 1.0, 0) == 1.0


def test_reachability_confirmed_beats_suspected_at_equal_confidence():
    assert reachability_score(CONFIRMED, 0.5, 0) > reachability_score(SUSPECTED, 0.5, 0)


def test_reachability_directness_nudges_up_but_bounded():
    base = reachability_score(SUSPECTED, 0.5, 0)
    nudged = reachability_score(SUSPECTED, 0.5, 3)
    assert nudged > base
    # directness bonus is capped at 4 steps
    assert reachability_score(SUSPECTED, 0.5, 10) == reachability_score(SUSPECTED, 0.5, 4)


# --- collection ------------------------------------------------------------

def test_empty_state_is_empty_report():
    report = collect_attack_surfaces(_state())
    assert report["summary"]["total"] == 0
    assert report["surfaces"] == []


def test_observation_endpoint_registered_as_suspected():
    report = collect_attack_surfaces(
        _state(observations=[_obs("discovered_endpoint", "http://t/admin")])
    )
    assert report["summary"]["total"] == 1
    surface = report["surfaces"][0]
    assert surface["kind"] == SurfaceKind.ENDPOINT
    assert surface["status"] == SUSPECTED
    assert surface["origin"] == "observation"


def test_source_audit_observation_becomes_source_surface():
    report = collect_attack_surfaces(
        _state(observations=[_obs("source_audit", "svc.py:2 [CWE-502] py_pickle_load")])
    )
    surface = report["surfaces"][0]
    assert surface["kind"] == SurfaceKind.SOURCE
    assert surface["status"] == SUSPECTED


def test_unmapped_observation_kind_is_ignored():
    report = collect_attack_surfaces(
        _state(observations=[_obs("debug_chatter", "noise")])
    )
    assert report["summary"]["total"] == 0


def test_explored_agenda_alive_is_confirmed():
    report = collect_attack_surfaces(
        _state(exploration_agenda=[
            _agenda("/login", explored=True, exploration_result="status=200 body_len=512"),
        ])
    )
    surface = report["surfaces"][0]
    assert surface["status"] == CONFIRMED
    assert surface["kind"] == SurfaceKind.ENDPOINT


def test_explored_agenda_dead_is_refuted_and_zero_reachability():
    report = collect_attack_surfaces(
        _state(exploration_agenda=[
            _agenda("/ghost", explored=True, exploration_result="status=404 body_len=0"),
        ])
    )
    surface = report["surfaces"][0]
    assert surface["status"] == REFUTED
    assert surface["reachability"] == 0.0


def test_unexplored_agenda_is_suspected():
    report = collect_attack_surfaces(
        _state(exploration_agenda=[_agenda("/maybe", explored=False, hint_strength=1)])
    )
    surface = report["surfaces"][0]
    assert surface["status"] == SUSPECTED


def test_hypothesis_maps_to_surface_kind_and_directness():
    report = collect_attack_surfaces(
        _state(hypotheses=[
            _hyp("sqli", description="id param injectable", confidence=0.8,
                 supporting_observations=["o1", "o2"], next_experiments=["e1"]),
        ])
    )
    surface = report["surfaces"][0]
    assert surface["kind"] == SurfaceKind.PARAM
    assert surface["status"] == SUSPECTED
    assert surface["directness"] == 1  # 2 supporting - 1 next


def test_rejected_hypothesis_is_refuted():
    report = collect_attack_surfaces(
        _state(hypotheses=[_hyp("ssti", description="jinja", status="rejected", confidence=0.3)])
    )
    surface = report["surfaces"][0]
    assert surface["status"] == REFUTED


def test_unknown_hypothesis_kind_falls_back_to_vector():
    report = collect_attack_surfaces(
        _state(hypotheses=[_hyp("exotic_thing", description="weird")])
    )
    assert report["surfaces"][0]["kind"] == SurfaceKind.VECTOR


def test_same_surface_merges_to_strongest_status():
    # An endpoint discovered by recon (suspected) and then probed alive (confirmed)
    # must collapse to ONE confirmed row, not two.
    report = collect_attack_surfaces(
        _state(
            observations=[_obs("agenda_exploration", "http://t/api")],
            exploration_agenda=[
                _agenda("http://t/api", explored=False, hint_strength=1),
            ],
        )
    )
    rows = [s for s in report["surfaces"] if s["value"] == "http://t/api"]
    assert len(rows) == 1
    assert rows[0]["status"] == CONFIRMED
    assert "observation" in rows[0]["origin"]
    assert "exploration_agenda" in rows[0]["origin"]


def test_surfaces_sorted_by_reachability_desc():
    report = collect_attack_surfaces(
        _state(
            exploration_agenda=[
                _agenda("/dead", explored=True, exploration_result="error"),
                _agenda("/alive", explored=True, exploration_result="status=200"),
                _agenda("/maybe", explored=False, hint_strength=3),
            ]
        )
    )
    reach = [s["reachability"] for s in report["surfaces"]]
    assert reach == sorted(reach, reverse=True)
    assert report["surfaces"][0]["value"] == "/alive"


def test_summary_counts_and_by_kind():
    report = collect_attack_surfaces(
        _state(
            observations=[_obs("ssti_engine_identified", "jinja2")],
            exploration_agenda=[_agenda("/x", explored=False)],
            hypotheses=[_hyp("sqli", description="p", confidence=0.5)],
        )
    )
    summary = report["summary"]
    assert summary["total"] == 3
    assert summary["confirmed"] == 1  # engine identified
    assert summary["suspected"] == 2  # agenda + hypothesis
    assert summary["by_kind"][SurfaceKind.ENGINE] == 1
    assert summary["by_kind"][SurfaceKind.PARAM] == 1


def test_top_n_caps_surfaces_but_not_summary():
    agenda = [_agenda(f"/p{i}", explored=False) for i in range(5)]
    report = collect_attack_surfaces(_state(exploration_agenda=agenda), top_n=2)
    assert report["summary"]["total"] == 5
    assert len(report["surfaces"]) == 2


# --- formatting ------------------------------------------------------------

def test_format_panel_empty():
    text = format_attack_surface_panel(collect_attack_surfaces(_state()))
    assert "0 total" in text
    assert "no attack surfaces" in text


def test_format_panel_lists_surfaces():
    report = collect_attack_surfaces(
        _state(observations=[_obs("discovered_endpoint", "http://t/admin")])
    )
    text = format_attack_surface_panel(report)
    assert "http://t/admin" in text
    assert "endpoint" in text
    assert "suspected" in text
