from __future__ import annotations

import asyncio
import time

import pytest

from pentestagent.agents.pa_agent.ctf_crew_coordinator import CTFCrewCoordinator
from pentestagent.agents.pa_agent.ctf_state import CTFState, Hypothesis


class _NoopVerifier:
    async def verify_flag(self, state: CTFState, *, flag: str, evidence_source: str, rationale: str = ""):
        state.add_flag(
            flag,
            level="verified",
            evidence_source=evidence_source,
            rationale=rationale,
            confidence=1.0,
        )
        return type(
            "Verification",
            (),
            {
                "decision": "verified",
                "flag": flag,
                "evidence_source": evidence_source,
                "rationale": rationale,
                "requires_followup": False,
                "metadata": {"platform_verified": False, "operator_confirmed": False},
            },
        )()


@pytest.mark.asyncio
async def test_ctf_crew_latency_gate_beats_serial_baseline_on_dense_endpoint_surface():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.hypotheses = [
        Hypothesis(
            id="hyp-sqli",
            kind="auth_form_sqli",
            description="SQLi login bypass",
            confidence=0.60,
            supporting_observations=["form-login"],
        ),
        Hypothesis(
            id="hyp-xss",
            kind="xss_admin_bot_sid",
            description="XSS admin bot chain",
            confidence=0.55,
            supporting_observations=["visit-admin"],
        ),
        Hypothesis(
            id="hyp-backup",
            kind="backup_source_leak",
            description="Backup/source leak",
            confidence=0.45,
            supporting_observations=["www.zip"],
        ),
    ]

    async def _runner(spec: dict, shared_state: CTFState, cancel_event: asyncio.Event):
        await asyncio.sleep(0.05)
        return {
            "worker_id": spec["worker_id"],
            "observations": [
                {
                    "kind": "timed_probe",
                    "value": spec["task"],
                    "source": spec["worker_type"],
                }
            ],
            "candidate_flags": [],
            "verified_flag": None,
        }

    page_features = {
        "endpoints": [
            "/api/v1/users",
            "/api/v1/roles",
            "/api/v1/logs",
            "/api/v1/debug",
            "/api/v1/health",
            "/admin/panel",
            "/admin/login",
            "/admin/audit",
            "/admin/export",
            "/admin/config",
        ]
    }

    baseline_coordinator = CTFCrewCoordinator(
        state=state,
        verifier=_NoopVerifier(),
        worker_runner=_runner,
        timeout_seconds=2,
    )
    specs = baseline_coordinator.build_worker_specs(
        target="http://ctf.local",
        page_features=page_features,
    )
    assert len(specs) >= 5

    serial_started = time.perf_counter()
    for spec in specs:
        await _runner(spec.to_dict(), state, asyncio.Event())
    serial_elapsed = time.perf_counter() - serial_started

    parallel_state = CTFState(target="http://ctf.local", goal="拿到flag")
    parallel_state.hypotheses = list(state.hypotheses)
    parallel_coordinator = CTFCrewCoordinator(
        state=parallel_state,
        verifier=_NoopVerifier(),
        worker_runner=_runner,
        timeout_seconds=2,
    )

    parallel_started = time.perf_counter()
    summary = await parallel_coordinator.run(specs)
    parallel_elapsed = time.perf_counter() - parallel_started

    assert summary.stop_reason == "workers_completed"
    assert parallel_elapsed < serial_elapsed * 0.6
