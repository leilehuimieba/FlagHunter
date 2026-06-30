from __future__ import annotations

from flaghunter.agents.pa_agent.hypothesis_engine import _CHAIN_BY_KIND
from flaghunter.knowledge.pattern_eval import run_eval
from flaghunter.knowledge.pattern_retrieval import PatternIndex, load_patterns


def test_every_chain_kind_has_a_pattern():
    # Governance: the searchable 曲库 must cover every real chain kind, else a
    # recalled-then-gated kind could have no metadata to recall it (design §2 governance).
    patterns = {p["kind"] for p in load_patterns()}
    meta_kinds = {"llm_driven_exploration", "generic_web_recon"}
    chain_kinds = set(_CHAIN_BY_KIND) - meta_kinds
    missing = chain_kinds - patterns
    assert missing == set(), f"kinds without pattern.json: {sorted(missing)}"


def test_patterns_have_required_schema_fields():
    required = {"id", "kind", "title", "status", "topic", "gate_probe", "exploit_chain_ref", "aliases", "signals"}
    for p in load_patterns():
        assert required <= set(p), f"{p.get('kind')} missing {required - set(p)}"
        assert p["id"] == f"ap-{p['kind']}"
        assert p["aliases"], f"{p['kind']} has no aliases (nothing to recall on)"


def test_retrieval_is_deterministic():
    idx = PatternIndex.from_dir()
    q = "Tornado web server renders {{handler.settings}} cookie_secret ssti"
    first = [(r.kind, r.score) for r in idx.retrieve(q, top_k=8)]
    second = [(r.kind, r.score) for r in idx.retrieve(q, top_k=8)]
    assert first == second
    # ranking is fully ordered (no equal-score adjacent ties left unbroken)
    kinds = [k for k, _ in first]
    assert len(kinds) == len(set(kinds))


def test_retrieval_recalls_expected_kind_in_topk():
    idx = PatternIndex.from_dir()
    res = idx.retrieve("Authorization Bearer eyJ alg HS256 admin token", top_k=5)
    assert "jwt_manipulation" in [r.kind for r in res]


def test_retrieval_empty_query_returns_nothing():
    idx = PatternIndex.from_dir()
    assert idx.retrieve("", top_k=8) == []
    assert idx.retrieve("!!!@@@###", top_k=8) == []


def test_result_carries_chain_ref():
    idx = PatternIndex.from_dir()
    res = idx.retrieve("login form username password sql injection", top_k=5)
    auth = next((r for r in res if r.kind == "auth_form_sqli"), None)
    assert auth is not None
    assert auth.chain == "sqli"


def test_golden_eval_all_hit_and_mrr_floor():
    # Byte-level regression guard: every known fingerprint recalls its kind within
    # max_rank, and MRR stays above a floor. Tighten the floor as 曲库 grows.
    report = run_eval()
    assert report.total >= 20
    assert report.failures == [], f"golden eval misses: {[(o.expected_kind, o.rank) for o in report.failures]}"
    assert report.hit_rate == 1.0
    assert report.mrr >= 0.6
