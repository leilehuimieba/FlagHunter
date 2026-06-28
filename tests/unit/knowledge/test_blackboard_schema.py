"""Tests for the canonical blackboard schema (P2 / 2A-1).

Pins the typed element shapes and — crucially — that they serialise
byte-identically to the historical ad-hoc dicts, so the read-model consumers
(``llm_executor``, ``swarm_bridge``, ``session_context``) and the existing
``test_blackboard.py`` assertions remain valid.
"""

from __future__ import annotations

from flaghunter.knowledge.blackboard_schema import (
    BoardFact,
    BoardIntent,
    BoardView,
    intent_sort_key,
)


class TestBoardFact:
    def test_observation_emits_observation_keys(self):
        f = BoardFact.observation(subkind="recon", value="login form", source="recon")
        assert f.to_dict() == {
            "kind": "observation",
            "subkind": "recon",
            "value": "login form",
            "source": "recon",
        }

    def test_artifact_emits_location_even_when_none(self):
        f = BoardFact.artifact(value="backup.zip", location=None, source="probe")
        d = f.to_dict()
        assert d == {"kind": "artifact", "value": "backup.zip", "location": None, "source": "probe"}
        assert "location" in d  # key present even when None (byte-identical)

    def test_flag_emits_confidence(self):
        f = BoardFact.flag(kind="verified_flag", value="flag{ok}", source="runtime", confidence=0.9)
        assert f.to_dict() == {
            "kind": "verified_flag",
            "value": "flag{ok}",
            "source": "runtime",
            "confidence": 0.9,
        }

    def test_kinds_emit_disjoint_key_sets(self):
        obs = set(BoardFact.observation(subkind="x", value="v", source="s").to_dict())
        art = set(BoardFact.artifact(value="v", location="/l", source="s").to_dict())
        flag = set(BoardFact.flag(kind="runtime_flag", value="v", source="s", confidence=0.1).to_dict())
        assert "subkind" in obs and "subkind" not in art and "subkind" not in flag
        assert "location" in art and "location" not in obs
        assert "confidence" in flag and "confidence" not in obs

    def test_forward_compat_fields_not_emitted_for_readmodel(self):
        # rationale / artifact_url / exploit_type exist for Layer 2 reuse but are
        # never emitted by the read-model constructors.
        f = BoardFact.observation(subkind="x", value="v", source="s")
        assert "artifact_url" not in f.to_dict()
        assert "exploit_type" not in f.to_dict()


class TestBoardFactWeb:
    """Web-snapshot (Layer 2) emission: camelCase, emit-if-present."""

    def test_plain_fact_emits_only_kind_value(self):
        # e.g. control_decision / next_action / artifact (value=location)
        f = BoardFact.web_fact("control_decision", "blocked")
        assert f.to_web_dict() == {"kind": "control_decision", "value": "blocked"}

    def test_observation_fact_emits_source_and_confidence(self):
        f = BoardFact.web_fact(
            "discovered_endpoint", "http://t/admin", source="recon", confidence="high"
        )
        assert f.to_web_dict() == {
            "kind": "discovered_endpoint",
            "value": "http://t/admin",
            "source": "recon",
            "confidence": "high",
        }

    def test_empty_string_source_is_emitted_but_none_is_omitted(self):
        # source="" is present (not None) → emitted; a fact with no source omits it
        assert "source" in BoardFact.web_fact("k", "v", source="").to_web_dict()
        assert "source" not in BoardFact.web_fact("k", "v").to_web_dict()

    def test_camelcase_optional_fields(self):
        f = BoardFact.web_fact(
            "local_challenge_source_hint",
            "...",
            source="ctx",
            confidence="high",
            artifact_url="/loot/x.php",
            exploit_type="php_unserialize",
        )
        d = f.to_web_dict()
        assert d["artifactUrl"] == "/loot/x.php"
        assert d["exploitType"] == "php_unserialize"

    def test_pending_verification_shape(self):
        f = BoardFact.web_fact(
            "runtime_flag", "flag{rt}", source="collector", rationale="runtime hit"
        )
        assert f.to_web_dict() == {
            "kind": "runtime_flag",
            "value": "flag{rt}",
            "source": "collector",
            "rationale": "runtime hit",
        }

    def test_verified_flag_string_confidence(self):
        f = BoardFact.web_fact("verified_flag", "flag{ok}", source="admin", confidence="high")
        assert f.to_web_dict() == {
            "kind": "verified_flag",
            "value": "flag{ok}",
            "source": "admin",
            "confidence": "high",
        }


class TestBoardIntent:
    def test_uniform_ten_key_shape(self):
        i = BoardIntent(
            id="h1",
            kind="sqli",
            description="d",
            confidence=0.4,
            value_score=0.5,
            status="active",
            refuted=False,
            next_experiments=["e1"],
            directness=1,
            origin="hypothesis",
        )
        assert i.to_dict() == {
            "id": "h1",
            "kind": "sqli",
            "description": "d",
            "confidence": 0.4,
            "value_score": 0.5,
            "status": "active",
            "refuted": False,
            "next_experiments": ["e1"],
            "directness": 1,
            "origin": "hypothesis",
        }

    def test_next_experiments_is_copied(self):
        src = ["e1"]
        i = BoardIntent(
            id="h", kind="k", description="d", confidence=0.0, value_score=0.0,
            status="active", refuted=False, next_experiments=src, directness=0, origin="hypothesis",
        )
        out = i.to_dict()
        out["next_experiments"].append("e2")
        assert src == ["e1"]  # original not mutated


class TestIntentSort:
    def _intent(self, *, value, directness, confidence, refuted=False):
        return BoardIntent(
            id="x", kind="k", description="d", confidence=confidence, value_score=value,
            status="rejected" if refuted else "active", refuted=refuted,
            next_experiments=[], directness=directness, origin="hypothesis",
        )

    def test_active_before_refuted_then_value_then_directness(self):
        high = self._intent(value=0.9, directness=0, confidence=0.5)
        low = self._intent(value=0.4, directness=0, confidence=0.5)
        ref = self._intent(value=0.99, directness=9, confidence=0.9, refuted=True)
        ranked = sorted([low, ref, high], key=intent_sort_key)
        assert [r.value_score for r in ranked[:2]] == [0.9, 0.4]
        assert ranked[-1].refuted is True  # refuted last despite highest value

    def test_directness_breaks_value_ties(self):
        direct = self._intent(value=0.7, directness=1, confidence=0.5)
        far = self._intent(value=0.7, directness=-2, confidence=0.5)
        ranked = sorted([far, direct], key=intent_sort_key)
        assert ranked[0] is direct


class TestBoardView:
    def test_to_dict_three_segments(self):
        view = BoardView(
            facts=[BoardFact.flag(kind="verified_flag", value="f", source="s", confidence=1.0)],
            intents=[
                BoardIntent(
                    id="i", kind="k", description="d", confidence=0.1, value_score=0.1,
                    status="active", refuted=False, next_experiments=[], directness=0,
                    origin="hypothesis",
                )
            ],
            hints=["h"],
        )
        d = view.to_dict()
        assert set(d) == {"facts", "intents", "hints"}
        assert d["facts"][0]["kind"] == "verified_flag"
        assert d["intents"][0]["id"] == "i"
        assert d["hints"] == ["h"]

    def test_empty_view(self):
        assert BoardView().to_dict() == {"facts": [], "intents": [], "hints": []}
