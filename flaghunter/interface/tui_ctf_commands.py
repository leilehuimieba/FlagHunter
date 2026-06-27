"""CTF /ctf command parsing + launch pipeline mixed into FlagHunterTUI (债池五波·TUI 刀 18, god-class).

Extracted from tui.py (three regions of the same feature). The big ``_parse_ctf_command``
/ctf dispatcher (fast CTF mode + CPA M2 CTF Kit, with its CPA M2 hook markers), the
CTF-source helpers (``_auto_detect_ctf_src`` / ``_read_ctf_source_context``), and the
launch pipeline (``_refresh_last_ctf_capabilities`` / ``_parse_ctf_launch_request`` /
``_prepare_ctf_hint_with_source`` / ``_start_ctf_execution`` / ``_merge_ctf_hint_text`` /
``_build_ctf_resume_autonomy_state``). These call each other plus stay-behind helpers
(``self._add_*`` / ``_run_ctf_dispatcher_mode`` / ``_render_last_ctf_*``) resolved at
runtime through the FlagHunterTUI instance MRO; the stay-behind ``_handle_command``
dispatches ``self._parse_ctf_command`` the same way. Module-level deps: ``re`` / ``time``
/ ``Any``; pathlib / shlex / urlparse / notes / CTF Kit / capability backends are all
lazy inside the bodies. No decorators.
"""

from __future__ import annotations

import re
import time
from typing import Any


