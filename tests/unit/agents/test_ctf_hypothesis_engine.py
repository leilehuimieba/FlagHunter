from __future__ import annotations

from pentestagent.agents.pa_agent.ctf_state import CTFState, FlagProof, Hypothesis
from pentestagent.agents.pa_agent.hypothesis_engine import HypothesisEngine


def test_hypothesis_engine_generates_rule_based_hypotheses_from_state():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "recon_url",
        "http://ctf.local",
        source="phase_recon",
        metadata={
            "endpoints": ["/visit", "/admin", "/login"],
            "forms": 1,
            "backup_clue": True,
            "visit_admin_clue": True,
        },
    )
    state.add_artifact(
        "ctf_runtime_fingerprint",
        location="http://ctf.local",
        source="notes",
        metadata={"content": "backup source code www.zip username password"},
    )

    engine = HypothesisEngine()
    hypotheses = engine.generate(state)
    kinds = [item.kind for item in hypotheses]

    assert "xss_admin_bot_sid" in kinds
    assert "backup_source_leak" in kinds
    assert state.hypotheses == hypotheses


def test_hypothesis_engine_choose_chain_order_uses_ranked_hypotheses():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "recon_url",
        "http://ctf.local",
        source="phase_recon",
        metadata={"endpoints": ["/visit", "/admin"], "forms": 1},
    )
    state.add_artifact(
        "ctf_runtime_fingerprint",
        location="http://ctf.local",
        source="notes",
        metadata={"content": "username password"},
    )

    engine = HypothesisEngine()
    chain_order = engine.choose_chain_order(state)

    assert chain_order[0] == "xss"
    assert "web" in chain_order


def test_hypothesis_engine_generates_xss_hypothesis_from_local_source_hints():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "local_challenge_source_hint",
        "app.py: @app.route('/visit')\n@app.route('/admin')\n@app.route('/login')\nusername password",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\app.py"},
    )

    engine = HypothesisEngine()
    hypotheses = engine.generate(state)
    kinds = [item.kind for item in hypotheses]

    assert "xss_admin_bot_sid" in kinds


def test_hypothesis_engine_choose_chain_order_prefers_xss_from_local_source_hints():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "local_challenge_source_hint",
        "app.py: @app.route('/visit')\n@app.route('/admin')\n@app.route('/login')\nusername password",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\app.py"},
    )

    engine = HypothesisEngine()
    chain_order = engine.choose_chain_order(state)

    assert chain_order[0] == "xss"
    assert "web" in chain_order


def test_hypothesis_engine_feedback_updates_confidence_and_status():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="sqli")
    engine = HypothesisEngine()
    hypotheses = engine.generate(state)
    hypothesis = next(item for item in hypotheses if item.kind == "auth_form_sqli")

    engine.record_experiment_feedback(
        state,
        hypothesis_id=hypothesis.id,
        progress_delta="strong",
        observed_signal="runtime flag pending verification",
    )
    assert hypothesis.confidence > 0.82
    assert hypothesis.status == "active"

    hypothesis.next_experiments = []
    engine.record_experiment_feedback(
        state,
        hypothesis_id=hypothesis.id,
        progress_delta="none",
        observed_signal="no signal 1",
    )
    engine.record_experiment_feedback(
        state,
        hypothesis_id=hypothesis.id,
        progress_delta="none",
        observed_signal="no signal 2",
    )
    engine.record_experiment_feedback(
        state,
        hypothesis_id=hypothesis.id,
        progress_delta="none",
        observed_signal="no signal 3",
    )

    assert hypothesis.counter_evidence.count("none") >= 3
    assert hypothesis.status in {"active", "exhausted"}


def test_hypothesis_engine_adds_structural_hypotheses_from_page_shape():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "recon_url",
        "http://ctf.local/file?filename=/flag.txt&filehash=deadbeef&render=index",
        source="phase_recon",
        metadata={
            "endpoints": [
                "/file?filename=/flag.txt&filehash=deadbeef",
                "/hints.txt",
            ],
            "server": "TornadoServer/6.5",
        },
    )

    engine = HypothesisEngine()
    hypotheses = engine.generate(state)
    kinds = {item.kind for item in hypotheses}

    assert "hash_guarded_file_read" in kinds
    assert "hash_reconstruction_attack" in kinds
    assert "hint_chain_followup" in kinds
    assert "tornado_ssti" in kinds
    assert "ssti_via_render_parameter" in kinds
    assert "path_traversal" in kinds
    assert "file_read_endpoint" in kinds


