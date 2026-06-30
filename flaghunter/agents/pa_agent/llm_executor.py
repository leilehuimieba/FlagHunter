"""LLM-driven exploration / action-execution cluster extracted from ctf_dispatcher.py.

L3i / Workstream A (object-ification, cut A): the LLM action-execution cluster
(15 methods, ``_run_llm_driven_exploration`` .. ``_expected_signal_met``) is lifted
out of ``LLMExecutorMixin`` into a single independent, stateless ``LLMExecutor``
class. Method bodies are moved byte-for-byte; the only behavioural inputs — the
shared ``CTFState``, the live ``llm`` handle, the ``runtime``, ``collector_port``,
``capability_registry`` and six sibling dispatcher methods (``_scan_and_store``,
``_extract_flag``, ``_observe_flag``, ``_recent_observed_source_fetch_write_exploit``,
``_runtime_proxy_action``, ``_runtime_execute_command``) — are supplied per call via
a lightweight ``LLMExecContext`` rather than read off ``self``. ``LLMExecutor`` holds
no eager state of its own (``vars(LLMExecutor()) == {}``).

The reason state/llm/runtime are injected per call rather than stored is that the
shared CTFState and the live llm handle are swapped out on replay/fork, so a stored
reference would silently go stale (the same trap addressed in L3d ``_notes_log`` and
L3h state injection).

``LLMExecutorMixin`` retains every method as a thin delegation shell with the
original names + signatures (and original ``__module__`` anchoring), so the MRO and
the external call sites (``strategy_registry.py`` ``hasattr`` guards,
``ssti_executor.py``, ``chains/*.py``) are unchanged. Pure code relocation,
near-zero risk.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from ...harness import build_tool_called_event, build_tool_finished_event
from ...llm.utils import parse_llm_json
from .chains.base import _ChainOutcome
from .ctf_state import LLMStepLog
from .dispatcher_helpers import _base_target
from .reasoning import PreActionReasoning
from .strategy_registry import StrategyContext


@dataclass
class LLMExecContext:
    """Per-call behavioural inputs for :class:`LLMExecutor`.

    Bundles the live dispatcher state/handles and the six injected sibling methods.
    A fresh context is built by the delegation shell on every call so nothing is
    retained across replay/fork state swaps.
    """

    state: Any
    llm: Any
    runtime: Any
    collector_port: Any
    capability_registry: Any
    scan_and_store: Callable[..., Awaitable[Any]]
    extract_flag: Callable[[str], Optional[str]]
    observe_flag: Callable[..., Awaitable[Any]]
    recent_observed_source_fetch_write_exploit: Callable[[], Optional[dict[str, Any]]]
    runtime_proxy_action: Callable[..., Awaitable[Any]]
    runtime_execute_command: Callable[..., Awaitable[Any]]
    # Session-ledger recorder for non-runtime tools (e.g. web_search, which does
    # not flow through the audited runtime actions). Optional so contexts built
    # without a ledger still work; None ⇒ events are simply not recorded.
    record_session_event: Optional[Callable[..., None]] = None


class LLMExecutor:
    """Stateless LLM-driven exploration and action execution.

    No instance state: the shared ``CTFState``, the live ``llm`` handle, the
    ``runtime``, ``collector_port``, ``capability_registry`` and the six sibling
    dispatcher methods are supplied per call through an :class:`LLMExecContext`.
    ``vars(LLMExecutor()) == {}``.
    """

    async def run_llm_driven_exploration(
        self, context: StrategyContext, ctx: LLMExecContext
    ) -> _ChainOutcome:
        if ctx.state is None:
            return _ChainOutcome(progress=False, reason="llm_exploration_unavailable")
        if not ctx.state.is_llm_exploration_allowed():
            return _ChainOutcome(progress=False, reason="llm_exploration_budget_exhausted")

        if ctx.llm is None:
            return _ChainOutcome(progress=False, reason="llm_not_configured")

        progress = False
        reason_fragments: list[str] = []
        # §3.5 检测/修正分离: a deterministic explanation of why the *previous* probe's
        # expected signal was not met, threaded into the next proposal. Detection +
        # explanation is the code's job (validator); the correction is the LLM's — it
        # is good at fixing a specific, precisely-stated error but bad at noticing its
        # own. We state the failure, never script the fix (don't cage the model).
        correction_hint = ""
        # §3.2: 用放宽的累计探索预算天花板(is_llm_exploration_allowed 默认值·env
        # FLAGHUNTER_LLM_EXPLORATION_CEILING 可调)取代旧硬编码 8——它把曲库外探索饿死。
        # 天花板只是成本/安全**边界**;"做完/做不下去就停"交给大模型自己的 stop 动作(下方
        # action_type=="stop")+ switch_chain,而非死板步数门(见 [[feedback_less_is_more_dont_cage_llm]])。
        while ctx.state.is_llm_exploration_allowed():
            action_spec = await self.call_llm_for_action(
                context, ctx, degradation_hint=correction_hint
            )
            if not action_spec:
                return _ChainOutcome(progress=progress, reason="llm_exploration_invalid_action")

            replan_count = 0
            while True:
                decision = PreActionReasoning.evaluate(
                    action_spec,
                    ctx.state,
                    capability_registry=ctx.capability_registry,
                    target=context.target,
                    collector_base=f"http://127.0.0.1:{ctx.collector_port}",
                )
                self.record_llm_reasoning(action_spec, decision, ctx)
                if decision.approve:
                    break
                ctx.state.record_weak_decision(decision.reason)
                # ToolGuard blocks (the only one being an out-of-scope/allowlist
                # violation) are a policy boundary, not a fixable proposal defect
                # like a missing tool or a vague signal — terminate and surface the
                # block reason rather than burning replan budget hoping the model
                # picks a different host. The outer loop then switches chain.
                should_replan = (
                    replan_count < 2
                    and (
                        bool(decision.downgrade_to)
                        or str(decision.reason or "").startswith(("Q1 blocked", "Q2 blocked", "Q4 blocked"))
                    )
                )
                if should_replan:
                    degradation_hint = f"Previous proposal was rejected: {decision.reason}. Propose a materially different next action that uses fresh evidence."
                    forced_tool = ""
                    if decision.downgrade_to:
                        degradation_hint = f"Do not use the missing tool. Re-plan with {decision.downgrade_to}."
                        forced_tool = decision.downgrade_to
                    action_spec = await self.call_llm_for_action(
                        context,
                        ctx,
                        degradation_hint=degradation_hint,
                        forced_tool=forced_tool,
                    )
                    replan_count += 1
                    if not action_spec:
                        return _ChainOutcome(progress=progress, reason="llm_exploration_invalid_action")
                    continue
                return _ChainOutcome(progress=progress, reason=decision.reason)

            if str(action_spec.get("action_type") or "").strip() == "stop":
                stop_reason = str(action_spec.get("rationale") or "llm_requested_stop").strip()
                return _ChainOutcome(progress=progress, reason=stop_reason)

            execution = await self.execute_llm_action(action_spec, context.target, ctx)
            response_text = str(execution.get("response_text") or "")
            target_url = str(execution.get("target_url") or context.target)
            verifier_decision = "none"
            verification = None
            if response_text:
                await ctx.scan_and_store(
                    response_text,
                    target_url,
                    evidence_source=str(execution.get("evidence_source") or "runtime-output"),
                )
                if flag := ctx.extract_flag(response_text):
                    verification = await ctx.observe_flag(
                        flag,
                        target_url,
                        evidence_source=str(execution.get("evidence_source") or "runtime-output"),
                        rationale="llm_driven_exploration observed flag candidate",
                    )
                    verifier_decision = (
                        str(getattr(verification, "decision", "none") or "none")
                    )
            expected_signal_met = self.expected_signal_met(
                str(action_spec.get("expected_signal") or ""),
                response_text,
                execution,
            )
            summary = self.summarize_response(response_text, execution)
            ctx.state.record_llm_step(
                LLMStepLog(
                    step=ctx.state.llm_exploration_steps + 1,
                    action_type=str(action_spec.get("action_type") or ""),
                    rationale=str(action_spec.get("rationale") or "")[:200],
                    payload_summary=self.summarize_payload(action_spec),
                    response_summary=summary,
                    verifier_decision=verifier_decision,
                    expected_signal_met=expected_signal_met,
                    timestamp=time.time(),
                )
            )
            ctx.state.add_observation(
                "llm_exploration_step",
                summary,
                source="llm_driven_exploration",
                metadata={
                    "action_type": str(action_spec.get("action_type") or ""),
                    "tool_name": str(action_spec.get("tool_name") or ""),
                    "expected_signal": str(action_spec.get("expected_signal") or ""),
                    "expected_signal_met": expected_signal_met,
                    "verifier_decision": verifier_decision,
                    "payload_summary": self.summarize_payload(action_spec),
                    "target_url": target_url,
                },
            )
            if response_text or expected_signal_met:
                progress = True
            # §3.5 检测/修正分离: detect+explain a missed expected signal and carry the
            # precise reason into the next proposal (correction is the model's job).
            correction_hint = self.explain_signal_miss(
                action_spec, response_text, execution, expected_signal_met=expected_signal_met
            )
            if verification is not None and getattr(verification, "decision", "") == "verified":
                return _ChainOutcome(
                    progress=True,
                    flag=verification.flag,
                    reason="llm_exploration: verified flag",
                )
            reason_fragments.append(
                f"step={ctx.state.llm_exploration_steps}:{action_spec.get('action_type')}:{verifier_decision or 'none'}"
            )
            next_if_fail = str(action_spec.get("next_if_fail") or "").lower()
            if "switch chain" in next_if_fail or "switch_chain" in next_if_fail:
                break

        if progress:
            return _ChainOutcome(
                progress=True,
                reason="llm_exploration: " + "; ".join(reason_fragments[-3:]),
            )
        return _ChainOutcome(progress=False, reason="llm_exploration_exhausted")

    async def call_llm_for_action(
        self,
        context: StrategyContext,
        ctx: LLMExecContext,
        *,
        degradation_hint: str = "",
        forced_tool: str = "",
    ) -> dict[str, Any] | None:
        if ctx.state is None or ctx.llm is None:
            return None

        observation_lines: list[str] = []
        for observation in ctx.state.observations[-5:]:
            value = str(observation.value or "")
            if len(value) > 200:
                value = value[:200] + "..."
            observation_lines.append(f"- {observation.kind}: {value}")
        rejected = [record.value for record in ctx.state.rejected_flags[-5:]]
        raw_links = list(context.page_features.get("raw_links") or [])[:20]
        artifacts = [
            {
                "name": getattr(item, "name", ""),
                "location": getattr(item, "location", ""),
                "metadata": getattr(item, "metadata", {}),
            }
            for item in (ctx.state.artifacts[-8:] if ctx.state is not None else [])
        ]
        runtime_summary = self.normalized_runtime_summary(ctx)
        source_fetch_exploit = ctx.recent_observed_source_fetch_write_exploit()
        recent_source_probes = self.recent_source_fetch_probe_targets(ctx, limit=10)
        prompt = (
            "You are planning the next CTF action.\n"
            "Return JSON only with keys action_type, tool_name, rationale, payload, expected_signal, next_if_fail.\n"
            "Allowed action_type: http_request, shell, stop.\n"
            f"Target: {context.target}\n"
            f"Runtime: {runtime_summary}\n"
            f"Known links: {raw_links}\n"
            f"Known artifacts: {json.dumps(artifacts, ensure_ascii=False)[:1600]}\n"
            f"Recent observations:\n" + ("\n".join(observation_lines) if observation_lines else "- none") + "\n"
            f"Rejected flags: {rejected}\n"
            "Allowed tools: http_request, terminal, manual_sqli_payload, manual_path_enumeration, knowledge_search, web_search.\n"
            "For attachment/misc/forensics challenges, you may use shell with python snippets to inspect downloaded artifacts, sqlite databases, WAL files, archives, or to decode/transform extracted fragments.\n"
        )
        # 设计 §3.3 Detect→Identify→Exploit: frame the proposal by the current
        # investigation stage so the loop runs a *staged* investigation (probe →
        # fingerprint → targeted exploit) instead of flailing single-step. The stage
        # is a deterministic pure function of accumulated evidence (exploration_stages),
        # and this only shapes the miss-path exploration prompt — never the
        # byte-identical 曲库-hit path (which does not call the LLM planner).
        try:
            from .exploration_stages import stage_guidance

            prompt += stage_guidance(ctx.state) + "\n"
        except Exception:
            pass
        # Cross-challenge negative feedback (consume half of record_failure):
        # payloads recorded as failures on similar past challenges. Same protocol
        # augmentation as the within-session "Rejected flags" / REFUTED-intent
        # signals — surfaces the failures so the planner stops re-proposing them;
        # it does not force a choice. No-op (byte-identical prompt) when memory is
        # cold, since the dispatcher leaves the list empty.
        known_failed_payloads = list(
            getattr(context.services, "_known_failed_payloads", None) or []
        )[:12]
        if known_failed_payloads:
            prompt += (
                "Payloads that already FAILED on similar past challenges (do NOT "
                "re-propose these; they were recorded as failures — try a "
                "materially different payload/approach):\n"
                + "\n".join(f"- {payload}" for payload in known_failed_payloads)
                + "\n"
            )
        # P8 回灌 (闭环波): cross-run emergent tool-chains, mined from provenance and
        # P7-scored once at bootstrap. Same advisory protocol-augmentation as the
        # failed-payload / agenda blocks — it surfaces what worked / spun on past
        # runs but does not force a choice (never removes a tool; C1 覆盖底线). No-op
        # (byte-identical prompt) when the provenance log is cold / has no recurring
        # chains, since the dispatcher leaves ``_emergent_chain_hints`` empty.
        chain_hints = getattr(context.services, "_emergent_chain_hints", None) or {}
        reuse_chains = list(chain_hints.get("reuse") or [])[:5]
        avoid_chains = list(chain_hints.get("avoid") or [])[:5]
        if reuse_chains:
            prompt += (
                "Tool sequences that LED TO A FLAG on prior runs (prefer extending "
                "or continuing these proven chains when the situation matches):\n"
                + "\n".join(f"- {chain}" for chain in reuse_chains)
                + "\n"
            )
        if avoid_chains:
            prompt += (
                "Tool sequences that historically just ERRORED or spun without "
                "progress (avoid blindly repeating these; prefer a materially "
                "different approach):\n"
                + "\n".join(f"- {chain}" for chain in avoid_chains)
                + "\n"
            )
        # P10/P11 白盒 (code_audit profile): suspicious points flagged by the
        # white-box source audit. Same advisory protocol — surfaces source sinks to
        # verify against the live target; these are pattern matches, not proven
        # vulns. No-op (byte-identical) for url entry (CTF), where the dispatcher
        # leaves _source_audit_findings empty.
        source_audit_findings = list(
            getattr(context.services, "_source_audit_findings", None) or []
        )[:12]
        if source_audit_findings:
            prompt += (
                "White-box source audit flagged these suspicious points (verify "
                "each against the live target before trusting it — confirm "
                "reachability/exploitability; they are pattern matches, not proven "
                "vulnerabilities):\n"
                + "\n".join(f"- {point}" for point in source_audit_findings)
                + "\n"
            )
        # Surface the structured ExplorationAgenda (recon-discovered + framework
        # conventional entry routes) as an explicit prioritized queue. Without
        # this the planner only saw raw_links buried in the prompt and fell back
        # to its CTF prior (.git/.env/backup guessing), leaving high-value app
        # entry points like /login,/register unexplored. This surfaces the queue
        # so the model can prefer it (protocol augmentation; it does not force a
        # choice).
        agenda_items = ctx.state.get_unexplored_priority_items(max_hint_strength=2)
        if agenda_items:
            agenda_lines = [
                f"- [{item.discovery_source},hint={item.hint_strength}] {item.url_or_path}"
                for item in agenda_items[:8]
            ]
            prompt += (
                "Unexplored high-value entry points (ExplorationAgenda). Prefer "
                "consuming these real app routes (e.g. /login, /register, /admin, "
                "/api) before blindly guessing backup/dotfile paths; on auth-gated "
                "apps, registering then logging in usually unlocks the shortest "
                "chain to the flag:\n"
                + "\n".join(agenda_lines) + "\n"
            )
        # Workstream B (slice B2): surface the ranked Fact/Intent/Hint blackboard so
        # the model decides the next action from the shared board. Intents are sorted
        # active+high-value first with already-refuted ones marked, closing the
        # "verification failed -> switch candidate" loop at the protocol level
        # (the board exposes the failure; it does not force the switch).
        from .blackboard import project_blackboard

        board = project_blackboard(ctx.state, intent_limit=8)
        if board["intents"]:
            intent_lines = []
            for intent in board["intents"]:
                description = str(intent.get("description") or "")[:120]
                if intent.get("refuted"):
                    tag = "REFUTED-already-tried"
                else:
                    tag = (
                        f"value={float(intent.get('value_score') or 0.0):.2f}"
                        f",direct={int(intent.get('directness') or 0)}"
                    )
                intent_lines.append(
                    f"- [{tag}] {intent.get('kind')}: {description} "
                    f"(confidence={float(intent.get('confidence') or 0.0):.2f})"
                )
            prompt += (
                "Blackboard intents (ranked; prefer the top active intent — higher "
                "value and higher direct= means a shorter remaining path to the flag, "
                "take the shortest chain. Do NOT re-propose REFUTED ones; switch to "
                "the next active intent when a candidate is refuted):\n"
                + "\n".join(intent_lines) + "\n"
            )
        if source_fetch_exploit is not None:
            exploit_info = dict(source_fetch_exploit.get("exploit_info") or {})
            prompt += (
                "Observed runtime exploit primitive: source_fetch_write_ssrf.\n"
                f"Exploit details: {json.dumps(exploit_info, ensure_ascii=False)[:800]}\n"
            )
            if recent_source_probes:
                prompt += (
                    "Recent confirmed fetch targets already executed: "
                    + json.dumps(recent_source_probes[-8:], ensure_ascii=False)
                    + "\n"
                )
            prompt += (
                "If you want to use this primitive again, prefer a direct read/write follow-up instead of re-fetching the same highlighted homepage source.\n"
                "Avoid requesting the exact same root page repeatedly unless you are testing a materially different path or parameter.\n"
            )
        if "windows" in runtime_summary.lower():
            prompt += (
                "This runtime is Windows-based. Do not use bash heredoc syntax like <<'PY' or Linux-only paths such as /tmp/.\n"
                "If shell is necessary, prefer portable commands or a single Python invocation compatible with Windows/PowerShell.\n"
            )
        if degradation_hint:
            prompt += f"Degradation hint: {degradation_hint}\n"
        if forced_tool:
            prompt += f"You must use tool_name={forced_tool}.\n"

        raw = ""
        finish_reason = ""
        if callable(ctx.llm):
            result = ctx.llm(prompt)
            resolved = await result if asyncio.iscoroutine(result) else result
            raw, finish_reason = self.extract_llm_action_text(resolved)
        elif hasattr(ctx.llm, "generate"):
            generator = getattr(ctx.llm, "generate")
            try:
                result = generator(prompt)
            except TypeError as exc:
                if "required positional argument" not in str(exc):
                    raise
                result = generator(
                    system_prompt=(
                        "You are planning the next CTF action. "
                        "Return JSON only with keys action_type, tool_name, rationale, payload, expected_signal, next_if_fail."
                    ),
                    messages=[{"role": "user", "content": prompt}],
                    tools=None,
                    task_hint="ctf_planning",
                )
            resolved = await result if asyncio.iscoroutine(result) else result
            raw, finish_reason = self.extract_llm_action_text(resolved)
        else:
            return None

        parsed = parse_llm_json(raw)
        if isinstance(parsed, dict):
            return parsed
        if finish_reason in {"provider_unavailable", "budget_exhausted", "error"} and raw:
            return {
                "action_type": "stop",
                "tool_name": "",
                "rationale": raw[:400],
                "payload": {},
                "expected_signal": finish_reason,
                "next_if_fail": "switch chain",
            }
        return None

    def normalized_runtime_summary(self, ctx: LLMExecContext) -> str:
        env = getattr(ctx.runtime, "environment", None)
        if env is None:
            return "unknown runtime"
        os_name = str(getattr(env, "os", "") or "").strip() or "unknown-os"
        shell_name = str(getattr(env, "shell", "") or "").strip() or "unknown-shell"
        available = getattr(env, "available_tools", []) or []
        tool_names: list[str] = []
        for item in available:
            name = getattr(item, "name", item)
            normalized = str(name or "").strip()
            if normalized:
                tool_names.append(normalized)
        tool_preview = ", ".join(tool_names[:16]) if tool_names else "none-detected"
        return f"os={os_name}; shell={shell_name}; tools={tool_preview}"

    def recent_source_fetch_probe_targets(
        self, ctx: LLMExecContext, *, limit: int = 12
    ) -> list[str]:
        if ctx.state is None:
            return []
        targets: list[str] = []
        seen: set[str] = set()
        for observation in reversed(list(ctx.state.observations)[-max(1, limit):]):
            if str(getattr(observation, "kind", "") or "").strip() != "source_fetch_write_probe":
                continue
            value = str(getattr(observation, "value", "") or "").strip()
            if value and value not in seen:
                seen.add(value)
                targets.append(value)
        targets.reverse()
        return targets

    @staticmethod
    def extract_llm_action_text(result: Any) -> tuple[str, str]:
        finish_reason = str(getattr(result, "finish_reason", "") or "")
        if hasattr(result, "content"):
            return str(getattr(result, "content", "") or ""), finish_reason
        if isinstance(result, dict):
            return str(result.get("content") or result.get("text") or result), finish_reason
        return str(result or ""), finish_reason

    def normalize_llm_http_payload(
        self,
        payload: Any,
        target: str,
    ) -> dict[str, Any]:
        if isinstance(payload, dict):
            normalized = dict(payload)
        else:
            normalized = {}

        if isinstance(payload, str):
            raw_payload = payload.strip()
            request_match = re.match(
                r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)$",
                raw_payload,
                flags=re.IGNORECASE,
            )
            if request_match:
                normalized["method"] = request_match.group(1).upper()
                normalized["url"] = request_match.group(2)
            elif raw_payload.startswith(("http://", "https://", "/", "file://")):
                normalized["url"] = raw_payload

        raw_url = str(
            normalized.get("url")
            or normalized.get("path")
            or normalized.get("endpoint")
            or ""
        ).strip()
        if not raw_url:
            candidate_lists = (
                normalized.get("candidate_urls"),
                normalized.get("urls"),
                normalized.get("candidate_file_urls"),
                normalized.get("file_urls"),
            )
            for values in candidate_lists:
                if not isinstance(values, list):
                    continue
                for item in values:
                    candidate = str(item or "").strip()
                    if candidate:
                        raw_url = candidate
                        break
                if raw_url:
                    break

        normalized["method"] = str(normalized.get("method") or "GET").upper()
        normalized["url"] = raw_url or target
        return normalized

    @staticmethod
    def looks_like_loopback_or_file_target(value: str) -> bool:
        candidate = str(value or "").strip().lower()
        if not candidate:
            return False
        if candidate.startswith("file://"):
            return True
        if candidate.startswith(("http://127.0.0.1", "https://127.0.0.1")):
            return True
        if candidate.startswith(("http://localhost", "https://localhost")):
            return True
        return False

    def normalize_llm_shell_command(self, command: str, ctx: LLMExecContext) -> str:
        normalized = str(command or "").strip()
        env = getattr(ctx.runtime, "environment", None)
        os_name = str(getattr(env, "os", "") or "").lower()
        if not normalized or "windows" not in os_name:
            return normalized

        temp_dir = Path(tempfile.gettempdir())
        temp_dir_forward = temp_dir.as_posix()
        normalized = re.sub(
            r"(?<![A-Za-z0-9_])\/tmp\/([A-Za-z0-9_.-]+)",
            lambda match: f"{temp_dir_forward}/{match.group(1)}",
            normalized,
        )

        heredoc_match = re.search(
            r"(?P<prefix>[\s\S]*?)(?P<runner>python3?|py(?:\s+-3)?)\s+-\s+<<'PY'\n(?P<script>[\s\S]+?)\nPY\s*$",
            normalized,
            flags=re.IGNORECASE,
        )
        if heredoc_match:
            script_path = temp_dir / f"flaghunter_llm_{uuid.uuid4().hex}.py"
            script_path.write_text(
                heredoc_match.group("script"),
                encoding="utf-8",
            )
            prefix = heredoc_match.group("prefix")
            runner = f"\"{sys.executable}\" \"{script_path}\""
            spacer = "" if not prefix or prefix.endswith((" ", "\t", "\n")) else " "
            normalized = f"{prefix}{spacer}{runner}".strip()

        normalized = re.sub(
            r"(?<![A-Za-z0-9_])python3(?=(?:\s|$))",
            lambda _match: f"\"{sys.executable}\"",
            normalized,
            flags=re.IGNORECASE,
        )
        return normalized

    def build_source_fetch_write_output_urls(
        self,
        target: str,
        exploit_info: dict[str, Any],
    ) -> list[str]:
        base = _base_target(target)
        probe_filename = str(
            exploit_info.get("probe_filename") or "p/flaghunter_probe.txt"
        ).strip() or "p/flaghunter_probe.txt"
        client_ip_value = str(exploit_info.get("client_ip_value") or "8.8.8.8").strip() or "8.8.8.8"
        sandbox_prefix = str(exploit_info.get("sandbox_prefix") or "sandbox/").strip() or "sandbox/"
        remote_addr_hash = str(exploit_info.get("remote_addr_hash") or "").strip().lower()
        remote_addr_salt = str(exploit_info.get("remote_addr_salt") or "").strip()
        if remote_addr_hash not in {"md5", "sha1"}:
            return []

        digest_input = (remote_addr_salt + client_ip_value).encode("utf-8")
        digest = hashlib.md5(digest_input).hexdigest() if remote_addr_hash == "md5" else hashlib.sha1(digest_input).hexdigest()
        output_parts = [sandbox_prefix.strip("/"), digest]
        normalized_probe = probe_filename.replace("\\", "/").strip("/")
        if "/" in normalized_probe:
            parent, leaf = normalized_probe.rsplit("/", 1)
            if parent and parent != ".":
                output_parts.append(parent.strip("/"))
            output_parts.append(leaf)
        elif normalized_probe:
            output_parts.append(normalized_probe)
        output_url = urljoin(
            base.rstrip("/") + "/",
            "/".join(part for part in output_parts if part),
        )
        return [output_url] if output_url else []

    def derive_source_fetch_write_llm_request(
        self,
        *,
        payload: dict[str, Any],
        target: str,
        ctx: LLMExecContext,
    ) -> dict[str, Any] | None:
        observed = ctx.recent_observed_source_fetch_write_exploit()
        if observed is None:
            return None

        exploit_info = dict(observed.get("exploit_info") or {})
        if not exploit_info:
            return None

        base = _base_target(target)
        url_param = str(exploit_info.get("url_param") or "url").strip() or "url"
        filename_param = str(exploit_info.get("filename_param") or "filename").strip() or "filename"
        probe_filename = str(exploit_info.get("probe_filename") or "p/flaghunter_probe.txt").strip() or "p/flaghunter_probe.txt"
        headers = dict(payload.get("headers") or {})

        client_ip_header = str(exploit_info.get("client_ip_header") or "").strip()
        client_ip_value = str(exploit_info.get("client_ip_value") or "8.8.8.8").strip() or "8.8.8.8"
        if client_ip_header and client_ip_header not in headers:
            headers[client_ip_header] = client_ip_value

        fetch_target = ""
        direct_url = str(payload.get("url") or "").strip()
        candidate_lists = (
            payload.get("candidate_file_urls"),
            payload.get("file_urls"),
            payload.get("candidate_urls"),
            payload.get("urls"),
        )
        for values in candidate_lists:
            if not isinstance(values, list):
                continue
            for item in values:
                candidate = str(item or "").strip()
                if self.looks_like_loopback_or_file_target(candidate):
                    fetch_target = candidate
                    break
            if fetch_target:
                break

        if not fetch_target and self.looks_like_loopback_or_file_target(direct_url):
            fetch_target = direct_url

        final_url = urljoin(
            target if target.endswith("/") else target + "/",
            direct_url or target,
        )
        parsed_final = urlparse(final_url)
        parsed_target = urlparse(base)
        if (
            not fetch_target
            and parsed_final.hostname
            and parsed_final.hostname == parsed_target.hostname
        ):
            query = parse_qs(parsed_final.query, keep_blank_values=True)
            if url_param in query and query.get(url_param):
                fetch_target = str(query[url_param][0] or "").strip()

        if not fetch_target:
            return None

        trigger_url = urljoin(
            base.rstrip("/") + "/",
            "?" + urlencode({url_param: fetch_target, filename_param: probe_filename}),
        )
        return {
            "fetch_target": fetch_target,
            "trigger_url": trigger_url,
            "headers": headers or None,
            "output_urls": self.build_source_fetch_write_output_urls(target, exploit_info),
        }

    async def execute_llm_action(
        self,
        action_spec: dict[str, Any],
        target: str,
        ctx: LLMExecContext,
    ) -> dict[str, Any]:
        action_type = str(action_spec.get("action_type") or "").strip()
        tool_name = str(action_spec.get("tool_name") or "").strip()

        # web_search is runtime-independent (pure HTTP backends). Dispatch it
        # before the runtime guard so an LLM web_search request is executed and
        # ledger-audited instead of being silently swallowed (the "能力够不着"
        # gap: the prompt allowed web_search but no branch ran it).
        if action_type == "web_search" or tool_name == "web_search":
            return await self._execute_web_search_action(action_spec, target, ctx)

        if ctx.runtime is None:
            return {"response_text": "", "target_url": target, "evidence_source": "runtime-output"}

        payload = action_spec.get("payload")

        if action_type == "http_request" and hasattr(ctx.runtime, "proxy_action"):
            payload_dict = self.normalize_llm_http_payload(payload, target)
            method = str(payload_dict.get("method") or "GET").upper()
            raw_url = str(payload_dict.get("url") or target).strip() or target
            final_url = urljoin(target if target.endswith("/") else target + "/", raw_url)
            ssrf_request = self.derive_source_fetch_write_llm_request(
                payload=payload_dict,
                target=target,
                ctx=ctx,
            )
            if ssrf_request is not None:
                trigger_url = str(ssrf_request.get("trigger_url") or final_url)
                headers = ssrf_request.get("headers")
                trigger_resp = await ctx.runtime_proxy_action(
                    "request",
                    method=method,
                    url=trigger_url,
                    headers=headers,
                    params={},
                    data=None,
                    json=None,
                    timeout=int(payload_dict.get("timeout") or 20),
                    audit_target=trigger_url,
                    audit_metadata={"phase": "llm_action", "method": method, "source_fetch_write": True},
                )
                trigger_body = str((trigger_resp or {}).get("body") or "")
                final_trigger_url = str((trigger_resp or {}).get("final_url") or trigger_url)
                combined_body = trigger_body
                combined_target = final_trigger_url
                combined_status = (trigger_resp or {}).get("status_code")
                for output_url in list(ssrf_request.get("output_urls") or []):
                    retrieve_resp = await ctx.runtime_proxy_action(
                        "get",
                        url=output_url,
                        headers=headers,
                        timeout=int(payload_dict.get("timeout") or 20),
                        audit_target=output_url,
                        audit_metadata={
                            "phase": "llm_action",
                            "stage": "retrieve_source_fetch_write_output",
                            "source_target": str(ssrf_request.get("fetch_target") or ""),
                        },
                    )
                    output_body = str((retrieve_resp or {}).get("body") or "")
                    if not output_body:
                        continue
                    combined_body = output_body
                    combined_target = str((retrieve_resp or {}).get("final_url") or output_url)
                    combined_status = (retrieve_resp or {}).get("status_code")
                    break
                return {
                    "response_text": combined_body,
                    "target_url": combined_target,
                    "status_code": combined_status,
                    "evidence_source": "source-leak",
                }
            response = await ctx.runtime_proxy_action(
                "request",
                method=method,
                url=final_url,
                headers=dict(payload_dict.get("headers") or {}),
                params=dict(payload_dict.get("params") or {}),
                data=payload_dict.get("data"),
                json=payload_dict.get("json"),
                timeout=int(payload_dict.get("timeout") or 20),
                audit_target=final_url,
                audit_metadata={"phase": "llm_action", "method": method},
            )
            return {
                "response_text": str((response or {}).get("body") or ""),
                "target_url": str((response or {}).get("final_url") or final_url),
                "status_code": (response or {}).get("status_code"),
                "evidence_source": "http-response",
            }

        if action_type == "shell" and hasattr(ctx.runtime, "execute_command"):
            payload_dict = payload if isinstance(payload, dict) else {}
            command = self.normalize_llm_shell_command(
                str(payload_dict.get("command") or "").strip(),
                ctx,
            )
            if not command:
                return {
                    "response_text": "empty shell command",
                    "target_url": target,
                    "status_code": 1,
                    "evidence_source": "command-output",
                }
            result = await ctx.runtime_execute_command(
                command,
                timeout=int(payload_dict.get("timeout") or 120),
                audit_target=target,
                audit_metadata={"phase": "llm_action"},
            )
            text = "\n".join(
                part for part in [getattr(result, "stdout", ""), getattr(result, "stderr", "")] if part
            )
            return {
                "response_text": text,
                "target_url": target,
                "status_code": getattr(result, "exit_code", 0),
                "evidence_source": "command-output",
            }

        if action_type == "http_request":
            return {"response_text": "", "target_url": target, "status_code": 0, "evidence_source": "http-response"}

        return {"response_text": "", "target_url": target, "evidence_source": "runtime-output"}

    async def _execute_web_search_action(
        self,
        action_spec: dict[str, Any],
        target: str,
        ctx: LLMExecContext,
    ) -> dict[str, Any]:
        """Run the web_search tool for an LLM-requested search and ledger-audit it.

        Returns the standard execute_llm_action response shape so the existing
        downstream pipeline (scan_and_store + observation recording) handles the
        result. Records paired tool_called/tool_finished ledger events here
        because web_search does not flow through the audited runtime actions, so
        it would otherwise be invisible to the session ledger.
        """
        query = self._extract_web_search_query(action_spec)
        if not query:
            return {
                "response_text": "Error: empty web_search query",
                "target_url": target,
                "status_code": 1,
                "evidence_source": "web-search",
            }

        self._record_web_search_event(ctx, "called", query=query)
        try:
            from ...tools.web_search import web_search as _web_search_tool

            result_text = str(await _web_search_tool({"query": query}, ctx.runtime) or "")
        except Exception as exc:  # never let a backend error vanish silently
            result_text = f"Error: web_search backend raised: {exc}"

        ok = not result_text.startswith("Error:")
        self._record_web_search_event(ctx, "finished", query=query, ok=ok, result_text=result_text)
        return {
            "response_text": result_text,
            "target_url": target,
            "status_code": 0 if ok else 1,
            "evidence_source": "web-search",
        }

    @staticmethod
    def _extract_web_search_query(action_spec: dict[str, Any]) -> str:
        """Pull the search query from payload (dict/str) or a top-level field."""
        payload = action_spec.get("payload")
        if isinstance(payload, dict):
            query = payload.get("query") or payload.get("q") or ""
        elif isinstance(payload, str):
            query = payload
        else:
            query = action_spec.get("query") or ""
        return str(query or "").strip()

    def _record_web_search_event(
        self,
        ctx: LLMExecContext,
        phase: str,
        *,
        query: str,
        ok: Optional[bool] = None,
        result_text: str = "",
    ) -> None:
        """Record a paired tool_called/tool_finished ledger event for web_search.

        No-op when the context carries no ledger recorder (e.g. ledger inactive).
        """
        recorder = getattr(ctx, "record_session_event", None)
        if recorder is None:
            return
        target = query[:200]
        metadata: dict[str, Any] = {"query": query[:500]}
        if phase == "called":
            event = build_tool_called_event(
                tool_name="web_search",
                action="search",
                target=target,
                metadata=metadata,
            )
            fallback_type = "tool_called"
        else:
            metadata.update(self._summarize_web_search_result(result_text))
            event = build_tool_finished_event(
                tool_name="web_search",
                action="search",
                ok=bool(ok),
                status_code=0 if ok else 1,
                target=target,
                metadata=metadata,
            )
            fallback_type = "tool_finished"
        recorder(
            str(event.get("event_type") or fallback_type),
            dict(event.get("payload") or {}),
        )

    @staticmethod
    def _summarize_web_search_result(result_text: str) -> dict[str, Any]:
        """Best-effort summary of a web_search result for the ledger payload."""
        text = str(result_text or "")
        urls = re.findall(r"https?://\S+", text)
        return {
            "hit_count": len(urls),
            "top_url": urls[0] if urls else "",
            "error": text.startswith("Error:"),
        }

    def record_llm_reasoning(
        self, action_spec: dict[str, Any], decision: Any, ctx: LLMExecContext
    ) -> None:
        if ctx.state is None:
            return
        entry = {
            "type": "llm_pre_action_reasoning",
            "action_type": str(action_spec.get("action_type") or ""),
            "tool_name": str(action_spec.get("tool_name") or ""),
            "question": getattr(decision, "question", ""),
            "expected_signal": getattr(decision, "expected_signal", ""),
            "next_if_fail": getattr(decision, "next_if_fail", ""),
            "approve": bool(getattr(decision, "approve", False)),
            "reason": str(getattr(decision, "reason", "")),
            "downgrade_to": getattr(decision, "downgrade_to", None),
            "repeated_reject": bool(getattr(decision, "repeated_reject", False)),
        }
        ctx.state.pre_action_reasonings.append(entry)

    def summarize_payload(self, action_spec: dict[str, Any]) -> str:
        payload = action_spec.get("payload")
        summary = json.dumps(
            {
                "tool_name": action_spec.get("tool_name"),
                "action_type": action_spec.get("action_type"),
                "payload": payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return summary[:200]

    def summarize_response(self, response_text: str, execution: dict[str, Any]) -> str:
        response_text = str(response_text or "")
        preview = response_text[:220] + ("..." if len(response_text) > 220 else "")
        status = execution.get("status_code")
        target_url = execution.get("target_url")
        return f"status={status}; url={target_url}; body={preview}"[:300]

    def expected_signal_met(
        self,
        expected_signal: str,
        response_text: str,
        execution: dict[str, Any],
    ) -> bool:
        signal = str(expected_signal or "").strip().lower()
        if not signal:
            return False
        response_lower = str(response_text or "").lower()
        if "200" in signal and str(execution.get("status_code") or "") == "200":
            if "body 含" in signal:
                marker = signal.split("body 含", 1)[1].strip()
                return bool(marker) and marker.lower() in response_lower
            if "body contains " in signal:
                marker = signal.split("body contains ", 1)[1].strip()
                return bool(marker) and marker.lower() in response_lower
            return True
        if "flag" in signal and "flag{" in response_lower:
            return True
        if "keyword:" in signal:
            marker = signal.split("keyword:", 1)[1].strip()
            return bool(marker) and marker in response_lower
        return signal in response_lower

    def explain_signal_miss(
        self,
        action_spec: dict[str, Any],
        response_text: str,
        execution: dict[str, Any],
        *,
        expected_signal_met: bool,
    ) -> str:
        """§3.5: a deterministic explanation of why a probe's expected signal failed.

        Detection/correction separation (CRITIC pattern): the validator's job is to
        *detect and state precisely* what the probe expected versus what it actually
        observed. The fix is left to the model — we never script the correction, only
        give it a sharp, factual failure signal to react to (don't cage the model).

        Returns ``""`` when the signal was met or no expected signal was declared.
        """
        expected = str(action_spec.get("expected_signal") or "").strip()
        if expected_signal_met or not expected:
            return ""
        action_type = str(action_spec.get("action_type") or "action").strip()
        payload = self.summarize_payload(action_spec)
        status = str(execution.get("status_code") or execution.get("status") or "").strip()
        observed = self.summarize_response(response_text, execution)
        status_part = f" (status {status})" if status else ""
        return (
            f"Your previous {action_type} expected the signal \"{expected}\" but it "
            f"was NOT observed{status_part}; the response was: {observed[:200]}. "
            "That probe's hypothesis appears wrong — do not repeat the same payload "
            f"({payload[:80]}); change the injection point, encoding, or hypothesis."
        )


class LLMExecutorMixin:
    """LLM-driven exploration and action execution.

    Thin delegation shells over the stateless :class:`LLMExecutor` held by the
    dispatcher as ``self._llm_executor``. Shells preserve the original
    names/signatures (and ``__module__`` anchoring) and build a fresh
    :class:`LLMExecContext` per call from the live dispatcher state/handles and the
    six injected sibling dispatcher methods, so replay/fork state swaps are never
    captured by a stale reference.
    """

    def _llm_exec_context(self) -> LLMExecContext:
        return LLMExecContext(
            state=self.state,
            llm=self.llm,
            runtime=self.runtime,
            collector_port=self.collector_port,
            capability_registry=self.capability_registry,
            scan_and_store=self._scan_and_store,
            extract_flag=self._extract_flag,
            observe_flag=self._observe_flag,
            recent_observed_source_fetch_write_exploit=self._recent_observed_source_fetch_write_exploit,
            runtime_proxy_action=self._runtime_proxy_action,
            runtime_execute_command=self._runtime_execute_command,
            record_session_event=getattr(self, "_record_session_event", None),
        )

    async def _run_llm_driven_exploration(self, context: StrategyContext) -> _ChainOutcome:
        return await self._llm_executor.run_llm_driven_exploration(
            context, self._llm_exec_context()
        )

    async def _call_llm_for_action(
        self,
        context: StrategyContext,
        *,
        degradation_hint: str = "",
        forced_tool: str = "",
    ) -> dict[str, Any] | None:
        return await self._llm_executor.call_llm_for_action(
            context,
            self._llm_exec_context(),
            degradation_hint=degradation_hint,
            forced_tool=forced_tool,
        )

    def _normalized_runtime_summary(self) -> str:
        return self._llm_executor.normalized_runtime_summary(self._llm_exec_context())

    def _recent_source_fetch_probe_targets(self, *, limit: int = 12) -> list[str]:
        return self._llm_executor.recent_source_fetch_probe_targets(
            self._llm_exec_context(), limit=limit
        )

    def _extract_llm_action_text(self, result: Any) -> tuple[str, str]:
        return self._llm_executor.extract_llm_action_text(result)

    def _normalize_llm_http_payload(
        self,
        payload: Any,
        target: str,
    ) -> dict[str, Any]:
        return self._llm_executor.normalize_llm_http_payload(payload, target)

    def _looks_like_loopback_or_file_target(self, value: str) -> bool:
        return self._llm_executor.looks_like_loopback_or_file_target(value)

    def _normalize_llm_shell_command(self, command: str) -> str:
        return self._llm_executor.normalize_llm_shell_command(
            command, self._llm_exec_context()
        )

    def _build_source_fetch_write_output_urls(
        self,
        target: str,
        exploit_info: dict[str, Any],
    ) -> list[str]:
        return self._llm_executor.build_source_fetch_write_output_urls(target, exploit_info)

    def _derive_source_fetch_write_llm_request(
        self,
        *,
        payload: dict[str, Any],
        target: str,
    ) -> dict[str, Any] | None:
        return self._llm_executor.derive_source_fetch_write_llm_request(
            payload=payload, target=target, ctx=self._llm_exec_context()
        )

    async def _execute_llm_action(
        self,
        action_spec: dict[str, Any],
        target: str,
    ) -> dict[str, Any]:
        return await self._llm_executor.execute_llm_action(
            action_spec, target, self._llm_exec_context()
        )

    def _record_llm_reasoning(self, action_spec: dict[str, Any], decision: Any) -> None:
        self._llm_executor.record_llm_reasoning(
            action_spec, decision, self._llm_exec_context()
        )

    def _summarize_payload(self, action_spec: dict[str, Any]) -> str:
        return self._llm_executor.summarize_payload(action_spec)

    def _summarize_response(self, response_text: str, execution: dict[str, Any]) -> str:
        return self._llm_executor.summarize_response(response_text, execution)

    def _expected_signal_met(
        self,
        expected_signal: str,
        response_text: str,
        execution: dict[str, Any],
    ) -> bool:
        return self._llm_executor.expected_signal_met(
            expected_signal, response_text, execution
        )

    # ------------------------------------------------------------------
    # 新增 web 策略执行方法（Phase 0.5 easy_tornado 补全）
    # ------------------------------------------------------------------
