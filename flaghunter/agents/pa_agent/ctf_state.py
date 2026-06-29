"""Structured state for deterministic /ctf task execution.

Phase 1 goal:
- introduce an explicit ``CTFState`` container
- centralize flag/artifact/rejected-flag state
- keep the current dispatcher behaviour stable while preparing for a later
  Verifier/RecoveryController refactor
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field, fields
import time
from typing import Any, Literal

from ...knowledge.kill_chain import Phase, phase_round_budget


FlagLevel = Literal["candidate", "runtime", "verified", "rejected"]


@dataclass(slots=True)
class Observation:
    kind: str
    value: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Artifact:
    name: str
    location: str | None = None
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Hypothesis:
    id: str
    kind: str
    description: str
    confidence: float
    status: Literal["active", "supported", "rejected", "exhausted"] = "active"
    supporting_observations: list[str] = field(default_factory=list)
    counter_evidence: list[str] = field(default_factory=list)
    next_experiments: list[str] = field(default_factory=list)
    # Phase 7 §1: Devil's Advocate abort condition + LATS value score
    abort_condition: str | None = None
    fallback_plan: str | None = None
    value_score: float = 0.5


@dataclass(slots=True)
class Experiment:
    id: str
    hypothesis_id: str
    action_type: str
    inputs: dict[str, Any] = field(default_factory=dict)
    expected_signal: str = ""
    observed_signal: str | None = None
    progress_delta: Literal["none", "weak", "strong", "terminal", "rejected"] = "none"
    status: Literal["planned", "running", "completed", "failed"] = "planned"


@dataclass(slots=True)
class VerificationResult:
    decision: Literal["candidate", "runtime", "verified", "rejected", "insufficient"]
    flag: str | None
    evidence_source: str
    confidence: float
    rationale: str
    requires_followup: bool = False
    proof: FlagProof | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FlagProof:
    proof_type: Literal[
        "runtime_http",
        "runtime_command",
        "runtime_collector",
        "source_code_leak",
        "dom_element",
        "platform_accept",
        "user_confirm",
    ]
    evidence_source: str
    evidence_url: str
    evidence_snippet: str
    replayable: bool
    submit_confidence: float
    source_trust: Literal["runtime", "source_only", "platform"]
    hypothesis_id: str | None = None
    strategy_kind: str | None = None
    timestamp: str = ""
    # Phase 7 §8: 审计字段——可复现步骤 + 关联观测
    reproduction_steps: list[str] = field(default_factory=list)
    related_observations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FlagRecord:
    value: str
    level: FlagLevel
    evidence_source: str
    rationale: str = ""
    confidence: float = 0.0
    requires_followup: bool = False
    proof: FlagProof | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExplorationItem:
    id: str
    url_or_path: str
    discovery_source: str
    hint_strength: int
    explored: bool = False
    exploration_result: str | None = None
    added_at: float = 0.0


@dataclass(slots=True)
class LLMStepLog:
    step: int
    action_type: str
    rationale: str
    payload_summary: str
    response_summary: str
    verifier_decision: str
    expected_signal_met: bool
    timestamp: float


@dataclass
class CTFState:
    schema_version: str = "1.7"
    target: str = ""
    goal: str = ""
    detected_type: str | None = None
    submit_endpoint: str | None = None
    submit_success_pattern: str | None = None
    submit_failure_pattern: str | None = None
    submit_platform_type: str | None = None
    submit_challenge_id: str | None = None
    submit_base_url: str | None = None
    submit_api_key: str | None = None
    submit_auth_token: str | None = None
    submit_auto: bool = False
    local_challenge_auto_verify: bool = False
    observations: list[Observation] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    experiments: list[Experiment] = field(default_factory=list)
    candidate_flags: list[FlagRecord] = field(default_factory=list)
    runtime_flags: list[FlagRecord] = field(default_factory=list)
    verified_flags: list[FlagRecord] = field(default_factory=list)
    rejected_flags: list[FlagRecord] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dict)
    no_progress_count: int = 0
    last_progress_marker: str | None = None
    stop_reason: str | None = None
    stop_report: dict[str, Any] | None = None
    exploration_agenda: list[ExplorationItem] = field(default_factory=list)
    interpretations: list[Any] = field(default_factory=list)
    pre_action_reasonings: list[Any] = field(default_factory=list)
    meta_reasonings: list[Any] = field(default_factory=list)
    retrospectives: list[Any] = field(default_factory=list)
    surprises: list[Any] = field(default_factory=list)
    hypothesis_memory_adjustments: dict[str, float] = field(default_factory=dict)
    llm_exploration_steps: int = 0
    llm_exploration_log: list[LLMStepLog] = field(default_factory=list)
    weak_decision_log: list[str] = field(default_factory=list)
    # Kill-chain工序 first-class tracking (P1). ``current_phase`` is the stage the
    # solve is in; ``phase_history`` is the ordered list of stages entered (one
    # entry per real transition). Additive observability only — no control-flow
    # gating. Plain str/list[str] so asdict/from_snapshot round-trip them for
    # free; old (pre-1.4) snapshots lacking these keys fall back to the defaults.
    current_phase: str = Phase.INIT
    phase_history: list[str] = field(default_factory=list)
    # P4 stopping rule — round dwell per phase. Incremented once per solve-loop
    # iteration under the active phase so the RecoveryController can read
    # ``rounds_in_phase(EXPLOIT)`` and apply a phase-budget backstop. Plain
    # dict[str,int] → round-trips for free; pre-1.5 snapshots fall back to {}.
    phase_round_counts: dict[str, int] = field(default_factory=dict)
    # P5 profile覆盖 — per-phase round-budget overrides injected from the active
    # Profile (e.g. code_audit tightens EXPLOIT to 12). Empty → ``effective_phase_budget``
    # falls back to the kill_chain module default, so CTF is byte-identical to P4.
    phase_round_budget_overrides: dict[str, int] = field(default_factory=dict)
    # P5 余量 — 进场信息形态投到 state(url=CTF / source=代码审计 / blackbox=演练)。
    # SETUP 阶段消费它(源码优先 profile 主动摄取在场 artifact);默认 url 故 CTF 字节级一致。
    entry_kind: str = "url"

    def __post_init__(self) -> None:
        self._write_lock = asyncio.Lock()

    def enter_phase(self, phase: str) -> str:
        """Stamp entry into a kill-chain phase (P1 装配线工序 tracking).

        Records the transition for observability (P4 stopping rule, blackboard,
        provenance) without gating control flow. Idempotent on same-phase
        re-entry — appends to ``phase_history`` only on a real change — so the
        history reflects stage transitions, not call frequency. Returns the
        resulting ``current_phase``.
        """
        normalized = str(phase or "").strip() or Phase.INIT
        if normalized != self.current_phase:
            self.current_phase = normalized
            self.phase_history.append(normalized)
        return self.current_phase

    def record_phase_round(self, phase: str | None = None) -> int:
        """Tally one round under ``phase`` (defaults to ``current_phase``).

        Drives the P4 phase-budget stopping rule. Idempotent vocabulary —
        increments a plain counter and returns the new round count.
        """
        normalized = str(phase or self.current_phase or "").strip() or Phase.INIT
        count = self.phase_round_counts.get(normalized, 0) + 1
        self.phase_round_counts[normalized] = count
        return count

    def rounds_in_phase(self, phase: str) -> int:
        """How many rounds have been tallied under ``phase`` (0 if none)."""
        normalized = str(phase or "").strip()
        return int(self.phase_round_counts.get(normalized, 0))

    def effective_phase_budget(self, phase: str) -> int | None:
        """Round budget for ``phase``: profile override if set, else module default.

        P5×P4 seam — the active Profile's ``phase_round_budgets`` are copied onto
        ``phase_round_budget_overrides``; this resolves them with the kill_chain
        module default as the fallback. ``None`` means the phase is unbudgeted.
        """
        normalized = str(phase or "").strip()
        if normalized in self.phase_round_budget_overrides:
            return int(self.phase_round_budget_overrides[normalized])
        return phase_round_budget(normalized)

    def apply_profile(self, profile: Any) -> None:
        """Project a Profile's covering knobs onto this state (P5).

        Duck-typed (no Profile import — knowledge layer stays below agents): reads
        ``entry_kind`` and ``phase_round_budgets`` off whatever is passed. Called
        at every state-creation choke point (bootstrap / crew planning / solve-loop
        re-entry) so the active profile follows a freshly built or resume-rebound
        state. ``None`` is a no-op, leaving the byte-identical CTF defaults.
        """
        if profile is None:
            return
        entry_kind = str(getattr(profile, "entry_kind", "") or "").strip()
        if entry_kind:
            self.entry_kind = entry_kind
        budgets = getattr(profile, "phase_round_budgets", None)
        if isinstance(budgets, dict):
            self.phase_round_budget_overrides = dict(budgets)

    async def acquire_write_lock(self) -> None:
        await self._write_lock.acquire()

    def release_write_lock(self) -> None:
        if self._write_lock.locked():
            self._write_lock.release()

    @asynccontextmanager
    async def write_lock(self):
        await self.acquire_write_lock()
        try:
            yield self
        finally:
            self.release_write_lock()

    def add_observation(
        self,
        kind: str,
        value: str,
        *,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Observation:
        record = Observation(
            kind=str(kind or "").strip(),
            value=str(value or ""),
            source=str(source or "").strip(),
            metadata=dict(metadata or {}),
        )
        self.observations.append(record)
        return record

    def recent_observations(
        self,
        kind: str | None = None,
        *,
        limit: int = 8,
    ) -> list[Observation]:
        normalized_limit = max(1, int(limit))
        normalized_kind = str(kind or "").strip()
        if not normalized_kind:
            return list(self.observations)[-normalized_limit:]

        matched: list[Observation] = []
        for observation in reversed(self.observations):
            if str(getattr(observation, "kind", "") or "").strip() != normalized_kind:
                continue
            matched.append(observation)
            if len(matched) >= normalized_limit:
                break
        matched.reverse()
        return matched

    def add_artifact(
        self,
        name: str,
        *,
        location: str | None = None,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        normalized_name = str(name or "").strip()
        normalized_location = (
            str(location).strip() if location is not None and str(location).strip() else None
        )
        meta = dict(metadata or {})
        for existing in self.artifacts:
            if existing.name == normalized_name and existing.location == normalized_location:
                if source and not existing.source:
                    existing.source = source
                if meta:
                    existing.metadata.update(meta)
                return existing

        artifact = Artifact(
            name=normalized_name,
            location=normalized_location,
            source=str(source or "").strip(),
            metadata=meta,
        )
        self.artifacts.append(artifact)
        return artifact

    def add_flag(
        self,
        value: str,
        *,
        level: FlagLevel,
        evidence_source: str,
        rationale: str = "",
        confidence: float = 0.0,
        requires_followup: bool = False,
        proof: FlagProof | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FlagRecord:
        normalized = str(value or "").strip()
        existing = self._find_existing_flag(normalized)
        if existing is not None and self._level_rank(existing.level) >= self._level_rank(level):
            if rationale and not existing.rationale:
                existing.rationale = rationale
            if evidence_source and not existing.evidence_source:
                existing.evidence_source = evidence_source
            if confidence > existing.confidence:
                existing.confidence = confidence
            existing.requires_followup = existing.requires_followup or requires_followup
            if proof is not None:
                existing.proof = proof
            if metadata:
                existing.metadata.update(dict(metadata))
            return existing

        self._remove_flag_from_other_levels(normalized, keep_level=level)
        bucket = self._bucket_for_level(level)
        for existing in bucket:
            if existing.value == normalized:
                if rationale and not existing.rationale:
                    existing.rationale = rationale
                if evidence_source and not existing.evidence_source:
                    existing.evidence_source = evidence_source
                if confidence > existing.confidence:
                    existing.confidence = confidence
                existing.requires_followup = (
                    existing.requires_followup or requires_followup
                )
                if proof is not None:
                    existing.proof = proof
                if metadata:
                    existing.metadata.update(dict(metadata))
                return existing

        record = FlagRecord(
            value=normalized,
            level=level,
            evidence_source=str(evidence_source or "").strip(),
            rationale=str(rationale or ""),
            confidence=float(confidence or 0.0),
            requires_followup=requires_followup,
            proof=proof,
            metadata=dict(metadata or {}),
        )
        bucket.append(record)
        return record

    def has_flag(self, value: str, *, level: FlagLevel | None = None) -> bool:
        normalized = str(value or "").strip()
        buckets = (
            [self._bucket_for_level(level)]
            if level is not None
            else [
                self.candidate_flags,
                self.runtime_flags,
                self.verified_flags,
                self.rejected_flags,
            ]
        )
        return any(record.value == normalized for bucket in buckets for record in bucket)

    def is_rejected_flag(self, value: str) -> bool:
        return self.has_flag(value, level="rejected")

    def mark_progress(self, marker: str | None = None) -> None:
        marker_text = str(marker or "").strip() or None
        self.no_progress_count = 0
        if marker_text:
            self.last_progress_marker = marker_text

    def mark_no_progress(self, marker: str | None = None) -> int:
        marker_text = str(marker or "").strip() or None
        if marker_text and marker_text != self.last_progress_marker:
            self.last_progress_marker = marker_text
            self.no_progress_count = 1
            return self.no_progress_count
        self.no_progress_count += 1
        return self.no_progress_count

    def add_exploration_item(
        self,
        url_or_path: str,
        *,
        discovery_source: str,
        hint_strength: int,
        explored: bool = False,
        exploration_result: str | None = None,
        added_at: float | None = None,
    ) -> ExplorationItem:
        # Contract:
        # Input: 读取调用方给出的 url_or_path、discovery_source、hint_strength 与可选探索状态。
        # Output: 写入/更新 CTFState.exploration_agenda，并返回对应 ExplorationItem。
        # Success: 同 url_or_path 不重复写入；条目被持久保存在 exploration_agenda。
        # Failure: 数据结构层无恢复器；调用方应通过单元测试发现契约回归。
        normalized_path = str(url_or_path or "").strip()
        normalized_source = str(discovery_source or "").strip()
        normalized_strength = max(1, min(3, int(hint_strength)))
        normalized_result = str(exploration_result) if exploration_result is not None else None
        item_added_at = float(added_at) if added_at is not None else time.time()

        for existing in self.exploration_agenda:
            if existing.url_or_path != normalized_path:
                continue
            existing.discovery_source = existing.discovery_source or normalized_source
            existing.hint_strength = min(existing.hint_strength, normalized_strength)
            existing.explored = existing.explored or explored
            if normalized_result:
                existing.exploration_result = normalized_result
            if existing.added_at == 0.0:
                existing.added_at = item_added_at
            return existing

        item = ExplorationItem(
            id=f"explore_{len(self.exploration_agenda) + 1}",
            url_or_path=normalized_path,
            discovery_source=normalized_source,
            hint_strength=normalized_strength,
            explored=explored,
            exploration_result=normalized_result,
            added_at=item_added_at,
        )
        self.exploration_agenda.append(item)
        return item

    def get_unexplored_priority_items(self, max_hint_strength: int = 2) -> list[ExplorationItem]:
        # Contract:
        # Input: 读取 CTFState.exploration_agenda 与 max_hint_strength 阈值。
        # Output: 返回未探索且 hint_strength <= max_hint_strength 的条目列表，不直接改状态。
        # Success: 结果仅包含高优先级未探索条目，并按 hint_strength / added_at 稳定排序。
        # Failure: 数据结构层无恢复器；上层 RecoveryController 负责消费空结果并继续恢复逻辑。
        normalized_strength = max(1, int(max_hint_strength))
        return sorted(
            [
                item
                for item in self.exploration_agenda
                if not item.explored and item.hint_strength <= normalized_strength
            ],
            key=lambda item: (item.hint_strength, item.added_at, item.url_or_path),
        )

    def is_llm_exploration_allowed(self, max_steps: int = 8) -> bool:
        return self.llm_exploration_steps < max(1, int(max_steps))

    def record_llm_step(self, log: LLMStepLog) -> None:
        self.llm_exploration_steps += 1
        self.llm_exploration_log.append(log)

    def record_weak_decision(self, message: str) -> None:
        normalized = str(message or "").strip()
        if normalized:
            self.weak_decision_log.append(normalized)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_snapshot(self) -> dict[str, Any]:
        return self.to_dict()

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> CTFState:
        allowed_fields = {item.name for item in fields(cls)}
        payload = {
            key: value
            for key, value in dict(data or {}).items()
            if key in allowed_fields
        }
        payload["observations"] = [
            item if isinstance(item, Observation) else Observation(**dict(item or {}))
            for item in list(payload.get("observations") or [])
        ]
        payload["artifacts"] = [
            item if isinstance(item, Artifact) else Artifact(**dict(item or {}))
            for item in list(payload.get("artifacts") or [])
        ]
        payload["hypotheses"] = [
            item if isinstance(item, Hypothesis) else Hypothesis(**dict(item or {}))
            for item in list(payload.get("hypotheses") or [])
        ]
        payload["experiments"] = [
            item if isinstance(item, Experiment) else Experiment(**dict(item or {}))
            for item in list(payload.get("experiments") or [])
        ]
        payload["candidate_flags"] = [
            _coerce_flag_record(item) for item in list(payload.get("candidate_flags") or [])
        ]
        payload["runtime_flags"] = [
            _coerce_flag_record(item) for item in list(payload.get("runtime_flags") or [])
        ]
        payload["verified_flags"] = [
            _coerce_flag_record(item) for item in list(payload.get("verified_flags") or [])
        ]
        payload["rejected_flags"] = [
            _coerce_flag_record(item) for item in list(payload.get("rejected_flags") or [])
        ]
        payload["exploration_agenda"] = [
            item if isinstance(item, ExplorationItem) else ExplorationItem(**dict(item or {}))
            for item in list(payload.get("exploration_agenda") or [])
        ]
        payload["llm_exploration_log"] = [
            item if isinstance(item, LLMStepLog) else LLMStepLog(**dict(item or {}))
            for item in list(payload.get("llm_exploration_log") or [])
        ]
        return cls(**payload)

    def _bucket_for_level(self, level: FlagLevel) -> list[FlagRecord]:
        mapping = {
            "candidate": self.candidate_flags,
            "runtime": self.runtime_flags,
            "verified": self.verified_flags,
            "rejected": self.rejected_flags,
        }
        return mapping[level]

    def _remove_flag_from_other_levels(self, value: str, *, keep_level: FlagLevel) -> None:
        for level in ("candidate", "runtime", "verified", "rejected"):
            if level == keep_level:
                continue
            bucket = self._bucket_for_level(level)  # type: ignore[arg-type]
            bucket[:] = [record for record in bucket if record.value != value]

    def _find_existing_flag(self, value: str) -> FlagRecord | None:
        for bucket in (
            self.rejected_flags,
            self.verified_flags,
            self.runtime_flags,
            self.candidate_flags,
        ):
            for record in bucket:
                if record.value == value:
                    return record
        return None

    def _level_rank(self, level: FlagLevel) -> int:
        return {
            "candidate": 1,
            "runtime": 2,
            "verified": 3,
            "rejected": 4,
        }[level]


def _coerce_flag_record(item: FlagRecord | dict[str, Any]) -> FlagRecord:
    if isinstance(item, FlagRecord):
        return item
    payload = dict(item or {})
    proof = payload.get("proof")
    if isinstance(proof, dict):
        payload["proof"] = FlagProof(**proof)
    return FlagRecord(**payload)
