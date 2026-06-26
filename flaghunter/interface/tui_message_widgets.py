"""Chat message + action-button display widgets for FlagHunterTUI (debt ledger 第五波·TUI 刀3).

Extracted from tui.py. Ten cohesive display widgets — the copy / rewind / fork
action buttons (each posting a nested ``Pressed`` / ``RewindPressed`` /
``ForkPressed`` message), the ``CopyableMixin`` base that mounts them on hover,
and the chat bubble widgets (Thinking / Tool / ToolResult / Assistant / User /
System) — plus their exclusive ``wrap_text_lines`` text helper. The helper was
co-located here because all five of its callers are these widgets and no
stay-behind tui.py code uses it (so it cannot strand a back-import). The cluster
references only each other plus rich/textual primitives + stdlib textwrap, so it
is down-closed with zero upward dependency on tui.py. tui.py re-imports the set
so stay-behind producers (FlagHunterTUI compose / mount paths) resolve unchanged.
"""

from __future__ import annotations

import textwrap
from typing import List

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Static


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
            (">> ", "#9a9a9a"), ("FlagHunter", "bold #d4d4d4")
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
