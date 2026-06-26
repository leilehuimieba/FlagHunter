"""Core input / scrollbar / tree widgets for FlagHunterTUI (debt ledger 第五波·TUI 刀6).

Extracted from tui.py. The pre-app widget infrastructure: the ASCII-safe
``ASCIIScrollBarRender`` (installed globally via the module-level
``ScrollBar.renderer = ...`` side effect on import), the ASCII ``CrewTree``, the
``COMMAND_SIGNATURES`` slash-command table, the floating ``CommandSuggestions``
autocomplete dropdown, and the multiline ``ChatInputTextArea`` input. The
tab-completion helpers are imported from tui_tab_complete (刀2). AST free-name
analysis confirms the only module-level reference was
COMMAND_SIGNATURES (used solely by CommandSuggestions, zero external users), so
it travels here. The ``TYPE_CHECKING`` FlagHunterAgent import stays behind in
tui.py because it serves a stay-behind FlagHunterTUI annotation, not these
widgets. tui.py re-imports the set so stay-behind callers resolve unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.scrollbar import ScrollBar, ScrollBarRender
from textual.widget import Widget
from textual.widgets import Static, TextArea, Tree

from .tui_tab_complete import (
    _get_display_parts,
    _is_placeholder,
    _sig_matches,
    _tab_complete,
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
    ("/quit", "Exit FlagHunter"),
]


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
