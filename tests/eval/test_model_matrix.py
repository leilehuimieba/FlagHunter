"""Deterministic tests for the model cross-evaluation (模型横评) matrix.

A live matrix run needs provider API keys and drives the full CTF dispatcher (which
escalates to real brute-force tooling on failure — minutes per failing solve), so
that path is opt-in and never exercised in CI. What CI pins here is:

* the matrix *wiring* — ``run_model_matrix`` injects a distinct ``LLM(model=...)``
  per model, threads it through ``run_benchmark(llm=...)``, and aggregates a
  side-by-side comparison;
* that the wiring actually *discriminates* — a "smart" fake reads the export
  archive id off the prompt and infers the ``.txt`` sibling URL (solves against
  the real fixture), while a "dumb" fake fetches the literal advertised path
  (404, no flag) — proving the comparison separates models;
* the new LLM-differentiating fixture's shape — the flag lives only at the
  *inferred* ``/exports/<id>.txt``, never at the advertised ``/exports/<id>``.

The discrimination test consults the injected LLM and hits the real fixture
server over HTTP, but deliberately skips the heavy dispatcher solve loop (covered
by ``test_ctf_dispatcher_acceptance_unknown_web_uses_llm_fallback``) so it stays
fast and deterministic — no network, no API keys.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.eval import benchmark_runner
from tests.eval.llm_inferred_path_server import (
    ARCHIVE_PATH,
    FLAG_PATH,
    FLAG_VALUE,
    llm_inferred_path_server,
)
from tests.eval.model_matrix import ModelMatrixReport, run_model_matrix


class _SmartFakeLLM:
    """Reads the export archive id off the prompt and infers the ``.txt`` URL."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        base = re.search(r"http://127\.0\.0\.1:\d+", prompt)
        archive = re.search(r"/exports/([0-9a-fA-F]{2,})(?:\.txt)?", prompt)
        if not (base and archive):
            return json.dumps({"action_type": "stop", "payload": {}})
        url = f"{base.group(0)}/exports/{archive.group(1)}.txt"
        return json.dumps(
            {
                "action_type": "http_request",
                "payload": {"method": "GET", "url": url},
            }
        )


