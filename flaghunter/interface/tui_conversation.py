"""Conversation persistence / restore / rewind / fork mixed into FlagHunterTUI (debt ledger 第五波·TUI 刀9, god-class).

Extracted from tui.py. The conversation lifecycle feature: truncate-to-message
(for rewind/fork), the ``@on(UserMessage.RewindPressed/ForkPressed)`` handlers and
their ``_do_*`` workers, plus save / restore of the current conversation and
session-state snapshot. Persistence backends (ConversationStore, session-file
helpers, json) are lazy-imported inside the method bodies, so they travel with
the code. All cross refs (``self._add_*`` message helpers, ``self._set_status`` /
``_update_header`` / ``_cancel_running_tasks``) resolve at runtime through the
FlagHunterTUI instance MRO. ``UserMessage`` is imported here because the ``@on``
decorators are evaluated at class-definition time (not just annotations).
"""

from __future__ import annotations

import logging
from typing import Any

from textual import on
from textual.containers import ScrollableContainer

from .tui_message_widgets import UserMessage


class ConversationMixin:
    """Conversation save / restore / rewind / fork for FlagHunterTUI."""

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
