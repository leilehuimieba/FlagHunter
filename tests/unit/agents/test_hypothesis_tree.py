"""§3.1 LATS slice (a): structure + value-init shadow tests.

The tree must be byte-identical to ``choose_chain_order`` (it does not change
selection yet) and must initialise node value from the engine's own score.
"""

from __future__ import annotations

import inspect

from flaghunter.agents.pa_agent import hypothesis_engine as engine_module
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.hypothesis_engine import HypothesisEngine
from flaghunter.agents.pa_agent.hypothesis_tree import (
    HypothesisNode,
    build_hypothesis_tree,
)


def _web_state_with_hypotheses() -> CTFState:
    """A web state that yields several rule-based hypotheses (no memory adjustments)."""
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "recon_url",
        "http://ctf.local",
        source="phase_recon",
        metadata={
            "endpoints": ["/visit", "/admin", "/login", "/index.php?id=1"],
            "forms": 1,
            "backup_clue": True,
            "visit_admin_clue": True,
        },
    )
    state.add_artifact(
        "ctf_runtime_fingerprint",
        location="http://ctf.local",
        source="notes",
        metadata={"content": "backup source code www.zip username password php"},
    )
    return state


def _empty_state() -> CTFState:
    """No accumulated hypotheses → build/choose both fall back to ``generate``."""
    return CTFState(target="http://ctf.local", goal="flag", detected_type="web")


def _typed_state() -> CTFState:
    """A non-web detected_type so the chain order is prepended deterministically."""
    return CTFState(target="http://ctf.local", goal="flag", detected_type="jwt")


# --- byte-identical shadow over choose_chain_order ---------------------------

def _assert_shadow(make_state):
    engine = HypothesisEngine()
    # Fresh, identical states for each side so the two independent rank passes
    # cannot drift via the engine's memory write-back side effects.
    tree = build_hypothesis_tree(engine, make_state())
    via_tree = tree.preferred_chain_order(engine, make_state())
    via_engine = HypothesisEngine().choose_chain_order(make_state())
    assert via_tree == via_engine, f"{via_tree!r} != {via_engine!r}"


def test_tree_chain_order_matches_engine_web():
    _assert_shadow(_web_state_with_hypotheses)


def test_tree_chain_order_matches_engine_empty():
    _assert_shadow(_empty_state)


def test_tree_chain_order_matches_engine_typed():
    _assert_shadow(_typed_state)


def test_tree_chain_order_matches_engine_populated_rank_path():
    # Pre-generate so ``state.hypotheses`` is non-empty and both sides take the
    # *scored rank* path (not the ``generate`` fallback) — exercises shadow
    # equivalence through ranked_with_scores.
    def _populated() -> CTFState:
        s = _web_state_with_hypotheses()
        HypothesisEngine().generate(s)
        return s

    _assert_shadow(_populated)


# --- value initialisation ----------------------------------------------------

def test_node_value_equals_engine_final_score():
    engine = HypothesisEngine()
    state = _web_state_with_hypotheses()
    engine.generate(state)  # populate hypotheses → tree takes the scored rank path
    tree = build_hypothesis_tree(engine, state)

    # Idempotent on this no-memory-adjustment state, so a second pass matches.
    _, scores = engine.ranked_with_scores(state)
    assert tree.candidates, "expected candidate hypotheses"
    for node in tree.candidates:
        assert node.value == scores[node.hypothesis_id]


def test_root_is_root_and_children_are_open_with_links():
    engine = HypothesisEngine()
    tree = build_hypothesis_tree(engine, _web_state_with_hypotheses())
    assert tree.root.is_root
    for node in tree.candidates:
        assert node.parent is tree.root
        assert node.status == "open"
        assert node.visits == 0


def test_preferred_kind_order_is_deduplicated_rank_order():
    engine = HypothesisEngine()
    state = _web_state_with_hypotheses()
    engine.generate(state)  # populate hypotheses → scored rank path
    tree = build_hypothesis_tree(engine, state)
    ranked, _ = engine.ranked_with_scores(state)
    expected: list[str] = []
    for h in ranked:
        if h.kind not in expected:
            expected.append(h.kind)
    assert tree.preferred_kind_order() == expected


# --- determinism -------------------------------------------------------------

def test_build_is_deterministic():
    engine = HypothesisEngine()
    a = build_hypothesis_tree(engine, _web_state_with_hypotheses())
    b = build_hypothesis_tree(HypothesisEngine(), _web_state_with_hypotheses())
    sig_a = [(n.hypothesis_id, n.kind, n.value) for n in a.candidates]
    sig_b = [(n.hypothesis_id, n.kind, n.value) for n in b.candidates]
    assert sig_a == sig_b


# --- off-hot-path guard ------------------------------------------------------

def test_engine_does_not_depend_on_tree_module():
    # Slice (a) is shadow-only: the dependency points tree -> engine, never the
    # reverse. The engine (the live selection authority) must not import or
    # reference the tree, proving the tree cannot affect selection yet.
    src = inspect.getsource(engine_module)
    assert "hypothesis_tree" not in src
    assert "HypothesisTree" not in src


def test_add_child_sets_parent():
    root = HypothesisNode(hypothesis_id="__root__", kind="__root__", value=0.0)
    child = root.add_child(HypothesisNode(hypothesis_id="h1", kind="web", value=0.5))
    assert child.parent is root
    assert root.children == [child]
