"""P10/P11 white-box — code_audit profile auto-scan wiring.

Write side: ``CTFCoordinator._apply_source_audit_contract`` scans the ingested
source tree on source-entry and stores ``_source_audit_findings`` on the
dispatcher (no-op for url-entry / CTF). Read side: the planner prompt builder
surfaces those suspicious points for live verification.

Note: source samples use Python sinks (pickle / subprocess) rather than PHP
``eval($_GET...)`` webshell strings, which on-host AntiVirus may quarantine.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from flaghunter.agents.pa_agent.coordinator import CTFCoordinator
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.llm_executor import LLMExecutor


def _mk_source_state():
    state = CTFState(target="http://t", goal="audit")
    state.entry_kind = "source"
    return state


def _dispatcher(*, entry_kind, challenge_path):
    state = CTFState(target="http://t", goal="audit")
    state.entry_kind = entry_kind
    return SimpleNamespace(
        state=state,
        _challenge_context={"challengePath": str(challenge_path)},
        _source_audit_findings=[],
    )


def _vuln_py(tmp_path):
    # Python deserialization sink (py_pickle_load → CWE-502). Avoids PHP webshell
    # signature strings that AntiVirus tends to quarantine.
    (tmp_path / "svc.py").write_text(
        "import pickle\nobj = pickle.loads(data)\n", encoding="utf-8"
    )


def test_source_entry_scans_and_surfaces_suspicious_points(tmp_path):
    _vuln_py(tmp_path)
    disp = _dispatcher(entry_kind="source", challenge_path=tmp_path)
    CTFCoordinator()._apply_source_audit_contract(disp)

    assert disp._source_audit_findings, "expected suspicious points surfaced"
    joined = "\n".join(disp._source_audit_findings)
    assert "py_pickle_load" in joined
    assert "CWE-502" in joined
    assert any(o.kind == "source_audit" for o in disp.state.observations)


def test_url_entry_is_noop(tmp_path):
    _vuln_py(tmp_path)
    disp = _dispatcher(entry_kind="url", challenge_path=tmp_path)
    CTFCoordinator()._apply_source_audit_contract(disp)
    assert disp._source_audit_findings == []
    assert not any(o.kind == "source_audit" for o in disp.state.observations)


def test_source_entry_clean_tree_is_noop(tmp_path):
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    disp = _dispatcher(entry_kind="source", challenge_path=tmp_path)
    CTFCoordinator()._apply_source_audit_contract(disp)
    assert disp._source_audit_findings == []


def test_missing_challenge_path_is_noop():
    disp = SimpleNamespace(
        state=_mk_source_state(),
        _challenge_context={},
        _source_audit_findings=[],
    )
    CTFCoordinator()._apply_source_audit_contract(disp)
    assert disp._source_audit_findings == []


def test_fail_safe_swallows_scan_error(monkeypatch, tmp_path):
    import flaghunter.tools.source_audit as sa

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(sa, "scan_source", _boom)
    disp = _dispatcher(entry_kind="source", challenge_path=tmp_path)
    CTFCoordinator()._apply_source_audit_contract(disp)
    assert disp._source_audit_findings == []


def test_planner_prompt_surfaces_source_audit_block():
    src = inspect.getsource(LLMExecutor.call_llm_for_action)
    assert "_source_audit_findings" in src
    assert "White-box source audit" in src
