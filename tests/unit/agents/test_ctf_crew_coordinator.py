from __future__ import annotations

import asyncio

import pytest

from flaghunter.agents.pa_agent.ctf_crew_coordinator import (
    CTFCrewCoordinator,
    CrewWorkerSpec,
)
from flaghunter.agents.pa_agent.ctf_state import CTFState, Hypothesis
from flaghunter.agents.pa_agent.verifier import CTFVerifier


class _FakeVerifier:
    async def verify_flag(self, state: CTFState, *, flag: str, evidence_source: str, rationale: str = ""):
        state.add_flag(
            flag,
            level="verified",
            evidence_source=evidence_source,
            rationale=rationale or "verified by fake verifier",
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
async def test_ctf_crew_coordinator_starts_three_workers_and_collects_results():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    async def _runner(spec: dict, shared_state: CTFState, cancel_event: asyncio.Event):
        await asyncio.sleep(0.01)
        return {
            "worker_id": spec["worker_id"],
            "observations": [
                {
                    "kind": "crew_observation",
                    "value": spec["task"],
                    "source": spec["worker_type"],
                    "metadata": {"worker_id": spec["worker_id"]},
                }
            ],
            "candidate_flags": [],
            "verified_flag": None,
        }

    coordinator = CTFCrewCoordinator(
        state=state,
        verifier=_FakeVerifier(),
        worker_runner=_runner,
    )
    summary = await coordinator.run(
        [
            CrewWorkerSpec(worker_id="recon-1", worker_type="recon", task="scan /api"),
            CrewWorkerSpec(worker_id="exploit-1", worker_type="exploit", task="test sqli"),
            CrewWorkerSpec(worker_id="llm-1", worker_type="llm_explorer", task="explore unknown"),
        ]
    )

    assert summary.stop_reason == "workers_completed"
    assert summary.started_workers == ["recon-1", "exploit-1", "llm-1"]
    assert set(summary.completed_workers) == {"recon-1", "exploit-1", "llm-1"}
    assert summary.cancelled_workers == []
    assert len(state.observations) == 3
    assert {item.source for item in state.observations} == {
        "recon",
        "exploit",
        "llm_explorer",
    }


@pytest.mark.asyncio
async def test_ctf_crew_coordinator_cancels_remaining_workers_after_verified_flag():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    async def _runner(spec: dict, shared_state: CTFState, cancel_event: asyncio.Event):
        worker_id = spec["worker_id"]
        if worker_id == "exploit-fast":
            await asyncio.sleep(0.02)
            return {
                "worker_id": worker_id,
                "observations": [],
                "candidate_flags": [],
                "verified_flag": "flag{crew_verified}",
            }

        try:
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        return {
            "worker_id": worker_id,
            "observations": [{"kind": "late", "value": worker_id, "source": "recon"}],
            "candidate_flags": [],
            "verified_flag": None,
        }

    coordinator = CTFCrewCoordinator(
        state=state,
        verifier=_FakeVerifier(),
        worker_runner=_runner,
        timeout_seconds=3,
    )
    summary = await coordinator.run(
        [
            CrewWorkerSpec(worker_id="recon-slow", worker_type="recon", task="enum /admin"),
            CrewWorkerSpec(worker_id="exploit-fast", worker_type="exploit", task="fire payload"),
            CrewWorkerSpec(worker_id="verifier-slow", worker_type="verifier", task="double check"),
        ]
    )

    assert summary.stop_reason == "flag_verified"
    assert summary.verified_flag == "flag{crew_verified}"
    assert "exploit-fast" in summary.completed_workers
    assert "recon-slow" in summary.cancelled_workers
    assert "verifier-slow" in summary.cancelled_workers
    assert [record.value for record in state.verified_flags] == ["flag{crew_verified}"]


def test_ctf_crew_coordinator_plans_parallel_recon_workers_from_endpoint_prefixes():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    coordinator = CTFCrewCoordinator(
        state=state,
        verifier=_FakeVerifier(),
    )

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

    specs = coordinator.build_worker_specs(
        target="http://ctf.local",
        page_features=page_features,
    )

    recon_specs = [item for item in specs if item.worker_type == "recon"]
    assert len(recon_specs) == 2
    assert {item.target_filter for item in recon_specs} == {"/api/v1", "/admin"}
    assert all(item.metadata["planned_by"] == "endpoint_prefix" for item in recon_specs)


@pytest.mark.asyncio
async def test_ctf_crew_coordinator_plans_parallel_exploit_workers_and_first_verified_wins():
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
        kind = str(spec.get("metadata", {}).get("hypothesis_kind") or "")
        if kind == "auth_form_sqli":
            await asyncio.sleep(0.02)
            return {
                "worker_id": spec["worker_id"],
                "observations": [],
                "candidate_flags": [],
                "verified_flag": "flag{crew_parallel_exploit}",
            }
        try:
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        return {
            "worker_id": spec["worker_id"],
            "observations": [{"kind": "late", "value": kind, "source": "exploit"}],
            "candidate_flags": [],
            "verified_flag": None,
        }

    coordinator = CTFCrewCoordinator(
        state=state,
        verifier=_FakeVerifier(),
        worker_runner=_runner,
        timeout_seconds=3,
    )
    specs = coordinator.build_worker_specs(
        target="http://ctf.local",
        page_features={"endpoints": []},
    )

    exploit_specs = [item for item in specs if item.worker_type == "exploit"]
    assert len(exploit_specs) == 3
    assert [
        item.metadata["hypothesis_kind"] for item in exploit_specs
    ] == ["auth_form_sqli", "xss_admin_bot_sid", "backup_source_leak"]

    summary = await coordinator.run(exploit_specs)

    assert summary.stop_reason == "flag_verified"
    assert summary.verified_flag == "flag{crew_parallel_exploit}"
    assert len(summary.started_workers) == 3
    assert any(worker_id in summary.cancelled_workers for worker_id in summary.started_workers)
    assert [record.value for record in state.verified_flags] == ["flag{crew_parallel_exploit}"]


@pytest.mark.asyncio
async def test_ctf_crew_coordinator_shadow_graph_guides_second_round_followup():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    seen_specs: list[dict[str, object]] = []

    async def _runner(spec: dict, shared_state: CTFState, cancel_event: asyncio.Event):
        seen_specs.append(
            {
                "worker_id": spec["worker_id"],
                "worker_type": spec["worker_type"],
                "task": spec["task"],
                "metadata": dict(spec.get("metadata") or {}),
            }
        )
        if spec["worker_type"] == "recon":
            return {
                "worker_id": spec["worker_id"],
                "observations": [
                    {
                        "kind": "endpoint_discovery",
                        "value": "recon discovered admin surface",
                        "source": "recon",
                        "metadata": {
                            "endpoints": [
                                "/admin/login",
                                "/admin/export",
                                "/backup.zip",
                            ]
                        },
                    }
                ],
                "candidate_flags": [],
                "verified_flag": None,
            }
        return {
            "worker_id": spec["worker_id"],
            "observations": [],
            "candidate_flags": [],
            "verified_flag": None,
        }

    coordinator = CTFCrewCoordinator(
        state=state,
        verifier=_FakeVerifier(),
        worker_runner=_runner,
        timeout_seconds=3,
    )
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

    summary = await coordinator.run_with_shadow_graph(
        target="http://ctf.local",
        page_features=page_features,
    )

    assert summary.stop_reason == "workers_completed"
    assert len(seen_specs) >= 3
    assert [item["worker_type"] for item in seen_specs[:2]] == ["recon", "recon"]
    assert any(
        item["metadata"].get("planned_by") == "shadow_graph"
        for item in seen_specs[2:]
    )
    assert any(
        "/admin" in str(item["task"]) or "backup" in str(item["task"]).lower()
        for item in seen_specs[2:]
    )


@pytest.mark.asyncio
async def test_crew3_duplicate_candidate_flags_strengthen_confidence_instead_of_duplication():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    async def _runner(spec: dict, shared_state: CTFState, cancel_event: asyncio.Event):
        return {
            "worker_id": spec["worker_id"],
            "observations": [],
            "candidate_flags": ["flag{same_candidate}"],
            "verified_flag": None,
        }

    coordinator = CTFCrewCoordinator(
        state=state,
        verifier=_FakeVerifier(),
        worker_runner=_runner,
        timeout_seconds=3,
    )

    summary = await coordinator.run(
        [
            CrewWorkerSpec(worker_id="worker-a", worker_type="exploit", task="probe A"),
            CrewWorkerSpec(worker_id="worker-b", worker_type="exploit", task="probe B"),
        ]
    )

    assert summary.stop_reason == "workers_completed"
    assert len(state.candidate_flags) == 1
    candidate = state.candidate_flags[0]
    assert candidate.value == "flag{same_candidate}"
    assert candidate.confidence > 0.5
    assert candidate.metadata["corroboration_count"] == 2
    assert set(candidate.metadata["corroborated_worker_ids"]) == {"worker-a", "worker-b"}


@pytest.mark.asyncio
async def test_crew4_runtime_flags_are_verified_independently_without_overwrite():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None)

    async def _runner(spec: dict, shared_state: CTFState, cancel_event: asyncio.Event):
        worker_id = spec["worker_id"]
        if worker_id == "worker-a":
            runtime_flags = ["flag{runtime_one}"]
        else:
            runtime_flags = ["flag{runtime_two}"]
        return {
            "worker_id": worker_id,
            "observations": [],
            "candidate_flags": [],
            "runtime_flags": runtime_flags,
            "verified_flag": None,
        }

    coordinator = CTFCrewCoordinator(
        state=state,
        verifier=verifier,
        worker_runner=_runner,
        timeout_seconds=3,
    )

    summary = await coordinator.run(
        [
            CrewWorkerSpec(worker_id="worker-a", worker_type="exploit", task="payload A"),
            CrewWorkerSpec(worker_id="worker-b", worker_type="exploit", task="payload B"),
        ]
    )

    assert summary.stop_reason == "workers_completed"
    assert {record.value for record in state.runtime_flags} == {
        "flag{runtime_one}",
        "flag{runtime_two}",
    }
    decisions = [
        item
        for item in state.meta_reasonings
        if isinstance(item, dict) and item.get("type") == "flag_verification_decision"
    ]
    assert len([item for item in decisions if item.get("decision") == "runtime"]) == 2


