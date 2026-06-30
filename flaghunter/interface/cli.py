"""Non-interactive CLI mode for FlagHunter."""

import ast
import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Windows encoding fix: force UTF-8 for stdout/stderr to prevent
# UnicodeEncodeError on GBK terminals when printing bullet points etc.
if sys.platform == "win32":
    try:
        import io
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from ..config.constants import AGENT_MAX_ITERATIONS, ORCHESTRATOR_MAX_ITERATIONS
from .control_contract import (
    build_control_decision_parts,
    resolve_control_decision,
)
from .mode_router import resolve_mode_contract

console = Console(emoji=False, legacy_windows=False)

# PA theme colors (matching TUI)
PA_PRIMARY = "#d4d4d4"  # light gray - primary text
PA_SECONDARY = "#9a9a9a"  # medium gray - secondary text
PA_DIM = "#6b6b6b"  # dim gray - muted text
PA_BORDER = "#3a3a3a"  # dark gray - borders
PA_ACCENT = "#7a7a7a"  # accent gray


def _normalize_string_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    normalized: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if value:
            normalized.append(value)
    return list(dict.fromkeys(normalized))


def _ctf_dispatcher_hint(
    *,
    challenge_path: str | None = None,
    artifact_paths: list[str] | None = None,
    control_decision: dict[str, Any] | None = None,
    blackboard_snapshot: dict[str, Any] | None = None,
) -> str:
    structured_parts: list[str] = []
    decision = dict(control_decision or {})
    snapshot = dict(blackboard_snapshot or {})
    challenge_path = str(challenge_path or "").strip()
    artifact_paths = _normalize_string_list(artifact_paths)
    decision_parts = build_control_decision_parts(decision, snapshot)
    if decision_parts:
        structured_parts.append("[control_decision]\n" + "\n".join(decision_parts))
    if challenge_path:
        structured_parts.append(f"challengePath={challenge_path}")
    if artifact_paths:
        structured_parts.append("artifactPaths=" + "; ".join(artifact_paths))
    if not structured_parts:
        return ""
    return "[local_ctf_assets]\n" + "\n".join(structured_parts)


def _sync_runtime_challenge_context(
    challenge_context: dict[str, Any],
    dispatcher: Any,
) -> str:
    runtime_context = getattr(dispatcher, "_challenge_context", None)
    if not isinstance(runtime_context, dict):
        return ""
    for key in ("challengePath", "derivedTarget", "derivedTargetSource", "derivedTargetComposePath"):
        value = str(runtime_context.get(key) or "").strip()
        if value:
            challenge_context[key] = value
    artifact_paths = _normalize_string_list(runtime_context.get("artifactPaths"))
    if artifact_paths:
        challenge_context["artifactPaths"] = artifact_paths
    return str(challenge_context.get("derivedTarget") or "").strip()


