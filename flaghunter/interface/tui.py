"""
FlagHunter TUI - Terminal User Interface
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
from .tui_messages import (
    ChildAgentWakeUpMessage,
    DespawnTerminalMessage,
    MCPTaskEvent,
    SpawnTerminalMessage,
)
from .tui_message_widgets import (
    AssistantMessage,
    CopyButton,
    CopyableMixin,
    ForkButton,
    RewindButton,
    SystemMessage,
    ThinkingMessage,
    ToolMessage,
    ToolResultMessage,
    UserMessage,
    wrap_text_lines,
)
from .tui_tab_complete import (
    _get_display_parts,
    _is_placeholder,
    _sig_matches,
    _tab_complete,
)
from .tui_screens import (
    ConversationsScreen,
    ForkConfirmScreen,
    HelpScreen,
    MCPScreen,
    RewindConfirmScreen,
    ToolsScreen,
    WorkspaceHelpScreen,
)
from .tui_diagnostics import (
    CTFMemoryControlPanel,
    CTFMemoryOperationsPanel,
    MemoryDiagnostics,
    ResizeDivider,
    StatusBar,
    TokenDiagnostics,
)
from .tui_core_widgets import (
    ASCIIScrollBarRender,
    COMMAND_SIGNATURES,
    ChatInputTextArea,
    CommandSuggestions,
    CrewTree,
)
from .tui_format_mixin import ToolResultFormatMixin
from .tui_scan_commands import ScanCommandMixin
from .tui_conversation import ConversationMixin
from .tui_cpa_commands import CpaCommandMixin
from .tui_mode_commands import ModeCommandMixin
from .tui_terminal import TerminalSpawnMixin
from .tui_ctf_memory import CtfMemoryMixin
from .tui_crew import CrewMixin
from .tui_ctf_render import CtfRenderMixin
from .tui_ctf_apply import CtfApplyMixin
from .tui_ctf_runners import CtfRunnerMixin
from .tui_ctf_commands import CtfCommandMixin
from .tui_info_commands import InfoCommandMixin
from .tui_retry_commands import RetryCommandMixin
from .tui_mcp_mode import McpModeMixin
from .tui_runtime_probe import RuntimeProbeMixin
from .tui_notification import NotificationMixin
from .tui_wakeup import WakeUpMixin
from .tui_actions import ActionsMixin
from .tui_chrome import ChromeMixin

# ANSI escape sequence pattern for stripping control codes from input
_ANSI_ESCAPE = re.compile(
    r"\x1b\[[0-9;]*[mGKHflSTABCDEFsu]|\x1b\].*?\x07|\x1b\[<[0-9;]*[Mm]"
)


if TYPE_CHECKING:
    from ..agents.pa_agent import FlagHunterAgent


# ----- Main TUI App -----


class FlagHunterTUI(ToolResultFormatMixin, ScanCommandMixin, ConversationMixin, CpaCommandMixin, ModeCommandMixin, TerminalSpawnMixin, CtfMemoryMixin, CrewMixin, CtfRenderMixin, CtfApplyMixin, CtfRunnerMixin, CtfCommandMixin, InfoCommandMixin, RetryCommandMixin, McpModeMixin, RuntimeProbeMixin, NotificationMixin, WakeUpMixin, ActionsMixin, ChromeMixin, App):
    """Main FlagHunter TUI Application"""

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

    TITLE = "FlagHunter"
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
        self.agent: Optional["FlagHunterAgent"] = None
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
            from ..session import AgentSession
            from ..tools import get_all_tools
            from .initializer import has_ssh_runtime_config

            if not self.model:
                self._add_system(
                    "[!] No model configured. Set FLAGHUNTER_MODEL environment variable or create a .env file (see .env.example)."
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

            # Single assembly path (architecture invariant I2). AgentSession.create
            # funnels build_agent_components, so the TUI initializes the runtime,
            # RAG, workspace AND the CPA modules (M1-M6) the same way as the CLI,
            # web and MCP entrypoints — instead of hand-calling the builder.
            session = await AgentSession.create(
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
            components = session.components

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
                        f"+ FlagHunter ready\n"
                        f"  Model: {self.model} | Tools: {len(self.all_tools)} | MCP: {mcp_server_count} | RAG: {rag_doc_count}\n"
                        f"  Runtime: {runtime_str} | Mode: Assist (use /agent or /crew for autonomous modes)"
                    )
                )
            except Exception:
                self._add_system(
                    f"+ FlagHunter ready\n"
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
                if isinstance(child, SystemMessage) and "FlagHunter ready" in getattr(
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
    """Run the FlagHunter TUI"""
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

    app = FlagHunterTUI(
        target=target,
        model=model,
        use_docker=use_docker,
        use_ssh=use_ssh,
        prebuilt_rag=prebuilt_rag,
    )
    app.run()


if __name__ == "__main__":
    run_tui()
