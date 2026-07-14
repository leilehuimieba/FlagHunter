"""Phase 6 replay benchmark harness for deterministic CTF dispatcher evals."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import inspect
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Callable, Iterator
from unittest.mock import patch

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher, SolveResult
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.session_context import SessionContextView
from flaghunter.runtime.runtime import LocalRuntime
from flaghunter.tools.notes import set_notes_file
from tests.eval.benchmark_result import BenchmarkReport, ChallengeResult
from tests.eval.llm_inferred_path_server import llm_inferred_path_server
from tests.integration import test_ctf_dispatcher_acceptance as auth_sqli_module
from tests.integration import test_ctf_dispatcher_backup_acceptance as backup_module
from tests.integration import (
    local_challenge_catalog as local_challenge_catalog_module,
)
from tests.integration import (
    local_challenge_runner as local_challenge_runner_module,
)
from tests.integration import (
    test_backup_node_app_candidate_eval as backup_node_app_eval_module,
)
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
def _benchmark_runtime_env() -> Iterator[None]:
    previous = {
        "CPA_M1_API_HUB": os.environ.get("CPA_M1_API_HUB"),
        "LITELLM_LOCAL_MODEL_COST_MAP": os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP"),
        # Strategy memory is now a shared, global cross-challenge store
        # (workspaces.utils.get_strategy_memory_file). A standalone benchmark /
        # model-matrix run builds REAL dispatchers, which query AND save to that
        # store — polluting the production memory with synthetic fixture entries
        # (ctf.local / 127.0.0.1 targets) that then mislead live pheromone recall.
        # Redirect it to a throwaway file for the run's duration so the benchmark
        # stays side-effect-free. (Under pytest, conftest's autouse fixture
        # already sets this; this covers the __main__ / script path.)
        "FLAGHUNTER_STRATEGY_MEMORY_PATH": os.environ.get(
            "FLAGHUNTER_STRATEGY_MEMORY_PATH"
        ),
    }
    os.environ["CPA_M1_API_HUB"] = "false"
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
    with tempfile.TemporaryDirectory() as _sm_dir:
        os.environ["FLAGHUNTER_STRATEGY_MEMORY_PATH"] = str(
            Path(_sm_dir) / "strategy_memory.json"
        )
        try:
            yield
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


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


def _has_wrong_flag_feedback(state: CTFState | None, result: SolveResult) -> bool:
    if state is None:
        return "wrong_flag_feedback" in str(result.reason or "").lower()
    stop_report = state.stop_report if isinstance(state.stop_report, dict) else {}
    stop_class = str(stop_report.get("reason") or "").strip().lower()
    if stop_class == "wrong_flag_feedback":
        return True
    if "wrong_flag_feedback" in str(state.stop_reason or "").lower():
        return True
    if len(state.rejected_flags) > 0:
        return True
    return "wrong_flag_feedback" in str(result.reason or "").lower()


def _has_source_only_artifact_forensics_signal(state: CTFState | None) -> bool:
    if state is None:
        return False
    if state.verified_flags or state.runtime_flags or state.rejected_flags:
        return False
    observation_kinds = {
        str(getattr(item, "kind", "") or "").strip()
        for item in getattr(state, "observations", [])
    }
    return {
        "local_challenge_artifact",
        "artifact_forensics_summary",
    }.issubset(observation_kinds)


def _derive_eval_observed_outcome(
    *,
    result: SolveResult,
    state: CTFState | None,
    wrong_flag_count: int = 0,
) -> str:
    verified_flag_count = len(state.verified_flags) if state is not None else 0
    candidate_flag_count = len(state.candidate_flags) if state is not None else 0
    if result.success or verified_flag_count > 0:
        return "verified_flag"
    if wrong_flag_count > 0 or _has_wrong_flag_feedback(state, result):
        return "unexpected_failure"
    if (
        _has_source_only_stop(state, result)
        or candidate_flag_count > 0
        or _has_source_only_artifact_forensics_signal(state)
    ):
        return "candidate_only_honesty"
    return "honest_no_flag"


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
    observed_outcome = _derive_eval_observed_outcome(
        result=result,
        state=state,
        wrong_flag_count=wrong_flag_count,
    )
    expected_outcome = str((eval_contract or {}).get("expected_outcome") or "").strip()

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
            "eval_verdict": {
                "expected_outcome": expected_outcome,
                "observed_outcome": observed_outcome,
                "matched": bool(expected_outcome) and expected_outcome == observed_outcome,
            },
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
    with _benchmark_runtime_env():
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
    llm: Any | None = None,
) -> tuple[SolveResult, CTFState | None, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="benchmark_llm_unknown_web_") as temp_dir:
        tmp_path = Path(temp_dir)
        with _temporary_cwd(tmp_path), _isolated_notes(tmp_path):
            with _fixture_server(llm_unknown_module.unknown_web_server.__wrapped__) as server:
                # Model matrix injects a real LLM(model=...); the deterministic
                # default benchmark passes none and uses a scripted FakeLLM so the
                # case stays solvable without network (existing behaviour).
                effective_llm = llm
                if effective_llm is None:
                    effective_llm = llm_unknown_module._FakeLLM(
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
                    llm=effective_llm,
                    verification_callback=verification_callback or (lambda flag: "yes"),
                )


async def _run_llm_inferred_path(
    verification_callback: Callable[[str], Any] | None = None,
    llm: Any | None = None,
) -> tuple[SolveResult, CTFState | None, dict[str, Any]]:
    """LLM-differentiating challenge: flag at a path the model must construct.

    No scripted fallback — with ``llm=None`` the deterministic dispatcher never
    builds ``/exports/<archive id>.txt`` and honestly returns no flag, so this
    case only succeeds when a capable injected model reads the page and infers
    the URL. That is what makes the model matrix discriminate.
    """
    with tempfile.TemporaryDirectory(prefix="benchmark_llm_inferred_path_") as temp_dir:
        tmp_path = Path(temp_dir)
        with _temporary_cwd(tmp_path), _isolated_notes(tmp_path):
            with _fixture_server(llm_inferred_path_server) as server:
                return await _execute_dispatcher(
                    target=server["base_url"],
                    goal="拿到flag",
                    challenge_type="auto",
                    llm=llm,
                    verification_callback=verification_callback or (lambda flag: "yes"),
                )


async def _run_local_easy_login_runtime_only(
    verification_callback: Callable[[str], Any] | None = None,
) -> tuple[SolveResult, CTFState | None, dict[str, Any]]:
    sample = local_challenge_catalog_module.get_local_challenge_sample("easy_login")
    with _benchmark_runtime_env():
        with tempfile.TemporaryDirectory(prefix="benchmark_local_easy_login_runtime_only_") as temp_dir:
            tmp_path = Path(temp_dir)
            with _temporary_cwd(tmp_path), _isolated_notes(tmp_path):
                with patch(
                    "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
                    lambda self, tools: {},
                ):
                    runtime = local_challenge_runner_module._EasyLoginRuntimeOnlyFallbackRuntime()
                    dispatcher = CTFTaskDispatcher(
                        runtime=runtime,
                        progress_callback=None,
                        verification_callback=verification_callback,
                    )
                    result = await dispatcher.run(
                        target=sample.target,
                        goal=sample.minimal_prompt,
                        type=sample.mode_subtype,
                        hint="",
                    )
                    run_id = str(getattr(dispatcher, "_ledger_run_id", "") or "").strip()
                    harness_summary = _build_harness_summary_for_run(
                        run_id=run_id,
                        workspace_root=tmp_path,
                    )
                    return result, dispatcher.state, harness_summary


async def _run_local_easy_login_none(
    verification_callback: Callable[[str], Any] | None = None,
) -> tuple[SolveResult, CTFState | None, dict[str, Any]]:
    sample = local_challenge_catalog_module.get_local_challenge_sample("easy_login")
    with _benchmark_runtime_env():
        with tempfile.TemporaryDirectory(prefix="benchmark_local_easy_login_none_") as temp_dir:
            tmp_path = Path(temp_dir)
            with _temporary_cwd(tmp_path), _isolated_notes(tmp_path):
                with patch(
                    "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
                    lambda self, tools: {},
                ):
                    runtime = local_challenge_runner_module._EasyLoginLocalAssetRuntime(
                        enable_local_pivot=False
                    )
                    dispatcher = CTFTaskDispatcher(
                        runtime=runtime,
                        progress_callback=None,
                        verification_callback=verification_callback,
                    )
                    result = await dispatcher.run(
                        target=sample.target,
                        goal=sample.minimal_prompt,
                        type=sample.mode_subtype,
                        hint="",
                    )
                    run_id = str(getattr(dispatcher, "_ledger_run_id", "") or "").strip()
                    harness_summary = _build_harness_summary_for_run(
                        run_id=run_id,
                        workspace_root=tmp_path,
                    )
                    return result, dispatcher.state, harness_summary


async def _run_local_backup_node_app_zip(
    verification_callback: Callable[[str], Any] | None = None,
) -> tuple[SolveResult, CTFState | None, dict[str, Any]]:
    sample = local_challenge_catalog_module.get_local_challenge_sample("backup_node_app")
    with _benchmark_runtime_env():
        with tempfile.TemporaryDirectory(prefix="benchmark_local_backup_node_app_zip_") as temp_dir:
            tmp_path = Path(temp_dir)
            with _temporary_cwd(tmp_path), _isolated_notes(tmp_path):
                with patch(
                    "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
                    lambda self, tools: {},
                ):
                    runtime = backup_node_app_eval_module._BackupNodeAppCandidateRuntime()
                    dispatcher = CTFTaskDispatcher(
                        runtime=runtime,
                        progress_callback=None,
                        verification_callback=verification_callback,
                    )
                    result = await dispatcher.run(
                        target=sample.target,
                        goal=sample.minimal_prompt,
                        type="auto",
                        challenge_context=local_challenge_catalog_module.build_challenge_context(
                            sample,
                            variant="zip",
                        ),
                    )
                    run_id = str(getattr(dispatcher, "_ledger_run_id", "") or "").strip()
                    harness_summary = _build_harness_summary_for_run(
                        run_id=run_id,
                        workspace_root=tmp_path,
                    )
                    return result, dispatcher.state, harness_summary


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
    "llm_inferred_path": _ChallengeSpec(
        challenge_id="llm_inferred_path",
        # Deterministic dispatcher (llm=None) cannot construct the inferred path,
        # so this is "unsolved" without a model — it only solves under the matrix
        # when a capable injected model reads the page and builds the URL.
        expected_solved=False,
        source="tests/eval/llm_inferred_path_server.py::llm_inferred_path_server",
        runner=_run_llm_inferred_path,
    ),
    "local_easy_login_runtime_only": _ChallengeSpec(
        challenge_id="local_easy_login_runtime_only",
        expected_solved=True,
        source="tests/integration/local_challenge_runner.py::easy_login:runtime_only",
        runner=_run_local_easy_login_runtime_only,
        eval_contract={
            "sample_key": "easy_login",
            "variant": "runtime_only",
            "expected_outcome": "verified_flag",
        },
    ),
    "local_easy_login_none": _ChallengeSpec(
        challenge_id="local_easy_login_none",
        expected_solved=False,
        source="tests/integration/local_challenge_runner.py::easy_login:none",
        runner=_run_local_easy_login_none,
        eval_contract={
            "sample_key": "easy_login",
            "variant": "none",
            "expected_outcome": "honest_no_flag",
        },
    ),
    "local_backup_node_app_zip": _ChallengeSpec(
        challenge_id="local_backup_node_app_zip",
        expected_solved=False,
        source="tests/integration/local_challenge_runner.py::backup_node_app:zip",
        runner=_run_local_backup_node_app_zip,
        eval_contract={
            "sample_key": "backup_node_app",
            "variant": "zip",
            "expected_outcome": "candidate_only_honesty",
        },
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
    eval_verdicts = [
        item.metadata.get("eval_verdict")
        for item in results
        if isinstance(item.metadata.get("eval_verdict"), dict)
    ]
    eval_expectation_matches = sum(
        1 for item in eval_verdicts if bool(item.get("matched"))
    )
    eval_expectation_mismatch_ids = [
        item.challenge_id
        for item in results
        if isinstance(item.metadata.get("eval_verdict"), dict)
        and item.metadata["eval_verdict"].get("matched") is False
    ]
    local_eval_results = [
        item
        for item in results
        if isinstance(item.metadata.get("eval_contract"), dict)
        and str(item.metadata["eval_contract"].get("sample_key") or "").strip()
    ]
    local_eval_matches = sum(
        1
        for item in local_eval_results
        if isinstance(item.metadata.get("eval_verdict"), dict)
        and bool(item.metadata["eval_verdict"].get("matched"))
    )
    local_eval_mismatch_ids = [
        item.challenge_id
        for item in local_eval_results
        if isinstance(item.metadata.get("eval_verdict"), dict)
        and item.metadata["eval_verdict"].get("matched") is False
    ]
    local_eval_sample_keys = list(
        dict.fromkeys(
            str(item.metadata["eval_contract"].get("sample_key") or "").strip()
            for item in local_eval_results
            if isinstance(item.metadata.get("eval_contract"), dict)
            and str(item.metadata["eval_contract"].get("sample_key") or "").strip()
        )
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
            "eval_expectation_match_rate": round(
                eval_expectation_matches / len(eval_verdicts), 4
            )
            if eval_verdicts
            else 0.0,
            "eval_expectation_mismatch_ids": eval_expectation_mismatch_ids,
            "local_eval_case_count": len(local_eval_results),
            "local_eval_match_rate": round(local_eval_matches / len(local_eval_results), 4)
            if local_eval_results
            else 0.0,
            "local_eval_mismatch_ids": local_eval_mismatch_ids,
            "local_eval_sample_keys": local_eval_sample_keys,
        },
    )


async def run_benchmark(
    challenges: list[str] | None = None,
    report_path: str | None = None,
    verification_callback: Callable[[str], Any] | None = None,
    llm: Any | None = None,
    write_report: bool = True,
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
        # Only forward the injected LLM to runners that declare an ``llm``
        # parameter, so legacy/fake runners that take just the verification
        # callback keep working unchanged.
        runner_kwargs: dict[str, Any] = {}
        if llm is not None:
            try:
                runner_params = inspect.signature(spec.runner).parameters
            except (TypeError, ValueError):
                runner_params = {}
            if "llm" in runner_params:
                runner_kwargs["llm"] = llm
        raw_result = await spec.runner(callback, **runner_kwargs)
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
    if write_report:
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
