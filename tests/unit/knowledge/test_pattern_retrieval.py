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


def test_shadow_coverage_recall_superset_of_fired_kinds():
    # Gating-readiness (design §2②): before retrieval can REPLACE running all probes,
    # its top-k recall must be a SUPERSET of the kinds the engine actually fires for a
    # given state — else gating would drop a hypothesis (regression). This shadow proof
    # covers the detected_type-driven path; the structural-probe path is future work
    # before the hot-path gating flip.
    from flaghunter.agents.pa_agent.ctf_state import CTFState
    from flaghunter.agents.pa_agent.hypothesis_engine import HypothesisEngine

    idx = PatternIndex.from_dir()
    engine = HypothesisEngine()
    for detected in ("lfi", "cmdi", "ssrf", "upload", "sqli"):
        state = CTFState(target="http://ctf.local", goal="flag", detected_type=detected)
        fired = {h.kind for h in engine._rule_based_hypotheses(state)}
        fired.discard("generic_web_recon")  # meta fallback, not a real pattern
        fingerprint = f"detected_type:{detected} " + detected
        recalled = {r.kind for r in idx.retrieve(fingerprint, top_k=8)}
        missing = fired - recalled
        assert missing == set(), f"{detected}: recall missed fired kinds {sorted(missing)}"


def _state_with(observation_value, *, detected_type="web", metadata=None):
    from flaghunter.agents.pa_agent.ctf_state import CTFState

    state = CTFState(target="http://ctf.local", goal="flag", detected_type=detected_type)
    state.add_observation(
        "recon_url", observation_value, source="phase_recon", metadata=metadata or {}
    )
    return state


def test_shadow_coverage_structural_probe_paths():
    # Gating-readiness for the STRUCTURAL-probe path (jwt/tornado/render/file/hash/
    # unicode/hint/backup/unserialize). For a state that fires each structural probe,
    # build the fingerprint from the SAME probe-visible blob the gating flip would use
    # (engine._state_blob) and assert retrieval recall ⊇ the kinds the engine fires.
    # Any miss here is an alias gap to close BEFORE the gating flip — recall must be a
    # superset or gating would drop a hypothesis (regression).
    from flaghunter.agents.pa_agent.hypothesis_engine import HypothesisEngine

    idx = PatternIndex.from_dir()
    engine = HypothesisEngine()

    cases = [
        # (label, observation value, metadata)
        ("jwt", "HTTP Authorization: Bearer eyJhbGciOiJIUzI1NiJ9 leaked jwt_secret", {}),
        ("tornado", "Server: TornadoServer/6.0 tornado.web framework", {}),
        ("render", "GET /page?msg=hello world template render", {}),
        ("file_endpoint", "GET /download?name=readme and /file?filename=notes", {}),
        ("hash_guard", "GET /file?filename=secret&filehash=ab12 guarded read", {}),
        ("hint", "discovered hint files /hints.txt /welcome.txt /flag.txt", {}),
        ("backup", "exposed www.zip backup .bak source disclosure", {}),
        ("unserialize", "source has unserialize() and __destruct magic method", {}),
        (
            "unicode_price",
            "Unicorn shop: purchase item, price is only one char",
            {"forms_detail": [{"action": "/charge", "inputs": [{"name": "id"}, {"name": "price"}]}]},
        ),
    ]

    failures = []
    for label, value, metadata in cases:
        state = _state_with(value, metadata=metadata)
        fired = {h.kind for h in engine._rule_based_hypotheses(state)}
        fired.discard("generic_web_recon")
        if not fired:
            failures.append(f"{label}: no kind fired (bad test fixture)")
            continue
        fingerprint = engine._state_blob(state)
        recalled = {r.kind for r in idx.retrieve(fingerprint, top_k=12)}
        missing = fired - recalled
        if missing:
            failures.append(f"{label}: fired={sorted(fired)} recall MISSED {sorted(missing)}")

    assert not failures, "gating-safety gaps:\n" + "\n".join(failures)


def test_golden_eval_all_hit_and_mrr_floor():
    # Byte-level regression guard: every known fingerprint recalls its kind within
    # max_rank, and MRR stays above a floor. Tighten the floor as 曲库 grows.
    report = run_eval()
    assert report.total >= 20
    assert report.failures == [], f"golden eval misses: {[(o.expected_kind, o.rank) for o in report.failures]}"
    assert report.hit_rate == 1.0
    assert report.mrr >= 0.6