@pytest.mark.asyncio
async def test_crew6_total_timeout_cancels_remaining_workers_and_preserves_completed_observations():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    async def _runner(spec: dict, shared_state: CTFState, cancel_event: asyncio.Event):
        worker_id = spec["worker_id"]
        if worker_id == "fast-recon":
            await asyncio.sleep(0.01)
            return {
                "worker_id": worker_id,
                "observations": [
                    {
                        "kind": "fast_observation",
                        "value": "first result",
                        "source": "recon",
                    }
                ],
                "candidate_flags": [],
                "verified_flag": None,
            }
        try:
            await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            raise
        return {
            "worker_id": worker_id,
            "observations": [],
            "candidate_flags": [],
            "verified_flag": None,
        }

    coordinator = CTFCrewCoordinator(
        state=state,
        verifier=_FakeVerifier(),
        worker_runner=_runner,
        timeout_seconds=0.05,
    )

    summary = await coordinator.run(
        [
            CrewWorkerSpec(worker_id="fast-recon", worker_type="recon", task="fast recon"),
            CrewWorkerSpec(worker_id="slow-exploit", worker_type="exploit", task="slow exploit"),
        ]
    )

    assert summary.stop_reason == "crew_timeout"
    assert "slow-exploit" in summary.cancelled_workers
    assert any(item.value == "first result" for item in state.observations)
