"""MCP-mode activation + task-event bridge mixed into FlagHunterTUI (债池五波·TUI 刀 21, god-class).

Extracted from tui.py. The MCP integration: the ``@work`` ``_activate_mcp_mode`` that
connects external MCP servers, the ``on_mcp_event`` bus callback that re-posts onto the
Textual loop as an ``MCPTaskEvent``, and the ``@on(MCPTaskEvent)`` ``handle_mcp_task_event``
that renders the update. The ``@on`` decorator binds ``MCPTaskEvent`` at class creation
(imported here), and Textual scans this mixin's MRO entry to register the handler;
stay-behind registration of ``on_mcp_event`` as the manager callback resolves through the
FlagHunterTUI instance MRO. Module-level deps: ``logging`` / ``on`` / ``work`` / ``Static``
/ ``MCPTaskEvent`` (tui_messages, 刀1); traceback is lazy inside the body.
"""

from __future__ import annotations

import logging

from textual import on, work
from textual.widgets import Static

from .tui_messages import MCPTaskEvent


class McpModeMixin:
    """MCP-mode activation + MCPTaskEvent bridge for FlagHunterTUI."""

    @work(thread=False)
    async def _activate_mcp_mode(self) -> None:
        """Set up TUI in MCP observation mode using pre-built components."""
        try:
            components = self._prebuilt_components or {}
            self.agent = components.get("agent")
            self.runtime = components.get("runtime")
            self.rag_engine = components.get("rag_engine")
            self.all_tools = components.get("all_tools") or []
            self.mcp_manager = components.get("mcp_manager")
            self.model = components.get("model") or self.model
            rag_doc_count = components.get("rag_doc_count", 0)
            mcp_server_count = components.get("mcp_server_count", 0)

            # Disable the input widget — operator cannot type commands.
            try:
                inp = self.query_one("#chat-input")
                inp.disabled = True
            except Exception:
                pass
            try:
                prompt = self.query_one("#chat-prompt", Static)
                prompt.update("")
            except Exception:
                pass
            try:
                container = self.query_one("#input-container")
                container.add_class("mcp-locked")
            except Exception:
                pass

            self._is_initializing = False
            self._set_status("idle", "mcp")

            self.mcp_server_count = mcp_server_count
            self.rag_doc_count = rag_doc_count
            try:
                self._update_header(
                    model_line=(
                        f"+ FlagHunter — MCP Server Mode (read-only)\n"
                        f"  Model: {self.model} | Tools: {len(self.all_tools)} | MCP servers: {mcp_server_count} | RAG: {rag_doc_count}\n"
                        f"  Waiting for MCP client tasks…"
                    )
                )
            except Exception:
                self._add_system(
                    f"+ FlagHunter — MCP Server Mode (read-only)\n"
                    f"  Model: {self.model} | Tools: {len(self.all_tools)} | MCP: {mcp_server_count} | RAG: {rag_doc_count}"
                )

            if self.target:
                try:
                    self._update_header(target=self.target)
                except Exception:
                    pass

        except Exception as e:
            import traceback

            self._add_system(f"[!] MCP mode init failed: {e}\n{traceback.format_exc()}")
            self._set_status("error")
            self._is_initializing = False

    def on_mcp_event(self, event: str, data: dict) -> None:
        """Called by mcp_tools._emit() from an asyncio task.

        Does NOT touch any Textual widgets directly — instead posts a
        MCPTaskEvent message so Textual dispatches the update safely inside
        its own message loop (avoids NoMatches / DOM-not-ready races).
        """
        try:
            self.post_message(MCPTaskEvent(event, data))
        except Exception as e:
            logging.getLogger(__name__).exception("MCP post_message failed: %s", e)

    @on(MCPTaskEvent)
    def handle_mcp_task_event(self, message: MCPTaskEvent) -> None:
        """Handle MCP task events inside Textual's message loop (DOM is ready)."""
        event = message.event
        data = message.data
        try:
            if event == "task_start":
                task = data.get("task", "")
                target = data.get("target")
                label = f"[MCP task] {task}"
                if target:
                    label += f"  (target: {target})"
                self._add_user(label)
                self._set_status("running", "mcp")
                self._is_running = True
                self._mcp_tool_messages = {}

            elif event == "thinking":
                content = data.get("content", "")
                if content:
                    self._add_thinking(content)

            elif event == "content":
                content = data.get("content", "")
                if content:
                    self._add_assistant(content)

            elif event == "tool_call":
                call_id = data.get("id", "")
                name = data.get("name", "")
                arguments = data.get("arguments", {})
                tm = self._add_tool(name, str(arguments))
                self._mcp_tool_messages[call_id] = tm

            elif event == "tool_result":
                call_id = data.get("tool_call_id", "")
                tool_name = data.get("tool_name", "")
                result = data.get("result", "")
                success = data.get("success", True)
                tm = self._mcp_tool_messages.get(call_id)
                if tm is not None:
                    label = result if success else f"Error: {result}"
                    self._add_tool_result(tm, tool_name, label or "Done")

            elif event == "task_done":
                status = data.get("status", "done")
                error = data.get("error")
                if status == "error" and error:
                    self._add_system(f"[!] Task error: {error}")
                elif status == "cancelled":
                    self._add_system("[!] Task cancelled.")
                self._set_status("idle", "mcp")
                self._is_running = False

        except Exception as e:
            logging.getLogger(__name__).exception("MCP task event handler error: %s", e)