def test_hypothesis_engine_treats_error_msg_surface_as_render_parameter():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "file_read_redirect",
        "http://ctf.local/error?msg=Error",
        source="file_read_endpoint",
        metadata={
            "url": "http://ctf.local/file?filename=/flag.txt",
            "final_url": "http://ctf.local/error?msg=Error",
            "redirect_history": [
                {
                    "status_code": 302,
                    "url": "http://ctf.local/file?filename=/flag.txt",
                    "location": "/error?msg=Error",
                }
            ],
        },
    )

    engine = HypothesisEngine()
    hypotheses = engine.generate(state)
    kinds = {item.kind for item in hypotheses}

    assert "ssti_via_render_parameter" in kinds


def test_hypothesis_engine_generates_unicode_numeric_form_bypass_from_purchase_form_shape():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "recon_url",
        "http://ctf.local/",
        source="phase_recon",
        metadata={
            "forms": 1,
            "forms_detail": [
                {
                    "action": "http://ctf.local/charge",
                    "method": "post",
                    "inputs": [
                        {"name": "id", "type": "text"},
                        {"name": "price", "type": "text"},
                    ],
                }
            ],
            "endpoints": ["/charge"],
            "content_preview": "Unicorn Shop Purchase Item ID Price Only one char allowed!",
        },
    )

    engine = HypothesisEngine()
    hypotheses = engine.generate(state)
    kinds = [item.kind for item in hypotheses]

    assert "unicode_numeric_form_bypass" in kinds
    assert kinds.index("unicode_numeric_form_bypass") < kinds.index("llm_driven_exploration")


def test_hypothesis_engine_deweights_uniform_failure_surface():
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
    state.add_observation(
        "file_read_redirect",
        "http://ctf.local/error?msg=Error",
        source="file_read_endpoint",
        metadata={"final_url": "http://ctf.local/error?msg=Error"},
    )

    engine = HypothesisEngine()
    hypotheses = engine.generate(state)
    ssti = next(item for item in hypotheses if item.kind == "ssti_via_render_parameter")

    assert ssti.confidence <= 0.08
    assert ssti.status == "exhausted"
    assert "uniform failure surface observed" in ssti.counter_evidence


def test_hypothesis_engine_caps_backup_source_leak_without_backup_clue():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "hint",
        "backup maybe exists but nothing concrete was found",
        source="phase_recon",
        metadata={"backup_clue": False},
    )

    engine = HypothesisEngine()
    hypotheses = engine.generate(state)
    backup = next(item for item in hypotheses if item.kind == "backup_source_leak")

    assert backup.confidence <= 0.2


def test_hypothesis_engine_observation_floor_moves_unsupported_hypothesis_behind_supported_one():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    supported = Hypothesis(
        id="supported_hint_chain",
        kind="hint_chain_followup",
        description="supported",
        confidence=0.55,
        supporting_observations=["obs_1"],
        counter_evidence=[],
        next_experiments=["read hint"],
    )
    unsupported = Hypothesis(
        id="unsupported_generic",
        kind="generic_web_recon",
        description="unsupported but confident",
        confidence=0.95,
        supporting_observations=[],
        counter_evidence=[],
        next_experiments=["recon"],
    )

    ranked = HypothesisEngine().rank(state, [unsupported, supported])

    assert ranked[0].kind == "hint_chain_followup"
    assert ranked[-1].kind == "generic_web_recon"


def test_hypothesis_engine_zeroes_contradicted_memory_bonus():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "recon",
        "page mentions backup in a misleading hint",
        source="phase_recon",
        metadata={"backup_clue": False},
    )
    state.hypothesis_memory_adjustments = {"backup_source_leak": 0.25}
    supported = Hypothesis(
        id="hint_chain_followup",
        kind="hint_chain_followup",
        description="supported",
        confidence=0.6,
        supporting_observations=["obs_1"],
        counter_evidence=[],
        next_experiments=["read hinted file"],
    )
    contradicted = Hypothesis(
        id="backup_source_leak",
        kind="backup_source_leak",
        description="memory boosted but contradicted",
        confidence=0.5,
        supporting_observations=[],
        counter_evidence=[],
        next_experiments=["fetch backup"],
    )

    ranked = HypothesisEngine().rank(state, [contradicted, supported])

    assert state.hypothesis_memory_adjustments["backup_source_leak"] == 0.0
    assert ranked[0].kind == "hint_chain_followup"
    assert any(
        item.get("type") == "hypothesis_memory_adjustment"
        and item.get("kind") == "backup_source_leak"
        and item.get("metadata", {}).get("reason") == "contradiction_zeroed"
        for item in state.meta_reasonings
        if isinstance(item, dict)
    )


