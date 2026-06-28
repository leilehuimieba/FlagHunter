"""Tests for the LLM07 system-prompt-extraction framing taxonomy."""

from __future__ import annotations

from flaghunter.redteam.extraction import (
    TECHNIQUE_ID,
    FAMILIES,
    ExtractionFraming,
    framing_families,
    list_framings,
    ml_only_framings,
)


def test_maps_to_llm07():
    assert TECHNIQUE_ID == "LLM07"


def test_all_framings_well_formed():
    framings = list_framings()
    assert framings, "taxonomy must not be empty"
    for f in framings:
        assert isinstance(f, ExtractionFraming)
        assert f.text.strip(), "framing text must be non-empty"
        assert f.family in FAMILIES, f"unknown family: {f.family}"
        assert isinstance(f.anchorable, bool)


def test_technique_slugs_are_unique():
    slugs = [f.technique for f in list_framings()]
    assert len(slugs) == len(set(slugs)), "technique slugs must be unique"


def test_every_declared_family_is_represented():
    present = set(framing_families())
    assert present == set(FAMILIES), "every FAMILIES entry must have ≥1 framing"


def test_family_filter():
    only_mood = list_framings(families=["A_mood_recast"])
    assert only_mood
    assert {f.family for f in only_mood} == {"A_mood_recast"}


def test_ml_only_are_exactly_the_unanchorable():
    ml = ml_only_framings()
    assert ml, "there must be ML-only (un-anchorable) targets"
    assert all(f.anchorable is False for f in ml)
    assert ml == list_framings(anchorable=False)
    # ...and they are disjoint from the anchorable set.
    anchorable = list_framings(anchorable=True)
    assert anchorable
    assert not ({f.technique for f in ml} & {f.technique for f in anchorable})


def test_no_literal_ignore_imperative():
    """The whole point: these evade the keyword layer, so none may carry the
    direct 'ignore (all) previous/prior instructions' trigger the taxonomy is
    designed to route *around*."""
    for f in list_framings():
        low = f.text.lower()
        assert "ignore all previous" not in low
        assert "ignore previous instructions" not in low
        assert "disregard the" not in low


def test_ml_only_framings_name_no_product_token():
    """Un-anchorable framings must not name a system-prompt product token —
    that is precisely why a regex cannot anchor them."""
    product_tokens = ("system prompt", "init prompt", "initialization prompt")
    for f in ml_only_framings():
        low = f.text.lower()
        for tok in product_tokens:
            assert tok not in low, f"{f.technique} names anchor token {tok!r}"
