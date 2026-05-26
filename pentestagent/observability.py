"""Unified observability metrics for PentestAgent.

Per-turn and per-session metrics collection with JSON export.
Tracks tool calls, token usage, wall time, findings, flags, and errors.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TurnMetrics:
    iteration: int
    tool_calls: list[str] = field(default_factory=list)
    tool_durations_ms: list[float] = field(default_factory=list)
    tool_success: list[bool] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    wall_time_ms: float = 0.0
    findings_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "tool_calls": self.tool_calls,
            "tool_durations_ms": self.tool_durations_ms,
            "tool_success": self.tool_success,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "wall_time_ms": self.wall_time_ms,
            "findings_count": self.findings_count,
        }


@dataclass
class SessionMetrics:
    session_id: str
    total_turns: int = 0
    total_tool_calls: int = 0
    total_tokens: int = 0
    total_wall_time_ms: float = 0.0
    findings_count: int = 0
    flags_found: int = 0
    errors_count: int = 0
    turns: list[TurnMetrics] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "total_turns": self.total_turns,
            "total_tool_calls": self.total_tool_calls,
            "total_tokens": self.total_tokens,
            "total_wall_time_ms": self.total_wall_time_ms,
            "findings_count": self.findings_count,
            "flags_found": self.flags_found,
            "errors_count": self.errors_count,
            "efficiency_ratio": (
                self.findings_count / max(self.total_turns, 1)
            ),
            "avg_tool_duration_ms": (
                sum(
                    sum(t.tool_durations_ms) / max(len(t.tool_durations_ms), 1)
                    for t in self.turns
                )
                / max(self.total_turns, 1)
            ),
            "turns": [t.to_dict() for t in self.turns],
        }


_DEFAULT_METRICS_DIR = Path("loot") / "metrics"


class MetricsCollector:
    """Per-session metrics aggregator with JSON export."""

    def __init__(self, base_path: Path | None = None):
        self._base = Path(base_path) if base_path else _DEFAULT_METRICS_DIR
        self._session: SessionMetrics | None = None
        self._turn_start: float = 0.0

    def start_session(self, session_id: str = "") -> str:
        """Begin a new metrics session. Returns session_id."""
        import uuid
        sid = session_id or uuid.uuid4().hex[:12]
        self._session = SessionMetrics(
            session_id=sid,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        return sid

    def start_turn(self) -> None:
        """Mark the start of a turn (for wall-time tracking)."""
        self._turn_start = time.monotonic()

    def record_turn(self, metrics: TurnMetrics) -> None:
        """Record metrics for a completed turn."""
        if self._session is None:
            return
        self._session.turns.append(metrics)
        self._session.total_turns += 1
        self._session.total_tool_calls += len(metrics.tool_calls)
        self._session.total_tokens += metrics.input_tokens + metrics.output_tokens
        self._session.total_wall_time_ms += metrics.wall_time_ms
        self._session.findings_count += metrics.findings_count
        self._session.errors_count += sum(
            1 for ok in metrics.tool_success if not ok
        )

    def record_flag(self) -> None:
        if self._session:
            self._session.flags_found += 1

    def record_finding(self) -> None:
        if self._session:
            self._session.findings_count += 1

    def record_error(self) -> None:
        if self._session:
            self._session.errors_count += 1

    def get_summary(self) -> SessionMetrics | None:
        return self._session

    def export_json(self, path: Path | None = None) -> Path | None:
        """Export current session metrics to a JSON file."""
        if self._session is None:
            return None
        self._session.ended_at = datetime.now(timezone.utc).isoformat()

        out_path = path or (self._base / f"metrics_{self._session.session_id}.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(self._session.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return out_path
