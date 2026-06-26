"""CPA-module slash-command parsers (/report /audit /swarm /turbo) mixed into FlagHunterTUI (债池五波·TUI 刀10, god-class).

Extracted from tui.py. The CPA M3-M6 command hooks — /report, /audit, /swarm,
/turbo — each parses its slash command and emits via ``self._add_system``. They
hold zero non-self module-level dependencies (all tool / module imports are lazy
inside the bodies; AST free-name scan shows only except/loop locals), so this is
a clean low-coupling feature mixin. The stay-behind ``_handle_command`` dispatcher
resolves ``self._parse_*_command`` through the FlagHunterTUI instance MRO.
"""

from __future__ import annotations


class CpaCommandMixin:
    """/report /audit /swarm /turbo command parsers for FlagHunterTUI."""

    # === CPA M3 HOOK BEGIN ===
    async def _parse_report_command(self, cmd: str) -> None:
        """Handle /report commands for CPA M3 Reporter."""
        try:
            from flaghunter.cpa_modules.m3_reporter import get_report_generator, get_m3_status, is_m3_enabled
        except Exception as exc:
            self._add_system(f"[CPA M3] Not initialized: {exc}")
            return

        if not is_m3_enabled():
            self._add_system("[CPA M3] Reporter disabled (CPA_M3_REPORTER=false).")
            return

        parts = cmd.strip().lstrip("/").split()
        sub = parts[1].lower() if len(parts) > 1 else ""

        try:
            if sub == "new":
                if len(parts) < 3:
                    self._add_system("[CPA M3] Usage: /report new <title>")
                    return
                title = " ".join(parts[2:])
                gen = get_report_generator()
                from flaghunter.cpa_modules.m3_reporter.report_models import ReportMeta
                gen.create_report(meta=ReportMeta(title=title))
                result = f"[CPA M3] Report created: {title}"
            elif sub == "finding":
                if len(parts) < 4:
                    self._add_system("[CPA M3] Usage: /report finding <title> <severity> [desc]")
                    return
                gen = get_report_generator()
                f_title = parts[2]
                severity = parts[3].lower()
                description = " ".join(parts[4:]) if len(parts) > 4 else ""
                fid = gen.add_finding(title=f_title, severity=severity,
                                      description=description, target="")
                result = f"[CPA M3] Finding added: {fid} ({severity}) — {f_title}"
            elif sub == "export":
                gen = get_report_generator()
                fmt = parts[2].lower() if len(parts) > 2 else "html"
                gen.finalize_report()
                if fmt == "all":
                    paths = gen.export_all()
                    result = "[CPA M3] Exported:\n" + "\n".join(
                        f"  {k}: {v}" for k, v in paths.items()
                    )
                elif fmt == "md":
                    result = f"[CPA M3] Exported MD: {gen.export_markdown()}"
                elif fmt == "pdf":
                    result = f"[CPA M3] Exported PDF: {gen.export_pdf()}"
                else:
                    result = f"[CPA M3] Exported HTML: {gen.export_html()}"
            elif sub in ("status", ""):
                st = get_m3_status()
                lines = [
                    "[CPA M3] Reporter Status",
                    f"  enabled:     {st['enabled']}",
                    f"  initialized: {st['initialized']}",
                    f"  version:     {st['version']}",
                ]
                for k, v in st["components"].items():
                    lines.append(f"  [{'✓' if v else '✗'}] {k}")
                lines.append(f"  output_dir:  {st['config']['output_dir']}")
                result = "\n".join(lines)
            else:
                result = (
                    f"[CPA M3] Unknown sub-command: {sub}\n"
                    "Usage: /report [new|finding|export|status]"
                )
        except Exception as exc:
            result = f"[CPA M3] Error: {exc}"

        self._add_system(result)
    # === CPA M3 HOOK END ===

    # === CPA M4 HOOK BEGIN ===
    async def _parse_audit_command(self, cmd: str) -> None:
        """Handle /audit commands for CPA M4 Audit Guard."""
        try:
            from flaghunter.cpa_modules.m4_audit_guard import (
                is_m4_enabled, get_audit_logger, get_roe_engine,
                get_scope_enforcer, get_data_protector,
            )
        except Exception as exc:
            self._add_system(f"[CPA M4] Not initialized: {exc}")
            return

        if not is_m4_enabled():
            self._add_system("[CPA M4] Audit Guard disabled (CPA_M4_AUDIT_GUARD=false).")
            return

        parts = cmd.strip().lstrip("/").split()
        sub = parts[1].lower() if len(parts) > 1 else ""

        try:
            if sub == "log":
                n = int(parts[2]) if len(parts) > 2 else 20
                al = get_audit_logger()
                entries = al.get_recent(n)
                if not entries:
                    result = "[CPA M4] 暂无审计记录。"
                else:
                    lines = [f"[CPA M4] 最近 {len(entries)} 条审计记录:"]
                    for e in entries:
                        ts = e.timestamp.strftime("%H:%M:%S") if e.timestamp else "?"
                        lines.append(f"  {ts} [{e.action_type:12s}] {e.target or '-'} → {e.result}")
                    result = "\n".join(lines)
            elif sub == "scope":
                if len(parts) < 3:
                    self._add_system("[CPA M4] Usage: /audit scope <target>")
                    return
                target = parts[2]
                se = get_scope_enforcer()
                res = se.validate_sync(action="check", target=target)
                allowed = res.get("allowed", True)
                reason = res.get("reason", "")
                icon = "✓" if allowed else "✗"
                result = f"[CPA M4] {icon} {target}: {reason}"
            elif sub == "roe":
                if len(parts) < 3:
                    self._add_system("[CPA M4] Usage: /audit roe <file_path>")
                    return
                roe_path = parts[2]
                import os
                if not os.path.isfile(roe_path):
                    result = f"[CPA M4] 文件不存在: {roe_path}"
                else:
                    re_eng = get_roe_engine()
                    re_eng.load_roe(roe_path)
                    result = f"[CPA M4] RoE 加载成功: {roe_path}\n{re_eng.get_config_summary()}"
            elif sub == "mask":
                if len(parts) < 3:
                    self._add_system("[CPA M4] Usage: /audit mask <text>")
                    return
                text = " ".join(parts[2:])
                dp = get_data_protector()
                masked = dp.mask(text)
                result = f"[CPA M4] 脱敏结果:\n  原文: {text}\n  脱敏: {masked}"
            elif sub in ("status", ""):
                lines = ["[CPA M4] Audit Guard Status"]
                al = get_audit_logger()
                lines.append(f"  audit_logger:   ✓ ({len(al.get_recent(200))} 条记录)")
                re_eng = get_roe_engine()
                lines.append(f"  roe_engine:     ✓ loaded={re_eng.is_loaded}")
                se = get_scope_enforcer()
                stats = se.get_stats()
                lines.append(f"  scope_enforcer: ✓ blocked={stats.get('blocked', 0)}")
                dp = get_data_protector()
                lines.append(f"  data_protector: ✓")
                result = "\n".join(lines)
            else:
                result = (
                    f"[CPA M4] Unknown sub-command: {sub}\n"
                    "Usage: /audit [log|scope|roe|mask|status]"
                )
        except Exception as exc:
            result = f"[CPA M4] Error: {exc}"

        self._add_system(result)
    # === CPA M4 HOOK END ===

    # === CPA M5 HOOK BEGIN ===
    async def _parse_swarm_command(self, cmd: str) -> None:
        """Handle /swarm commands for CPA M5 Swarm Link."""
        try:
            from flaghunter.cpa_modules.m5_swarm_link import swarm_commands as _sw
            from flaghunter.cpa_modules.m5_swarm_link import is_m5_enabled
        except Exception as exc:
            self._add_system(f"[CPA M5] Not available: {exc}")
            return

        parts = cmd.strip().lstrip("/").split()
        sub = parts[1].lower() if len(parts) > 1 else ""
        # Use a fixed agent_id for TUI-originated commands
        agent_id = "tui"

        try:
            if sub == "status":
                result = await _sw.cmd_swarm_status(agent_id=agent_id)
            elif sub == "top":
                n = int(parts[2]) if len(parts) > 2 else 5
                result = await _sw.cmd_swarm_top(agent_id=agent_id, top_n=n)
            elif sub == "deposit":
                if len(parts) < 3:
                    self._add_system("[CPA M5] Usage: /swarm deposit <target> [amount]")
                    return
                target = parts[2]
                amount = float(parts[3]) if len(parts) > 3 else 1.0
                result = await _sw.cmd_swarm_deposit(agent_id=agent_id, target=target, amount=amount)
            elif sub == "board":
                limit = int(parts[2]) if len(parts) > 2 else 10
                if len(parts) > 2 and parts[2].lower() == "query":
                    msg_type = parts[3] if len(parts) > 3 else "finding"
                    result = await _sw.cmd_swarm_board_query(agent_id=agent_id, msg_type=msg_type)
                else:
                    result = await _sw.cmd_swarm_board(agent_id=agent_id, limit=limit)
            elif sub == "msg":
                if len(parts) < 3:
                    self._add_system("[CPA M5] Usage: /swarm msg <content>")
                    return
                content = " ".join(parts[2:])
                result = await _sw.cmd_swarm_msg(agent_id=agent_id, content=content)
            elif sub == "propose":
                if len(parts) < 3:
                    self._add_system("[CPA M5] Usage: /swarm propose <question>")
                    return
                question = " ".join(parts[2:])
                result = await _sw.cmd_swarm_propose(agent_id=agent_id, question=question)
            elif sub == "vote":
                if len(parts) < 4:
                    self._add_system("[CPA M5] Usage: /swarm vote <vote_id> <choice>")
                    return
                result = await _sw.cmd_swarm_vote(agent_id=agent_id, vote_id=parts[2], choice=parts[3])
            elif sub == "consensus":
                if len(parts) < 3:
                    self._add_system("[CPA M5] Usage: /swarm consensus <target1> [target2...]")
                    return
                result = await _sw.cmd_swarm_consensus(agent_id=agent_id, targets=parts[2:])
            elif sub == "join":
                if len(parts) < 3:
                    self._add_system("[CPA M5] Usage: /swarm join <group>")
                    return
                result = await _sw.cmd_swarm_join(agent_id=agent_id, group=parts[2])
            elif sub == "leave":
                if len(parts) < 3:
                    self._add_system("[CPA M5] Usage: /swarm leave <group>")
                    return
                result = await _sw.cmd_swarm_leave(agent_id=agent_id, group=parts[2])
            elif sub == "reset":
                result = await _sw.cmd_swarm_reset(agent_id=agent_id)
            else:
                result = await _sw.cmd_swarm(agent_id=agent_id)
        except Exception as exc:
            result = f"[CPA M5] Error: {exc}"

        self._add_system(result)
    # === CPA M5 HOOK END ===

    # === CPA M6 HOOK BEGIN ===
    async def _parse_turbo_command(self, cmd: str) -> None:
        """Handle /turbo commands for CPA M6 Turbo."""
        try:
            from flaghunter.cpa_modules.m6_turbo import is_m6_enabled
            from flaghunter.cpa_modules.m6_turbo.turbo_commands import cmd_turbo as _cmd_turbo
        except Exception as exc:
            self._add_system(f"[CPA M6] Not initialized: {exc}")
            return

        if not is_m6_enabled():
            self._add_system("[CPA M6] Turbo disabled (CPA_M6_TURBO=false).")
            return

        parts = cmd.strip().split()
        args = parts[1:]  # drop "/turbo"

        try:
            result = await _cmd_turbo(args=args)
        except Exception as exc:
            result = f"[CPA M6] Error: {exc}"

        self._add_system(result)
    # === CPA M6 HOOK END ===
