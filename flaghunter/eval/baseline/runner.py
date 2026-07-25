"""Subprocess driver for the solve-rate baseline.

Each challenge is driven as an **isolated** ``flaghunter run`` subprocess. Running
out-of-process (rather than calling ``run_cli`` inline) buys three things the
inline path can't: a clean OS-level memory/state reset per challenge, per-run env
overrides (isolated strategy memory), and immunity to the heavy internal-API
churn — the harness only touches the stable CLI surface.

Cost guards are mandatory here: a 30-challenge sweep with no ``timeout`` /
``--max-loops`` / token ceiling can burn hours and a lot of tokens on a single
stuck challenge. Every run is bounded on all three axes.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .corpus import Challenge
from .judge import Verdict, judge_run

# Default invocation: same-venv Python, module entry (flaghunter/__main__.py).
_DEFAULT_BASE_CMD = [sys.executable, "-m", "flaghunter"]


@dataclass
class ScorecardRow:
    challenge_id: str
    tier: str
    type: str
    verdict: str
    expected_verdict: str
    matched_expectation: bool
    memory_mode: str  # cold | warm
    flag_found: str | None = None
    steps: int | None = None
    max_loops: int | None = None
    wall_time_s: float | None = None
    tokens: int | None = None
    tools_used: list[str] = field(default_factory=list)
    diseases: list[str] = field(default_factory=list)
    target: str = ""
    returncode: int | None = None
    timed_out: bool = False
    error: str = ""
    detail: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _skipped_row(challenge: Challenge, memory_mode: str, reason: str) -> ScorecardRow:
    return ScorecardRow(
        challenge_id=challenge.id,
        tier=challenge.tier.value,
        type=challenge.type,
        verdict=Verdict.SKIPPED.value,
        expected_verdict=challenge.expected_verdict,
        matched_expectation=False,
        memory_mode=memory_mode,
        max_loops=challenge.max_loops,
        error=reason,
    )


def _build_command(
    base_cmd: list[str],
    challenge: Challenge,
    target: str,
    *,
    ssh: bool,
    docker: bool,
    report_path: Path,
) -> list[str]:
    cmd = [
        *base_cmd,
        "run",
        "-t",
        target,
        challenge.task,
        "--mode",
        "ctf",
        "--ctf-type",
        challenge.ctf_type or challenge.type,
        "--max-loops",
        str(challenge.max_loops),
        "--report",
        str(report_path),
    ]
    if ssh:
        cmd.append("--ssh")
    if docker:
        cmd.append("--docker")
    return cmd


def _synthetic_stdout(challenge: Challenge) -> str:
    """Deterministic fake output for --dry-run, shaped by the tier's expectation.

    Lets the harness plumbing + judge + report be exercised offline (no network,
    no LLM, no tools). Rows are stamped so a dry run is never mistaken for real.
    """
    header = f"5/{challenge.max_loops} tokens: 1234\ntool: recon\ntool: sqli\n"
    if challenge.expected_verdict == "solved":
        return header + "Flag captured: CTF2{dry-run-synthetic}\n"
    if challenge.expected_verdict == "near":
        return header + "candidate flag found but unverified (near-solve)\n"
    return header + "repertoire_miss: no chain reaches this vector\n"


def run_one(
    challenge: Challenge,
    target: str | None,
    *,
    memory_mode: str = "cold",
    base_cmd: list[str] | None = None,
    ssh: bool = False,
    docker: bool = False,
    dry_run: bool = False,
    warm_memory_path: Path | None = None,
    runs_dir: Path | None = None,
) -> ScorecardRow:
    """Drive one challenge and score it. Returns a SKIPPED row if no target."""
    if not target:
        return _skipped_row(challenge, memory_mode, "no target resolved (supply --targets)")

    base_cmd = base_cmd or _DEFAULT_BASE_CMD
    runs_dir = runs_dir or Path(tempfile.mkdtemp(prefix="fh_baseline_"))
    runs_dir.mkdir(parents=True, exist_ok=True)
    report_path = runs_dir / f"{challenge.id}_{memory_mode}.md"
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    if dry_run:
        res = judge_run(challenge, stdout=_synthetic_stdout(challenge), returncode=0)
        row = _row_from_judge(challenge, target, memory_mode, res, stamp)
        row.error = "dry-run (synthetic outcome)"
        row.wall_time_s = 0.0
        return row

    # --- env isolation: cold → fresh per-challenge memory; warm → shared store.
    env = dict(os.environ)
    strategy_dir = tempfile.mkdtemp(prefix=f"fh_mem_{challenge.id}_")
    if memory_mode == "warm" and warm_memory_path is not None:
        env["FLAGHUNTER_STRATEGY_MEMORY_PATH"] = str(warm_memory_path)
    else:
        env["FLAGHUNTER_STRATEGY_MEMORY_PATH"] = str(Path(strategy_dir) / "strategy_memory.json")

    cmd = _build_command(
        base_cmd, challenge, target, ssh=ssh, docker=docker, report_path=report_path
    )

    started = time.time()
    timed_out = False
    returncode: int | None = None
    stdout = ""
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=challenge.timeout_s,
            encoding="utf-8",
            errors="replace",
        )
        stdout = (proc.stdout or "") + "\n" + (proc.stderr or "")
        returncode = proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
    except Exception as exc:  # noqa: BLE001 — record, never crash the sweep
        elapsed = time.time() - started
        return ScorecardRow(
            challenge_id=challenge.id,
            tier=challenge.tier.value,
            type=challenge.type,
            verdict=Verdict.ERROR.value,
            expected_verdict=challenge.expected_verdict,
            matched_expectation=False,
            memory_mode=memory_mode,
            target=target,
            wall_time_s=round(elapsed, 1),
            error=f"{type(exc).__name__}: {exc}",
            timestamp=stamp,
        )

    elapsed = time.time() - started
    report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else ""
    res = judge_run(
        challenge,
        stdout=stdout,
        report_text=report_text,
        returncode=returncode or 0,
        timed_out=timed_out,
    )
    row = _row_from_judge(challenge, target, memory_mode, res, stamp)
    row.wall_time_s = round(elapsed, 1)
    row.returncode = returncode
    row.timed_out = timed_out
    return row


def _row_from_judge(challenge, target, memory_mode, res, stamp) -> ScorecardRow:
    return ScorecardRow(
        challenge_id=challenge.id,
        tier=challenge.tier.value,
        type=challenge.type,
        verdict=res.verdict.value,
        expected_verdict=challenge.expected_verdict,
        matched_expectation=res.matched_expectation,
        memory_mode=memory_mode,
        flag_found=res.flag_found,
        steps=res.steps,
        max_loops=res.max_loops,
        tokens=res.tokens,
        tools_used=res.tools_used,
        diseases=res.diseases,
        target=target,
        detail=res.detail,
        timestamp=stamp,
    )


def run_baseline(
    challenges: list[Challenge],
    targets: dict[str, str] | None = None,
    *,
    memory_mode: str = "cold",
    base_cmd: list[str] | None = None,
    ssh: bool = False,
    docker: bool = False,
    dry_run: bool = False,
    runs_dir: Path | None = None,
    on_row=None,
) -> list[ScorecardRow]:
    """Run the full corpus sequentially, one scorecard row per challenge.

    ``targets`` maps challenge id → live URL; ids without a target are SKIPPED
    (never silently passed). In ``warm`` mode all challenges share one strategy
    memory store so the sweep measures memory accumulation across the batch;
    ``cold`` gives each challenge a fresh store.
    """
    targets = targets or {}
    runs_dir = runs_dir or Path(tempfile.mkdtemp(prefix="fh_baseline_"))
    warm_memory_path = runs_dir / "warm_strategy_memory.json" if memory_mode == "warm" else None

    rows: list[ScorecardRow] = []
    for challenge in challenges:
        row = run_one(
            challenge,
            targets.get(challenge.id) or ("dry-run-target" if dry_run else None),
            memory_mode=memory_mode,
            base_cmd=base_cmd,
            ssh=ssh,
            docker=docker,
            dry_run=dry_run,
            warm_memory_path=warm_memory_path,
            runs_dir=runs_dir,
        )
        rows.append(row)
        if on_row is not None:
            on_row(row)
    return rows
