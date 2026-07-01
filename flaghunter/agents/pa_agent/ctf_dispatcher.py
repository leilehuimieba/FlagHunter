"""Minimal deterministic CTF dispatcher for /ctf execution mode."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import socket
import sys
import struct
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, quote, quote_plus, urlencode, urljoin, urlparse

try:
    import jwt as _pyjwt  # type: ignore[import-not-found]
except Exception:
    _pyjwt = None

from ...tools.notes import get_all_notes_sync, notes as notes_tool
from ...tools.tool_guard import ToolGuard, ToolMissingError
from ...llm.utils import parse_llm_json
from ...harness.artifact_registry import ArtifactRegistry
from ...harness.audit_events import (
    build_artifact_registered_event,
    build_checkpoint_written_event,
    build_missing_tools_recorded_event,
    build_recovery_decision_event,
    build_task_finished_event,
    build_tool_called_event,
    build_tool_finished_event,
    build_verification_decision_event,
)
from ...harness.checkpoint_store import CheckpointStore
from ...harness.session_ledger import SessionLedger
from ...knowledge.kill_chain import Phase
from ...knowledge.profile import Profile, get_profile
from .chains.base import _ChainOutcome
from .chains.file_read import LFIChainMixin
from .chains.injection import GenericInjectionChainMixin
from .chains.jwt import JWTChainMixin
from .chains.misc import MiscChainMixin
from .chains.sqli import SQLIChainMixin
from .chains.upload import UploadChainMixin
from .chains.web import WebChainMixin
from .chains.xss import XSSChainMixin
from .coordinator import CTFCoordinator, CoordinatorDispatcherServices
from .flag_parser import FlagParserMixin
from .flag_proof import FlagProofMixin
from .hash_backup_executor import HashBackupExecutorMixin
from .artifact_forensics import ArtifactForensicsMixin
from .audit_infra import AuditInfraMixin, AuditStore, RuntimeAuditedActions
from .capability_registry import CapabilityRegistry
from .ctf_state import CTFState, FlagProof, FlagRecord, LLMStepLog
from .exploit_replay_memory import ExploitReplayMemoryMixin
from .flag_observer import FlagObserver, FlagObserverMixin
from .hypothesis_engine import _CHAIN_BY_KIND, HypothesisEngine
from .jwt_contact_chain import JWTContactChainMixin
from .jwt_executor import JWTExecutor, JWTExecutorMixin
from .llm_executor import LLMExecutor, LLMExecutorMixin
from .note_store import NoteStore, NoteStoreMixin
from .php_exploit_chain import PHPExploitChainMixin
from .platform_executor import PlatformExecutorMixin
from .platform_orchestrator import PlatformTaskOrchestrator
from .progress_tracker import ProgressTracker, ProgressTrackerMixin
from .reasoning import PreActionReasoning, ReasoningLayer
from .recon_executor import ReconExecutor, ReconExecutorMixin
from .recovery import RecoveryController
from .render_surface import RenderSurfaceMixin
from .source_hint_registry import SourceHintRegistryMixin
from .sqli_executor import SQLiExecutorMixin
from .ssti_executor import SSTIExecutorMixin
from .xss_collector_chain import XSSCollectorChainMixin
from .strategy_registry import StrategyContext, StrategyRegistry
from .strategy_memory import ChallengeFingerprint, StrategyMemoryStore
from .ctf_planner import (
    detect_type,
    find_auth_form,
    find_writable_field_name,
    get_ctf_chain,
)
from .verifier import CTFVerifier
from ...knowledge.retrospective import export_ctf_session_retrospective
from .dispatcher_helpers import *  # noqa: F401,F403  # extracted helpers/consts, re-exported
# _CollectorServer moved to xss_collector_chain.py with XSSCollectorChainMixin (20th cut)


# _FLAG_RE / _STRICT_FLAG_RE / _SCRIPT_SRC_RE / _BACKUP_CLUE_RE moved to dispatcher_helpers.py (re-exported via import *)
# _ATTACHMENT_CLUE_RE moved to artifact_forensics.py with ArtifactForensicsMixin (19th cut)
# _COMMON_BACKUP_PATHS / _DJANGO_STATIC_SOURCE_PROBES moved to hash_backup_executor.py
# with HashBackupExecutorMixin (17th cut)
# _SOURCE_HINT_BACKUP_PROBES moved to source_hint_registry.py with SourceHintRegistryMixin (22nd cut)
# _SQLI_AUTH_BYPASS_PAYLOADS moved to sqli_executor.py with SQLiExecutorMixin (16th cut)
# _CONTACT_POW_CHALLENGE_RE moved to jwt_contact_chain.py with JWTContactChainMixin (21st cut)
_HTML_TAG_PSEUDO_PATHS = {
    "/a",
    "/article",
    "/aside",
    "/body",
    "/button",
    "/canvas",
    "/div",
    "/fieldset",
    "/figure",
    "/footer",
    "/form",
    "/h1",
    "/h2",
    "/h3",
    "/h4",
    "/h5",
    "/h6",
    "/head",
    "/header",
    "/html",
    "/img",
    "/input",
    "/label",
    "/legend",
    "/li",
    "/link",
    "/main",
    "/meta",
    "/nav",
    "/ol",
    "/option",
    "/p",
    "/script",
    "/section",
    "/small",
    "/span",
    "/style",
    "/svg",
    "/table",
    "/tbody",
    "/td",
    "/textarea",
    "/tfoot",
    "/th",
    "/thead",
    "/title",
    "/tr",
    "/ul",
}

_STATIC_RESOURCE_SUFFIXES = (
    ".avif",
    ".bmp",
    ".css",
    ".eot",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".map",
    ".mjs",
    ".mp3",
    ".mp4",
    ".ogg",
    ".otf",
    ".png",
    ".svg",
    ".ttf",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
)
_SERVER_SIDE_PATH_SUFFIXES = (
    ".asp",
    ".aspx",
    ".bak",
    ".cgi",
    ".do",
    ".gz",
    ".htaccess",
    ".html",
    ".inc",
    ".ini",
    ".jar",
    ".jsp",
    ".json",
    ".log",
    ".php",
    ".phps",
    ".phtml",
    ".pl",
    ".py",
    ".rb",
    ".sh",
    ".sql",
    ".swp",
    ".tar",
    ".tar.gz",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
    ".zip",
)
# Solve-time reverse lookup (_select_hypothesis_for_chain) shares the single
# source of truth defined in hypothesis_engine._CHAIN_BY_KIND. Aliased rather
# than copied so the two can never drift again (the old fork lacked
# jwt_manipulation → the jwt chain could never select its own hypothesis).
_CHAIN_NAME_FOR_HYPOTHESIS = _CHAIN_BY_KIND


def _best_flag_record(bucket: list[FlagRecord]) -> FlagRecord | None:
    """Highest-confidence flag in a level bucket (or ``None`` when empty).

    Used by the blackboard terminal mapping to surface the strongest near-solve flag
    so a wait_for_verification / candidate-only stop reports its value rather than
    dropping it. Mirrors ``blackboard_adapter._best_flag``'s selection rule.
    """
    return max(
        bucket,
        key=lambda r: float(getattr(r, "confidence", 0.0) or 0.0),
        default=None,
    )


def _blackboard_loop_enabled() -> bool:
    """Slice 5a opt-in flag for the model-driven solve loop (default OFF).

    Same ``FLAGHUNTER_*`` truthy convention as the other dispatcher env flags
    (e.g. ``FLAGHUNTER_AUTO_INSTALL``). Off → the chain-order harness runs unchanged.
    """
    return os.getenv("FLAGHUNTER_BLACKBOARD_LOOP", "false").strip().lower() == "true"


@dataclass
class SolveResult:
    success: bool
    flag: str | None = None
    chain_used: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    missing_tools: list[str] = field(default_factory=list)
    reason: str = ""


class CTFTaskDispatcher(
    AuditInfraMixin,
    LLMExecutorMixin,
    ReconExecutorMixin,
    FlagObserverMixin,
    FlagParserMixin,
    FlagProofMixin,
    JWTExecutorMixin,
    NoteStoreMixin,
    PlatformExecutorMixin,
    ProgressTrackerMixin,
    RenderSurfaceMixin,
    SSTIExecutorMixin,
    XSSCollectorChainMixin,
    JWTContactChainMixin,
    SourceHintRegistryMixin,
    ExploitReplayMemoryMixin,
    SQLiExecutorMixin,
    HashBackupExecutorMixin,
    PHPExploitChainMixin,
    ArtifactForensicsMixin,
    GenericInjectionChainMixin,
    LFIChainMixin,
    MiscChainMixin,
    JWTChainMixin,
    UploadChainMixin,
    SQLIChainMixin,
    XSSChainMixin,
    WebChainMixin,
):
    def __init__(
        self,
        runtime,
        progress_callback: Callable[[str], None] | None = None,
        collector_port: int = 7777,
        verification_callback: Callable[[str], Any] | None = None,
        llm: Any | None = None,
        exploitation_mode: str | None = None,
        profile: Profile | str | None = None,
    ):
        self.runtime = runtime
        self.progress_callback = progress_callback
        self.collector_port = collector_port
        self.llm = llm
        # P5: the active project-type Profile (CTF / code_audit / …). Always a
        # resolved Profile — ``None`` / unknown names resolve to CTF, so callers
        # that pass nothing keep the byte-identical CTF default.
        self.profile = profile if isinstance(profile, Profile) else get_profile(profile)
        # "aggressive" (CTF default): take the shortest chain to the flag — fire
        # specific exploit payloads directly. "conservative" (pentest/audit): gate
        # specific exploitation on prior vuln-class confirmation (info-gathering
        # first). See _ssti_exploitation_gated_by_mode. Precedence: an explicit
        # ``exploitation_mode=`` wins (keeps direct-mode callers/tests stable);
        # otherwise it is derived from the active Profile.
        _mode = exploitation_mode if exploitation_mode is not None else self.profile.exploitation_mode
        self.exploitation_mode = str(_mode or "aggressive").strip().lower() or "aggressive"
        self.tool_guard = ToolGuard(runtime=runtime)
        self._notes_log: list[str] = []
        # Phase 0 指标真相: 每次审计 runtime 动作(HTTP/shell/browser)经 _record_session_event
        # 发 tool_called 时递增。CTF 快路径不走 agent base-loop,对外 Loops/Tools 计数原本恒 0,
        # 报告失真。activity_metrics() 把它和 EXPLOIT 轮/LLM 探索步一并暴露给 CLI 回填。
        self._tool_call_count = 0
        self.state: CTFState | None = None
        self._progress = ProgressTracker()
        self._flag_observer = FlagObserver()
        self._note_store = NoteStore()
        self._runtime_actions = RuntimeAuditedActions()
        self._audit_store = AuditStore()
        self._jwt_executor = JWTExecutor()
        self._llm_executor = LLMExecutor()
        self._recon_executor = ReconExecutor()
        self.hypothesis_engine = HypothesisEngine()
        self.recovery_controller = RecoveryController(self.hypothesis_engine)
        self.strategy_registry = StrategyRegistry.build_default()
        self.capability_registry = CapabilityRegistry.build_default(
            runtime=runtime,
            tool_guard=self.tool_guard,
            collector_port=collector_port,
        )
        self.strategy_memory = StrategyMemoryStore()
        self.reasoning_layer = ReasoningLayer()
        self.platform_orchestrator = PlatformTaskOrchestrator()
        self._current_fingerprint: ChallengeFingerprint | None = None
        self._memory_match_ids: list[str] = []
        # Negative-feedback recall (consume half of record_failure): payloads that
        # failed on similar past challenges, surfaced to the planner so it avoids
        # re-proposing them. Empty until the strategy-memory contract populates it.
        self._known_failed_payloads: list[str] = []
        # P8 回灌: cross-run tool-chain hints {"reuse":[...], "avoid":[...]} mined
        # from provenance + P7-scored, surfaced to the next-action planner.
        self._emergent_chain_hints: dict[str, list[str]] = {}
        # P10/P11 白盒: source-audit suspicious points (file:line) surfaced to the
        # planner on source entry (code_audit profile). Empty for url entry (CTF).
        self._source_audit_findings: list[str] = []
        self._pending_wrong_flag_feedback: list[dict[str, str]] = []
        self._active_hypothesis_context = None
        self._active_strategy_context = None
        self._exhausted_visit_url_targets: set[str] = set()
        self._challenge_context: dict[str, Any] | None = None
        self._ingress_handoff: dict[str, Any] | None = None
        self._session_ledger: SessionLedger | None = None
        self._ledger_run_id: str | None = None
        self._artifact_registry: ArtifactRegistry | None = None
        self._artifact_run_id: str | None = None
        self._checkpoint_store: CheckpointStore | None = None
        self._checkpoint_run_id: str | None = None
        self._restored_resume_checkpoint_id: str | None = None
        self._local_challenge_artifacts_loaded = False
        self._registered_local_source_hints_loaded = False
        self._failover_monitor = None
        self._failover_monitor_owned = False
        self.coordinator = CTFCoordinator()
        self.verifier = CTFVerifier(
            runtime=runtime,
            confirmation_callback=verification_callback,
        )

    async def run(
        self,
        target: str,
        goal: str,
        type: str | None = None,
        hint: str | None = None,
        submit_profile: dict[str, Any] | None = None,
        challenge_context: dict[str, Any] | None = None,
        ingress_handoff: dict[str, Any] | None = None,
        run_id: str | None = None,
        ledger_root: str | Path | None = None,
        registry_root: str | Path | None = None,
        checkpoint_root: str | Path | None = None,
    ) -> SolveResult:
        # Façade (slice 1c): the public entry always delegates to the coordinator,
        # which runs the setup contracts and hands off to _run_solve_loop. The
        # fallback retry supports coordinators whose execute() predates ingress_handoff.
        kwargs = {
            "target": target,
            "goal": goal,
            "type": type,
            "hint": hint,
            "submit_profile": submit_profile,
            "challenge_context": challenge_context,
            "run_id": run_id,
            "ledger_root": ledger_root,
            "registry_root": registry_root,
            "checkpoint_root": checkpoint_root,
        }
        try:
            return await self.coordinator.execute(
                self,
                **kwargs,
                ingress_handoff=ingress_handoff,
            )
        except TypeError as exc:
            if "ingress_handoff" not in str(exc):
                raise
            return await self.coordinator.execute(self, **kwargs)

    def activity_metrics(self) -> dict[str, int]:
        """Real solve-activity counters for honest run reporting (Phase 0).

        The CTF dispatcher never drives the agent base-loop, so a caller's
        loop/tool counters (e.g. the CLI summary) used to read 0 even after
        dozens of LLM turns and HTTP probes — the report claimed "Loops 0 /
        Commands 0" for an 18-LLM-call, ~10-HTTP run. Surface the true counts:

        - ``loops``: EXPLOIT solve-loop rounds + LLM-exploration sub-steps —
          the dispatcher's analogue of agent base-loop iterations.
        - ``llm_exploration_steps``: LLM-driven exploration turns (subset of loops).
        - ``tool_calls``: audited runtime actions (HTTP / shell / browser).
        - ``experiments``: hypothesis experiments recorded.

        Pure read of already-tracked state — additive observability, no
        control-flow effect.
        """
        state = self.state
        exploit_rounds = state.rounds_in_phase(Phase.EXPLOIT) if state is not None else 0
        llm_steps = int(getattr(state, "llm_exploration_steps", 0) or 0) if state is not None else 0
        experiments = len(state.experiments) if state is not None else 0
        return {
            "loops": int(exploit_rounds) + llm_steps,
            "llm_exploration_steps": llm_steps,
            "tool_calls": int(getattr(self, "_tool_call_count", 0) or 0),
            "experiments": experiments,
        }

    def _structured_followup_next_action(self) -> str:
        handoff = self._ingress_handoff if isinstance(self._ingress_handoff, dict) else {}
        return str(handoff.get("nextAction") or "").strip()

    def _structured_followup_value(self, key: str) -> str:
        handoff = self._ingress_handoff if isinstance(self._ingress_handoff, dict) else {}
        return str(handoff.get(key) or "").strip()

    def _record_ingress_handoff_observations(
        self,
        ingress_handoff: dict[str, Any],
    ) -> None:
        if self.state is None or not isinstance(ingress_handoff, dict):
            return
        resume_bootstrap = ingress_handoff.get("resumeBootstrap")
        if not isinstance(resume_bootstrap, dict):
            return
        summary = str(resume_bootstrap.get("summary") or "").strip()
        run_id = str(resume_bootstrap.get("runId") or "").strip()
        checkpoint_id = str(resume_bootstrap.get("checkpointId") or "").strip()
        if not any([summary, run_id, checkpoint_id]):
            return
        metadata = {
            "decision_kind": str(ingress_handoff.get("decisionKind") or "").strip(),
            "next_action": str(ingress_handoff.get("nextAction") or "").strip(),
            "run_id": run_id,
            "checkpoint_id": checkpoint_id,
        }
        observation_value = summary or f"resume from {checkpoint_id or run_id}"
        if any(
            obs.kind == "resume_bootstrap_hint"
            and obs.source == "ingress_handoff"
            and obs.value == observation_value
            and getattr(obs, "metadata", {}) == metadata
            for obs in self.state.observations
        ):
            return
        self.state.add_observation(
            "resume_bootstrap_hint",
            observation_value,
            source="ingress_handoff",
            metadata=metadata,
        )

    async def _run_solve_loop(
        self,
        *,
        ctx: CoordinatorDispatcherServices | None = None,
        target: str,
        hint: str,
        page_features: dict[str, Any],
        detected_type: str,
        chain_order: list[str],
        result: SolveResult | None = None,
    ) -> SolveResult:
        """Run the chain/exploit solve loop over a prepared chain_order.

        Dedicated seam between the coordinator's setup phase and the actual
        solving loop (façade slices 1a–1c). The coordinator calls this directly
        once all setup contracts have run; ``run`` is now a thin façade that
        always delegates to ``coordinator.execute``, so the old dual-purpose
        re-entry and its ``_*_ready`` skip-flags are gone. ``result`` defaults to
        a fresh ``SolveResult`` when omitted.

        承载收尾·机制刀(L4a, 2026-06-22): coordinator hands its run-scoped
        ``RunContext`` in via ``ctx``; the solve loop forwards that seam object
        (not the raw dispatcher) to every ``self.coordinator._*`` contract call.
        ``ctx`` is still a zero-carrying transparent proxy, so ``ctx.X`` is
        byte-for-byte ``self.X`` and behaviour is unchanged — this only wires up
        the *reachability* a later cut needs to carry executors onto the seam.
        When ``ctx`` is omitted (direct/legacy call), it falls back to ``self``
        so the cut is strictly additive. See ADR §5.2 卡 L4a.
        """
        if result is None:
            result = SolveResult(success=False)
        # P1: entering the chain/exploit solve loop — stamp the EXPLOIT phase.
        # P5: re-project the active Profile onto the (possibly resume-rebound)
        # state so entry_kind + the recovery backstop's budget overrides follow it.
        if self.state is not None:
            self.state.enter_phase(Phase.EXPLOIT)
            self.state.apply_profile(self.profile)
        # Slice 5a (strangler cutover, default OFF): when FLAGHUNTER_BLACKBOARD_LOOP
        # is enabled, hand the solve to the model-driven Shape-A loop instead of the
        # chain-order harness below. Strictly additive and reversible — when the flag
        # is off (or the run lacks state/llm) this is a no-op and the old path is
        # byte-unchanged. The recovery/terminal/experiment contracts below are NOT yet
        # replicated by the new loop (migrated incrementally in 5b); this bypass exists
        # to validate the driver on live runs, not to retire them. The new loop is the
        # eventual sole driver (then choose_chain_order is deleted) only once it covers
        # them. See [[project_flaghunter_blackboard_pivot]].
        if self.state is not None and self.llm is not None and _blackboard_loop_enabled():
            # F1 (P0 fatal-bug hardening): the blackboard loop was invoked unguarded.
            # Any exception (LLM 5xx, brain init, ChainHands crash, strategy_memory
            # shape-error) would crash the whole solve — falling back to the old chain
            # -order path is unsafe (副作用重复:budget/state 已消费),so we salvage the
            # partial ``result`` and route it through the same terminal ``_finalize_solve_result``
            # the loop's happy path uses. The old harness stays reserved for when the
            # feature-flag is OFF (byte-identical to pre-5a); the flag being ON now
            # means "brain drives, brain is the only driver" — a mid-loop crash reports
            # the failure, it does not silently re-run the whole solve.
            try:
                return await self._run_blackboard_loop(
                    target=target,
                    hint=hint,
                    page_features=page_features,
                    result=result,
                )
            except Exception as exc:
                self._emit(
                    f"[CTF dispatcher] [blackboard] loop error: {type(exc).__name__}: {exc} "
                    "— finalizing partial result"
                )
                result.success = False
                result.reason = f"blackboard_loop_error:{type(exc).__name__}:{str(exc)[:120]}"
                return await self._finalize_solve_result(result)
        chain_order = list(dict.fromkeys(chain_order))
        # The seam object the coordinator contracts run against: the carried
        # ``RunContext`` when supplied, else the raw dispatcher (== old behaviour).
        contract_ctx: Any = ctx if ctx is not None else self

        no_progress_rounds = 0
        chain_index = 0
        while chain_index < len(chain_order):
            chain_name = chain_order[chain_index]
            # P4: tally one EXPLOIT round per loop iteration so the recovery
            # controller's phase-budget backstop can cap runaway churn.
            if self.state is not None:
                self.state.record_phase_round(Phase.EXPLOIT)
            result.chain_used.append(chain_name)
            self._restore_context()
            before_state = self._snapshot_flag_counts()
            iteration_contract = self.coordinator._prepare_chain_iteration_contract(
                contract_ctx,
                chain_name=chain_name,
                target=target,
                page_features=page_features,
                hint=hint,
                chain_order=chain_order,
            )
            active_hypothesis = iteration_contract["active_hypothesis"]
            strategy = iteration_contract["strategy"]
            self._active_hypothesis_context = active_hypothesis
            self._active_strategy_context = strategy
            experiment = iteration_contract["experiment"]

            try:
                outcome = await self._execute_chain(
                    chain_name=chain_name,
                    target=target,
                    page_features=page_features,
                    hint=hint,
                )
            except ToolMissingError as exc:
                self._active_hypothesis_context = None
                self._active_strategy_context = None
                missing_names = sorted(exc.missing)
                if os.getenv("FLAGHUNTER_AUTO_INSTALL", "false").lower() == "true":
                    for name in missing_names:
                        ok = await self.tool_guard.install_and_verify(name)
                        self._emit(f"[CTF dispatcher] auto-install {name}: {'ok' if ok else 'failed'}")
                    continue
                recovery_contract = await self.coordinator._apply_missing_tools_recovery_contract(
                    contract_ctx,
                    chain_name=chain_name,
                    chain_index=chain_index,
                    chain_order=chain_order,
                    missing_names=missing_names,
                    result=result,
                    target=target,
                    active_hypothesis=active_hypothesis,
                    experiment=experiment,
                )
                if recovery_contract["continue_loop"]:
                    chain_order = list(recovery_contract["chain_order"])
                    chain_index = int(recovery_contract["next_chain_index"])
                    continue
                return recovery_contract["final_result"]
            finally:
                self._active_hypothesis_context = None
                self._active_strategy_context = None
            wrong_flag_result = await self.coordinator._apply_wrong_flag_early_stop_contract(
                contract_ctx,
                result=result,
                outcome=outcome,
                target=target,
                chain_name=chain_name,
            )
            if wrong_flag_result is not None:
                return wrong_flag_result
            terminal_result = await self.coordinator._apply_terminal_success_contract(
                contract_ctx,
                result=result,
                outcome=outcome,
                chain_name=chain_name,
                active_hypothesis=active_hypothesis,
                experiment=experiment,
            )
            if terminal_result is not None:
                return terminal_result

            progress_contract = self.coordinator._apply_progress_evaluation_contract(
                contract_ctx,
                chain_name=chain_name,
                before_state=before_state,
                outcome=outcome,
                no_progress_rounds=no_progress_rounds,
                active_hypothesis=active_hypothesis,
                experiment=experiment,
            )
            progress_delta = progress_contract["progress_delta"]
            effective_progress = progress_contract["effective_progress"]
            no_progress_rounds = int(progress_contract["no_progress_rounds"])
            # Phase 7 §1: Devil's Advocate abort_condition 提前剪枝
            if self.state is not None:
                _aborted = self.hypothesis_engine.update_after_chain(
                    self.state,
                    observed_signal=outcome.reason if outcome is not None else chain_name,
                )
                if _aborted:
                    self._emit(
                        f"[CTF hypothesis] abort_condition 命中，提前终止假设: "
                        + ", ".join(h.kind for h in _aborted)
                    )
            recovery_contract = await self.coordinator._apply_after_chain_recovery_contract(
                contract_ctx,
                chain_name=chain_name,
                chain_index=chain_index,
                chain_order=chain_order,
                result=result,
                target=target,
                active_hypothesis=active_hypothesis,
                effective_progress=effective_progress,
                no_progress_rounds=no_progress_rounds,
            )
            no_progress_rounds = int(recovery_contract["no_progress_rounds"])
            if recovery_contract["continue_loop"]:
                chain_order = list(recovery_contract["chain_order"])
                chain_index = int(recovery_contract["next_chain_index"])
                continue
            if recovery_contract["final_result"] is not None:
                return recovery_contract["final_result"]
            chain_index = int(recovery_contract["next_chain_index"])

        return await self.coordinator._apply_final_recovery_contract(
            contract_ctx,
            result=result,
            target=target,
            detected_type=detected_type,
            no_progress_rounds=no_progress_rounds,
        )

    async def _run_blackboard_loop(
        self,
        *,
        target: str,
        hint: str,
        page_features: dict[str, Any],
        result: SolveResult,
    ) -> SolveResult:
        """Slice 5a: drive the solve with the model-driven Shape-A blackboard loop.

        Binds the loop's seams to this dispatcher — chains-as-tools (``ChainHands`` /
        ``chain_tools`` over ``_chain_handler_map`` + ``_execute_chain``), the
        deterministic ``CTFState`` seams, and an LLM brain over ``self.llm`` — then maps
        the loop's ``SolveOutcome`` onto a ``SolveResult`` and finalizes it the same way
        the chain-order path does. Reached only behind ``FLAGHUNTER_BLACKBOARD_LOOP``.

        Known capability gaps vs the chain-order harness (terminal-success
        verification, recovery/rerank, experiment feedback, missing-tool handling) are
        NOT yet covered here; they migrate onto the loop's record/verify seams in 5b.
        Until then this path is an opt-in driver for live validation, not a replacement.
        """
        from .blackboard_adapter import bind_seams
        from .blackboard_brain import LLMBrain
        from .blackboard_hands import ChainContext, ChainHands, chain_tools
        from .blackboard_loop import Budget, run_blackboard_solve

        context = ChainContext(
            target=target,
            page_features=dict(page_features or {}),
            hint=str(hint or ""),
        )

        # 5b cut-1 (terminal-success migration): the old chain-order harness detected a
        # win from the chain's asserted ``outcome.flag`` (via the terminal-success
        # contract), not from a regex over arbitrary output. Mirror that faithfully —
        # promote only the chain's asserted flag into a runtime flag so ``goal()`` sees
        # it and the loop reports solved. Trusting the chain's assertion (not scanning
        # all tool text) avoids the false-positive flags a blind regex would mint.
        # Track whether a win came from a chain's TERMINAL assertion (outcome.flag) vs
        # a flag that merely entered state incidentally (e.g. the verifier promoting a
        # runtime flag mid-chain). The old chain-order path treats only the terminal
        # assertion as an unconditional success (``_apply_terminal_success_contract``);
        # an incidental runtime flag routes through ``recovery.finalize`` →
        # wait_for_verification (NOT a success). ``goal()`` alone can't distinguish the
        # two (both are runtime-level), so 5b cut-3 records the provenance here.
        terminal_win: dict[str, Any] = {"asserted": False, "flag": ""}

        def _promote_chain_flag(chain_name: str, outcome) -> None:
            flag = str(getattr(outcome, "flag", "") or "").strip()
            if flag and self.state is not None:
                self.state.add_flag(
                    flag,
                    level="runtime",
                    evidence_source=chain_name or "blackboard_loop",
                    rationale=str(getattr(outcome, "reason", "") or "") or "blackboard chain win",
                    confidence=0.9,
                )
                terminal_win["asserted"] = True
                terminal_win["flag"] = flag

        # 5b cut-4 (missing-tool contract): a chain needing an uninstalled binary raises
        # ToolMissingError; ChainHands catches it and reports the names here so the
        # capability gap surfaces on the finished event (``result.missing_tools``), just
        # like the chain-order path's missing-tools recovery contract. The brain then
        # picks a different tool on its own — no code-forced reorder.
        def _record_missing_tools(missing: list[str]) -> None:
            if not missing:
                return
            result.missing_tools = list(
                dict.fromkeys(list(result.missing_tools) + list(missing))
            )
            self._emit(
                f"[CTF dispatcher] [blackboard] tool unavailable: {', '.join(missing)} "
                "— reported; brain to pick another"
            )

        # 5b cut-2 (observability): the loop is otherwise a black box live — surface the
        # brain's per-step decision trail (kind/tool/rationale + tool-result preview) both
        # to the progress stream (real-time) and into the notes log (so it persists into
        # ``result.notes`` / session events after the in-memory CTFState is gone). Without
        # this a failed solve is undiagnosable; it is the prerequisite to validating the
        # remaining 5b contract migrations against the new loop.
        def _on_step(step: int, action, result) -> None:
            kind = str(getattr(action, "kind", "") or "?")
            rationale = str(getattr(action, "rationale", "") or "").strip()
            if kind == "call_tool":
                tool = str(getattr(action, "tool", "") or "?")
                preview = str(result or "").replace("\n", " ").strip()[:160]
                detail = f"call_tool {tool} → {preview}"
            elif kind in ("write_fact", "declare_intent"):
                detail = f"{kind} — {str(getattr(action, 'content', '') or '').strip()[:160]}"
            else:
                detail = kind
            line = f"[CTF dispatcher] [blackboard] step {step}: {detail}"
            if rationale:
                line = f"{line}  ({rationale[:80]})"
            self._notes_log.append(line)
            self._emit(line)

        # 5b cut-5 (cross-run negative-feedback READ side → brain): the D1 loop's WRITE
        # side (strategy_memory record_failure / record_outcome / session entry) already
        # flows on this path via the shared _finalize + chain-internal writes; but the
        # brain flew BLIND to the recall — the board carried NO hints. Surface the
        # cross-run signals the chain-order planner already gets (llm_executor): payloads
        # that FAILED on similar past challenges (don't re-propose) + emergent tool-chains
        # that won / spun before. Advisory only (Hints, never removes a tool) — the brain
        # decides. Complements ATTEMPTS (this-run dead ends) with prior-run failures.
        # Byte-identical empty when memory is cold (both lists empty). A thunk so it
        # re-reads per projection (and sets the pattern for 曲库 hint injection later).
        def _cross_run_hints() -> list[str]:
            hints: list[str] = []
            for payload in list(self._known_failed_payloads or [])[:8]:
                text = str(payload or "").strip()
                if text:
                    hints.append(
                        f"AVOID — payload FAILED on similar past challenges, do not "
                        f"re-propose (try a materially different approach): {text}"
                    )
            chain_hints = self._emergent_chain_hints or {}
            for chain in list(chain_hints.get("reuse") or [])[:5]:
                text = str(chain or "").strip()
                if text:
                    hints.append(f"PREFER — this tool-chain led to a flag on a prior run: {text}")
            for chain in list(chain_hints.get("avoid") or [])[:5]:
                text = str(chain or "").strip()
                if text:
                    hints.append(f"AVOID — this tool-chain spun with no progress on prior runs: {text}")
            # 5b cut-7 (② 曲库正面注入): the POSITIVE half of cross-run recall. The
            # chain-order path reorders its chains by ant-colony pheromone — chains that
            # solved fingerprint-SIMILAR past challenges via short, re-confirmed paths
            # (coordinator._apply_chain_order_contract → recall_chain_pheromone, line
            # ~1454). The brain flew blind to that positive曲库 signal: cut-5 gave it only
            # the negatives (failed payloads / spun chains). Surface the top-weighted
            # winning chains as an advisory PREFER hint — the brain still chooses its own
            # tool, we do NOT reorder its list ([[feedback_less_is_more_dont_cage_llm]]).
            # Fail-safe + byte-identical empty when memory is cold or no fingerprint was
            # built (guards mirror the chain-order path's own guard).
            fingerprint = getattr(self, "_current_fingerprint", None)
            if fingerprint is not None:
                try:
                    pheromone = self.strategy_memory.recall_chain_pheromone(fingerprint)
                except Exception:
                    pheromone = {}
                top = sorted(
                    (
                        (str(chain).strip(), float(strength))
                        for chain, strength in (pheromone or {}).items()
                        if str(chain).strip() and float(strength) > 0.0
                    ),
                    key=lambda item: item[1],
                    reverse=True,
                )[:5]
                for chain, strength in top:
                    hints.append(
                        f"PREFER — this chain solved SIMILAR past challenges "
                        f"(pheromone {strength:.2f}, higher = more/shorter prior wins): {chain}"
                    )
            return hints

        # Cost boundary, not a scripted step count: reuse the EXPLOIT phase round
        # budget (profile override, else the module default) — §3.2 不把大模型关进笼子.
        budget_steps = self.state.effective_phase_budget(Phase.EXPLOIT) or 24
        outcome = await run_blackboard_solve(
            brain=LLMBrain.from_llm(self.llm),
            hands=ChainHands(
                self,
                context=context,
                on_outcome=_promote_chain_flag,
                on_missing_tools=_record_missing_tools,
            ),
            tools=chain_tools(self, context=context),
            budget=Budget(max_steps=int(budget_steps)),
            on_step=_on_step,
            **bind_seams(self.state, hints=_cross_run_hints),
        )
        self._emit(
            f"[CTF dispatcher] [blackboard] done: stopped={outcome.stopped} "
            f"steps={outcome.steps} solved={outcome.solved}"
        )
        # Record the chains the brain actually invoked BEFORE the terminal mapping, so
        # ``recovery.finalize`` (below) sees the real used-chain list — the same input
        # the chain-order path feeds it.
        used = [
            obs.source
            for obs in self.state.observations
            if obs.kind == "tool_result" and obs.source
        ]
        if used:
            result.chain_used = list(dict.fromkeys(used))
        # 5b cut-3 (terminal flag-contract migration): map the loop's outcome onto the
        # SAME terminal contracts the chain-order path uses, so the new driver never
        # over-claims an unverified flag as success nor silently drops a near-solve.
        #   • terminal-asserted flag → clean success (cut-1, preserved).
        #   • verifier-confirmed VERIFIED flag → clean success (a real win w/o a chain
        #     assertion).
        #   • otherwise delegate the give-up to ``recovery.finalize`` — the identical
        #     terminal contract the chain-order path runs — so wait_for_verification
        #     (runtime-but-unverified), stop_candidate_only (source-only), blocked-surface
        #     and repertoire_miss are all handled the same way. This SUPERSEDES the
        #     manual ④ miss-marking (finalize sets repertoire_miss via the shared
        #     predicate) and additionally surfaces the runtime/candidate flag so a
        #     near-solve is reported, not dropped.
        best_verified = _best_flag_record(self.state.verified_flags)
        if outcome.solved and terminal_win["asserted"]:
            result.success = True
            result.flag = outcome.flag or terminal_win["flag"]
            result.reason = f"blackboard_loop:{outcome.stopped}"
        elif best_verified is not None:
            result.success = True
            result.flag = best_verified.value
            result.reason = "blackboard_loop:verified"
        else:
            result.success = False
            decision = self.recovery_controller.finalize(
                self.state,
                used_chains=list(result.chain_used),
                no_progress_count=0,
            )
            # Surface the strongest near-solve flag (runtime outranks candidate) so a
            # wait_for_verification / candidate-only stop reports the value instead of
            # dropping it — mirrors the chain-order recovery decision carrying it.
            near = _best_flag_record(self.state.runtime_flags) or _best_flag_record(
                self.state.candidate_flags
            )
            result.flag = near.value if near is not None else None
            result.reason = f"blackboard_loop:{outcome.stopped}|{decision.reason}"
            self._emit(f"[CTF dispatcher] [blackboard] terminal: {decision.reason}")
        # 5b cut-6 (wrong-flag contract): prune RECOVERABLE (source-only) wrong-flag
        # feedback before finalize. The chain-order path drops these per-iteration in
        # ``_apply_wrong_flag_early_stop_contract``'s recoverable branch (a source-only
        # rejected guess is not a real wrong submission); the blackboard loop never runs
        # that contract, so a lingering recoverable entry would make the shared _finalize
        # both mislabel the run "wrong flag feedback" AND wrongly penalize the reused
        # strategy_memory entries (apply_rejected_feedback) for a mere unverified guess.
        # NON-recoverable (hard-rejected) feedback is kept — its wrong-flag stop + memory
        # penalty are correct. We do NOT force an early stop: continuation is the brain's
        # call ([[feedback_less_is_more_dont_cage_llm]]).
        recoverable = [
            item
            for item in self._pending_wrong_flag_feedback
            if str(item.get("recoverable") or "").strip().lower() == "true"
        ]
        if recoverable:
            self._pending_wrong_flag_feedback = [
                item
                for item in self._pending_wrong_flag_feedback
                if str(item.get("recoverable") or "").strip().lower() != "true"
            ]
            for item in recoverable:
                self.state.meta_reasonings.append(
                    {
                        "type": "recoverable_wrong_flag_continued",
                        "flag": str(item.get("flag") or "").strip(),
                        "rationale": str(item.get("rationale") or "").strip(),
                        "evidence_source": str(item.get("evidence_source") or "").strip(),
                        "chain_name": "blackboard_loop",
                    }
                )
        return await self._finalize_solve_result(result)

    async def _finalize_solve_result(self, result: SolveResult) -> SolveResult:
        result.notes = list(self._notes_log)
        if self.state is None:
            finished_event = build_task_finished_event(
                success=result.success,
                flag=result.flag or "",
                reason=result.reason or "",
                chain_used=list(result.chain_used),
                missing_tools=list(result.missing_tools),
            )
            self._record_session_event(
                str(finished_event.get("event_type") or "task_finished"),
                dict(finished_event.get("payload") or {}),
            )
            await self._stop_failover_monitor_if_owned()
            return result

        if not result.success and self._pending_wrong_flag_feedback:
            latest_wrong = self._pending_wrong_flag_feedback[-1]
            previous_reason = str(result.reason or self.state.stop_reason or "").strip()
            result.reason = f"wrong flag feedback: {latest_wrong.get('flag', '')}"
            if previous_reason and "wrong flag feedback" not in previous_reason.lower():
                result.reason += f" | previous={previous_reason}"

        reason = result.reason or self.state.stop_reason or ""
        self.state.stop_reason = reason
        if not self.state.retrospectives and reason:
            self.reasoning_layer.record_retrospective(
                self.state,
                trigger="stop",
                reason=reason,
            )

        missing_capabilities = list(result.missing_tools)

        if self._current_fingerprint is None:
            self._current_fingerprint = self.strategy_memory.build_fingerprint(self.state)
        entry = self.strategy_memory.build_entry(
            state=self.state,
            fingerprint=self._current_fingerprint,
            chain_used=result.chain_used,
            solved=result.success,
        )
        await self.strategy_memory.save(entry)
        self.state.meta_reasonings.append(
            {
                "type": "strategy_memory_session_entry",
                "entry_id": entry.id,
                "solved": result.success,
                "chain_used": list(result.chain_used),
            }
        )
        skip_standard_outcome_update = False
        if not result.success and self._pending_wrong_flag_feedback:
            latest_wrong = self._pending_wrong_flag_feedback[-1]
            wrong_audit = await self.strategy_memory.apply_rejected_feedback(
                self._memory_match_ids,
                session_entry_id=entry.id,
            )
            skip_standard_outcome_update = True
            self.state.meta_reasonings.append(
                {
                    "type": "strategy_memory_wrong_flag_audit",
                    "wrong_flag": latest_wrong.get("flag"),
                    "rationale": latest_wrong.get("rationale"),
                    "matched_entry_ids": list(self._memory_match_ids),
                    **wrong_audit,
                }
            )
        if self._memory_match_ids and not skip_standard_outcome_update:
            updated_entries = await self.strategy_memory.record_outcome(
                self._memory_match_ids,
                solved=result.success,
            )
            updated_entries = updated_entries or []
            suggested_mute_entry_ids = [
                entry.id
                for entry in updated_entries
                if (
                    not result.success
                    and entry.metadata.manual_status == "active"
                )
            ]
            auto_muted_entry_ids = [
                entry.id
                for entry in updated_entries
                if entry.metadata.manual_status == "muted"
            ]
            rollback_candidate_entry_ids = [
                entry.id
                for entry in updated_entries
                if result.success and entry.metadata.manual_status == "active"
            ]
            self.state.meta_reasonings.append(
                {
                    "type": "strategy_memory_outcome_audit",
                    "matched_entry_ids": list(self._memory_match_ids),
                    "solved": result.success,
                    "entries": [
                        {
                            "id": entry.id,
                            "manual_status": entry.metadata.manual_status,
                            "applied_count": entry.metadata.applied_count,
                            "successful_applications": entry.metadata.successful_applications,
                            "failed_applications": entry.metadata.failed_applications,
                            "success_correlation": entry.metadata.success_correlation,
                        }
                        for entry in updated_entries
                    ],
                    "suggested_mute_entry_ids": suggested_mute_entry_ids,
                    "auto_muted_entry_ids": auto_muted_entry_ids,
                    "rollback_candidate_entry_ids": rollback_candidate_entry_ids,
                }
            )
        stop_report = self.reasoning_layer.generate_stop_report(
            self.state,
            reason=reason,
            missing_capabilities=missing_capabilities,
        )
        self.state.stop_report = stop_report.to_dict()
        finished_event = build_task_finished_event(
            success=result.success,
            flag=result.flag or "",
            reason=reason,
            chain_used=list(result.chain_used),
            missing_tools=list(result.missing_tools),
        )
        finished_checkpoint_payload = dict(finished_event.get("payload") or {})
        rejected_flags = [
            str(record.value).strip()
            for record in list(self.state.rejected_flags)
            if str(record.value).strip()
        ]
        if rejected_flags:
            finished_checkpoint_payload["rejected_flags"] = rejected_flags
        self._record_session_event(
            str(finished_event.get("event_type") or "task_finished"),
            dict(finished_event.get("payload") or {}),
        )
        self._write_checkpoint(
            "task_finished",
            finished_checkpoint_payload,
        )
        await self._stop_failover_monitor_if_owned()
        try:
            export_ctf_session_retrospective(self.state, result)
        except Exception:
            pass
        return result

    async def _start_failover_monitor_if_available(self) -> None:
        if self._failover_monitor is not None:
            return
        try:
            import flaghunter.cpa_modules.m1_api_hub as m1_api_hub  # noqa: PLC0415

            if not m1_api_hub.is_m1_enabled():
                return
            try:
                self._failover_monitor = m1_api_hub.get_failover_monitor()
                self._failover_monitor_owned = False
                return
            except Exception:
                pass

            try:
                await m1_api_hub.init_m1()
            except Exception:
                self._failover_monitor = None
                self._failover_monitor_owned = False
                return

            try:
                self._failover_monitor = m1_api_hub.get_failover_monitor()
                self._failover_monitor_owned = self._failover_monitor is not None
            except Exception:
                self._failover_monitor = None
                self._failover_monitor_owned = False
        except Exception:
            self._failover_monitor = None
            self._failover_monitor_owned = False

    async def _stop_failover_monitor_if_owned(self) -> None:
        monitor = self._failover_monitor
        owned = self._failover_monitor_owned
        self._failover_monitor = None
        self._failover_monitor_owned = False
        if not owned or monitor is None:
            return
        stop = getattr(monitor, "stop", None)
        if stop is None:
            return
        try:
            result = stop()
            if hasattr(result, "__await__"):
                await result
        except Exception:
            return

    def _select_primary_strategy(
        self,
        chain_name: str,
        *,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ):
        strategies = self._strategies_for_chain(
            chain_name,
            target=target,
            page_features=page_features,
            hint=hint,
            extras={"base_target": _base_target(target)},
        )
        if chain_name == "web":
            normalized_hint = str(hint or "")
            structured_next_action = self._structured_followup_next_action()
            structured_switched_from = self._structured_followup_value("switchedFrom").lower()
            structured_trigger_reason = self._structured_followup_value("triggerReason").lower()
            structured_trigger_action_driver = self._structured_followup_value("triggerActionDriver").lower()
            if (
                (
                    "nextAction=exploit_identified_engine" in normalized_hint
                    or structured_next_action == "exploit_identified_engine"
                    or (
                        (
                            structured_switched_from == "probe_discovered_endpoint"
                            or structured_trigger_action_driver == "blackboard.discovered_endpoint"
                        )
                        and (
                            "template engine" in structured_trigger_reason
                            or "identified engine" in structured_trigger_reason
                            or "engine primitive" in structured_trigger_reason
                        )
                    )
                )
                and self.state is not None
                and any(
                    str(getattr(observation, "kind", "") or "").strip() == "ssti_engine_identified"
                    for observation in list(self.state.observations)
                )
            ):
                for strategy in strategies:
                    if str(getattr(strategy, "kind", "") or "").strip() == "ssti_exploit":
                        return strategy
            if (
                (
                    "nextAction=validate_leaked_secret" in normalized_hint
                    or structured_next_action == "validate_leaked_secret"
                    or (
                        (
                            structured_switched_from == "probe_discovered_endpoint"
                            or structured_trigger_action_driver in {
                                "blackboard.discovered_endpoint",
                                "blackboard.leaked_secret",
                            }
                        )
                        and (
                            "cookie secret" in structured_trigger_reason
                            or "guarded file" in structured_trigger_reason
                            or "filehash" in structured_trigger_reason
                            or structured_trigger_action_driver == "blackboard.leaked_secret"
                        )
                    )
                )
                and self.state is not None
                and any(
                    str(getattr(observation, "kind", "") or "").strip() == "cookie_secret_leaked"
                    for observation in list(self.state.observations)
                )
            ):
                for strategy in strategies:
                    if str(getattr(strategy, "kind", "") or "").strip() == "hash_guarded_file_read":
                        return strategy
            if (
                (
                    structured_next_action == "collect_initial_facts"
                    or structured_switched_from == "probe_discovered_endpoint"
                    or structured_trigger_action_driver == "blackboard.discovered_endpoint"
                )
                and (
                    "source leak" in structured_trigger_reason
                    or "backup" in structured_trigger_reason
                    or "artifact" in structured_trigger_reason
                    or "source archive" in structured_trigger_reason
                    or "zip" in structured_trigger_reason
                    or "source bundle" in structured_trigger_reason
                )
            ):
                for strategy in strategies:
                    if str(getattr(strategy, "kind", "") or "").strip() == "backup_source_leak":
                        return strategy
            if (
                (
                    structured_next_action == "collect_initial_facts"
                    or structured_switched_from == "probe_discovered_endpoint"
                    or structured_trigger_action_driver == "blackboard.discovered_endpoint"
                )
                and (
                    "unserialize" in structured_trigger_reason
                    or "magic method" in structured_trigger_reason
                    or "__destruct" in structured_trigger_reason
                    or "deserial" in structured_trigger_reason
                )
            ):
                for strategy in strategies:
                    if str(getattr(strategy, "kind", "") or "").strip() == "php_unserialize_magic_method":
                        return strategy
            if self._recent_php_unserialize_source_exploit():
                for strategy in strategies:
                    if str(getattr(strategy, "kind", "") or "").strip() == "php_unserialize_magic_method":
                        return strategy
            source_hint_text = self._recent_local_source_hint_text().lower()
            if "filename" in source_hint_text and "filehash" in source_hint_text:
                for strategy in strategies:
                    if str(getattr(strategy, "kind", "") or "").strip() == "hash_guarded_file_read":
                        return strategy
        if chain_name == "web" and self._has_recent_local_source_hint():
            for strategy in strategies:
                if str(getattr(strategy, "kind", "") or "").strip() == "backup_source_leak":
                    return strategy
        return strategies[0] if strategies else None

    def _extract_followup_fetch_targets(self, text: str) -> list[str]:
        blob = str(text or "")
        if not blob:
            return []

        targets: list[str] = []
        seen: set[str] = set()

        def _append(value: str) -> None:
            normalized = str(value or "").strip().rstrip(".,;:!?)\"]'")
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            targets.append(normalized)

        loopback_urls = re.findall(
            r"https?://(?:127\.0\.0\.1|localhost)[^\s\"'<>]+",
            blob,
            flags=re.IGNORECASE,
        )
        for url in loopback_urls:
            _append(url)

        allowed_prefixes = (
            "/app/",
            "/etc/",
            "/flag",
            "/home/",
            "/opt/",
            "/proc/",
            "/run/",
            "/sandbox/",
            "/srv/",
            "/tmp/",
            "/usr/",
            "/var/",
        )
        for raw_path in re.findall(r"(?<![A-Za-z0-9_])(/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]{1,160})", blob):
            path = str(raw_path or "").strip().rstrip(".,;:!?)\"]'")
            if not path or path in _HTML_TAG_PSEUDO_PATHS:
                continue
            leaf = path.rsplit("/", 1)[-1]
            if not (
                path == "/flag"
                or path == "/flag.txt"
                or path.startswith(allowed_prefixes)
                or "." in leaf
            ):
                continue
            _append(f"file://{path}")

        return targets

    def _jwt_target_candidates(self, base: str, page_features: dict[str, Any]) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def _add(url: str) -> None:
            normalized = str(url or "").strip()
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            candidates.append(normalized)

        route_candidates: set[str] = set()
        route_candidates.update(
            str(item).strip()
            for item in (page_features.get("endpoints") or [])
            if str(item).strip()
        )
        route_candidates.update(
            str(item).strip()
            for item in (page_features.get("raw_links") or [])
            if str(item).strip()
        )
        route_candidates.update(self._recent_local_source_hint_routes())

        protected_tokens = ("/api/admin", "/dashboard", "/admin", "/flag", "/profile")
        for route in route_candidates:
            lowered = route.lower()
            if any(token in lowered for token in protected_tokens):
                _add(urljoin(base.rstrip("/") + "/", route.lstrip("/")))

        _add(base)
        return candidates

    def _primary_capability_for_chain(self, chain_name: str) -> str | None:
        if chain_name == "web":
            source_hint_text = self._recent_local_source_hint_text().lower()
            if "index.php" in source_hint_text and "unserialize" in source_hint_text:
                return "php_deserialization_test"
            if any(
                token in source_hint_text
                for token in ("app.py", "@app.route", "/admin", "/login", "flask(")
            ):
                return "http_request_basic"
        mapping = {
            "sqli": "sql_injection_test",
            "xss": "callback_listener",
            "web": "source_download",
            "jwt": "jwt_testing",
            "lfi": "http_request_basic",
            "cmdi": "http_request_basic",
            "ssrf": "http_request_basic",
            "upload": "http_request_basic",
        }
        return mapping.get(chain_name)

    # Web-framework signatures: (name, cookie markers, header markers, body markers).
    # Recon fingerprints the framework so the agent recognises e.g. a Laravel app
    # from its laravel_session cookie instead of treating it as a blank web target.
    _FRAMEWORK_SIGNATURES = (
        ("laravel", ("laravel_session",), (), ()),
        ("thinkphp", ("think_lang", "thinkphp"), (), ("thinkphp", "think\\app")),
        ("django", ("csrftoken", "sessionid"), (), ("csrfmiddlewaretoken",)),
        ("wordpress", ("wordpress_", "wp-settings"), (), ("wp-content", "wp-includes")),
        ("rails", ("_session_id",), (), ()),
        ("express", ("connect.sid",), ("express",), ()),
        ("spring", ("jsessionid",), (), ()),
        ("flask", (), ("werkzeug",), ()),
    )

    # Conventional high-value entry routes per framework. Seeded into the
    # exploration agenda whenever the framework is fingerprinted, so recon stays
    # robust even when the landing page links nothing scrapable (SPA, a
    # redirect-to-login, or a transient empty/booting body). The cookies/headers
    # that drive _fingerprint_framework arrive reliably even when the body does
    # not, so keying route seeding off the fingerprint keeps the agent on the
    # app's real entry points instead of degrading to blind backup/dotfile
    # guessing.
    _FRAMEWORK_CONVENTIONAL_ROUTES: dict[str, tuple[str, ...]] = {
        "laravel": ("/login", "/register", "/home", "/api"),
        "thinkphp": ("/index.php", "/admin", "/public"),
        "django": ("/admin/", "/login", "/api"),
        "wordpress": ("/wp-login.php", "/wp-admin/", "/wp-json"),
        "rails": ("/login", "/users/sign_in"),
        "express": ("/login", "/api", "/admin"),
        "spring": ("/login", "/actuator", "/swagger-ui.html"),
        "flask": ("/login", "/admin"),
    }

    def _fingerprint_framework(self, features: dict[str, Any]) -> str | None:
        """Record a ``framework_detected`` observation from recon signals.

        Matches cookie names / response headers / body markers against known web
        frameworks (Laravel, ThinkPHP, Django, WordPress, …). Returns the detected
        framework name, or None. Idempotent per framework.
        """
        if self.state is None:
            return None
        cookies = str(features.get("cookies") or "").lower()
        headers = features.get("headers") if isinstance(features.get("headers"), dict) else {}
        header_blob = " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
        body = f"{features.get('html', '')}\n{features.get('content', '')}".lower()
        for name, cookie_sigs, header_sigs, body_sigs in self._FRAMEWORK_SIGNATURES:
            cookie_hit = next((sig for sig in cookie_sigs if sig in cookies), None)
            header_hit = next((sig for sig in header_sigs if sig in header_blob), None)
            body_hit = next((sig for sig in body_sigs if sig in body), None)
            evidence = cookie_hit or header_hit or body_hit
            if not evidence:
                continue
            already = any(
                str(getattr(o, "kind", "")) == "framework_detected"
                and str(getattr(o, "value", "")) == name
                for o in self.state.observations
            )
            if not already:
                self.state.add_observation(
                    "framework_detected",
                    name,
                    source="phase_recon",
                    metadata={
                        "evidence": str(evidence),
                        "signal": "cookie" if cookie_hit else ("header" if header_hit else "body"),
                    },
                )
            return name
        return None

    async def _proxy_get_with_retry(
        self,
        url: str,
        *,
        attempts: int = 3,
        timeout: int = 10,
        audit_target: str = "",
        audit_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET via proxy_action, retrying transient boot/unavailable responses.

        CTF target instances are frequently mid-boot for the first seconds and
        return 5xx ("Target unavailable") or a tiny placeholder body. Accepting
        that as the page leaves recon with no links/forms → empty agenda → the
        agent gives up. Retry a few times with a short backoff and return the
        first usable response (2xx/3xx/4xx with a non-trivial body); otherwise the
        last response seen.
        """
        last: dict[str, Any] = {}
        for attempt in range(max(1, attempts)):
            page = await self._runtime_proxy_action(
                "get",
                url=url,
                timeout=timeout,
                audit_target=audit_target or url,
                audit_metadata=audit_metadata,
            )
            last = page if isinstance(page, dict) else {}
            if isinstance(page, dict) and not page.get("error"):
                status = int(page.get("status_code") or 0)
                body = str(page.get("body") or "")
                if status and status < 500 and len(body) >= 200:
                    return page
            if attempt < attempts - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
        return last

    @staticmethod
    def _is_legacy_browser_runtime_probe(probe: Any) -> bool:
        if not isinstance(probe, dict):
            return False
        error = str(probe.get("error") or "").strip().lower()
        if not error:
            return False
        return "unexpected action: diagnose" in error or "unexpected browser action: diagnose" in error

    async def _execute_chain(
        self,
        *,
        chain_name: str,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        chain_handlers = self._chain_handler_map(
            target=target,
            page_features=page_features,
            hint=hint,
        )
        handler = chain_handlers.get(chain_name, self._default_chain_handler(target=target))
        outcome = await handler()

        if (
            not outcome.flag
            and not outcome.progress
            and self.llm is not None
            and self.state is not None
            and self.state.is_llm_exploration_allowed()
        ):
            fallback = await self._run_llm_driven_exploration(
                self._strategy_context(
                    target=target,
                    page_features=page_features,
                    hint=hint,
                    extras={"chain_name": chain_name},
                )
            )
            if fallback.progress or fallback.flag:
                return fallback
        return outcome

    def _chain_handler_map(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> dict[str, Callable[[], Awaitable[_ChainOutcome]]]:
        return {
            "xss": lambda: self._execute_xss_route(target, page_features, hint),
            "web": lambda: self._execute_web_route(target, page_features, hint),
            "misc": lambda: self._execute_misc_chain(target, page_features, hint),
            "sqli": lambda: self._execute_sqli_chain(target, page_features, hint),
            "jwt": lambda: self._execute_jwt_chain(target, page_features),
            "lfi": lambda: self._execute_lfi_chain(target),
            "cmdi": lambda: self._attempt_generic_param_cmdi(target, page_features),
            "ssrf": lambda: self._attempt_generic_param_ssrf(target, page_features),
            "upload": lambda: self._execute_upload_chain(target, page_features, hint),
        }

    def _default_chain_handler(
        self,
        *,
        target: str,
    ) -> Callable[[], Awaitable[_ChainOutcome]]:
        return lambda: self._execute_terminal_commands(
            target,
            [
                f'curl -s "{target}"',
                f'curl -s "{urljoin(target if target.endswith("/") else target + "/", "robots.txt")}"',
            ],
        )

    async def _submit_form_request(
        self,
        target: str,
        form: dict[str, Any],
        fields: dict[str, str],
    ) -> tuple[dict[str, Any], str]:
        method = str(form.get("method") or "GET").upper()
        action = str(form.get("action") or "").strip()
        if not action:
            action = target
        action_url = urljoin(target if target.endswith("/") else target + "/", action)

        if method == "GET":
            request_url = _with_query(action_url, fields)
            response = await self._runtime_proxy_action(
                "request",
                method="GET",
                url=request_url,
                timeout=20,
                audit_target=request_url,
                audit_metadata={"phase": "submit_form_request", "method": "GET"},
            )
            return response, request_url

        response = await self._runtime_proxy_action(
            "request",
            method="POST",
            url=action_url,
            data=fields,
            timeout=20,
            audit_target=action_url,
            audit_metadata={"phase": "submit_form_request", "method": "POST"},
        )
        return response, action_url

    async def _execute_terminal_commands(
        self,
        target: str,
        commands: list[str],
    ) -> _ChainOutcome:
        self.tool_guard.require(["terminal"])
        progress = False
        for command in commands:
            result = await self._runtime_execute_command(
                command,
                timeout=180,
                audit_target=target,
                audit_metadata={"phase": "terminal_commands"},
            )
            text = "\n".join(
                part for part in [getattr(result, "stdout", ""), getattr(result, "stderr", "")] if part
            )
            if text:
                progress = True
            await self._scan_and_store(text, target, evidence_source="command-output")
            if flag := self._extract_flag(text):
                verification = await self._observe_flag(
                    flag,
                    target,
                    evidence_source="command-output",
                    rationale=f"command hit: {command}",
                )
                if verification.decision == "verified":
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason=f"command hit: {command}",
                    )
        return _ChainOutcome(progress=progress, reason="commands exhausted")

    async def _scan_and_store(
        self,
        text: str,
        target: str,
        *,
        evidence_source: str = "runtime-output",
        page_features: dict[str, Any] | None = None,
    ) -> None:
        if not text:
            return
        if evidence_source == "source-leak":
            self._register_runtime_source_hint(
                text,
                target,
                evidence_source=evidence_source,
            )
        discovered_links = self._extract_embedded_links(text, target)
        target_lower = str(target or "").strip().lower()
        if target and any(token in target_lower for token in ("?file=", "&file=", "?path=", "&path=", "filename=", "/hints.txt", "/welcome.txt", "/flag.txt")):
            discovered_links = [str(target).strip(), *discovered_links]
        if discovered_links:
            self._ingest_discovered_links(
                discovered_links,
                page_features=page_features,
                discovery_source=evidence_source,
            )
        if flag := self._extract_runtime_flag(text):
            await self._observe_flag(
                flag,
                target,
                evidence_source=evidence_source,
                rationale=f"observed during {evidence_source}",
            )
        sid = _extract_sid_from_text(text)
        if sid:
            await self._store_secret_note("sid", sid, target)

    def _extract_embedded_links(self, text: str, base_url: str) -> list[str]:
        raw_links: list[str] = []
        seen: set[str] = set()
        blob = str(text or "")

        def _append(candidate: str) -> None:
            normalized_candidate = candidate.strip()
            if normalized_candidate.startswith("?"):
                absolute = urljoin(_base_target(base_url) + "/", normalized_candidate)
            else:
                absolute = _join_relative_url(str(base_url or ""), normalized_candidate)
            absolute = _normalize_exploration_url(absolute)
            if (
                not absolute
                or absolute in seen
                or self._should_ignore_exploration_candidate(absolute, base_url=base_url)
            ):
                return
            seen.add(absolute)
            raw_links.append(absolute)

        for href in re.findall(r'href=["\']([^"\'<>]+)["\']', blob, re.IGNORECASE):
            href = href.strip()
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                _append(href)
        for action in re.findall(r'action=["\']([^"\'<>]+)["\']', blob, re.IGNORECASE):
            action = action.strip()
            if action and not action.startswith(("#", "javascript:", "mailto:")):
                _append(action)
        for comment in re.findall(r"<!--(.*?)-->", blob, flags=re.IGNORECASE | re.DOTALL):
            for candidate in re.findall(
                r"(?<![\w/.-])([A-Za-z0-9_.-]+\.(?:php|phps|inc|txt|bak))(?![\w.-])",
                comment,
                flags=re.IGNORECASE,
            ):
                _append(candidate)
        for candidate in re.findall(
            r"(?<![\w/.-])((?:source|hint|flag|welcome|index)\.(?:php|phps|inc|txt|bak))(?![\w.-])",
            blob,
            flags=re.IGNORECASE,
        ):
            _append(candidate)
        for query in re.findall(
            r'(\?(?:[A-Za-z0-9_.-]+=[^"\'<>\s&]+)(?:&[A-Za-z0-9_.-]+=[^"\'<>\s&]+)*)',
            blob,
            re.IGNORECASE,
        ):
            lowered = query.lower()
            if any(token in lowered for token in ("file=", "path=", "filename=", "page=", "include=")):
                _append(query)
        return raw_links

    def _ingest_discovered_links(
        self,
        links: list[str],
        *,
        page_features: dict[str, Any] | None,
        discovery_source: str,
    ) -> None:
        if not links:
            return

        raw_links = list(page_features.get("raw_links") or []) if page_features is not None else []
        endpoints = list(page_features.get("endpoints") or []) if page_features is not None else []
        base_url = (
            str((page_features or {}).get("url") or "")
            or str(getattr(self.state, "target", "") or "")
        )

        for link in links:
            absolute = _normalize_exploration_url(str(link or "").strip())
            if not absolute or self._should_ignore_exploration_candidate(absolute, base_url=base_url):
                continue
            parsed = urlparse(absolute)
            lowered = absolute.lower()
            web_subtypes: list[str] = []
            if any(token in lowered for token in ("?file=", "&file=", "?path=", "&path=", "filename=")):
                web_subtypes.append("file_endpoint")
            if "filehash=" in lowered and "filename=" in lowered:
                web_subtypes.append("file_hash_guard")
            if any(token in lowered for token in ("/hints.txt", "/welcome.txt", "/flag.txt")):
                web_subtypes.append("hint_file")

            if page_features is not None and absolute not in raw_links:
                raw_links.append(absolute)
            if page_features is not None and parsed.path and parsed.path not in endpoints:
                endpoints.append(parsed.path)

            if self.state is None:
                continue

            metadata = {
                "url": absolute,
                "discovery_source": discovery_source,
            }
            if web_subtypes:
                metadata["web_subtype"] = web_subtypes
            self.state.add_observation(
                "derived_link",
                absolute,
                source="secondary_content",
                metadata=metadata,
            )
            self.state.add_exploration_item(
                absolute,
                discovery_source="secondary_content",
                hint_strength=self._classify_exploration_hint_strength(absolute, "secondary_content"),
            )

        if page_features is not None:
            page_features["raw_links"] = raw_links
            page_features["endpoints"] = sorted(set(endpoints))

    def _should_ignore_exploration_candidate(
        self,
        candidate: str,
        *,
        base_url: str | None = None,
    ) -> bool:
        text = str(candidate or "").strip()
        if not text:
            return True
        lowered = text.lower()
        if lowered.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            return True

        parsed = urlparse(text)
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            return True

        # Normalise default ports so http://host and http://host:80 (and https/:443)
        # compare equal — otherwise a target given as http://host:80 makes every
        # same-host link (written without :80 in the HTML) look cross-host and get
        # ignored, leaving the exploration agenda empty.
        def _norm_host(netloc: str, scheme: str) -> str:
            netloc = str(netloc or "").lower()
            if scheme == "http" and netloc.endswith(":80"):
                netloc = netloc[:-3]
            elif scheme == "https" and netloc.endswith(":443"):
                netloc = netloc[:-4]
            return netloc

        base_parsed = urlparse(str(base_url or ""))
        base_host = _norm_host(base_parsed.netloc, base_parsed.scheme or "http")
        current_host = _norm_host(parsed.netloc, parsed.scheme or base_parsed.scheme or "http")
        if base_host and current_host and current_host != base_host:
            return True

        path = (parsed.path or text).strip()
        normalized_path = path.lower().rstrip("/")
        if normalized_path in _HTML_TAG_PSEUDO_PATHS:
            return True

        if normalized_path.endswith(_STATIC_RESOURCE_SUFFIXES):
            return True

        leaf = normalized_path.rsplit("/", 1)[-1]
        if (
            text.startswith("/")
            and "." in leaf
            and not leaf.endswith(_SERVER_SIDE_PATH_SUFFIXES)
            and re.fullmatch(r"[a-z0-9-]+\.[a-z]{2,8}", leaf)
        ):
            return True

        return False

    def _classify_exploration_hint_strength(
        self,
        candidate: str,
        discovery_source: str,
    ) -> int:
        text = str(candidate or "").strip()
        lowered = text.lower()
        parsed = urlparse(text)
        path_only = parsed.path or text
        if "filename=" in lowered and "filehash=" in lowered:
            return 1
        if any(token in lowered for token in ("?file=", "&file=", "?path=", "&path=", "php://filter")):
            return 1
        if any(token in lowered for token in ("/hints.txt", "/welcome.txt", "/flag.txt")):
            return 1
        if any(token in lowered for token in ("/file?", "/read?", "/download?")):
            return 2
        if any(token in lowered for token in ("/file", "/flag", "/hint", "/welcome", "/secret")):
            return 2
        if discovery_source == "link_href" and path_only not in {"", "/"}:
            return 2
        return 3

    def _build_file_wrapper_urls(self, candidate_url: str) -> list[str]:
        parsed = urlparse(str(candidate_url or "").strip())
        params = parse_qs(parsed.query, keep_blank_values=True)
        if not params:
            return []

        wrapper_urls: list[str] = []
        seen: set[str] = set()
        wrapper_param_names = {"file", "path", "filename", "page", "include"}
        candidate_resources = self._collect_candidate_include_resources(params)
        wrapper_prefixes = (
            "php://filter/convert.base64-encode/resource=",
            "php://filter/read=convert.base64-encode/resource=",
        )

        for param_name, values in params.items():
            if param_name.lower() not in wrapper_param_names:
                continue
            for resource in candidate_resources:
                normalized_resource = str(resource or "").strip().lstrip("/")
                if not normalized_resource:
                    continue
                for prefix in wrapper_prefixes:
                    mutated_params = dict(params)
                    mutated_params[param_name] = [prefix + normalized_resource]
                    mutated_url = parsed._replace(query=urlencode(mutated_params, doseq=True)).geturl()
                    if mutated_url not in seen:
                        seen.add(mutated_url)
                        wrapper_urls.append(mutated_url)
        return wrapper_urls

    def _collect_candidate_include_resources(self, params: dict[str, list[str]]) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()
        for values in params.values():
            for value in values:
                normalized = str(value or "").strip()
                if not normalized:
                    continue
                if normalized.startswith("php://"):
                    continue
                stripped = normalized.lstrip("/")
                if stripped and stripped not in seen:
                    seen.add(stripped)
                    candidates.append(stripped)

        for candidate in self._collect_candidate_filenames():
            normalized = str(candidate or "").strip().lstrip("/")
            if normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)
        return candidates

    def _decode_base64_source_blob(self, text: str) -> str | None:
        blob = str(text or "").replace("\\r\\n", "\n").replace("\\n", "\n")
        candidate_tokens = re.findall(r"[A-Za-z0-9+/=]{24,}", blob)
        if not candidate_tokens:
            compact = re.sub(r"\s+", "", blob)
            if re.fullmatch(r"[A-Za-z0-9+/=]{24,}", compact):
                candidate_tokens = [compact]

        for compact in candidate_tokens:
            if len(compact) % 4 != 0:
                continue
            try:
                decoded = base64.b64decode(compact, validate=True).decode("utf-8", errors="ignore")
            except Exception:
                continue
            if not decoded:
                continue
            lowered = decoded.lower()
            printable_ratio = sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t") / max(len(decoded), 1)
            if printable_ratio < 0.8:
                continue
            if any(marker in lowered for marker in ("<?php", "flag{", "include", "require", "$_")):
                return decoded
        return None

    def _apply_submit_profile(self, submit_profile: dict[str, Any] | None) -> None:
        if self.state is None:
            return
        profile = dict(submit_profile or {})
        if not profile:
            return
        if profile.get("endpoint"):
            self.state.submit_endpoint = str(profile.get("endpoint") or "").strip() or None
        if profile.get("success_pattern"):
            self.state.submit_success_pattern = str(profile.get("success_pattern") or "").strip() or None
        if profile.get("failure_pattern"):
            self.state.submit_failure_pattern = str(profile.get("failure_pattern") or "").strip() or None
        if profile.get("platform_type"):
            self.state.submit_platform_type = str(profile.get("platform_type") or "").strip() or None
        if profile.get("challenge_id"):
            self.state.submit_challenge_id = str(profile.get("challenge_id") or "").strip() or None
        if profile.get("base_url"):
            self.state.submit_base_url = str(profile.get("base_url") or "").strip() or None
        if profile.get("api_key"):
            self.state.submit_api_key = str(profile.get("api_key") or "").strip() or None
        if profile.get("auth_token"):
            self.state.submit_auth_token = str(profile.get("auth_token") or "").strip() or None
        if "auto_submit" in profile:
            value = profile.get("auto_submit")
            self.state.submit_auto = (
                bool(value)
                if isinstance(value, bool)
                else str(value or "").strip().lower() in {"1", "true", "yes", "on"}
            )

    async def _record_uniform_failure_surface(
        self,
        value: str,
        *,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.state is None:
            return
        normalized_meta = dict(metadata or {})
        self.state.add_observation(
            "uniform_failure_surface",
            value,
            source=source,
            metadata=normalized_meta,
        )
        if not self._memory_match_ids:
            return
        entry_id = str(self._memory_match_ids[0] or "").strip()
        if not entry_id:
            return
        payload = str(
            normalized_meta.get("payload")
            or normalized_meta.get("signature")
            or normalized_meta.get("request_url")
            or value
            or ""
        ).strip()
        reason = str(normalized_meta.get("reason") or value or "").strip()
        updated = await self.strategy_memory.record_failure(
            entry_id,
            payload=payload,
            reason=reason,
        )
        if updated is not None:
            self.state.meta_reasonings.append(
                {
                    "type": "strategy_memory_failure_recorded",
                    "entry_id": entry_id,
                    "payload": payload[:80],
                    "reason": reason[:120],
                }
            )

    def _restore_context(self) -> None:
        notes = get_all_notes_sync()
        self._emit(f"[CTF dispatcher] restored notes: {len(notes)} entries")
        if (
            self.state is None
            or self._checkpoint_store is None
            or not isinstance(self._challenge_context, dict)
        ):
            return
        resume_context = self._challenge_context.get("resumeContext")
        if not isinstance(resume_context, dict):
            return
        resume_run_id = str(resume_context.get("runId") or "").strip()
        resume_checkpoint_id = str(resume_context.get("checkpointId") or "").strip()
        if not resume_run_id:
            return
        if (
            self._restored_resume_checkpoint_id is not None
            and self._restored_resume_checkpoint_id == (resume_checkpoint_id or "__latest__")
        ):
            return
        record = (
            self._checkpoint_store.get_checkpoint(resume_run_id, resume_checkpoint_id)
            if resume_checkpoint_id
            else self._checkpoint_store.latest_checkpoint(resume_run_id)
        )
        if not isinstance(record, dict):
            return
        snapshot = record.get("state")
        if not isinstance(snapshot, dict):
            return
        try:
            restored_state = CTFState.from_snapshot(snapshot)
        except Exception:
            return
        restored_state.target = str(self.state.target or restored_state.target or "").strip()
        restored_state.goal = str(self.state.goal or restored_state.goal or "").strip()
        restored_state.local_challenge_auto_verify = (
            restored_state.local_challenge_auto_verify or self.state.local_challenge_auto_verify
        )
        if getattr(self.state, "capabilities", None):
            restored_state.capabilities = {
                **dict(restored_state.capabilities or {}),
                **dict(self.state.capabilities or {}),
            }
        self.state = restored_state
        self._restored_resume_checkpoint_id = str(
            resume_checkpoint_id or record.get("checkpoint_id") or "__latest__"
        ).strip() or "__latest__"
        self._emit(
            "[CTF dispatcher] restored checkpoint state: "
            f"run_id={resume_run_id} checkpoint_id={self._restored_resume_checkpoint_id}"
        )

    def _select_hypothesis_for_chain(self, chain_name: str):
        if self.state is None:
            return None
        for hypothesis in self.state.hypotheses:
            if _CHAIN_NAME_FOR_HYPOTHESIS.get(hypothesis.kind) == chain_name:
                return hypothesis
        return self.state.hypotheses[0] if self.state.hypotheses else None

    def _strategy_context(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
        hint: str,
        extras: dict[str, Any] | None = None,
    ) -> StrategyContext:
        resolved_extras = dict(extras or {})
        if not resolved_extras.get("exploit_info"):
            if derived := self._recent_php_unserialize_source_exploit():
                resolved_extras.setdefault("exploit_info", derived.get("exploit_info") or {})
                resolved_extras.setdefault("artifact_url", str(derived.get("artifact_url") or ""))
        if not resolved_extras.get("cookie_secret") and self.state is not None:
            for observation in reversed(list(self.state.observations)):
                if str(getattr(observation, "kind", "") or "").strip() != "cookie_secret_leaked":
                    continue
                cookie_secret = str(getattr(observation, "value", "") or "").strip()
                if cookie_secret:
                    resolved_extras.setdefault("cookie_secret", cookie_secret)
                    break
        return StrategyContext(
            services=self,
            target=target,
            page_features=page_features,
            hint=hint,
            extras=resolved_extras,
            state=self.state,
            ingress_handoff=self._ingress_handoff if isinstance(self._ingress_handoff, dict) else {},
            challenge_context=self._challenge_context if isinstance(self._challenge_context, dict) else {},
        )

    def _strategies_for_chain(
        self,
        chain_name: str,
        *,
        target: str,
        page_features: dict[str, Any],
        hint: str,
        extras: dict[str, Any] | None = None,
    ):
        return self.strategy_registry.list_for_chain(
            chain_name,
            self._strategy_context(
                target=target,
                page_features=page_features,
                hint=hint,
                extras=extras,
            ),
        )

    def _emit(self, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message)




__all__ = ["CTFTaskDispatcher", "SolveResult"]
