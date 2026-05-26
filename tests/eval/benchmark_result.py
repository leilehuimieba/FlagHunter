"""Serializable result objects for Phase 6 replay benchmark reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ChallengeResult:
    challenge_id: str
    solved: bool
    expected_solved: bool
    wrong_flag_count: int
    flag_submit_attempts: int
    chain_iterations: int
    stop_reason: str
    stop_reason_class: str
    has_source_only_stop: bool
    hypothesis_exhausted_count: int
    hypothesis_total_count: int
    wall_time_seconds: float
    candidate_flag_count: int = 0
    runtime_flag_count: int = 0
    verified_flag_count: int = 0
    rejected_flag_count: int = 0
    first_chain_solve: bool = False
    recovered_after_wrong_flag: bool = False
    notes_count: int = 0
    flag: str | None = None
    chain_used: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Phase 7: NYU CTF Bench failure taxonomy
    # Values: "give_up" | "round_exceeded" | "connection_failure" | "token_exceeded" | "wrong_answer" | None
    failure_taxonomy: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BenchmarkReport:
    run_id: str
    timestamp: str
    git_sha: str
    results: list[ChallengeResult]
    solve_rate: float
    wrong_flag_rate: float
    premature_stop_rate: float
    avg_chains_to_solve: float
    hypothesis_exhaustion_rate: float
    source_only_false_stop: int = 0
    hypothesis_first_hit_rate: float = 0.0
    recovery_after_wrong_rate: float = 0.0
    no_progress_stop_rate: float = 0.0
    total_challenges: int = 0
    solved_challenges: int = 0
    total_flag_submit_attempts: int = 0
    wrong_flag_submissions: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    # Phase 7: NYU CTF Bench failure taxonomy distribution
    failure_distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["results"] = [result.to_dict() for result in self.results]
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def write_json(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.to_json(), encoding="utf-8")
        return output_path

