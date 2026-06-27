"""Model cross-evaluation (模型横评) harness.

Closes the long-standing "模型效果无实测" debt. ``benchmark_runner`` measures the
*deterministic* dispatcher (``llm=None``); this layer injects a real
``LLM(model=...)`` per model over the LLM-sensitive challenge subset and
aggregates a side-by-side comparison (solve rate / wrong-flag rate /
chains-to-solve / wall-time), so two models can be compared on the same suite.

Opt-in and offline: a live run needs provider API keys and makes real model
calls, so this is NOT a CI test. The wiring (model loop, per-model aggregation,
comparison table) is pinned deterministically by ``tests/eval/test_model_matrix.py``
using a FakeLLM factory — no network — including a smart-vs-dumb model pair that
proves the matrix actually *discriminates* on the ``llm_inferred_path`` challenge.

    python -m tests.eval.model_matrix --models claude-opus-4-8 gpt-4o
    python -m tests.eval.model_matrix --models <m1> <m2> --challenges llm_inferred_path
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Callable

from tests.eval.benchmark_result import BenchmarkReport
from tests.eval.benchmark_runner import (
    _compact_timestamp,
    _git_sha,
    _iso_timestamp,
    run_benchmark,
)

# Model effectiveness only shows on challenges that actually reach the LLM —
# deterministic strategies solve the rest before a model is ever consulted.
_MODEL_MATRIX_DEFAULT_CHALLENGE_IDS = ["llm_unknown_web", "llm_inferred_path"]

LLMFactory = Callable[[str], Any]


def default_llm_factory(model: str) -> Any:
    """Construct a live ``LLM`` for ``model`` (lazy import; needs API keys)."""
    from flaghunter.llm.llm import LLM

    return LLM(model=model)


def _comparison_row(model: str, report: BenchmarkReport) -> dict[str, Any]:
    wall_times = [item.wall_time_seconds for item in report.results]
    avg_wall = round(sum(wall_times) / len(wall_times), 4) if wall_times else 0.0
    return {
        "model": model,
        "solved": report.solved_challenges,
        "total": report.total_challenges,
        "solve_rate": report.solve_rate,
        "wrong_flag_rate": report.wrong_flag_rate,
        "avg_chains_to_solve": report.avg_chains_to_solve,
        "premature_stop_rate": report.premature_stop_rate,
        "avg_wall_time_seconds": avg_wall,
        "solved_ids": [item.challenge_id for item in report.results if item.solved],
    }


@dataclass(slots=True)
class ModelMatrixReport:
    timestamp: str
    git_sha: str
    challenge_ids: list[str]
    models: list[str]
    per_model: dict[str, dict[str, Any]] = field(default_factory=dict)
    comparison: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def write_json(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.to_json(), encoding="utf-8")
        return output_path

    def to_table(self) -> str:
        headers = ["model", "solved", "solve_rate", "wrong_flag_rate", "avg_chains", "avg_wall_s"]
        rows = [
            [
                str(row["model"]),
                f"{row['solved']}/{row['total']}",
                f"{row['solve_rate']:.2f}",
                f"{row['wrong_flag_rate']:.2f}",
                f"{row['avg_chains_to_solve']:.2f}",
                f"{row['avg_wall_time_seconds']:.2f}",
            ]
            for row in self.comparison
        ]
        widths = [
            max(len(headers[col]), *(len(r[col]) for r in rows)) if rows else len(headers[col])
            for col in range(len(headers))
        ]
        fmt = "  ".join(f"{{:<{width}}}" for width in widths)
        lines = [fmt.format(*headers), fmt.format(*("-" * width for width in widths))]
        lines.extend(fmt.format(*row) for row in rows)
        return "\n".join(lines)


def _default_report_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "reports" / "model_matrix" / f"model_matrix_{_compact_timestamp()}.json"


async def run_model_matrix(
    models: list[str],
    challenges: list[str] | None = None,
    llm_factory: LLMFactory | None = None,
    verification_callback: Callable[[str], Any] | None = None,
    report_path: str | None = None,
    write_report: bool = True,
) -> ModelMatrixReport:
    """Run the benchmark suite once per model and aggregate a comparison.

    Each model gets a fresh ``llm_factory(model)`` injected into the dispatcher
    via ``run_benchmark(llm=...)``; per-model reports are not written to disk
    (only the combined matrix report is, when ``write_report``).
    """
    factory = llm_factory or default_llm_factory
    selected = list(challenges) if challenges else list(_MODEL_MATRIX_DEFAULT_CHALLENGE_IDS)
    report = ModelMatrixReport(
        timestamp=_iso_timestamp(),
        git_sha=_git_sha(),
        challenge_ids=selected,
        models=list(models),
    )

    for model in models:
        llm = factory(model)
        bench = await run_benchmark(
            challenges=selected,
            verification_callback=verification_callback,
            llm=llm,
            write_report=False,
        )
        report.per_model[model] = bench.to_dict()
        report.comparison.append(_comparison_row(model, bench))

    if write_report:
        destination = Path(report_path) if report_path else _default_report_path()
        report.write_json(destination)
    return report


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the model cross-evaluation (模型横评) matrix over LLM-sensitive challenges."
    )
    parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        help="LiteLLM model names to compare (e.g. claude-opus-4-8 gpt-4o).",
    )
    parser.add_argument(
        "--challenges",
        nargs="*",
        default=None,
        help=f"Challenge subset. Defaults to {_MODEL_MATRIX_DEFAULT_CHALLENGE_IDS}.",
    )
    parser.add_argument(
        "--report",
        dest="report_path",
        default=None,
        help="Output JSON path. Defaults to reports/model_matrix/model_matrix_<timestamp>.json",
    )
    return parser


async def _async_main(argv: list[str] | None = None) -> int:
    parser = _build_cli()
    args = parser.parse_args(argv)
    report = await run_model_matrix(
        models=args.models,
        challenges=args.challenges,
        report_path=args.report_path,
    )
    print(report.to_table())
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
