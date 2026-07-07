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
from enum import Enum
import os
import re
import time
import uuid
from typing import Any, Literal

from ...config.constants import (
    CTF_P1_CLAIM_KIND_ALLOWLIST,
    CTF_RUNTIME_IS_VERIFICATION_SEMANTIC,
    is_ctf_claims_v1_enabled,
)
from ...knowledge.kill_chain import Phase, phase_round_budget
from .solve_node import (
    SolveNode,
    SolveNodeEdge,
    SolveNodeGraph,
    SolveNodeReceipt,
    TaskBrief,
    solve_node_from_dict,
    solve_node_receipt_from_dict,
    solve_node_receipt_to_dict,
    task_brief_from_dict,
    task_brief_to_dict,
    _preview as _p3_preview,
    _safe_metadata as _p3_safe_metadata,
)
from .task_dag_plan import (
    TaskDAGPlan,
    sanitize_task_dag_plan,
    task_dag_plan_from_dict,
    task_dag_plan_to_dict,
)


FlagLevel = Literal["candidate", "runtime", "verified", "rejected"]


class ClaimKind(str, Enum):
    FLAG_FOUND = "flag_found"
    CREDENTIAL_VALID = "credential_valid"
    ENDPOINT_EXISTS = "endpoint_exists"
    EXPLOIT_SUCCEEDED = "exploit_succeeded"
    FILE_DISCLOSED = "file_disclosed"
    PARAMETER_CONTROLLABLE = "parameter_controllable"
    SINK_REACHABLE = "sink_reachable"
    PLATFORM_FEEDBACK = "platform_feedback"


class ClaimLevel(str, Enum):
    ASSUMPTION = "assumption"
    CONJECTURE = "conjecture"
    VERIFIED = "verified"
    RETRACTED = "retracted"


class ClaimStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
    ARCHIVED = "archived"


class VerificationMethod(str, Enum):
    RUNTIME_HTTP = "runtime_http"
    RUNTIME_COMMAND = "runtime_command"
    RUNTIME_BROWSER = "runtime_browser"
    DETERMINISTIC_PARSER = "deterministic_parser"
    CROSS_CHECK = "cross_check"
    PLATFORM_SUBMIT = "platform_submit"
    LOCAL_CHALLENGE_AUTO_VERIFY = "local_challenge_auto_verify"
    OPERATOR_CONFIRM = "operator_confirm"
    PRIOR_SUBMIT_LOOKUP = "prior_submit_lookup"
    NONE = "none"


class VerificationDecision(str, Enum):
    INSUFFICIENT = "insufficient"
    CANDIDATE = "candidate"
    RUNTIME_SUPPORTED = "runtime_supported"
    VERIFIED = "verified"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


class ExecutionTraceKind(str, Enum):
    TOOL_RECEIPT = "tool_receipt"
    VERIFICATION_RECEIPT = "verification_receipt"
    CONTROL_RECEIPT = "control_receipt"


P1_CLAIM_KIND_ALLOWLIST: tuple[str, ...] = CTF_P1_CLAIM_KIND_ALLOWLIST
# P1 semantic freeze: "runtime" remains a verification/evidence quality, not a
# canonical ClaimLevel. The legacy runtime_flags bucket stays intact for now.
RUNTIME_IS_VERIFICATION_SEMANTIC: bool = CTF_RUNTIME_IS_VERIFICATION_SEMANTIC


def _now_ts() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _require_text(value: Any, field_name: str) -> str:
    raw = value.value if isinstance(value, Enum) else value
    normalized = str(raw or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _llm_exploration_ceiling() -> int:
    """Generous, env-overridable ceiling on cumulative LLM-exploration steps.

    A cost/safety **boundary**, not a behavioural cage — the old hardcoded 8
    starved out-of-repertoire exploration. Set ``FLAGHUNTER_LLM_EXPLORATION_CEILING``
    to tune. The adaptive "stop when genuinely stuck" decision lives at the call
    site, not here.
    """
    try:
        return max(8, int(os.environ.get("FLAGHUNTER_LLM_EXPLORATION_CEILING", "24") or 24))
    except (TypeError, ValueError):
        return 24


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
class Claim:
    id: str
    run_id: str = ""
    node_id: str | None = None
    parent_claim_ids: list[str] = field(default_factory=list)
    superseded_by: str | None = None
    content: str = ""
    normalized_content: str = ""
    kind: ClaimKind = ClaimKind.FLAG_FOUND
    level: ClaimLevel = ClaimLevel.CONJECTURE
    status: ClaimStatus = ClaimStatus.ACTIVE
    producer_type: str = ""
    producer_id: str = ""
    source_channel: str = ""
    primary_trace_id: str = ""
    evidence_trace_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    verification_record_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    confidence_reason: str = ""
    replayable: bool = False
    tainted_by: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=_now_ts)
    updated_at: float = field(default_factory=_now_ts)
    retracted_at: float | None = None


@dataclass(slots=True)
class VerificationRecord:
    id: str
    run_id: str = ""
    claim_id: str = ""
    verifier_type: str = ""
    verifier_id: str = ""
    method: VerificationMethod = VerificationMethod.NONE
    decision: VerificationDecision = VerificationDecision.INSUFFICIENT
    passed: bool = False
    sufficient_for_upgrade: bool = False
    trace_id: str = ""
    evidence_trace_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    rationale: str = ""
    evidence_summary: str = ""
    confidence_delta: float = 0.0
    replayable: bool = False
    submitted_value: str | None = None
    platform_receipt: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=_now_ts)


@dataclass(slots=True)
class ExecutionTrace:
    id: str
    kind: ExecutionTraceKind = ExecutionTraceKind.TOOL_RECEIPT
    receipt_id: str = ""
    created_at: float = field(default_factory=_now_ts)
    producer: str = ""
    input_summary: str = ""
    output_summary: str = ""
    success: bool = False
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


