"""Embedded-terminal spawn / despawn feature mixed into FlagHunterTUI (债池五波·TUI 刀12, god-class).

Extracted from tui.py. The child-agent embedded-terminal feature: the
``_spawn_terminal_callback`` / ``_despawn_terminal_callback`` that post messages,
the ``@on(SpawnTerminalMessage)`` / ``@on(DespawnTerminalMessage)`` handlers that
mount/unmount the terminal widget, and the ``/spawn`` / ``/despawn`` command
parsers with their ``@work`` runners. Decorator + post_message refs to the two
terminal messages (tui_messages, 刀1) and ResizeDivider (tui_diagnostics, 刀5) are
imported here; child-agent + terminal-widget backends are lazy inside the bodies.
Stay-behind callers (on_mount registers the callbacks, _handle_command dispatches
the parsers) resolve through the FlagHunterTUI instance MRO.
"""

from __future__ import annotations

import logging

from textual import on, work

from .tui_diagnostics import ResizeDivider
from .tui_messages import DespawnTerminalMessage, SpawnTerminalMessage


class TerminalSpawnMixin:
    """Child-agent embedded-terminal spawn/despawn for FlagHunterTUI."""

    def _spawn_terminal_callback(self, master_fd: int, label: str) -> None:
        """Callback wired to `notifier.register_spawn_terminal_callback`.

        Called from an asyncio task (agent tool execution), so we route
        through post_message / call_from_thread to stay on the Textual loop.
        """
        try:
            if hasattr(self, "call_from_thread"):
                try:
                    self.call_from_thread(
                        self.post_message, SpawnTerminalMessage(master_fd, label)
                    )
                    return
                except Exception:
                    pass
            self.post_message(SpawnTerminalMessage(master_fd, label))
        except Exception as e:
            logging.getLogger(__name__).exception(
                "spawn_terminal_callback failed: %s", e
            )

    @on(SpawnTerminalMessage)
    def _handle_spawn_terminal(self, message: SpawnTerminalMessage) -> None:
        """Mount a CollapsibleTerminal widget and show the agents panel."""
        from .widgets import CollapsibleTerminal

        try:
            panel = self.query_one("#agents-panel")
            terminal = CollapsibleTerminal(
                master_fd=message.master_fd,
                label=message.label,
            )
            panel.mount(terminal)
            panel.add_class("visible")
            try:
                self.query_one("#resize-divider", ResizeDivider).add_class("visible")
            except Exception:
                pass
            self.refresh(layout=True)
            self._add_system(
                f"[+] Child agent '{message.label}' terminal opened in side panel."
            )
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to mount EmbeddedTerminal: %s", e
            )

    def _despawn_terminal_callback(self, label: str) -> None:
        """Callback wired to `notifier.register_despawn_terminal_callback`."""
        try:
            if hasattr(self, "call_from_thread"):
                try:
                    self.call_from_thread(
                        self.post_message, DespawnTerminalMessage(label)
                    )
                    return
                except Exception:
                    pass
            self.post_message(DespawnTerminalMessage(label))
        except Exception as e:
            logging.getLogger(__name__).exception(
                "despawn_terminal_callback failed: %s", e
            )

    @on(DespawnTerminalMessage)
    def _handle_despawn_terminal(self, message: DespawnTerminalMessage) -> None:
        """Unmount the CollapsibleTerminal whose label matches the despawned agent."""
        from .widgets import CollapsibleTerminal

        try:
            panel = self.query_one("#agents-panel")

            # Count terminals that will remain *after* this removal.  We must
            # do this BEFORE calling remove() because widget.remove() is
            # deferred in Textual — the DOM query would still find the widget
            # that is being removed if we check afterwards.
            all_terminals = list(panel.query(CollapsibleTerminal))
            remaining_after = [w for w in all_terminals if w._label != message.label]

            for widget in all_terminals:
                if widget._label == message.label:
                    widget.remove()
                    break

            # Hide the panel and resize divider if no terminals will remain,
            # and reset the panel width so it fills correctly on next spawn.
            if not remaining_after:
                panel.remove_class("visible")
                panel.styles.width = None  # reset to CSS default (84)
                try:
                    self.query_one("#resize-divider", ResizeDivider).remove_class(
                        "visible"
                    )
                except Exception:
                    pass
                self.refresh(layout=True)

            self._add_system(
                f"[-] Child agent '{message.label}' terminal removed from side panel."
            )
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to unmount CollapsibleTerminal: %s", e
            )

    async def _parse_spawn_command(self, cmd: str) -> None:
        """Parse and execute /spawn command — manually spawn a child MCP agent."""
        import shlex

        if not self.agent:
            self._add_system("[!] No agent initialised.")
            return

        rest = cmd[len("/spawn") :].strip()

        # Parse flags
        target: str = ""
        scope: list[str] = []
        model: str = ""
        no_rag: bool = False
        no_mcp: bool = True

        try:
            tokens = shlex.split(rest)
        except ValueError as exc:
            self._add_system(f"[!] Parse error: {exc}")
            return

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok == "--target" and i + 1 < len(tokens):
                target = tokens[i + 1]
                i += 2
            elif tok == "--scope" and i + 1 < len(tokens):
                i += 1
                while i < len(tokens) and not tokens[i].startswith("--"):
                    scope.append(tokens[i])
                    i += 1
            elif tok == "--model" and i + 1 < len(tokens):
                model = tokens[i + 1]
                i += 2
            elif tok == "--no-rag":
                no_rag = True
                i += 1
            elif tok == "--no-mcp":
                no_mcp = True
                i += 1
            elif not tok.startswith("--") and not target:
                # Bare positional argument → target
                target = tok
                i += 1
            else:
                i += 1

        self._add_user(cmd)
        self._add_system(
            f"Spawning child agent… target={target or 'none'}  "
            f"scope={scope or []}  model={model or 'default'}"
        )
        if not self._is_running:
            self._current_worker = self._run_spawn_command(
                target, scope, model, no_rag, no_mcp
            )

    @work(thread=False)
    async def _run_spawn_command(
        self,
        target: str,
        scope: list,
        model: str,
        no_rag: bool,
        no_mcp: bool,
    ) -> None:
        from ..tools.mcp_agent import spawn_child_agent

        self._is_running = True
        try:
            result = await spawn_child_agent(
                self.agent,
                self.agent.runtime,
                {
                    "target": target,
                    "scope": scope,
                    "model": model,
                    "no_rag": no_rag,
                    "no_mcp": no_mcp,
                },
            )
            self._add_system(result)
        except Exception as exc:
            self._add_system(f"[!] Spawn failed: {exc}")
        finally:
            self._is_running = False

    async def _parse_despawn_command(self, cmd: str) -> None:
        """Parse and execute /despawn <server_name>."""
        if not self.agent:
            self._add_system("[!] No agent initialised.")
            return

        server_name = cmd[len("/despawn") :].strip()
        if not server_name:
            self._add_system(
                "Usage: /despawn <server_name>\n"
                "Example: /despawn child_agent_1\n"
                "Use /mcp list to see active child agents."
            )
            return

        self._add_user(cmd)
        self._add_system(f"Despawning '{server_name}'…")
        if not self._is_running:
            self._current_worker = self._run_despawn_command(server_name)

    @work(thread=False)
    async def _run_despawn_command(self, server_name: str) -> None:
        from ..tools.mcp_agent import despawn_child_agent

        self._is_running = True
        try:
            result = await despawn_child_agent(
                self.agent, self.agent.runtime, server_name
            )
            self._add_system(result)
        except Exception as exc:
            self._add_system(f"[!] Despawn failed: {exc}")
        finally:
            self._is_running = False
