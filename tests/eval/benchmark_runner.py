"""Phase 6 replay benchmark harness for deterministic CTF dispatcher evals."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Callable, Iterator
from unittest.mock import patch

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher, SolveResult
from pentestagent.agents.pa_agent.ctf_state import CTFState
from pentestagent.knowledge.session_context import SessionContextView
from pentestagent.runtime.runtime import LocalRuntime
from pentestagent.tools.notes import set_notes_file
from tests.eval.benchmark_result import BenchmarkReport, ChallengeResult
from tests.integration import test_ctf_dispatcher_acceptance as auth_sqli_module
from tests.integration import test_ctf_dispatcher_backup_acceptance as backup_module
from tests.integration import (
    test_ctf_dispatcher_easy_tornado_acceptance as easy_tornado_module,
)
from tests.integration import (
    test_ctf_dispatcher_llm_fallback_acceptance as llm_unknown_module,
)
from tests.integration import (
    test_ctf_dispatcher_php_object_injection_acceptance as php_unserialize_module,
)


_BROWSER_MISSING_ERROR = {
    "error": (
        "Playwright not installed. Install with:\n"
        "  pip install playwright\n"
        "  playwright install chromium"
    )
}


@dataclass(frozen=True, slots=True)
class _ChallengeSpec:
    challenge_id: str
    expected_solved: bool
    source: str
    runner: Callable[[Callable[[str], Any] | None], Any]
    eval_contract: dict[str, Any] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_timestamp() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def _compact_timestamp() -> str:
    return _utc_now().strftime("%Y%m%dT%H%M%SZ")


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[2],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            .strip()
        )
    except Exception:
        return "unknown"


@contextmanager
def _temporary_cwd(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


@contextmanager
def _isolated_notes(path: Path) -> Iterator[Path]:
    previous_custom = notes_module._custom_notes_file
    previous_loaded = notes_module._loaded_notes_file
    previous_notes = dict(notes_module._notes)
    notes_file = path / "notes.json"
    set_notes_file(notes_file)
    notes_module._notes.clear()
    notes_module._loaded_notes_file = None
    try:
        yield notes_file
    finally:
        notes_module._notes.clear()
        notes_module._notes.update(previous_notes)
        notes_module._custom_notes_file = previous_custom
        notes_module._loaded_notes_file = previous_loaded


@contextmanager
def _fixture_server(server_factory: Callable[[], Iterator[dict[str, Any]]]) -> Iterator[dict[str, Any]]:
    generator = server_factory()
    payload = next(generator)
    try:
        yield payload
    finally:
        try:
            next(generator)
        except StopIteration:
            pass


async def _browser_missing(action: str, **kwargs) -> dict[str, str]:
    return dict(_BROWSER_MISSING_ERROR)


def _collect_submit_attempts(state: CTFState | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    return [
        item
        for item in state.meta_reasonings
        if isinstance(item, dict) and item.get("type") == "flag_submit_attempt"
    ]


def _has_source_only_stop(state: CTFState | None, result: SolveResult) -> bool:
    if state is None:
        return False
    stop_report = state.stop_report if isinstance(state.stop_report, dict) else {}
    stop_class = str(stop_report.get("reason") or "").strip().lower()
    if stop_class == "candidate_only":
        return True
    return bool(
        state.candidate_flags
        and not state.runtime_flags
        and not state.verified_flags
        and "source-only candidate flag" in str(result.reason or "").lower()
    )


def _first_chain_solve(state: CTFState | None, result: SolveResult) -> bool:
    if state is None or not result.success:
        return False
    return len(result.chain_used) <= 1


def _no_progress_stop(state: CTFState | None) -> bool:
    if state is None:
        return False
    stop_report = state.stop_report if isinstance(state.stop_report, dict) else {}
    stop_class = str(stop_report.get("reason") or "").strip().lower()
    if stop_class == "all_hypotheses_exhausted":
        return True
    return "no progress" in str(state.stop_reason or "").lower()


def _build_challenge_result(
    *,
    challenge_id: str,
    expected_solved: bool,
    source: str,
    result: SolveResult,
    state: CTFState | None,
    wall_time_seconds: float,
    harness_summary: dict[str, Any] | None = None,
    eval_contract: dict[str, Any] | None = None,
) -> ChallengeResult:
    submit_attempts = _collect_submit_attempts(state)
    wrong_flag_count = sum(1 for item in submit_attempts if item.get("correct") is False)
    exhausted_count = (
        sum(1 for item in state.hypotheses if item.status == "exhausted")
        if state is not None
        else 0
    )
    hypothesis_total_count = len(state.hypotheses) if state is not None else 0
    stop_reason = str(result.reason or getattr(state, "stop_reason", "") or "").strip()
    stop_report = state.stop_report if isinstance(getattr(state, "stop_report", None), dict) else {}
    stop_reason_class = str(stop_report.get("reason") or "").strip()
    recovered_after_wrong = bool(wrong_flag_count > 0 and result.success)
    flag_value = result.flag
    if flag_value is None and state is not None and state.verified_flags:
        flag_value = state.verified_flags[-1].value

    # Phase 7: NYU CTF Bench failure taxonomy
    failure_taxonomy: str | None = None
    if not result.success:
        if wrong_flag_count > 0:
            failure_taxonomy = "wrong_answer"
        elif _no_progress_stop(state):
            failure_taxonomy = "give_up"
        else:
            failure_taxonomy = "give_up"

    return ChallengeResult(
        challenge_id=challenge_id,
        solved=bool(result.success),
        expected_solved=expected_solved,
        wrong_flag_count=wrong_flag_count,
        flag_submit_attempts=len(submit_attempts),
        chain_iterations=len(result.chain_used),
        stop_reason=stop_reason,
        stop_reason_class=stop_reason_class,
        has_source_only_stop=_has_source_only_stop(state, result),
        hypothesis_exhausted_count=exhausted_count,
        hypothesis_total_count=hypothesis_total_count,
        wall_time_seconds=round(float(wall_time_seconds), 4),
        candidate_flag_count=len(state.candidate_flags) if state is not None else 0,
        runtime_flag_count=len(state.runtime_flags) if state is not None else 0,
        verified_flag_count=len(state.verified_flags) if state is not None else 0,
        rejected_flag_count=len(state.rejected_flags) if state is not None else 0,
        first_chain_solve=_first_chain_solve(state, result),
        recovered_after_wrong_flag=recovered_after_wrong,
        notes_count=len(result.notes or []),
        flag=flag_value,
        chain_used=list(result.chain_used or []),
        metadata={
            "source": source,
            "no_progress_stop": _no_progress_stop(state),
            "strongest_remaining_hypothesis": (
                stop_report.get("strongest_remaining_hypothesis")
                if isinstance(stop_report, dict)
                else None
            ),
            "harness": dict(harness_summary or {}),
            "eval_contract": dict(eval_contract or {}),
        },
        failure_taxonomy=failure_taxonomy,
    )


def _build_harness_summary_for_run(*, run_id: str, workspace_root: str | Path) -> dict[str, Any]:
    normalized_run_id = str(run_id or "").strip()
    root = Path(workspace_root)
    ledger_path = root / "loot" / "session_ledgers" / f"{normalized_run_id}.jsonl"
    if not normalized_run_id:
        return {
            "has_session_ledger": False,
            "run_id": "",
            "ledger_path": "",
            "event_types": [],
            "tool_event_count": 0,
            "artifact_count": 0,
            "artifact_titles": [],
            "artifact_kinds": [],
            "artifact_producers": [],
            "artifact_categories": [],
            "artifact_locations_preview": [],
            "has_checkpoint": False,
            "latest_checkpoint_label": "",
            "latest_checkpoint_stop_reason": "",
        }

    view = SessionContextView(
        ledger_root=root / "loot" / "session_ledgers",
        artifact_root=root / "loot" / "artifact_registry",
        checkpoint_root=root / "loot" / "checkpoints",
    )
    context = view.build_run_context(normalized_run_id)
    recent_events = context.get("recentEvents") if isinstance(context.get("recentEvents"), list) else []
    latest_checkpoint = context.get("latestCheckpoint") if isinstance(context.get("latestCheckpoint"), dict) else {}
    artifacts = context.get("artifacts") if isinstance(context.get("artifacts"), list) else []
    event_types = [
        str(item.get("type") or "").strip()
        for item in recent_events
        if isinstance(item, dict) and str(item.get("type") or "").strip()
    ]
    tool_event_count = sum(1 for event_type in event_types if event_type.startswith("tool_"))
    artifact_titles = [
        str(item.get("title") or "").strip()
        for item in artifacts
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    artifact_kinds = [
        str(item.get("kind") or "").strip()
        for item in artifacts
        if isinstance(item, dict) and str(item.get("kind") or "").strip()
    ]
    artifact_producers = [
        str(item.get("producer") or "").strip()
        for item in artifacts
        if isinstance(item, dict) and str(item.get("producer") or "").strip()
    ]
    artifact_categories = [
        str((item.get("metadata") or {}).get("category") or "").strip()
        for item in artifacts
        if isinstance(item, dict)
        and isinstance(item.get("metadata"), dict)
        and str((item.get("metadata") or {}).get("category") or "").strip()
    ]
    artifact_locations_preview = []
    seen_artifact_location_keys: set[str] = set()
    seen_artifact_preview_values: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        title_key = str(item.get("title") or "").strip()
        location_value = item.get("location")
        path_value = item.get("path")
        preview = str(location_value or path_value or "").strip()
        location_key = title_key or preview
        if (
            preview
            and location_key
            and location_key not in seen_artifact_location_keys
            and preview not in seen_artifact_preview_values
        ):
            seen_artifact_location_keys.add(location_key)
            seen_artifact_preview_values.add(preview)
            artifact_locations_preview.append(preview)
    artifact_titles = list(dict.fromkeys(artifact_titles))
    artifact_kinds = list(dict.fromkeys(artifact_kinds))
    artifact_producers = list(dict.fromkeys(artifact_producers))
    artifact_categories = list(dict.fromkeys(artifact_categories))
    artifact_locations_preview = artifact_locations_preview[:3]
    return {
        "has_session_ledger": len(recent_events) > 0,
        "run_id": normalized_run_id,
        "ledger_path": str(ledger_path),
        "event_types": event_types,
        "tool_event_count": tool_event_count,
        "artifact_count": len([item for item in artifacts if isinstance(item, dict)]),
        "artifact_titles": artifact_titles,
        "artifact_kinds": artifact_kinds,
        "artifact_producers": artifact_producers,
        "artifact_categories": artifact_categories,
        "artifact_locations_preview": artifact_locations_preview,
        "has_checkpoint": bool(latest_checkpoint),
        "latest_checkpoint_label": str(latest_checkpoint.get("label") or "").strip(),
        "latest_checkpoint_stop_reason": str(latest_checkpoint.get("stopReason") or "").strip(),
    }


def _normalize_runner_result(
    raw: Any,
) -> tuple[SolveResult, CTFState | None, dict[str, Any] | None]:
    if not isinstance(raw, tuple):
        raise TypeError(f"runner must return tuple, got {type(raw)!r}")
    if len(raw) == 2:
        result, state = raw
        return result, state, None
    if len(raw) == 3:
        result, state, harness_summary = raw
        return result, state, dict(harness_summary or {})
    raise ValueError(f"runner returned unexpected tuple length: {len(raw)}")


async def _execute_dispatcher(
    *,
    target: str,
    goal: str,
    challenge_type: str,
    hint: str = "",
    llm: Any | None = None,
    verification_callback: Callable[[str], Any] | None = None,
) -> tuple[SolveResult, CTFState | None, dict[str, Any]]:
    runtime = LocalRuntime()
    await runtime.start()
    try:
        runtime.browser_action = _browser_missing  # type: ignore[method-assign]
        dispatcher = CTFTaskDispatcher(
            runtime=runtime,
            progress_callback=None,
            verification_callback=verification_callback,
            llm=llm,
        )
        result = await dispatcher.run(
            target=target,
            goal=goal,
            type=challenge_type,
            hint=hint,
        )
        run_id = str(getattr(dispatcher, "_ledger_run_id", "") or "").strip()
        harness_summary = _build_harness_summary_for_run(
            run_id=run_id,
            workspace_root=Path.cwd(),
        )
        return result, dispatcher.state, harness_summary
    finally:
        await runtime.stop()


async def _run_easy_tornado(
    verification_callback: Callable[[str], Any] | None = None,
) -> tuple[SolveResult, CTFState | None, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="benchmark_easy_tornado_") as temp_dir:
        tmp_path = Path(temp_dir)
        with _temporary_cwd(tmp_path), _isolated_notes(tmp_path):
            with _fixture_server(easy_tornado_module.easy_tornado_server.__wrapped__) as server:
                return await _execute_dispatcher(
                    target=server["base_url"],
                    goal="拿到flag",
                    challenge_type="auto",
                    verification_callback=verification_callback or (lambda flag: "yes"),
                )


async def _run_php_backup(
    verification_callback: Callable[[str], Any] | None = None,
) -> tuple[SolveResult, CTFState | None, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="benchmark_php_backup_") as temp_dir:
        tmp_path = Path(temp_dir)
        with _temporary_cwd(tmp_path), _isolated_notes(tmp_path):
            with _fixture_server(backup_module.backup_php_server.__wrapped__) as server:
                return await _execute_dispatcher(
                    target=server["base_url"],
                    goal="拿到flag",
                    challenge_type="auto",
                    verification_callback=verification_callback,
                )


async def _run_php_unserialize(
    verification_callback: Callable[[str], Any] | None = None,
) -> tuple[SolveResult, CTFState | None, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="benchmark_php_unserialize_") as temp_dir:
        tmp_path = Path(temp_dir)
        with _temporary_cwd(tmp_path), _isolated_notes(tmp_path):
            with _fixture_server(
                php_unserialize_module.php_object_injection_server.__wrapped__
            ) as server:
                return await _execute_dispatcher(
                    target=server["base_url"],
                    goal="拿到flag",
                    challenge_type="auto",
                    verification_callback=verification_callback or (lambda flag: "yes"),
                )


async def _run_auth_sqli(
    verification_callback: Callable[[str], Any] | None = None,
) -> tuple[SolveResult, CTFState | None, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="benchmark_auth_sqli_") as temp_dir:
        tmp_path = Path(temp_dir)
        with _temporary_cwd(tmp_path), _isolated_notes(tmp_path):
            with _fixture_server(auth_sqli_module.easy_sqli_server.__wrapped__) as server:
                return await _execute_dispatcher(
                    target=server["base_url"],
                    goal="拿到flag",
                    challenge_type="sqli",
                    verification_callback=verification_callback or (lambda flag: "yes"),
                )


async def _run_llm_unknown_web(
    verification_callback: Callable[[str], Any] | None = None,
) -> tuple[SolveResult, CTFState | None, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="benchmark_llm_unknown_web_") as temp_dir:
        tmp_path = Path(temp_dir)
        with _temporary_cwd(tmp_path), _isolated_notes(tmp_path):
            with _fixture_server(llm_unknown_module.unknown_web_server.__wrapped__) as server:
                llm = llm_unknown_module._FakeLLM(
                    [
                        {
                            "action_type": "http_request",
                            "tool_name": "http_request",
                            "rationale": (
                                "known strategies found no anchor; probe secret-looking "
                                "admin text file directly"
                            ),
                            "payload": {
                                "method": "GET",
                                "url": f"{server['base_url']}/admin/secret.txt",
                            },
                            "expected_signal": "200 且 body 含 flag",
                            "next_if_fail": "switch chain",
                        }
                    ]
                )
                return await _execute_dispatcher(
                    target=server["base_url"],
                    goal="拿到flag",
                    challenge_type="auto",
                    llm=llm,
                    verification_callback=verification_callback or (lambda flag: "yes"),
                )


_CHALLENGE_CATALOG: dict[str, _ChallengeSpec] = {
    "easy_tornado": _ChallengeSpec(
        challenge_id="easy_tornado",
        expected_solved=True,
        source="tests/integration/test_ctf_dispatcher_easy_tornado_acceptance.py::easy_tornado_server",
        runner=_run_easy_tornado,
    ),
    "php_backup": _ChallengeSpec(
        challenge_id="php_backup",
        expected_solved=False,
        source="tests/integration/test_ctf_dispatcher_backup_acceptance.py::backup_php_server",
        runner=_run_php_backup,
    ),
    "php_unserialize": _ChallengeSpec(
        challenge_id="php_unserialize",
        expected_solved=True,
        source="tests/integration/test_ctf_dispatcher_php_object_injection_acceptance.py::php_object_injection_server",
        runner=_run_php_unserialize,
    ),
    "auth_sqli": _ChallengeSpec(
        challenge_id="auth_sqli",
        expected_solved=True,
        source="tests/integration/test_ctf_dispatcher_acceptance.py::easy_sqli_server",
        runner=_run_auth_sqli,
    ),
    "llm_unknown_web": _ChallengeSpec(
        challenge_id="llm_unknown_web",
        expected_solved=True,
        source="tests/integration/test_ctf_dispatcher_llm_fallback_acceptance.py::unknown_web_server",
        runner=_run_llm_unknown_web,
    ),
}

_DEFAULT_CHALLENGE_IDS = [
    "easy_tornado",
    "php_backup",
    "php_unserialize",
    "auth_sqli",
    "llm_unknown_web",
]


def _normalize_challenge_ids(challenges: list[str] | None) -> list[str]:
    if not challenges:
        return list(_DEFAULT_CHALLENGE_IDS)
    normalized: list[str] = []
    for raw in challenges:
        key = str(raw or "").strip()
        if not key:
            continue
        if key not in _CHALLENGE_CATALOG:
            supported = ", ".join(sorted(_CHALLENGE_CATALOG))
            raise ValueError(f"Unknown challenge_id: {key}. Supported: {supported}")
        if key not in normalized:
            normalized.append(key)
    return normalized


def _default_report_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "reports" / "benchmarks" / f"benchmark_{_compact_timestamp()}.json"


def _aggregate_report(
    *,
    run_id: str,
    timestamp: str,
    git_sha: str,
    results: list[ChallengeResult],
) -> BenchmarkReport:
    total = len(results)
    solved = sum(1 for item in results if item.solved)
    total_flag_submit_attempts = sum(item.flag_submit_attempts for item in results)
    wrong_flag_submissions = sum(item.wrong_flag_count for item in results)
    stopped_without_flag = sum(1 for item in results if item.verified_flag_count == 0)
    solved_chain_iterations = [
        item.chain_iterations for item in results if item.solved and item.chain_iterations > 0
    ]
    exhausted_total = sum(item.hypothesis_exhausted_count for item in results)
    hypothesis_total = sum(item.hypothesis_total_count for item in results)
    source_only_false_stop = sum(1 for item in results if item.has_source_only_stop)
    recovery_denominator = sum(
        1 for item in results if item.wrong_flag_count > 0 or item.rejected_flag_count > 0
    )
    recovery_numerator = sum(1 for item in results if item.recovered_after_wrong_flag)
    no_progress_stop_count = sum(
        1 for item in results if bool(item.metadata.get("no_progress_stop"))
    )
    first_hit_rate = solved and sum(1 for item in results if item.first_chain_solve) / total or 0.0
    harness_session_hits = sum(
        1
        for item in results
        if isinstance(item.metadata.get("harness"), dict)
        and bool(item.metadata["harness"].get("has_session_ledger"))
    )
    harness_checkpoint_hits = sum(
        1
        for item in results
        if isinstance(item.metadata.get("harness"), dict)
        and bool(item.metadata["harness"].get("has_checkpoint"))
    )
    harness_artifact_hits = sum(
        1
        for item in results
        if isinstance(item.metadata.get("harness"), dict)
        and int(item.metadata["harness"].get("artifact_count", 0) or 0) > 0
    )
    harness_tool_event_hits = sum(
        1
        for item in results
        if isinstance(item.metadata.get("harness"), dict)
        and int(item.metadata["harness"].get("tool_event_count", 0) or 0) > 0
    )

    # Phase 7: failure taxonomy distribution
    failure_distribution: dict[str, int] = {}
    for item in results:
        if item.failure_taxonomy:
            failure_distribution[item.failure_taxonomy] = (
                failure_distribution.get(item.failure_taxonomy, 0) + 1
            )

    return BenchmarkReport(
        run_id=run_id,
        timestamp=timestamp,
        git_sha=git_sha,
        results=results,
        solve_rate=round(solved / total, 4) if total else 0.0,
        wrong_flag_rate=round(
            wrong_flag_submissions / total_flag_submit_attempts, 4
        )
        if total_flag_submit_attempts
        else 0.0,
        premature_stop_rate=round(stopped_without_flag / total, 4) if total else 0.0,
        avg_chains_to_solve=round(
            sum(solved_chain_iterations) / len(solved_chain_iterations), 4
        )
        if solved_chain_iterations
        else 0.0,
        hypothesis_exhaustion_rate=round(exhausted_total / hypothesis_total, 4)
        if hypothesis_total
        else 0.0,
        source_only_false_stop=source_only_false_stop,
        hypothesis_first_hit_rate=round(first_hit_rate, 4),
        recovery_after_wrong_rate=round(
            recovery_numerator / recovery_denominator, 4
        )
        if recovery_denominator
        else 0.0,
        no_progress_stop_rate=round(no_progress_stop_count / total, 4) if total else 0.0,
        total_challenges=total,
        solved_challenges=solved,
        total_flag_submit_attempts=total_flag_submit_attempts,
        wrong_flag_submissions=wrong_flag_submissions,
        failure_distribution=failure_distribution,
        metadata={
            "challenge_ids": [item.challenge_id for item in results],
            "harness_session_coverage": round(harness_session_hits / total, 4) if total else 0.0,
            "harness_checkpoint_coverage": round(harness_checkpoint_hits / total, 4) if total else 0.0,
            "harness_artifact_coverage": round(harness_artifact_hits / total, 4) if total else 0.0,
            "harness_tool_event_coverage": round(harness_tool_event_hits / total, 4)
            if total
            else 0.0,
        },
    )


async def run_benchmark(
    challenges: list[str] | None = None,
    report_path: str | None = None,
    verification_callback: Callable[[str], Any] | None = None,
) -> BenchmarkReport:
    selected_ids = _normalize_challenge_ids(challenges)
    callback = verification_callback or (lambda flag: "yes")
    timestamp = _iso_timestamp()
    run_id = f"benchmark_{_compact_timestamp()}"
    git_sha = _git_sha()
    collected: list[ChallengeResult] = []

    for challenge_id in selected_ids:
        spec = _CHALLENGE_CATALOG[challenge_id]
        started = time.perf_counter()
        raw_result = await spec.runner(callback)
        result, state, harness_summary = _normalize_runner_result(raw_result)
        wall_time = time.perf_counter() - started
        if harness_summary is None and state is not None:
            run_id = getattr(state, "run_id", None)
            if not run_id and hasattr(state, "meta_reasonings"):
                for item in getattr(state, "meta_reasonings", []):
                    if isinstance(item, dict) and item.get("type") == "run_context":
                        run_id = item.get("run_id")
                        break
            if run_id:
                harness_summary = _build_harness_summary_for_run(
                    run_id=str(run_id),
                    workspace_root=Path.cwd(),
                )
        collected.append(
            _build_challenge_result(
                challenge_id=spec.challenge_id,
                expected_solved=spec.expected_solved,
                source=spec.source,
                result=result,
                state=state,
                wall_time_seconds=wall_time,
                harness_summary=harness_summary,
                eval_contract=spec.eval_contract,
            )
        )

    report = _aggregate_report(
        run_id=run_id,
        timestamp=timestamp,
        git_sha=git_sha,
        results=collected,
    )
    destination = Path(report_path) if report_path else _default_report_path()
    report.write_json(destination)
    return report


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 6 replay benchmark harness.")
    parser.add_argument(
        "--challenges",
        nargs="*",
        default=None,
        help="Optional subset of challenge ids to run.",
    )
    parser.add_argument(
        "--report",
        dest="report_path",
        default=None,
        help="Optional output JSON path. Defaults to reports/benchmarks/benchmark_<timestamp>.json",
    )
    return parser


async def _async_main(argv: list[str] | None = None) -> int:
    parser = _build_cli()
    args = parser.parse_args(argv)
    report = await run_benchmark(
        challenges=args.challenges,
        report_path=args.report_path,
    )
    print(report.to_json())
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