async def run_cli(
    target: str,
    model: str,
    task: str = None,
    report: str = None,
    max_loops: int = AGENT_MAX_ITERATIONS,
    use_docker: bool = False,
    use_ssh: bool = False,
    mode: str = "agent",
    ctf_type: str | None = None,
    challenge_path: str | None = None,
    artifact_paths: list[str] | None = None,
    crew: bool = False,
    profile: str = "ctf",
):
    """
    Run FlagHunter in non-interactive mode.

    Args:
        target: Target to test
        model: LLM model to use
        task: Optional task description
        report: Report path ("auto" for loot/reports/<target>_<timestamp>.md)
        max_loops: Max agent loops before stopping
        use_docker: Run tools in Docker container
        use_ssh: Run tools on Kali VM via SSH
        mode: Execution mode ("agent" / "crew" / "auto" / "pentest" / "ctf")
    """
    from ..interface.initializer import has_ssh_runtime_config
    from ..session import AgentSession

    legacy_execution_mode = "crew" if mode == "crew" else "agent"
    contract = resolve_mode_contract(
        {
            "mode": mode if mode in {"auto", "pentest", "ctf"} else "",
            "ctfType": ctf_type,
        }
    )
    resolved_mode = str(contract.get("mode") or "pentest")
    resolved_subtype = str(contract.get("modeSubtype") or "").strip().lower()
    if resolved_subtype == "unknown":
        resolved_subtype = ""

    # Startup panel
    start_text = Text()
    start_text.append("FLAGHUNTER", style=f"bold {PA_PRIMARY}")
    start_text.append(" - Non-interactive Mode\n\n", style=PA_DIM)
    start_text.append("Target: ", style=PA_SECONDARY)
    start_text.append(f"{target}\n", style=PA_PRIMARY)
    start_text.append("Model: ", style=PA_SECONDARY)
    start_text.append(f"{model}\n", style=PA_PRIMARY)
    start_text.append("Mode: ", style=PA_SECONDARY)
    mode_label = resolved_mode.upper()
    if resolved_mode == "pentest" and legacy_execution_mode == "crew":
        mode_label = "PENTEST / CREW"
    elif resolved_mode == "pentest":
        mode_label = "PENTEST / AGENT"
    elif resolved_subtype and resolved_subtype != "unknown":
        mode_label = f"{mode_label} / {resolved_subtype.upper()}"
    start_text.append(f"{mode_label}\n", style=PA_PRIMARY)
    start_text.append("Runtime: ", style=PA_SECONDARY)
    runtime_label = (
        "SSH (Kali VM)"
        if use_ssh
        else "Docker"
        if use_docker
        else "Auto (SSH→Local)"
        if has_ssh_runtime_config()
        else "Local"
    )
    start_text.append(f"{runtime_label}\n", style=PA_PRIMARY)
    start_text.append("Max loops: ", style=PA_SECONDARY)
    # Show the actual max iterations used by each mode
    actual_max = ORCHESTRATOR_MAX_ITERATIONS if legacy_execution_mode == "crew" else max_loops
    start_text.append(f"{actual_max}\n", style=PA_PRIMARY)

    task_msg = task or f"Perform a penetration test on {target}"
    start_text.append("Task: ", style=PA_SECONDARY)
    start_text.append(task_msg, style=PA_PRIMARY)

    console.print()
    console.print(
        Panel(start_text, title=f"[{PA_SECONDARY}]Starting", border_style=PA_BORDER)
    )
    console.print()

    # MCP auto-connect/install has been disabled. Operators should run the
    # installation scripts under `third_party/` manually and configure
    # `mcp_servers.json` for any MCP servers they intend to use. No automatic
    # background installs or starts will be performed by the CLI.
    mcp_manager = None

    def _on_progress(level: str, msg: str) -> None:
        style = "yellow" if level == "warning" else PA_DIM
        console.print(f"[{style}]{msg}[/]")

    # Single assembly path (architecture invariant I2). AgentSession.create
    # funnels build_agent_components, so RAG, runtime, workspace activation AND
    # the CPA modules (M1-M6) all initialize for the CLI — previously the CLI
    # hand-rolled LLM/Tools/Runtime per mode and silently skipped the CPA hooks.
    session = await AgentSession.create(
        target=target,
        model=model,
        docker=use_docker,
        ssh=use_ssh,
        no_mcp=True,
        on_progress=_on_progress,
    )
    runtime = session.runtime
    runtime_info = session.runtime_info
    rag = session.rag_engine
    runtime.mcp_manager = mcp_manager
    console.print(
        f"[{PA_DIM}]Runtime resolved: {runtime_info.get('label', type(runtime).__name__)}"
        f" | {runtime_info.get('status_text', '')}[/]"
    )

    # Stats tracking
    start_time = time.time()
    tool_count = 0
    iteration = 0
    findings_count = 0  # Count of notes/findings recorded
    findings = []  # Store actual findings text
    total_tokens = 0  # Track total token usage
    messages = []  # Store agent messages
    tool_log = []  # Log of tools executed (ts, name, command, result, exit_code)
    ctf_chain: list[str] = []  # CTF dispatcher chain_used (report trace when tool_log empty)
    ctf_notes: list[str] = []  # CTF dispatcher notes log (report trace)
    last_content = ""
    last_msg_intermediate = False  # Track if previous message was intermediate (to avoid double counting tokens)
    stopped_reason = None

    def print_status(msg: str, style: str = PA_DIM):
        elapsed = int(time.time() - start_time)
        mins, secs = divmod(elapsed, 60)
        timestamp = f"[{mins:02d}:{secs:02d}]"
        console.print(f"[{PA_DIM}]{timestamp}[/] [{style}]{msg}[/]")

    def display_message(content: str, title: str) -> bool:
        """Display a message panel if it hasn't been shown yet.

        This will attempt to detect JSON or Python-dict-like content and
        pretty-print it inside a fenced JSON code block so it's readable
        in the terminal. Falls back to rendering as Markdown otherwise.
        """
        nonlocal last_content
        if not content or content == last_content:
            return False

        # Try to detect JSON first and recursively unescape nested JSON strings
        pretty_md = None

        def _parse_nested(obj):
            """Recursively parse nested JSON strings inside dicts/lists."""
            if isinstance(obj, str):
                # Quick JSON parse
                try:
                    parsed = json.loads(obj)
                    return _parse_nested(parsed)
                except Exception:
                    # Attempt to find a JSON substring (handles escaped inner JSON)
                    m = re.search(r"(\{[\s\S]*\})", obj)
                    if m:
                        try:
                            parsed = json.loads(m.group(1))
                            return _parse_nested(parsed)
                        except Exception:
                            return obj
                    return obj
            elif isinstance(obj, dict):
                return {k: _parse_nested(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_parse_nested(v) for v in obj]
            else:
                return obj

        try:
            parsed = json.loads(content)
            parsed = _parse_nested(parsed)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
            pretty_md = f"```json\n{pretty}\n```"
        except Exception:
            # Not valid JSON — try Python literal (e.g. single-quoted dict)
            try:
                parsed = ast.literal_eval(content)
                parsed = _parse_nested(parsed)
                if isinstance(parsed, (dict, list)):
                    pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
                    pretty_md = f"```json\n{pretty}\n```"
            except Exception:
                pretty_md = None

        console.print()
        if pretty_md is not None:
            # Use the already-parsed structure (may have been unescaped
            # / normalized by _parse_nested) to prefer a human-readable
            # `summary` field. Fall back to pretty JSON when no summary.
            parsed_for_summary = None
            try:
                parsed_for_summary = parsed  # set in the JSON branch above
            except NameError:
                try:
                    parsed_for_summary = ast.literal_eval(content)
                except Exception:
                    parsed_for_summary = None

            if isinstance(parsed_for_summary, dict) and isinstance(
                parsed_for_summary.get("summary"), str
            ):
                console.print(
                    Panel(
                        Markdown(parsed_for_summary.get("summary")),
                        title=f"[{PA_PRIMARY}]{title}",
                        border_style=PA_BORDER,
                    )
                )
            else:
                console.print(
                    Panel(
                        Markdown(pretty_md),
                        title=f"[{PA_PRIMARY}]{title}",
                        border_style=PA_BORDER,
                    )
                )
        else:
            console.print(
                Panel(
                    Markdown(content),
                    title=f"[{PA_PRIMARY}]{title}",
                    border_style=PA_BORDER,
                )
            )
        console.print()
        last_content = content
        return True

    def generate_report() -> str:
        """Generate markdown report."""
        elapsed = int(time.time() - start_time)
        mins, secs = divmod(elapsed, 60)

        status_text = "Complete"
        if stopped_reason:
            status_text = f"Interrupted ({stopped_reason})"

        lines = [
            "# FlagHunter Penetration Test Report",
            "",
            "## Executive Summary",
            "",
        ]

        # Add AI summary at top if available
        # If the last finding is a full report (Crew mode), use it as the main body
        # and avoid adding duplicate headers
        main_content = ""
        if findings:
            main_content = findings[-1]
            # If it's a full report (starts with #), don't add our own headers if possible
            if not main_content.strip().startswith("#"):
                lines.append(main_content)
                lines.append("")
            else:
                # It's a full report, so we might want to replace the default header
                # or just append it. Let's append it but skip the "Executive Summary" header above if we could.
                # For now, just append it.
                lines.append(main_content)
                lines.append("")
        else:
            lines.append("*Assessment incomplete - no analysis generated.*")
            lines.append("")

        # Engagement details table
        lines.extend(
            [
                "## Engagement Details",
                "",
                "| Field | Value |",
                "|-------|-------|",
                f"| **Target** | `{target}` |",
                f"| **Task** | {task_msg} |",
                f"| **Date** | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |",
                f"| **Duration** | {mins}m {secs}s |",
                f"| **Commands Executed** | {tool_count} |",
                f"| **Status** | {status_text} |",
                "",
                "---",
                "",
                "## Commands Executed",
                "",
            ]
        )

        # Detailed command log
        for i, entry in enumerate(tool_log, 1):
            ts = entry.get("ts", "??:??")
            name = entry.get("name", "unknown")
            command = entry.get("command", "")
            result = entry.get("result", "")
            exit_code = entry.get("exit_code")

            lines.append(f"### {i}. {name} `[{ts}]`")
            lines.append("")

            if command:
                lines.append("**Command:**")
                lines.append("```")
                lines.append(command)
                lines.append("```")
                lines.append("")

            if exit_code is not None:
                lines.append(f"**Exit Code:** `{exit_code}`")
                lines.append("")

            if result:
                lines.append("**Output:**")
                lines.append("```")
                # Limit output to 2000 chars per command for report size
                if len(result) > 2000:
                    lines.append(result[:2000])
                    lines.append(f"\n... (truncated, {len(result)} total chars)")
                else:
                    lines.append(result)
                lines.append("```")
                lines.append("")

        # CTF solve chain — the dispatcher fast path emits chain_used/notes rather than
        # tool_log entries, so without this the report shows "Commands Executed: 0" and
        # no trace. Render the chain + note trace when present.
        if ctf_chain or ctf_notes:
            lines.extend(["---", "", "## CTF Solve Chain", ""])
            if ctf_chain:
                lines.append("**Chain used:** " + " → ".join(ctf_chain))
                lines.append("")
            if ctf_notes:
                lines.append("**Trace:**")
                lines.append("")
                for n in ctf_notes:
                    lines.append(f"- {n}")
                lines.append("")

        # Findings section
        # Only show if there are other findings besides the final report we already showed
        other_findings = findings[:-1] if findings and len(findings) > 1 else []

        if other_findings:
            lines.extend(
                [
                    "---",
                    "",
                    "## Detailed Findings",
                    "",
                ]
            )

            for i, finding in enumerate(other_findings, 1):
                if len(other_findings) > 1:
                    lines.append(f"### Finding {i}")
                    lines.append("")
                lines.append(finding)
                lines.append("")

        # Footer
        lines.extend(
            [
                "---",
                "",
                f"*Report generated by FlagHunter on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            ]
        )

        return "\n".join(lines)

    def save_report():
        """Save report to file."""
        if not report:
            return

        # Determine path
        if report == "auto":
            reports_dir = Path("loot/reports")
            reports_dir.mkdir(parents=True, exist_ok=True)
            safe_target = target.replace("://", "_").replace("/", "_").replace(":", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = reports_dir / f"{safe_target}_{timestamp}.md"
        else:
            report_path = Path(report)
            report_path.parent.mkdir(parents=True, exist_ok=True)

        content = generate_report()
        report_path.write_text(content, encoding="utf-8")
        console.print(f"[{PA_SECONDARY}]Report saved: {report_path}[/]")

    async def generate_summary():
        """Ask the LLM to summarize findings when stopped early."""
        if not tool_log:
            return None

        print_status("Generating summary...", PA_SECONDARY)

        # Build context from tool results (use full results, not truncated)
        context_lines = ["Summarize the penetration test findings so far:\n"]
        context_lines.append(f"Target: {target}")
        context_lines.append(f"Tools executed: {tool_count}\n")

        for entry in tool_log[-10:]:  # Last 10 tools
            name = entry.get("name", "unknown")
            command = entry.get("command", "")
            result = entry.get("result", "")[:500]  # Limit for context window
            context_lines.append(f"- **{name}**: `{command}`")
            if result:
                context_lines.append(f"  Output: {result}")

        context_lines.append(
            "\nProvide a brief summary of what was discovered and any security concerns found."
        )

        try:
            response = await llm.generate(
                system_prompt="You are a penetration testing assistant. Summarize the findings concisely.",
                messages=[{"role": "user", "content": "\n".join(context_lines)}],
                tools=[],
                task_hint="tool_parse",
            )
            content = response.content or ""
            # Prefer structured JSON 'summary' if present
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict) and isinstance(parsed.get("summary"), str):
                    return parsed.get("summary")
            except Exception:
                pass

            return content
        except Exception:
            return None

    async def print_summary(interrupted: bool = False):
        nonlocal messages

        # Generate summary if we don't have messages yet
        if not messages and tool_log:
            summary = await generate_summary()
            if summary:
                messages.append(summary)

        elapsed = int(time.time() - start_time)
        mins, secs = divmod(elapsed, 60)

        title = "Interrupted" if interrupted else "Finished"
        status = "PARTIAL RESULTS" if interrupted else "COMPLETE"
        if stopped_reason:
            status = f"STOPPED ({stopped_reason})"

        final_text = Text()
        final_text.append(f"{status}\n\n", style=f"bold {PA_PRIMARY}")
        final_text.append("Duration: ", style=PA_DIM)
        final_text.append(f"{mins}m {secs}s\n", style=PA_SECONDARY)
        final_text.append("Loops: ", style=PA_DIM)
        final_text.append(f"{iteration}/{max_loops}\n", style=PA_SECONDARY)
        final_text.append("Tools: ", style=PA_DIM)
        final_text.append(f"{tool_count}\n", style=PA_SECONDARY)

        if total_tokens > 0:
            final_text.append("Tokens: ", style=PA_DIM)
            final_text.append(f"{total_tokens:,}\n", style=PA_SECONDARY)

        if findings_count > 0:
            final_text.append("Findings: ", style=PA_DIM)
            final_text.append(f"{findings_count}", style=PA_SECONDARY)

        console.print()
        console.print(
            Panel(
                final_text,
                title=f"[{PA_SECONDARY}]{title}",
                border_style=PA_BORDER,
            )
        )

        # Show summary/messages only if it's new content (not just displayed)
        if messages:
            display_message(messages[-1], "Summary")

        # Save report
        save_report()

    print_status("Initializing...")

    try:
        if resolved_mode == "ctf":
            from ..agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

            cli_control_decision = resolve_control_decision(
                {
                    "mode": resolved_mode,
                    "target": target,
                    "challengePath": str(challenge_path or "").strip(),
                    "artifactPaths": _normalize_string_list(artifact_paths),
                }
            )
            llm = session.llm
            dispatcher_hint = _ctf_dispatcher_hint(
                challenge_path=challenge_path,
                artifact_paths=artifact_paths,
                control_decision=cli_control_decision,
            )
            cli_challenge_context = {
                "challengePath": str(challenge_path or "").strip() or None,
                "artifactPaths": _normalize_string_list(artifact_paths),
            }
            if crew:
                # CTF crew (multi-worker via CTFCrewCoordinator) — previously
                # TUI-only; the shared headless runner gives CLI/web parity (D4).
                from ..agents.pa_agent.ctf_crew_runner import run_ctf_crew_solve

                print_status("CTF crew mode (multi-worker)", PA_ACCENT)
                solve_result, crew_dispatcher = await run_ctf_crew_solve(
                    runtime=runtime,
                    llm=llm,
                    target=target,
                    goal=task_msg,
                    chtype=resolved_subtype or "auto",
                    hint=dispatcher_hint,
                    challenge_context=cli_challenge_context,
                    progress_callback=lambda message: print_status(str(message), PA_DIM),
                    worker_event=lambda wid, evt, data: print_status(
                        f"[crew:{wid}] {evt}" + (f" ({data})" if data else ""), PA_DIM
                    ),
                    profile=profile,
                )
                derived_target = _sync_runtime_challenge_context(cli_challenge_context, crew_dispatcher)
            else:
                dispatcher = CTFTaskDispatcher(
                    runtime=runtime,
                    progress_callback=lambda message: print_status(str(message), PA_DIM),
                    llm=llm,
                    profile=profile,
                )
                solve_result = await dispatcher.run(
                    target=target,
                    goal=task_msg,
                    type=resolved_subtype or "auto",
                    hint=dispatcher_hint,
                    challenge_context=cli_challenge_context,
                )
                derived_target = _sync_runtime_challenge_context(cli_challenge_context, dispatcher)
            if derived_target and not str(target or "").strip():
                target = derived_target
                print_status(f"Derived target resolved: {derived_target}", PA_DIM)
            # Phase 0: 把 dispatcher 的真实活动回填到对外 Loops/Tools 计数。CTF 快路径不走
            # agent base-loop,iteration/tool_count 原本恒为 0 → 报告失真(18 次 LLM + ~10 次
            # HTTP 显示为 Loops 0 / Commands 0)。读 dispatcher.activity_metrics() 还原真相。
            active_dispatcher = crew_dispatcher if crew else dispatcher
            _metrics_fn = getattr(active_dispatcher, "activity_metrics", None)
            if callable(_metrics_fn):
                try:
                    _ctf_metrics = _metrics_fn()
                    iteration = int(_ctf_metrics.get("loops", 0) or 0)
                    tool_count = int(_ctf_metrics.get("tool_calls", 0) or 0)
                except Exception:
                    pass
            result_text = str(getattr(solve_result, "flag", "") or getattr(solve_result, "reason", "") or "")
            if result_text:
                messages.append(result_text)
                display_message(result_text, "CTF Result")
            if getattr(solve_result, "flag", None):
                print_status(f"Flag verified: {getattr(solve_result, 'flag')}", "green")
            elif getattr(solve_result, "reason", None):
                print_status(f"CTF stop reason: {getattr(solve_result, 'reason')}", "yellow")
            # 修复快路径报告偏薄:dispatcher 解题走 chain/notes 而非 tool_log,
            # 把链路喂进报告(generate_report 渲染为 "CTF Solve Chain" 段)。
            try:
                ctf_chain[:] = [str(c) for c in (getattr(solve_result, "chain_used", []) or [])]
                ctf_notes[:] = [str(n) for n in (getattr(solve_result, "notes", []) or [])]
            except Exception:
                pass
            # 数据治理第②层自动回填:成功解题写入 knowledge/ctf_sessions/。dispatcher 快
            # 路径(0 loop)不经 agent-loop 的 finish 工具,原来漏挂回填 → 知识库无本题草稿。
            # 放在真实 CLI 入口而非 dispatcher 内,避免单元测试驱动 dispatcher 时污染 RAG。
            if getattr(solve_result, "success", False) and str(getattr(solve_result, "flag", "") or "").strip():
                try:
                    from ..knowledge.ctf_experience import save_ctf_experience

                    await save_ctf_experience(
                        url=str(target or ""),
                        chtype=resolved_subtype or "web",
                        hint=str(dispatcher_hint or ""),
                        flag=str(getattr(solve_result, "flag", "") or ""),
                        successful_steps=(ctf_chain or ctf_notes),
                        failed_steps=[],
                    )
                except Exception:
                    pass
            # 设计 §2④ —— 曲库外 miss(repertoire_miss 且未解)落 candidate radar inbox,让
            # miss 变可累积资产(对标参考库 candidate radar)。镜像上面的成功回填:同样放 CLI
            # 入口而非 dispatcher 内避免污染测试,全程 try/except 不影响解题结果。
            elif not getattr(solve_result, "success", False):
                try:
                    _miss_state = getattr(active_dispatcher, "state", None)
                    if _miss_state is not None and getattr(_miss_state, "repertoire_miss", False):
                        from ..knowledge.repertoire_radar import record_repertoire_miss

                        record_repertoire_miss(
                            target=str(target or ""),
                            detected_type=str(
                                getattr(_miss_state, "detected_type", "") or resolved_subtype or ""
                            ),
                            triggered_probes=ctf_chain or [],
                            hypothesis_kinds=[
                                getattr(h, "kind", "")
                                for h in (getattr(_miss_state, "hypotheses", []) or [])
                            ],
                            observation_kinds=[
                                getattr(o, "kind", "")
                                for o in (getattr(_miss_state, "observations", []) or [])
                            ],
                            reason=str(getattr(solve_result, "reason", "") or "repertoire_miss"),
                        )
                except Exception:
                    pass

        elif legacy_execution_mode == "crew":
            llm = session.llm
            tools = session.tools
            from ..agents.crew import CrewOrchestrator

            def on_worker_event(worker_id: str, event_type: str, data: dict):
                nonlocal tool_count, findings_count, total_tokens

                if event_type == "spawn":
                    task = data.get("task", "")
                    print_status(f"Spawned worker {worker_id}: {task}", PA_ACCENT)

                elif event_type == "tool":
                    tool_name = data.get("tool", "unknown")
                    tool_count += 1
                    print_status(f"Worker {worker_id} using tool: {tool_name}", PA_DIM)

                    # Log tool usage (limited info available from event)
                    elapsed = int(time.time() - start_time)
                    mins, secs = divmod(elapsed, 60)
                    ts = f"{mins:02d}:{secs:02d}"

                    tool_log.append(
                        {
                            "ts": ts,
                            "name": tool_name,
                            "command": f"(Worker {worker_id})",
                            "result": "",
                            "exit_code": None,
                        }
                    )

                elif event_type == "tokens":
                    tokens = data.get("tokens", 0)
                    total_tokens += tokens

                elif event_type == "complete":
                    f_count = data.get("findings_count", 0)
                    findings_count += f_count
                    print_status(
                        f"Worker {worker_id} complete ({f_count} findings)", "green"
                    )

                elif event_type == "failed":
                    reason = data.get("reason", "unknown")
                    print_status(f"Worker {worker_id} failed: {reason}", "red")

                elif event_type == "status":
                    status = data.get("status", "")
                    print_status(f"Worker {worker_id} status: {status}", PA_DIM)

                elif event_type == "warning":
                    reason = data.get("reason", "unknown")
                    print_status(f"Worker {worker_id} warning: {reason}", "yellow")

                elif event_type == "error":
                    error = data.get("error", "unknown")
                    print_status(f"Worker {worker_id} error: {error}", "red")

                elif event_type == "cancelled":
                    print_status(f"Worker {worker_id} cancelled", "yellow")

            crew = CrewOrchestrator(
                llm=llm,
                tools=tools,
                runtime=runtime,
                on_worker_event=on_worker_event,
                rag_engine=rag,
                target=target,
            )

            async for update in crew.run(task_msg):
                iteration += 1
                phase = update.get("phase", "")

                if phase == "starting":
                    print_status("Crew orchestrator starting...", PA_PRIMARY)

                elif phase == "thinking":
                    content = update.get("content", "")
                    if content:
                        display_message(content, "FlagHunter Plan")

                elif phase == "tool_call":
                    tool = update.get("tool", "")
                    args = update.get("args", {})
                    print_status(f"Orchestrator calling: {tool}", PA_ACCENT)

                elif phase == "complete":
                    report_content = update.get("report", "")
                    if report_content:
                        messages.append(report_content)
                        findings.append(
                            report_content
                        )  # Add to findings so it appears in the saved report
                        display_message(report_content, "Crew Report")

                elif phase == "error":
                    error = update.get("error", "Unknown error")
                    print_status(f"Crew error: {error}", "red")

                if iteration >= max_loops:
                    stopped_reason = "max loops reached"
                    raise StopIteration()

        else:
            # Default Agent Mode — reuse the agent assembled by AgentSession
            # (built through the single composition root, so CPA hooks ran).
            agent = session.agent

            async for response in agent.agent_loop(task_msg):
                iteration += 1

                # Track token usage
                if response.usage:
                    usage = response.usage.get("total_tokens", 0)
                    is_intermediate = response.metadata.get("intermediate", False)
                    has_tools = bool(response.tool_calls)

                    # Logic to avoid double counting:
                    # 1. Intermediate messages (thinking) always count
                    # 2. Tool messages count ONLY if not preceded by intermediate message
                    if is_intermediate:
                        total_tokens += usage
                        last_msg_intermediate = True
                    elif has_tools:
                        if not last_msg_intermediate:
                            total_tokens += usage
                        last_msg_intermediate = False
                    else:
                        # Other messages (like plan)
                        total_tokens += usage
                        last_msg_intermediate = False

                # Show tool calls and results as they happen
                if response.tool_calls:
                    for i, call in enumerate(response.tool_calls):
                        tool_count += 1
                        name = getattr(call, "name", None) or getattr(
                            call.function, "name", "tool"
                        )

                        # Track findings (notes tool)
                        if name == "notes":
                            findings_count += 1
                            try:
                                args = getattr(call, "arguments", None) or getattr(
                                    call.function, "arguments", "{}"
                                )
                                if isinstance(args, str):
                                    import json

                                    args = json.loads(args)
                                if isinstance(args, dict):
                                    note_content = (
                                        args.get("value", "")
                                        or args.get("content", "")
                                        or args.get("note", "")
                                    )
                                    if note_content:
                                        findings.append(note_content)
                            except Exception:
                                pass

                        elapsed = int(time.time() - start_time)
                        mins, secs = divmod(elapsed, 60)
                        ts = f"{mins:02d}:{secs:02d}"

                        # Get result if available
                        if response.tool_results and i < len(response.tool_results):
                            tr = response.tool_results[i]
                            result_text = tr.result or tr.error or ""
                            if result_text:
                                # Truncate for display
                                preview = result_text[:200].replace("\n", " ")
                                if len(result_text) > 200:
                                    preview += "..."

                        # Parse args for command extraction
                        command_text = ""
                        exit_code = None
                        try:
                            args = getattr(call, "arguments", None) or getattr(
                                call.function, "arguments", "{}"
                            )
                            if isinstance(args, str):
                                import json

                                args = json.loads(args)
                            if isinstance(args, dict):
                                command_text = args.get("command", "")
                        except Exception:
                            pass

                        # Extract exit code from result
                        if response.tool_results and i < len(response.tool_results):
                            tr = response.tool_results[i]
                            full_result = tr.result or tr.error or ""
                            # Try to parse exit code
                            if "Exit Code:" in full_result:
                                try:
                                    import re

                                    match = re.search(
                                        r"Exit Code:\s*(\d+)", full_result
                                    )
                                    if match:
                                        exit_code = int(match.group(1))
                                except Exception:
                                    pass
                        else:
                            full_result = ""

                        # Store full data for report (not truncated)
                        tool_log.append(
                            {
                                "ts": ts,
                                "name": name,
                                "command": command_text,
                                "result": full_result,
                                "exit_code": exit_code,
                            }
                        )

                        # Metasploit-style output with better spacing
                        console.print()  # Blank line before each tool
                        print_status(f"$ {name} ({tool_count})", PA_ACCENT)

                        # Show command/args on separate indented line (truncated for display)
                        if command_text:
                            display_cmd = command_text[:80]
                            if len(command_text) > 80:
                                display_cmd += "..."
                            console.print(f"         [{PA_DIM}]{display_cmd}[/]")

                        # Show result on separate line with status indicator
                        if response.tool_results and i < len(response.tool_results):
                            tr = response.tool_results[i]
                            if tr.error:
                                console.print(
                                    f"         [{PA_DIM}][!] {tr.error[:100]}[/]"
                                )
                            elif tr.result:
                                # Show exit code or brief result
                                result_line = tr.result[:100].replace("\n", " ")
                                if exit_code == 0 or "success" in result_line.lower():
                                    console.print(f"         [{PA_DIM}][+] OK[/]")
                                elif exit_code is not None and exit_code != 0:
                                    console.print(
                                        f"         [{PA_DIM}][-] Exit {exit_code}[/]"
                                    )
                                else:
                                    console.print(
                                        f"         [{PA_DIM}][*] {result_line[:60]}...[/]"
                                    )

                # Print assistant content immediately (analysis/findings)
                if response.content:
                    if display_message(response.content, "FlagHunter"):
                        messages.append(response.content)

                # Check max loops limit
                if iteration >= max_loops:
                    stopped_reason = "max loops reached"
                    console.print()
                    print_status(f"Max loops limit reached ({max_loops})", "yellow")
                    raise StopIteration()

        # In agent mode, ensure the final message is treated as the main finding (Executive Summary)
        if mode != "crew" and messages:
            findings.append(messages[-1])

        await print_summary(interrupted=False)

    except StopIteration:
        await print_summary(interrupted=True)
    except (KeyboardInterrupt, asyncio.CancelledError):
        stopped_reason = "user interrupt"
        await print_summary(interrupted=True)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/]")
        stopped_reason = f"error: {e}"
        await print_summary(interrupted=True)

    finally:
        # Cleanup MCP connections first
        if mcp_manager:
            try:
                await mcp_manager.disconnect_all()
                await asyncio.sleep(0.1)  # Allow transports to close cleanly
            except Exception:
                pass

        # Then stop runtime
        if runtime:
            try:
                await runtime.stop()
            except Exception:
                pass