def test_hypothesis_engine_atomic_facts_strengthen_memory_adjustment_with_trace():
    state = CTFState(target="http://ctf.local/login", goal="拿到flag", detected_type="sqli")
    state.add_observation(
        "recon",
        "username password sql syntax error",
        source="phase_recon",
        metadata={"forms": [{"inputs": [{"name": "username"}, {"name": "password"}]}]},
    )
    state.hypothesis_memory_adjustments = {"auth_form_sqli": 0.10}
    state.meta_reasonings.append(
        {
            "type": "strategy_memory_audit",
            "current_atomic_facts": [
                "type:sqli",
                "signal:login_form",
                "auth:form_login",
                "error:sql_error",
            ],
            "matched_entries": [
                {
                    "id": "mem_sqli",
                    "atomic_facts": [
                        "type:sqli",
                        "signal:login_form",
                        "auth:form_login",
                        "error:sql_error",
                    ],
                    "winning_hypothesis_kinds": ["auth_form_sqli"],
                    "failed_hypothesis_kinds": [],
                }
            ],
        }
    )
    supported = Hypothesis(
        id="auth_form_sqli",
        kind="auth_form_sqli",
        description="memory supported",
        confidence=0.55,
        supporting_observations=["obs_login"],
        counter_evidence=[],
        next_experiments=["submit auth form with SQLi bypass"],
    )

    HypothesisEngine().rank(state, [supported])

    assert state.hypothesis_memory_adjustments["auth_form_sqli"] > 0.10
    assert any(
        item.get("type") == "hypothesis_memory_adjustment"
        and item.get("kind") == "auth_form_sqli"
        and item.get("metadata", {}).get("reason") == "atomic_fact_supported"
        and "signal:login_form" in list(item.get("metadata", {}).get("matched_atomic_facts") or [])
        for item in state.meta_reasonings
        if isinstance(item, dict)
    )


def test_hypothesis_engine_atomic_facts_weaken_unsupported_memory_bonus():
    state = CTFState(target="http://ctf.local/", goal="拿到flag", detected_type="web")
    state.hypothesis_memory_adjustments = {"backup_source_leak": 0.15}
    state.meta_reasonings.append(
        {
            "type": "strategy_memory_audit",
            "current_atomic_facts": ["type:web"],
            "matched_entries": [
                {
                    "id": "mem_backup",
                    "atomic_facts": ["artifact:backup_archive", "signal:source_hint"],
                    "winning_hypothesis_kinds": ["backup_source_leak"],
                    "failed_hypothesis_kinds": [],
                }
            ],
        }
    )
    supported = Hypothesis(
        id="backup_source_leak",
        kind="backup_source_leak",
        description="memory only",
        confidence=0.40,
        supporting_observations=["soft hint"],
        counter_evidence=[],
        next_experiments=["fetch backup"],
    )

    HypothesisEngine().rank(state, [supported])

    assert state.hypothesis_memory_adjustments["backup_source_leak"] == 0.05
    assert any(
        item.get("type") == "hypothesis_memory_adjustment"
        and item.get("kind") == "backup_source_leak"
        and item.get("metadata", {}).get("reason") == "atomic_fact_weak_support"
        for item in state.meta_reasonings
        if isinstance(item, dict)
    )


