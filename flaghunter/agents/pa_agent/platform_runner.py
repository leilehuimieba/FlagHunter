"""Platform-level autonomous runner for multi-challenge /ctf execution."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class PlatformRunConfig:
    mode: str = "switch"
    max_challenges: int = 4
    timebox_seconds: int = 900
    max_consecutive_stops: int = 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "PlatformRunConfig":
        raw = dict(payload or {})
        mode = str(raw.get("mode") or "switch").strip().lower() or "switch"
        if mode not in {"single", "switch", "drain"}:
            mode = "switch"
        return cls(
            mode=mode,
            max_challenges=max(1, _safe_int(raw.get("max_challenges"), default=4)),
            timebox_seconds=max(1, _safe_int(raw.get("timebox_seconds"), default=900)),
            max_consecutive_stops=max(
                1, _safe_int(raw.get("max_consecutive_stops"), default=2)
            ),
        )


@dataclass(slots=True)
class PlatformRunRecord:
    challenge_id: str
    challenge_name: str
    url: str
    outcome: str
    reason: str
    success: bool
    started_at: float
    ended_at: float
    chain_used: list[str] = field(default_factory=list)
    missing_tools: list[str] = field(default_factory=list)
    blocked_reason: str = ""
    skip_reason: str = ""
    stop_reason_class: str = ""
    failure_taxonomy: str = ""
    visit_key: str = ""
    switch_reason: str = ""
    switch_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "PlatformRunRecord":
        raw = dict(payload or {})
        return cls(
            challenge_id=str(raw.get("challenge_id") or "").strip(),
            challenge_name=str(raw.get("challenge_name") or "").strip(),
            url=str(raw.get("url") or "").strip(),
            outcome=str(raw.get("outcome") or "").strip(),
            reason=str(raw.get("reason") or "").strip(),
            success=bool(raw.get("success")),
            started_at=_safe_float(raw.get("started_at"), default=0.0),
            ended_at=_safe_float(raw.get("ended_at"), default=0.0),
            chain_used=list(raw.get("chain_used") or []),
            missing_tools=list(raw.get("missing_tools") or []),
            blocked_reason=str(raw.get("blocked_reason") or "").strip(),
            skip_reason=str(raw.get("skip_reason") or "").strip(),
            stop_reason_class=str(raw.get("stop_reason_class") or "").strip(),
            failure_taxonomy=str(raw.get("failure_taxonomy") or "").strip(),
            visit_key=str(raw.get("visit_key") or "").strip(),
            switch_reason=str(raw.get("switch_reason") or "").strip(),
            switch_source=str(raw.get("switch_source") or "").strip(),
        )


@dataclass(slots=True)
class PlatformRunState:
    config: PlatformRunConfig
    started_at: float
    visited_keys: set[str] = field(default_factory=set)
    records: list[PlatformRunRecord] = field(default_factory=list)
    consecutive_stops: int = 0
    switched_count: int = 0
    switch_events: list[dict[str, Any]] = field(default_factory=list)
    last_switch_reason: str = ""
    last_switch_source: str = ""
    resume_count: int = 0
    resumed_from_record_count: int = 0
    resume_reason: str = ""
    last_resumed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "started_at": self.started_at,
            "visited_keys": sorted(self.visited_keys),
            "records": [record.to_dict() for record in self.records],
            "consecutive_stops": self.consecutive_stops,
            "switched_count": self.switched_count,
            "switch_events": list(self.switch_events),
            "last_switch_reason": self.last_switch_reason,
            "last_switch_source": self.last_switch_source,
            "resume_count": self.resume_count,
            "resumed_from_record_count": self.resumed_from_record_count,
            "resume_reason": self.resume_reason,
            "last_resumed_at": self.last_resumed_at,
            "solved_count": sum(1 for record in self.records if record.outcome == "solved"),
            "blocked_count": sum(
                1 for record in self.records if record.outcome in {"blocked", "stopped"}
            ),
            "skipped_count": sum(1 for record in self.records if record.outcome == "skipped"),
            "blocked_reasons": [
                record.blocked_reason
                for record in self.records
                if record.blocked_reason
            ],
            "skip_reasons": [
                record.skip_reason
                for record in self.records
                if record.skip_reason
            ],
        }

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any] | None,
        *,
        fallback_config: PlatformRunConfig | None = None,
    ) -> "PlatformRunState":
        raw = dict(payload or {})
        config = fallback_config or PlatformRunConfig.from_dict(raw.get("config"))
        records = [
            PlatformRunRecord.from_dict(item)
            for item in list(raw.get("records") or [])
            if isinstance(item, dict)
        ]
        return cls(
            config=config,
            started_at=_safe_float(raw.get("started_at"), default=time.time()),
            visited_keys={
                str(item).strip() for item in list(raw.get("visited_keys") or []) if str(item).strip()
            },
            records=records,
            consecutive_stops=max(0, _safe_int(raw.get("consecutive_stops"), default=0)),
            switched_count=max(0, _safe_int(raw.get("switched_count"), default=0)),
            switch_events=[
                dict(item)
                for item in list(raw.get("switch_events") or [])
                if isinstance(item, dict)
            ],
            last_switch_reason=str(raw.get("last_switch_reason") or "").strip(),
            last_switch_source=str(raw.get("last_switch_source") or "").strip(),
            resume_count=max(0, _safe_int(raw.get("resume_count"), default=0)),
            resumed_from_record_count=max(
                0, _safe_int(raw.get("resumed_from_record_count"), default=0)
            ),
            resume_reason=str(raw.get("resume_reason") or "").strip(),
            last_resumed_at=_safe_float(raw.get("last_resumed_at"), default=0.0),
        )


class PlatformAutonomyRunner:
    def start(self, config: PlatformRunConfig, *, initial_visit_key: str = "") -> PlatformRunState:
        state = PlatformRunState(config=config, started_at=time.time())
        if initial_visit_key:
            state.visited_keys.add(initial_visit_key)
        return state

    def restore(
        self,
        payload: dict[str, Any] | None,
        *,
        config: PlatformRunConfig | None = None,
        initial_visit_key: str = "",
        resume_reason: str = "",
    ) -> PlatformRunState:
        state = PlatformRunState.from_dict(payload, fallback_config=config)
        if config is not None:
            state.config = config
        if initial_visit_key:
            state.visited_keys.add(initial_visit_key)
        state.resumed_from_record_count = len(state.records)
        state.resume_count = max(0, int(state.resume_count)) + 1
        state.resume_reason = str(resume_reason or "resume").strip()
        state.last_resumed_at = time.time()
        return state

    def classify_result(self, *, result: Any, stop_reason: str) -> str:
        raw_reason = str(stop_reason or "").strip().lower()
        reason = raw_reason.replace("_", " ").replace("-", " ")
        if getattr(result, "success", False):
            return "solved"
        if "already solved" in reason:
            return "skipped"
        if "wrong flag feedback" in reason:
            return "blocked"
        if "capability_ceiling" in reason or "candidate_only" in reason:
            return "blocked"
        if "all_hypotheses_exhausted" in reason or "未命中 flag" in str(getattr(result, "reason", "") or ""):
            return "stopped"
        return "stopped"

    def classify_failure_taxonomy(self, *, result: Any, stop_reason: str, outcome: str) -> str:
        if getattr(result, "success", False):
            return ""
        normalized = str(stop_reason or getattr(result, "reason", "") or "").strip().lower()
        reason = normalized.replace("-", "_").replace(" ", "_")
        if "wrong_flag_feedback" in reason or "wrong_answer" in reason:
            return "wrong_answer"
        if any(token in reason for token in ("token_exceeded", "context_length", "context_window", "max_tokens")):
            return "token_exceeded"
        if any(token in reason for token in ("connection_failure", "connection_error", "network_error", "timeout", "timed_out", "dns", "refused")):
            return "connection_failure"
        if any(token in reason for token in ("round_exceeded", "budget_exhausted", "iteration_exhausted", "max_rounds")):
            return "round_exceeded"
        if outcome in {"blocked", "stopped"}:
            return "give_up"
        return ""

    def record_result(
        self,
        state: PlatformRunState,
        *,
        challenge_id: str,
        challenge_name: str,
        url: str,
        result: Any,
        stop_reason: str,
        started_at: float,
        ended_at: float | None = None,
    ) -> PlatformRunRecord:
        outcome = self.classify_result(result=result, stop_reason=stop_reason)
        failure_taxonomy = self.classify_failure_taxonomy(
            result=result,
            stop_reason=stop_reason,
            outcome=outcome,
        )
        record = PlatformRunRecord(
            challenge_id=str(challenge_id or ""),
            challenge_name=str(challenge_name or ""),
            url=str(url or ""),
            outcome=outcome,
            reason=str(stop_reason or ""),
            success=bool(getattr(result, "success", False)),
            started_at=float(started_at),
            ended_at=float(ended_at if ended_at is not None else time.time()),
            chain_used=list(getattr(result, "chain_used", []) or []),
            missing_tools=list(getattr(result, "missing_tools", []) or []),
            blocked_reason=str(stop_reason or "") if outcome == "blocked" else "",
            skip_reason=str(stop_reason or "") if outcome == "skipped" else "",
            stop_reason_class=outcome,
            failure_taxonomy=failure_taxonomy,
            visit_key=f"{str(challenge_id or '').strip()}|{str(url or '').strip()}",
            switch_reason=state.last_switch_reason if state.last_switch_reason else "",
            switch_source=state.last_switch_source if state.last_switch_source else "",
        )
        state.records.append(record)
        if outcome == "solved":
            state.consecutive_stops = 0
        elif outcome == "skipped":
            state.consecutive_stops = max(0, state.consecutive_stops)
        else:
            state.consecutive_stops += 1
        return record

    def should_continue(
        self,
        state: PlatformRunState,
        *,
        operator_stop: bool,
        queue_snapshot: dict[str, Any] | None,
    ) -> tuple[bool, str]:
        if operator_stop:
            return False, "operator_stop"
        config = state.config
        if config.mode == "single":
            return False, "single_mode"
        if len(state.records) >= max(1, int(config.max_challenges)):
            return False, "challenge_budget_exhausted"
        elapsed = time.time() - state.started_at
        if elapsed >= max(1, int(config.timebox_seconds)):
            return False, "timebox_exhausted"
        if state.consecutive_stops >= max(1, int(config.max_consecutive_stops)):
            return False, "consecutive_stops_exhausted"
        if queue_snapshot:
            limited_until = float(queue_snapshot.get("rate_limited_until") or 0.0)
            if limited_until and limited_until > time.time():
                return False, "submit_rate_limited"
            if int(queue_snapshot.get("unsolved_count") or 0) <= 0:
                return False, "queue_exhausted"
        return True, "continue"

    def mark_switch(
        self,
        state: PlatformRunState,
        visit_key: str,
        *,
        reason: str = "",
        source: str = "platform_queue",
    ) -> None:
        state.switched_count += 1
        if visit_key:
            state.visited_keys.add(visit_key)
        state.last_switch_reason = str(reason or "").strip()
        state.last_switch_source = str(source or "").strip()
        state.switch_events.append(
            {
                "visit_key": str(visit_key or "").strip(),
                "reason": state.last_switch_reason,
                "source": state.last_switch_source,
                "created_at": time.time(),
            }
        )


__all__ = [
    "PlatformAutonomyRunner",
    "PlatformRunConfig",
    "PlatformRunRecord",
    "PlatformRunState",
]


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)
