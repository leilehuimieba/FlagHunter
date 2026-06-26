"""Modal screen classes for FlagHunterTUI (debt ledger 第五波·TUI 刀4).

Extracted from tui.py. The seven full-screen / confirmation modals — Help,
WorkspaceHelp, Tools, Conversations, MCP, RewindConfirm, ForkConfirm. Each is a
self-contained ModalScreen; cross-package types (Tool / MCPManager /
FlagHunterAgent / preference + memory stores) are imported lazily inside the
class bodies and method bodies, so they travel with the code. The ``tui``
back-reference is a string forward annotation (``"FlagHunterTUI"``), never
evaluated, and no screen touches FlagHunterTUI / module globals at runtime — so
the cluster is down-closed with zero upward dependency on tui.py (verified by AST
free-name analysis: zero module-level up-calls). tui.py re-imports the set so
stay-behind push_screen callers in FlagHunterTUI resolve unchanged.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import (
    Center,
    Container,
    Horizontal,
    ScrollableContainer,
    Vertical,
)
from textual.screen import ModalScreen
from textual.widgets import Button, Static, Switch, Tree


class HelpScreen(ModalScreen):
    """Help modal"""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
        scrollbar-background: #1a1a1a;
        scrollbar-background-hover: #1a1a1a;
        scrollbar-background-active: #1a1a1a;
        scrollbar-color: #3a3a3a;
        scrollbar-color-hover: #3a3a3a;
        scrollbar-color-active: #3a3a3a;
        scrollbar-corner-color: #1a1a1a;
        scrollbar-size: 1 1;
    }

    #help-container {
        width: 110;
        height: 34;
        background: #121212;
        border: solid #3a3a3a;
        padding: 1 2;
        layout: vertical;
    }

    #help-title {
        text-align: center;
        text-style: bold;
        color: #d4d4d4;
        margin-bottom: 1;
    }

    #help-content {
        color: #9a9a9a;
    }


    #help-close {
        margin-top: 1;
        width: auto;
        min-width: 10;
        background: #1a1a1a;
        color: #9a9a9a;
        border: none;
    }

    #help-close:hover {
        background: #262626;
    }

    #help-close:focus {
        background: #262626;
        text-style: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Container(
            Static("FlagHunter Help", id="help-title"),
            Static(self._get_help_text(), id="help-content"),
            Center(Button("Close", id="help-close")),
            id="help-container",
        )

    def _get_help_text(self) -> str:
        header = (
            "[bold]Modes:[/] Assist | Agent | Crew | Interact\n"
            "[bold]Keys:[/] Enter=Send  Shift+Enter=New line  Up/Down=History  Ctrl+Q=Quit\n"
            "[bold]Rewind:[/] Click 'rewind' on your messages to undo from that point\n\n"
            "[bold]Commands:[/]\n"
        )

        cmds = [
            ("/assist <task>", "Run in assist mode"),
            ("/agent <task>", "Run in agent mode"),
            (
                '/ctf <url> [type=web|sqli|xss|lfi|cmd|crypto|pwn|misc] [hint="..."]',
                "Run fast CTF mode",
            ),
            ("/crew <task>", "Run multi-agent crew mode"),
            ("/interact <task>", "Run in interact mode"),
            ("/nmap <target> [ports]", "Run structured nmap scan"),
            ("/dirscan <url> [wordlist]", "Run structured dir scan"),
            ("/nuclei <target> [severity]", "Run nuclei scan"),
            ("/sqlmap <url> [--data <data>]", "Run sqlmap test"),
            (
                "/spawn \\[target] [--scope CIDR] [--model M] [--no-rag] [--no-mcp]",
                "Spawn child MCP agent",
            ),
            ("/despawn <server_name>", "Despawn child MCP agent"),
            ("/target <host>", "Set target · 自动隔离 loot/notes 到该目标的 workspace"),
            ("/workspace <name|list>", "Manage workspaces"),
            ("/prompt", "Show system prompt"),
            ("/memory", "Show memory stats"),
            ("/token", "Show token usage & cost"),
            ("/notes", "Show saved notes"),
            ("/graph", "Show attack path graph (Mermaid)"),
            ("/report", "Generate report"),
            ("/help", "Show help"),
            ("/clear", "Clear chat"),
            ("/tools", "List tools"),
            ("/conversations", "Browse & restore saved conversations"),
            ("/mcp", "List mcp servers"),
            ("/quit", "Exit"),
        ]

        # Determine consistent width for command column so the dash aligns.
        # Use visual length (\[ renders as [ in Rich, subtract the backslash).
        def _vlen(s: str) -> int:
            return len(s.replace("\\[", "["))

        cmd_col_width = max(_vlen(c) for c, _ in cmds) + 3
        lines = []
        for cmd, desc in cmds:
            pad = " " * (cmd_col_width - _vlen(cmd))
            lines.append(f"  {cmd}{pad}- {desc}")

        return header + "\n".join(lines)

    def action_dismiss(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#help-close")
    def close_help(self) -> None:
        self.app.pop_screen()


class WorkspaceHelpScreen(ModalScreen):
    """Help modal for workspace commands."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    CSS = """
    WorkspaceHelpScreen {
        align: center middle;
        scrollbar-background: #1a1a1a;
        scrollbar-background-hover: #1a1a1a;
        scrollbar-background-active: #1a1a1a;
        scrollbar-color: #3a3a3a;
        scrollbar-color-hover: #3a3a3a;
        scrollbar-color-active: #3a3a3a;
        scrollbar-corner-color: #1a1a1a;
        scrollbar-size: 1 1;
    }

    #help-container {
        width: 60;
        height: 26;
        background: #121212;
        border: solid #3a3a3a;
        padding: 1 2;
        layout: vertical;
    }

    #help-title {
        text-align: center;
        text-style: bold;
        color: #d4d4d4;
        margin-bottom: 1;
    }

    #help-content {
        color: #9a9a9a;
    }


    #help-close {
        margin-top: 1;
        width: auto;
        min-width: 10;
        background: #1a1a1a;
        color: #9a9a9a;
        border: none;
    }

    #help-close:hover {
        background: #262626;
    }

    #help-close:focus {
        background: #262626;
        text-style: none;
    }
    """

    def compose(self) -> ComposeResult:
        from rich.table import Table
        from rich.text import Text

        # Build a two-column table to prevent wrapping
        table = Table.grid(padding=(0, 3))
        table.add_column(justify="left", ratio=2)
        table.add_column(justify="left", ratio=3)

        # Header and usage
        header = Text("Workspace Commands", style="bold")
        usage = Text("Usage: /workspace <action> or /workspace <name>")

        # Commands list
        cmds = [
            ("/workspace", "Show active"),
            ("/workspace list", "List all workspaces"),
            ("/workspace info [NAME]", "Show workspace metadata"),
            ("/workspace note <text>", "Add operator note"),
            ("/workspace clear", "Deactivate workspace"),
            ("/workspace NAME", "Create or activate workspace"),
            ("/workspace help", "Show this help"),
        ]

        # Compose table rows
        table.add_row(Text("Commands:", style="bold"), Text(""))

        for left, right in cmds:
            table.add_row(left, right)

        yield Container(
            Static(header, id="help-title"),
            Static(usage, id="help-usage"),
            Static(table, id="help-content"),
            Center(Button("Close", id="help-close"), id="help-center"),
            id="help-container",
        )

    def _get_help_text(self) -> str:
        header = "Usage: /workspace <action> or /workspace <name>\n"
        cmds = [
            ("/workspace", "Show active"),
            ("/workspace list", "List all workspaces"),
            ("/workspace info [NAME]", "Show workspace metadata"),
            ("/workspace note <text>", "Add operator note"),
            ("/workspace clear", "Deactivate workspace"),
            ("/workspace NAME", "Create or activate workspace"),
            ("/workspace help", "Show this help"),
        ]

        # Build two-column layout with fixed left column width
        left_width = 44
        lines = [header, "Commands:\n"]
        for left, right in cmds:
            if len(left) >= left_width - 2:
                # if left is long, place on its own line
                lines.append(f"  {left}\n    {right}")
            else:
                pad = " " * (left_width - len(left))
                lines.append(f"  {left}{pad}{right}")

        return "\n".join(lines)

    def action_dismiss(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#help-close")
    def close_help(self) -> None:
        self.app.pop_screen()


class ToolsScreen(ModalScreen):
    """Interactive tools browser — split-pane layout.

    Left pane: tree of tools. Right pane: full description (scrollable).
    Selecting another tool replaces the right-pane content. Close returns
    to the main screen.
    """

    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("q", "dismiss", "Close")]

    CSS = """
    ToolsScreen { align: center middle; }
    """
    from ..tools import Tool

    def __init__(self, tools: List[Tool], tui: "FlagHunterTUI") -> None:
        from ..tools import Tool

        super().__init__()
        self.tools = tools
        self.selected_tool: Optional[Tool] = None
        self.tui = tui

    def compose(self) -> ComposeResult:
        # Build a split view: left tree, right description
        with Container(id="tools-container"):
            with Horizontal(id="tools-split"):
                with Vertical(id="tools-left"):
                    yield Static("Tools", id="tools-title")
                    yield Tree("TOOLS", id="tools-tree")

                with Vertical(id="tools-right"):
                    yield Button("Enabled: OFF", id="tool-toggle-enabled")
                    yield Static("Description", id="tools-desc-title")
                    yield ScrollableContainer(
                        Static("Select a tool to view details.", id="tools-desc"),
                        id="tools-desc-scroll",
                    )

            yield Center(Button("Close", id="tools-close"))

    def on_mount(self) -> None:
        try:
            tree = self.query_one("#tools-tree", Tree)
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to query tools tree: %s", e)
            try:
                from ..interface.notifier import notify

                notify("warning", f"TUI: failed to initialize tools tree: {e}")
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about tools tree init failure: %s", e
                )
            return

        root = tree.root
        root.allow_expand = True
        root.show_root = False

        # Populate tool nodes
        for t in self.tools:
            name = getattr(t, "name", str(t))
            root.add(name, data={"tool": t})

        # Hide toggle button initially
        toggle_btn = self.query_one("#tool-toggle-enabled", Button)
        toggle_btn.display = False

        try:
            tree.focus()
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to focus tools tree: %s", e)
            try:
                from ..interface.notifier import notify

                notify("warning", f"TUI: failed to focus tools tree: {e}")
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about tools tree focus failure: %s", e
                )

    @on(Tree.NodeSelected, "#tools-tree")
    def on_tool_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        try:
            tool = node.data.get("tool") if node.data else None
            self.selected_tool = tool
            name = getattr(tool, "name", str(tool)) if tool else "Unknown"

            # Prefer Tool.description (registered tools use this), then fall back
            desc = None
            tool_enabled = False
            if tool is not None:
                desc = getattr(tool, "description", None)
                if not desc:
                    desc = (
                        getattr(tool, "summary", None)
                        or getattr(tool, "help_text", None)
                        or getattr(tool, "__doc__", None)
                    )

                tool_enabled = getattr(tool, "enabled", False)

            if not desc:
                desc = "No description available."

            # Update right-hand description pane
            try:
                desc_widget = self.query_one("#tools-desc", Static)
                toggle_btn = self.query_one("#tool-toggle-enabled", Button)
                text = Text()
                text.append(f"{name}\n", style="bold #d4d4d4")
                text.append(str(desc), style="#d4d4d4")
                desc_widget.update(text)

                if tool:
                    enabled_icon = "ON" if tool_enabled else "OFF"
                    toggle_btn.display = True
                    toggle_btn.label = f"Enabled: {enabled_icon}"
                else:
                    toggle_btn.display = False

            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to update tool description pane: %s", e
                )
                try:
                    from ..interface.notifier import notify

                    notify("warning", f"TUI: failed to update tool description: {e}")
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about tool desc update failure: %s",
                        e,
                    )
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Unhandled error in on_tool_selected: %s", e
            )
            try:
                from ..interface.notifier import notify

                notify("warning", f"TUI: error handling tool selection: {e}")
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about tool selection error: %s", e
                )

    @on(Button.Pressed, "#tools-close")
    def close_tools(self) -> None:
        self.app.pop_screen()

    # ------------------------------------------------------------

    @on(Button.Pressed, "#tool-toggle-enabled")
    async def toggle_enabled(self) -> None:

        try:

            tool = self.selected_tool
            if tool is None:
                return

            tool.enabled = not tool.enabled

            await self._refresh_tool_widget()

        except Exception as e:
            logging.getLogger(__name__).exception("Toggle failed: %s", e)
            try:
                from ..interface.notifier import notify

                # Make best effort naming
                tool_name = getattr(tool, "name", None) or (
                    tool.get("name") if isinstance(tool, dict) else str(tool)
                )
                notify("error", f"Failed to toggle tool {tool_name}: {e}")
            except Exception:
                pass
            return

    async def _refresh_tool_widget(self) -> None:
        if self.selected_tool:
            # Simulate reselecting same node
            dummy = type("Node", (), {"data": {"tool": self.selected_tool}})
            event = type("Evt", (), {"node": dummy})
            self.on_tool_selected(event)
            self.tui._update_header()


class ConversationsScreen(ModalScreen):
    """Conversation history browser — split-pane layout.

    Left pane: list of saved conversations (title + date).
    Right pane: metadata preview of the selected entry.
    Buttons: Restore (loads the conversation) + Close.
    Dismisses with the selected ConversationMeta, or None to cancel.
    """

    BINDINGS = [
        Binding("escape", "cancel_screen", "Close"),
        Binding("q", "cancel_screen", "Close"),
    ]

    CSS = """
    ConversationsScreen { align: center middle; }
    #conv-prefs-row {
        height: 3;
        align: center middle;
        padding: 0 2;
    }
    #conv-prefs-label {
        padding: 0 1;
        color: #9a9a9a;
    }
    """

    def __init__(self, conversations: list, store) -> None:
        super().__init__()
        self._conversations = conversations
        self._store = store
        self._selected = None

    def compose(self) -> ComposeResult:
        with Container(id="conv-container"):
            with Horizontal(id="conv-split"):
                with Vertical(id="conv-left"):
                    yield Static("Saved Conversations", id="conv-title")
                    yield Tree("CONVERSATIONS", id="conv-tree")
                with Vertical(id="conv-right"):
                    yield Static("Preview", id="conv-preview-title")
                    yield ScrollableContainer(
                        Static("Select a conversation to preview.", id="conv-preview"),
                        id="conv-preview-scroll",
                    )
            with Horizontal(id="conv-prefs-row"):
                yield Switch(id="conv-auto-reload", value=False)
                yield Static(
                    "Auto-reload last session on startup", id="conv-prefs-label"
                )
            with Center():
                yield Button("Restore", id="conv-restore", disabled=True)
                yield Button("Close", id="conv-close")

    def on_mount(self) -> None:
        tree = self.query_one("#conv-tree", Tree)
        root = tree.root
        root.allow_expand = True
        root.show_root = False
        for meta in self._conversations:
            label = f"{meta.title[:40]}  [{meta.created_at[:10]}]  ({meta.message_count} msgs)"
            root.add(label, data={"meta": meta})
        if not self._conversations:
            try:
                self.query_one("#conv-preview", Static).update(
                    "No saved conversations found."
                )
            except Exception:
                pass
        try:
            tree.focus()
        except Exception:
            pass
        # Load auto-reload preference
        try:
            import json as _json

            from ..workspaces.utils import get_preferences_file

            prefs_file = get_preferences_file()
            if prefs_file.exists():
                prefs = _json.loads(prefs_file.read_text(encoding="utf-8"))
                value = bool(prefs.get("auto_reload_session", False))
            else:
                value = False
            self.query_one("#conv-auto-reload", Switch).value = value
        except Exception:
            pass

    @on(Switch.Changed, "#conv-auto-reload")
    def on_auto_reload_changed(self, event: Switch.Changed) -> None:
        try:
            import json as _json

            from ..workspaces.utils import get_preferences_file

            prefs_file = get_preferences_file()
            prefs = {}
            if prefs_file.exists():
                try:
                    prefs = _json.loads(prefs_file.read_text(encoding="utf-8"))
                except Exception:
                    prefs = {}
            prefs["auto_reload_session"] = event.value
            prefs_file.write_text(_json.dumps(prefs, indent=2), encoding="utf-8")
        except Exception:
            pass

    @on(Tree.NodeSelected, "#conv-tree")
    def on_conv_selected(self, event: Tree.NodeSelected) -> None:
        meta = event.node.data.get("meta") if event.node.data else None
        self._selected = meta
        try:
            self.query_one("#conv-restore", Button).disabled = meta is None
        except Exception:
            pass
        if meta is None:
            return
        try:
            from rich.text import Text as RichText

            text = RichText()
            text.append(f"{meta.title}\n", style="bold #d4d4d4")
            text.append(
                f"Date:     {meta.created_at[:19].replace('T', ' ')}  |  ",
                style="#9a9a9a",
            )
            text.append(f"Messages: {meta.message_count}\n", style="#9a9a9a")
            text.append("─" * 40 + "\n", style="#444444")

            messages = self._store.load(meta.id)
            shown = 0
            for msg in messages:
                if shown >= 5:
                    remaining = len(messages) - shown
                    text.append(f"\n… {remaining} more message(s)", style="#6a6a6a")
                    break
                if msg.role == "user":
                    snippet = (msg.content or "").replace("\n", " ").strip()[:200]
                    text.append("\nYou: ", style="bold #7ec8e3")
                    text.append(snippet + "\n", style="#d4d4d4")
                    shown += 1
                elif msg.role == "assistant":
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            text.append("\n[tool] ", style="bold #e3c07e")
                            text.append(f"{tc.name}\n", style="#d4d4d4")
                            shown += 1
                            if shown >= 5:
                                break
                    elif msg.content and msg.content.strip():
                        snippet = msg.content.replace("\n", " ").strip()[:200]
                        text.append("\nAgent: ", style="bold #a8cc8c")
                        text.append(snippet + "\n", style="#d4d4d4")
                        shown += 1
                elif msg.role == "tool_result" and msg.tool_results:
                    for tr in msg.tool_results:
                        result_text = (
                            (tr.result or tr.error or "")
                            .replace("\n", " ")
                            .strip()[:150]
                        )
                        text.append(f"\n  ↳ {tr.tool_name}: ", style="#9a9a9a")
                        text.append(result_text + "\n", style="#888888")
                        shown += 1
                        if shown >= 5:
                            break

            self.query_one("#conv-preview", Static).update(text)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to update conversation preview: %s", e
            )

    @on(Button.Pressed, "#conv-restore")
    def restore_conversation(self) -> None:
        if self._selected:
            self.dismiss(self._selected)

    @on(Button.Pressed, "#conv-close")
    def close_screen(self) -> None:
        self.dismiss(None)

    def action_cancel_screen(self) -> None:
        self.dismiss(None)


class MCPScreen(ModalScreen):
    """Interactive MCP browser — split-pane layout."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    CSS = """
    MCPScreen { align: center middle; }
    """

    from ..agents.pa_agent import FlagHunterAgent
    from ..mcp import MCPManager, MCPServerConfig, SSEServerConfig, StdioServerConfig

    def __init__(
        self, mcp_manager: MCPManager, agent: FlagHunterAgent, tui: "FlagHunterTUI"
    ) -> None:
        super().__init__()
        self.mcp_manager = mcp_manager
        self.agent = agent
        self.tui = tui
        self.selected_server = None
        self.selected_tool = None

    # ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Container(id="mcp-container"):
            with Horizontal(id="mcp-split"):

                # LEFT SIDE
                with Vertical(id="mcp-left"):
                    yield Static("MCP Servers", id="mcp-title")
                    yield Tree("MCP Servers", id="mcp-tree")

                # RIGHT SIDE
                with Vertical(id="mcp-right"):
                    # ---- Toggle Button ----
                    yield Button("Enabled: OFF", id="mcp-toggle-enabled")
                    yield Static("Description", id="mcp-desc-title")

                    yield ScrollableContainer(
                        Static("Select a MCP server to view details.", id="mcp-desc"),
                        id="mcp-desc-scroll",
                    )

            yield Center(Button("Close", id="mcp-close"))

    # ------------------------------------------------------------

    def on_mount(self) -> None:
        try:
            tree = self.query_one("#mcp-tree", Tree)
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to query MCP tree: %s", e)
            return

        root = tree.root
        root.allow_expand = True
        root.show_root = False

        servers = self.mcp_manager.get_all_servers()

        for server in servers:
            server_node = root.add(server.name, data={"server": server})
            for tool in server.tools:
                server_node.add(tool["name"], data={"tool": tool})

        # Hide toggle button initially
        toggle_btn = self.query_one("#mcp-toggle-enabled", Button)
        toggle_btn.display = False

        try:
            tree.focus()
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to focus MCP tree: %s", e)

    # ------------------------------------------------------------

    @on(Tree.NodeSelected, "#mcp-tree")
    def on_mcp_selected(self, event: Tree.NodeSelected) -> None:
        from ..mcp import MCPServer, SSEServerConfig, StdioServerConfig

        node = event.node

        self.selected_server = node.data.get("server") if node.data else None
        self.selected_tool = node.data.get("tool") if node.data else None

        desc_widget = self.query_one("#mcp-desc", Static)
        toggle_btn = self.query_one("#mcp-toggle-enabled", Button)

        text = Text()

        if self.selected_server is not None:
            mcp: MCPServer = self.selected_server

            text.append(f"{mcp.name}\n", style="bold #d4d4d4")
            text.append(f"{mcp.config.description}\n\n", style="#d4d4d4")

            text.append(f"Type: {mcp.config.type}\n", style="#9a9a9a")

            if isinstance(mcp.config, SSEServerConfig):
                text.append(f"URL: {mcp.config.url}\n", style="#9a9a9a")

            elif isinstance(mcp.config, StdioServerConfig):
                text.append(f"Command: {mcp.config.command}\n", style="#9a9a9a")
                text.append(f"Args: {mcp.config.args}\n\n", style="#9a9a9a")

            enabled_icon = "ON" if mcp.config.enabled else "OFF"
            connected_icon = "ON" if mcp.connected else "OFF"

            text.append(f"Connected: {connected_icon}\n", style="#9a9a9a")

            if mcp.last_error:
                text.append(f"\nLast error: {mcp.last_error}\n", style="#e91b1b")

            logs = mcp.get_logs()

            if logs:
                text.append(f"\n{logs}\n", style="#86e41a")

            desc_widget.update(text)

            toggle_btn.display = True
            toggle_btn.label = f"Enabled: {enabled_icon}"

        elif self.selected_tool is not None:
            text.append(f"{self.selected_tool['description']}\n", style="#d4d4d4")
            desc_widget.update(text)
            toggle_btn.display = False

        else:
            desc_widget.update("Choose a server.")
            toggle_btn.display = False

    # ------------------------------------------------------------

    @on(Button.Pressed, "#mcp-toggle-enabled")
    async def toggle_enabled(self) -> None:
        mcp = self.selected_server
        if mcp is None:
            return

        try:
            new_value = not mcp.config.enabled

            if new_value:
                await self.mcp_manager.enable(mcp.name)
                tools = self.mcp_manager.create_mcp_tools_from_server(mcp)
                self.agent.add_tools(tools)
            else:
                tools = self.mcp_manager.create_mcp_tools_from_server(mcp)
                self.agent.delete_tools(tools)
                await self.mcp_manager.disable(mcp.name)

            self.tui._update_header()

        except Exception as e:
            logging.getLogger(__name__).exception("Toggle failed: %s", e)
            try:
                from ..interface.notifier import notify

                notify("error", f"Failed to toggle {mcp.name}: {e}")
            except Exception:
                pass
            return

        # Refresh UI
        self._refresh_description()

    # ------------------------------------------------------------

    def _refresh_description(self):
        """Rebuild right-hand side using current selection."""
        if self.selected_server:
            # Simulate reselecting same node
            dummy = type("Node", (), {"data": {"server": self.selected_server}})
            event = type("Evt", (), {"node": dummy})
            self.on_mcp_selected(event)

    # ------------------------------------------------------------

    @on(Button.Pressed, "#mcp-close")
    def close_mcp(self) -> None:
        self.app.pop_screen()


# ----- Rewind confirmation modal -----


class RewindConfirmScreen(ModalScreen[bool]):
    """Small confirmation dialog before rewinding the conversation."""

    BINDINGS = [
        Binding("escape", "dismiss_false", "Cancel"),
        Binding("n", "dismiss_false", "No"),
        Binding("y", "dismiss_true", "Yes"),
    ]

    CSS = """
    RewindConfirmScreen {
        align: center middle;
    }
    #rewind-confirm-container {
        width: 52;
        height: 11;
        background: #121212;
        border: solid #3a3a3a;
        padding: 1 2;
        layout: vertical;
    }
    #rewind-confirm-title {
        text-align: center;
        color: #d4d4d4;
        height: 3;
        content-align: center middle;
    }
    #rewind-yes {
        width: 12;
        background: #1a1a1a;
        color: #e07070;
        border: none;
        margin: 0 1;
    }
    #rewind-yes:hover { background: #2a1a1a; }
    #rewind-no {
        width: 12;
        background: #1a1a1a;
        color: #75d164;
        border: none;
        margin: 0 1;
    }
    #rewind-no:hover { background: #262626; }
    """

    def compose(self) -> ComposeResult:
        with Container(id="rewind-confirm-container"):
            yield Static(
                "Rewind conversation from this point?", id="rewind-confirm-title"
            )
            yield Center(
                Button("Yes  (y)", id="rewind-yes"), Button("No  (n)", id="rewind-no")
            )

    def action_dismiss_false(self) -> None:
        self.dismiss(False)

    def action_dismiss_true(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#rewind-yes")
    def confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#rewind-no")
    def cancel(self) -> None:
        self.dismiss(False)


class ForkConfirmScreen(ModalScreen[bool]):
    """Confirmation dialog before forking — saves the current conversation first."""

    BINDINGS = [
        Binding("escape", "dismiss_false", "Cancel"),
        Binding("n", "dismiss_false", "No"),
        Binding("y", "dismiss_true", "Yes"),
    ]

    CSS = """
    ForkConfirmScreen {
        align: center middle;
    }
    #fork-confirm-container {
        width: 56;
        height: 13;
        background: #121212;
        border: solid #3a3a3a;
        padding: 1 2;
        layout: vertical;
    }
    #fork-confirm-title {
        text-align: center;
        color: #d4d4d4;
        height: 5;
        content-align: center middle;
    }
    #fork-yes {
        width: 12;
        background: #1a1a1a;
        color: #70a0e0;
        border: none;
        margin: 0 1;
    }
    #fork-yes:hover { background: #1a1a2a; }
    #fork-no {
        width: 12;
        background: #1a1a1a;
        color: #75d164;
        border: none;
        margin: 0 1;
    }
    #fork-no:hover { background: #262626; }
    """

    def compose(self) -> ComposeResult:
        with Container(id="fork-confirm-container"):
            yield Static(
                "Fork conversation from this point?\nThe current conversation will be saved.",
                id="fork-confirm-title",
            )
            yield Center(
                Button("Yes  (y)", id="fork-yes"), Button("No  (n)", id="fork-no")
            )

    def action_dismiss_false(self) -> None:
        self.dismiss(False)

    def action_dismiss_true(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#fork-yes")
    def confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#fork-no")
    def cancel(self) -> None:
        self.dismiss(False)
