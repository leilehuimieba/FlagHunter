"""Unified observability metrics for FlagHunter.

Per-turn and per-session metrics collection with JSON export.
Tracks tool calls, token usage, wall time, findings, flags, and errors.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator


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


class SpanScope(str, Enum):
    """Known span kinds for hierarchical metrics attribution."""

    ENTRY = "entry"
    STEP = "step"
    CHAIN = "chain"
    SKILL = "skill"


@dataclass
class Span:
    """A hierarchical unit of work with direct token and timing metrics."""

    span_id: str
    name: str
    kind: str
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    started_at: float = 0.0
    ended_at: float | None = None
    child_ids: list[str] = field(default_factory=list)

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Add direct token usage to this span."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    @property
    def duration_ms(self) -> float:
        if self.ended_at is None:
            return 0.0
        return round((self.ended_at - self.started_at) * 1000, 3)

    @property
    def tokens(self) -> dict[str, int]:
        return {
            "input": self.input_tokens,
            "output": self.output_tokens,
            "total": self.input_tokens + self.output_tokens,
        }

    def to_dict(
        self,
        children: list[dict[str, Any]],
        token_rollup: dict[str, int],
    ) -> dict[str, Any]:
        return {
            "id": self.span_id,
            "name": self.name,
            "kind": self.kind,
            "parent_id": self.parent_id,
            "metadata": dict(self.metadata),
            "duration_ms": self.duration_ms,
            "tokens": self.tokens,
            "token_rollup": token_rollup,
            "children": children,
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
        self._span_counter: int = 0
        self._spans: dict[str, Span] = {}
        self._root_span_ids: list[str] = []
        self._span_stack: list[str] = []

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

    def start_span(
        self,
        name: str,
        kind: SpanScope | str,
        *,
        parent_id: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> Span:
        """Start a hierarchical metrics span and make it the active parent."""
        resolved_parent_id = parent_id
        if resolved_parent_id is None and self._span_stack:
            resolved_parent_id = self._span_stack[-1]

        span = Span(
            span_id=self._next_span_id(),
            name=name,
            kind=self._scope_value(kind),
            parent_id=resolved_parent_id,
            metadata=dict(metadata or {}),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            started_at=time.monotonic(),
        )
        self._spans[span.span_id] = span

        if resolved_parent_id and resolved_parent_id in self._spans:
            self._spans[resolved_parent_id].child_ids.append(span.span_id)
        else:
            self._root_span_ids.append(span.span_id)

        self._span_stack.append(span.span_id)
        return span

    def end_span(
        self,
        span: Span | str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> Span | None:
        """End a span by object or ID and add any final direct token usage."""
        span_id = span.span_id if isinstance(span, Span) else span
        target = self._spans.get(span_id)
        if target is None:
            return None

        if input_tokens or output_tokens:
            target.add_tokens(input_tokens=input_tokens, output_tokens=output_tokens)
        target.ended_at = time.monotonic()

        if span_id in self._span_stack:
            idx = len(self._span_stack) - 1 - self._span_stack[::-1].index(span_id)
            del self._span_stack[idx:]

        return target

    @contextmanager
    def span(
        self,
        name: str,
        kind: SpanScope | str,
        *,
        parent_id: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Span]:
        """Context manager wrapper around start_span/end_span."""
        active_span = self.start_span(
            name,
            kind,
            parent_id=parent_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            metadata=metadata,
        )
        try:
            yield active_span
        finally:
            self.end_span(active_span)

    def export_spans(self) -> list[dict[str, Any]]:
        """Return completed and active spans as a structured tree."""
        return [self._export_span(span_id) for span_id in self._root_span_ids]

    def get_span_attribution(
        self, kind: SpanScope | str
    ) -> dict[str, dict[str, Any]]:
        """Summarize span duration and rolled-up tokens by kind attribution key."""
        target_kind = self._scope_value(kind)
        attribution: dict[str, dict[str, Any]] = {}

        for span in self._spans.values():
            if span.kind != target_kind:
                continue
            key = (
                span.metadata.get(target_kind)
                or span.metadata.get("name")
                or span.name
            )
            key = str(key)
            rollup = self._token_rollup(span.span_id)
            entry = attribution.setdefault(
                key,
                {
                    "count": 0,
                    "duration_ms": 0.0,
                    "tokens": {"input": 0, "output": 0, "total": 0},
                },
            )
            entry["count"] += 1
            entry["duration_ms"] = round(
                entry["duration_ms"] + span.duration_ms,
                3,
            )
            entry["tokens"]["input"] += rollup["input"]
            entry["tokens"]["output"] += rollup["output"]
            entry["tokens"]["total"] += rollup["total"]

        return attribution

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

    def _next_span_id(self) -> str:
        self._span_counter += 1
        return f"span-{self._span_counter}"

    def _scope_value(self, kind: SpanScope | str) -> str:
        if isinstance(kind, SpanScope):
            return kind.value
        return str(kind)

    def _token_rollup(self, span_id: str) -> dict[str, int]:
        span = self._spans[span_id]
        tokens = dict(span.tokens)
        for child_id in span.child_ids:
            child_tokens = self._token_rollup(child_id)
            tokens["input"] += child_tokens["input"]
            tokens["output"] += child_tokens["output"]
            tokens["total"] += child_tokens["total"]
        return tokens

    def _export_span(self, span_id: str) -> dict[str, Any]:
        span = self._spans[span_id]
        children = [self._export_span(child_id) for child_id in span.child_ids]
        return span.to_dict(children, self._token_rollup(span_id))