class CtfCommandMixin:
    """CTF /ctf command parsing + launch pipeline for FlagHunterTUI."""

    def _auto_detect_ctf_src(self, url: str) -> str:
        """Try to find a local source directory that matches the given CTF URL.

        Heuristic: if url is localhost:<port>, search CTF_SEARCH_ROOTS for a
        directory containing a package.json / app.py / index.js / Dockerfile
        that listens on that port (or has the port in docker-compose.yml).
        Returns the best matching directory path, or "".
        """
        import re, pathlib
        m = re.match(r"https?://(?:localhost|127\.0\.0\.1):(\d+)", url)
        if not m:
            return ""
        port = m.group(1)

        for root_str in self._CTF_SEARCH_ROOTS:
            root = pathlib.Path(root_str).expanduser()
            if not root.exists():
                continue
            for candidate in root.rglob("*"):
                if not candidate.is_dir():
                    continue
                if any(skip in candidate.parts for skip in self._CTF_SKIP_DIRS):
                    continue
                # Check if this dir has a source marker file
                markers = ["package.json", "app.py", "main.py", "index.js",
                           "app.js", "server.js", "Dockerfile", "docker-compose.yml"]
                has_marker = any((candidate / m).exists() for m in markers)
                if not has_marker:
                    continue
                # Check if port is referenced in key files
                for fname in ["package.json", "app.py", "index.js", "app.js",
                              "server.js", "Dockerfile", "docker-compose.yml", "docker-compose.yaml"]:
                    fpath = candidate / fname
                    if fpath.exists():
                        try:
                            text = fpath.read_text(encoding="utf-8", errors="ignore")
                            if port in text:
                                return str(candidate)
                        except Exception:
                            pass
        return ""

    def _read_ctf_source_context(self, src_dir, max_files: int = 12, max_bytes_per_file: int = 4000) -> str:
        """Read key source files from src_dir and return a formatted string for LLM context.

        Strategy:
        1. Enumerate files with CTF-relevant extensions, skip skip-dirs
        2. Prioritise small, top-level, and obviously interesting files
        3. Cap each file at max_bytes_per_file, total at max_files
        """
        import pathlib

        src_dir = pathlib.Path(src_dir)
        collected: list[tuple[int, pathlib.Path]] = []  # (depth, path)

        for fpath in src_dir.rglob("*"):
            if fpath.is_dir():
                continue
            if any(skip in fpath.parts for skip in self._CTF_SKIP_DIRS):
                continue
            suffix = fpath.suffix.lower()
            name = fpath.name
            if suffix not in self._CTF_SRC_EXTS and name not in self._CTF_SRC_EXTS:
                continue
            depth = len(fpath.relative_to(src_dir).parts)
            collected.append((depth, fpath))

        # Sort: shallow first, then alphabetical
        collected.sort(key=lambda x: (x[0], x[1].name))

        parts = [f"\n[CTF Source: {src_dir}]"]
        shown = 0
        for depth, fpath in collected:
            if shown >= max_files:
                parts.append(f"  ... (truncated, showing {max_files} of {len(collected)} files)")
                break
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if not text.strip():
                continue
            rel = fpath.relative_to(src_dir)
            if len(text) > max_bytes_per_file:
                text = text[:max_bytes_per_file] + f"\n... [{len(text) - max_bytes_per_file} bytes truncated]"
            parts.append(f"\n--- {rel} ---\n{text}")
            shown += 1

        parts.append("\n[/CTF Source]\n")
        return "\n".join(parts)

    # === CPA M2 HOOK BEGIN ===
    async def _parse_ctf_command(self, cmd: str) -> None:
        """Handle /ctf commands for fast CTF mode or CPA M2 CTF Kit."""
        import shlex

        rest = cmd[len("/ctf") :].strip()
        if not rest:
            try:
                from flaghunter.cpa_modules.m2_ctf_kit import ctf_commands as _ctf
            except Exception as exc:
                self._add_system(f"[CPA M2] Not initialized: {exc}")
                return
            try:
                result = await _ctf.cmd_ctf()
            except Exception as exc:
                result = f"[CPA M2] Error: {exc}"
            self._add_system(result)
            return

        try:
            parts = shlex.split(rest)
        except ValueError as exc:
            self._add_system(f"[!] Parse error: {exc}")
            return

        sub = parts[0].lower() if parts else ""
        ctf_subcommands = {
            "crew",
            "list",
            "run",
            "phase",
            "next",
            "flag",
            "hint",
            "override",
            "wrong",
            "reasoning",
            "capabilities",
            "memory",
            "queue",
            "pwn",
            "decode",
            "rev",
            "status",
        }
        is_ctf_agent_mode = bool(parts) and sub not in ctf_subcommands

        if is_ctf_agent_mode or sub == "crew":
            execution_mode = "crew" if sub == "crew" else "dispatcher"
            launch_tokens = parts[1:] if sub == "crew" else parts
            launch_request = self._parse_ctf_launch_request(launch_tokens)
            url = str(launch_request.get("url") or "").strip()
            chtype = str(launch_request.get("type") or "auto")
            goal = str(launch_request.get("goal") or "拿到flag")
            hint = str(launch_request.get("hint") or "")
            src_path = str(launch_request.get("src_path") or "")
            submit_profile = dict(launch_request.get("submit_profile") or {})
            runner_config = dict(launch_request.get("runner_config") or {})

            if not url:
                self._add_system(
                    'Usage: /ctf <url> [type=auto|web|sqli|xss|lfi|cmdi|ssrf|upload|crypto|pwn|misc] [goal="拿到flag"] [hint="..."] [src=<dir>] [submit=auto] [platform=ctfd] [challenge_id=123] [submit_url=https://ctf.example.com] [queue=single|switch|drain] [max_challenges=4] [timebox=900] [max_stops=2]\n'
                    '       /ctf crew <url> [type=...] [goal="拿到flag"] [hint="..."]\n'
                    "Example: /ctf http://localhost:3000 type=xss goal=\"拿到flag\"\n"
                    "         /ctf crew http://localhost:3000 type=sqli goal=\"拿到flag\"\n"
                    "         /ctf http://dvwa.local/ type=sqli src=D:/webstudy/CTF/easy_login\n"
                    "         /ctf https://target.local type=web submit=auto platform=ctfd challenge_id=42 submit_url=https://ctf.example.com queue=drain max_challenges=6 timebox=1200"
                )
                return

            effective_hint, effective_src_path = self._prepare_ctf_hint_with_source(
                url=url,
                hint=hint,
                src_path=src_path,
            )

            self._set_status("idle", "agent")
            self._update_header()
            self._add_system(
                "Changed to CTF crew mode\n"
                if execution_mode == "crew"
                else "Changed to CTF dispatcher mode\n"
            )
            self._add_user(cmd)
            try:
                from urllib.parse import urlparse as _urlparse

                _p = _urlparse(url)
                _target_host = _p.netloc or _p.path
            except Exception:
                _target_host = url
            self._set_target(f"/target {_target_host}")
            self._add_system(">> CTF Crew Mode" if execution_mode == "crew" else ">> CTF Mode")
            if execution_mode == "crew":
                self._show_sidebar()
            else:
                self._hide_sidebar()

            if (self.runtime or self.agent) and not self._is_running:
                self._last_ctf_context = {
                    "url": url,
                    "goal": goal,
                    "type": chtype,
                    "hint": effective_hint,
                    "src_path": effective_src_path,
                    "submit_profile": dict(submit_profile),
                    "runner_config": dict(runner_config),
                    "execution_mode": execution_mode,
                }
                self._current_worker = self._start_ctf_execution(
                    execution_mode=execution_mode,
                    url=url,
                    goal=goal,
                    chtype=chtype,
                    hint=effective_hint,
                    submit_profile=dict(submit_profile),
                    runner_config=dict(runner_config),
                )
            return

        if sub == "reasoning":
            reasoning_args = parts[1:]
            mode = "summary"
            limit = 5
            idx = 0
            while idx < len(reasoning_args):
                token = str(reasoning_args[idx]).strip().lower()
                if token == "surprises":
                    mode = "surprises"
                elif token == "postmortem":
                    mode = "postmortem"
                elif token == "-n" and idx + 1 < len(reasoning_args):
                    try:
                        limit = max(1, int(reasoning_args[idx + 1]))
                    except Exception:
                        pass
                    idx += 1
                idx += 1
            self._add_system(self._render_last_ctf_reasoning(mode=mode, limit=limit))
            return
        if sub == "capabilities":
            refresh = any(str(token).strip().lower() == "--refresh" for token in parts[1:])
            if refresh:
                await self._refresh_last_ctf_capabilities()
            self._add_system(self._render_last_ctf_capabilities())
            return
        if sub == "memory":
            self._add_system(await self._handle_ctf_memory_subcommand(parts[1:]))
            return
        if sub == "queue":
            self._add_system(self._render_last_ctf_queue())
            return
        if sub == "status":
            self._add_system(self._render_last_ctf_status())
            return
        if sub == "hint":
            if len(parts) < 2:
                self._add_system("[CTF] Usage: /ctf hint <text>")
                return
            user_hint = " ".join(parts[1:]).strip()
            runtime = self.runtime or getattr(self.agent, "runtime", None)
            try:
                from ..tools.notes import notes as _notes_tool

                safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", user_hint).strip("._-")[:80]
                await _notes_tool(
                    {
                        "action": "update",
                        "key": f"ctf_hint_{safe_key or 'operator_hint'}",
                        "value": f"Operator hint: {user_hint}",
                        "category": "task",
                        "confidence": "high",
                        "target": getattr(self, "target", "") or "ctf",
                    },
                    runtime=runtime,
                )
            except Exception as exc:
                self._add_system(f"[CTF] Failed to record hint: {exc}")
                return

            merged_hint = self._apply_ctf_user_hint(user_hint)
            self._add_system(
                "\n".join(
                    [
                        "[CTF hint]",
                        f"- recorded_hint: {user_hint}",
                        "- priority: high",
                    ]
                )
            )
            last_ctx = getattr(self, "_last_ctf_context", None) or {}
            if last_ctx and not self._is_running:
                last_ctx["hint"] = merged_hint
                self._last_ctf_context = last_ctx
                self._add_system("[CTF] 已记录 hint，基于上次上下文继续执行。")
                resumed_runner_config = dict(last_ctx.get("runner_config") or {})
                resume_state = self._build_ctf_resume_autonomy_state(last_ctx)
                if isinstance(resume_state, dict):
                    resumed_runner_config["_autonomy_resume_state"] = resume_state
                    resumed_runner_config["_autonomy_resume_reason"] = "operator_hint_restart"
                self._current_worker = self._start_ctf_execution(
                    execution_mode=str(last_ctx.get("execution_mode") or "dispatcher"),
                    url=last_ctx.get("url", ""),
                    goal=last_ctx.get("goal", "拿到flag"),
                    chtype=last_ctx.get("type", "auto"),
                    hint=merged_hint,
                    submit_profile=dict(last_ctx.get("submit_profile") or {}),
                    runner_config=resumed_runner_config,
                )
                return

            self._add_system("[CTF] 已记录 hint；下次 /ctf 运行时会注入该方向。")
            return
        if sub == "override":
            if len(parts) < 2:
                self._add_system("[CTF] Usage: /ctf override <flag>")
                return
            override_flag = parts[1].strip()
            runtime = self.runtime or getattr(self.agent, "runtime", None)
            try:
                from ..tools.notes import notes as _notes_tool

                safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", override_flag).strip("._-")[:80]
                await _notes_tool(
                    {
                        "action": "update",
                        "key": f"ctf_override_flag_{safe_key or 'verified'}",
                        "value": f"Operator override verified flag: {override_flag}",
                        "category": "artifact",
                        "confidence": "high",
                        "target": getattr(self, "target", "") or "ctf",
                    },
                    runtime=runtime,
                )
            except Exception as exc:
                self._add_system(f"[CTF] Failed to record override flag: {exc}")
                return

            summary = self._apply_ctf_override_flag(override_flag)
            self._add_system(summary)
            return
        if sub == "wrong":
            if len(parts) < 2:
                self._add_system("[CTF] Usage: /ctf wrong <flag>")
                return
            wrong_flag = parts[1].strip()
            runtime = self.runtime or getattr(self.agent, "runtime", None)
            try:
                from ..tools.notes import notes as _notes_tool

                safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", wrong_flag).strip("._-")[:80]
                await _notes_tool(
                    {
                        "action": "update",
                        "key": f"ctf_wrong_flag_{safe_key or 'rejected'}",
                        "value": f"Rejected submitted flag: {wrong_flag}",
                        "category": "task",
                        "confidence": "high",
                        "target": getattr(self, "target", "") or "ctf",
                    },
                    runtime=runtime,
                )
            except Exception as exc:
                self._add_system(f"[CTF] Failed to record wrong flag: {exc}")
                return

            recovery_summary = await self._apply_ctf_wrong_flag_feedback(wrong_flag)
            self._add_system(recovery_summary)
            self._show_ctf_memory_panel(
                filter_mode="audit",
                sort_by="correlation",
                threshold=0.6,
            )
            last_ctx = getattr(self, "_last_ctf_context", None) or {}
            if last_ctx and not self._is_running:
                retry_hint = str(last_ctx.get("hint") or "").strip()
                retry_hint = (
                    retry_hint + "\n\n"
                    if retry_hint
                    else ""
                ) + (
                    f"[Rejected flag feedback]\n"
                    f"- The previously extracted flag `{wrong_flag}` was rejected.\n"
                    f"- Do NOT stop on that candidate again.\n"
                    f"- Re-open strategy memory in audit mode before trusting the previous winning chain.\n"
                    f"- Continue deeper exploitation from the strongest runtime-backed primitive."
                )
                self._add_system("[CTF] 已记录错误 flag，已切到 memory audit 视图，并基于上次上下文继续深挖。")
                resumed_runner_config = dict(last_ctx.get("runner_config") or {})
                resume_state = self._build_ctf_resume_autonomy_state(last_ctx)
                if isinstance(resume_state, dict):
                    resumed_runner_config["_autonomy_resume_state"] = resume_state
                    resumed_runner_config["_autonomy_resume_reason"] = (
                        "wrong_flag_feedback_restart"
                    )
                self._current_worker = self._start_ctf_execution(
                    execution_mode=str(last_ctx.get("execution_mode") or "dispatcher"),
                    url=last_ctx.get("url", ""),
                    goal=last_ctx.get("goal", "拿到flag"),
                    chtype=last_ctx.get("type", "auto"),
                    hint=retry_hint,
                    submit_profile=dict(last_ctx.get("submit_profile") or {}),
                    runner_config=resumed_runner_config,
                )
                return

            self._add_system(f"[CTF] 已记录错误 flag: {wrong_flag}\n下次 /ctf 运行时会自动忽略它；如需立即继续，请重新执行原 /ctf 命令。")
            return

        try:
            from flaghunter.cpa_modules.m2_ctf_kit import ctf_commands as _ctf
        except Exception as exc:
            self._add_system(f"[CPA M2] Not initialized: {exc}")
            return

        try:
            if sub == "list":
                result = await _ctf.cmd_ctf_list()
            elif sub == "run":
                if len(parts) < 3:
                    self._add_system("[CPA M2] Usage: /ctf run <playbook> <target>")
                    return
                result = await _ctf.cmd_ctf_run(parts[1], parts[2])
            elif sub == "phase":
                result = await _ctf.cmd_ctf_phase()
            elif sub == "next":
                result = await _ctf.cmd_ctf_next()
            elif sub == "flag":
                if len(parts) < 2:
                    self._add_system("[CPA M2] Usage: /ctf flag <flag> [challenge_id]")
                    return
                cid = parts[2] if len(parts) >= 3 else None
                result = await _ctf.cmd_ctf_flag(parts[1], challenge_id=cid)
                lowered_result = str(result or "").lower()
                if any(marker in lowered_result for marker in ("rejected", "flag 错误", "wrong")):
                    recovery_summary = await self._apply_ctf_wrong_flag_feedback(parts[1])
                    self._add_system(recovery_summary)
                    self._show_ctf_memory_panel(
                        filter_mode="audit",
                        sort_by="correlation",
                        threshold=0.6,
                    )
            elif sub == "pwn":
                if len(parts) < 3:
                    self._add_system("[CPA M2] Usage: /ctf pwn <host> <port>")
                    return
                result = await _ctf.cmd_ctf_pwn(parts[1], int(parts[2]))
            elif sub == "decode":
                if len(parts) < 2:
                    self._add_system("[CPA M2] Usage: /ctf decode <text>")
                    return
                result = await _ctf.cmd_ctf_decode(" ".join(parts[1:]))
            elif sub == "rev":
                if len(parts) < 2:
                    self._add_system("[CPA M2] Usage: /ctf rev <binary>")
                    return
                result = await _ctf.cmd_ctf_rev(parts[1])
            elif sub == "status":
                result = await _ctf.cmd_ctf_status()
            else:
                result = await _ctf.cmd_ctf()
        except Exception as exc:
            result = f"[CPA M2] Error: {exc}"

        self._add_system(result)
    # === CPA M2 HOOK END ===

    async def _refresh_last_ctf_capabilities(self) -> None:
        runtime = self.runtime or getattr(self.agent, "runtime", None)
        registry = None
        dispatcher = getattr(self, "_last_ctf_dispatcher", None)
        if dispatcher is not None:
            registry = getattr(dispatcher, "capability_registry", None)
        if registry is None:
            if runtime is None:
                self._add_system("[CTF capabilities] 无法 refresh：runtime 尚未就绪。")
                return
            from ..agents.pa_agent.capability_registry import CapabilityRegistry

            registry = CapabilityRegistry.build_default(runtime=runtime)
            if dispatcher is not None:
                dispatcher.capability_registry = registry

        await registry.full_check()
        state = getattr(self, "_last_ctf_state", None)
        if isinstance(state, dict):
            state["capabilities"] = registry.to_dict()
        if dispatcher is not None and getattr(dispatcher, "state", None) is not None:
            dispatcher.state.capabilities = registry.to_dict()
        self._add_system("[CTF capabilities] capability snapshot refreshed.")

    def _parse_ctf_launch_request(self, tokens: list[str]) -> dict[str, Any]:
        url = ""
        chtype = "auto"
        goal = "拿到flag"
        hint = ""
        src_path = ""
        submit_profile: dict[str, Any] = {}
        runner_config: dict[str, Any] = {
            "mode": "switch",
            "max_challenges": 4,
            "timebox_seconds": 900,
            "max_consecutive_stops": 2,
        }

        for token in tokens:
            if token.startswith("type="):
                value = token.split("=", 1)[1].strip()
                if value:
                    chtype = value
            elif token.startswith("goal="):
                value = token.split("=", 1)[1].strip()
                if value:
                    goal = value
            elif token.startswith("hint="):
                hint = token.split("=", 1)[1].strip()
            elif token.startswith("src="):
                src_path = token.split("=", 1)[1].strip()
            elif token.startswith("platform="):
                submit_profile["platform_type"] = token.split("=", 1)[1].strip()
            elif token.startswith("challenge_id="):
                submit_profile["challenge_id"] = token.split("=", 1)[1].strip()
            elif token.startswith("submit_url="):
                submit_profile["base_url"] = token.split("=", 1)[1].strip()
            elif token.startswith("submit_endpoint="):
                submit_profile["endpoint"] = token.split("=", 1)[1].strip()
            elif token.startswith("submit="):
                value = token.split("=", 1)[1].strip().lower()
                submit_profile["auto_submit"] = value in {"1", "true", "yes", "on", "auto"}
            elif token.startswith("queue="):
                value = token.split("=", 1)[1].strip().lower()
                if value:
                    runner_config["mode"] = value
            elif token.startswith("max_challenges="):
                value = token.split("=", 1)[1].strip()
                try:
                    runner_config["max_challenges"] = max(1, int(value))
                except Exception:
                    pass
            elif token.startswith("timebox="):
                value = token.split("=", 1)[1].strip()
                try:
                    runner_config["timebox_seconds"] = max(1, int(value))
                except Exception:
                    pass
            elif token.startswith("max_stops="):
                value = token.split("=", 1)[1].strip()
                try:
                    runner_config["max_consecutive_stops"] = max(1, int(value))
                except Exception:
                    pass
            elif "=" not in token and not url:
                url = token

        return {
            "url": url,
            "type": chtype,
            "goal": goal,
            "hint": hint,
            "src_path": src_path,
            "submit_profile": submit_profile,
            "runner_config": runner_config,
        }

    def _prepare_ctf_hint_with_source(
        self,
        *,
        url: str,
        hint: str,
        src_path: str,
    ) -> tuple[str, str]:
        effective_src_path = src_path or self._auto_detect_ctf_src(url)
        src_context = ""
        if effective_src_path:
            import pathlib

            p = pathlib.Path(effective_src_path)
            if p.exists():
                src_context = self._read_ctf_source_context(p)
                self._add_system(f"[CTF] 找到源码目录: {p} — 已注入上下文")
            else:
                self._add_system(f"[CTF] src 路径不存在: {effective_src_path}，跳过源码注入")

        effective_hint = str(hint or "")
        if src_context:
            effective_hint = (
                f"{effective_hint}\n\n[Injected source context]\n{src_context}"
                if effective_hint
                else f"[Injected source context]\n{src_context}"
            )
        return effective_hint, effective_src_path

    def _start_ctf_execution(
        self,
        *,
        execution_mode: str,
        url: str,
        goal: str,
        chtype: str,
        hint: str,
        submit_profile: dict[str, Any] | None = None,
        runner_config: dict[str, Any] | None = None,
    ):
        if execution_mode == "crew":
            return self._run_ctf_crew_dispatcher_mode(
                url,
                goal,
                chtype,
                hint,
                dict(submit_profile or {}),
                dict(runner_config or {}),
            )
        return self._run_ctf_dispatcher_mode(
            url,
            goal,
            chtype,
            hint,
            dict(submit_profile or {}),
            dict(runner_config or {}),
        )

    def _merge_ctf_hint_text(self, existing_hint: str, new_hint: str) -> str:
        existing = str(existing_hint or "").strip()
        incoming = str(new_hint or "").strip()
        if not incoming:
            return existing
        if incoming in existing:
            return existing
        block = f"[User hint]\n{incoming}"
        return f"{existing}\n\n{block}".strip() if existing else block

    def _build_ctf_resume_autonomy_state(self, last_ctx: dict[str, Any]) -> dict[str, Any] | None:
        autonomy_state = last_ctx.get("autonomy_state")
        if isinstance(autonomy_state, dict):
            return dict(autonomy_state)

        session_context = last_ctx.get("sessionContext")
        resume_context = (
            session_context.get("resumeContext")
            if isinstance(session_context, dict)
            else None
        )
        if not isinstance(resume_context, dict):
            return None

        submit_profile = dict(last_ctx.get("submit_profile") or {})
        challenge_id = str(submit_profile.get("challenge_id") or "").strip()
        current_url = str(last_ctx.get("url") or "").strip()
        stop_reason = str(resume_context.get("stopReason") or "").strip()
        verified_flags = [
            str(item).strip()
            for item in list(resume_context.get("verifiedFlags") or [])
            if str(item).strip()
        ]
        runtime_flags = [
            str(item).strip()
            for item in list(resume_context.get("runtimeFlags") or [])
            if str(item).strip()
        ]

        outcome = "stopped"
        success = False
        blocked_reason = ""
        failure_taxonomy = ""
        if verified_flags or stop_reason == "flag_verified":
            outcome = "solved"
            success = True
        elif stop_reason == "wrong_flag_feedback":
            outcome = "blocked"
            blocked_reason = stop_reason
            failure_taxonomy = "wrong_answer"

        visit_key = f"{challenge_id}|{current_url}".strip("|")
        now = time.time()
        return {
            "config": dict(last_ctx.get("runner_config") or {}),
            "started_at": now,
            "visited_keys": [visit_key] if visit_key else [],
            "records": [
                {
                    "challenge_id": challenge_id,
                    "challenge_name": str(resume_context.get("checkpointLabel") or "").strip(),
                    "url": current_url,
                    "outcome": outcome,
                    "reason": stop_reason,
                    "success": success,
                    "started_at": now,
                    "ended_at": now,
                    "chain_used": [],
                    "missing_tools": [],
                    "blocked_reason": blocked_reason,
                    "skip_reason": "",
                    "stop_reason_class": outcome,
                    "failure_taxonomy": failure_taxonomy,
                    "visit_key": visit_key,
                    "switch_reason": "",
                    "switch_source": "",
                }
            ],
            "consecutive_stops": 0 if success else 1,
            "switched_count": 0,
            "switch_events": [],
            "last_switch_reason": "",
            "last_switch_source": "",
            "resume_count": 0,
            "resumed_from_record_count": 0,
            "resume_reason": "",
            "last_resumed_at": 0.0,
        }