class _DumbFakeLLM:
    """Fetches the advertised archive path literally; never infers the ``.txt`` sibling."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        link = re.search(r"http://127\.0\.0\.1:\d+/exports/[0-9a-fA-F]+", prompt)
        url = link.group(0) if link else "http://127.0.0.1:1/nope"
        return json.dumps(
            {
                "action_type": "http_request",
                "payload": {"method": "GET", "url": url},
            }
        )


def _fake_factory(model: str):
    return _SmartFakeLLM() if model == "smart" else _DumbFakeLLM()


async def _run_inferred_path_probe(_verification_callback=None, llm=None):
    """Lightweight matrix runner: consult the injected LLM, hit the real fixture.

    Mirrors what the dispatcher's LLM-exploration would do (the model proposes one
    HTTP action; we execute it and check for the flag) without the dispatcher's
    slow failure-escalation, so the matrix discrimination can be pinned fast.
    """
    from flaghunter.agents.pa_agent.ctf_dispatcher import SolveResult
    from flaghunter.agents.pa_agent.ctf_state import CTFState

    with benchmark_runner._fixture_server(llm_inferred_path_server) as server:
        base = server["base_url"]
        # The prompt mirrors the real first-turn context: base URL + the export
        # archive link recon surfaces into the ExplorationAgenda.
        prompt = (
            f"Target: {base}\n"
            f"Known links: ['{base}{ARCHIVE_PATH}']\n"
            f"ExplorationAgenda: [link_href] {base}{ARCHIVE_PATH}\n"
            "exports are served as .txt files\n"
        )
        action = json.loads(await llm.generate(prompt))
        url = str((action.get("payload") or {}).get("url") or "")
        body, status = "", 0
        if action.get("action_type") == "http_request" and url:
            def _fetch() -> tuple[str, int]:
                try:
                    with urllib.request.urlopen(url, timeout=3) as resp:
                        return resp.read().decode("utf-8", "replace"), resp.status
                except Exception:
                    return "", 404

            body, status = await asyncio.to_thread(_fetch)

        solved = status == 200 and FLAG_VALUE in body
        state = CTFState(target=base, goal="拿到flag")
        if solved:
            state.add_flag(
                FLAG_VALUE,
                level="verified",
                evidence_source="http-response",
                rationale="inferred export .txt path",
                confidence=1.0,
            )
            state.stop_reason = "flag verified"
            state.stop_report = {"reason": "flag_verified"}
        else:
            state.stop_reason = "no progress"
            state.stop_report = {"reason": "all_hypotheses_exhausted"}
        result = SolveResult(
            success=solved,
            flag=FLAG_VALUE if solved else None,
            chain_used=["web"] if solved else [],
            notes=[],
            reason="flag verified" if solved else "inferred path not constructed",
        )
        return result, state


@pytest.fixture
def _inferred_path_probe_catalog(monkeypatch):
    catalog = {
        "inferred_path_probe": benchmark_runner._ChallengeSpec(
            challenge_id="inferred_path_probe",
            expected_solved=False,
            source="tests/eval/llm_inferred_path_server.py::llm_inferred_path_server",
            runner=_run_inferred_path_probe,
        )
    }
    monkeypatch.setattr(benchmark_runner, "_CHALLENGE_CATALOG", catalog)
    return catalog


def test_llm_inferred_path_fixture_serves_flag_only_at_inferred_path():
    """The flag lives at the inferred ``.txt`` sibling, never at the advertised path."""
    with benchmark_runner._fixture_server(llm_inferred_path_server) as server:
        base = server["base_url"]

        def _get(path: str) -> tuple[int, str]:
            try:
                with urllib.request.urlopen(base + path, timeout=3) as resp:
                    return resp.status, resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
                return exc.code, ""

        root_status, root_body = _get("/")
        assert root_status == 200
        assert ARCHIVE_PATH in root_body  # the archive link is advertised

        assert _get(ARCHIVE_PATH)[0] == 404  # advertised path does NOT serve the flag

        flag_status, flag_body = _get(FLAG_PATH)
        assert flag_status == 200
        assert FLAG_VALUE in flag_body


@pytest.mark.asyncio
async def test_model_matrix_discriminates_smart_vs_dumb(_inferred_path_probe_catalog):
    """Smart model infers the export URL and solves; dumb fetches the literal path and fails.

    Exercises the real ``run_model_matrix`` -> ``run_benchmark(llm=...)`` wiring and
    the real fixture server; the only difference between columns is the injected
    FakeLLM, so a 1.0 vs 0.0 split proves the matrix discriminates.
    """
    report = await run_model_matrix(
        ["smart", "dumb"],
        challenges=["inferred_path_probe"],
        llm_factory=_fake_factory,
        write_report=False,
    )

    assert report.challenge_ids == ["inferred_path_probe"]
    assert report.models == ["smart", "dumb"]

    by_model = {row["model"]: row for row in report.comparison}
    assert by_model["smart"]["solve_rate"] == 1.0
    assert by_model["smart"]["solved_ids"] == ["inferred_path_probe"]
    assert by_model["dumb"]["solve_rate"] == 0.0
    assert by_model["dumb"]["solved_ids"] == []

    smart_results = report.per_model["smart"]["results"]
    assert any(item.get("flag") == FLAG_VALUE for item in smart_results)


def test_model_matrix_report_serializes_and_renders_table(tmp_path: Path):
    report = ModelMatrixReport(
        timestamp="2026-06-27T00:00:00+00:00",
        git_sha="deadbeef",
        challenge_ids=["llm_inferred_path"],
        models=["smart", "dumb"],
        per_model={"smart": {"solve_rate": 1.0}, "dumb": {"solve_rate": 0.0}},
        comparison=[
            {
                "model": "smart",
                "solved": 1,
                "total": 1,
                "solve_rate": 1.0,
                "wrong_flag_rate": 0.0,
                "avg_chains_to_solve": 1.0,
                "premature_stop_rate": 0.0,
                "avg_wall_time_seconds": 0.5,
                "solved_ids": ["llm_inferred_path"],
            },
            {
                "model": "dumb",
                "solved": 0,
                "total": 1,
                "solve_rate": 0.0,
                "wrong_flag_rate": 0.0,
                "avg_chains_to_solve": 0.0,
                "premature_stop_rate": 1.0,
                "avg_wall_time_seconds": 0.4,
                "solved_ids": [],
            },
        ],
    )

    payload = json.loads(report.to_json())
    assert payload["models"] == ["smart", "dumb"]
    assert payload["challenge_ids"] == ["llm_inferred_path"]
    assert payload["comparison"][0]["model"] == "smart"
    assert payload["comparison"][1]["solve_rate"] == 0.0

    output_path = report.write_json(tmp_path / "nested" / "matrix.json")
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))["git_sha"] == "deadbeef"

    table = report.to_table()
    lines = table.splitlines()
    assert lines[0].split()[0] == "model"
    assert "solve_rate" in lines[0]
    # header + separator + one row per model
    assert len(lines) == 4
    assert "smart" in table and "dumb" in table


@pytest.mark.asyncio
async def test_run_benchmark_forwards_llm_only_to_declaring_runners(monkeypatch):
    """``run_benchmark`` injects ``llm`` only into runners that declare it.

    Pins the inspect-based threading so legacy runners taking just the
    verification callback keep working unchanged when a matrix injects an LLM.
    """
    seen: dict[str, object] = {}

    def _synthetic_solved():
        from flaghunter.agents.pa_agent.ctf_dispatcher import SolveResult
        from flaghunter.agents.pa_agent.ctf_state import CTFState

        state = CTFState(target="http://ctf.local", goal="拿到flag")
        state.add_flag(
            "flag{synthetic}",
            level="verified",
            evidence_source="http-response",
            rationale="synthetic",
            confidence=1.0,
        )
        state.stop_reason = "synthetic success"
        state.stop_report = {"reason": "flag_verified"}
        return (
            SolveResult(success=True, flag="flag{synthetic}", chain_used=["web"], reason="ok"),
            state,
        )

    async def _runner_no_llm(_verification_callback=None):
        seen["no_llm_called"] = True
        return _synthetic_solved()

    async def _runner_with_llm(_verification_callback=None, llm=None):
        seen["with_llm_value"] = llm
        return _synthetic_solved()

    fake_catalog = {
        "no_llm": benchmark_runner._ChallengeSpec(
            challenge_id="no_llm",
            expected_solved=True,
            source="test",
            runner=_runner_no_llm,
        ),
        "with_llm": benchmark_runner._ChallengeSpec(
            challenge_id="with_llm",
            expected_solved=True,
            source="test",
            runner=_runner_with_llm,
        ),
    }
    monkeypatch.setattr(benchmark_runner, "_CHALLENGE_CATALOG", fake_catalog)

    sentinel = object()
    report = await benchmark_runner.run_benchmark(
        challenges=["no_llm", "with_llm"],
        llm=sentinel,
        write_report=False,
    )

    assert report.total_challenges == 2
    assert seen["no_llm_called"] is True
    assert seen["with_llm_value"] is sentinel