def test_hypothesis_engine_wrong_flag_feedback_precisely_downranks_strategy_from_proof():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="sqli")
    engine = HypothesisEngine()
    hypotheses = engine.generate(state)
    hypothesis = next(item for item in hypotheses if item.kind == "auth_form_sqli")
    starting_confidence = hypothesis.confidence
    proof = FlagProof(
        proof_type="runtime_http",
        evidence_source="submit-endpoint",
        evidence_url="http://submit.local/flag",
        evidence_snippet="wrong flag",
        replayable=True,
        submit_confidence=0.85,
        source_trust="runtime",
        hypothesis_id="auth_form_sqli",
        strategy_kind="auth_form_sqli",
        timestamp="2026-05-24T00:00:00+00:00",
    )

    engine.apply_wrong_flag_feedback(
        state,
        flag="flag{wrong_one}",
        rationale="platform rejected submitted runtime flag",
        proof=proof,
    )

    assert hypothesis.confidence < starting_confidence
    assert "wrong_flag:flag{wrong_one}" in hypothesis.counter_evidence
    assert state.hypothesis_memory_adjustments["auth_form_sqli"] == -0.2
    assert any(
        item.get("type") == "hypothesis_wrong_flag_feedback"
        and item.get("proof_strategy_kind") == "auth_form_sqli"
        and "auth_form_sqli" in list(item.get("adjusted_keys") or [])
        for item in state.meta_reasonings
        if isinstance(item, dict)
    )


def test_hypothesis_engine_keeps_llm_fallback_last_when_other_hypotheses_exist():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="sqli")

    hypotheses = HypothesisEngine().generate(state)

    assert hypotheses[-1].kind == "llm_driven_exploration"
    assert hypotheses[-1].confidence == 0.15


def test_hypothesis_engine_promotes_llm_fallback_when_no_other_hypothesis_exists():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="")
    state.observations = []
    state.artifacts = []

    engine = HypothesisEngine()
    only_llm = engine.rank(
        state,
        [
            Hypothesis(
                id="llm_driven_exploration",
                kind="llm_driven_exploration",
                description="fallback",
                confidence=0.55,
                supporting_observations=["fallback:llm"],
                counter_evidence=[],
                next_experiments=["ask llm"],
            )
        ],
    )

    assert len(only_llm) == 1
    assert only_llm[0].kind == "llm_driven_exploration"
    assert only_llm[0].confidence == 0.55


# ---------------------------------------------------------------------------
# Bug-fix regression tests: immediate exhaustion on "orz"
# ---------------------------------------------------------------------------


def _make_hint_chain_hypothesis(state: CTFState) -> Hypothesis:
    """Return the hint_chain_followup hypothesis, generating it if needed.

    Adds the minimal state observations so that HypothesisEngine.generate()
    produces a hint_chain_followup entry.
    """
    state.add_observation(
        "recon_url",
        "http://ctf.local/file?filename=/flag.txt&filehash=deadbeef",
        source="phase_recon",
        metadata={
            "endpoints": ["/file?filename=/flag.txt&filehash=deadbeef", "/hints.txt"],
            "server": "TornadoServer/6.5",
        },
    )
    engine = HypothesisEngine()
    hypotheses = engine.generate(state)
    return next(item for item in hypotheses if item.kind == "hint_chain_followup")


def test_hypothesis_engine_does_not_exhaust_on_first_orz_rejected_signal():
    """progress_delta='rejected' + 'orz' signal must NOT immediately exhaust.

    Historically a single 'orz' signal caused immediate status='exhausted',
    killing hint_chain_followup before the agent could try remaining paths.
    The fix requires *two* consecutive 'uniform_failure_surface' counter-evidence
    entries before marking a hypothesis exhausted.
    """
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    engine = HypothesisEngine()
    hypothesis = _make_hint_chain_hypothesis(state)

    engine.record_experiment_feedback(
        state,
        hypothesis_id=hypothesis.id,
        progress_delta="rejected",
        observed_signal="render parameter surface returned uniform blocked responses ORZ",
    )

    # First hit: confidence crushed but hypothesis must stay alive so the
    # agent can try other chains / explore the agenda.
    assert hypothesis.status not in {"exhausted", "rejected"}, (
        "hypothesis was prematurely killed on a single 'orz' block signal"
    )
    assert "uniform_failure_surface" in hypothesis.counter_evidence


def test_hypothesis_engine_exhausts_on_repeated_orz_rejected_signals():
    """Two 'uniform_failure_surface' entries should trigger exhaustion."""
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    engine = HypothesisEngine()
    hypothesis = _make_hint_chain_hypothesis(state)

    for _ in range(2):
        engine.record_experiment_feedback(
            state,
            hypothesis_id=hypothesis.id,
            progress_delta="rejected",
            observed_signal="uniform failure surface ORZ blocked",
        )

    assert hypothesis.counter_evidence.count("uniform_failure_surface") >= 2
    assert hypothesis.status == "exhausted"