ToolReceipt = ExecutionTrace
VerificationReceipt = ExecutionTrace


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
    claims_by_id: dict[str, Claim] = field(default_factory=dict)
    claim_index_by_kind: dict[str, list[str]] = field(default_factory=dict)
    verification_records_by_id: dict[str, VerificationRecord] = field(default_factory=dict)
    verification_index_by_claim: dict[str, list[str]] = field(default_factory=dict)
    execution_traces_by_id: dict[str, ExecutionTrace] = field(default_factory=dict)
    solve_node_graph: SolveNodeGraph = field(default_factory=SolveNodeGraph)
    task_briefs_by_id: dict[str, TaskBrief] = field(default_factory=dict)
    solve_node_receipts_by_id: dict[str, SolveNodeReceipt] = field(default_factory=dict)
    task_dag_plan: TaskDAGPlan = field(default_factory=TaskDAGPlan)
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
    # Phase 1 曲库 miss 一等信号 —— 当 HypothesisEngine 的规则层没有任何结构化探测器命中
    # (只能落到 generic_web_recon 兜底)时置 True。每次 generate() 重算,是活信号:recon
    # 后若某 _has_* 命中则回落 False。纯加性观测,**不**门控控制流——曲库外自主探索升级
    # (Phase 2)会消费它作为触发门。默认 False 故曲库命中的题字节级一致。
    repertoire_miss: bool = False

    def __post_init__(self) -> None:
        self._write_lock = asyncio.Lock()
        self._rebuild_claim_indexes()

    @property
    def ctf_claims_v1_enabled(self) -> bool:
        return is_ctf_claims_v1_enabled()

    def _require_claim_store_writes_enabled(self) -> None:
        if not self.ctf_claims_v1_enabled:
            raise RuntimeError(
                "canonical claim store writes require FLAGHUNTER_CTF_CLAIMS_V1=1"
            )

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

    def record_execution_trace(
        self,
        *,
        kind: ExecutionTraceKind | str,
        producer: str,
        input_summary: str = "",
        output_summary: str = "",
        success: bool = False,
        artifact_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
        receipt_id: str | None = None,
        created_at: float | None = None,
    ) -> ExecutionTrace:
        normalized_kind = _coerce_execution_trace_kind(_require_text(kind, "kind"))
        normalized_producer = _require_text(producer, "producer")
        normalized_trace_id = (
            str(trace_id or "").strip() if trace_id is not None else ""
        ) or _new_id("trace")
        normalized_receipt_id = (
            str(receipt_id or "").strip() if receipt_id is not None else ""
        ) or _new_id("receipt")
        trace = ExecutionTrace(
            id=normalized_trace_id,
            kind=normalized_kind,
            receipt_id=normalized_receipt_id,
            created_at=float(created_at if created_at is not None else _now_ts()),
            producer=normalized_producer,
            input_summary=str(input_summary or "")[:500],
            output_summary=str(output_summary or "")[:1000],
            success=bool(success),
            artifact_refs=[
                str(item).strip() for item in (artifact_refs or []) if str(item).strip()
            ],
            metadata=dict(metadata or {}),
        )
        self.execution_traces_by_id[trace.id] = trace
        return trace

    def record_tool_receipt(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        output_summary: str = "",
        success: bool = False,
        artifact_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolReceipt:
        normalized_tool = _require_text(tool_name, "tool_name")
        meta = dict(metadata or {})
        meta.setdefault("tool_name", normalized_tool)
        return self.record_execution_trace(
            kind=ExecutionTraceKind.TOOL_RECEIPT,
            producer=f"tool:{normalized_tool}",
            input_summary=_safe_compact(arguments or {}),
            output_summary=output_summary,
            success=success,
            artifact_refs=artifact_refs,
            metadata=meta,
        )

    def record_verification_receipt(
        self,
        *,
        verifier_id: str,
        decision: str,
        flag: str | None,
        evidence_source: str = "",
        rationale: str = "",
        success: bool = False,
        artifact_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VerificationReceipt:
        normalized_verifier = _require_text(verifier_id, "verifier_id")
        normalized_decision = _require_text(decision, "decision")
        meta = dict(metadata or {})
        meta.setdefault("decision", normalized_decision)
        meta.setdefault("flag", str(flag or "").strip())
        meta.setdefault("evidence_source", str(evidence_source or "").strip())
        return self.record_execution_trace(
            kind=ExecutionTraceKind.VERIFICATION_RECEIPT,
            producer=normalized_verifier,
            input_summary=str(flag or "").strip(),
            output_summary=str(rationale or "")[:1000],
            success=success,
            artifact_refs=artifact_refs,
            metadata=meta,
        )

    def record_solve_node(self, node: SolveNode | dict[str, Any]) -> str:
        normalized = _p3_sanitize_solve_node(
            node if isinstance(node, SolveNode) else solve_node_from_dict(node)
        )
        self.solve_node_graph.add_node(normalized)
        return normalized.id

    def get_solve_node(self, node_id: str) -> SolveNode | None:
        return self.solve_node_graph.get_node(node_id)

    def record_task_brief(self, brief: TaskBrief | dict[str, Any]) -> str:
        normalized = _p3_sanitize_task_brief(
            brief if isinstance(brief, TaskBrief) else task_brief_from_dict(brief)
        )
        self.task_briefs_by_id[normalized.id] = normalized
        return normalized.id

    def get_task_brief(self, brief_id: str) -> TaskBrief | None:
        return self.task_briefs_by_id.get(str(brief_id or "").strip())

    def record_solve_node_receipt(
        self,
        receipt: SolveNodeReceipt | dict[str, Any],
    ) -> str:
        normalized = _p3_sanitize_solve_node_receipt(
            receipt
            if isinstance(receipt, SolveNodeReceipt)
            else solve_node_receipt_from_dict(receipt)
        )
        self.solve_node_receipts_by_id[normalized.id] = normalized
        return normalized.id

    def get_solve_node_receipt(self, receipt_id: str) -> SolveNodeReceipt | None:
        return self.solve_node_receipts_by_id.get(str(receipt_id or "").strip())

    def set_task_dag_plan(self, plan: TaskDAGPlan | dict[str, Any] | None) -> str:
        normalized = _coerce_task_dag_plan(plan)
        self.task_dag_plan = normalized
        return normalized.id

    def get_task_dag_plan(self) -> TaskDAGPlan:
        self.task_dag_plan = _coerce_task_dag_plan(self.task_dag_plan)
        return self.task_dag_plan

    def create_claim(
        self,
        *,
        kind: ClaimKind | str,
        content: str,
        producer_type: str,
        producer_id: str,
        primary_trace_id: str,
        run_id: str | None = None,
        node_id: str | None = None,
        parent_claim_ids: list[str] | None = None,
        level: ClaimLevel | str = ClaimLevel.CONJECTURE,
        source_channel: str = "",
        evidence_trace_ids: list[str] | None = None,
        artifact_refs: list[str] | None = None,
        confidence: float = 0.0,
        confidence_reason: str = "",
        replayable: bool = False,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Claim:
        return _create_claim(
            self,
            kind=kind,
            content=content,
            producer_type=producer_type,
            producer_id=producer_id,
            primary_trace_id=primary_trace_id,
            run_id=run_id,
            node_id=node_id,
            parent_claim_ids=parent_claim_ids,
            level=level,
            source_channel=source_channel,
            evidence_trace_ids=evidence_trace_ids,
            artifact_refs=artifact_refs,
            confidence=confidence,
            confidence_reason=confidence_reason,
            replayable=replayable,
            tags=tags,
            metadata=metadata,
        )

    def append_verification_record(
        self,
        claim_id: str,
        *,
        verifier_type: str,
        verifier_id: str,
        method: VerificationMethod | str,
        decision: VerificationDecision | str,
        trace_id: str,
        passed: bool = False,
        sufficient_for_upgrade: bool = False,
        run_id: str | None = None,
        evidence_trace_ids: list[str] | None = None,
        artifact_refs: list[str] | None = None,
        rationale: str = "",
        evidence_summary: str = "",
        confidence_delta: float = 0.0,
        replayable: bool = False,
        submitted_value: str | None = None,
        platform_receipt: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VerificationRecord:
        self._require_claim_store_writes_enabled()
        normalized_claim_id = _require_text(claim_id, "claim_id")
        claim = self.get_claim(normalized_claim_id)
        if claim is None:
            raise KeyError(f"unknown claim_id: {claim_id}")
        normalized_trace = _require_text(trace_id, "trace_id")
        normalized_verifier_type = _require_text(verifier_type, "verifier_type")
        normalized_verifier_id = _require_text(verifier_id, "verifier_id")
        normalized_method = _coerce_verification_method(_require_text(method, "method"))
        normalized_decision = _coerce_verification_decision(
            _require_text(decision, "decision")
        )

        record = VerificationRecord(
            id=_new_id("verification"),
            run_id=str(run_id or claim.run_id or "").strip(),
            claim_id=claim.id,
            verifier_type=normalized_verifier_type,
            verifier_id=normalized_verifier_id,
            method=normalized_method,
            decision=normalized_decision,
            passed=bool(passed),
            sufficient_for_upgrade=bool(sufficient_for_upgrade),
            trace_id=normalized_trace,
            evidence_trace_ids=[
                str(item).strip() for item in (evidence_trace_ids or []) if str(item).strip()
            ],
            artifact_refs=[str(item).strip() for item in (artifact_refs or []) if str(item).strip()],
            rationale=str(rationale or ""),
            evidence_summary=str(evidence_summary or ""),
            confidence_delta=float(confidence_delta or 0.0),
            replayable=bool(replayable),
            submitted_value=str(submitted_value).strip() if submitted_value is not None else None,
            platform_receipt=dict(platform_receipt) if isinstance(platform_receipt, dict) else None,
            metadata=dict(metadata or {}),
        )
        self.verification_records_by_id[record.id] = record
        self.verification_index_by_claim.setdefault(claim.id, []).append(record.id)
        if record.id not in claim.verification_record_ids:
            claim.verification_record_ids.append(record.id)
        claim.updated_at = _now_ts()
        return record

    def upgrade_claim_to_verified(
        self,
        claim_id: str,
        *,
        verification_record_id: str,
        verifier_id: str | None = None,
    ) -> Claim:
        self._require_claim_store_writes_enabled()
        claim = self.get_claim(claim_id)
        if claim is None:
            raise KeyError(f"unknown claim_id: {claim_id}")
        if claim.level == ClaimLevel.RETRACTED or claim.status == ClaimStatus.RETRACTED:
            raise ValueError("retracted claims cannot be upgraded")

        record = self.verification_records_by_id.get(str(verification_record_id or "").strip())
        if record is None or record.claim_id != claim.id:
            raise KeyError(f"verification record does not belong to claim: {verification_record_id}")
        if not (record.passed and record.sufficient_for_upgrade):
            raise ValueError("verified upgrade requires a passed sufficient verification record")

        claim.level = ClaimLevel.VERIFIED
        claim.status = ClaimStatus.ACTIVE
        claim.confidence = max(float(claim.confidence or 0.0), 1.0)
        if verifier_id:
            claim.metadata["verified_by"] = str(verifier_id or "").strip()
        claim.metadata["verified_by_record_id"] = record.id
        trace = self.execution_traces_by_id.get(record.trace_id)
        if trace is not None:
            claim.metadata["verified_trace_id"] = trace.id
            claim.metadata["verified_receipt_id"] = trace.receipt_id
            claim.metadata.pop("verified_trace_warning", None)
        else:
            claim.metadata.pop("verified_receipt_id", None)
            claim.metadata["verified_trace_warning"] = (
                "verification_record_trace_missing_receipt"
            )
        claim.updated_at = _now_ts()
        if record.id not in claim.verification_record_ids:
            claim.verification_record_ids.append(record.id)
        return claim

    def retract_claim(
        self,
        claim_id: str,
        *,
        reason: str,
        trace_id: str | None = None,
        actor_id: str | None = None,
        caused_by_claim_id: str | None = None,
    ) -> Claim:
        self._require_claim_store_writes_enabled()
        claim = self.get_claim(claim_id)
        if claim is None:
            raise KeyError(f"unknown claim_id: {claim_id}")
        now = _now_ts()
        claim.level = ClaimLevel.RETRACTED
        claim.status = ClaimStatus.RETRACTED
        claim.retracted_at = now
        claim.updated_at = now
        claim.metadata["retraction_reason"] = str(reason or "").strip()
        if trace_id:
            claim.metadata["retraction_trace_id"] = str(trace_id or "").strip()
        if actor_id:
            claim.metadata["retracted_by"] = str(actor_id or "").strip()
        if caused_by_claim_id:
            claim.metadata["caused_by_claim_id"] = str(caused_by_claim_id or "").strip()
        return claim

    def get_claim(self, claim_id: str) -> Claim | None:
        return self.claims_by_id.get(str(claim_id or "").strip())

    def get_execution_trace(self, trace_id: str) -> ExecutionTrace | None:
        return self.execution_traces_by_id.get(str(trace_id or "").strip())

    def get_claim_trace(self, claim_id: str) -> ExecutionTrace | None:
        claim = self.get_claim(claim_id)
        if claim is None:
            return None
        return self.get_execution_trace(claim.primary_trace_id)

    def get_verification_trace(self, record_id: str) -> ExecutionTrace | None:
        record = self.verification_records_by_id.get(str(record_id or "").strip())
        if record is None:
            return None
        return self.get_execution_trace(record.trace_id)

    def get_claim_trace_chain(self, claim_id: str) -> dict[str, Any]:
        claim = self.get_claim(claim_id)
        if claim is None:
            return {
                "claim_id": str(claim_id or "").strip(),
                "primary_trace": None,
                "evidence_traces": [],
                "verification_traces": [],
            }
        evidence_traces = [
            self._trace_projection(trace_id)
            for trace_id in list(claim.evidence_trace_ids or [])
            if self._trace_projection(trace_id) is not None
        ]
        verification_traces: list[dict[str, Any]] = []
        for record_id in list(claim.verification_record_ids or []):
            record = self.verification_records_by_id.get(record_id)
            if record is None:
                continue
            trace = self.get_execution_trace(record.trace_id)
            if trace is None:
                continue
            projection = self._trace_projection(trace.id)
            if projection is None:
                continue
            projection["verification_record_id"] = record.id
            projection["decision"] = record.decision.value
            projection["method"] = record.method.value
            projection["evidence_trace_ids"] = list(record.evidence_trace_ids or [])
            verification_traces.append(projection)

        return {
            "claim_id": claim.id,
            "claim_kind": claim.kind.value,
            "content": claim.content,
            "primary_trace": self._trace_projection(claim.primary_trace_id),
            "evidence_traces": evidence_traces,
            "verification_traces": verification_traces,
        }

    def claim_trace_refs(self, *, limit: int = 5) -> list[dict[str, Any]]:
        normalized_limit = int(limit)
        if normalized_limit <= 0:
            return []
        selected_claims = sorted(
            list(self.claims_by_id.values()),
            key=lambda claim: (
                float(claim.updated_at or claim.created_at or 0.0),
                str(claim.id or ""),
            ),
            reverse=True,
        )[:normalized_limit]
        selected_claims = sorted(
            selected_claims,
            key=lambda claim: (
                float(claim.updated_at or claim.created_at or 0.0),
                str(claim.id or ""),
            ),
        )
        refs: list[dict[str, Any]] = []
        for claim in selected_claims:
            verification_trace_ids: list[str] = []
            for record_id in list(claim.verification_record_ids or []):
                record = self.verification_records_by_id.get(record_id)
                if record is not None and record.trace_id:
                    verification_trace_ids.append(record.trace_id)
            refs.append(
                {
                    "claimId": claim.id,
                    "kind": claim.kind.value,
                    "content": _text_preview(
                        _redact_context_preview(claim.content),
                        limit=160,
                    ),
                    "primaryTraceId": claim.primary_trace_id,
                    "verificationTraceIds": list(dict.fromkeys(verification_trace_ids)),
                }
            )
        return refs

    def claim_evidence_refs(
        self,
        *,
        limit: int = 5,
        evidence_trace_limit: int = 3,
        preview_limit: int = 160,
    ) -> list[dict[str, Any]]:
        normalized_limit = int(limit)
        if normalized_limit <= 0:
            return []
        normalized_evidence_limit = max(0, int(evidence_trace_limit))
        selected_claims = sorted(
            list(self.claims_by_id.values()),
            key=lambda claim: (
                float(claim.updated_at or claim.created_at or 0.0),
                str(claim.id or ""),
            ),
            reverse=True,
        )[:normalized_limit]
        selected_claims = sorted(
            selected_claims,
            key=lambda claim: (
                float(claim.updated_at or claim.created_at or 0.0),
                str(claim.id or ""),
            ),
        )

        refs: list[dict[str, Any]] = []
        for claim in selected_claims:
            records = [
                self.verification_records_by_id[item]
                for item in list(claim.verification_record_ids or [])
                if item in self.verification_records_by_id
            ]
            latest_record = max(records, key=lambda record: record.created_at, default=None)
            evidence_trace_ids = list(
                dict.fromkeys(
                    str(item).strip()
                    for item in list(claim.evidence_trace_ids or [])
                    if str(item).strip()
                )
            )[:normalized_evidence_limit]
            verification_trace_ids = list(
                dict.fromkeys(
                    str(record.trace_id or "").strip()
                    for record in records
                    if str(record.trace_id or "").strip()
                )
            )[:normalized_evidence_limit]
            primary_trace = self._compact_trace_projection(
                claim.primary_trace_id,
                preview_limit=preview_limit,
            )
            evidence_traces = [
                projection
                for projection in (
                    self._compact_trace_projection(trace_id, preview_limit=preview_limit)
                    for trace_id in evidence_trace_ids
                )
                if projection is not None
            ]
            source_trace_id = str(claim.metadata.get("source_trace_id") or "").strip()
            source_receipt_id = str(claim.metadata.get("source_receipt_id") or "").strip()
            if not source_receipt_id and source_trace_id:
                source_trace = self.get_execution_trace(source_trace_id)
                if source_trace is not None:
                    source_receipt_id = source_trace.receipt_id
            refs.append(
                {
                    "claimId": claim.id,
                    "kind": claim.kind.value,
                    "level": claim.level.value,
                    "status": claim.status.value,
                    "contentPreview": _text_preview(
                        _redact_context_preview(claim.content),
                        limit=max(1, int(preview_limit)),
                    ),
                    "primaryTraceId": claim.primary_trace_id,
                    "evidenceTraceIds": evidence_trace_ids,
                    "verificationTraceIds": verification_trace_ids,
                    "sourceTool": str(claim.metadata.get("source_tool") or "").strip(),
                    "sourceTraceId": source_trace_id,
                    "sourceReceiptId": source_receipt_id,
                    "latestVerificationDecision": (
                        latest_record.decision.value if latest_record is not None else ""
                    ),
                    "latestVerificationTraceId": (
                        latest_record.trace_id if latest_record is not None else ""
                    ),
                    "primaryTrace": primary_trace,
                    "evidenceTraces": evidence_traces,
                }
            )
        return refs

    def find_claims_by_kind(
        self,
        kind: ClaimKind | str,
        *,
        include_inactive: bool = False,
    ) -> list[Claim]:
        normalized_kind = _coerce_claim_kind(kind)
        ids = self.claim_index_by_kind.get(normalized_kind.value, [])
        claims = [self.claims_by_id[item] for item in ids if item in self.claims_by_id]
        if include_inactive:
            return claims
        return [
            claim
            for claim in claims
            if claim.status == ClaimStatus.ACTIVE and claim.level != ClaimLevel.RETRACTED
        ]

    def active_claims(self, kind: ClaimKind | str | None = None) -> list[Claim]:
        if kind is not None:
            return self.find_claims_by_kind(kind)
        return [
            claim
            for claim in self.claims_by_id.values()
            if claim.status == ClaimStatus.ACTIVE and claim.level != ClaimLevel.RETRACTED
        ]

    def strongest_claim(self, kind: ClaimKind | str) -> Claim | None:
        claims = self.find_claims_by_kind(kind)
        if not claims:
            return None
        return max(
            claims,
            key=lambda claim: (
                self._claim_level_rank(claim.level),
                float(claim.confidence or 0.0),
                float(claim.updated_at or 0.0),
            ),
        )

    def _trace_projection(self, trace_id: str) -> dict[str, Any] | None:
        trace = self.get_execution_trace(trace_id)
        if trace is None:
            return None
        return {
            "id": trace.id,
            "receipt_id": trace.receipt_id,
            "kind": trace.kind.value,
            "producer": trace.producer,
            "success": trace.success,
            "artifact_refs": list(trace.artifact_refs or []),
            "metadata": dict(trace.metadata or {}),
        }

    def _compact_trace_projection(
        self,
        trace_id: str,
        *,
        preview_limit: int = 160,
    ) -> dict[str, Any] | None:
        trace = self.get_execution_trace(trace_id)
        if trace is None:
            return None
        return {
            "id": trace.id,
            "receiptId": trace.receipt_id,
            "kind": trace.kind.value,
            "producer": trace.producer,
            "success": trace.success,
            "outputPreview": _text_preview(
                _redact_context_preview(trace.output_summary),
                limit=max(1, int(preview_limit)),
            ),
        }

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

    def is_llm_exploration_allowed(self, max_steps: int | None = None) -> bool:
        # 探索预算天花板 = 约束**边界**,不是死板步数(见 [[feedback_less_is_more_dont_cage_llm]])。
        # 默认放宽到 24(旧硬编码 8 把曲库外探索饿死),env FLAGHUNTER_LLM_EXPLORATION_CEILING 可调。
        # 这只是成本/安全上限;真正的"做不下去就停"由调用方的进度门(卡死才停)自适应决定。
        ceiling = max_steps if max_steps is not None else _llm_exploration_ceiling()
        return self.llm_exploration_steps < max(1, int(ceiling))

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
        return _export_state_snapshot(self)

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> CTFState:
        return _restore_state_snapshot(data, cls)

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

    def _normalize_claim_content(self, kind: ClaimKind, content: str) -> str:
        text = str(content or "").strip()
        if kind == ClaimKind.FLAG_FOUND:
            return text
        return " ".join(text.split())

    def _index_claim(self, claim: Claim) -> None:
        bucket = self.claim_index_by_kind.setdefault(claim.kind.value, [])
        if claim.id not in bucket:
            bucket.append(claim.id)

    def _rebuild_claim_indexes(self) -> None:
        self.claim_index_by_kind = {}
        for claim in self.claims_by_id.values():
            self._normalize_restored_claim_integrity(claim)
            self._index_claim(claim)

        self.verification_index_by_claim = {}
        for record in self.verification_records_by_id.values():
            if not record.claim_id or record.claim_id not in self.claims_by_id:
                continue
            self.verification_index_by_claim.setdefault(record.claim_id, []).append(record.id)

        for claim in self.claims_by_id.values():
            ids = self.verification_index_by_claim.get(claim.id, [])
            merged = list(dict.fromkeys([*claim.verification_record_ids, *ids]))
            claim.verification_record_ids = [
                item for item in merged if item in self.verification_records_by_id
            ]
            self._demote_invalid_restored_verified_claim(claim)

    def _normalize_restored_claim_integrity(self, claim: Claim) -> None:
        if claim.level == ClaimLevel.RETRACTED or claim.status == ClaimStatus.RETRACTED:
            claim.level = ClaimLevel.RETRACTED
            claim.status = ClaimStatus.RETRACTED
            if claim.retracted_at is None:
                claim.retracted_at = float(claim.updated_at or claim.created_at or _now_ts())

    def _has_sufficient_verified_record(self, claim: Claim) -> bool:
        for record_id in list(claim.verification_record_ids or []):
            record = self.verification_records_by_id.get(record_id)
            if record is None:
                continue
            if record.claim_id != claim.id:
                continue
            if record.decision != VerificationDecision.VERIFIED:
                continue
            if record.passed is not True:
                continue
            if record.sufficient_for_upgrade is not True:
                continue
            return True
        return False

    def _demote_invalid_restored_verified_claim(self, claim: Claim) -> None:
        if claim.level != ClaimLevel.VERIFIED:
            return
        if self._has_sufficient_verified_record(claim):
            return
        claim.level = ClaimLevel.CONJECTURE
        claim.status = ClaimStatus.ACTIVE
        claim.confidence = min(float(claim.confidence or 0.0), 0.5)
        claim.metadata["restore_integrity_warning"] = (
            "verified_claim_missing_sufficient_record"
        )
        claim.updated_at = _now_ts()

    def _claim_level_rank(self, level: ClaimLevel | str) -> int:
        normalized = _coerce_claim_level(level)
        return {
            ClaimLevel.ASSUMPTION: 1,
            ClaimLevel.CONJECTURE: 2,
            ClaimLevel.VERIFIED: 3,
            ClaimLevel.RETRACTED: 0,
        }[normalized]


def _export_state_snapshot(state: CTFState) -> dict[str, Any]:
    snapshot = state.to_dict()
    snapshot["solve_node_graph"] = _coerce_solve_node_graph(
        state.solve_node_graph
    ).to_dict()
    snapshot["task_briefs_by_id"] = {
        brief_id: task_brief_to_dict(_p3_sanitize_task_brief(brief))
        for brief_id, brief in state.task_briefs_by_id.items()
    }
    snapshot["solve_node_receipts_by_id"] = {
        receipt_id: solve_node_receipt_to_dict(
            _p3_sanitize_solve_node_receipt(receipt)
        )
        for receipt_id, receipt in state.solve_node_receipts_by_id.items()
    }
    snapshot["task_dag_plan"] = task_dag_plan_to_dict(
        _coerce_task_dag_plan(state.task_dag_plan)
    )
    return snapshot


def _create_claim(
    state: CTFState,
    *,
    kind: ClaimKind | str,
    content: str,
    producer_type: str,
    producer_id: str,
    primary_trace_id: str,
    run_id: str | None = None,
    node_id: str | None = None,
    parent_claim_ids: list[str] | None = None,
    level: ClaimLevel | str = ClaimLevel.CONJECTURE,
    source_channel: str = "",
    evidence_trace_ids: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    confidence: float = 0.0,
    confidence_reason: str = "",
    replayable: bool = False,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Claim:
    state._require_claim_store_writes_enabled()
    normalized_kind = _coerce_claim_kind(_require_text(kind, "kind"))
    if normalized_kind.value not in P1_CLAIM_KIND_ALLOWLIST:
        raise ValueError(f"claim kind is not enabled for P1: {normalized_kind.value}")
    normalized_level = _coerce_claim_level(level)
    if normalized_level == ClaimLevel.VERIFIED:
        raise ValueError("create_claim cannot directly create verified claims")
    normalized_content = state._normalize_claim_content(normalized_kind, content)
    if not normalized_content:
        raise ValueError("claim content is required")
    normalized_trace = _require_text(primary_trace_id, "primary_trace_id")
    normalized_producer_type = _require_text(producer_type, "producer_type")
    normalized_producer_id = _require_text(producer_id, "producer_id")

    now = _now_ts()
    claim = Claim(
        id=_new_id("claim"),
        run_id=str(run_id or "").strip(),
        node_id=(
            str(node_id).strip()
            if node_id is not None and str(node_id).strip()
            else None
        ),
        parent_claim_ids=[
            str(item).strip()
            for item in (parent_claim_ids or [])
            if str(item).strip()
        ],
        content=str(content or "").strip(),
        normalized_content=normalized_content,
        kind=normalized_kind,
        level=normalized_level,
        status=ClaimStatus.ACTIVE,
        producer_type=normalized_producer_type,
        producer_id=normalized_producer_id,
        source_channel=str(source_channel or "").strip(),
        primary_trace_id=normalized_trace,
        evidence_trace_ids=[
            str(item).strip()
            for item in (evidence_trace_ids or [])
            if str(item).strip()
        ],
        artifact_refs=[
            str(item).strip()
            for item in (artifact_refs or [])
            if str(item).strip()
        ],
        confidence=max(0.0, min(1.0, float(confidence or 0.0))),
        confidence_reason=str(confidence_reason or ""),
        replayable=bool(replayable),
        tags=[str(item).strip() for item in (tags or []) if str(item).strip()],
        metadata=dict(metadata or {}),
        created_at=now,
        updated_at=now,
    )
    state.claims_by_id[claim.id] = claim
    state._index_claim(claim)
    return claim


def _restore_state_snapshot(
    data: dict[str, Any],
    state_type: type[CTFState] = CTFState,
) -> CTFState:
    allowed_fields = {item.name for item in fields(state_type)}
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
        _coerce_flag_record(item)
        for item in list(payload.get("candidate_flags") or [])
    ]
    payload["runtime_flags"] = [
        _coerce_flag_record(item)
        for item in list(payload.get("runtime_flags") or [])
    ]
    payload["verified_flags"] = [
        _coerce_flag_record(item)
        for item in list(payload.get("verified_flags") or [])
    ]
    payload["rejected_flags"] = [
        _coerce_flag_record(item)
        for item in list(payload.get("rejected_flags") or [])
    ]
    raw_claims = dict(payload.get("claims_by_id") or {})
    payload["claims_by_id"] = {
        str(claim_id): _coerce_claim(item)
        for claim_id, item in raw_claims.items()
    }
    raw_verifications = dict(payload.get("verification_records_by_id") or {})
    payload["verification_records_by_id"] = {
        str(record_id): _coerce_verification_record(item)
        for record_id, item in raw_verifications.items()
    }
    raw_traces = dict(payload.get("execution_traces_by_id") or {})
    payload["execution_traces_by_id"] = {
        str(trace_id): _coerce_execution_trace(item)
        for trace_id, item in raw_traces.items()
    }
    payload["solve_node_graph"] = _coerce_solve_node_graph(
        payload.get("solve_node_graph")
    )
    payload["task_briefs_by_id"] = _coerce_task_brief_store(
        payload.get("task_briefs_by_id")
    )
    payload["solve_node_receipts_by_id"] = _coerce_solve_node_receipt_store(
        payload.get("solve_node_receipts_by_id")
    )
    payload["task_dag_plan"] = _coerce_task_dag_plan(
        payload.get("task_dag_plan")
    )
    payload["claim_index_by_kind"] = _coerce_string_list_index(
        payload.get("claim_index_by_kind")
    )
    payload["verification_index_by_claim"] = _coerce_string_list_index(
        payload.get("verification_index_by_claim")
    )
    payload["exploration_agenda"] = [
        item
        if isinstance(item, ExplorationItem)
        else ExplorationItem(**dict(item or {}))
        for item in list(payload.get("exploration_agenda") or [])
    ]
    payload["llm_exploration_log"] = [
        item if isinstance(item, LLMStepLog) else LLMStepLog(**dict(item or {}))
        for item in list(payload.get("llm_exploration_log") or [])
    ]
    return state_type(**payload)


def _coerce_flag_record(item: FlagRecord | dict[str, Any]) -> FlagRecord:
    if isinstance(item, FlagRecord):
        return item
    payload = dict(item or {})
    proof = payload.get("proof")
    if isinstance(proof, dict):
        payload["proof"] = FlagProof(**proof)
    return FlagRecord(**payload)


def _coerce_claim_kind(value: ClaimKind | str) -> ClaimKind:
    if isinstance(value, ClaimKind):
        return value
    return ClaimKind(str(value or "").strip())


def _coerce_claim_level(value: ClaimLevel | str) -> ClaimLevel:
    if isinstance(value, ClaimLevel):
        return value
    return ClaimLevel(str(value or "").strip())


def _coerce_claim_status(value: ClaimStatus | str) -> ClaimStatus:
    if isinstance(value, ClaimStatus):
        return value
    return ClaimStatus(str(value or "").strip())


def _coerce_verification_method(value: VerificationMethod | str) -> VerificationMethod:
    if isinstance(value, VerificationMethod):
        return value
    return VerificationMethod(str(value or "").strip())


def _coerce_verification_decision(value: VerificationDecision | str) -> VerificationDecision:
    if isinstance(value, VerificationDecision):
        return value
    return VerificationDecision(str(value or "").strip())


def _coerce_execution_trace_kind(value: ExecutionTraceKind | str) -> ExecutionTraceKind:
    if isinstance(value, ExecutionTraceKind):
        return value
    return ExecutionTraceKind(str(value or "").strip())


def _coerce_claim(item: Claim | dict[str, Any]) -> Claim:
    if isinstance(item, Claim):
        return item
    payload = dict(item or {})
    payload["kind"] = _coerce_claim_kind(payload.get("kind", ClaimKind.FLAG_FOUND))
    payload["level"] = _coerce_claim_level(payload.get("level", ClaimLevel.CONJECTURE))
    payload["status"] = _coerce_claim_status(payload.get("status", ClaimStatus.ACTIVE))
    for key in [
        "parent_claim_ids",
        "evidence_trace_ids",
        "artifact_refs",
        "verification_record_ids",
        "tainted_by",
        "tags",
    ]:
        payload[key] = [str(value) for value in list(payload.get(key) or [])]
    payload["metadata"] = dict(payload.get("metadata") or {})
    return Claim(**payload)


def _coerce_verification_record(
    item: VerificationRecord | dict[str, Any],
) -> VerificationRecord:
    if isinstance(item, VerificationRecord):
        return item
    payload = dict(item or {})
    payload["method"] = _coerce_verification_method(
        payload.get("method", VerificationMethod.NONE)
    )
    payload["decision"] = _coerce_verification_decision(
        payload.get("decision", VerificationDecision.INSUFFICIENT)
    )
    for key in ["evidence_trace_ids", "artifact_refs"]:
        payload[key] = [str(value) for value in list(payload.get(key) or [])]
    payload["metadata"] = dict(payload.get("metadata") or {})
    if payload.get("platform_receipt") is not None:
        payload["platform_receipt"] = dict(payload.get("platform_receipt") or {})
    return VerificationRecord(**payload)


def _coerce_execution_trace(item: ExecutionTrace | dict[str, Any]) -> ExecutionTrace:
    if isinstance(item, ExecutionTrace):
        return item
    payload = dict(item or {})
    payload["kind"] = _coerce_execution_trace_kind(
        payload.get("kind", ExecutionTraceKind.TOOL_RECEIPT)
    )
    payload["artifact_refs"] = [
        str(value) for value in list(payload.get("artifact_refs") or [])
    ]
    payload["metadata"] = dict(payload.get("metadata") or {})
    return ExecutionTrace(**payload)


def _safe_compact(value: Any, *, limit: int = 500) -> str:
    try:
        import json

        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        text = str(value)
    return text[:limit]


def _text_preview(value: Any, *, limit: int = 160) -> str:
    text = str(value or "")
    return text[: max(0, int(limit))]


def _redact_context_preview(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"(?im)^\s*set-cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*authorization\s*:.*$", "<redacted>", text)
    text = re.sub(
        r"(?i)\bauthorization\s*:\s*bearer\s+[^\s,;&]+",
        "authorization=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|api[_-]?key|password|secret|session|cookie|authorization)\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)([\"'](?:token|api[_-]?key|password|secret|session|cookie|authorization)[\"']\s*:\s*)([\"'][^\"']*[\"']|[^,\n\r}\]]+)",
        r'\1"<redacted>"',
        text,
    )
    return text


def _p3_sanitize_solve_node(node: SolveNode) -> SolveNode:
    return SolveNode(
        id=str(node.id or ""),
        run_id=_p3_preview(node.run_id, limit=160),
        parent_id=_p3_preview(node.parent_id, limit=160),
        kind=node.kind,
        status=node.status,
        title=_p3_preview(node.title, limit=160),
        goal=_p3_preview(node.goal, limit=160),
        summary=_p3_preview(node.summary, limit=160),
        created_at=node.created_at,
        updated_at=node.updated_at,
        started_at=node.started_at,
        finished_at=node.finished_at,
        claim_ids=list(node.claim_ids),
        trace_ids=list(node.trace_ids),
        receipt_ids=list(node.receipt_ids),
        artifact_refs=[_p3_preview(item, limit=160) for item in node.artifact_refs],
        metadata=_p3_safe_metadata(node.metadata, preview_limit=160),
    )


def _p3_sanitize_edge(edge: SolveNodeEdge) -> SolveNodeEdge:
    return SolveNodeEdge(
        source_id=str(edge.source_id or ""),
        target_id=str(edge.target_id or ""),
        relation=str(edge.relation or "depends_on"),
        created_at=edge.created_at,
        metadata=_p3_safe_metadata(edge.metadata, preview_limit=160),
    )


def _p3_sanitize_task_brief(brief: TaskBrief) -> TaskBrief:
    return TaskBrief(
        id=str(brief.id or ""),
        node_id=str(brief.node_id or ""),
        run_id=_p3_preview(brief.run_id, limit=160),
        worker_type=_p3_preview(brief.worker_type, limit=160),
        objective=_p3_preview(brief.objective, limit=160),
        context_summary=_p3_preview(brief.context_summary, limit=160),
        constraints=[_p3_preview(item, limit=160) for item in brief.constraints],
        allowed_tool_names=[
            _p3_preview(item, limit=160) for item in brief.allowed_tool_names
        ],
        blocked_tool_names=[
            _p3_preview(item, limit=160) for item in brief.blocked_tool_names
        ],
        claim_ids=list(brief.claim_ids),
        trace_ids=list(brief.trace_ids),
        artifact_refs=[_p3_preview(item, limit=160) for item in brief.artifact_refs],
        created_at=brief.created_at,
        metadata=_p3_safe_metadata(brief.metadata, preview_limit=160),
    )


def _p3_sanitize_solve_node_receipt(
    receipt: SolveNodeReceipt,
) -> SolveNodeReceipt:
    return SolveNodeReceipt(
        id=str(receipt.id or ""),
        node_id=str(receipt.node_id or ""),
        run_id=_p3_preview(receipt.run_id, limit=160),
        worker_id=_p3_preview(receipt.worker_id, limit=160),
        worker_type=_p3_preview(receipt.worker_type, limit=160),
        status=receipt.status,
        started_at=receipt.started_at,
        finished_at=receipt.finished_at,
        duration_ms=receipt.duration_ms,
        input_brief_id=str(receipt.input_brief_id or ""),
        output_summary=_p3_preview(receipt.output_summary, limit=160),
        claim_ids=list(receipt.claim_ids),
        trace_ids=list(receipt.trace_ids),
        artifact_refs=[
            _p3_preview(item, limit=160) for item in receipt.artifact_refs
        ],
        error_class=_p3_preview(receipt.error_class, limit=160),
        error_summary=_p3_preview(receipt.error_summary, limit=160),
        metadata=_p3_safe_metadata(receipt.metadata, preview_limit=160),
    )


def _coerce_solve_node_graph(value: Any) -> SolveNodeGraph:
    if isinstance(value, SolveNodeGraph):
        graph = value
    elif isinstance(value, dict):
        raw = dict(value)
        if "nodes" not in raw and isinstance(raw.get("nodes_by_id"), dict):
            raw["nodes"] = list(dict(raw.get("nodes_by_id") or {}).values())
        graph = SolveNodeGraph.from_dict(raw)
    else:
        graph = SolveNodeGraph()

    sanitized = SolveNodeGraph()
    for node in graph.nodes_by_id.values():
        sanitized.add_node(_p3_sanitize_solve_node(node))
    for edge in graph.edges:
        safe_edge = _p3_sanitize_edge(edge)
        try:
            sanitized.add_edge(
                safe_edge.source_id,
                safe_edge.target_id,
                relation=safe_edge.relation,
                metadata=safe_edge.metadata,
            )
        except ValueError as exc:
            sanitized.restore_warnings.append(_p3_preview(str(exc), limit=160))
    sanitized.restore_warnings.extend(
        _p3_preview(item, limit=160) for item in graph.restore_warnings
    )
    return sanitized


def _coerce_task_brief_store(value: Any) -> dict[str, TaskBrief]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, TaskBrief] = {}
    for item in value.values():
        if not isinstance(item, (TaskBrief, dict)):
            continue
        try:
            brief = _p3_sanitize_task_brief(task_brief_from_dict(item))
        except (TypeError, ValueError):
            continue
        result[brief.id] = brief
    return result


def _coerce_solve_node_receipt_store(value: Any) -> dict[str, SolveNodeReceipt]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, SolveNodeReceipt] = {}
    for item in value.values():
        if not isinstance(item, (SolveNodeReceipt, dict)):
            continue
        try:
            receipt = _p3_sanitize_solve_node_receipt(
                solve_node_receipt_from_dict(item)
            )
        except (TypeError, ValueError):
            continue
        result[receipt.id] = receipt
    return result


def _coerce_task_dag_plan(value: Any) -> TaskDAGPlan:
    if isinstance(value, TaskDAGPlan):
        return sanitize_task_dag_plan(value)
    if isinstance(value, dict):
        try:
            return sanitize_task_dag_plan(task_dag_plan_from_dict(value))
        except (TypeError, ValueError) as exc:
            return TaskDAGPlan(
                restore_warnings=[
                    _p3_preview(f"invalid task_dag_plan snapshot: {exc}", limit=160)
                ]
            )
    if value is None:
        return TaskDAGPlan()
    return TaskDAGPlan(
        restore_warnings=[
            "invalid task_dag_plan snapshot"
        ]
    )


def _coerce_string_list_index(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): [str(item) for item in list(items or [])]
        for key, items in value.items()
    }
