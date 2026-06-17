"""
PentestAgent TUI - Terminal User Interface
"""

import asyncio
import json
import logging
import re
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

try:
    import pyperclip
except Exception:  # pragma: no cover - optional clipboard dependency
    pyperclip = None
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import (
    Center,
    Container,
    Horizontal,
    ScrollableContainer,
    Vertical,
)
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.scrollbar import ScrollBar, ScrollBarRender
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Button, Static, Switch, TextArea, Tree
from textual.widgets.tree import TreeNode

from ..config.constants import DEFAULT_MODEL

# ANSI escape sequence pattern for stripping control codes from input
_ANSI_ESCAPE = re.compile(
    r"\x1b\[[0-9;]*[mGKHflSTABCDEFsu]|\x1b\].*?\x07|\x1b\[<[0-9;]*[Mm]"
)


# ASCII-safe scrollbar renderer to avoid Unicode glyph issues
class ASCIIScrollBarRender(ScrollBarRender):
    """Scrollbar renderer using ASCII-safe characters."""

    BLANK_GLYPH = " "
    VERTICAL_BARS = [" ", " ", " ", " ", " ", " ", " ", " "]
    HORIZONTAL_BARS = [" ", " ", " ", " ", " ", " ", " ", " "]


# Apply ASCII scrollbar globally
ScrollBar.renderer = ASCIIScrollBarRender


# Custom Tree with ASCII-safe icons for PowerShell compatibility
class CrewTree(Tree):
    """Tree widget with ASCII-compatible expand/collapse icons."""

    ICON_NODE = "> "
    ICON_NODE_EXPANDED = "v "


if TYPE_CHECKING:
    from ..agents.pa_agent import PentestAgentAgent


# Each entry is (signature, description).
# Signature tokens that are <placeholders> or [optionals] match any user input.
COMMAND_SIGNATURES: List[tuple] = [
    ("/assist <task>", "Single AI call with tool execution"),
    ("/agent <task>", "Autonomous single-agent loop"),
    (
        '/ctf <url> [type=web|sqli|xss|lfi|cmd|crypto|pwn|misc] [hint="..."]',
        "CTF 快速模式：跳过泛化侦察，直接找 flag",
    ),
    ("/crew <task>", "Multi-agent: orchestrator + workers"),
    ("/interact <task>", "Guided interactive chat"),
    ("/retry", "Retry the most recent FAIL/IN_PROGRESS plan step"),
    ("/copy [n]", "Copy last n messages to clipboard (default 5)"),
    ("/retro", "Show unresolved retrospective items"),
    ("/retro resolve <id>", "Mark one retrospective item as resolved"),
    ("/nmap <target> [ports]", "Structured nmap scan → JSON port list"),
    ("/dirscan <url> [wordlist]", "Dir enumeration → structured found paths"),
    ("/nuclei <target> [severity]", "Nuclei template scan → findings list"),
    ("/sqlmap <url> [--data <data>]", "SQLmap injection test → structured result"),
    ("/target <host>", "Set pentest target host · 自动隔离 loot/notes 到该目标的 workspace"),
    ("/tools", "List and manage available tools"),
    ("/notes", "Show saved findings"),
    ("/graph", "Show attack path graph (Mermaid) from current notes"),
    ("/report", "Generate report from session"),
    ("/mcp list", "List configured MCP servers"),
    ("/mcp add stdio <name> <command> [args...]", "Add STDIO MCP server"),
    ("/mcp add sse <name> <url>", "Add SSE/HTTP MCP server"),
    # === CPA M1 HOOK BEGIN ===
    ("/api", "Show M1 API Hub provider status"),
    ("/api status", "Show provider health and cost"),
    ("/providers", "Show M1 API Hub provider status"),
    # === CPA M1 HOOK END ===
    # === CPA M2 HOOK BEGIN ===
    ("/ctf", "Show CTF Kit status panel"),
    ("/ctf list", "List available playbooks"),
    ("/ctf run <playbook> <target>", "Run a CTF playbook"),
    ("/ctf phase", "Show current phase progress"),
    ("/ctf next", "Advance to next phase"),
    ("/ctf flag <flag>", "Submit a flag"),
    ("/ctf hint <text>", "Record a high-priority user hint and continue"),
    ("/ctf override <flag>", "Force-upgrade a candidate/runtime flag to verified"),
    ("/ctf wrong <flag>", "Mark a previously extracted flag as wrong and continue"),
    ("/ctf reasoning", "Show latest CTF reasoning / stop report summary"),
    ("/ctf capabilities", "Show latest CTF capability snapshot"),
    ("/ctf memory", "Show latest strategy-memory audit and recent entries"),
    ("/ctf memory list [limit] [active|muted|deprecated]", "List strategy-memory entries"),
    ("/ctf memory show <id>", "Show one strategy-memory entry"),
    ("/ctf memory mute <id>", "Mute one strategy-memory entry"),
    ("/ctf memory activate <id>", "Re-activate one strategy-memory entry"),
    ("/ctf memory rollback <id>", "Rollback a mute and reactivate the entry"),
    ("/ctf memory audit [threshold]", "Audit low-quality strategy-memory entries"),
    ("/ctf memory delete <id>", "Delete one strategy-memory entry"),
    ("/ctf memory export <path>", "Export all strategy-memory entries to JSON"),
    ("/ctf memory clear confirm", "Clear all strategy-memory entries"),
    ("/ctf memory panel", "Mount StopReport + memory actions panel"),
    ("/ctf pwn <host> <port>", "Quick pwn: connect + leak"),
    ("/ctf decode <text>", "Auto-decode ciphertext"),
    ("/ctf rev <binary>", "Quick reverse engineering"),
    ("/ctf status", "Show CTF module diagnostics"),
    # === CPA M2 HOOK END ===
    # === CPA M3 HOOK BEGIN ===
    ("/report", "Show current report status"),
    ("/report new <title>", "Create a new pentest report"),
    ("/report finding <title> <severity>", "Add a finding to current report"),
    ("/report export [html|md|pdf|all]", "Export report to file"),
    ("/report status", "Show M3 Reporter module status"),
    # === CPA M3 HOOK END ===
    # === CPA M4 HOOK BEGIN ===
    ("/audit", "Show Audit Guard status"),
    ("/audit log [n]", "Show last N audit entries"),
    ("/audit scope <target>", "Check if target is in scope"),
    ("/audit roe <file>", "Load Rules of Engagement file"),
    ("/audit mask <text>", "Redact sensitive data from text"),
    ("/audit status", "Show M4 module diagnostics"),
    # === CPA M4 HOOK END ===
    # === CPA M5 HOOK BEGIN ===
    ("/swarm", "Show Swarm Link status (requires CPA_M5_SWARM_LINK=true)"),
    ("/swarm status", "Show pheromone stats and active targets"),
    ("/swarm top [n]", "Show top N pheromone targets"),
    ("/swarm deposit <target> [amount]", "Deposit pheromone on a target"),
    ("/swarm board [n]", "Show last N blackboard messages"),
    ("/swarm msg <content>", "Post message to shared blackboard"),
    ("/swarm propose <question>", "Start a consensus vote"),
    ("/swarm vote <vote_id> <choice>", "Cast a vote"),
    ("/swarm reset", "Reset all pheromone data"),
    # === CPA M5 HOOK END ===
    # === CPA M6 HOOK BEGIN ===
    ("/turbo", "Show Turbo acceleration status"),
    ("/turbo status", "Cache hit rate + memory + concurrency stats"),
    ("/turbo cache stats", "Cache statistics"),
    ("/turbo cache clear [tool]", "Clear cache (all or by tool)"),
    ("/turbo memory", "Memory usage report"),
    ("/turbo memory cleanup", "Trigger garbage collection"),
    ("/turbo wrap <tool>", "Enable turbo for a tool"),
    ("/turbo wrap list", "List wrapped tools"),
    ("/turbo unwrap <tool>", "Disable turbo for a tool"),
    ("/turbo parallel <targets...>", "Run parallel scan on targets"),
    # === CPA M6 HOOK END ===
    ("/workspace list", "List all workspaces"),
    ("/workspace info <name>", "Show workspace info"),
    ("/workspace note <text>", "Add note to active workspace"),
    ("/workspace clear", "Deactivate current workspace"),
    ("/workspace help", "Show workspace help"),
    ("/workspace <name>", "Create or activate workspace"),
    ("/spawn <task>", "Spawn child MCP agent"),
    ("/despawn <server_name>", "Despawn child MCP agent"),
    ("/conversations", "Browse saved conversations"),
    ("/clear", "Clear chat history"),
    ("/memory", "Show memory statistics"),
    ("/token", "Show token usage statistics"),
    ("/prompt", "Show system prompt"),
    ("/help", "Show help"),
    ("/quit", "Exit PentestAgent"),
]


def _is_placeholder(token: str) -> bool:
    return (token.startswith("<") and token.endswith(">")) or (
        token.startswith("[") and token.endswith("]")
    )


def _sig_matches(sig: str, value: str) -> bool:
    """Return True if the current input is a valid prefix path of the signature."""
    sig_tokens = sig.split()
    stripped = value.rstrip()
    has_trailing = bool(value) and value[-1] == " "
    val_tokens = stripped.split() if stripped else []

    completed = val_tokens if has_trailing else val_tokens[:-1]
    partial = "" if has_trailing else (val_tokens[-1] if val_tokens else "")

    if len(completed) > len(sig_tokens):
        return False

    for i, tok in enumerate(completed):
        sig_tok = sig_tokens[i]
        if _is_placeholder(sig_tok):
            continue
        if sig_tok != tok:
            return False

    if partial:
        next_idx = len(completed)
        if next_idx >= len(sig_tokens):
            return False
        sig_tok = sig_tokens[next_idx]
        if _is_placeholder(sig_tok):
            return True
        return sig_tok.startswith(partial)

    return True


def _get_display_parts(sig: str, value: str) -> tuple:
    """Return (next_token, remaining_tokens_str) for rendering the suggestion row."""
    sig_tokens = sig.split()
    stripped = value.rstrip()
    has_trailing = bool(value) and value[-1] == " "
    val_tokens = stripped.split() if stripped else []

    next_idx = len(val_tokens) if has_trailing else max(0, len(val_tokens) - 1)
    next_tok = sig_tokens[next_idx] if next_idx < len(sig_tokens) else ""
    remaining = (
        " ".join(sig_tokens[next_idx + 1 :]) if next_idx + 1 < len(sig_tokens) else ""
    )
    return next_tok, remaining


def _tab_complete(sig: str, value: str) -> str:
    """Return new input value produced by Tab-completing the given signature."""
    sig_tokens = sig.split()
    stripped = value.rstrip()
    has_trailing = bool(value) and value[-1] == " "
    val_tokens = stripped.split() if stripped else []

    next_idx = len(val_tokens) if has_trailing else max(0, len(val_tokens) - 1)
    if next_idx >= len(sig_tokens):
        return value

    kept = val_tokens[:next_idx]
    return " ".join(kept + [sig_tokens[next_idx]]) + " "


class CommandSuggestions(Widget):
    """Floating autocomplete dropdown for slash commands."""

    DEFAULT_CSS = """
    CommandSuggestions {
        display: none;
        width: 100%;
        height: auto;
        max-height: 12;
        background: #1a1a1a;
        border: round #383838;
        padding: 0;
        margin: 0 2;
        overflow-y: auto;
    }
    CommandSuggestions .suggestion-item {
        width: 100%;
        height: 1;
        padding: 0 1;
    }
    CommandSuggestions .suggestion-item.--selected {
        background: #252525;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._matches: List[tuple] = []
        self._selected: int = 0
        self._current_value: str = ""

    def compose(self) -> ComposeResult:
        return iter([])

    def update_suggestions(self, value: str) -> None:
        self._current_value = value
        self._matches = [
            (sig, desc) for sig, desc in COMMAND_SIGNATURES if _sig_matches(sig, value)
        ]
        self._selected = 0
        self._rebuild()
        self.display = bool(self._matches)

    def _rebuild(self) -> None:
        self.remove_children()
        for i, (sig, desc) in enumerate(self._matches):
            next_tok, remaining = _get_display_parts(sig, self._current_value)
            label = Text()
            if next_tok:
                if _is_placeholder(next_tok):
                    label.append(next_tok, style="bold #f59e0b")
                else:
                    label.append(next_tok, style="bold #38bdf8")
            if remaining:
                label.append(f" {remaining}", style="#4a4a4a")
            label.append(f"  {desc}", style="italic #4a4a4a")
            item = Static(label, classes="suggestion-item")
            if i == self._selected:
                item.add_class("--selected")
            self.mount(item)

    def select_next(self) -> None:
        if not self._matches:
            return
        self._selected = (self._selected + 1) % len(self._matches)
        self._highlight()

    def select_previous(self) -> None:
        if not self._matches:
            return
        self._selected = (self._selected - 1) % len(self._matches)
        self._highlight()

    def _highlight(self) -> None:
        children = list(self.children)
        for i, child in enumerate(children[: len(self._matches)]):
            if i == self._selected:
                child.add_class("--selected")
            else:
                child.remove_class("--selected")

    def get_tab_completion(self) -> Optional[str]:
        """Return new input value after Tab, or None if nothing to complete."""
        if not self._matches or self._selected >= len(self._matches):
            return None
        sig = self._matches[self._selected][0]
        return _tab_complete(sig, self._current_value)

    def hide(self) -> None:
        self._matches = []
        self._selected = 0
        self._current_value = ""
        self.display = False
        self.remove_children()


class ChatInputTextArea(TextArea):
    """Multi-line chat input with Enter submission and Shift+Enter newline."""

    BINDINGS = TextArea.BINDINGS

    @dataclass
    class Submitted(Message):
        """Posted when the operator submits the chat input."""

        text_area: "ChatInputTextArea"
        text: str

        @property
        def control(self) -> "ChatInputTextArea":
            return self.text_area

    def action_submit_input(self) -> None:
        """Submit the current content."""
        self.post_message(self.Submitted(self, self.text))

    def action_insert_newline(self) -> None:
        """Insert a newline explicitly for Shift+Enter."""
        self.insert("\n")

    async def _on_key(self, event: events.Key) -> None:
        """Override TextArea's default Enter=newline behavior for chat input."""
        if self.read_only:
            return

        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.action_submit_input()
            return

        if event.key in {"shift+enter", "alt+enter"}:
            event.stop()
            event.prevent_default()
            self.action_insert_newline()
            return

        await super()._on_key(event)


def wrap_text_lines(text: str, width: int = 80) -> List[str]:
    """
    Wrap text content preserving line breaks and wrapping long lines.

    Args:
        text: The text to wrap
        width: Maximum width per line (default 80 for safe terminal fit)

    Returns:
        List of wrapped lines
    """
    result = []
    for line in text.split("\n"):
        if len(line) <= width:
            result.append(line)
        else:
            # Wrap long lines
            wrapped = textwrap.wrap(
                line, width=width, break_long_words=False, break_on_hyphens=False
            )
            result.extend(wrapped if wrapped else [""])
    return result


