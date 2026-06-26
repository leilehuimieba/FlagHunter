"""Mode / service slash-command parsers mixed into FlagHunterTUI (债池五波·TUI 刀11, god-class).

Extracted from tui.py. The /agent, /crew, /interact, /assist, /mcp, /api command
parsers — each parses its slash command, updates header/status/sidebar, and kicks
off the matching ``self._run_*`` worker (agent/crew/interact/assist) or pushes the
MCP screen. ``MCPScreen`` (extracted to tui_screens in 刀4) is the only non-self
module-level dependency; everything else (``self._add_*`` / ``_set_status`` /
``_update_header`` / ``_run_*``) resolves at runtime through the FlagHunterTUI
instance MRO. The stay-behind ``_handle_command`` dispatcher resolves these too.
"""

from __future__ import annotations

from .tui_screens import MCPScreen


class ModeCommandMixin:
    """/agent /crew /interact /assist /mcp /api command parsers for FlagHunterTUI."""

    async def _parse_agent_command(self, cmd: str) -> None:
        """Parse and execute /agent command"""

        self._set_status("idle", "agent")
        self._update_header()
        self._add_system("Changed to agent mode\n")

        # Remove /agent prefix
        rest = cmd[len("/agent") :].strip()

        if not rest:
            self._add_system(
                "Usage: /agent <task>\n"
                "Example: /agent scan 192.168.1.1\n"
                "         /agent enumerate SSH on target"
            )
            return

        task = rest

        if not task:
            self._add_system("Error: No task provided. Usage: /agent <task>")
            return

        self._add_user(f"/agent {task}")
        self._add_system(">> Agent Mode")

        # Hide crew sidebar when entering agent mode
        self._hide_sidebar()

        if self.agent and not self._is_running:
            # Schedule agent mode and keep task handle
            # Schedule agent run and keep task handle (do not wrap in asyncio.create_task; @work returns a Worker)
            self._current_worker = self._run_agent_mode(task)

    async def _parse_crew_command(self, cmd: str) -> None:
        """Parse and execute /crew command"""

        self._set_status("idle", "crew")
        self._update_header()
        self._add_system("Changed to crew mode\n")

        # Remove /crew prefix
        rest = cmd[len("/crew") :].strip()

        if not rest:
            self._add_system(
                "Usage: /crew <task>\n"
                "Example: /crew https://example.com\n"
                "         /crew 192.168.1.100\n\n"
                "Crew mode spawns specialized workers in parallel:\n"
                "  - recon: Reconnaissance and mapping\n"
                "  - sqli: SQL injection testing\n"
                "  - xss: Cross-site scripting testing\n"
                "  - ssrf: Server-side request forgery\n"
                "  - auth: Authentication testing\n"
                "  - idor: Insecure direct object references\n"
                "  - info: Information disclosure"
            )
            return

        target = rest

        if not self._is_running:
            self._add_user(f"/crew {target}")
            self._show_sidebar()
            # Schedule crew mode and keep handle
            # Schedule crew run and keep task handle (do not wrap in asyncio.create_task; @work returns a Worker)
            self._current_worker = self._run_crew_mode(target)

    async def _parse_interact_command(self, cmd: str) -> None:
        # Use interact mode by default

        self._set_status("idle", "interact")
        self._update_header()
        self._add_system("Changed to interact mode\n")

        message = cmd[len("/interact") :].strip()
        if not message:
            self._add_system(
                "Usage: /interact <task>\n"
                "Example: /interact Can you help me recon the target site?\n"
            )
            return

        if self.agent and not self._is_running:
            # Schedule interact run and keep task handle (do not wrap in asyncio.create_task; @work returns a Worker)
            self._current_worker = self._run_interact(message)

    async def _parse_assist_command(self, cmd: str) -> None:
        # Use assist mode by default

        self._set_status("idle", "assist")
        self._update_header()
        self._add_system("Changed to assist mode\n")

        message = cmd[len("/assist") :].strip()
        if not message:
            self._add_system(
                "Usage: /assist <task>\n"
                "Example: /assist Can you help me recon the target site?\n"
            )
            return

        if self.agent and not self._is_running:
            # Schedule assist run and keep task handle (do not wrap in asyncio.create_task; @work returns a Worker)
            self._current_worker = self._run_assist(message)

    async def _parse_mcp_command(self, cmd: str) -> None:
        # Remove /agent prefix
        rest = cmd[len("/mcp") :].strip()

        if not rest:
            self._add_system(
                "Usage: /mcp <command>\n" "Example: /mcp list \n" "         /mcp add"
            )
            return

        action = rest

        if action == "list":
            if self.mcp_manager:

                # Open the interactive mcp browser (split-pane).
                try:
                    await self.push_screen(
                        MCPScreen(
                            mcp_manager=self.mcp_manager, agent=self.agent, tui=self
                        )
                    )
                except Exception:
                    pass
        elif action.startswith("add"):

            from ..tools import get_all_tools, register_tool_instance

            args = rest[len("add") :].strip()

            # Parse the args string into individual components
            parts = args.split()
            if len(parts) < 2:
                self._add_system(
                    "Usage: /mcp add <type> <name> <command|url> [args...]"
                )
                return

            mcp_type = parts[0]
            name = parts[1]
            command_or_url = parts[1]

            mcp_args = parts[2:] if len(parts) > 2 else []

            if not self.mcp_manager:
                return

            if mcp_type == "sse":
                self.mcp_manager.add_sse_server(
                    name=name,
                    url=command_or_url,
                )
            else:
                self.mcp_manager.add_stdio_server(
                    name=name,
                    command=command_or_url,
                    args=mcp_args,
                )

            server = await self.mcp_manager.connect_server(name)

            self.mcp_server_count = len(self.mcp_manager.list_configured_servers())

            if server:

                tools = self.mcp_manager.create_mcp_tools_from_server(server)

                if self.agent:
                    self.agent.add_tools(tools)

                for tool in tools:
                    register_tool_instance(tool)

                self.all_tools = get_all_tools()
                self._update_header()

        if not action:
            self._add_system("Error: No action provided. Usage: /mcp <command>")
            return

    # === CPA M1 HOOK BEGIN ===
    async def _parse_api_command(self, cmd: str) -> None:
        """Handle /api commands — show CPA M1 API Hub provider status."""
        try:
            from flaghunter.cpa_modules.m1_api_hub import get_provider_manager, get_cost_tracker
            pm = get_provider_manager()
            ct = get_cost_tracker()
        except Exception as exc:
            self._add_system(f"[CPA M1] Not initialized: {exc}")
            return

        providers = pm.list_providers()
        if not providers:
            self._add_system("[CPA M1] No providers registered.")
            return

        lines = ["[CPA M1] Provider Status"]
        for p in providers:
            status = pm.get_status(p.id)
            usage = ct.get_provider_usage(p.id)
            emoji = status.state_emoji() if status else "⚪"
            state = status.state.value if status else "unknown"
            lines.append(
                f"  {emoji} {p.id}  model={p.model}  state={state}"
                f"  req={usage['requests']}  tokens={usage['tokens']}"
                f"  cost=${usage['cost']:.4f}  avg_lat={usage['avg_latency_ms']:.0f}ms"
            )
        self._add_system("\n".join(lines))
