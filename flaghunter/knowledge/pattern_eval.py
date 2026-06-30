"""Golden eval for attack-pattern retrieval — byte-level regression guard (⑤).

Runs the fingerprint queries in ``attack_patterns/eval/pattern-queries.jsonl``
through :class:`PatternIndex` and reports hit@k / MRR plus per-query rank. Every
time a pattern is added or an alias edited, run this to confirm the known
fingerprints still recall their expected ``kind`` within ``max_rank`` and the
ranking didn't regress (mirror of the reference KB's ``eval-search.py``).

Deterministic end-to-end — same patterns + same queries → same metrics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .pattern_retrieval import PatternIndex

_DEFAULT_EVAL_FILE = (
    Path(__file__).resolve().parent / "attack_patterns" / "eval" / "pattern-queries.jsonl"
)


@dataclass(frozen=True)
class QueryOutcome:
    query: str
    expected_kind: str
    max_rank: int
    rank: int | None  # 1-based rank of expected_kind, or None if not recalled
    hit: bool


@dataclass(frozen=True)
class EvalReport:
    outcomes: tuple[QueryOutcome, ...]

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def hits(self) -> int:
        return sum(1 for o in self.outcomes if o.hit)

    @property
    def hit_rate(self) -> float:
        return (self.hits / self.total) if self.total else 0.0

    @property
    def mrr(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum((1.0 / o.rank) if o.rank else 0.0 for o in self.outcomes) / self.total

    @property
    def failures(self) -> list[QueryOutcome]:
        return [o for o in self.outcomes if not o.hit]


def load_eval_queries(path: str | Path | None = None) -> list[dict[str, Any]]:
    eval_path = Path(path) if path is not None else _DEFAULT_EVAL_FILE
    rows: list[dict[str, Any]] = []
    if not eval_path.exists():
        return rows
    for line in eval_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("query") and obj.get("expected_kind"):
            rows.append(obj)
    return rows


def run_eval(
    *,
    index: PatternIndex | None = None,
    eval_path: str | Path | None = None,
    top_k: int = 8,
) -> EvalReport:
    idx = index if index is not None else PatternIndex.from_dir()
    outcomes: list[QueryOutcome] = []
    for row in load_eval_queries(eval_path):
        query = str(row["query"])
        expected = str(row["expected_kind"])
        max_rank = int(row.get("max_rank", top_k) or top_k)
        results = idx.retrieve(query, top_k=max(top_k, max_rank))
        kinds = [r.kind for r in results]
        rank = (kinds.index(expected) + 1) if expected in kinds else None
        hit = rank is not None and rank <= max_rank
        outcomes.append(
            QueryOutcome(
                query=query,
                expected_kind=expected,
                max_rank=max_rank,
                rank=rank,
                hit=hit,
            )
        )
    return EvalReport(outcomes=tuple(outcomes))


__all__ = ["EvalReport", "QueryOutcome", "load_eval_queries", "run_eval"]