# ----- Help Screen -----


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
            Static("PentestAgent Help", id="help-title"),
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

    def __init__(self, tools: List[Tool], tui: "PentestAgentTUI") -> None:
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

    from ..agents.pa_agent import PentestAgentAgent
    from ..mcp import MCPManager, MCPServerConfig, SSEServerConfig, StdioServerConfig

    def __init__(
        self, mcp_manager: MCPManager, agent: PentestAgentAgent, tui: "PentestAgentTUI"
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


# ----- MCP task event message (for safe cross-task UI updates) -----


class MCPTaskEvent(Message):
    """Posted by on_mcp_event() so Textual handles the UI update safely."""

    def __init__(self, event: str, data: dict) -> None:
        super().__init__()
        self.event = event
        self.data = data


class SpawnTerminalMessage(Message):
    """Posted when a child agent requests an EmbeddedTerminal widget."""

    def __init__(self, master_fd: int, label: str) -> None:
        super().__init__()
        self.master_fd = master_fd
        self.label = label


class DespawnTerminalMessage(Message):
    """Posted when a child agent has been despawned and its terminal should be removed."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label


class ChildAgentWakeUpMessage(Message):
    """Posted (thread-safely) when a child async task completes and the parent
    agent is idle.  Triggers _run_wake_up_mode() through Textual's message loop
    so we never call @work methods from an arbitrary async context."""


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


# ----- Copy to clipboard button -----


class CopyButton(Static):
    """Minimal copy-to-clipboard button using Static instead of Button"""

    DEFAULT_CSS = """
    CopyButton {
        width: auto;
        height: 1;
        color: #6a6a6a;
        background: transparent;
        padding: 0 1;
    }
    CopyButton:hover {
        color: #d4d4d4;
        background: #2a2a2a;
    }
    CopyButton.-copied {
        color: #4ec994;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("copy", **kwargs)

    def on_click(self, event: Click) -> None:
        self.post_message(CopyButton.Pressed(self))
        event.stop()

    class Pressed(Message):
        def __init__(self, button: "CopyButton") -> None:
            super().__init__()
            self.button = button


class RewindButton(Static):
    """Button to rewind conversation from this message."""

    DEFAULT_CSS = """
    RewindButton {
        width: auto;
        height: 1;
        color: #6a6a6a;
        background: transparent;
        padding: 0 1;
    }
    RewindButton:hover {
        color: #d4d4d4;
        background: #2a2a2a;
    }
    RewindButton.-active {
        color: #e07070;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("<< rewind", **kwargs)

    def on_click(self, event: Click) -> None:
        self.post_message(RewindButton.Pressed(self))
        event.stop()

    class Pressed(Message):
        def __init__(self, button: "RewindButton") -> None:
            super().__init__()
            self.button = button


class ForkButton(Static):
    """Button to fork conversation from this message (saves current history first)."""

    DEFAULT_CSS = """
    ForkButton {
        width: auto;
        height: 1;
        color: #6a6a6a;
        background: transparent;
        padding: 0 1;
    }
    ForkButton:hover {
        color: #d4d4d4;
        background: #2a2a2a;
    }
    ForkButton.-active {
        color: #70a0e0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(">> fork", **kwargs)

    def on_click(self, event: Click) -> None:
        self.post_message(ForkButton.Pressed(self))
        event.stop()

    class Pressed(Message):
        def __init__(self, button: "ForkButton") -> None:
            super().__init__()
            self.button = button


class CopyableMixin(Static):
    """Base class for messages with a copy button."""

    _copy_content: str = ""
    _header_text: Text = Text()
    _body_text: Text = Text()

    DEFAULT_CSS = """
    CopyableMixin { layout: vertical; padding: 0; }
    CopyableMixin .message-header { layout: horizontal; height: 1; width: 100%; }
    CopyableMixin .message-body { padding-left: 2; }
    CopyableMixin .btn-group { dock: right; width: auto; height: 1; layout: horizontal; background: transparent; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(classes="message-header"):
            yield Static(self._header_text)
            with Horizontal(classes="btn-group"):
                yield CopyButton(classes="copy-btn")
        yield Static(self._body_text, classes="message-body")

    def on_copy_button_pressed(self, event: CopyButton.Pressed) -> None:

        try:
            if pyperclip is None:
                raise RuntimeError("pyperclip not installed")
            pyperclip.copy(self._copy_content)
            btn = self.query_one(".copy-btn", CopyButton)
            btn.update("copied")
            btn.add_class("-copied")
            self.set_timer(2, self._reset_copy_btn)

        except Exception as e:
            logging.getLogger(__name__).exception("Failed to update status bar: %s", e)
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to copy output to the clipboard: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about status bar update failure: %s", ne
                )

    def _reset_copy_btn(self) -> None:
        btn = self.query_one(".copy-btn", CopyButton)
        btn.update("copy")
        btn.remove_class("-copied")


# ----- Main Chat Message Widgets -----


class ThinkingMessage(CopyableMixin):
    def __init__(self, content: str, **kwargs):
        super().__init__(**kwargs)
        self._copy_content = content
        self._header_text = Text.assemble(
            ("* ", "#9a9a9a"), ("Thinking", "bold #9a9a9a")
        )
        body = Text()
        for line in wrap_text_lines(content, width=90):
            body.append(f"{line}\n", style="#6b6b6b italic")
        self._body_text = body


class ToolMessage(Static):
    """Tool execution message"""

    TOOL_COLOR = "#9a9a9a"
    ARG_COLOR = "#6b6b6b"
    HINT_COLOR = "#6b6b6b"

    CHEVRON_COLLAPSED = ">"
    CHEVRON_EXPANDED = "v"
    HINT_TEXT = " (click to see result)"

    expanded: bool = reactive(False, layout=True)

    def __init__(self, tool_name: str, args: str = "", **kwargs):
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.tool_args = args
        self._result_widget: ToolResultMessage | None = None

    def render(self) -> Text:
        text = Text()

        chevron = self.CHEVRON_EXPANDED if self.expanded else self.CHEVRON_COLLAPSED

        # Header line
        text.append(f"{chevron} ", style=self.TOOL_COLOR)
        text.append(self.tool_name, style=self.TOOL_COLOR)

        # Hint text (only when result exists and is collapsed)
        if self._result_widget and not self.expanded:
            text.append(self.HINT_TEXT, style=self.HINT_COLOR)

        text.append("\n")

        # Tool arguments
        if self.tool_args:
            for line in wrap_text_lines(self.tool_args, width=110):
                text.append(f"  {line}\n", style=self.ARG_COLOR)

        return text

    def attach_result(self, result_widget: "ToolResultMessage") -> None:
        """Attach a ToolResultMessage widget below this message."""
        if self._result_widget is not None:
            return

        self._result_widget = result_widget
        self._result_widget.display = self.expanded

        # Mount directly after this widget
        self.mount(self._result_widget, after=self)

    def on_click(self) -> None:
        self.expanded = not self.expanded
        if self._result_widget:
            self._result_widget.display = self.expanded


class ToolResultMessage(CopyableMixin):
    RESULT_ICON = "#"
    RESULT_COLOR = "#124670"
    OUTPUT_COLOR = "#17606d"

    def __init__(self, tool_name: str, result: str = "", **kwargs):
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.result = result
        self._copy_content = result
        self._header_text = Text.assemble(
            (f"{self.RESULT_ICON} ", self.RESULT_COLOR),
            (f"{tool_name} output", self.RESULT_COLOR),
        )
        body = Text()
        if result:
            for line in wrap_text_lines(result, width=110):
                body.append(f"{line}\n", style=self.OUTPUT_COLOR)
        self._body_text = body


class AssistantMessage(CopyableMixin):
    def __init__(self, content: str, **kwargs):
        super().__init__(**kwargs)
        self._copy_content = content
        self._header_text = Text.assemble(
            (">> ", "#9a9a9a"), ("PentestAgent", "bold #d4d4d4")
        )
        body = Text()
        for line in wrap_text_lines(content, width=90):
            body.append(f"{line}\n", style="#d4d4d4")
        self._body_text = body


class UserMessage(CopyableMixin):
    def __init__(self, content: str, **kwargs):
        super().__init__(**kwargs)
        self._copy_content = content
        self._header_text = Text.assemble(("> ", "#9a9a9a"), ("You", "bold #d4d4d4"))
        body = Text()
        for line in wrap_text_lines(content, width=90):
            body.append(f"{line}\n", style="#d4d4d4")
        self._body_text = body

    def compose(self) -> ComposeResult:
        with Horizontal(classes="message-header"):
            yield Static(self._header_text)
            with Horizontal(classes="btn-group"):
                yield RewindButton(classes="rewind-btn")
                yield ForkButton(classes="fork-btn")
                yield CopyButton(classes="copy-btn")
        yield Static(self._body_text, classes="message-body")

    def on_rewind_button_pressed(self, event: RewindButton.Pressed) -> None:
        self.post_message(UserMessage.RewindPressed(self))

    def on_fork_button_pressed(self, event: ForkButton.Pressed) -> None:
        self.post_message(UserMessage.ForkPressed(self))

    class RewindPressed(Message):
        def __init__(self, user_message: "UserMessage") -> None:
            super().__init__()
            self.user_message = user_message

    class ForkPressed(Message):
        def __init__(self, user_message: "UserMessage") -> None:
            super().__init__()
            self.user_message = user_message


class SystemMessage(Static):
    """System message"""

    def __init__(self, content: str, **kwargs):
        super().__init__(**kwargs)
        self.message_content = content

    def render(self) -> Text:
        text = Text()
        for line in self.message_content.split("\n"):
            text.append(f"  {line}\n", style="#6b6b6b")  # phantom - subtle system text
        return text


# ----- Status Bar -----


class StatusBar(Static):
    """Animated status bar"""

    status = reactive("idle")
    mode = reactive("assist")  # "assist" or "agent"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._frame = 0
        self._timer: Optional[Timer] = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.2, self._tick)

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % 4
        if self.status not in ["idle", "complete"]:
            self.refresh()

    def render(self) -> Text:
        dots = "." * (self._frame + 1)

        # Use fixed-width labels (pad dots to 4 chars so text doesn't jump)
        dots_padded = dots.ljust(4)

        # PA theme status colors (muted, ethereal)
        status_map = {
            "idle": ("Ready", "#6b6b6b"),
            "initializing": (f"Initializing{dots_padded}", "#9a9a9a"),
            "thinking": (f"Thinking{dots_padded}", "#9a9a9a"),
            "running": (f"Running{dots_padded}", "#9a9a9a"),
            "processing": (f"Processing{dots_padded}", "#9a9a9a"),
            "waiting": ("Waiting for input", "#9a9a9a"),
            "complete": ("Complete", "#4a9f6e"),
            "error": ("Error", "#9f4a4a"),
        }

        label, color = status_map.get(self.status, (self.status, "#6b6b6b"))

        text = Text()

        # Show mode (ASCII-safe symbols)
        if self.mode == "crew":
            text.append("  :: Crew ", style="#9a9a9a")
        elif self.mode == "agent":
            text.append("  >> Agent ", style="#9a9a9a")
        elif self.mode == "interact":
            text.append("  >> Interact ", style="#9a9a9a")
        elif self.mode == "mcp":
            text.append("  [MCP] ", style="#6b9a9a")
        else:
            text.append("  >> Assist ", style="#9a9a9a")

        text.append(f"| {label}", style=color)

        if self.status not in ["idle", "initializing", "complete", "error"]:
            text.append("    ESC to stop", style="#525252")

        return text


class MemoryDiagnostics(Static):
    """Live memory diagnostics widget mounted into the chat area.

    This widget polls the agent's LLM memory stats periodically and
    renders a compact, updating diagnostics panel.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._timer: Optional[Timer] = None

    def on_mount(self) -> None:
        # Refresh periodically for a lively display
        self._timer = self.set_interval(0.8, self.refresh)

    def on_unmount(self) -> None:
        if self._timer:
            self._timer.stop()

    def _bar(self, ratio: float, width: int = 20) -> str:
        filled = int(max(0, min(1.0, ratio)) * width)
        return "█" * filled + "░" * (width - filled)

    def render(self) -> Text:
        text = Text()

        try:
            app = self.app
            agent = getattr(app, "agent", None)
            if not agent or not getattr(agent, "llm", None):
                text.append("Memory Diagnostics\n", style="bold #d4d4d4")
                text.append("Agent not initialized", style="#9a9a9a")
                return text

            stats = agent.llm.get_memory_stats()
            msgs = len(agent.conversation_history)
            llm_msgs = agent._format_messages_for_llm()
            current_tokens = agent.llm.memory.get_total_tokens(llm_msgs)

            budget = stats.get("token_budget") or 1
            thresh = stats.get("summarize_threshold") or budget
            recent_keep = stats.get("recent_to_keep", 5)
            has_summary = stats.get("has_summary", False)
            summarized_count = stats.get("summarized_message_count", 0)

            # Header
            text.append("Memory Diagnostics\n", style="bold #d4d4d4")

            # Use a consistent bar width for all bars and align labels
            bar_width = 28
            labels = ["Tokens:", "Messages:", "Retention:"]
            label_width = max(len(label_text) for label_text in labels)

            # Tokens line
            ratio = current_tokens / max(1, budget)
            bar = self._bar(ratio, width=bar_width)
            label = "Tokens:".ljust(label_width)
            text.append(
                f"{label} [{bar}] {current_tokens:,} / {budget:,}\n", style="#9a9a9a"
            )

            # Messages line (scale messages to an expected max window)
            expected_msgs_max = max(1, recent_keep * 6)
            mratio = min(1.0, msgs / expected_msgs_max)
            mbar = self._bar(mratio, width=bar_width)
            label = "Messages:".ljust(label_width)
            text.append(f"{label} [{mbar}] {msgs} active\n", style="#9a9a9a")

            # Retention / recent
            k_ratio = min(1.0, recent_keep / max(1, recent_keep))
            keep_bar = self._bar(k_ratio, width=bar_width)
            label = "Retention:".ljust(label_width)
            text.append(
                f"{label} [{keep_bar}] keeping last {recent_keep}\n", style="#9a9a9a"
            )

            # Summary status
            summary_state = "active" if has_summary else "inactive"
            emoji = "ON" if has_summary else "OFF"
            text.append(f"Summary: {emoji} {summary_state}\n", style="#9a9a9a")

            # Summarized / threshold
            text.append(
                f"Summarized: {summarized_count} / {thresh:,}\n", style="#9a9a9a"
            )
            text.append(f"Threshold: {thresh:,}\n", style="#9a9a9a")

        except Exception as e:
            text.append(f"Memory diagnostics error: {e}", style="#9a9a9a")

        return text


class CTFMemoryOperationsPanel(Static):
    """Compact static panel for StopReport + strategy-memory actions."""

    DEFAULT_CSS = """
    CTFMemoryOperationsPanel {
        width: 100%;
        height: auto;
        background: #121212;
        border: round #3a3a3a;
        padding: 1 2;
        margin: 1 0;
    }
    """

    def __init__(self, title: str, body: str, **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._body = body

    def render(self) -> Text:
        text = Text()
        text.append(f"{self._title}\n", style="bold #d4d4d4")
        text.append(self._body, style="#9a9a9a")
        return text


class CTFMemoryControlPanel(Static):
    """Interactive strategy-memory control panel mounted in chat area."""

    DEFAULT_CSS = """
    CTFMemoryControlPanel {
        width: 100%;
        height: auto;
        background: #121212;
        border: round #3a3a3a;
        padding: 1;
        margin: 1 0;
        layout: vertical;
    }
    #ctf-memory-control-summary {
        height: auto;
        color: #9a9a9a;
        padding: 0 1 1 1;
    }
    #ctf-memory-control-toolbar {
        height: auto;
        layout: horizontal;
        padding: 0 0 1 0;
    }
    #ctf-memory-control-actions {
        height: auto;
        layout: horizontal;
        padding: 1 0 0 0;
    }
    #ctf-memory-control-main {
        height: 18;
        layout: horizontal;
    }
    #ctf-memory-control-left {
        width: 38;
        height: 100%;
        border: round #262626;
        margin-right: 1;
    }
    #ctf-memory-control-right {
        width: 1fr;
        height: 100%;
        border: round #262626;
        padding: 0 1;
    }
    #ctf-memory-control-detail {
        height: 100%;
        color: #d4d4d4;
    }
    """

    def __init__(
        self,
        tui: "PentestAgentTUI",
        *,
        filter_mode: str = "all",
        sort_by: str = "recent",
        threshold: float = 0.3,
        preferred_entry_ids: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.tui = tui
        self.filter_mode = filter_mode
        self.sort_by = sort_by
        self.threshold = threshold
        self.preferred_entry_ids = [
            str(entry_id).strip()
            for entry_id in (preferred_entry_ids or [])
            if str(entry_id).strip()
        ]
        self.entries: list[Any] = []
        self.selected_entry_id: str | None = None
        self._armed_delete_entry_id: str | None = None
        self._clear_armed = False

    def compose(self) -> ComposeResult:
        yield Static("", id="ctf-memory-control-summary")
        with Horizontal(id="ctf-memory-control-toolbar"):
            yield Button("Refresh", id="ctf-mem-refresh")
            yield Button("All", id="ctf-mem-filter-all")
            yield Button("Active", id="ctf-mem-filter-active")
            yield Button("Muted", id="ctf-mem-filter-muted")
            yield Button("Audit", id="ctf-mem-filter-audit")
            yield Button("Sort:Recent", id="ctf-mem-sort-recent")
            yield Button("Sort:Corr", id="ctf-mem-sort-correlation")
            yield Button("Sort:Applied", id="ctf-mem-sort-applied")
        with Horizontal(id="ctf-memory-control-main"):
            with Vertical(id="ctf-memory-control-left"):
                yield Tree("MEMORY", id="ctf-memory-tree")
            with Vertical(id="ctf-memory-control-right"):
                yield Static("Select an entry to view details.", id="ctf-memory-control-detail")
        with Horizontal(id="ctf-memory-control-actions"):
            yield Button("Mute", id="ctf-mem-action-mute")
            yield Button("Activate", id="ctf-mem-action-activate")
            yield Button("Rollback", id="ctf-mem-action-rollback")
            yield Button("Delete", id="ctf-mem-action-delete")
            yield Button("Export", id="ctf-mem-action-export")
            yield Button("Clear All", id="ctf-mem-action-clear")

    async def on_mount(self) -> None:
        await self.reload_panel()

    @on(Tree.NodeSelected, "#ctf-memory-tree")
    def on_memory_selected(self, event: Tree.NodeSelected) -> None:
        entry_id = event.node.data.get("entry_id") if event.node.data else None
        self.selected_entry_id = str(entry_id) if entry_id else None
        self._armed_delete_entry_id = None
        self._update_detail()
        self._update_action_buttons()

    @on(Button.Pressed, "#ctf-mem-refresh")
    async def on_refresh_pressed(self) -> None:
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-filter-all")
    async def on_filter_all(self) -> None:
        self.filter_mode = "all"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-filter-active")
    async def on_filter_active(self) -> None:
        self.filter_mode = "active"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-filter-muted")
    async def on_filter_muted(self) -> None:
        self.filter_mode = "muted"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-filter-audit")
    async def on_filter_audit(self) -> None:
        self.filter_mode = "audit"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-sort-recent")
    async def on_sort_recent(self) -> None:
        self.sort_by = "recent"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-sort-correlation")
    async def on_sort_correlation(self) -> None:
        self.sort_by = "correlation"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-sort-applied")
    async def on_sort_applied(self) -> None:
        self.sort_by = "applied"
        await self.reload_panel()

    @on(Button.Pressed, "#ctf-mem-action-mute")
    async def on_action_mute(self) -> None:
        await self._run_selected_entry_action("mute")

    @on(Button.Pressed, "#ctf-mem-action-activate")
    async def on_action_activate(self) -> None:
        await self._run_selected_entry_action("activate")

    @on(Button.Pressed, "#ctf-mem-action-rollback")
    async def on_action_rollback(self) -> None:
        await self._run_selected_entry_action("rollback")

    @on(Button.Pressed, "#ctf-mem-action-delete")
    async def on_action_delete(self) -> None:
        if not self.selected_entry_id:
            return
        if self._armed_delete_entry_id != self.selected_entry_id:
            self._armed_delete_entry_id = self.selected_entry_id
            self.tui._add_system(
                f"[CTF memory] delete armed for {self.selected_entry_id}; click Delete again to confirm."
            )
            self._update_action_buttons()
            return
        await self._run_selected_entry_action("delete")

    @on(Button.Pressed, "#ctf-mem-action-export")
    async def on_action_export(self) -> None:
        await self._run_selected_entry_action("export")

    @on(Button.Pressed, "#ctf-mem-action-clear")
    async def on_action_clear(self) -> None:
        if not self._clear_armed:
            self._clear_armed = True
            self.tui._add_system("[CTF memory] clear armed; click Clear All again to confirm.")
            self._update_action_buttons()
            return
        await self._run_selected_entry_action("clear")

    async def reload_panel(self) -> None:
        from ..agents.pa_agent.strategy_memory import StrategyMemoryStore

        store = StrategyMemoryStore()
        stats = await store.stats(threshold=self.threshold)
        if self.filter_mode == "audit":
            self.entries = await store.audit_entries(
                threshold=self.threshold,
                sort_by=self.sort_by if self.sort_by != "recent" else "correlation",
            )
        else:
            manual_status = None if self.filter_mode == "all" else self.filter_mode
            self.entries = await store.list_entries(
                limit=50,
                manual_status=manual_status,
                sort_by=self.sort_by,
            )

        tree = self.query_one("#ctf-memory-tree", Tree)
        tree.root.remove_children()
        tree.root.show_root = False
        for entry in self.entries:
            label = (
                f"{entry.id} "
                f"[{entry.metadata.manual_status}] "
                f"applied={entry.metadata.applied_count} "
                f"corr={entry.metadata.success_correlation:.2f}"
            )
            tree.root.add(label, data={"entry_id": entry.id})

        valid_ids = {entry.id for entry in self.entries}
        if self.selected_entry_id not in valid_ids:
            self.selected_entry_id = None
            for preferred_id in self.preferred_entry_ids:
                if preferred_id in valid_ids:
                    self.selected_entry_id = preferred_id
                    break
            if self.selected_entry_id is None:
                self.selected_entry_id = self.entries[0].id if self.entries else None
        self._armed_delete_entry_id = None
        self._clear_armed = False

        summary = self.query_one("#ctf-memory-control-summary", Static)
        summary.update(
            "\n".join(
                [
                    f"view={self.filter_mode} sort={self.sort_by} threshold={self.threshold:.2f}",
                    f"stats total={stats['total']} active={stats['active']} muted={stats['muted']} deprecated={stats['deprecated']} audit_candidates={stats['audit_candidates']}",
                    self.tui._build_ctf_memory_panel_body(),
                ]
            )
        )
        self._update_detail()
        self._update_action_buttons()
        try:
            tree.focus()
        except Exception:
            pass

    def _selected_entry(self) -> Any | None:
        for entry in self.entries:
            if entry.id == self.selected_entry_id:
                return entry
        return None

    def _update_detail(self) -> None:
        detail = self.query_one("#ctf-memory-control-detail", Static)
        entry = self._selected_entry()
        if entry is None:
            detail.update("No entry selected.")
            return
        detail.update(self.tui._format_ctf_memory_entry_detail(entry))

    def _update_action_buttons(self) -> None:
        entry = self._selected_entry()
        has_entry = entry is not None
        for selector in (
            "#ctf-mem-action-mute",
            "#ctf-mem-action-activate",
            "#ctf-mem-action-rollback",
            "#ctf-mem-action-delete",
        ):
            try:
                self.query_one(selector, Button).disabled = not has_entry
            except Exception:
                pass
        try:
            delete_btn = self.query_one("#ctf-mem-action-delete", Button)
            delete_btn.label = (
                "Delete (confirm)"
                if has_entry and self._armed_delete_entry_id == self.selected_entry_id
                else "Delete"
            )
        except Exception:
            pass
        try:
            clear_btn = self.query_one("#ctf-mem-action-clear", Button)
            clear_btn.label = "Clear All (confirm)" if self._clear_armed else "Clear All"
        except Exception:
            pass

    async def _run_selected_entry_action(self, action: str) -> None:
        from ..agents.pa_agent.strategy_memory import StrategyMemoryStore

        store = StrategyMemoryStore()
        entry = self._selected_entry()
        target_id = entry.id if entry is not None else None

        if action in {"mute", "activate", "rollback", "delete"} and not target_id:
            self.tui._add_system("[CTF memory] no entry selected.")
            return

        message = ""
        if action == "mute":
            updated = await store.mute_entry(target_id or "")
            message = (
                f"[CTF memory] muted {target_id}" if updated is not None else f"[CTF memory] mute failed: {target_id}"
            )
        elif action == "activate":
            updated = await store.activate_entry(target_id or "")
            message = (
                f"[CTF memory] activated {target_id}" if updated is not None else f"[CTF memory] activate failed: {target_id}"
            )
        elif action == "rollback":
            updated = await store.rollback_mute(target_id or "")
            message = (
                f"[CTF memory] rollback applied to {target_id}" if updated is not None else f"[CTF memory] rollback failed: {target_id}"
            )
        elif action == "delete":
            deleted = await store.delete_entry(target_id or "")
            message = (
                f"[CTF memory] deleted {target_id}" if deleted else f"[CTF memory] delete failed: {target_id}"
            )
        elif action == "export":
            export_path = Path("loot") / "strategy_memory_export.json"
            exported = await store.export_entries(export_path)
            message = f"[CTF memory] exported to {exported}"
        elif action == "clear":
            count = await store.clear_entries()
            message = f"[CTF memory] cleared {count} entries"

        if message:
            self.tui._add_system(message)
        await self.reload_panel()


class TokenDiagnostics(Static):
    """Live token/cost diagnostics panel mounted into the chat area.

    Reads persisted daily usage from the token_tracker, computes cost
    using environment variables, and displays a simple ASCII progress bar.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._timer: Optional[Timer] = None

    def on_mount(self) -> None:
        # Refresh periodically for a lively display
        self._timer = self.set_interval(1.0, self.refresh)

    def on_unmount(self) -> None:
        if self._timer:
            self._timer.stop()

    def _bar(self, ratio: float, width: int = 28) -> str:
        """Block-style usage bar matching MemoryDiagnostics visuals."""
        r = max(0.0, min(1.0, ratio))
        filled = int(r * width)
        return "█" * filled + "░" * (width - filled)

    def render(self) -> Text:
        text = Text()
        try:
            import os

            # Lazy import of token_tracker (best-effort)
            try:
                from ..tools import token_tracker
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to import token_tracker: %s", e
                )
                try:
                    from ..interface.notifier import notify

                    notify("warning", f"TUI: token tracker import failed: {e}")
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about token_tracker import failure: %s",
                        e,
                    )
                token_tracker = None

            text.append("Token Usage Diagnostics\n", style="bold #d4d4d4")

            if not token_tracker:
                text.append(
                    "Token tracker not available (tools/token_tracker).\n",
                    style="#9a9a9a",
                )
                return text

            stats = token_tracker.get_stats_sync()

            # If a reset is pending (date changed), perform a reset now so daily
            # usage is accurate and visible to the user.
            reset_occurred = False
            if stats.get("reset_pending"):
                try:
                    token_tracker.record_usage_sync(0, 0)
                    stats = token_tracker.get_stats_sync()
                    reset_occurred = True
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Token tracker reset failed: %s", e
                    )
                    try:
                        from ..interface.notifier import notify

                        notify("warning", f"Token tracker reset failed: {e}")
                    except Exception as e:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about token tracker reset failure: %s",
                            e,
                        )

            # Extract values
            last_in = int(stats.get("last_input_tokens", 0) or 0)
            last_out = int(stats.get("last_output_tokens", 0) or 0)
            last_total = int(stats.get("last_total_tokens", 0) or 0)
            daily_usage = int(stats.get("daily_usage", 0) or 0)
            last_reset = stats.get("last_reset_date")
            current_date = stats.get("current_date")

            # (env parsing moved below)

            # Environment cost config
            def _parse_env(name: str):
                v = os.getenv(name)
                if v is None or v == "":
                    return None
                try:
                    return float(v)
                except Exception as e:
                    logging.getLogger(__name__).debug(
                        "Failed to parse env var %s: %s", name, e
                    )
                    return "INVALID"

            unified = _parse_env("COST_PER_MILLION")
            input_cost_per_m = _parse_env("INPUT_COST_PER_MILLION")
            output_cost_per_m = _parse_env("OUTPUT_COST_PER_MILLION")
            daily_limit = _parse_env("DAILY_TOKEN_LIMIT")

            # Determine if any env-based limits exist
            has_env_limits = any(
                v is not None
                for v in (unified, input_cost_per_m, output_cost_per_m, daily_limit)
            )

            # If nothing has been recorded yet (no tokens, no daily usage)
            # and no env limits are configured, show the concise sentinel only.
            if last_total == 0 and daily_usage == 0 and not has_env_limits:
                text.append("No token usage recorded\n", style="#9a9a9a")
                return text

            # Validate env vars
            env_errors = []
            if unified == "INVALID":
                env_errors.append("COST_PER_MILLION is not numeric")
            if input_cost_per_m == "INVALID":
                env_errors.append("INPUT_COST_PER_MILLION is not numeric")
            if output_cost_per_m == "INVALID":
                env_errors.append("OUTPUT_COST_PER_MILLION is not numeric")
            if daily_limit == "INVALID":
                env_errors.append("DAILY_TOKEN_LIMIT is not numeric")

            if env_errors:
                text.append("Environment configuration errors:\n", style="#ef4444")
                for e in env_errors:
                    text.append(f"  - {e}\n", style="#9a9a9a")
                text.append(
                    "\nSet environment variables correctly to compute costs.\n",
                    style="#9a9a9a",
                )
                return text

            # Compute costs
            if unified is not None:
                # Use unified cost for both input and output
                input_cost = (last_in / 1_000_000.0) * float(unified)
                output_cost = (last_out / 1_000_000.0) * float(unified)
            else:
                # Require per-direction costs to be present to compute
                if input_cost_per_m is None or output_cost_per_m is None:
                    text.append(
                        "Cost vars missing. Set COST_PER_MILLION or both INPUT_COST_PER_MILLION and OUTPUT_COST_PER_MILLION.\n",
                        style="#9a9a9a",
                    )
                    # Still show numeric token stats below
                    input_cost = output_cost = None
                else:
                    input_cost = (last_in / 1_000_000.0) * float(input_cost_per_m)
                    output_cost = (last_out / 1_000_000.0) * float(output_cost_per_m)

            total_cost = None
            if input_cost is not None and output_cost is not None:
                total_cost = input_cost + output_cost

            # Daily budget calculations per spec
            # Derive daily usage excluding last command (in case tracker already included it)
            daily_without_last = max(daily_usage - last_total, 0)
            new_daily_total = daily_without_last + last_total

            remaining_tokens = None
            percent_used = None
            if daily_limit is not None:
                try:
                    dl = float(daily_limit)
                    remaining_tokens = max(int(dl - new_daily_total), 0)
                    percent_used = (new_daily_total / max(1.0, dl)) * 100.0
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to compute daily limit values: %s", e
                    )
                    try:
                        from ..interface.notifier import notify

                        notify(
                            "warning", f"TUI: failed to compute daily token limit: {e}"
                        )
                    except Exception as e:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about daily limit computation failure: %s",
                            e,
                        )
                    remaining_tokens = None

            # Render structured panel with aligned labels and block bars
            bar_width = 28
            labels = [
                "Last command:",
                "Cost:",
                "Daily usage:",
                "Remaining:",
                "Usage:",
                "Last reset:",
                "Current date:",
                "Reset occurred:",
            ]
            label_width = max(len(label_text) for label_text in labels)

            # Last command tokens
            label = "Last command:".ljust(label_width)
            text.append(
                f"{label} in={last_in:,} out={last_out:,} total={last_total:,}\n",
                style="#9a9a9a",
            )

            # Cost line
            label = "Cost:".ljust(label_width)
            if input_cost is not None and output_cost is not None:
                text.append(
                    f"{label} in=${input_cost:.6f} out=${output_cost:.6f} total=${total_cost:.6f}\n",
                    style="#9a9a9a",
                )
            else:
                text.append(
                    f"{label} not computed (missing env vars)\n",
                    style="#9a9a9a",
                )

            # Daily usage
            label = "Daily usage:".ljust(label_width)
            text.append(f"{label} {new_daily_total:,}\n", style="#9a9a9a")

            # Remaining tokens
            label = "Remaining:".ljust(label_width)
            if remaining_tokens is not None:
                text.append(f"{label} {remaining_tokens:,}\n", style="#9a9a9a")
            else:
                text.append(
                    f"{label} N/A (DAILY_TOKEN_LIMIT not set)\n",
                    style="#9a9a9a",
                )

            # Usage percent + bar
            label = "Usage:".ljust(label_width)
            if percent_used is not None:
                bar = self._bar(percent_used / 100.0, width=bar_width)
                text.append(
                    f"{label} [{bar}] {percent_used:.1f}%\n",
                    style="#9a9a9a",
                )
            else:
                text.append(f"{label} N/A\n", style="#9a9a9a")

            # Dates
            label = "Last reset:".ljust(label_width)
            text.append(f"{label} {last_reset}\n", style="#9a9a9a")
            label = "Current date:".ljust(label_width)
            text.append(f"{label} {current_date}\n", style="#9a9a9a")

            # Reset occurrence
            label = "Reset occurred:".ljust(label_width)
            text.append(
                f"{label} {'Yes' if reset_occurred else 'No'}\n",
                style="#9a9a9a",
            )

        except Exception as e:
            text.append(f"Token diagnostics error: {e}\n", style="#9a9a9a")

        return text


# ----- Resize Divider -----


class ResizeDivider(Widget):
    """Draggable vertical divider between the chat area and the agents panel.

    Drag left to expand the agents panel; drag right to shrink it (giving more
    room back to the parent chat area).  Hidden when the agents panel is not
    visible.
    """

    DEFAULT_CSS = """
    ResizeDivider {
        width: 2;
        height: 100%;
        background: #1a1a1a;
        color: #3a3a3a;
        display: none;
        content-align: center middle;
    }
    ResizeDivider.visible {
        display: block;
    }
    ResizeDivider:hover {
        background: #262626;
        color: #7878b0;
    }
    ResizeDivider.dragging {
        background: #262626;
        color: #9090d0;
    }
    """

    # Each row renders this single character — a thin vertical bar.
    _CHAR_IDLE = "│"
    _CHAR_ACTIVE = "┃"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._dragging: bool = False
        self._start_x: int = 0
        self._start_width: int = 84

    def render(self) -> Text:
        char = self._CHAR_ACTIVE if self._dragging else self._CHAR_IDLE
        h = max(1, self.size.height)
        return Text("\n".join([char] * h), no_wrap=True, overflow="fold")

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._dragging = True
        self._start_x = event.screen_x
        try:
            panel = self.app.query_one("#agents-panel")
            self._start_width = panel.size.width
        except Exception:
            self._start_width = 84
        self.add_class("dragging")
        self.refresh()
        self.capture_mouse()
        event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._dragging:
            return
        # Drag left  → expand agents-panel (delta negative → new_width grows)
        # Drag right → shrink agents-panel (delta positive → new_width shrinks)
        delta = event.screen_x - self._start_x
        new_width = max(20, self._start_width - delta)
        try:
            panel = self.app.query_one("#agents-panel")
            panel.styles.width = new_width
        except Exception:
            pass
        event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._dragging:
            self._dragging = False
            self.remove_class("dragging")
            self.refresh()
            self.release_mouse()
        event.stop()


# ----- Main TUI App -----


class PentestAgentTUI(App):
    """Main PentestAgent TUI Application"""

    # ═══════════════════════════════════════════════════════════
    # PA THEME - Ethereal grays
    # ═══════════════════════════════════════════════════════════
    # Void:       #0a0a0a  (terminal black - the darkness)
    # Shadow:     #121212  (subtle surface)
    # Mist:       #1a1a1a  (panels, elevated)
    # Whisper:    #262626  (default borders)
    # Fog:        #3a3a3a  (hover states)
    # Apparition: #525252  (focus states)
    # Phantom:    #6b6b6b  (secondary text)
    # Spirit:     #9a9a9a  (normal text)
    # Specter:    #d4d4d4  (primary text)
    # Ectoplasm:  #f0f0f0  (highlights)
    # ═══════════════════════════════════════════════════════════

    CSS = """
    Screen {
        background: #0a0a0a;
    }

    #main-container {
        width: 100%;
        height: 100%;
        layout: horizontal;
    }

    /* Chat area - takes full width normally, fills remaining space with sidebar */
    #chat-area {
        width: 1fr;
        height: 100%;
    }

    #chat-area.with-sidebar {
        width: 1fr;
    }

    #chat-scroll {
        width: 100%;
        height: 1fr;
        background: transparent;
        padding: 1 2;
        scrollbar-background: #1a1a1a;
        scrollbar-background-hover: #1a1a1a;
        scrollbar-background-active: #1a1a1a;
        scrollbar-color: #3a3a3a;
        scrollbar-color-hover: #3a3a3a;
        scrollbar-color-active: #3a3a3a;
        scrollbar-corner-color: #1a1a1a;
        scrollbar-size: 1 1;
    }

    #input-container {
        width: 100%;
        height: 5;
        background: transparent;
        border: round #262626;
        margin: 0 2;
        padding: 0;
        layout: horizontal;
        align-vertical: top;
    }

    #input-container:focus-within {
        border: round #525252;
    }

    #input-container:focus-within #chat-prompt {
        color: #d4d4d4;
    }

    #chat-prompt {
        width: auto;
        height: auto;
        padding: 1 0 0 1;
        color: #6b6b6b;
        content-align-vertical: top;
    }

    #chat-input {
        width: 1fr;
        height: 100%;
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
        color: #d4d4d4;
    }

    #chat-input:focus {
        border: none;
    }

    #chat-input:disabled {
        color: #525252;
        background: transparent;
    }

    #input-container.mcp-locked {
        border: round #1a1a1a;
        opacity: 0.5;
    }

    #tab-hint {
        display: none;
        width: auto;
        height: 100%;
        padding: 0 1;
        color: #3a3a3a;
        content-align-vertical: middle;
        text-style: italic;
    }

    #status-bar {
        width: 100%;
        height: 1;
        background: transparent;
        padding: 0 3;
        margin: 0;
    }

    .message {
        margin-bottom: 1;
    }

    /* Sidebar - hidden by default */
    #sidebar {
        width: 28;
        height: 100%;
        display: none;
        padding-right: 1;
    }

    #sidebar.visible {
        display: block;
    }

    #agents-panel {
        width: 84;
        height: 100%;
        display: none;
        padding-right: 1;
    }

    #agents-panel.visible {
        display: block;
    }

    #workers-tree {
        height: 1fr;
        background: transparent;
        border: round #262626;
        padding: 0 1;
        margin-bottom: 0;
    }

    #workers-tree:focus {
        border: round #3a3a3a;
    }

    #crew-stats {
        height: auto;
        max-height: 10;
        background: transparent;
        border: round #262626;
        border-title-color: #9a9a9a;
        border-title-style: bold;
        padding: 0 1;
        margin-top: 0;
    }

    Tree {
        background: transparent;
        color: #d4d4d4;
        scrollbar-background: #1a1a1a;
        scrollbar-background-hover: #1a1a1a;
        scrollbar-background-active: #1a1a1a;
        scrollbar-color: #3a3a3a;
        scrollbar-color-hover: #3a3a3a;
        scrollbar-color-active: #3a3a3a;
        scrollbar-size: 1 1;
    }

    Tree > .tree--cursor {
        background: transparent;
    }

    Tree > .tree--highlight {
        background: transparent;
    }

    Tree > .tree--highlight-line {
        background: transparent;
    }

    .tree--node-label {
        padding: 0 1;
    }

    .tree--node:hover .tree--node-label {
        background: transparent;
    }

    .tree--node.-selected .tree--node-label {
        background: transparent;
        color: #d4d4d4;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit_app", "Quit", priority=True),
        Binding("ctrl+c", "stop_agent", "Stop", priority=True, show=False),
        Binding("escape", "stop_agent", "Stop", priority=True),
        Binding("f1", "show_help", "Help"),
        Binding("tab", "focus_next", "Next", show=False),
        Binding("up", "history_up", "Prev", show=False),
        Binding("down", "history_down", "Next", show=False),
    ]

    TITLE = "PentestAgent"
    SUB_TITLE = "AI Penetration Testing"

    @property
    def _runtime(self):
        """Compatibility alias for command helpers that expect self._runtime."""
        return self.runtime

    def __init__(
        self,
        target: Optional[str] = None,
        model: Optional[str] = None,
        use_docker: bool = False,
        use_ssh: bool = False,
        mcp_mode: bool = False,
        prebuilt_components: Optional[Dict[str, Any]] = None,
        prebuilt_rag=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.target = target
        self.model = model or DEFAULT_MODEL
        self.use_docker = use_docker
        self.use_ssh = use_ssh
        self.runtime_info: Dict[str, Any] = {
            "selected": "ssh" if use_ssh else "docker" if use_docker else "local",
            "label": "SSH" if use_ssh else "Docker" if use_docker else "Local",
            "status_text": "",
            "connected": use_ssh or use_docker,
        }
        self._runtime_probe_timer = None
        self._runtime_probe_inflight = False
        self._prebuilt_rag = prebuilt_rag

        # MCP observation mode: TUI is read-only and driven by an external MCP server.
        self.mcp_mode = mcp_mode
        self._prebuilt_components = prebuilt_components

        # Agent components
        self.agent: Optional["PentestAgentAgent"] = None
        self.runtime = None
        self.mcp_manager = None
        self.all_tools = []
        self.rag_engine = None  # RAG engine

        # State
        self._mode = (
            "mcp" if mcp_mode else "assist"
        )  # "assist", "agent", "crew", "interact", "mcp"
        self._is_running = False
        self._is_initializing = True  # Block input during init
        self._should_stop = False
        self._flag_banner: str = ""
        self._current_conv_id: Optional[str] = (
            None  # ID of the ongoing conversation on disk
        )
        self._pending_tool_install: Optional[Dict[str, Any]] = None
        self._last_ctf_context: Dict[str, Any] = {}
        self._last_ctf_dispatcher: Any = None
        self._last_ctf_result: Any = None
        self._last_ctf_state: Dict[str, Any] | None = None

        # Per-task tool-message mapping for MCP observation mode
        self._mcp_tool_messages: Dict[str, Any] = {}
        # Worker handle returned by `@work` or an `asyncio.Task` (keep generic)
        self._current_worker: Optional[Any] = (
            None  # Track running worker for cancellation
        )
        self._current_crew = None  # Track crew orchestrator for cancellation

        # Crew mode state
        self._crew_workers: Dict[str, Dict[str, Any]] = {}
        self._crew_worker_nodes: Dict[str, TreeNode] = {}
        self._crew_orchestrator_node: Optional[TreeNode] = None
        self._crew_findings_count = 0
        self._viewing_worker_id: Optional[str] = None
        self._worker_events: Dict[str, List[Dict]] = {}
        self._crew_start_time: Optional[float] = None
        self._crew_tokens_used: int = 0
        self._crew_stats_timer: Optional[Timer] = None
        self._spinner_timer: Optional[Timer] = None
        self._spinner_frame: int = 0
        self._spinner_frames = [
            "⠋",
            "⠙",
            "⠹",
            "⠸",
            "⠼",
            "⠴",
            "⠦",
            "⠧",
            "⠇",
            "⠏",
        ]  # Braille dots spinner

        # Command history
        self._cmd_history: List[str] = []
        self._history_index: int = 0

        # Chat widgets list for rewind functionality
        self._chat_widgets: List[Widget] = []

    def _get_chat_input(self) -> ChatInputTextArea:
        """Return the multi-line chat input widget."""
        return self.query_one("#chat-input", ChatInputTextArea)

    def _get_chat_input_text(self) -> str:
        """Return current chat input text."""
        return self._get_chat_input().text

    def _set_chat_input_text(self, value: str) -> None:
        """Set chat input text and move the caret to the end."""
        input_widget = self._get_chat_input()
        input_widget.text = value
        lines = value.split("\n")
        input_widget.move_cursor((len(lines) - 1, len(lines[-1]) if lines else 0))

    def _clear_chat_input(self) -> None:
        """Clear chat input text."""
        self._set_chat_input_text("")

    @staticmethod
    def _should_offer_command_suggestions(value: str) -> bool:
        """Offer slash-command suggestions only for single-line slash input."""
        stripped = value.lstrip()
        return stripped.startswith("/") and "\n" not in value

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-container"):
            # Chat area (left side)
            with Vertical(id="chat-area"):
                # Persistent header shown above the chat scroll so operator
                # always sees runtime/mode/target information.
                yield Static("", id="header")
                yield ScrollableContainer(id="chat-scroll")
                yield StatusBar(id="status-bar")
                yield CommandSuggestions(id="cmd-suggestions")
                with Horizontal(id="input-container"):
                    yield Static("> ", id="chat-prompt")
                    if self.mcp_mode:
                        yield ChatInputTextArea(
                            placeholder="MCP Server Mode — read-only, tasks driven by MCP client",
                            id="chat-input",
                            disabled=True,
                            compact=True,
                            highlight_cursor_line=False,
                        )
                    else:
                        yield ChatInputTextArea(
                            placeholder="Enter task or type /help (Enter to send, Shift+Enter newline)",
                            id="chat-input",
                            compact=True,
                            highlight_cursor_line=False,
                        )
                    yield Static("Press Tab to autocomplete", id="tab-hint")

            # Resize divider — hidden until agents panel is visible
            yield ResizeDivider(id="resize-divider")

            # Agents panel (right side, hidden by default; shows EmbeddedTerminal widgets)
            with Vertical(id="agents-panel"):
                pass

            # Sidebar (right side, hidden by default)
            with Vertical(id="sidebar"):
                yield CrewTree("CREW", id="workers-tree")
                yield Static("", id="crew-stats")

    async def on_mount(self) -> None:
        """Initialize on mount"""
        # Register notifier callback so other modules can emit operator-visible messages
        try:
            from .notifier import (
                register_agent_wake_up_callback,
                register_callback,
                register_despawn_terminal_callback,
                register_spawn_terminal_callback,
            )

            register_callback(self._notifier_callback)
            register_spawn_terminal_callback(self._spawn_terminal_callback)
            register_despawn_terminal_callback(self._despawn_terminal_callback)
            register_agent_wake_up_callback(self._on_agent_wake_up_callback)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to register TUI notifier callback: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to register notifier callback: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about notifier registration failure: %s",
                    ne,
                )

        # Added, because the _notes variable is not properly loaded at the beginning and the notes.json is recreated unless you do a /notes command explicitely.
        from ..tools.notes import get_all_notes

        await get_all_notes()

        if not self.mcp_mode:
            self._runtime_probe_timer = self.set_interval(
                15.0, self._schedule_runtime_probe
            )

        if self.mcp_mode:
            # Activate MCP observation mode using pre-built components.
            _ = cast(Any, self._activate_mcp_mode())
        else:
            # Call the textual worker - decorator returns a Worker, not a coroutine
            _ = cast(Any, self._initialize_agent())

    @work(thread=False)
    async def _initialize_agent(self) -> None:
        """Initialize agent using the shared component builder."""
        self._set_status("initializing")

        try:
            from ..tools import get_all_tools
            from .initializer import build_agent_components, has_ssh_runtime_config

            if not self.model:
                self._add_system(
                    "[!] No model configured. Set PENTESTAGENT_MODEL environment variable or create a .env file (see .env.example)."
                )
                self._set_status("error")
                self._is_initializing = False
                return

            if self.use_ssh:
                self._add_system("+ Connecting to Kali VM over SSH...")
            elif self.use_docker:
                self._add_system("+ Starting Docker container...")
            elif has_ssh_runtime_config():
                self._add_system(
                    "+ Detected Kali VM SSH configuration — checking connectivity..."
                )

            def _on_progress(level: str, msg: str) -> None:
                if level == "warning":
                    self._add_system(f"[!] {msg}")
                # info messages are omitted from TUI chat to keep it clean

            # After external MCP tools are loaded, refresh header + tool list.
            def _after_mcp_load() -> None:
                self.all_tools = get_all_tools()
                self._update_header()
                if self.runtime and self.mcp_manager:
                    self.runtime.mcp_manager = self.mcp_manager

            components = await build_agent_components(
                target=self.target,
                scope=[],
                model=self.model,
                docker=self.use_docker,
                ssh=self.use_ssh,
                no_rag=False,
                no_mcp=False,
                on_progress=_on_progress,
                after_mcp_load=_after_mcp_load,
                prebuilt_rag=self._prebuilt_rag,
            )

            self.agent = components["agent"]
            self.runtime = components["runtime"]
            self.runtime_info = components.get("runtime_info", self.runtime_info)
            self.rag_engine = components["rag_engine"]
            self.all_tools = components["all_tools"]
            self.mcp_manager = components["mcp_manager"]
            rag_doc_count = components["rag_doc_count"]
            mcp_server_count = components["mcp_server_count"]

            # Wire runtime ↔ MCP manager now that both are ready.
            if self.runtime and self.mcp_manager:
                self.runtime.mcp_manager = self.mcp_manager

            # Inject spawn/despawn child-MCP-server tools (TUI-only feature).
            from ..tools import (
                create_despawn_mcp_agent_tool,
                create_spawn_mcp_agent_tool,
            )

            if self.agent is not None:
                self.agent.add_tools(
                    [
                        create_spawn_mcp_agent_tool(self.agent),
                        create_despawn_mcp_agent_tool(self.agent),
                    ]
                )

            self._set_status("idle", "assist")
            self._is_initializing = False

            selected_runtime = self.runtime_info.get("selected", "local")
            self.use_ssh = selected_runtime == "ssh"
            self.use_docker = selected_runtime == "docker"
            runtime_str = self.runtime_info.get(
                "label",
                "SSH" if self.use_ssh else "Docker" if self.use_docker else "Local",
            )
            self.mcp_server_count = mcp_server_count
            self.rag_doc_count = rag_doc_count
            try:
                self._update_header(
                    model_line=(
                        f"+ PentestAgent ready\n"
                        f"  Model: {self.model} | Tools: {len(self.all_tools)} | MCP: {mcp_server_count} | RAG: {rag_doc_count}\n"
                        f"  Runtime: {runtime_str} | Mode: Assist (use /agent or /crew for autonomous modes)"
                    )
                )
            except Exception:
                self._add_system(
                    f"+ PentestAgent ready\n"
                    f"  Model: {self.model} | Tools: {len(self.all_tools)} | MCP: {mcp_server_count} | RAG: {rag_doc_count}\n"
                    f"  Runtime: {runtime_str} | Mode: Assist (use /agent or /crew for autonomous modes)"
                )

            if self.target:
                try:
                    self._update_header(target=self.target)
                except Exception:
                    self._add_system(f"  Target: {self.target}")

            await self._restore_session()

        except Exception as e:
            import traceback

            self._add_system(f"[!] Init failed: {e}\n{traceback.format_exc()}")
            self._set_status("error")
            self._is_initializing = False

    # ------------------------------------------------------------------
    # MCP observation mode
    # ------------------------------------------------------------------

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
                        f"+ PentestAgent — MCP Server Mode (read-only)\n"
                        f"  Model: {self.model} | Tools: {len(self.all_tools)} | MCP servers: {mcp_server_count} | RAG: {rag_doc_count}\n"
                        f"  Waiting for MCP client tasks…"
                    )
                )
            except Exception:
                self._add_system(
                    f"+ PentestAgent — MCP Server Mode (read-only)\n"
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

    def _set_status(self, status: str, mode: Optional[str] = None) -> None:
        """Update status bar"""
        try:
            bar = self.query_one("#status-bar", StatusBar)
            bar.status = status
            if mode:
                bar.mode = mode
                self._mode = mode
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to update status bar: %s", e)
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to update status bar: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about status bar update failure: %s", ne
                )

    def _schedule_runtime_probe(self) -> None:
        """Kick off a background runtime probe if one is not already running."""
        if self.mcp_mode or self._runtime_probe_inflight:
            return
        _ = cast(Any, self._probe_runtime_connectivity())

    async def _switch_runtime(
        self, new_runtime: Any, new_runtime_info: Dict[str, Any], announce: str
    ) -> None:
        """Atomically switch the active runtime and refresh dependent state."""
        old_runtime = self.runtime

        self.runtime = new_runtime
        self.runtime_info = new_runtime_info
        self.use_ssh = new_runtime_info.get("selected") == "ssh"
        self.use_docker = new_runtime_info.get("selected") == "docker"

        if self.mcp_manager and self.runtime:
            self.runtime.mcp_manager = self.mcp_manager

        if self.agent is not None:
            self.agent.runtime = self.runtime

        self._update_header(target=self.target)
        self._add_system(announce)

        if old_runtime:
            try:
                await old_runtime.stop()
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed stopping previous runtime during switch: %s", e
                )

    @work(thread=False)
    async def _probe_runtime_connectivity(self) -> None:
        """Periodically probe Kali SSH reachability and hot-update runtime status."""
        if self._runtime_probe_inflight or self.mcp_mode:
            return

        self._runtime_probe_inflight = True
        probe_runtime = None

        try:
            from ..runtime.ssh_runtime import SSHRuntime
            from .initializer import build_runtime, has_ssh_runtime_config

            if not has_ssh_runtime_config():
                return

            probe_runtime = SSHRuntime()
            try:
                await probe_runtime.start()
                ssh_info = {
                    "requested": self.runtime_info.get("requested", "auto-ssh"),
                    "selected": "ssh",
                    "auto_selected": True,
                    "connected": True,
                    "host": probe_runtime.host,
                    "port": probe_runtime.port,
                    "user": probe_runtime.user,
                    "label": "SSH (auto)",
                    "status_text": (
                        f"SSH connected: {probe_runtime.user}@{probe_runtime.host}:{probe_runtime.port}"
                    ),
                    "fallback_reason": None,
                }

                if self.runtime_info.get("selected") == "ssh":
                    self.runtime_info.update(ssh_info)
                    self._update_header(target=self.target)
                    await probe_runtime.stop()
                    probe_runtime = None
                    return

                if self.runtime_info.get("requested") in ("auto", "auto-ssh"):
                    if self._is_running or self._is_initializing:
                        self.runtime_info.update(
                            {
                                "status_text": (
                                    "SSH available — will switch to SSHRuntime when idle"
                                ),
                                "host": probe_runtime.host,
                                "port": probe_runtime.port,
                                "user": probe_runtime.user,
                            }
                        )
                        self._update_header(target=self.target)
                        await probe_runtime.stop()
                        probe_runtime = None
                        return

                    await self._switch_runtime(
                        probe_runtime,
                        ssh_info,
                        "+ SSH became available — switched to SSHRuntime.",
                    )
                    probe_runtime = None
            except Exception as exc:
                selected_runtime = self.runtime_info.get("selected")
                requested_runtime = self.runtime_info.get("requested")

                if (
                    selected_runtime == "ssh"
                    and requested_runtime in ("auto", "auto-ssh")
                    and not self._is_running
                    and not self._is_initializing
                ):
                    local_runtime, local_info = await build_runtime(
                        docker=False,
                        ssh=False,
                        auto_ssh=False,
                    )
                    local_info.update(
                        {
                            "requested": requested_runtime,
                            "status_text": (
                                "SSH unavailable — fell back to LocalRuntime"
                            ),
                            "fallback_reason": str(exc),
                        }
                    )
                    await self._switch_runtime(
                        local_runtime,
                        local_info,
                        f"[!] SSH unavailable — switched to LocalRuntime: {exc}",
                    )
                    return

                if selected_runtime == "ssh":
                    self.runtime_info.update(
                        {
                            "connected": False,
                            "fallback_reason": str(exc),
                            "status_text": (
                                "SSH unavailable — retrying in background"
                                if requested_runtime in ("auto", "auto-ssh")
                                else "SSH disconnected"
                            ),
                        }
                    )
                    self._update_header(target=self.target)
                    return

                if requested_runtime in ("auto", "auto-ssh"):
                    self.runtime_info.update(
                        {
                            "connected": False,
                            "fallback_reason": str(exc),
                            "status_text": (
                                "SSH unavailable — using LocalRuntime"
                                if selected_runtime != "ssh"
                                else "SSH unavailable — retrying in background"
                            ),
                        }
                    )
                    self._update_header(target=self.target)
        finally:
            if probe_runtime is not None:
                try:
                    await probe_runtime.stop()
                except Exception:
                    pass
            self._runtime_probe_inflight = False

    def _format_tool_install_panel(self, payload: Dict[str, Any]) -> str:
        """Render a boxed warning for missing tools that need operator action."""
        tool = str(payload.get("tool", "unknown"))
        install_hint = str(
            payload.get("install_hint") or payload.get("message") or "Install manually."
        )
        size_mb = payload.get("size_mb", 0)
        size_display = f"~{size_mb} MB" if size_mb else "unknown"
        disk_free_gb = payload.get("disk_free_gb", "?")
        disk_free_pct = payload.get("disk_free_pct", "?")
        lines = [
            f"⚠ Tool Required: {tool}",
            f"Install: {install_hint}",
            f"Size: {size_display}  |  Disk free: {disk_free_gb} GB ({disk_free_pct}%)",
            "",
            "Agent will wait. Install manually, then",
            "type /retry to continue current step.",
        ]
        inner_width = max(45, max(len(line) for line in lines))
        top = "┌" + ("─" * (inner_width + 2)) + "┐"
        bottom = "└" + ("─" * (inner_width + 2)) + "┘"
        body = [f"│ {line.ljust(inner_width)} │" for line in lines]
        return "\n".join([top, *body, bottom])

    def _show_notification(self, level: str, message: Any) -> None:
        """Display a short operator-visible notification in the chat area."""
        try:
            if level.lower() == "flag_found":
                self._flag_banner = message
                self._add_system(f"🚩 FLAG FOUND: {message}")
                self._update_header()
                return
            if level.lower() == "tool_install_required":
                payload = message if isinstance(message, dict) else {"message": str(message)}
                self._pending_tool_install = payload
                self._add_system(self._format_tool_install_panel(payload))
                self._set_status("waiting", "agent" if self._mode == "agent" else self._mode)
                return
            # Prepend a concise system message so it is visible in the chat
            prefix = "[!]" if level.lower() in ("error", "critical") else "[!]"
            self._add_system(f"{prefix} {message}")
            # Set status bar to error briefly for emphasis
            if level.lower() in ("error", "critical"):
                self._set_status("error")
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to show notification in TUI: %s", e
            )

    def _notifier_callback(self, level: str, message: Any) -> None:
        """Callback wired to `flaghunter.interface.notifier`.

        This will be registered on mount so other modules can emit notifications.
        """
        try:
            try:
                asyncio.get_running_loop()
                # Already on the app's event loop (e.g. called from an asyncio task).
                # call_from_thread would raise here — call directly instead.
                self._show_notification(level, message)
                return
            except RuntimeError:
                pass
            # Called from a worker thread — use call_from_thread.
            if hasattr(self, "call_from_thread"):
                self.call_from_thread(self._show_notification, level, message)
            else:
                self._show_notification(level, message)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Exception in notifier callback handling: %s", e
            )

    def _find_retryable_plan_step(self) -> Optional[Any]:
        """Find the most recent FAIL or IN_PROGRESS plan step."""
        runtime = self.runtime or getattr(self.agent, "runtime", None)
        plan = getattr(runtime, "plan", None) if runtime else None
        if not plan or not getattr(plan, "steps", None):
            return None

        try:
            from ..tools.finish import StepStatus

            retryable = {
                StepStatus.FAIL,
                StepStatus.IN_PROGRESS,
                "fail",
                "in_progress",
            }
            for step in reversed(plan.steps):
                if getattr(step, "status", None) in retryable:
                    return step
        except Exception:
            return None
        return None

    async def _handle_retry_command(self) -> None:
        """Re-run the most recent failed/in-progress step without resetting the plan."""
        if not self.agent:
            self._add_system("[!] Agent not ready")
            return
        if self._is_running:
            self._add_system("[!] Agent is already running.")
            return

        step = self._find_retryable_plan_step()
        if not step:
            self._add_system("[!] No FAIL or IN_PROGRESS plan step available for /retry.")
            return

        try:
            from ..tools.finish import StepStatus

            step.status = StepStatus.PENDING
            step.result = None
        except Exception as exc:
            self._add_system(f"[!] Failed to reset retry step: {exc}")
            return

        tool_context = ""
        if self._pending_tool_install and self._pending_tool_install.get("tool"):
            tool_context = (
                f" Missing tool context: {self._pending_tool_install['tool']} "
                f"({self._pending_tool_install.get('install_hint', 'install manually')})."
            )

        self._add_system(
            f"[retry] Re-queued Step {step.id}: {step.description}"
        )
        self._pending_tool_install = None
        self._current_worker = self._run_retry_plan_step(
            step.id,
            str(step.description),
            tool_context,
        )

    @work(thread=False)
    async def _run_retry_plan_step(
        self, step_id: int, step_description: str, tool_context: str = ""
    ) -> None:
        """Continue the existing plan from a retried step."""
        if not self.agent:
            self._add_system("[!] Agent not ready")
            return

        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", "agent")

        retry_prompt = (
            f"Retry the current plan from Step {step_id}: {step_description}."
            f"{tool_context} Re-execute this step and continue the existing plan."
            " Do not reset the task or create a brand-new unrelated plan unless the"
            " current plan is no longer feasible."
        )

        try:
            tool_messages_mapping: dict[str, ToolMessage] = {}
            await self._display_responses(
                self.agent.continue_conversation(retry_prompt),
                tool_messages_mapping,
                is_agent=True,
            )
            self._set_status("complete", "agent")
            self._add_system("+ Retry complete. Back to assist mode.")
            await asyncio.sleep(1)
            self._set_status("idle", "assist")
        except asyncio.CancelledError:
            self._add_system("[!] Retry cancelled")
            self._set_status("idle", "assist")
        except Exception as e:
            self._add_system(f"[!] Retry error: {e}")
            self._set_status("error")
        finally:
            await self._save_current_conversation()
            self._is_running = False

    async def _handle_copy_command(self, cmd: str) -> None:
        """Copy the last N agent/system messages to the clipboard.

        Usage: /copy [n]   (default n=5)
        On Windows uses clip.exe; on Linux/macOS tries xclip/pbcopy.
        """
        import subprocess as _sp

        parts = cmd.strip().split()
        try:
            n = int(parts[1]) if len(parts) > 1 else 5
        except (IndexError, ValueError):
            n = 5

        # Collect text from the most recent N message widgets
        snippets: list[str] = []
        for w in self._chat_widgets[-n * 2 :]:  # overshoot, then trim
            if hasattr(w, "_copy_content"):
                snippets.append(w._copy_content)
            elif hasattr(w, "message_content"):
                snippets.append(w.message_content)
            if len(snippets) >= n:
                break

        if not snippets:
            self._add_system("[copy] No messages to copy.")
            return

        text = "\n\n---\n\n".join(snippets)

        try:
            import sys as _sys
            if _sys.platform == "win32":
                _sp.run(["clip"], input=text.encode("utf-16"), check=True)
            elif _sys.platform == "darwin":
                _sp.run(["pbcopy"], input=text.encode(), check=True)
            else:
                _sp.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
            self._add_system(f"[copy] {len(snippets)} message(s) copied to clipboard.")
        except Exception as e:
            # Fallback: write to a temp file
            import tempfile, pathlib
            tf = pathlib.Path(tempfile.gettempdir()) / "flaghunter_copy.txt"
            tf.write_text(text, encoding="utf-8")
            self._add_system(f"[copy] clipboard unavailable ({e}); saved to {tf}")

    async def _handle_retro_command(self, cmd: str) -> None:
        """Show unresolved retrospective items or resolve an item by id."""
        parts = cmd.strip().split()

        try:
            from ..knowledge.retrospective import (
                get_unresolved_entries,
                mark_resolved,
            )
        except Exception as exc:
            self._add_system(f"[retro] unavailable: {exc}")
            return

        if len(parts) >= 3 and parts[1].lower() == "resolve":
            try:
                entry_id = int(parts[2])
            except Exception:
                self._add_system("[retro] Usage: /retro resolve <id>")
                return

            try:
                mark_resolved(entry_id)
                self._add_system(f"[retro] Marked entry #{entry_id} as resolved.")
            except Exception as exc:
                self._add_system(f"[retro] resolve failed: {exc}")
            return

        unresolved = get_unresolved_entries()
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"[CTF Retrospective] {len(unresolved)} unresolved items",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        for entry in unresolved:
            ts = str(entry.get("timestamp", ""))
            date_str = ts[:10] if len(ts) >= 10 else ts
            lines.append(
                f"#{entry.get('id')} [{entry.get('category', 'other')}] {date_str}"
            )
            lines.append(f"   {entry.get('description', '')}")
            suggestion = str(entry.get("suggestion", "") or "").strip()
            if suggestion:
                lines.append(f"   Suggestion: {suggestion}")
            lines.append("")

        if not unresolved:
            lines.append("No unresolved retrospective items.")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self._add_system("\n".join(lines))

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

    def _add_message(self, widget: Static) -> None:
        """Add a message widget to chat"""
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            widget.add_class("message")
            scroll.mount(widget)
            scroll.scroll_end(animate=False)
            self._chat_widgets.append(widget)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to add message to chat: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to add chat message: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about add_message failure: %s", ne
                )

    def _add_system(self, content: str) -> None:
        self._add_message(SystemMessage(content))

    def _add_user(self, content: str) -> None:
        self._add_message(UserMessage(content))

    async def _cancel_running_tasks(self) -> None:
        """Cancel any in-flight worker or crew and reset running state."""
        if self._current_worker:
            self._current_worker.cancel()
            self._current_worker = None
        if self._current_crew:
            try:
                await self._current_crew.cancel()
            except Exception:
                pass
            self._current_crew = None
        self._is_running = False

    async def _truncate_to_user_message(self, user_message: "UserMessage") -> bool:
        """Cancel tasks, then truncate history and UI to before user_message.

        Returns True on success, False if the widget was not found.
        """
        await self._cancel_running_tasks()

        user_message_count = 0
        widget_index = -1
        for i, widget in enumerate(self._chat_widgets):
            if isinstance(widget, UserMessage):
                user_message_count += 1
                if widget is user_message:
                    widget_index = i
                    break

        if widget_index == -1:
            return False

        history_user_count = 0
        history_index = -1
        for i, msg in enumerate(self.agent.conversation_history):
            if msg.role == "user":
                history_user_count += 1
                if history_user_count == user_message_count:
                    history_index = i
                    break

        if history_index == -1:
            return False

        self.agent.conversation_history = self.agent.conversation_history[
            :history_index
        ]
        for widget in reversed(self._chat_widgets[widget_index:]):
            try:
                widget.remove()
            except Exception:
                pass
        self._chat_widgets = self._chat_widgets[:widget_index]
        return True

    @on(UserMessage.RewindPressed)
    def _handle_rewind(self, event: UserMessage.RewindPressed) -> None:
        if not self.agent:
            return

        def on_confirm(confirmed: bool | None) -> None:
            if confirmed:
                self.call_later(self._do_rewind, event.user_message)

        self.push_screen(RewindConfirmScreen(), on_confirm)

    async def _do_rewind(self, user_message: "UserMessage") -> None:
        if await self._truncate_to_user_message(user_message):
            self._add_system(
                f"Conversation rewound to before: {user_message._copy_content[:50]}..."
            )

    @on(UserMessage.ForkPressed)
    def _handle_fork(self, event: UserMessage.ForkPressed) -> None:
        if not self.agent:
            return

        def on_confirm(confirmed: bool | None) -> None:
            if confirmed:
                self.call_later(self._do_fork, event.user_message)

        self.push_screen(ForkConfirmScreen(), on_confirm)

    async def _do_fork(self, user_message: "UserMessage") -> None:
        saved_id: str | None = None
        try:
            from ..workspaces.utils import get_conversations_base
            from .conversation_store import ConversationStore

            if self.agent and self.agent.conversation_history:
                store = ConversationStore(get_conversations_base())
                saved_id = store.save(self.agent.conversation_history)
        except Exception as e:
            self._add_system(f"[!] Fork: could not save conversation: {e}")

        if await self._truncate_to_user_message(user_message):
            save_note = f" (saved as {saved_id[:8]}…)" if saved_id else ""
            self._add_system(
                f"Conversation forked{save_note}. Previous history saved. "
                f"Continuing before: {user_message._copy_content[:50]}…"
            )

    def _add_assistant(self, content: str) -> None:
        self._add_message(AssistantMessage(content))

    def _add_thinking(self, content: str) -> None:
        self._add_message(ThinkingMessage(content))

    def _add_tool(self, name: str, action: str = "") -> ToolMessage:
        tool_message = ToolMessage(name, action)
        self._add_message(tool_message)
        return tool_message

    def _add_tool_result(
        self, tool_message: ToolMessage, name: str, result: str
    ) -> None:
        """Display tool execution result"""
        tool_message.attach_result(ToolResultMessage(name, result))

    def _show_system_prompt(self) -> None:
        """Display the current system prompt"""
        if self.agent:
            prompt = self.agent.get_system_prompt(self._mode)
            self._add_system(f"=== System Prompt ===\n{prompt}")
        else:
            self._add_system("Agent not initialized")

    def _show_memory_stats(self) -> None:
        """Mount a live memory diagnostics widget into the chat area."""
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to query chat-scroll for memory diagnostics: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: memory diagnostics unavailable: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about memory diagnostics availability: %s",
                    ne,
                )
            self._add_system("Agent not initialized")
            return
        # Mount a new diagnostics panel with a unique ID and scroll into view
        try:
            import uuid

            panel_id = f"memory-diagnostics-{uuid.uuid4().hex}"
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to generate memory diagnostics panel id: %s", e
            )
            panel_id = None

        widget = MemoryDiagnostics(id=panel_id)
        scroll.mount(widget)
        try:
            scroll.scroll_end(animate=False)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to scroll to memory diagnostics panel: %s", e
            )
            try:
                from .notifier import notify

                notify(
                    "warning", f"TUI: failed to scroll to memory diagnostics panel: {e}"
                )
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about scroll failure: %s", ne
                )

    def _show_token_stats(self) -> None:
        """Mount a live token diagnostics widget into the chat area."""
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to query chat-scroll for token diagnostics: %s", e
            )
            try:
                from ..interface.notifier import notify

                notify("warning", f"TUI: token diagnostics unavailable: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about token diagnostics availability: %s",
                    ne,
                )
            self._add_system("Agent not initialized")
            return
        # Mount a new diagnostics panel with a unique ID and scroll into view
        try:
            import uuid

            panel_id = f"token-diagnostics-{uuid.uuid4().hex}"
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to generate token diagnostics panel id: %s", e
            )
            try:
                from ..interface.notifier import notify

                notify(
                    "warning",
                    f"TUI: failed to generate token diagnostics panel id: {e}",
                )
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about token diagnostics panel id generation failure: %s",
                    ne,
                )
            panel_id = None

        widget = TokenDiagnostics(id=panel_id)
        scroll.mount(widget)
        try:
            scroll.scroll_end(animate=False)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to scroll to token diagnostics panel: %s", e
            )
            try:
                from ..interface.notifier import notify

                notify(
                    "warning", f"TUI: failed to scroll to token diagnostics panel: {e}"
                )
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about token diagnostics scroll failure: %s",
                    ne,
                )

    async def _show_notes(self) -> None:
        """Display saved notes"""
        from ..tools.notes import get_all_notes
        from ..workspaces.utils import get_loot_file

        notes = await get_all_notes()
        if not notes:
            self._add_system(
                "=== Notes ===\nNo notes saved.\n\nThe AI can save key findings using the notes tool."
            )
            return

        lines = [f"=== Notes ({len(notes)} entries) ==="]
        for key, value in notes.items():
            if isinstance(value, dict):
                category = value.get("category", "info")
                confidence = value.get("confidence", "medium")
                content = str(value.get("content", ""))
                header = f"{key} [{category}/{confidence}]:"

                # Show full value, indent multi-line content
                if "\n" in content:
                    indented = content.replace("\n", "\n    ")
                    lines.append(f"\n{header}\n    {indented}")
                else:
                    lines.append(f"{header} {content}")
            else:
                content = str(value)
                if "\n" in content:
                    indented = content.replace("\n", "\n    ")
                    lines.append(f"\n{key}\n    {indented}")
                else:
                    lines.append(f"{key}: {content}")
            lines.append(f"  -> 输入 /notes delete {key} 删除")
            lines.append(f"  -> 输入 /notes archive {key} 归档")
        notes_path = get_loot_file("notes.json")
        archive_path = notes_path.parent / "notes_archive.json"
        reports_dir = notes_path.parent / "reports"
        lines.append(f"\nFile: {notes_path.as_posix()}")
        lines.append(f"Archive: {archive_path.as_posix()}")
        lines.append(f"Reports: {reports_dir.as_posix()}/")

        self._add_system("\n".join(lines))

    async def _handle_notes_command(self, cmd: str) -> None:
        """Handle /notes and lightweight note maintenance actions."""
        from ..tools.notes import notes as notes_tool

        rest = cmd[len("/notes") :].strip()
        if not rest:
            await self._show_notes()
            return

        parts = rest.split(maxsplit=1)
        action = parts[0].lower()
        if action not in {"delete", "archive"}:
            self._add_system(
                "Usage: /notes\n"
                "       /notes delete <key>\n"
                "       /notes archive <key>"
            )
            return

        key = parts[1].strip() if len(parts) > 1 else ""
        if not key:
            self._add_system(f"Usage: /notes {action} <key>")
            return

        result = await notes_tool({"action": action, "key": key}, runtime=None)
        self._add_system(f"[notes] {result}")
        if not result.startswith("Error:") and "not found" not in result.lower():
            await self._show_notes()

    async def _handle_graph_command(self) -> None:
        from flaghunter.knowledge.graph import ShadowGraph
        from flaghunter.tools.notes import get_all_notes

        notes = await get_all_notes()
        if not notes:
            self._add_system("No notes yet. Run a task first.")
            return

        graph = ShadowGraph()
        graph.update_from_notes(notes)

        if graph.graph.number_of_nodes() == 0:
            self._add_system(
                "Graph empty — notes don't contain host/service/credential data yet."
            )
            return

        mermaid = graph.to_mermaid()
        stats = graph.export_summary()

        self._add_system(
            f"Attack Path Graph ({graph.graph.number_of_nodes()} nodes, "
            f"{graph.graph.number_of_edges()} edges)\n\n"
            f"```mermaid\n{mermaid}\n```\n\n"
            f"Summary:\n{stats}"
        )

        out = Path("reports") / f"graph_{int(time.time())}.mmd"
        out.parent.mkdir(exist_ok=True)
        out.write_text(mermaid, encoding="utf-8")
        self._add_system(f"Saved to {out}")

    def _build_prior_context(self) -> str:
        """Build a summary of prior findings for crew mode.

        Extracts:
        - Tool results (nmap scans, etc.) - the actual findings
        - Assistant analyses - interpretations and summaries
        - Last user task - what they were working on

        Excludes:
        - Raw user messages (noise)
        - Tool call declarations (just names/args, not results)
        - Very short responses
        """
        if not self.agent or not self.agent.conversation_history:
            return ""

        findings = []
        last_user_task = ""

        for msg in self.agent.conversation_history:
            # Track user tasks/questions
            if msg.role == "user" and msg.content:
                last_user_task = msg.content[:200]

            # Extract tool results (the actual findings)
            elif msg.tool_results:
                for result in msg.tool_results:
                    if result.success and result.result:
                        content = (
                            result.result[:1500]
                            if len(result.result) > 1500
                            else result.result
                        )
                        findings.append(f"[{result.tool_name}]\n{content}")

            # Include assistant analyses (but not tool call messages)
            elif msg.role == "assistant" and msg.content and not msg.tool_calls:
                if len(msg.content) > 50:
                    findings.append(f"[Analysis]\n{msg.content[:1000]}")

        if not findings and not last_user_task:
            return ""

        # Build context with last user task + recent findings
        parts = []
        if last_user_task:
            parts.append(f"Last task: {last_user_task}")
        if findings:
            parts.append("Findings:\n" + "\n\n".join(findings[-5:]))

        context = "\n\n".join(parts)
        if len(context) > 4000:
            context = context[:4000] + "\n... (truncated)"

        return context

    async def _save_current_conversation(self) -> None:
        """Persist the current conversation history to the active loot store.

        On first call for a session, creates a new file and stores the id in
        _current_conv_id.  Subsequent calls update the same file so that one
        TUI session maps to exactly one saved conversation.
        """
        if not self.agent or not self.agent.conversation_history:
            return
        if not any(m.role == "user" for m in self.agent.conversation_history):
            return
        try:
            from ..workspaces.utils import get_conversations_base
            from .conversation_store import ConversationStore

            store = ConversationStore(get_conversations_base())
            conv_id = store.save(
                self.agent.conversation_history,
                conv_id=self._current_conv_id,
                handoff=self._build_conversation_handoff_metadata(),
            )
            if conv_id:
                self._current_conv_id = conv_id
                await self._save_session_state()
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to auto-save conversation: %s", e
            )

    async def _restore_conversation(self, conv_id: str) -> None:
        """Load a saved conversation and re-render it in the chat UI."""
        try:
            from ..workspaces.utils import get_conversations_base
            from .conversation_store import ConversationStore

            store = ConversationStore(get_conversations_base())
            messages = store.load(conv_id)
            handoff = store.load_handoff_metadata(conv_id)
            if not messages:
                self._add_system("[!] Could not load conversation (empty or missing).")
                return

            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            await scroll.remove_children()
            self._chat_widgets.clear()

            if self.agent:
                self.agent.conversation_history = messages
            self._current_conv_id = conv_id
            if isinstance(handoff, dict):
                restored_ctf_context = handoff.get("ctf_context")
                if isinstance(restored_ctf_context, dict):
                    self._last_ctf_context = dict(restored_ctf_context)
                    session_context = (
                        dict(self._last_ctf_context.get("sessionContext") or {})
                        if isinstance(self._last_ctf_context.get("sessionContext"), dict)
                        else {}
                    )
                    resume_ingress = (
                        dict(session_context.get("resumeIngress") or {})
                        if isinstance(session_context.get("resumeIngress"), dict)
                        else {}
                    )
                    ingress_run_id = str(handoff.get("last_resume_from_run") or "").strip()
                    ingress_checkpoint_id = str(handoff.get("last_resume_from_checkpoint") or "").strip()
                    if ingress_run_id or ingress_checkpoint_id:
                        resume_ingress["hasResumeContext"] = True
                        if ingress_run_id:
                            resume_ingress["runId"] = ingress_run_id
                        if ingress_checkpoint_id:
                            resume_ingress["checkpointId"] = ingress_checkpoint_id
                        resume_ingress["sourceEvent"] = str(
                            resume_ingress.get("sourceEvent") or "conversation_handoff"
                        ).strip() or "conversation_handoff"
                        session_context["resumeIngress"] = resume_ingress
                        self._last_ctf_context["sessionContext"] = session_context

            # Maps tool_call_id → ToolMessage widget, same pattern as _display_responses
            tool_messages_mapping: dict[str, ToolMessage] = {}

            for msg in messages:
                if msg.role == "user":
                    self._add_user(msg.content or "")
                elif msg.role == "assistant":
                    if msg.content and msg.content.strip():
                        if msg.tool_calls:
                            self._add_thinking(msg.content)
                        else:
                            self._add_assistant(msg.content)
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            tool_messages_mapping[tc.id] = self._add_tool(
                                tc.name, str(tc.arguments)
                            )
                elif msg.role == "tool_result":
                    if msg.tool_results:
                        for tr in msg.tool_results:
                            tm = tool_messages_mapping.get(tr.tool_call_id)
                            if tm is not None:
                                if tr.success:
                                    self._add_tool_result(
                                        tm, tr.tool_name, tr.result or "Done"
                                    )
                                else:
                                    self._add_tool_result(
                                        tm, tr.tool_name, f"Error: {tr.error}"
                                    )
                elif msg.role == "system" and msg.content:
                    self._add_system(msg.content)

            self._add_system(f"Conversation restored ({len(messages)} messages)")
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to restore conversation: %s", e
            )
            self._add_system(f"[!] Restore failed: {e}")

    def _build_conversation_handoff_metadata(self) -> dict[str, Any] | None:
        last_ctx = getattr(self, "_last_ctf_context", None) or {}
        if not isinstance(last_ctx, dict) or not last_ctx:
            return None

        session_context = (
            dict(last_ctx.get("sessionContext") or {})
            if isinstance(last_ctx.get("sessionContext"), dict)
            else {}
        )
        resume_context = (
            dict(session_context.get("resumeContext") or {})
            if isinstance(session_context.get("resumeContext"), dict)
            else {}
        )
        resume_ingress = (
            dict(session_context.get("resumeIngress") or {})
            if isinstance(session_context.get("resumeIngress"), dict)
            else {}
        )
        normalized_ctf_context = {
            "url": str(last_ctx.get("url") or "").strip(),
            "goal": str(last_ctx.get("goal") or "").strip(),
            "type": str(last_ctx.get("type") or "").strip(),
            "hint": str(last_ctx.get("hint") or "").strip(),
            "submit_profile": dict(last_ctx.get("submit_profile") or {}),
            "runner_config": dict(last_ctx.get("runner_config") or {}),
            "execution_mode": str(last_ctx.get("execution_mode") or "").strip(),
            "autonomy_state": (
                dict(last_ctx.get("autonomy_state") or {})
                if isinstance(last_ctx.get("autonomy_state"), dict)
                else None
            ),
            "autonomy_end_reason": str(last_ctx.get("autonomy_end_reason") or "").strip(),
            "sessionContext": session_context or None,
        }
        return {
            "last_run_id": str(resume_context.get("runId") or "").strip(),
            "last_checkpoint": str(resume_context.get("checkpointId") or "").strip(),
            "last_ledger": "",
            "last_resume_summary": str(resume_context.get("summary") or "").strip(),
            "last_resume_from_run": str(resume_ingress.get("runId") or "").strip(),
            "last_resume_from_checkpoint": str(resume_ingress.get("checkpointId") or "").strip(),
            "ctf_context": normalized_ctf_context,
        }

    async def _save_session_state(self) -> None:
        """Persist current conv_id, mode, and target to session.json."""
        if not self._current_conv_id:
            return
        try:
            import json as _json

            from ..workspaces.utils import get_session_file

            session_file = get_session_file()
            session_file.write_text(
                _json.dumps(
                    {
                        "conv_id": self._current_conv_id,
                        "mode": self._mode,
                        "target": self.target,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to save session state: %s", e)

    async def _restore_session(self) -> None:
        """On startup, restore last session from session.json if the preference is enabled."""
        try:
            import json as _json

            from ..workspaces.utils import get_preferences_file, get_session_file

            # Check user preference — default is disabled
            prefs_file = get_preferences_file()
            auto_reload = False
            if prefs_file.exists():
                try:
                    prefs = _json.loads(prefs_file.read_text(encoding="utf-8"))
                    auto_reload = bool(prefs.get("auto_reload_session", False))
                except Exception:
                    pass
            if not auto_reload:
                return

            session_file = get_session_file()
            if not session_file.exists():
                return
            data = _json.loads(session_file.read_text(encoding="utf-8"))
            conv_id = data.get("conv_id")
            mode = data.get("mode", "assist")
            saved_target = data.get("target")

            if conv_id:
                await self._restore_conversation(conv_id)

            if mode in ("assist", "agent", "crew", "interact"):
                self._mode = mode
                self._set_status("idle", mode)

            if saved_target and not self.target:
                self.target = saved_target
                if self.agent:
                    self.agent.target = saved_target
                try:
                    self._update_header(target=saved_target)
                except Exception:
                    pass
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to restore session: %s", e)

    # ── CTF 源码自动探索 ─────────────────────────────────────────────────
    _CTF_SEARCH_ROOTS = [
        r"D:\webstudy\CTF",
        r"C:\CTF",
        r"~/CTF",
        r"~/ctf",
    ]
    # 读取时跳过的目录名
    _CTF_SKIP_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".venv", "vendor", "dist", "build"}
    # 只读取这些扩展名的源文件
    _CTF_SRC_EXTS = {".py", ".js", ".ts", ".php", ".rb", ".go", ".java", ".c", ".cpp",
                     ".html", ".yaml", ".yml", ".json", ".conf", ".env.example",
                     ".dockerfile", "Dockerfile", "docker-compose.yml"}

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

    def _set_target(self, cmd: str) -> None:
        """Set the target for the engagement"""
        # Remove /target prefix
        target = cmd[7:].strip()

        if not target:
            if self.target:
                self._add_system(
                    f"Current target: {self.target}\nUsage: /target <host>"
                )
            else:
                self._add_system(
                    "No target set.\nUsage: /target <host>\nExample: /target 192.168.1.1"
                )
            return

        self.target = target
        workspace_name = None

        # Update agent's target if agent exists
        if self.agent:
            self.agent.target = target
            try:
                from flaghunter.agents.base_agent import AgentMessage

                # Inform the agent (LLM) that the operator changed the target so
                # subsequent generations use the new value instead of older
                # workspace-bound targets from conversation history.
                self.agent.conversation_history.append(
                    AgentMessage(
                        role="system", content=f"Operator set target to {target}"
                    )
                )
                # Track manual target override so workspace restores can remove
                # or supersede this message when appropriate.
                try:
                    self.agent._manual_target = target
                except Exception:
                    pass
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to append target change to agent history: %s", e
                )

        # Activate the workspace derived from the new target
        try:
            from .initializer import activate_workspace_for_target

            workspace_name = activate_workspace_for_target(target)
            self._add_system(f"Workspace activated: {workspace_name}")
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to activate workspace for target %s: %s", target, e
            )
            try:
                from flaghunter.interface.notifier import notify

                notify("warning", f"TUI: failed to activate workspace for target: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about workspace activation failure: %s",
                    ne,
                )

        # Update displayed Target in the UI
        try:
            self._apply_target_display(target)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to apply target display: %s", e
            )
            try:
                from flaghunter.interface.notifier import notify

                notify("warning", f"Failed to update target display: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about target display error: %s", ne
                )
        # Update the initial ready SystemMessage (if present) so Target appears under Runtime
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            updated = False
            for child in scroll.children:
                if isinstance(child, SystemMessage) and "PentestAgent ready" in getattr(
                    child, "message_content", ""
                ):
                    # Replace existing Target line if present, otherwise append
                    try:
                        if "Target:" in child.message_content:
                            # replace the first Target line
                            child.message_content = re.sub(
                                r"(?m)^\s*Target:.*$",
                                f"  Target: {target}",
                                child.message_content,
                                count=1,
                            )
                        else:
                            child.message_content = (
                                child.message_content + f"\n  Target: {target}"
                            )
                        try:
                            child.refresh()
                        except Exception as e:
                            logging.getLogger(__name__).exception(
                                "Failed to refresh child message after target update: %s",
                                e,
                            )
                            try:
                                from flaghunter.interface.notifier import notify

                                notify(
                                    "warning",
                                    f"Failed to refresh UI after target update: {e}",
                                )
                            except Exception as ne:
                                logging.getLogger(__name__).exception(
                                    "Failed to notify operator about UI refresh error: %s",
                                    ne,
                                )
                    except Exception as e:
                        # Fallback to append if regex replacement fails, and surface warning
                        logging.getLogger(__name__).exception(
                            "Failed to update SystemMessage target line: %s", e
                        )
                        try:
                            from flaghunter.interface.notifier import notify

                            notify("warning", f"Failed to update target display: {e}")
                        except Exception as ne:
                            logging.getLogger(__name__).exception(
                                "Failed to notify operator about target update error: %s",
                                ne,
                            )
                        child.message_content = (
                            child.message_content + f"\n  Target: {target}"
                        )
                    updated = True
                    break
            if not updated:
                # If we couldn't find an existing banner SystemMessage to
                # update, update the persistent header instead of inserting
                # additional in-chat system messages to avoid duplicates.
                try:
                    self._update_header(target=target)
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Failed to update persistent header with target"
                    )
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed while applying target display: %s", e
            )
            try:
                from flaghunter.interface.notifier import notify

                notify("warning", f"TUI: failed while updating target display: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about target display outer failure: %s",
                    ne,
                )
            # Last resort: append a subtle system line
            self._add_system(f"  Target: {target}")

    @work(exclusive=True)
    async def _run_report_generation(self) -> None:
        """Generate a pentest report from notes and conversation"""

        from ..tools.notes import get_all_notes

        if not self.agent or not self.agent.llm:
            self._add_system("[!] Agent not initialized")
            return

        notes = await get_all_notes()
        if not notes:
            self._add_system(
                "No notes found. PentestAgent saves findings using the notes tool during testing."
            )
            return

        self._add_system("Generating report...")

        # Format notes - extract structured content from note dicts
        notes_lines = []
        for k, v in notes.items():
            if isinstance(v, dict):
                content = v.get("content", "")
                category = v.get("category", "info")
                confidence = v.get("confidence", "medium")
                status = v.get("status", "confirmed")
                meta = v.get("metadata", {})
                target = meta.get("target", "N/A")
                header = f"### {k} [{category}] (confidence: {confidence}, status: {status}, target: {target})"
                notes_lines.append(f"{header}\n{content}")
                if meta.get("services"):
                    notes_lines.append(f"Services: {json.dumps(meta['services'])}")
                if meta.get("technologies"):
                    notes_lines.append(
                        f"Technologies: {json.dumps(meta['technologies'])}"
                    )
                if meta.get("endpoints"):
                    notes_lines.append(f"Endpoints: {json.dumps(meta['endpoints'])}")
                if meta.get("weaknesses"):
                    notes_lines.append(f"Weaknesses: {json.dumps(meta['weaknesses'])}")
                if meta.get("cve"):
                    notes_lines.append(f"CVE: {meta['cve']}")
                if meta.get("username"):
                    notes_lines.append(f"Username: {meta['username']}")
                notes_lines.append("")
            else:
                notes_lines.append(f"### {k}\n{v}\n")
        notes_text = "\n".join(notes_lines)

        # Build conversation summary from full history
        conversation_summary = ""
        if self.agent.conversation_history:
            # Summarize key actions from conversation
            actions = []
            for msg in self.agent.conversation_history:
                if msg.role == "assistant" and msg.tool_calls:
                    for tc in msg.tool_calls:
                        actions.append(f"- Tool: {tc.name}")
                elif msg.role == "tool_result" and msg.tool_results:
                    for tr in msg.tool_results:
                        # Include more of the result for report context
                        result = tr.result or ""
                        output = result[:1000] + "..." if len(result) > 1000 else result
                        status = "OK" if tr.success else "FAIL"
                        actions.append(f"  [{status}] {tr.tool_name}: {output}")
            if actions:
                conversation_summary = "\n".join(actions[-30:])  # Last 30 actions

        report_prompt = f"""Generate a penetration test report in Markdown from the notes below.

# Notes
{notes_text}

# Activity Log
{conversation_summary if conversation_summary else "N/A"}

# Target
{self.target or "Not specified"}

Output a report with:
1. Executive Summary (2-3 sentences)
2. Findings (use notes, include severity: Critical/High/Medium/Low/Info)
3. Recommendations

Be concise. Use the actual data from notes."""

        try:
            # Use generate() directly with higher max_tokens for reports (16k vs default 8k)
            report_response = await self.agent.llm.generate(
                system_prompt="You are a penetration tester writing a security report. Be concise and factual. Include ALL findings from the notes.",
                messages=[{"role": "user", "content": report_prompt}],
                tools=None,
                max_tokens=16384,
            )
            report_content = report_response.content or ""

            if not report_content or not report_content.strip():
                self._add_system(
                    "[!] Report generation returned empty. Check LLM connection."
                )
                return

            # Save to loot/reports/
            reports_dir = Path("loot/reports")
            reports_dir.mkdir(parents=True, exist_ok=True)

            # Append Shadow Graph if available
            try:
                from ..knowledge.graph import ShadowGraph
                from ..tools.notes import get_all_notes_sync

                # Rehydrate graph from notes
                graph = ShadowGraph()
                notes = get_all_notes_sync()
                if notes:
                    graph.update_from_notes(notes)
                    mermaid_code = graph.to_mermaid()

                    if mermaid_code:
                        report_content += (
                            "\n\n## Attack Graph (Visual)\n\n```mermaid\n"
                            + mermaid_code
                            + "\n```\n"
                        )
            except Exception as e:
                self._add_system(f"[!] Graph generation error: {e}")

            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            report_path = reports_dir / f"report_{timestamp}.md"
            report_path.write_text(report_content, encoding="utf-8")

            self._add_system(f"+ Report saved: {report_path}")

        except Exception as e:
            self._add_system(f"[!] Report error: {e}")

    @on(TextArea.Changed, "#chat-input")
    def handle_input_changed(self, event: TextArea.Changed) -> None:
        """Show/filter command suggestions when typing a slash command."""
        try:
            suggestions = self.query_one("#cmd-suggestions", CommandSuggestions)
            hint = self.query_one("#tab-hint", Static)
            inp = self._get_chat_input()
        except Exception:
            return
        val = event.text_area.text
        if self._should_offer_command_suggestions(val):
            suggestions.update_suggestions(val)
            show = bool(suggestions.display)
            hint.display = show
            inp.styles.width = "1fr"
        else:
            suggestions.hide()
            hint.display = False
            inp.styles.width = "1fr"

    @on(ChatInputTextArea.Submitted, "#chat-input")
    async def handle_submit(self, event: ChatInputTextArea.Submitted) -> None:
        """Handle input submission"""
        # Hide suggestions on submit
        try:
            self.query_one("#cmd-suggestions", CommandSuggestions).hide()
            self.query_one("#tab-hint", Static).display = False
            self._get_chat_input().styles.width = "1fr"
        except Exception:
            pass

        # MCP observation mode: the input is disabled at the widget level, but
        # guard here as well to be safe.
        if self.mcp_mode:
            self._clear_chat_input()
            return

        # Block input while initializing or AI is processing
        if self._is_initializing or self._is_running:
            return

        # Strip ANSI escape sequences and control codes
        message = _ANSI_ESCAPE.sub("", event.text).strip()
        if not message:
            return

        # Save to history (de-duplicate consecutive duplicates)
        if not (self._cmd_history and self._cmd_history[-1] == message):
            self._cmd_history.append(message)
        # Reset index to one past the end (blank)
        self._history_index = len(self._cmd_history)

        self._clear_chat_input()

        # Commands
        if message.startswith("/"):
            await self._handle_command(message)
            return

        self._add_user(message)

        if self.agent and not self._is_running:
            if self._mode == "assist":
                # Schedule assist run and keep task handle (do not wrap in asyncio.create_task; @work returns a Worker)
                self._hide_sidebar()
                self._current_worker = self._run_assist(message)
            elif self._mode == "interact":
                self._hide_sidebar()
                self._current_worker = self._run_interact(message)
            elif self._mode == "agent":
                self._hide_sidebar()
                self._current_worker = self._run_agent_mode(message)
            elif self._mode == "crew":
                self._current_worker = self._run_crew_mode(message)

    async def _handle_command(self, cmd: str) -> None:
        """Handle slash commands"""
        cmd_lower = cmd.lower().strip()
        cmd_original = cmd.strip()

        if cmd_lower in ["/help", "/h", "/?"]:
            await self.push_screen(HelpScreen())
        elif cmd_lower == "/clear":
            await self._save_current_conversation()
            self._current_conv_id = None
            # Remove autosave session pointer so next startup starts fresh
            try:
                from ..workspaces.utils import get_session_file

                sf = get_session_file()
                if sf.exists():
                    sf.unlink()
            except Exception:
                pass
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            await scroll.remove_children()
            self._chat_widgets.clear()
            self._hide_sidebar()
            # Clear agent conversation history for fresh start
            if self.agent:
                self.agent.conversation_history.clear()
            self._add_system("Chat cleared")
        elif cmd_lower == "/tools":
            # Open the interactive tools browser (split-pane).
            try:
                if self.agent:
                    await self.push_screen(
                        ToolsScreen(tools=self.agent.get_tools(), tui=self)
                    )
            except Exception:
                # Fallback: list tools in the system area if UI push fails
                from ..runtime.runtime import detect_environment

                names = [t.name for t in self.all_tools]
                msg = f"Tools ({len(names)}): " + ", ".join(names)

                # Add detected CLI tools
                env = detect_environment()
                if env.available_tools:
                    # Group by category
                    by_category = {}
                    for tool_info in env.available_tools:
                        if tool_info.category not in by_category:
                            by_category[tool_info.category] = []
                        by_category[tool_info.category].append(tool_info.name)

                    cli_sections = []
                    for category in sorted(by_category.keys()):
                        tools_list = ", ".join(sorted(by_category[category]))
                        cli_sections.append(f"{category}: {tools_list}")

                    msg += f"\n\nCLI Tools ({len(env.available_tools)}):\n" + "\n".join(
                        cli_sections
                    )

                self._add_system(msg)
        elif cmd_lower.startswith("/mcp"):
            await self._parse_mcp_command(cmd_original)
        # === CPA M1 HOOK BEGIN ===
        elif cmd_lower.startswith("/api") or cmd_lower.startswith("/providers"):
            await self._parse_api_command(cmd_original)
        # === CPA M1 HOOK END ===
        # === CPA M2 HOOK BEGIN ===
        elif cmd_lower.startswith("/ctf"):
            await self._parse_ctf_command(cmd_original)
        # === CPA M2 HOOK END ===
        # === CPA M3 HOOK BEGIN ===
        elif cmd_lower.startswith("/report"):
            await self._parse_report_command(cmd_original)
        # === CPA M3 HOOK END ===
        # === CPA M4 HOOK BEGIN ===
        elif cmd_lower.startswith("/audit"):
            await self._parse_audit_command(cmd_original)
        # === CPA M4 HOOK END ===
        # === CPA M5 HOOK BEGIN ===
        elif cmd_lower.startswith("/swarm"):
            await self._parse_swarm_command(cmd_original)
        # === CPA M5 HOOK END ===
        # === CPA M6 HOOK BEGIN ===
        elif cmd_lower.startswith("/turbo"):
            await self._parse_turbo_command(cmd_original)
        # === CPA M6 HOOK END ===
        elif cmd_lower == "/retry":
            await self._handle_retry_command()
        elif cmd_lower == "/copy" or cmd_lower.startswith("/copy "):
            await self._handle_copy_command(cmd_original)
        elif cmd_lower == "/retro" or cmd_lower.startswith("/retro "):
            await self._handle_retro_command(cmd_original)
        elif cmd_lower in ["/quit", "/exit", "/q"]:
            self.exit()
        elif cmd_lower == "/prompt":
            self._show_system_prompt()
        elif cmd_lower == "/memory":
            self._show_memory_stats()
        elif cmd_lower == "/token":
            self._show_token_stats()
        elif cmd_lower == "/notes" or cmd_lower.startswith("/notes "):
            await self._handle_notes_command(cmd_original)
        elif cmd_lower == "/graph":
            await self._handle_graph_command()
        elif cmd_lower == "/report":
            # Call the textual worker - decorator returns a Worker
            _ = cast(Any, self._run_report_generation())
        elif cmd_original.startswith("/target"):
            self._set_target(cmd_original)
        elif cmd_original.startswith("/workspace"):
            # Support lightweight workspace management from the TUI
            try:

                from flaghunter.workspaces.manager import (
                    WorkspaceError,
                    WorkspaceManager,
                )
                from flaghunter.workspaces.utils import resolve_knowledge_paths

                wm = WorkspaceManager()
                rest = cmd_original[len("/workspace") :].strip()

                if not rest:
                    active = wm.get_active()
                    if not active:
                        self._add_system("No active workspace.")
                    else:
                        # restore last target if present
                        last = wm.get_meta_field(active, "last_target")
                        if last:
                            self.target = last
                            if self.agent:
                                self.agent.target = last
                                # If the operator set a manual target while no
                                # workspace was active, remove/supersede that
                                # system message so the LLM uses the workspace
                                # target instead of the stale manual one.
                                try:
                                    manual = getattr(self.agent, "_manual_target", None)
                                    if manual:
                                        self.agent.conversation_history = [
                                            m
                                            for m in self.agent.conversation_history
                                            if not (
                                                m.role == "system"
                                                and isinstance(m.content, str)
                                                and m.content.strip().startswith(
                                                    "Operator set target to"
                                                )
                                            )
                                        ]
                                        try:
                                            delattr(self.agent, "_manual_target")
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                try:
                                    from flaghunter.agents.base_agent import (
                                        AgentMessage,
                                    )

                                    self.agent.conversation_history.append(
                                        AgentMessage(
                                            role="system",
                                            content=f"Workspace active; restored last target: {last}",
                                        )
                                    )
                                except Exception:
                                    pass
                            try:
                                self._apply_target_display(last)
                            except Exception as e:
                                logging.getLogger(__name__).exception(
                                    "Failed to apply target display when restoring last target: %s",
                                    e,
                                )
                                try:
                                    from flaghunter.interface.notifier import notify

                                    notify(
                                        "warning",
                                        f"TUI: failed restoring last target display: {e}",
                                    )
                                except Exception:
                                    logging.getLogger(__name__).exception(
                                        "Failed to notify operator about restore-last-target failure"
                                    )
                        self._add_system(f"Active workspace: {active}")
                    return

                parts = rest.split()
                verb = parts[0].lower()

                if verb == "help":
                    try:
                        await self.push_screen(WorkspaceHelpScreen())
                    except Exception:
                        # Fallback: show inline help text
                        self._add_system(
                            "Usage: /workspace <action>\nCommands: list, info, note, clear, help, <name>"
                        )
                    return

                if verb == "list":
                    wss = wm.list_workspaces()
                    if not wss:
                        self._add_system("No workspaces found.")
                        return
                    out = []
                    active = wm.get_active()
                    for name in sorted(wss):
                        prefix = "* " if name == active else "  "
                        out.append(f"{prefix}{name}")
                    self._add_system("\n".join(out))
                    return

                if verb == "info":
                    name = parts[1] if len(parts) > 1 else wm.get_active()
                    if not name:
                        self._add_system(
                            "No workspace specified and no active workspace."
                        )
                        return
                    try:
                        meta = wm.get_meta(name)
                        created = meta.get("created_at")
                        last_active = meta.get("last_active_at")
                        targets = meta.get("targets", [])
                        kp = resolve_knowledge_paths()
                        ks = "workspace" if kp.get("using_workspace") else "global"
                        self._add_system(
                            f"Name: {name}\nCreated: {created}\nLast active: {last_active}\nTargets: {len(targets)}\nKnowledge scope: {ks}"
                        )
                    except Exception as e:
                        self._add_system(f"Error retrieving workspace info: {e}")
                    return

                if verb == "note":
                    # By default, use the active workspace; allow explicit override via --workspace/-w.
                    name = wm.get_active()
                    i = 1
                    # Parse optional workspace selector flags before the note text.
                    while i < len(parts):
                        part = parts[i]
                        if part in ("--workspace", "-w"):
                            if i + 1 >= len(parts):
                                self._add_system(
                                    "Usage: /workspace note [--workspace NAME] <text>"
                                )
                                return
                            name = parts[i + 1]
                            i += 2
                            continue
                        # First non-option token marks the start of the note text
                        break
                    if not name:
                        self._add_system(
                            "No active workspace. Set one with /workspace <name>."
                        )
                        return
                    text = " ".join(parts[i:])
                    if not text:
                        self._add_system(
                            "Usage: /workspace note [--workspace NAME] <text>"
                        )
                        return
                    try:
                        wm.set_operator_note(name, text)
                        self._add_system(f"Operator note saved for workspace '{name}'.")
                    except Exception as e:
                        self._add_system(f"Error saving note: {e}")
                    return

                if verb == "clear":
                    active = wm.get_active()
                    if not active:
                        self._add_system("No active workspace.")
                        return
                    marker = wm.active_marker()
                    try:
                        if marker.exists():
                            marker.unlink()
                        # Clear TUI and agent target when workspace is deactivated
                        self.target = ""
                        try:
                            self._apply_target_display("")
                        except Exception:
                            pass
                        if self.agent:
                            try:
                                # Clear agent's target and any manual override
                                self.agent.target = ""
                                try:
                                    if hasattr(self.agent, "_manual_target"):
                                        delattr(self.agent, "_manual_target")
                                except Exception:
                                    pass
                                from flaghunter.agents.base_agent import AgentMessage

                                self.agent.conversation_history.append(
                                    AgentMessage(
                                        role="system",
                                        content=(
                                            f"Workspace '{active}' deactivated; cleared target"
                                        ),
                                    )
                                )
                            except Exception:
                                logging.getLogger(__name__).exception(
                                    "Failed to clear agent target on workspace clear"
                                )
                        self._add_system(f"Workspace '{active}' deactivated.")
                    except Exception as e:
                        self._add_system(f"Error deactivating workspace: {e}")
                    return

                # Default: treat rest as workspace name -> create (only if missing) and set active
                name = rest
                try:
                    existed = wm.workspace_path(name).exists()
                    if not existed:
                        wm.create(name)
                    wm.set_active(name)
                    # restore last target if set on workspace
                    last = wm.get_meta_field(name, "last_target")
                    if last:
                        self.target = last
                        if self.agent:
                            self.agent.target = last
                        try:
                            self._apply_target_display(last)
                        except Exception as e:
                            logging.getLogger(__name__).exception(
                                "Failed to apply target display when activating workspace: %s",
                                e,
                            )
                            try:
                                from flaghunter.interface.notifier import notify

                                notify(
                                    "warning",
                                    f"TUI: failed to restore workspace target display: {e}",
                                )
                            except Exception:
                                logging.getLogger(__name__).exception(
                                    "Failed to notify operator about workspace target restore failure"
                                )

                    if existed:
                        self._add_system(f"Workspace '{name}' set active.")
                    else:
                        self._add_system(f"Workspace '{name}' created and set active.")
                except WorkspaceError as e:
                    self._add_system(f"Error: {e}")
                except Exception as e:
                    self._add_system(f"Error creating workspace: {e}")
            except Exception as e:
                self._add_system(f"Workspace command error: {e}")
            return
        elif cmd_original.startswith("/spawn"):
            await self._parse_spawn_command(cmd_original)
        elif cmd_original.startswith("/despawn"):
            await self._parse_despawn_command(cmd_original)
        elif cmd_original.startswith("/agent"):
            await self._parse_agent_command(cmd_original)
        elif cmd_original.startswith("/crew"):
            await self._parse_crew_command(cmd_original)
        elif cmd_original.startswith("/interact"):
            await self._parse_interact_command(cmd_original)
        elif cmd_original.startswith("/assist"):
            await self._parse_assist_command(cmd_original)
        # === TOOL CMD BEGIN: /nmap ===
        elif cmd_original.startswith("/nmap"):
            await self._parse_nmap_command(cmd_original)
        # === TOOL CMD END: /nmap ===
        # === TOOL CMD BEGIN: /dirscan ===
        elif cmd_original.startswith("/dirscan"):
            await self._parse_dirscan_command(cmd_original)
        # === TOOL CMD END: /dirscan ===
        # === TOOL CMD BEGIN: /nuclei ===
        elif cmd_original.startswith("/nuclei"):
            await self._parse_nuclei_command(cmd_original)
        # === TOOL CMD END: /nuclei ===
        # === TOOL CMD BEGIN: /sqlmap ===
        elif cmd_original.startswith("/sqlmap"):
            await self._parse_sqlmap_command(cmd_original)
        # === TOOL CMD END: /sqlmap ===
        elif cmd_lower == "/conversations":
            try:
                from ..workspaces.utils import get_conversations_base
                from .conversation_store import ConversationStore

                store = ConversationStore(get_conversations_base())
                convs = store.list_conversations()

                def on_conv_selected(meta) -> None:
                    if meta is not None:
                        self.call_later(self._restore_conversation, meta.id)

                await self.push_screen(
                    ConversationsScreen(convs, store), on_conv_selected
                )
            except Exception as e:
                self._add_system(f"[!] Conversations error: {e}")
        else:
            self._add_system(f"Unknown command: {cmd}\nType /help for commands.")

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

    def _format_nmap_result(self, result: dict[str, Any], target: str, ports: str) -> str:
        """Format structured nmap output for TUI display."""
        lines = [f"[nmap] Target: {result.get('target') or target}"]

        status = result.get("status")
        if status:
            lines.append(f"Status: {status}")

        port_items = result.get("ports")
        if isinstance(port_items, list) and port_items:
            lines.append("Ports:")
            for item in port_items:
                if not isinstance(item, dict):
                    continue
                port_value = item.get("port", "?")
                state = item.get("state", "unknown")
                service = item.get("service") or "unknown"
                protocol = item.get("protocol") or ""
                version = item.get("version") or ""
                line = f"- {port_value}"
                if protocol:
                    line += f"/{protocol}"
                line += f" {state} {service}"
                if version:
                    line += f" ({version})"
                lines.append(line)
        else:
            lines.append(f"Ports: no results for range {ports}")

        os_guess = result.get("os_guess")
        if os_guess:
            lines.append(f"OS Guess: {os_guess}")

        error = result.get("error")
        if error:
            lines.append(f"Error: {error}")
        elif result.get("raw") and not (isinstance(port_items, list) and port_items):
            lines.append("Note: scan completed but no structured port rows were parsed.")

        return "\n".join(lines)

    def _format_dirscan_result(
        self, result: dict[str, Any], url: str, wordlist: str
    ) -> str:
        """Format structured dirscan output for TUI display."""
        lines = [f"[dirscan] URL: {result.get('url') or url}"]
        tool_used = result.get("tool_used")
        if tool_used:
            lines.append(f"Tool: {tool_used}")
        lines.append(f"Wordlist: {wordlist}")

        found_items = result.get("found")
        if isinstance(found_items, list) and found_items:
            lines.append("Found paths:")
            for item in found_items:
                if not isinstance(item, dict):
                    continue
                status = item.get("status", "?")
                path = item.get("path") or "/"
                size = item.get("size")
                line = f"- {status} {path}"
                if size not in (None, "", 0):
                    line += f" [size={size}]"
                lines.append(line)
        else:
            lines.append("Found paths: none")

        error = result.get("error")
        if error:
            lines.append(f"Error: {error}")

        return "\n".join(lines)

    def _format_nuclei_result(
        self, result: dict[str, Any], target: str, severity: list[str]
    ) -> str:
        """Format structured nuclei output for TUI display."""
        lines = [f"[nuclei] Target: {result.get('target') or target}"]
        lines.append(f"Severity filter: {','.join(severity)}")

        findings = result.get("findings")
        if isinstance(findings, list) and findings:
            lines.append(f"Findings ({len(findings)}):")
            for item in findings:
                if not isinstance(item, dict):
                    continue
                template_id = item.get("template_id") or "unknown-template"
                sev = item.get("severity") or "unknown"
                name = item.get("name") or ""
                line = f"- {template_id} {sev}"
                if name:
                    line += f" - {name}"
                lines.append(line)
        else:
            lines.append("Findings: none")

        error = result.get("error")
        if error:
            lines.append(f"Error: {error}")

        return "\n".join(lines)

    def _format_sqlmap_result(self, result: dict[str, Any], url: str) -> str:
        """Format structured sqlmap output for TUI display."""
        vulnerable = bool(result.get("vulnerable"))
        lines = [f"[sqlmap] URL: {url}", f"Vulnerable: {'yes' if vulnerable else 'no'}"]

        injection_points = result.get("injection_points")
        if isinstance(injection_points, list) and injection_points:
            lines.append("Injection points:")
            for item in injection_points:
                if not isinstance(item, dict):
                    continue
                parameter = item.get("parameter") or "unknown"
                injection_type = item.get("type") or "unknown"
                dbms = item.get("dbms") or ""
                payload = item.get("payload") or ""
                line = f"- {parameter}: {injection_type}"
                if dbms:
                    line += f" [{dbms}]"
                if payload:
                    line += f" | payload={payload}"
                lines.append(line)
        else:
            lines.append("Injection points: none")

        databases = result.get("databases")
        if isinstance(databases, list) and databases:
            lines.append("Databases: " + ", ".join(str(db) for db in databases))

        error = result.get("error")
        if error:
            lines.append(f"Error: {error}")

        return "\n".join(lines)

    # === TOOL CMD BEGIN: /nmap ===
    async def _parse_nmap_command(self, cmd: str) -> None:
        """Parse and execute /nmap command."""
        import shlex

        try:
            parts = shlex.split(cmd)
        except ValueError as exc:
            self._add_system(f"[nmap] Parse error: {exc}")
            return

        if len(parts) < 2:
            self._add_system(
                "Usage: /nmap <target> [ports]\n"
                "Example: /nmap 127.0.0.1\n"
                "         /nmap 127.0.0.1 22,80,443"
            )
            return

        target = parts[1].strip()
        ports = parts[2].strip() if len(parts) > 2 else "1-1000"

        if not target:
            self._add_system("Usage: /nmap <target> [ports]")
            return

        try:
            from ..tools.nmap import run_nmap
        except Exception as exc:
            self._add_system(f"[nmap] Tool unavailable: {exc}")
            return

        try:
            result = await run_nmap(target, ports, runtime=self._runtime)
        except Exception as exc:
            self._add_system(f"[nmap] Scan failed: {exc}")
            return

        if not isinstance(result, dict):
            self._add_system("[nmap] Unexpected tool result format.")
            return

        self._add_system(self._format_nmap_result(result, target, ports))

    # === TOOL CMD END: /nmap ===

    # === TOOL CMD BEGIN: /dirscan ===
    async def _parse_dirscan_command(self, cmd: str) -> None:
        """Parse and execute /dirscan command."""
        import shlex

        try:
            parts = shlex.split(cmd)
        except ValueError as exc:
            self._add_system(f"[dirscan] Parse error: {exc}")
            return

        if len(parts) < 2:
            self._add_system(
                "Usage: /dirscan <url> [wordlist]\n"
                "Example: /dirscan http://127.0.0.1\n"
                "         /dirscan http://127.0.0.1 /usr/share/wordlists/dirb/common.txt"
            )
            return

        url = parts[1].strip()
        wordlist = (
            parts[2].strip()
            if len(parts) > 2
            else "/usr/share/wordlists/dirb/common.txt"
        )

        if not url:
            self._add_system("Usage: /dirscan <url> [wordlist]")
            return

        try:
            from ..tools.dirscan import run_dirscan
        except Exception as exc:
            self._add_system(f"[dirscan] Tool unavailable: {exc}")
            return

        try:
            result = await run_dirscan(url, wordlist, runtime=self._runtime)
        except Exception as exc:
            self._add_system(f"[dirscan] Scan failed: {exc}")
            return

        if not isinstance(result, dict):
            self._add_system("[dirscan] Unexpected tool result format.")
            return

        self._add_system(self._format_dirscan_result(result, url, wordlist))

    # === TOOL CMD END: /dirscan ===

    # === TOOL CMD BEGIN: /nuclei ===
    async def _parse_nuclei_command(self, cmd: str) -> None:
        """Parse and execute /nuclei command."""
        import shlex

        try:
            parts = shlex.split(cmd)
        except ValueError as exc:
            self._add_system(f"[nuclei] Parse error: {exc}")
            return

        if len(parts) < 2:
            self._add_system(
                "Usage: /nuclei <target> [severity]\n"
                "Example: /nuclei http://127.0.0.1\n"
                "         /nuclei http://127.0.0.1 critical,high,medium"
            )
            return

        target = parts[1].strip()
        severity_arg = parts[2].strip() if len(parts) > 2 else "critical,high,medium"
        severity = [item.strip() for item in severity_arg.split(",") if item.strip()]
        if not severity:
            severity = ["critical", "high", "medium"]

        if not target:
            self._add_system("Usage: /nuclei <target> [severity]")
            return

        try:
            from ..tools.nuclei import run_nuclei
        except Exception as exc:
            self._add_system(f"[nuclei] Tool unavailable: {exc}")
            return

        try:
            result = await run_nuclei(target, severity=severity, runtime=self._runtime)
        except Exception as exc:
            self._add_system(f"[nuclei] Scan failed: {exc}")
            return

        if not isinstance(result, dict):
            self._add_system("[nuclei] Unexpected tool result format.")
            return

        self._add_system(self._format_nuclei_result(result, target, severity))

    # === TOOL CMD END: /nuclei ===

    # === TOOL CMD BEGIN: /sqlmap ===
    async def _parse_sqlmap_command(self, cmd: str) -> None:
        """Parse and execute /sqlmap command."""
        import shlex

        try:
            parts = shlex.split(cmd)
        except ValueError as exc:
            self._add_system(f"[sqlmap] Parse error: {exc}")
            return

        if len(parts) < 2:
            self._add_system(
                "Usage: /sqlmap <url> [--data <post_data>]\n"
                "Example: /sqlmap http://127.0.0.1/item.php?id=1\n"
                "         /sqlmap http://127.0.0.1/login --data \"user=admin&pass=test\""
            )
            return

        url = parts[1].strip()
        data = ""
        idx = 2
        while idx < len(parts):
            token = parts[idx]
            if token == "--data":
                if idx + 1 >= len(parts):
                    self._add_system("Usage: /sqlmap <url> [--data <post_data>]")
                    return
                data = parts[idx + 1]
                idx += 2
                continue

            self._add_system(f"[sqlmap] Unknown option: {token}")
            return

        if not url:
            self._add_system("Usage: /sqlmap <url> [--data <post_data>]")
            return

        try:
            from ..tools.sqlmap import run_sqlmap
        except Exception as exc:
            self._add_system(f"[sqlmap] Tool unavailable: {exc}")
            return

        try:
            result = await run_sqlmap(url, data=data, runtime=self._runtime)
        except Exception as exc:
            self._add_system(f"[sqlmap] Scan failed: {exc}")
            return

        if not isinstance(result, dict):
            self._add_system("[sqlmap] Unexpected tool result format.")
            return

        self._add_system(self._format_sqlmap_result(result, url))

    # === TOOL CMD END: /sqlmap ===

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
    # === CPA M1 HOOK END ===

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

    def _show_sidebar(self) -> None:
        """Show the sidebar for crew mode."""
        try:
            import time

            sidebar = self.query_one("#sidebar")
            sidebar.add_class("visible")

            chat_area = self.query_one("#chat-area")
            chat_area.add_class("with-sidebar")

            # Setup tree
            tree = self.query_one("#workers-tree", CrewTree)
            tree.root.expand()
            tree.show_root = False

            # Clear old nodes
            tree.root.remove_children()
            self._crew_worker_nodes.clear()
            self._crew_workers.clear()
            self._worker_events.clear()
            self._crew_findings_count = 0

            # Start tracking time and tokens
            self._crew_start_time = time.time()
            self._crew_tokens_used = 0

            # Start stats timer (update every second)
            if self._crew_stats_timer:
                self._crew_stats_timer.stop()
            self._crew_stats_timer = self.set_interval(1.0, self._update_crew_stats)

            # Start spinner timer for running workers (faster interval for smooth animation)
            if self._spinner_timer:
                self._spinner_timer.stop()
            self._spinner_timer = self.set_interval(0.15, self._update_spinner)

            # Add crew root node (no orchestrator - just "CREW" header)
            self._crew_orchestrator_node = tree.root.add(
                "CREW", data={"type": "crew", "id": "crew"}
            )
            if self._crew_orchestrator_node:
                try:
                    self._crew_orchestrator_node.expand()
                    tree.select_node(self._crew_orchestrator_node)
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to expand/select crew orchestrator node: %s", e
                    )
                    try:
                        from .notifier import notify

                        notify(
                            "warning", f"TUI: failed to expand crew sidebar node: {e}"
                        )
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about crew node expansion failure"
                        )
            self._viewing_worker_id = None

            # Update stats
            self._update_crew_stats()
        except Exception as e:
            self._add_system(f"[!] Sidebar error: {e}")

    def _apply_target_display(self, target: str) -> None:
        """Update or insert the Target line in the system/banner area."""
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            updated = False
            for child in scroll.children:
                if isinstance(child, SystemMessage) and "PentestAgent ready" in getattr(
                    child, "message_content", ""
                ):
                    # Replace existing Target line if present, otherwise append
                    try:
                        if "Target:" in child.message_content:
                            child.message_content = re.sub(
                                r"(?m)^\s*Target:.*$",
                                f"  Target: {target}",
                                child.message_content,
                                count=1,
                            )
                        else:
                            child.message_content = (
                                child.message_content + f"\n  Target: {target}"
                            )
                        try:
                            child.refresh()
                        except Exception as e:
                            logging.getLogger(__name__).exception(
                                "Failed to refresh child message: %s", e
                            )
                            try:
                                from flaghunter.interface.notifier import notify

                                notify(
                                    "warning", f"TUI: failed to refresh UI element: {e}"
                                )
                            except Exception:
                                logging.getLogger(__name__).exception(
                                    "Failed to notify operator about child refresh failure"
                                )
                    except Exception as e:
                        logging.getLogger(__name__).exception(
                            "Failed to update SystemMessage target line: %s", e
                        )
                        try:
                            from flaghunter.interface.notifier import notify

                            notify("warning", f"Failed to update target display: {e}")
                        except Exception:
                            logging.getLogger(__name__).exception(
                                "Failed to notify operator about target update error"
                            )
                        child.message_content = (
                            child.message_content + f"\n  Target: {target}"
                        )
                    updated = True
                    break
                if not updated:
                    try:
                        self._update_header(target=target)
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "Failed to update persistent header with target"
                        )
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed updating in-scroll target display: %s", e
            )
            # Also update the persistent header so the target is always visible
        try:
            self._update_header(target=target)
        except Exception:
            pass

    # === CPA M1 HOOK BEGIN ===
    def _cpa_m1_status_str(self) -> str:
        """Return a compact M1 provider status string for the header."""
        import os
        if os.getenv("CPA_M1_API_HUB", "true").lower() == "false":
            return ""
        try:
            from flaghunter.cpa_modules.m1_api_hub import get_provider_manager
            pm = get_provider_manager()
            providers = pm.list_providers()
            if not providers:
                return ""
            parts = []
            for p in providers[:2]:
                st = pm.get_status(p.id)
                state = st.state.value if st else "unknown"
                dot = "●" if state == "healthy" else ("◑" if state == "degraded" else "○")
                parts.append(f"{p.id} {dot}")
            return "M1: " + " | ".join(parts)
        except Exception:
            return ""
    # === CPA M1 HOOK END ===

    def _update_header(
        self, model_line: Optional[str] = None, target: Optional[str] = None
    ) -> None:
        """Compose and update the persistent header widget."""
        try:
            header = self.query_one("#header", Static)
            # Build header text from provided pieces or current state
            lines: List[str] = []
            flag_banner = getattr(self, "_flag_banner", "")
            if flag_banner:
                lines.append(f"🚩 FLAG FOUND: {flag_banner}")
            if model_line:
                lines.append(model_line)
            else:
                # try to recreate a compact model/runtime line
                runtime_str = (
                    getattr(self, "runtime_info", {}).get("label")
                    or ("Docker" if getattr(self, "use_docker", False) else "Local")
                )
                tools_count = 0
                if self.agent:
                    tools_count = len([t for t in self.agent.get_tools() if t.enabled])
                mode = getattr(self, "_mode", "")
                mode += " (use /assist for single tool execution, /agent or /crew for autonomous modes, /interact for interactive chat)"
                lines.append(
                    f"+ PentestAgent ready\n  Model: {getattr(self, 'model', '')} | Tools: {tools_count} | MCP: {getattr(self, 'mcp_server_count', '')} | RAG: {getattr(self, 'rag_doc_count', '')}\n  Runtime: {runtime_str} | Mode: {mode}"
                )
            runtime_status = getattr(self, "runtime_info", {}).get("status_text", "")
            if runtime_status:
                lines.append(f"  Runtime Status: {runtime_status}")
            # Ensure target line is present/updated
            if target is None:
                target = getattr(self, "target", "")
            if target:
                # append target on its own line
                lines.append(f"  Target: {target}")

            # === CPA M1 HOOK BEGIN ===
            m1_str = self._cpa_m1_status_str()
            if m1_str and lines:
                sub = lines[0].split("\n")
                if len(sub) >= 2:
                    sub[1] = sub[1] + f" | {m1_str}"
                    lines[0] = "\n".join(sub)
            # === CPA M1 HOOK END ===
            header.update("\n".join(lines))
        except Exception:
            pass

    def _hide_sidebar(self) -> None:
        """Hide the sidebar."""
        try:
            # Stop stats timer
            if self._crew_stats_timer:
                self._crew_stats_timer.stop()
                self._crew_stats_timer = None

            sidebar = self.query_one("#sidebar")
            sidebar.remove_class("visible")

            chat_area = self.query_one("#chat-area")
            chat_area.remove_class("with-sidebar")
        except Exception as e:
            logging.getLogger(__name__).exception("Sidebar error: %s", e)
            try:
                from .notifier import notify

                notify("warning", f"TUI: sidebar error: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about sidebar error"
                )

    def _update_crew_stats(self) -> None:
        """Update crew stats panel."""
        try:
            import time

            text = Text()

            # Elapsed time
            text.append("Time:   ", style="bold #d4d4d4")
            if self._crew_start_time:
                elapsed = time.time() - self._crew_start_time
                if elapsed < 60:
                    time_str = f"{int(elapsed)}s"
                elif elapsed < 3600:
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    time_str = f"{mins}m {secs}s"
                else:
                    hrs = int(elapsed // 3600)
                    mins = int((elapsed % 3600) // 60)
                    time_str = f"{hrs}h {mins}m"
                text.append(time_str, style="#9a9a9a")
            else:
                text.append("--", style="#525252")

            text.append("\n")

            # Tokens used
            text.append("Tokens: ", style="bold #d4d4d4")
            if self._crew_tokens_used > 0:
                if self._crew_tokens_used >= 1000:
                    token_str = f"{self._crew_tokens_used / 1000:.1f}k"
                else:
                    token_str = str(self._crew_tokens_used)
                text.append(token_str, style="#9a9a9a")
            else:
                text.append("--", style="#525252")

            stats = self.query_one("#crew-stats", Static)
            stats.update(text)
            stats.border_title = "# Stats"
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to hide sidebar: %s", e)
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to hide sidebar: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about hide_sidebar failure"
                )

    def _update_spinner(self) -> None:
        """Update spinner animation for running workers."""
        try:
            # Advance spinner frame
            self._spinner_frame += 1

            # Only update labels for running workers (efficient)
            has_running = False
            for worker_id, worker in self._crew_workers.items():
                if worker.get("status") == "running":
                    has_running = True
                    # Update the tree node label
                    if worker_id in self._crew_worker_nodes:
                        node = self._crew_worker_nodes[worker_id]
                        node.set_label(self._format_worker_label(worker_id))

            # Stop spinner if no workers are running (save resources)
            if not has_running and self._spinner_timer:
                self._spinner_timer.stop()
                self._spinner_timer = None
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to update crew stats: %s", e)
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to update crew stats: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about crew stats update failure"
                )

    def _add_crew_worker(self, worker_id: str, worker_type: str, task: str) -> None:
        """Add a worker to the sidebar tree."""
        self._crew_workers[worker_id] = {
            "worker_type": worker_type,
            "task": task,
            "status": "pending",
            "findings": 0,
        }

        try:
            label = self._format_worker_label(worker_id)
            if self._crew_orchestrator_node:
                node = self._crew_orchestrator_node.add(
                    label, data={"type": "worker", "id": worker_id}
                )
                self._crew_worker_nodes[worker_id] = node
                try:
                    self._crew_orchestrator_node.expand()
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to expand crew orchestrator node: %s", e
                    )
                    try:
                        from .notifier import notify

                        notify("warning", f"TUI: failed to expand crew node: {e}")
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about crew node expansion failure"
                        )
            self._update_crew_stats()
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to update spinner: %s", e)
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to update spinner: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about spinner update failure"
                )

    def _update_crew_worker(self, worker_id: str, **updates) -> None:
        """Update a worker's state."""
        if worker_id not in self._crew_workers:
            return

        self._crew_workers[worker_id].update(updates)

        # Restart spinner if a worker started running
        if updates.get("status") == "running" and not self._spinner_timer:
            self._spinner_timer = self.set_interval(0.15, self._update_spinner)

        try:
            if worker_id in self._crew_worker_nodes:
                label = self._format_worker_label(worker_id)
                self._crew_worker_nodes[worker_id].set_label(label)
            self._update_crew_stats()
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to add crew worker node: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to add crew worker node: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about add_crew_worker failure"
                )

    def _format_worker_label(self, worker_id: str) -> Text:
        """Format worker label for tree."""
        worker = self._crew_workers.get(worker_id, {})
        status = worker.get("status", "pending")
        wtype = worker.get("worker_type", "worker")
        findings = worker.get("findings", 0)

        # 4-state icons: working (braille), done (checkmark), warning (!), error (X)
        if status in ("running", "pending"):
            # Animated braille spinner for all in-progress states
            icon = self._spinner_frames[self._spinner_frame % len(self._spinner_frames)]
            color = "#d4d4d4"  # white
        elif status == "complete":
            icon = "✓"
            color = "#22c55e"  # green
        elif status == "warning":
            icon = "!"
            color = "#f59e0b"  # amber/orange
        else:  # error, cancelled, unknown
            icon = "✗"
            color = "#ef4444"  # red

        text = Text()
        text.append(f"{icon} ", style=color)
        text.append(wtype.upper(), style="bold")

        if status == "complete" and findings > 0:
            text.append(f" [{findings}]", style="#22c55e")  # green
        elif status in ("error", "cancelled"):
            # Don't append " !" here since we already have the X icon
            pass

        return text

    def _handle_worker_event(
        self, worker_id: str, event_type: str, data: Dict[str, Any]
    ) -> None:
        """Handle worker events from CrewAgent - updates tree sidebar only."""
        try:
            if event_type == "spawn":
                worker_type = data.get("worker_type", "unknown")
                task = data.get("task", "")
                self._add_crew_worker(worker_id, worker_type, task)
            elif event_type == "status":
                status = data.get("status", "running")
                self._update_crew_worker(worker_id, status=status)
            elif event_type == "tool":
                # Add tool as child node under the agent
                tool_name = data.get("tool", "unknown")
                self._add_tool_to_worker(worker_id, tool_name)
            elif event_type == "tokens":
                # Track token usage
                tokens = data.get("tokens", 0)
                self._crew_tokens_used += tokens
            elif event_type == "complete":
                findings_count = data.get("findings_count", 0)
                self._update_crew_worker(
                    worker_id, status="complete", findings=findings_count
                )
                self._crew_findings_count += findings_count
                self._update_crew_stats()
            elif event_type == "warning":
                # Worker hit max iterations but has results
                self._update_crew_worker(worker_id, status="warning")
                reason = data.get("reason", "Partial completion")
                worker = self._crew_workers.get(worker_id, {})
                wtype = worker.get("worker_type", "worker")
                self._add_system(f"[!] {wtype.upper()} stopped: {reason}")
                self._update_crew_stats()
            elif event_type == "failed":
                # Worker determined task infeasible
                self._update_crew_worker(worker_id, status="failed")
                reason = data.get("reason", "Task infeasible")
                worker = self._crew_workers.get(worker_id, {})
                wtype = worker.get("worker_type", "worker")
                self._add_system(f"[!] {wtype.upper()} failed: {reason}")
                self._update_crew_stats()
            elif event_type == "error":
                self._update_crew_worker(worker_id, status="error")
                worker = self._crew_workers.get(worker_id, {})
                wtype = worker.get("worker_type", "worker")
                error_msg = data.get("error", "Unknown error")
                # Only show errors in chat - they're important
                self._add_system(f"[!] {wtype.upper()} failed: {error_msg}")
        except Exception as e:
            self._add_system(f"[!] Worker event error: {e}")

    def _add_tool_to_worker(self, worker_id: str, tool_name: str) -> None:
        """Add a tool usage as child node under worker in tree."""
        try:
            node = self._crew_worker_nodes.get(worker_id)
            if node:
                node.add_leaf(f"  {tool_name}")
                node.expand()
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to update crew worker display: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to update crew worker display: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about update_crew_worker failure"
                )

    @on(Tree.NodeSelected, "#workers-tree")
    def on_worker_tree_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection."""
        node = event.node
        if node.data:
            node_type = node.data.get("type")
            if node_type == "crew":
                self._viewing_worker_id = None
            elif node_type == "worker":
                self._viewing_worker_id = node.data.get("id")

    @work(thread=False)
    async def _run_crew_mode(self, target: str) -> None:
        """Run crew mode with sidebar."""
        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", "crew")

        try:
            from ..agents.base_agent import AgentMessage
            from ..agents.crew import CrewOrchestrator
            from ..llm import LLM, ModelConfig

            # Build prior context from assist/agent conversation history
            prior_context = self._build_prior_context()

            # Ensure model/runtime are available for static analysis
            assert self.model is not None
            assert self.runtime is not None

            llm = LLM(model=self.model, config=ModelConfig(temperature=0.7))

            crew = CrewOrchestrator(
                llm=llm,
                tools=self.all_tools,
                runtime=self.runtime,
                on_worker_event=self._handle_worker_event,
                rag_engine=self.rag_engine,
                target=target,
                prior_context=prior_context,
            )
            self._current_crew = crew  # Track for cancellation

            self._add_system(f"@ Task: {target}")

            # Track crew results for memory
            crew_report = None

            async for update in crew.run(target):
                if self._should_stop:
                    await crew.cancel()
                    self._add_system("[!] Stopped by user")
                    break

                phase = update.get("phase", "")

                if phase == "starting":
                    self._set_status("thinking", "crew")

                elif phase == "tokens":
                    # Track orchestrator token usage
                    tokens = update.get("tokens", 0)
                    self._crew_tokens_used += tokens
                    self._update_crew_stats()

                elif phase == "thinking":
                    # Show the orchestrator's reasoning
                    content = update.get("content", "")
                    if content:
                        self._add_thinking(content)

                elif phase == "tool_call":
                    # Show orchestration tool calls
                    tool = update.get("tool", "")
                    args = update.get("args", {})
                    self._add_tool(tool, str(args))

                elif phase == "tool_result":
                    # Tool results are tracked via worker events
                    pass

                elif phase == "complete":
                    crew_report = update.get("report", "")
                    if crew_report:
                        self._add_assistant(crew_report)

                elif phase == "error":
                    error = update.get("error", "Unknown error")
                    self._add_system(f"[!] Crew error: {error}")

            # Add crew results to main agent's conversation history
            # so assist mode can reference what happened
            if self.agent and crew_report:
                # Add the crew task as a user message
                self.agent.conversation_history.append(
                    AgentMessage(
                        role="user",
                        content=f"[CREW MODE] Run parallel analysis on target: {target}",
                    )
                )
                # Add the crew report as assistant response
                self.agent.conversation_history.append(
                    AgentMessage(role="assistant", content=crew_report)
                )

            self._set_status("complete", "crew")
            self._add_system("+ Crew task complete.")

            # Stop timers
            if self._crew_stats_timer:
                self._crew_stats_timer.stop()
                self._crew_stats_timer = None
            if self._spinner_timer:
                self._spinner_timer.stop()
                self._spinner_timer = None

            # Clear crew reference
            self._current_crew = None

        except asyncio.CancelledError:
            # Cancel crew workers first
            if self._current_crew:
                await self._current_crew.cancel()
                self._current_crew = None
            self._add_system("[!] Cancelled")
            self._set_status("idle", "crew")
            # Stop timers on cancel
            if self._crew_stats_timer:
                self._crew_stats_timer.stop()
                self._crew_stats_timer = None
            if self._spinner_timer:
                self._spinner_timer.stop()
                self._spinner_timer = None

        except Exception as e:
            import traceback

            # Cancel crew workers on error too
            if self._current_crew:
                try:
                    await self._current_crew.cancel()
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to add tool to worker node: %s", e
                    )
                    try:
                        from .notifier import notify

                        notify("warning", f"TUI: failed to add tool to worker: {e}")
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about add_tool_to_worker failure"
                        )
                self._current_crew = None
            self._add_system(f"[!] Crew error: {e}\n{traceback.format_exc()}")
            self._set_status("error")
            # Stop timers on error too
            if self._crew_stats_timer:
                self._crew_stats_timer.stop()
                self._crew_stats_timer = None
            if self._spinner_timer:
                self._spinner_timer.stop()
                self._spinner_timer = None
        finally:
            await self._save_current_conversation()
            self._is_running = False

    async def _display_responses(
        self,
        responses,
        tool_messages_mapping: dict,
        *,
        is_agent: bool = False,
    ) -> None:
        """Consume an agent message iterator and update the chat UI.

        Shared by _run_interact, _run_assist, _run_agent_mode and
        _run_wake_up_mode.  The only behavioural differences between modes
        are gated on is_agent:
          - agent:      intermediate metadata treated as thinking; state checks
                        after each message; _set_status("thinking") between turns
          - non-agent:  no state checks; "finish" tool calls/results skipped
        """
        if is_agent:
            from ..agents.base_agent import AgentState

        async for response in responses:
            if self._should_stop:
                self._add_system("[!] Stopped by user")
                break

            self._set_status("processing")

            if response.content:
                content = response.content.strip()
                if response.tool_calls or (
                    is_agent and response.metadata.get("intermediate")
                ):
                    self._add_thinking(content)
                else:
                    self._add_assistant(content)

            if response.tool_calls:
                for call in response.tool_calls:
                    if not is_agent and call.name == "finish":
                        continue
                    args_str = str(call.arguments)
                    tool_messages_mapping[call.id] = self._add_tool(call.name, args_str)

            if response.tool_results:
                for result in response.tool_results:
                    if result.tool_name == "finish":
                        continue
                    if result.tool_call_id not in tool_messages_mapping:
                        continue
                    if result.success:
                        self._add_tool_result(
                            tool_messages_mapping[result.tool_call_id],
                            result.tool_name,
                            result.result or "Done",
                        )
                    else:
                        self._add_tool_result(
                            tool_messages_mapping[result.tool_call_id],
                            result.tool_name,
                            f"Error: {result.error}",
                        )

            if is_agent:
                if self.agent.get_state() == AgentState.WAITING_INPUT:
                    self._set_status("waiting")
                    self._add_system("? Awaiting input...")
                    break
                elif self.agent.get_state() == AgentState.COMPLETE:
                    break
                self._set_status("thinking")

    @work(thread=False)
    async def _run_interact(self, message: str) -> None:
        """Run in interact mode"""
        if not self.agent:
            self._add_system("[!] Agent not ready")
            return

        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", "interact")

        try:
            tool_messages_mapping: dict[str, ToolMessage] = {}
            await self._display_responses(
                self.agent.interact(message), tool_messages_mapping
            )
            self._set_status("idle", "interact")
        except asyncio.CancelledError:
            self._add_system("[!] Cancelled")
            self._set_status("idle", "interact")
        except Exception as e:
            self._add_system(f"[!] Error: {e}")
            self._set_status("error")
        finally:
            await self._save_current_conversation()
            self._is_running = False

    @work(thread=False)
    async def _run_assist(self, message: str) -> None:
        """Run in assist mode - single response"""
        if not self.agent:
            self._add_system("[!] Agent not ready")
            return

        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", "assist")

        try:
            tool_messages_mapping: dict[str, ToolMessage] = {}
            await self._display_responses(
                self.agent.assist(message), tool_messages_mapping
            )
            self._set_status("idle", "assist")
        except asyncio.CancelledError:
            self._add_system("[!] Cancelled")
            self._set_status("idle", "assist")
        except Exception as e:
            self._add_system(f"[!] Error: {e}")
            self._set_status("error")
        finally:
            await self._save_current_conversation()
            self._is_running = False

    @work(thread=False)
    async def _run_ctf_dispatcher_mode(
        self,
        url: str,
        goal: str,
        chtype: str,
        hint: str,
        submit_profile: dict[str, Any] | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> None:
        """Run the deterministic CTF dispatcher instead of the generic agent loop."""
        runtime = self.runtime or getattr(self.agent, "runtime", None)
        if runtime is None:
            self._add_system("[!] Runtime not ready")
            return

        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", "agent")

        try:
            from ..agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
            from ..agents.pa_agent.platform_runner import (
                PlatformAutonomyRunner,
                PlatformRunConfig,
            )

            current_url = url
            current_goal = goal
            current_type = chtype
            current_hint = hint
            current_submit_profile = dict(submit_profile or {})
            raw_runner_config = dict(runner_config or {})
            resume_autonomy_state = raw_runner_config.pop("_autonomy_resume_state", None)
            resume_reason = str(raw_runner_config.pop("_autonomy_resume_reason", "") or "").strip()
            run_mode = str(raw_runner_config.get("mode") or "switch").strip().lower()
            if run_mode not in {"single", "switch", "drain"}:
                run_mode = "switch"
            normalized_runner_config = {
                "mode": run_mode,
                "max_challenges": max(
                    1, int(raw_runner_config.get("max_challenges") or 4)
                ),
                "timebox_seconds": max(
                    1, int(raw_runner_config.get("timebox_seconds") or 900)
                ),
                "max_consecutive_stops": max(
                    1, int(raw_runner_config.get("max_consecutive_stops") or 2)
                ),
            }
            runner = PlatformAutonomyRunner()
            auto_switch_depth = 0
            initial_key = (
                f"{str(current_submit_profile.get('challenge_id') or '').strip()}|{current_url}"
            )
            runtime_config = PlatformRunConfig(**normalized_runner_config)
            if isinstance(resume_autonomy_state, dict):
                autonomy_state = runner.restore(
                    resume_autonomy_state,
                    config=runtime_config,
                    initial_visit_key=initial_key.strip("|"),
                    resume_reason=resume_reason or "resume",
                )
            else:
                autonomy_state = runner.start(
                    runtime_config,
                    initial_visit_key=initial_key.strip("|"),
                )
            autonomy_end_reason = "not_started"

            while True:
                challenge_started_at = time.time()
                dispatcher = CTFTaskDispatcher(
                    runtime=runtime,
                    progress_callback=self._add_system,
                    llm=getattr(self.agent, "llm", None),
                )
                self._last_ctf_dispatcher = dispatcher
                solve_result = await dispatcher.run(
                    target=current_url,
                    goal=current_goal,
                    type=current_type,
                    hint=current_hint,
                    submit_profile=current_submit_profile,
                )
                self._last_ctf_result = solve_result
                self._last_ctf_state = (
                    dispatcher.state.to_dict() if dispatcher.state is not None else None
                )
                current_state = self._last_ctf_state or {}
                stop_report = (
                    current_state.get("stop_report")
                    if isinstance(current_state, dict)
                    else {}
                ) or {}
                stop_reason = str(
                    stop_report.get("reason")
                    or current_state.get("stop_reason")
                    or solve_result.reason
                    or ""
                )
                current_profile = None
                if isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "platform_profile_snapshot"
                        ):
                            current_profile = item
                            break
                current_challenge_id = str(
                    (current_profile or {}).get("challenge_id")
                    or current_submit_profile.get("challenge_id")
                    or ""
                ).strip()
                current_challenge_name = str(
                    (current_profile or {}).get("challenge_name")
                    or (current_profile or {}).get("name")
                    or ""
                ).strip()
                if not current_challenge_name and isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "platform_challenge_alignment"
                        ):
                            current_challenge_name = str(
                                item.get("challenge_name") or ""
                            ).strip()
                            if current_challenge_name:
                                break
                runner.record_result(
                    autonomy_state,
                    challenge_id=current_challenge_id,
                    challenge_name=current_challenge_name,
                    url=current_url,
                    result=solve_result,
                    stop_reason=stop_reason,
                    started_at=challenge_started_at,
                    ended_at=time.time(),
                )
                queue_snapshot = None
                if isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "platform_task_queue_snapshot"
                        ):
                            queue_snapshot = item
                            break
                    self._last_ctf_state = self._write_platform_run_meta(
                        current_state,
                        autonomy_state=autonomy_state,
                        autonomy_end_reason=autonomy_end_reason,
                    )

                if solve_result.success:
                    self._add_system(
                        "\n".join(
                            [
                                "[CTF dispatcher] success",
                                f"flag: {solve_result.flag}",
                                f"chain_used: {solve_result.chain_used}",
                                f"reason: {solve_result.reason}",
                            ]
                        )
                    )
                    if dispatcher.state is not None and dispatcher.state.stop_report:
                        self._add_system(self._render_last_ctf_stop_report())
                        self._add_system(self._render_last_ctf_reasoning())
                        self._show_ctf_memory_panel()
                    self._set_status("complete", "agent")
                else:
                    lines = [
                        "[CTF dispatcher] stopped",
                        f"chain_used: {solve_result.chain_used}",
                        f"reason: {solve_result.reason}",
                    ]
                    if solve_result.missing_tools:
                        lines.append(
                            "missing_tools: " + ", ".join(solve_result.missing_tools)
                        )
                    self._add_system("\n".join(lines))
                    if dispatcher.state is not None and dispatcher.state.stop_report:
                        self._add_system(self._render_last_ctf_stop_report())
                        self._add_system(self._render_last_ctf_reasoning())
                        self._show_ctf_memory_panel()

                should_continue, autonomy_end_reason = runner.should_continue(
                    autonomy_state,
                    operator_stop=bool(getattr(self, "_should_stop", False)),
                    queue_snapshot=queue_snapshot,
                )
                if not should_continue:
                    break

                next_ctx = self._resolve_ctf_auto_switch_context(
                    result=solve_result,
                    current_url=current_url,
                    current_goal=current_goal,
                    current_type=current_type,
                    current_hint=current_hint,
                    current_submit_profile=current_submit_profile,
                    auto_switch_depth=auto_switch_depth,
                    visited_keys=autonomy_state.visited_keys,
                )
                if next_ctx is None:
                    autonomy_end_reason = "queue_switch_unavailable"
                    break

                autonomy_end_reason = "continue"
                runner.mark_switch(
                    autonomy_state,
                    str(next_ctx.get("visit_key") or ""),
                    reason=str(next_ctx.get("switch_reason") or ""),
                    source=str(next_ctx.get("switch_source") or "platform_queue"),
                )
                auto_switch_depth += 1
                current_url = str(next_ctx["url"])
                current_goal = str(next_ctx["goal"])
                current_type = str(next_ctx["type"])
                current_hint = str(next_ctx["hint"])
                current_submit_profile = dict(next_ctx.get("submit_profile") or {})
                if isinstance(self._last_ctf_state, dict):
                    meta_reasonings = list(self._last_ctf_state.get("meta_reasonings") or [])
                    meta_reasonings.append(
                        {
                            "type": "platform_queue_switch_decision",
                            "switch_reason": str(next_ctx.get("switch_reason") or ""),
                            "switch_source": str(next_ctx.get("switch_source") or "platform_queue"),
                            "skipped_candidates": list(next_ctx.get("skipped_candidates") or []),
                            "next_challenge_id": str(current_submit_profile.get("challenge_id") or ""),
                            "next_url": current_url,
                        }
                    )
                    self._last_ctf_state["meta_reasonings"] = meta_reasonings
                self._last_ctf_context = {
                    "url": current_url,
                    "goal": current_goal,
                    "type": current_type,
                    "hint": current_hint,
                    "submit_profile": dict(current_submit_profile),
                    "runner_config": dict(normalized_runner_config),
                    "execution_mode": "dispatcher",
                    "switch_reason": str(next_ctx.get("switch_reason") or ""),
                    "switch_source": str(next_ctx.get("switch_source") or "platform_queue"),
                    "skipped_candidates": list(next_ctx.get("skipped_candidates") or []),
                    "auto_switch_depth": auto_switch_depth,
                    "visited_queue_keys": sorted(
                        key for key in autonomy_state.visited_keys if key
                    ),
                    "autonomy_state": autonomy_state.to_dict(),
                }
                self._add_system(
                    "\n".join(
                        [
                            "[CTF queue] auto-switch engaged",
                            f"next_url: {current_url}",
                            f"next_challenge_id: {current_submit_profile.get('challenge_id', '')}",
                            f"depth: {auto_switch_depth}",
                            f"switch_reason: {next_ctx.get('switch_reason', '')}",
                            f"runner_mode: {normalized_runner_config['mode']}",
                        ]
                    )
                )

            if isinstance(self._last_ctf_state, dict):
                current_state = self._last_ctf_state
                self._last_ctf_state = self._write_platform_run_meta(
                    current_state,
                    autonomy_state=autonomy_state,
                    autonomy_end_reason=autonomy_end_reason,
                )

            if self._last_ctf_context:
                self._last_ctf_context["runner_config"] = dict(normalized_runner_config)
                self._last_ctf_context["autonomy_state"] = autonomy_state.to_dict()
                self._last_ctf_context["autonomy_end_reason"] = autonomy_end_reason
                self._last_ctf_context["execution_mode"] = str(
                    self._last_ctf_context.get("execution_mode") or "dispatcher"
                )

            await asyncio.sleep(1)
            self._set_status("idle", "assist")
        except asyncio.CancelledError:
            self._add_system("[!] Cancelled")
            self._set_status("idle", "assist")
        except Exception as e:
            self._add_system(f"[!] CTF dispatcher error: {e}")
            self._set_status("error")
        finally:
            await self._save_current_conversation()
            self._is_running = False

    @work(thread=False)
    async def _run_ctf_crew_dispatcher_mode(
        self,
        url: str,
        goal: str,
        chtype: str,
        hint: str,
        submit_profile: dict[str, Any] | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> None:
        """Run the CTF dispatcher through CTFCrewCoordinator."""
        runtime = self.runtime or getattr(self.agent, "runtime", None)
        if runtime is None:
            self._add_system("[!] Runtime not ready")
            return

        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", "crew")

        try:
            from ..agents.crew.swarm_bridge import run_ctf_dispatcher_worker
            from ..agents.pa_agent.ctf_crew_coordinator import CTFCrewCoordinator
            from ..agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher, SolveResult
            from ..agents.pa_agent.ctf_planner import detect_type
            from ..agents.pa_agent.ctf_state import CTFState
            from ..agents.pa_agent.platform_runner import (
                PlatformAutonomyRunner,
                PlatformRunConfig,
            )

            current_url = url
            current_goal = goal
            current_type = chtype
            current_hint = hint
            current_submit_profile = dict(submit_profile or {})
            raw_runner_config = dict(runner_config or {})
            resume_autonomy_state = raw_runner_config.pop("_autonomy_resume_state", None)
            resume_reason = str(raw_runner_config.pop("_autonomy_resume_reason", "") or "").strip()
            run_mode = str(raw_runner_config.get("mode") or "switch").strip().lower()
            if run_mode not in {"single", "switch", "drain"}:
                run_mode = "switch"
            normalized_runner_config = {
                "mode": run_mode,
                "max_challenges": max(1, int(raw_runner_config.get("max_challenges") or 4)),
                "timebox_seconds": max(1, int(raw_runner_config.get("timebox_seconds") or 900)),
                "max_consecutive_stops": max(1, int(raw_runner_config.get("max_consecutive_stops") or 2)),
            }
            runner = PlatformAutonomyRunner()
            auto_switch_depth = 0
            initial_key = f"{str(current_submit_profile.get('challenge_id') or '').strip()}|{current_url}"
            runtime_config = PlatformRunConfig(**normalized_runner_config)
            if isinstance(resume_autonomy_state, dict):
                autonomy_state = runner.restore(
                    resume_autonomy_state,
                    config=runtime_config,
                    initial_visit_key=initial_key.strip("|"),
                    resume_reason=resume_reason or "resume",
                )
            else:
                autonomy_state = runner.start(
                    runtime_config,
                    initial_visit_key=initial_key.strip("|"),
                )
            autonomy_end_reason = "not_started"

            while True:
                challenge_started_at = time.time()
                requested_type = str(current_type or "auto").strip().lower() or "auto"
                planning_dispatcher = CTFTaskDispatcher(
                    runtime=runtime,
                    progress_callback=self._add_system,
                    llm=getattr(self.agent, "llm", None),
                )
                planning_dispatcher.state = CTFState(target=current_url, goal=current_goal)
                planning_dispatcher._apply_submit_profile(current_submit_profile)
                self._carry_forward_platform_switch_context(
                    planning_dispatcher.state,
                    execution_mode="crew",
                    current_url=current_url,
                    current_submit_profile=current_submit_profile,
                )
                self._last_ctf_dispatcher = planning_dispatcher

                await planning_dispatcher._snapshot_platform_context(current_url)
                await planning_dispatcher.capability_registry.full_check()
                planning_dispatcher.state.capabilities = (
                    planning_dispatcher.capability_registry.to_dict()
                )

                page_features = await planning_dispatcher._phase_recon(current_url)
                alignment = planning_dispatcher._align_platform_challenge(current_url, page_features)
                if alignment is not None and planning_dispatcher.state is not None:
                    planning_dispatcher.state.meta_reasonings.append(
                        {
                            "type": "platform_challenge_alignment",
                            **alignment,
                        }
                    )
                    aligned_id = str(alignment.get("challenge_id") or "").strip()
                    if aligned_id and not planning_dispatcher.state.submit_challenge_id:
                        planning_dispatcher.state.submit_challenge_id = aligned_id

                already_solved = bool(alignment and alignment.get("already_solved") is True)
                if already_solved:
                    stop_reason = "challenge_already_solved"
                    planning_dispatcher.state.stop_reason = stop_reason
                    planning_dispatcher.reasoning_layer.generate_stop_report(
                        planning_dispatcher.state,
                        reason=stop_reason,
                        missing_capabilities=[],
                    )
                    solve_result = SolveResult(
                        success=False,
                        flag=None,
                        chain_used=[],
                        notes=[],
                        missing_tools=[],
                        reason=planning_dispatcher._build_already_solved_reason(),
                    )
                    summary = None
                    detected_type = requested_type
                else:
                    detected_type = (
                        requested_type
                        if requested_type not in {"", "auto"}
                        else detect_type(
                            f"{page_features.get('html', '')}\n{page_features.get('content', '')}",
                            current_url,
                        )
                    )
                    planning_dispatcher.state.detected_type = detected_type
                    planning_dispatcher.hypothesis_engine.generate(planning_dispatcher.state)

                    async def _worker_runner(
                        spec: dict[str, Any],
                        shared_state: Any,
                        cancel_event: asyncio.Event,
                    ) -> dict[str, Any]:
                        worker_id = str(spec.get("worker_id") or "worker")
                        worker_type = str(spec.get("worker_type") or "worker")
                        metadata = dict(spec.get("metadata") or {})
                        target_filter = str(spec.get("target_filter") or "").strip()

                        self._update_crew_worker(worker_id, status="running")

                        hint_blocks = [str(current_hint or "").strip()]
                        if worker_type == "recon" and target_filter:
                            hint_blocks.append(
                                f"[Crew directive]\nFocus recon on namespace `{target_filter}` and nearby endpoints first."
                            )
                        hypothesis_kind = str(metadata.get("hypothesis_kind") or "").strip()
                        if hypothesis_kind:
                            hint_blocks.append(
                                f"[Crew directive]\nPrioritize hypothesis `{hypothesis_kind}`. Only pivot when this branch is exhausted."
                            )
                        if worker_type == "llm_explorer":
                            hint_blocks.append(
                                "[Crew directive]\nExplore the unknown surface and produce at least one new actionable observation."
                            )
                        worker_hint = "\n\n".join(block for block in hint_blocks if block)

                        dispatcher = CTFTaskDispatcher(
                            runtime=runtime,
                            progress_callback=lambda message, wid=worker_id: self._add_system(
                                f"[CTF crew:{wid}] {message}"
                            ),
                            llm=getattr(self.agent, "llm", None),
                        )

                        try:
                            result = await run_ctf_dispatcher_worker(
                                dispatcher,
                                target=current_url,
                                goal=current_goal,
                                chtype=detected_type,
                                hint=worker_hint,
                                submit_profile=dict(current_submit_profile or {}),
                                worker_id=worker_id,
                                worker_type=worker_type,
                                cancel_event=cancel_event,
                            )
                        except asyncio.CancelledError:
                            self._update_crew_worker(worker_id, status="cancelled")
                            raise
                        except Exception:
                            self._update_crew_worker(worker_id, status="error")
                            raise

                        state_diff = dict(result.get("state_diff") or {})
                        findings_count = len(list(result.get("candidate_flags") or []))
                        findings_count += len(list(state_diff.get("runtime_flags") or []))
                        if result.get("verified_flag"):
                            findings_count += 1

                        self._update_crew_worker(
                            worker_id,
                            status="complete" if not result.get("cancelled") else "cancelled",
                            findings=findings_count,
                        )
                        return result

                    coordinator = CTFCrewCoordinator(
                        state=planning_dispatcher.state,
                        verifier=planning_dispatcher.verifier,
                        worker_runner=_worker_runner,
                        progress_callback=self._add_system,
                    )
                    self._current_crew = coordinator
                    self._show_sidebar()

                    preview_specs = coordinator.build_worker_specs(
                        target=current_url,
                        page_features=page_features,
                    )
                    for spec in preview_specs:
                        self._add_crew_worker(spec.worker_id, spec.worker_type, spec.task)

                    summary = await coordinator.run_with_shadow_graph(
                        target=current_url,
                        page_features=page_features,
                    )
                    stop_reason = self._derive_ctf_crew_stop_reason(summary)
                    coordinator.state.stop_reason = stop_reason
                    planning_dispatcher.reasoning_layer.generate_stop_report(
                        coordinator.state,
                        reason=stop_reason,
                        missing_capabilities=[],
                    )
                    missing_tools = sorted(
                        {
                            tool
                            for item in summary.worker_results.values()
                            for tool in list(item.get("missing_tools") or [])
                        }
                    )
                    solve_result = SolveResult(
                        success=bool(summary.verified_flag),
                        flag=summary.verified_flag,
                        chain_used=[worker_id for worker_id in summary.started_workers],
                        notes=[],
                        missing_tools=missing_tools,
                        reason=stop_reason,
                    )

                self._last_ctf_result = solve_result
                self._last_ctf_state = (
                    planning_dispatcher.state.to_dict() if planning_dispatcher.state is not None else None
                )
                current_state = self._last_ctf_state or {}
                stop_report = (
                    current_state.get("stop_report") if isinstance(current_state, dict) else {}
                ) or {}
                stop_reason = str(
                    stop_report.get("reason")
                    or current_state.get("stop_reason")
                    or solve_result.reason
                    or ""
                )
                current_profile = None
                if isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if isinstance(item, dict) and item.get("type") == "platform_profile_snapshot":
                            current_profile = item
                            break
                current_challenge_id = str(
                    (current_profile or {}).get("challenge_id")
                    or current_submit_profile.get("challenge_id")
                    or ""
                ).strip()
                current_challenge_name = str(
                    (current_profile or {}).get("challenge_name")
                    or (current_profile or {}).get("name")
                    or ""
                ).strip()
                if not current_challenge_name and isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if isinstance(item, dict) and item.get("type") == "platform_challenge_alignment":
                            current_challenge_name = str(item.get("challenge_name") or "").strip()
                            if current_challenge_name:
                                break

                runner.record_result(
                    autonomy_state,
                    challenge_id=current_challenge_id,
                    challenge_name=current_challenge_name,
                    url=current_url,
                    result=solve_result,
                    stop_reason=stop_reason,
                    started_at=challenge_started_at,
                    ended_at=time.time(),
                )
                queue_snapshot = None
                if isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if isinstance(item, dict) and item.get("type") == "platform_task_queue_snapshot":
                            queue_snapshot = item
                            break
                    self._last_ctf_state = self._write_platform_run_meta(
                        current_state,
                        autonomy_state=autonomy_state,
                        autonomy_end_reason=autonomy_end_reason,
                    )

                if solve_result.success:
                    self._add_system(
                        "\n".join(
                            [
                                "[CTF crew] success",
                                f"flag: {solve_result.flag}",
                                f"chain_used: {solve_result.chain_used}",
                                f"reason: {solve_result.reason}",
                            ]
                        )
                    )
                    self._set_status("complete", "crew")
                else:
                    lines = [
                        "[CTF crew] stopped",
                        f"chain_used: {solve_result.chain_used}",
                        f"reason: {solve_result.reason}",
                    ]
                    if solve_result.missing_tools:
                        lines.append("missing_tools: " + ", ".join(solve_result.missing_tools))
                    if summary is not None:
                        lines.extend(
                            [
                                f"workers_started: {', '.join(summary.started_workers) or 'none'}",
                                f"workers_completed: {', '.join(summary.completed_workers) or 'none'}",
                                f"workers_cancelled: {', '.join(summary.cancelled_workers) or 'none'}",
                            ]
                        )
                    self._add_system("\n".join(lines))
                    self._set_status("idle", "crew")

                if planning_dispatcher.state is not None and planning_dispatcher.state.stop_report:
                    self._add_system(self._render_last_ctf_stop_report())
                    self._add_system(self._render_last_ctf_reasoning())
                    self._show_ctf_memory_panel()

                should_continue, autonomy_end_reason = runner.should_continue(
                    autonomy_state,
                    operator_stop=bool(getattr(self, "_should_stop", False)),
                    queue_snapshot=queue_snapshot,
                )
                if not should_continue:
                    break

                next_ctx = self._resolve_ctf_auto_switch_context(
                    result=solve_result,
                    current_url=current_url,
                    current_goal=current_goal,
                    current_type=current_type,
                    current_hint=current_hint,
                    current_submit_profile=current_submit_profile,
                    auto_switch_depth=auto_switch_depth,
                    visited_keys=autonomy_state.visited_keys,
                )
                if next_ctx is None:
                    autonomy_end_reason = "queue_switch_unavailable"
                    break

                autonomy_end_reason = "continue"
                runner.mark_switch(
                    autonomy_state,
                    str(next_ctx.get("visit_key") or ""),
                    reason=str(next_ctx.get("switch_reason") or ""),
                    source=str(next_ctx.get("switch_source") or "platform_queue"),
                )
                auto_switch_depth += 1
                current_url = str(next_ctx["url"])
                current_goal = str(next_ctx["goal"])
                current_type = str(next_ctx["type"])
                current_hint = str(next_ctx["hint"])
                current_submit_profile = dict(next_ctx.get("submit_profile") or {})
                if isinstance(self._last_ctf_state, dict):
                    meta_reasonings = list(self._last_ctf_state.get("meta_reasonings") or [])
                    meta_reasonings.append(
                        {
                            "type": "platform_queue_switch_decision",
                            "switch_reason": str(next_ctx.get("switch_reason") or ""),
                            "switch_source": str(next_ctx.get("switch_source") or "platform_queue"),
                            "skipped_candidates": list(next_ctx.get("skipped_candidates") or []),
                            "next_challenge_id": str(current_submit_profile.get("challenge_id") or ""),
                            "next_url": current_url,
                        }
                    )
                    self._last_ctf_state["meta_reasonings"] = meta_reasonings
                self._last_ctf_context = {
                    "url": current_url,
                    "goal": current_goal,
                    "type": current_type,
                    "hint": current_hint,
                    "submit_profile": dict(current_submit_profile),
                    "runner_config": dict(normalized_runner_config),
                    "execution_mode": "crew",
                    "switch_reason": str(next_ctx.get("switch_reason") or ""),
                    "switch_source": str(next_ctx.get("switch_source") or "platform_queue"),
                    "skipped_candidates": list(next_ctx.get("skipped_candidates") or []),
                    "auto_switch_depth": auto_switch_depth,
                    "visited_queue_keys": sorted(key for key in autonomy_state.visited_keys if key),
                    "autonomy_state": autonomy_state.to_dict(),
                }
                self._add_system(
                    "\n".join(
                        [
                            "[CTF crew queue] auto-switch engaged",
                            f"next_url: {current_url}",
                            f"next_challenge_id: {current_submit_profile.get('challenge_id', '')}",
                            f"depth: {auto_switch_depth}",
                            f"switch_reason: {next_ctx.get('switch_reason', '')}",
                            f"runner_mode: {normalized_runner_config['mode']}",
                        ]
                    )
                )

            if isinstance(self._last_ctf_state, dict):
                current_state = self._last_ctf_state
                self._last_ctf_state = self._write_platform_run_meta(
                    current_state,
                    autonomy_state=autonomy_state,
                    autonomy_end_reason=autonomy_end_reason,
                )

            if self._last_ctf_context:
                self._last_ctf_context["runner_config"] = dict(normalized_runner_config)
                self._last_ctf_context["autonomy_state"] = autonomy_state.to_dict()
                self._last_ctf_context["autonomy_end_reason"] = autonomy_end_reason
                self._last_ctf_context["execution_mode"] = str(
                    self._last_ctf_context.get("execution_mode") or "crew"
                )

            await asyncio.sleep(1)
            self._set_status("idle", "crew")
        except asyncio.CancelledError:
            if self._current_crew:
                await self._current_crew.cancel()
            self._add_system("[!] Cancelled")
            self._set_status("idle", "crew")
        except Exception as e:
            self._add_system(f"[!] CTF crew error: {e}")
            self._set_status("error")
        finally:
            self._current_crew = None
            await self._save_current_conversation()
            self._is_running = False

    def _derive_ctf_crew_stop_reason(self, summary: Any) -> str:
        base_reason = str(getattr(summary, "stop_reason", "") or "").strip()
        if base_reason in {"flag_verified", "crew_timeout"} or base_reason.startswith("worker_error:"):
            return base_reason

        worker_results = dict(getattr(summary, "worker_results", {}) or {})
        reasons = [str(item.get("reason") or "").strip().lower() for item in worker_results.values() if isinstance(item, dict)]
        missing_tools = [
            tool
            for item in worker_results.values()
            if isinstance(item, dict)
            for tool in list(item.get("missing_tools") or [])
        ]
        if any("wrong flag feedback" in reason for reason in reasons):
            return "wrong_flag_feedback"
        if any("already solved" in reason for reason in reasons):
            return "challenge_already_solved"
        if missing_tools or any(
            token in reason
            for reason in reasons
            for token in ("capability_ceiling", "侦察依赖缺失", "missing tool", "missing_tools")
        ):
            return "capability_ceiling"
        if base_reason == "workers_completed":
            return "all_hypotheses_exhausted"
        return base_reason or "workers_completed"

    def _resolve_ctf_auto_switch_context(
        self,
        *,
        result: Any,
        current_url: str,
        current_goal: str,
        current_type: str,
        current_hint: str,
        current_submit_profile: dict[str, Any] | None,
        auto_switch_depth: int,
        visited_keys: set[str],
    ) -> dict[str, Any] | None:
        state = getattr(self, "_last_ctf_state", None) or {}
        if not self._should_auto_switch_ctf_task(
            state=state,
            result=result,
            auto_switch_depth=auto_switch_depth,
        ):
            return None

        snapshot = None
        for item in reversed(state.get("meta_reasonings") or []):
            if isinstance(item, dict) and item.get("type") == "platform_task_queue_snapshot":
                snapshot = item
                break
        if not snapshot:
            return None

        profile = None
        for item in reversed(state.get("meta_reasonings") or []):
            if isinstance(item, dict) and item.get("type") == "platform_profile_snapshot":
                profile = item
                break
        current_challenge_id = ""
        if profile:
            current_challenge_id = str(profile.get("challenge_id") or "").strip()

        from ..agents.pa_agent.platform_orchestrator import PlatformTaskOrchestrator

        selection = PlatformTaskOrchestrator().select_next_task(
            snapshot,
            current_challenge_id=current_challenge_id,
            visited_keys=visited_keys,
        )
        next_task = selection.get("task")
        if not isinstance(next_task, dict):
            return None

        next_url = self._resolve_next_ctf_queue_url(
            current_url=current_url,
            current_submit_profile=current_submit_profile or {},
            current_challenge_id=current_challenge_id,
            next_task=next_task,
        )
        if not next_url:
            return None

        submit_profile = dict(current_submit_profile or {})
        next_challenge_id = str(next_task.get("challenge_id") or "").strip()
        if next_challenge_id:
            submit_profile["challenge_id"] = next_challenge_id

        queue_hint = (
            f"[Platform queue switch]\n"
            f"- Previous challenge stopped with reason: {getattr(result, 'reason', '')}\n"
            f"- Switched to next queue candidate `{next_task.get('name', '')}` ({next_challenge_id}).\n"
            f"- Switch reason: {selection.get('switch_reason', '')}\n"
            f"- Preserve platform submit profile and continue autonomous solving."
        )
        next_hint = (
            f"{current_hint}\n\n{queue_hint}" if current_hint else queue_hint
        )
        return {
            "url": next_url,
            "goal": current_goal,
            "type": current_type,
            "hint": next_hint,
            "submit_profile": submit_profile,
            "visit_key": f"{next_challenge_id}|{next_url}",
            "switch_reason": str(selection.get("switch_reason") or ""),
            "switch_source": str(selection.get("switch_source") or "platform_queue"),
            "skipped_candidates": list(selection.get("skipped_candidates") or []),
        }

    def _should_auto_switch_ctf_task(
        self,
        *,
        state: dict[str, Any],
        result: Any,
        auto_switch_depth: int,
    ) -> bool:
        if auto_switch_depth >= 3:
            return False
        if getattr(self, "_should_stop", False):
            return False

        stop_report = state.get("stop_report") or {}
        reason = str(stop_report.get("reason") or getattr(result, "reason", "") or "").strip().lower()
        if getattr(result, "success", False):
            return True
        if reason in {
            "challenge_already_solved",
            "all_hypotheses_exhausted",
            "capability_ceiling",
            "stopped",
            "candidate_only",
        }:
            return True
        if "already solved" in reason:
            return True
        if "未命中 flag" in str(getattr(result, "reason", "") or ""):
            return True
        return False

    def _resolve_next_ctf_queue_url(
        self,
        *,
        current_url: str,
        current_submit_profile: dict[str, Any],
        current_challenge_id: str,
        next_task: dict[str, Any],
    ) -> str:
        task_url = str(next_task.get("url") or "").strip()
        if task_url:
            if task_url.startswith("http://") or task_url.startswith("https://"):
                return task_url
            base_url = str(current_submit_profile.get("base_url") or "").strip()
            if base_url:
                return urljoin(base_url.rstrip("/") + "/", task_url.lstrip("/"))

        next_id = str(next_task.get("challenge_id") or "").strip()
        if not next_id:
            return ""

        parsed = urlparse(current_url)
        params = parse_qs(parsed.query)
        replaced = False
        for key in ("challenge_id", "cid", "id", "task_id", "room_code"):
            if key in params:
                params[key] = [next_id]
                replaced = True
        if replaced:
            new_query = urlencode(params, doseq=True)
            return parsed._replace(query=new_query).geturl()

        path_parts = parsed.path.split("/")
        if current_challenge_id:
            replaced_parts = [
                next_id if part == current_challenge_id else part for part in path_parts
            ]
            if replaced_parts != path_parts:
                return parsed._replace(path="/".join(replaced_parts)).geturl()

        base_url = str(current_submit_profile.get("base_url") or "").strip()
        if base_url:
            return urljoin(base_url.rstrip("/") + "/", f"challenges/{next_id}")
        return ""

    def _carry_forward_platform_switch_context(
        self,
        state: Any,
        *,
        execution_mode: str,
        current_url: str,
        current_submit_profile: dict[str, Any] | None,
    ) -> None:
        if state is None or not hasattr(state, "meta_reasonings"):
            return

        previous_context = getattr(self, "_last_ctf_context", None) or {}
        if str(previous_context.get("execution_mode") or "").strip() != execution_mode:
            return

        previous_profile = dict(previous_context.get("submit_profile") or {})
        current_profile = dict(current_submit_profile or {})
        current_challenge_id = str(current_profile.get("challenge_id") or "").strip()
        previous_challenge_id = str(previous_profile.get("challenge_id") or "").strip()
        if current_challenge_id and previous_challenge_id and current_challenge_id != previous_challenge_id:
            return

        switch_reason = str(previous_context.get("switch_reason") or "").strip()
        switch_source = str(previous_context.get("switch_source") or "").strip()
        if not switch_reason and not switch_source:
            return

        carryover = {
            "type": "platform_switch_carryover_context",
            "execution_mode": execution_mode,
            "current_url": current_url,
            "challenge_id": current_challenge_id or previous_challenge_id,
            "switch_reason": switch_reason,
            "switch_source": switch_source or "platform_queue",
            "skipped_candidates": list(previous_context.get("skipped_candidates") or []),
            "auto_switch_depth": int(previous_context.get("auto_switch_depth") or 0),
            "visited_queue_keys": list(previous_context.get("visited_queue_keys") or []),
        }

        meta_reasonings = list(getattr(state, "meta_reasonings", []) or [])
        meta_reasonings = [
            item
            for item in meta_reasonings
            if not (
                isinstance(item, dict)
                and item.get("type")
                in {"platform_switch_carryover_context", "platform_queue_switch_decision"}
            )
        ]
        meta_reasonings.append(carryover)
        meta_reasonings.append(
            {
                "type": "platform_queue_switch_decision",
                "switch_reason": carryover["switch_reason"],
                "switch_source": carryover["switch_source"],
                "skipped_candidates": list(carryover["skipped_candidates"]),
                "next_challenge_id": carryover["challenge_id"],
                "next_url": current_url,
            }
        )
        state.meta_reasonings = meta_reasonings

    def _write_platform_run_meta(
        self,
        state: dict[str, Any],
        *,
        autonomy_state: Any,
        autonomy_end_reason: str,
    ) -> dict[str, Any]:
        if not isinstance(state, dict):
            return state

        elapsed_seconds = round(max(0.0, time.time() - autonomy_state.started_at), 3)
        summary = autonomy_state.to_dict()
        summary.update(
            {
                "type": "platform_autonomy_run_summary",
                "end_reason": autonomy_end_reason,
                "elapsed_seconds": elapsed_seconds,
                "challenge_count": len(autonomy_state.records),
            }
        )
        last_record = summary.get("records", [])[-1] if summary.get("records") else {}
        stop_summary = {
            "type": "platform_run_stop_summary",
            "end_reason": autonomy_end_reason,
            "elapsed_seconds": elapsed_seconds,
            "challenge_count": len(autonomy_state.records),
            "consecutive_stops": summary.get("consecutive_stops", 0),
            "blocked_reasons": list(summary.get("blocked_reasons") or []),
            "skip_reasons": list(summary.get("skip_reasons") or []),
            "resume_count": summary.get("resume_count", 0),
            "resumed_from_record_count": summary.get("resumed_from_record_count", 0),
            "resume_reason": str(summary.get("resume_reason") or ""),
            "last_switch_reason": str(summary.get("last_switch_reason") or ""),
            "last_switch_source": str(summary.get("last_switch_source") or ""),
            "switch_events": list(summary.get("switch_events") or [])[-3:],
            "last_record": dict(last_record) if isinstance(last_record, dict) else {},
        }

        meta_reasonings = list(state.get("meta_reasonings") or [])
        meta_reasonings = [
            item
            for item in meta_reasonings
            if not (
                isinstance(item, dict)
                and item.get("type")
                in {"platform_autonomy_run_summary", "platform_run_stop_summary"}
            )
        ]
        meta_reasonings.extend([summary, stop_summary])
        state["meta_reasonings"] = meta_reasonings
        return state

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

    def _render_last_ctf_stop_report(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        if not state:
            return "[CTF StopReport]\n- unavailable: 请先执行一次 /ctf 题目。"

        stop_report = dict(state.get("stop_report") or {})
        if not stop_report:
            return "[CTF StopReport]\n- unavailable: 当前还没有 stop_report。"

        def _flag_values(field_name: str, fallback_bucket: str) -> list[str]:
            values = [
                str(item).strip()
                for item in list(stop_report.get(field_name) or [])
                if str(item).strip()
            ]
            if values:
                return values
            return [
                self._ctf_state_flag_value(item)
                for item in list(state.get(fallback_bucket) or [])
                if self._ctf_state_flag_value(item)
            ]

        lines = [
            "[CTF StopReport]",
            f"- reason: {stop_report.get('reason', '')}",
            f"- strongest_remaining_hypothesis: {stop_report.get('strongest_remaining_hypothesis', '') or 'n/a'}",
            f"- why_not_pursued: {stop_report.get('why_not_pursued', '') or 'n/a'}",
            f"- candidate_flags: {', '.join(_flag_values('candidate_flags', 'candidate_flags')) or 'none'}",
            f"- runtime_flags: {', '.join(_flag_values('runtime_flags', 'runtime_flags')) or 'none'}",
            f"- verified_flags: {', '.join(_flag_values('verified_flags', 'verified_flags')) or 'none'}",
            f"- rejected_flags: {', '.join(_flag_values('rejected_flags', 'rejected_flags')) or 'none'}",
            f"- missing_capabilities: {', '.join(stop_report.get('missing_capabilities') or []) or 'none'}",
            f"- memory_explanations: {' | '.join(stop_report.get('memory_explanations') or []) or 'none'}",
            f"- memory_focus_entry_ids: {', '.join(stop_report.get('memory_focus_entry_ids') or []) or 'none'}",
            f"- memory_quick_commands: {' | '.join(stop_report.get('memory_quick_commands') or []) or 'none'}",
            f"- recommended_memory_actions: {' | '.join(stop_report.get('recommended_memory_actions') or []) or 'none'}",
            f"- user_next_steps: {' | '.join(stop_report.get('user_next_steps') or []) or 'none'}",
        ]
        return "\n".join(lines)

    def _render_last_ctf_reasoning(self, *, mode: str = "summary", limit: int = 5) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        if not state:
            return "[CTF] 暂无 reasoning：请先执行一次 /ctf 题目。"

        pre_action_reasonings = state.get("pre_action_reasonings") or []
        stop_report = state.get("stop_report") or {}
        surprises = state.get("surprises") or []
        retrospectives = state.get("retrospectives") or []
        meta_reasonings = state.get("meta_reasonings") or []

        limit = max(1, int(limit))

        if mode == "surprises":
            if not surprises:
                return "[CTF reasoning surprises]\n- no surprises recorded"
            lines = ["[CTF reasoning surprises]"]
            for item in list(surprises)[-limit:]:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('id', 'surprise')}: {item.get('actual_result_summary', '')}"
                    )
                else:
                    lines.append(f"- {item}")
            return "\n".join(lines)

        if mode == "postmortem":
            if not retrospectives:
                return "[CTF reasoning postmortem]\n- no retrospectives recorded"
            lines = ["[CTF reasoning postmortem]"]
            for item in list(retrospectives)[-limit:]:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('id', 'retro')}: {item.get('failure_root_cause', '')}"
                    )
                else:
                    lines.append(f"- {item}")
            return "\n".join(lines)

        lines = ["[CTF reasoning]"]
        if pre_action_reasonings:
            selected = list(pre_action_reasonings)[-limit:]
            for idx, item in enumerate(selected, start=1):
                if not isinstance(item, dict):
                    lines.append(f"- reasoning[{idx}]: {item}")
                    continue
                prefix = "" if len(selected) == 1 else f"[pre_action_reasoning {idx}/{len(selected)}]"
                if prefix:
                    lines.append(prefix)
                lines.extend(
                    [
                        f"- current_belief: {item.get('current_belief', '')}",
                        f"- action_rationale: {item.get('action_rationale', '')}",
                        f"- expected_success: {item.get('expected_success_signal', '')}",
                        f"- expected_failure: {item.get('expected_failure_signal', '')}",
                    ]
                )
        if surprises:
            latest_surprise = surprises[-1]
            lines.extend(
                [
                    f"- surprises: {len(surprises)}",
                    f"- latest_surprise: {latest_surprise.get('actual_result_summary', '')}",
                ]
            )
        if stop_report:
            lines.extend(
                [
                    "[CTF stop_report]",
                    f"- reason: {stop_report.get('reason', '')}",
                    f"- strongest_remaining_hypothesis: {stop_report.get('strongest_remaining_hypothesis', '')}",
                    f"- memory_explanations: {' | '.join(stop_report.get('memory_explanations') or [])}",
                    f"- memory_focus_entry_ids: {' | '.join(stop_report.get('memory_focus_entry_ids') or [])}",
                    f"- memory_quick_commands: {' | '.join(stop_report.get('memory_quick_commands') or [])}",
                    f"- recommended_memory_actions: {' | '.join(stop_report.get('recommended_memory_actions') or [])}",
                    f"- user_next_steps: {' | '.join(stop_report.get('user_next_steps') or [])}",
                ]
            )
        lines.extend(self._render_ctf_flag_buckets(state))
        for item in reversed(meta_reasonings):
            if isinstance(item, dict) and item.get("type") == "flag_submit_attempt":
                lines.extend(
                    [
                        "[CTF submit_attempt]",
                        f"- source: {item.get('source', '')}",
                        f"- success: {item.get('success')} correct: {item.get('correct')}",
                        f"- message: {item.get('message', '') or item.get('error', '')}",
                    ]
                )
                break
        for item in reversed(meta_reasonings):
            if isinstance(item, dict) and item.get("type") == "platform_profile_snapshot":
                lines.extend(
                    [
                        "[CTF platform]",
                        f"- platform_type: {item.get('platform_type', '')}",
                        f"- challenge_id: {item.get('challenge_id', '') or 'unknown'}",
                        f"- auto_submit: {item.get('auto_submit')}",
                    ]
                )
                break
        for item in reversed(meta_reasonings):
            if isinstance(item, dict) and item.get("type") == "platform_challenge_alignment":
                lines.append(
                    f"- platform_alignment: matched={item.get('matched')} solved={item.get('already_solved')} challenge={item.get('challenge_name', '')}"
                )
                break
        if retrospectives:
            latest_retro = retrospectives[-1]
            if isinstance(latest_retro, dict):
                lines.append(
                    f"- latest_retrospective: {latest_retro.get('failure_root_cause', '')}"
                )
        return "\n".join(lines)

    def _render_last_ctf_capabilities(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        capabilities = state.get("capabilities") or {}
        primitives = capabilities.get("primitives") or {}
        if not primitives:
            return "[CTF] 暂无 capability 快照：请先执行一次 /ctf 题目。"

        lines = ["[CTF capabilities]"]
        for name, primitive in list(primitives.items())[:8]:
            best = primitive.get("best_available") or {}
            impl = best.get("method") or "none"
            quality = best.get("quality") or "n/a"
            lines.append(
                f"- {name}: implementation={impl} quality={quality}"
            )
        return "\n".join(lines)

    def _render_last_ctf_status(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        if not state:
            return "[CTF] 暂无 status：请先执行一次 /ctf 题目。"

        meta_reasonings = state.get("meta_reasonings") or []
        profile = None
        sync = None
        submit_attempt = None
        alignment = None
        submit_gate = None
        queue_snapshot = None
        autonomy_summary = None
        stop_summary = None
        queue_switch = None
        switch_carryover = None
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if profile is None and item.get("type") == "platform_profile_snapshot":
                profile = item
            if sync is None and item.get("type") == "platform_sync_snapshot":
                sync = item
            if submit_attempt is None and item.get("type") == "flag_submit_attempt":
                submit_attempt = item
            if alignment is None and item.get("type") == "platform_challenge_alignment":
                alignment = item
            if submit_gate is None and item.get("type") == "submit_gate_decision":
                submit_gate = item
            if queue_snapshot is None and item.get("type") == "platform_task_queue_snapshot":
                queue_snapshot = item
            if autonomy_summary is None and item.get("type") == "platform_autonomy_run_summary":
                autonomy_summary = item
            if stop_summary is None and item.get("type") == "platform_run_stop_summary":
                stop_summary = item
            if queue_switch is None and item.get("type") == "platform_queue_switch_decision":
                queue_switch = item
            if switch_carryover is None and item.get("type") == "platform_switch_carryover_context":
                switch_carryover = item
            if (
                profile
                and sync
                and submit_attempt
                and alignment
                and submit_gate
                and queue_snapshot
                and autonomy_summary
            ):
                break

        if queue_switch is None and switch_carryover is not None:
            queue_switch = {
                "switch_reason": switch_carryover.get("switch_reason", ""),
                "switch_source": switch_carryover.get("switch_source", ""),
                "next_challenge_id": switch_carryover.get("challenge_id", ""),
                "next_url": switch_carryover.get("current_url", ""),
                "skipped_candidates": list(switch_carryover.get("skipped_candidates") or []),
            }

        stop_report = state.get("stop_report") or {}
        lines = ["[CTF status]"]
        if profile:
            lines.extend(
                [
                    f"- platform_type: {profile.get('platform_type', '')}",
                    f"- base_url: {profile.get('base_url', '')}",
                    f"- challenge_id: {profile.get('challenge_id', '') or 'unknown'}",
                    f"- auto_submit: {profile.get('auto_submit')}",
                ]
            )
        if sync:
            lines.extend(
                [
                    "[platform sync]",
                    f"- success: {sync.get('success')}",
                    f"- challenge_count: {sync.get('challenge_count')}",
                    f"- scoreboard_keys: {sync.get('scoreboard_keys') or []}",
                    f"- sync_error: {sync.get('error') or sync.get('challenge_error') or sync.get('scoreboard_error') or ''}",
                ]
            )
        if alignment:
            lines.extend(
                [
                    "[challenge alignment]",
                    f"- matched: {alignment.get('matched')} reason={alignment.get('match_reason', '')}",
                    f"- challenge_name: {alignment.get('challenge_name', '')}",
                    f"- already_solved: {alignment.get('already_solved')}",
                    f"- confidence: {alignment.get('confidence')}",
                ]
            )
        if submit_gate:
            lines.extend(
                [
                    "[submit gate]",
                    f"- allow: {submit_gate.get('allow')} reason={submit_gate.get('reason', '')}",
                    f"- source: {submit_gate.get('evidence_source', '')}",
                ]
            )
        if queue_snapshot:
            lines.extend(
                [
                    "[platform queue]",
                    f"- total: {queue_snapshot.get('total')} unsolved: {queue_snapshot.get('unsolved_count')} solved: {queue_snapshot.get('solved_count')}",
                    f"- next: {queue_snapshot.get('next_challenge_id') or ''} {queue_snapshot.get('next_challenge_name') or ''}",
                    f"- rate_limited_until: {queue_snapshot.get('rate_limited_until')}",
                ]
            )
        if autonomy_summary:
            config = autonomy_summary.get("config") or {}
            lines.extend(
                [
                    "[autonomy runner]",
                    f"- mode: {config.get('mode', '')}",
                    f"- challenges: {autonomy_summary.get('challenge_count')} solved={autonomy_summary.get('solved_count')} blocked={autonomy_summary.get('blocked_count')} skipped={autonomy_summary.get('skipped_count')}",
                    f"- switched: {autonomy_summary.get('switched_count')} consecutive_stops={autonomy_summary.get('consecutive_stops')}",
                    f"- elapsed_seconds: {autonomy_summary.get('elapsed_seconds')} end_reason={autonomy_summary.get('end_reason', '')}",
                ]
            )
            if int(autonomy_summary.get("resume_count") or 0) > 0:
                lines.append(
                    f"- resumed: count={autonomy_summary.get('resume_count')} from_records={autonomy_summary.get('resumed_from_record_count', 0)} reason={autonomy_summary.get('resume_reason', '')}"
                )
            if autonomy_summary.get("last_switch_reason") or autonomy_summary.get(
                "last_switch_source"
            ):
                lines.append(
                    f"- last_switch: reason={autonomy_summary.get('last_switch_reason', '')} source={autonomy_summary.get('last_switch_source', '')}"
                )
        if stop_summary:
            last_record = stop_summary.get("last_record") or {}
            lines.extend(
                [
                    "[platform run stop]",
                    f"- end_reason: {stop_summary.get('end_reason', '')}",
                    f"- blocked_reasons: {stop_summary.get('blocked_reasons') or []}",
                    f"- skip_reasons: {stop_summary.get('skip_reasons') or []}",
                ]
            )
            if int(stop_summary.get("resume_count") or 0) > 0:
                lines.append(
                    f"- resume_context: count={stop_summary.get('resume_count')} reason={stop_summary.get('resume_reason', '')}"
                )
            if last_record:
                lines.append(
                    f"- last_record: {last_record.get('challenge_id', '') or 'unknown'} outcome={last_record.get('outcome', '')} reason={last_record.get('reason', '')}"
                )
        if queue_switch:
            lines.extend(
                [
                    "[queue switch]",
                    f"- reason: {queue_switch.get('switch_reason', '')}",
                    f"- source: {queue_switch.get('switch_source', '')}",
                    f"- next_challenge_id: {queue_switch.get('next_challenge_id', '')}",
                    f"- skipped_candidates: {len(queue_switch.get('skipped_candidates') or [])}",
                ]
            )
        if submit_attempt:
            lines.extend(
                [
                    "[latest submit]",
                    f"- source: {submit_attempt.get('source', '')}",
                    f"- success: {submit_attempt.get('success')} correct: {submit_attempt.get('correct')}",
                    f"- message: {submit_attempt.get('message', '') or submit_attempt.get('error', '')}",
                ]
            )
        if stop_report:
            lines.append(f"- stop_reason: {stop_report.get('reason', '')}")
        return "\n".join(lines)

    def _render_last_ctf_queue(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        if not state:
            return "[CTF] 暂无 queue：请先执行一次 /ctf 题目。"

        snapshot = None
        for item in reversed(state.get("meta_reasonings") or []):
            if isinstance(item, dict) and item.get("type") == "platform_task_queue_snapshot":
                snapshot = item
                break
        if not snapshot:
            return "[CTF queue] 暂无平台队列快照。"

        lines = [
            "[CTF queue]",
            f"- platform_type: {snapshot.get('platform_type', '')}",
            f"- total: {snapshot.get('total')} unsolved: {snapshot.get('unsolved_count')} solved: {snapshot.get('solved_count')}",
            f"- next: {snapshot.get('next_challenge_id') or ''} {snapshot.get('next_challenge_name') or ''}",
            f"- rate_limited_until: {snapshot.get('rate_limited_until')}",
        ]
        for task in list(snapshot.get("tasks") or [])[:8]:
            if not isinstance(task, dict):
                continue
            lines.append(
                f"- [{task.get('challenge_id')}] {task.get('name')} solved={task.get('solved')} score={task.get('priority_score')} reason={task.get('priority_reason')}"
            )
        return "\n".join(lines)

    async def _render_last_ctf_memory(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        meta_reasonings = state.get("meta_reasonings") or []
        lines = ["[CTF strategy_memory]"]

        audit = None
        outcome_audit = None
        wrong_feedback_audit = None
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if audit is None and item.get("type") == "strategy_memory_audit":
                audit = item
            if outcome_audit is None and item.get("type") == "strategy_memory_outcome_audit":
                outcome_audit = item
            if wrong_feedback_audit is None and item.get("type") == "strategy_memory_wrong_flag_audit":
                wrong_feedback_audit = item
            if audit and outcome_audit and wrong_feedback_audit:
                break

        if audit:
            lines.append(
                "- adjustments: "
                + json.dumps(audit.get("adjustments") or {}, ensure_ascii=False)
            )
            matched = audit.get("matched_entries") or []
            for item in matched[:3]:
                lines.append(
                    f"- match {item.get('id')}: similarity={item.get('similarity')} win={item.get('winning_hypothesis_kinds')} fail={item.get('failed_hypothesis_kinds')}"
                )
        else:
            lines.append("- adjustments: none")

        if outcome_audit:
            lines.append(
                f"- last_outcome: solved={outcome_audit.get('solved')} matched_entry_ids={outcome_audit.get('matched_entry_ids')}"
            )
        if wrong_feedback_audit:
            lines.append(
                f"- wrong_flag_feedback: rejected={wrong_feedback_audit.get('wrong_flag')} affected={wrong_feedback_audit.get('affected_entry_ids') or []}"
            )
            deprecated_entry_id = wrong_feedback_audit.get("deprecated_entry_id")
            if deprecated_entry_id:
                lines.append(f"- deprecated_session_entry: {deprecated_entry_id}")

        try:
            from ..agents.pa_agent.strategy_memory import StrategyMemoryStore

            store = StrategyMemoryStore()
            recent_entries = await store.list_entries(limit=3)
            if recent_entries:
                lines.append("[recent entries]")
                for entry in recent_entries:
                    lines.append(
                        f"- {entry.id}: type={entry.fingerprint.detected_type} win={entry.winning_hypothesis_kinds} fail={entry.failed_hypothesis_kinds} applied={entry.metadata.applied_count} corr={entry.metadata.success_correlation:.2f}"
                    )
        except Exception as exc:
            lines.append(f"- recent_entries_error: {exc}")

        return "\n".join(lines)

    def _ctf_state_flag_value(self, record: Any) -> str:
        if isinstance(record, dict):
            return str(record.get("value") or "").strip()
        return str(record or "").strip()

    def _render_ctf_flag_buckets(self, state: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        rendered = False
        for bucket_name, label in (
            ("candidate_flags", "candidate"),
            ("runtime_flags", "runtime"),
            ("verified_flags", "verified"),
            ("rejected_flags", "rejected"),
        ):
            values = [
                self._ctf_state_flag_value(item)
                for item in list(state.get(bucket_name) or [])
                if self._ctf_state_flag_value(item)
            ]
            if not values and not rendered:
                continue
            if not rendered:
                lines.append("[CTF flags]")
                rendered = True
            lines.append(f"- {label}: {', '.join(values) if values else 'none'}")
        return lines

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

    def _apply_ctf_user_hint(self, user_hint: str) -> str:
        state = getattr(self, "_last_ctf_state", None)
        last_ctx = getattr(self, "_last_ctf_context", None) or {}
        merged_hint = self._merge_ctf_hint_text(last_ctx.get("hint", ""), user_hint)
        if last_ctx:
            last_ctx["hint"] = merged_hint
            self._last_ctf_context = last_ctx

        if not isinstance(state, dict):
            return merged_hint

        observations = list(state.get("observations") or [])
        observations.append(
            {
                "kind": "user_hint",
                "value": user_hint,
                "source": "operator",
                "metadata": {"priority": "high"},
            }
        )
        state["observations"] = observations

        meta_reasonings = list(state.get("meta_reasonings") or [])
        meta_reasonings.append(
            {
                "type": "user_hint",
                "hint": user_hint,
                "priority": "high",
            }
        )
        state["meta_reasonings"] = meta_reasonings

        stop_report = dict(state.get("stop_report") or {})
        next_steps = list(stop_report.get("user_next_steps") or [])
        next_steps.insert(0, f"已接收用户 hint：{user_hint}")
        deduped_steps: list[str] = []
        seen_steps: set[str] = set()
        for step in next_steps:
            normalized = str(step).strip()
            if not normalized or normalized in seen_steps:
                continue
            seen_steps.add(normalized)
            deduped_steps.append(normalized)
        stop_report["user_next_steps"] = deduped_steps
        state["stop_report"] = stop_report
        return merged_hint

    def _mark_last_ctf_flag_verified(self, override_flag: str) -> None:
        state = getattr(self, "_last_ctf_state", None)
        if not isinstance(state, dict):
            return

        normalized = str(override_flag or "").strip()
        if not normalized:
            return

        for bucket_name in ("candidate_flags", "runtime_flags", "verified_flags", "rejected_flags"):
            bucket = list(state.get(bucket_name) or [])
            state[bucket_name] = [
                item for item in bucket if self._ctf_state_flag_value(item) != normalized
            ]

        verified_bucket = list(state.get("verified_flags") or [])
        verified_bucket.append(
            {
                "value": normalized,
                "level": "verified",
                "evidence_source": "user-override",
                "rationale": "flag explicitly promoted by user override",
                "confidence": 1.0,
                "requires_followup": False,
                "metadata": {"manual_override": True},
            }
        )
        state["verified_flags"] = verified_bucket

    def _rebuild_override_stop_report(self, override_flag: str) -> dict[str, Any]:
        state = getattr(self, "_last_ctf_state", None) or {}
        last_ctx = getattr(self, "_last_ctf_context", None) or {}

        try:
            from ..agents.pa_agent.ctf_state import CTFState
            from ..agents.pa_agent.reasoning import ReasoningLayer

            temp_state = CTFState(
                target=str(state.get("target") or last_ctx.get("url") or ""),
                goal=str(last_ctx.get("goal") or "拿到flag"),
                detected_type=state.get("detected_type"),
            )
            for bucket_name, level in (
                ("candidate_flags", "candidate"),
                ("runtime_flags", "runtime"),
                ("verified_flags", "verified"),
                ("rejected_flags", "rejected"),
            ):
                for item in state.get(bucket_name) or []:
                    value = self._ctf_state_flag_value(item)
                    if not value:
                        continue
                    temp_state.add_flag(
                        value,
                        level=level,  # type: ignore[arg-type]
                        evidence_source="restored-state",
                        rationale="rebuilt from persisted ctf state",
                    )
            temp_state.meta_reasonings = list(state.get("meta_reasonings") or [])
            report = ReasoningLayer().generate_stop_report(
                temp_state,
                reason="flag_verified",
                missing_capabilities=[],
            ).to_dict()
        except Exception:
            report = {
                "reason": "flag_verified",
                "candidate_flags": [],
                "runtime_flags": [],
                "verified_flags": [override_flag],
                "rejected_flags": [],
                "strongest_remaining_hypothesis": None,
                "why_not_pursued": "operator override promoted a flag to verified",
                "missing_capabilities": [],
                "degradation_events": [],
                "surprises": list(state.get("surprises") or []),
                "recommended_memory_actions": [],
                "user_next_steps": [
                    "该 flag 已由用户 override 为 verified；如平台仍拒绝，请立刻执行 `/ctf wrong <flag>`。",
                ],
            }

        previous = state.get("stop_report") or {}
        if not report.get("strongest_remaining_hypothesis"):
            report["strongest_remaining_hypothesis"] = previous.get(
                "strongest_remaining_hypothesis"
            )
        user_steps = list(report.get("user_next_steps") or [])
        user_steps.insert(
            0,
            f"该 flag 已由用户 override 为 verified：{override_flag}",
        )
        report["user_next_steps"] = [
            step
            for idx, step in enumerate(user_steps)
            if str(step).strip() and step not in user_steps[:idx]
        ]
        return report

    def _apply_ctf_override_flag(self, override_flag: str) -> str:
        state = getattr(self, "_last_ctf_state", None)
        if not isinstance(state, dict):
            return (
                f"[CTF override]\n"
                f"- verified_flag: {override_flag}\n"
                "- 当前还没有上一轮 /ctf 状态；已仅持久化 override flag。"
            )

        self._mark_last_ctf_flag_verified(override_flag)
        meta_reasonings = list(state.get("meta_reasonings") or [])
        meta_reasonings.append(
            {
                "type": "user_flag_override",
                "flag": override_flag,
                "decision": "verified",
                "source": "operator",
            }
        )
        state["meta_reasonings"] = meta_reasonings
        state["stop_report"] = self._rebuild_override_stop_report(override_flag)

        last_result = getattr(self, "_last_ctf_result", None)
        try:
            if last_result is not None:
                setattr(last_result, "success", True)
                setattr(last_result, "flag", override_flag)
                setattr(last_result, "reason", "flag_verified")
        except Exception:
            pass

        report = state.get("stop_report") or {}
        lines = [
            "[CTF override]",
            f"- verified_flag: {override_flag}",
            f"- reason: {report.get('reason') or 'flag_verified'}",
            f"- strongest_remaining_hypothesis: {report.get('strongest_remaining_hypothesis') or 'n/a'}",
            f"- user_next_steps: {' | '.join(report.get('user_next_steps') or []) or 'none'}",
        ]
        return "\n".join(lines)

    def _mark_last_ctf_flag_rejected(self, wrong_flag: str) -> None:
        state = getattr(self, "_last_ctf_state", None)
        if not isinstance(state, dict):
            return

        normalized = str(wrong_flag or "").strip()
        if not normalized:
            return

        for bucket_name in ("candidate_flags", "runtime_flags", "verified_flags", "rejected_flags"):
            bucket = list(state.get(bucket_name) or [])
            state[bucket_name] = [
                item for item in bucket if self._ctf_state_flag_value(item) != normalized
            ]

        rejected_bucket = list(state.get("rejected_flags") or [])
        rejected_bucket.append(
            {
                "value": normalized,
                "level": "rejected",
                "evidence_source": "user-feedback",
                "rationale": "flag explicitly rejected by user feedback",
                "confidence": 1.0,
                "requires_followup": False,
                "metadata": {},
            }
        )
        state["rejected_flags"] = rejected_bucket

    def _rebuild_wrong_flag_stop_report(self, wrong_flag: str) -> dict[str, Any]:
        state = getattr(self, "_last_ctf_state", None) or {}
        last_ctx = getattr(self, "_last_ctf_context", None) or {}

        try:
            from ..agents.pa_agent.ctf_state import CTFState
            from ..agents.pa_agent.reasoning import ReasoningLayer

            temp_state = CTFState(
                target=str(state.get("target") or last_ctx.get("url") or ""),
                goal=str(last_ctx.get("goal") or "拿到flag"),
                detected_type=state.get("detected_type"),
            )
            for bucket_name, level in (
                ("candidate_flags", "candidate"),
                ("runtime_flags", "runtime"),
                ("verified_flags", "verified"),
                ("rejected_flags", "rejected"),
            ):
                for item in state.get(bucket_name) or []:
                    value = self._ctf_state_flag_value(item)
                    if not value:
                        continue
                    temp_state.add_flag(
                        value,
                        level=level,  # type: ignore[arg-type]
                        evidence_source="restored-state",
                        rationale="rebuilt from persisted ctf state",
                    )
            temp_state.meta_reasonings = list(state.get("meta_reasonings") or [])
            report = ReasoningLayer().generate_stop_report(
                temp_state,
                reason=f"wrong flag feedback: {wrong_flag}",
                missing_capabilities=[],
            ).to_dict()
        except Exception:
            report = {
                "reason": "wrong_flag_feedback",
                "candidate_flags": [],
                "runtime_flags": [],
                "verified_flags": [],
                "rejected_flags": [wrong_flag],
                "strongest_remaining_hypothesis": None,
                "why_not_pursued": None,
                "missing_capabilities": [],
                "degradation_events": [],
                "surprises": list(state.get("surprises") or []),
                "recommended_memory_actions": [
                    "执行 `/ctf memory audit 0.60 sort=correlation`，优先检查错误 flag 后相关性最低的记忆条目。"
                ],
                "user_next_steps": [
                    "已确认前一个 flag 错误；不要再把它视为成功终点。",
                    "优先沿最近一次 runtime-backed 原语继续深挖。",
                ],
            }

        previous = state.get("stop_report") or {}
        if not report.get("strongest_remaining_hypothesis"):
            report["strongest_remaining_hypothesis"] = previous.get(
                "strongest_remaining_hypothesis"
            )
        return report

    async def _apply_ctf_wrong_flag_feedback(self, wrong_flag: str) -> str:
        state = getattr(self, "_last_ctf_state", None)
        if not isinstance(state, dict):
            return (
                f"[CTF wrong-flag recovery]\n"
                f"- rejected_flag: {wrong_flag}\n"
                "- 当前还没有上一轮 /ctf 状态；已仅持久化 wrong flag。"
            )

        self._mark_last_ctf_flag_rejected(wrong_flag)
        meta_reasonings = list(state.get("meta_reasonings") or [])
        matched_entry_ids: list[str] = []
        session_entry_id: str | None = None
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if not matched_entry_ids and item.get("type") == "strategy_memory_outcome_audit":
                matched_entry_ids = [
                    str(entry_id).strip()
                    for entry_id in (item.get("matched_entry_ids") or [])
                    if str(entry_id).strip()
                ]
            if session_entry_id is None and item.get("type") == "strategy_memory_session_entry":
                candidate = str(item.get("entry_id") or "").strip()
                if candidate:
                    session_entry_id = candidate
            if matched_entry_ids and session_entry_id:
                break

        audit_payload: dict[str, Any] = {
            "type": "strategy_memory_wrong_flag_audit",
            "wrong_flag": wrong_flag,
            "matched_entry_ids": matched_entry_ids,
            "matched_atomic_facts": [],
            "current_atomic_facts": [],
            "memory_trace": [],
            "affected_entry_ids": [],
            "auto_muted_entry_ids": [],
            "deprecated_entry_id": None,
            "entries": [],
        }
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "strategy_memory_audit":
                audit_payload["current_atomic_facts"] = list(
                    item.get("current_atomic_facts") or []
                )
            if item.get("type") == "hypothesis_memory_adjustment":
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                matched_entry_trace = [
                    str(entry_id).strip()
                    for entry_id in (metadata.get("matched_entry_ids") or [])
                    if str(entry_id).strip()
                ]
                if matched_entry_ids and not set(matched_entry_ids) & set(matched_entry_trace):
                    continue
                trace_item = {
                    "kind": str(item.get("kind") or "").strip(),
                    "reason": str(metadata.get("reason") or "").strip(),
                    "matched_atomic_facts": list(metadata.get("matched_atomic_facts") or []),
                    "required_atomic_facts": list(metadata.get("required_atomic_facts") or []),
                    "matched_entry_ids": matched_entry_trace,
                }
                if trace_item["kind"] or trace_item["matched_atomic_facts"] or trace_item["required_atomic_facts"]:
                    audit_payload["memory_trace"].append(trace_item)
            if item.get("type") == "strategy_memory_audit":
                for matched in list(item.get("matched_entries") or []):
                    if not isinstance(matched, dict):
                        continue
                    if matched_entry_ids and str(matched.get("id") or "").strip() not in matched_entry_ids:
                        continue
                    audit_payload["matched_atomic_facts"].extend(
                        str(fact).strip()
                        for fact in (matched.get("atomic_facts") or [])
                        if str(fact).strip()
                    )
        audit_payload["matched_atomic_facts"] = list(
            dict.fromkeys(audit_payload["matched_atomic_facts"])
        )
        try:
            from ..agents.pa_agent.strategy_memory import StrategyMemoryStore

            store = StrategyMemoryStore()
            store_audit = await store.apply_rejected_feedback(
                matched_entry_ids,
                session_entry_id=session_entry_id,
            )
            audit_payload.update(store_audit)
        except Exception as exc:
            audit_payload["error"] = str(exc)

        meta_reasonings.append(audit_payload)
        state["meta_reasonings"] = meta_reasonings
        retrospectives = list(state.get("retrospectives") or [])
        retrospectives.append(
            {
                "id": f"retro_wrong_flag_{len(retrospectives) + 1}",
                "trigger": "wrong_flag_feedback",
                "failure_root_cause": f"user rejected previously extracted flag: {wrong_flag}",
                "learned_rule": "错误 flag 反馈必须回写 memory audit，并沿最近 runtime-backed 原语继续深挖。",
                "strategy_memory_update": True,
            }
        )
        state["retrospectives"] = retrospectives
        state["stop_report"] = self._rebuild_wrong_flag_stop_report(wrong_flag)

        report = state.get("stop_report") or {}
        lines = [
            "[CTF wrong-flag recovery]",
            f"- rejected_flag: {wrong_flag}",
            f"- strongest_remaining_hypothesis: {report.get('strongest_remaining_hypothesis') or 'unknown'}",
            f"- recommended_memory_actions: {' | '.join(report.get('recommended_memory_actions') or []) or 'none'}",
            f"- user_next_steps: {' | '.join(report.get('user_next_steps') or []) or 'none'}",
        ]
        if audit_payload.get("affected_entry_ids"):
            lines.append(
                f"- affected_memory_entries: {audit_payload.get('affected_entry_ids')}"
            )
        if audit_payload.get("deprecated_entry_id"):
            lines.append(
                f"- deprecated_session_entry: {audit_payload.get('deprecated_entry_id')}"
            )
        if audit_payload.get("auto_muted_entry_ids"):
            lines.append(
                f"- auto_muted_entries: {audit_payload.get('auto_muted_entry_ids')}"
            )
        if audit_payload.get("matched_atomic_facts"):
            lines.append(
                f"- matched_atomic_facts: {audit_payload.get('matched_atomic_facts')}"
            )
        if audit_payload.get("memory_trace"):
            lines.append(
                f"- memory_trace: {audit_payload.get('memory_trace')}"
            )
        if audit_payload.get("error"):
            lines.append(f"- memory_audit_error: {audit_payload.get('error')}")
        return "\n".join(lines)

    async def _handle_ctf_memory_subcommand(self, args: list[str]) -> str:
        if not args:
            return await self._render_last_ctf_memory()

        sub = str(args[0] or "").strip().lower()
        from ..agents.pa_agent.strategy_memory import StrategyMemoryStore

        store = StrategyMemoryStore()

        if sub == "list":
            limit = 10
            status, sort_by, threshold, extras = self._parse_ctf_memory_view_args(
                args[1:],
                default_sort="recent",
                default_threshold=0.3,
            )
            for token in extras:
                if token.isdigit():
                    limit = max(1, int(token))
            try:
                entries = await store.list_entries(
                    limit=limit,
                    manual_status=status,
                    sort_by=sort_by,
                )
            except TypeError:
                entries = await store.list_entries(
                    limit=limit,
                    manual_status=status,
                )
            if not entries:
                return "[CTF memory] 暂无记忆条目。"
            lines = [
                f"[CTF memory list] count={len(entries)} filter={status or 'all'} sort={sort_by} threshold={threshold:.2f}"
            ]
            for entry in entries:
                lines.append(self._format_ctf_memory_entry_brief(entry))
            return "\n".join(lines)

        if sub == "show":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory show <id>"
            entry = await store.get_entry(args[1])
            if entry is None:
                return f"[CTF memory] 未找到条目: {args[1]}"
            return self._format_ctf_memory_entry_detail(entry)

        if sub == "mute":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory mute <id>"
            entry = await store.mute_entry(args[1])
            if entry is None:
                return f"[CTF memory] mute 失败: {args[1]}"
            return (
                f"[CTF memory] muted {entry.id}\n"
                + self._format_ctf_memory_entry_brief(entry)
            )

        if sub == "activate":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory activate <id>"
            entry = await store.activate_entry(args[1])
            if entry is None:
                return f"[CTF memory] activate 失败: {args[1]}"
            return (
                f"[CTF memory] activated {entry.id}\n"
                + self._format_ctf_memory_entry_brief(entry)
            )

        if sub == "rollback":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory rollback <id>"
            entry = await store.rollback_mute(args[1])
            if entry is None:
                return f"[CTF memory] rollback 失败: {args[1]}"
            return (
                f"[CTF memory] rollback applied to {entry.id}\n"
                + self._format_ctf_memory_entry_brief(entry)
            )

        if sub == "audit":
            _, sort_by, threshold, _ = self._parse_ctf_memory_view_args(
                args[1:],
                default_sort="correlation",
                default_threshold=0.3,
            )
            try:
                entries = await store.audit_entries(
                    threshold=threshold,
                    sort_by=sort_by,
                )
            except TypeError:
                entries = await store.audit_entries(
                    threshold=threshold,
                )
            if not entries:
                return (
                    f"[CTF memory audit] 无需关注条目（threshold={threshold:.2f}, sort={sort_by}）"
                )
            lines = [
                f"[CTF memory audit] count={len(entries)} threshold={threshold:.2f} sort={sort_by}"
            ]
            for entry in entries:
                lines.append(self._format_ctf_memory_entry_brief(entry))
            return "\n".join(lines)

        if sub == "delete":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory delete <id>"
            deleted = await store.delete_entry(args[1])
            if not deleted:
                return f"[CTF memory] delete 失败: {args[1]}"
            return f"[CTF memory] deleted {args[1]}"

        if sub == "export":
            if len(args) < 2:
                return "[CTF memory] Usage: /ctf memory export <path>"
            exported = await store.export_entries(args[1])
            return f"[CTF memory] exported to {exported}"

        if sub == "clear":
            if len(args) < 2 or str(args[1]).strip().lower() != "confirm":
                return "[CTF memory] Usage: /ctf memory clear confirm"
            count = await store.clear_entries()
            return f"[CTF memory] cleared {count} entries"

        if sub == "panel":
            status, sort_by, threshold, _ = self._parse_ctf_memory_view_args(
                args[1:],
                default_sort="recent",
                default_threshold=0.3,
            )
            filter_mode = status or "all"
            if any(str(token or "").strip().lower() == "audit" for token in args[1:]):
                filter_mode = "audit"
            self._show_ctf_memory_panel(
                filter_mode=filter_mode,
                sort_by=sort_by,
                threshold=threshold,
            )
            return "[CTF memory] panel mounted."

        return (
            "[CTF memory] 用法:\n"
            "- /ctf memory\n"
            "- /ctf memory list [limit] [active|muted|deprecated|filter=<...>] [sort=recent|correlation|applied|last_used]\n"
            "- /ctf memory show <id>\n"
            "- /ctf memory mute <id>\n"
            "- /ctf memory activate <id>\n"
            "- /ctf memory rollback <id>\n"
            "- /ctf memory audit [threshold] [sort=correlation|recent|applied|last_used]\n"
            "- /ctf memory delete <id>\n"
            "- /ctf memory export <path>\n"
            "- /ctf memory clear confirm\n"
            "- /ctf memory panel [filter=all|active|muted|deprecated|audit] [sort=recent|correlation|applied|last_used] [threshold=0.3]"
        )

    def _format_ctf_memory_entry_brief(self, entry: Any) -> str:
        atomic_facts = list(getattr(entry, "atomic_facts", []) or [])
        fact_summary = ", ".join(str(item) for item in atomic_facts[:3]) or "none"
        return (
            f"- {entry.id} "
            f"status={entry.metadata.manual_status} "
            f"type={entry.fingerprint.detected_type} "
            f"win={entry.winning_hypothesis_kinds} "
            f"fail={entry.failed_hypothesis_kinds} "
            f"applied={entry.metadata.applied_count} "
            f"corr={entry.metadata.success_correlation:.2f} "
            f"facts={fact_summary}"
        )

    def _format_ctf_memory_entry_detail(self, entry: Any) -> str:
        lines = [
            f"[CTF memory show] {entry.id}",
            f"- status: {entry.metadata.manual_status}",
            f"- detected_type: {entry.fingerprint.detected_type}",
            f"- tech_stack: {entry.fingerprint.tech_stack}",
            f"- auth_mechanism: {entry.fingerprint.auth_mechanism}",
            f"- winning_hypothesis_kinds: {entry.winning_hypothesis_kinds}",
            f"- failed_hypothesis_kinds: {entry.failed_hypothesis_kinds}",
            f"- winning_primitive_sequence: {entry.winning_primitive_sequence}",
            f"- atomic_facts: {getattr(entry, 'atomic_facts', []) or []}",
            f"- learned_rules: {entry.learned_rules}",
            f"- applied_count: {entry.metadata.applied_count}",
            f"- successful_applications: {entry.metadata.successful_applications}",
            f"- failed_applications: {entry.metadata.failed_applications}",
            f"- success_correlation: {entry.metadata.success_correlation:.2f}",
            f"- confidence_decay_factor: {entry.metadata.confidence_decay_factor:.2f}",
            f"- challenge_url: {entry.challenge_url}",
        ]
        lines.extend(self._ctf_memory_entry_trace_lines(str(entry.id)))
        return "\n".join(lines)

    def _parse_ctf_memory_view_args(
        self,
        tokens: list[str],
        *,
        default_sort: str,
        default_threshold: float,
    ) -> tuple[str | None, str, float, list[str]]:
        status = None
        sort_by = default_sort
        threshold = default_threshold
        extras: list[str] = []

        for raw_token in tokens:
            token = str(raw_token or "").strip()
            lowered = token.lower()
            if lowered in {"active", "muted", "deprecated"}:
                status = lowered
            elif lowered == "audit":
                status = "audit"
            elif lowered.startswith("filter="):
                candidate = lowered.split("=", 1)[1].strip()
                if candidate in {"all", "active", "muted", "deprecated", "audit"}:
                    status = None if candidate == "all" else candidate
                else:
                    extras.append(token)
            elif lowered.startswith("sort="):
                candidate = lowered.split("=", 1)[1].strip()
                if candidate in {"recent", "correlation", "applied", "last_used"}:
                    sort_by = candidate
                else:
                    extras.append(token)
            elif lowered.startswith("threshold="):
                candidate = lowered.split("=", 1)[1].strip()
                try:
                    threshold = float(candidate)
                except ValueError:
                    extras.append(token)
            else:
                try:
                    threshold = float(token)
                except ValueError:
                    extras.append(token)

        return status, sort_by, threshold, extras

    def _show_ctf_memory_panel(
        self,
        *,
        filter_mode: str = "all",
        sort_by: str = "recent",
        threshold: float = 0.3,
        preferred_entry_ids: list[str] | None = None,
    ) -> None:
        preferred_ids = [
            str(entry_id).strip()
            for entry_id in (preferred_entry_ids or self._ctf_memory_preferred_entry_ids())
            if str(entry_id).strip()
        ]
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
        except Exception:
            self._add_system(self._build_ctf_memory_panel_body())
            return
        try:
            import uuid

            panel_id = f"ctf-memory-panel-{uuid.uuid4().hex}"
        except Exception:
            panel_id = None
        widget = CTFMemoryControlPanel(
            self,
            filter_mode=filter_mode,
            sort_by=sort_by,
            threshold=threshold,
            preferred_entry_ids=preferred_ids,
            id=panel_id,
        )
        scroll.mount(widget)
        try:
            scroll.scroll_end(animate=False)
        except Exception:
            pass

    def _build_ctf_memory_panel_body(self) -> str:
        state = getattr(self, "_last_ctf_state", None) or {}
        stop_report = state.get("stop_report") or {}
        meta_reasonings = state.get("meta_reasonings") or []
        lines: list[str] = []
        if stop_report:
            lines.extend(
                [
                    f"reason: {stop_report.get('reason', '')}",
                    f"strongest_remaining_hypothesis: {stop_report.get('strongest_remaining_hypothesis', '')}",
                    f"memory_explanations: {' | '.join(stop_report.get('memory_explanations') or []) or 'none'}",
                    f"memory_focus_entry_ids: {', '.join(stop_report.get('memory_focus_entry_ids') or []) or 'none'}",
                    f"memory_quick_commands: {' | '.join(stop_report.get('memory_quick_commands') or []) or 'none'}",
                    f"recommended_memory_actions: {' | '.join(stop_report.get('recommended_memory_actions') or []) or 'none'}",
                    f"user_next_steps: {' | '.join(stop_report.get('user_next_steps') or []) or 'none'}",
                ]
            )
        audit = None
        wrong_flag_audit = None
        for item in reversed(meta_reasonings):
            if isinstance(item, dict) and item.get("type") == "strategy_memory_outcome_audit":
                audit = item
                break
        for item in reversed(meta_reasonings):
            if isinstance(item, dict) and item.get("type") == "strategy_memory_wrong_flag_audit":
                wrong_flag_audit = item
                break
        if audit:
            lines.append(
                f"matched_entry_ids: {audit.get('matched_entry_ids') or []}"
            )
            lines.append(
                f"suggested_mute_entry_ids: {audit.get('suggested_mute_entry_ids') or []}"
            )
            lines.append(
                f"auto_muted_entry_ids: {audit.get('auto_muted_entry_ids') or []}"
            )
            lines.append(
                f"rollback_candidate_entry_ids: {audit.get('rollback_candidate_entry_ids') or []}"
            )
        if wrong_flag_audit:
            lines.append(
                f"wrong_flag: {wrong_flag_audit.get('wrong_flag') or ''}"
            )
            lines.append(
                f"affected_entry_ids: {wrong_flag_audit.get('affected_entry_ids') or []}"
            )
            lines.append(
                f"deprecated_entry_id: {wrong_flag_audit.get('deprecated_entry_id') or ''}"
            )
            lines.append(
                f"auto_muted_entry_ids: {wrong_flag_audit.get('auto_muted_entry_ids') or []}"
            )
            lines.append(
                f"matched_atomic_facts: {wrong_flag_audit.get('matched_atomic_facts') or []}"
            )
        preferred_entry_ids = self._ctf_memory_preferred_entry_ids()
        if preferred_entry_ids:
            lines.append(f"focus_entry_ids: {preferred_entry_ids}")
        if not lines:
            lines.append("No StopReport / strategy-memory audit available yet.")
        return "\n".join(lines)

    def _ctf_memory_preferred_entry_ids(self) -> list[str]:
        state = getattr(self, "_last_ctf_state", None) or {}
        meta_reasonings = state.get("meta_reasonings") or []
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "strategy_memory_wrong_flag_audit":
                ordered: list[str] = []
                for key in ("affected_entry_ids", "matched_entry_ids", "auto_muted_entry_ids"):
                    for entry_id in list(item.get(key) or []):
                        normalized = str(entry_id).strip()
                        if normalized and normalized not in ordered:
                            ordered.append(normalized)
                deprecated = str(item.get("deprecated_entry_id") or "").strip()
                if deprecated and deprecated not in ordered:
                    ordered.append(deprecated)
                if ordered:
                    return ordered
            if item.get("type") == "strategy_memory_outcome_audit":
                ordered = [
                    str(entry_id).strip()
                    for entry_id in list(item.get("matched_entry_ids") or [])
                    if str(entry_id).strip()
                ]
                if ordered:
                    return ordered
        return []

    def _ctf_memory_entry_trace_lines(self, entry_id: str) -> list[str]:
        normalized_entry_id = str(entry_id or "").strip()
        if not normalized_entry_id:
            return []
        state = getattr(self, "_last_ctf_state", None) or {}
        meta_reasonings = state.get("meta_reasonings") or []
        lines: list[str] = []
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "strategy_memory_wrong_flag_audit":
                affected = {
                    str(candidate).strip()
                    for candidate in (
                        list(item.get("affected_entry_ids") or [])
                        + list(item.get("matched_entry_ids") or [])
                        + list(item.get("auto_muted_entry_ids") or [])
                    )
                    if str(candidate).strip()
                }
                deprecated = str(item.get("deprecated_entry_id") or "").strip()
                if deprecated:
                    affected.add(deprecated)
                if normalized_entry_id in affected:
                    lines.append(
                        f"- related_wrong_flag: {item.get('wrong_flag') or ''}"
                    )
                    lines.append(
                        f"- related_atomic_facts: {item.get('matched_atomic_facts') or []}"
                    )
                    trace_items = list(item.get("memory_trace") or [])
                    if trace_items:
                        lines.append(f"- related_memory_trace: {trace_items}")
                    break
        for item in reversed(meta_reasonings):
            if not isinstance(item, dict) or item.get("type") != "strategy_memory_audit":
                continue
            for matched in list(item.get("matched_entries") or []):
                if not isinstance(matched, dict):
                    continue
                if str(matched.get("id") or "").strip() != normalized_entry_id:
                    continue
                lines.append(
                    f"- last_similarity: {matched.get('similarity', '')}"
                )
                lines.append(
                    f"- matched_atomic_facts: {matched.get('atomic_facts') or []}"
                )
                return lines
        return lines

    @work(thread=False)
    async def _run_agent_mode(self, task: str) -> None:
        """Run in agent mode - autonomous until task complete or user stops"""
        if not self.agent:
            self._add_system("[!] Agent not ready")
            return

        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", "agent")

        try:
            tool_messages_mapping: dict[str, ToolMessage] = {}
            await self._display_responses(
                self.agent.agent_loop(task), tool_messages_mapping, is_agent=True
            )
            self._set_status("complete", "agent")
            self._add_system("+ Agent task complete. Back to assist mode.")
            await asyncio.sleep(1)
            self._set_status("idle", "assist")
        except asyncio.CancelledError:
            self._add_system("[!] Cancelled")
            self._set_status("idle", "assist")
        except Exception as e:
            self._add_system(f"[!] Error: {e}")
            self._set_status("error")
        finally:
            await self._save_current_conversation()
            self._is_running = False

    def _on_agent_wake_up_callback(self) -> None:
        """Triggered by notifier.agent_wake_up() — may come from any async context."""
        try:
            try:
                asyncio.get_running_loop()
                # Already on the app's event loop — post_message directly.
                self.post_message(ChildAgentWakeUpMessage())
                return
            except RuntimeError:
                pass
            # Called from a worker thread — use call_from_thread.
            if hasattr(self, "call_from_thread"):
                try:
                    self.call_from_thread(self.post_message, ChildAgentWakeUpMessage())
                    return
                except Exception:
                    pass
            self.post_message(ChildAgentWakeUpMessage())
        except Exception as e:
            logging.getLogger(__name__).exception(
                "_on_agent_wake_up_callback failed: %s", e
            )

    def on_child_agent_wake_up_message(self, _event: ChildAgentWakeUpMessage) -> None:
        """Received on Textual's main loop — safe to start a @work method here."""
        if not self._is_running and self.agent:
            self._current_worker = self._run_wake_up_mode()

    @work(thread=False)
    async def _run_wake_up_mode(self) -> None:
        """Resume processing a pending child-agent notification in the active mode.

        The notification has already been injected into conversation_history by
        the watcher.  Dispatches display logic per mode so the behaviour is
        identical to the regular runner (_run_assist / _run_interact /
        _run_agent_mode) — avoiding subtle differences in state checks or
        status updates that would break result display.
        """
        if not self.agent:
            return

        mode = self._mode
        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", mode)
        tool_messages_mapping: dict[str, ToolMessage] = {}

        try:
            tool_messages_mapping: dict[str, ToolMessage] = {}
            await self._display_responses(
                self.agent.wake_up(mode),
                tool_messages_mapping,
                is_agent=(mode == "agent"),
            )
            self._set_status("idle", mode)

        except asyncio.CancelledError:
            self._add_system("[!] Cancelled")
            self._set_status("idle", mode)
        except Exception as e:
            self._add_system(f"[!] Error: {e}")
            self._set_status("error")
        finally:
            self._is_running = False

    def action_quit_app(self) -> None:
        # Stop any running tasks first
        if self._is_running:
            self._should_stop = True
            if (
                self._current_worker
                and not getattr(self._current_worker, "done", lambda: False)()
            ):
                cancel = getattr(self._current_worker, "cancel", None)
                if cancel:
                    cancel()
            if self._current_crew:
                # Schedule cancel but don't wait - we're exiting
                asyncio.create_task(self._cancel_crew())
        self.exit()

    def action_stop_agent(self) -> None:
        # Hide suggestions on Escape without stopping the agent
        try:
            suggestions = self.query_one("#cmd-suggestions", CommandSuggestions)
            if suggestions.display:
                suggestions.hide()
                self.query_one("#tab-hint", Static).display = False
                self._get_chat_input().styles.width = "1fr"
                return
        except Exception:
            pass
        if self._is_running:
            self._should_stop = True
            self._add_system("[!] Stopping...")

            # Cancel the running worker to interrupt blocking awaits
            if (
                self._current_worker
                and not getattr(self._current_worker, "done", lambda: False)()
            ):
                cancel = getattr(self._current_worker, "cancel", None)
                if cancel:
                    cancel()

            # Cancel crew orchestrator if running
            if self._current_crew:
                asyncio.create_task(self._cancel_crew())

            # Clean up agent state to prevent stale tool responses
            if self.agent:
                self.agent.cleanup_after_cancel()

            # Reconnect MCP servers (they may be in a bad state after cancellation)
            if self.mcp_manager:
                asyncio.create_task(self._reconnect_mcp_after_cancel())

    async def _cancel_crew(self) -> None:
        """Cancel crew orchestrator and all workers."""
        try:
            if self._current_crew:
                await self._current_crew.cancel()
                self._current_crew = None
                # Mark all running workers as cancelled in the UI
                for worker_id, worker in self._crew_workers.items():
                    if worker.get("status") in ("running", "pending"):
                        self._update_crew_worker(worker_id, status="cancelled")
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to cancel crew orchestrator cleanly: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed during crew cancellation: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about crew cancellation failure"
                )

    async def _reconnect_mcp_after_cancel(self) -> None:
        """Reconnect MCP servers after cancellation to restore clean state."""
        await asyncio.sleep(0.5)  # Brief delay for cancellation to propagate
        try:
            if self.mcp_manager:
                await self.mcp_manager.reconnect_all()
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to reconnect MCP servers after cancel: %s", e
            )
            try:
                from .notifier import notify

                notify(
                    "warning", f"TUI: failed to reconnect MCP servers after cancel: {e}"
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about MCP reconnect failure"
                )

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_focus_next(self) -> None:
        """Complete suggestion with Tab, or fall back to normal focus cycling."""
        if self._suggestions_visible():
            try:
                suggestions = self.query_one("#cmd-suggestions", CommandSuggestions)
                new_value = suggestions.get_tab_completion()
                if new_value is not None:
                    self._set_chat_input_text(new_value)
                    # Refresh suggestions for the new value
                    suggestions.update_suggestions(new_value)
                    return
            except Exception:
                pass
        super().action_focus_next()

    # ----- History navigation -----

    def _suggestions_visible(self) -> bool:
        try:
            return self.query_one("#cmd-suggestions", CommandSuggestions).display
        except Exception:
            return False

    def action_history_up(self) -> None:
        """Navigate suggestions up, or recall previous input into the chat field."""
        if self._suggestions_visible():
            try:
                self.query_one("#cmd-suggestions", CommandSuggestions).select_previous()
            except Exception:
                pass
            return

        try:
            inp = self._get_chat_input()
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to query chat input for history up: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: history navigation failed: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about history_up failure"
                )
            return

        if not self._cmd_history:
            return

        # Move back but not below zero
        if self._history_index > 0:
            self._history_index -= 1

        inp.text = self._cmd_history[self._history_index]
        self._set_chat_input_text(inp.text)

    def action_history_down(self) -> None:
        """Navigate suggestions down, or recall next input (or clear when at end)."""
        if self._suggestions_visible():
            try:
                self.query_one("#cmd-suggestions", CommandSuggestions).select_next()
            except Exception:
                pass
            return

        try:
            inp = self._get_chat_input()
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to query chat input for history down: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: history navigation failed: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about history_down failure"
                )
            return

        if not self._cmd_history:
            return

        if self._history_index < len(self._cmd_history) - 1:
            self._history_index += 1
            inp.text = self._cmd_history[self._history_index]
            self._set_chat_input_text(inp.text)
        else:
            # Past the end: clear input and set index to end
            self._history_index = len(self._cmd_history)
            self._clear_chat_input()

    async def on_unmount(self) -> None:
        """Cleanup"""
        await self._save_current_conversation()

        if self._runtime_probe_timer:
            try:
                self._runtime_probe_timer.stop()
            except Exception:
                pass

        if self.mcp_manager:
            try:
                await self.mcp_manager.disconnect_all()
                await asyncio.sleep(0.1)
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to disconnect MCP manager on unmount: %s", e
                )
                try:
                    from .notifier import notify

                    notify("warning", f"TUI: error during shutdown disconnect: {e}")
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about MCP disconnect failure"
                    )

        if self.runtime:
            try:
                await self.runtime.stop()
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to stop runtime on unmount: %s", e
                )
                try:
                    from .notifier import notify

                    notify("warning", f"TUI: runtime stop error during shutdown: {e}")
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about runtime stop failure"
                    )


# ----- Entry Point -----


def run_tui(
    target: Optional[str] = None,
    model: Optional[str] = None,
    use_docker: bool = False,
    use_ssh: bool = False,
):
    """Run the PentestAgent TUI"""
    # Pre-build RAG before Textual takes over the terminal.
    # On Python 3.14 Textual sets terminal FDs to raw/CLOEXEC mode;
    # sentence-transformers then spawns worker subprocesses that inherit
    # those FDs and crash with "bad value(s) in fds_to_keep".
    # Indexing here (before app.run()) avoids that entirely.
    prebuilt_rag = None
    try:
        import os
        from pathlib import Path as _Path

        from ..knowledge import RAGEngine
        from ..knowledge.embeddings import should_use_local_embeddings

        use_local = should_use_local_embeddings()

        bundled_path = _Path(__file__).parent.parent / "knowledge" / "sources"
        local_path = _Path("knowledge")
        knowledge_path = None
        if local_path.exists() and any(local_path.rglob("*.*")):
            knowledge_path = local_path
        elif bundled_path.exists():
            knowledge_path = bundled_path

        if knowledge_path:
            prebuilt_rag = RAGEngine(
                knowledge_path=knowledge_path,
                use_local_embeddings=use_local,
            )
            prebuilt_rag.index()
    except Exception:
        prebuilt_rag = None

    app = PentestAgentTUI(
        target=target,
        model=model,
        use_docker=use_docker,
        use_ssh=use_ssh,
        prebuilt_rag=prebuilt_rag,
    )
    app.run()


if __name__ == "__main__":
    run_tui()
