"""Note / artifact persistence extracted from ctf_dispatcher.py.

L3d / cut A: the contiguous note/artifact storage cluster (6 methods,
_store_secret_note .. _derive_artifact_category) is object-ified into an
independent ``NoteStore`` class.  ``NoteStoreMixin`` is retained as a thin
delegation shell (original method names + signatures) so the MRO and every call
site are unchanged.  Method bodies are byte-for-byte identical; the only
mechanical change is that the per-turn / sibling collaborators (``state``,
``runtime``, ``reasoning_layer``, ``_record_session_event``,
``_select_hypothesis_for_chain``, ``_register_artifact_record``, ``_emit``) and
the mutable ``_notes_log`` list are passed per-call rather than resolved via
``self.*``.  ``_notes_log`` deliberately stays owned by the dispatcher and is
handed in as a list reference so ``result.notes = list(self._notes_log)`` keeps
reading the same list — ``NoteStore`` never holds it.  Pure code relocation,
near-zero risk.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ...harness.audit_events import build_missing_tools_recorded_event
from ...tools.notes import notes as notes_tool


class NoteStore:
    """Persist findings/credentials/artifacts to the notes tool and agent state.

    Object-ified (L3d, cut A): independent of ``CTFTaskDispatcher`` and
    unit-testable fully detached.  Has no ``__init__`` and holds **no** eager
    reference to ``state``, ``runtime`` or sibling methods — those are rebound
    every turn / on resume by the dispatcher, so they are passed per-call.  The
    mutable ``_notes_log`` is owned by the dispatcher and passed in as a list
    reference; this class only ``.append(...)`` to it (never stores it), so the
    dispatcher's ``result.notes`` keeps reading the same list.  Behaviour is
    byte-for-byte identical to the previous inline implementation.
    """

    async def store_secret_note(
        self,
        state,
        *,
        runtime,
        register_artifact_record,
        emit,
        notes_log,
        name: str,
        value: str,
        target: str,
    ) -> None:
        await self.store_note(
            state,
            runtime=runtime,
            register_artifact_record=register_artifact_record,
            emit=emit,
            notes_log=notes_log,
            key=f"ctf_{name}",
            value=f"Recovered {name}: {value}",
            category="credential",
            target=urlparse(target).netloc or target,
            username=name,
            password=value,
        )

    async def store_missing_tools(
        self,
        state,
        *,
        runtime,
        record_session_event,
        register_artifact_record,
        emit,
        notes_log,
        missing: list[str],
        install_commands: dict[str, str],
    ) -> None:
        missing_tools_event = build_missing_tools_recorded_event(
            missing_tools=list(missing),
            install_commands=dict(install_commands),
        )
        record_session_event(
            str(missing_tools_event.get("event_type") or "missing_tools_recorded"),
            dict(missing_tools_event.get("payload") or {}),
        )
        message = "缺少: " + ", ".join(missing) + "\n建议:\n" + "\n".join(
            f"- {name}: {cmd}" for name, cmd in install_commands.items()
        )
        await self.store_note(
            state,
            runtime=runtime,
            register_artifact_record=register_artifact_record,
            emit=emit,
            notes_log=notes_log,
            key="tool_missing_ctf_chain",
            value=message,
            category="artifact",
            target="ctf",
        )

    async def store_retrospective(
        self,
        state,
        *,
        runtime,
        reasoning_layer,
        select_hypothesis_for_chain,
        register_artifact_record,
        emit,
        notes_log,
        reason: str,
        target: str,
        chain_name: str,
    ) -> None:
        if state is not None:
            active_hypothesis = select_hypothesis_for_chain(chain_name)
            reasoning_layer.record_retrospective(
                state,
                trigger=chain_name,
                reason=reason,
                active_hypothesis=active_hypothesis,
            )
        await self.store_note(
            state,
            runtime=runtime,
            register_artifact_record=register_artifact_record,
            emit=emit,
            notes_log=notes_log,
            key="ctf_retrospective",
            value=f"chain={chain_name}; reason={reason}",
            category="task",
            target=urlparse(target).netloc or target,
        )

    async def store_note(
        self,
        state,
        *,
        runtime,
        register_artifact_record,
        emit,
        notes_log,
        key: str,
        value: str,
        category: str = "finding",
        **metadata,
    ) -> None:
        await notes_tool(
            {
                "action": "update",
                "key": key,
                "value": value,
                "category": category,
                "confidence": "high",
                **metadata,
            },
            runtime=runtime,
        )
        if state is not None and category in {"artifact", "credential"}:
            artifact_producer = self.derive_artifact_producer(
                key=key,
                category=category,
                metadata=metadata,
            )
            artifact_category = self.derive_artifact_category(
                key=key,
                category=category,
                metadata=metadata,
            )
            path = metadata.get("path") or metadata.get("file_path") or metadata.get("local_path")
            location = metadata.get("url") or metadata.get("target") or metadata.get("location")
            artifact_metadata = {
                "category": artifact_category,
                "note_category": category,
                "content": value,
                **metadata,
            }
            state.add_artifact(
                key,
                location=str(location) if location is not None else None,
                source=artifact_producer,
                metadata=artifact_metadata,
            )
            register_artifact_record(
                kind=category,
                title=key,
                path=str(path) if path is not None else None,
                location=str(location) if location is not None else None,
                producer=artifact_producer,
                metadata=artifact_metadata,
            )
        line = f"[{category}] {key}: {value}"
        notes_log.append(line)
        emit(f"[CTF dispatcher] note saved: {key}")

    def derive_artifact_producer(
        self,
        *,
        key: str,
        category: str,
        metadata: dict[str, Any],
    ) -> str:
        explicit = str(
            metadata.get("artifact_producer") or metadata.get("producer") or ""
        ).strip()
        if explicit:
            return explicit
        strategy_kind = str(metadata.get("strategy_kind") or "").strip()
        if strategy_kind:
            return strategy_kind
        normalized_key = str(key or "").strip().lower()
        if normalized_key.startswith("ctf_flag"):
            return "verifier"
        if normalized_key.startswith("ctf_backup_"):
            return "backup_source_leak"
        return "notes" if category == "artifact" else str(category or "").strip() or "notes"

    def derive_artifact_category(
        self,
        *,
        key: str,
        category: str,
        metadata: dict[str, Any],
    ) -> str:
        explicit = str(metadata.get("artifact_category") or "").strip()
        if explicit:
            return explicit
        normalized_key = str(key or "").strip().lower()
        mapped_categories = {
            "ctf_flag_candidate": "flag_candidate",
            "ctf_flag_runtime": "flag_runtime",
            "ctf_flag": "flag_verified",
            "ctf_backup_candidate": "backup_candidate",
            "ctf_backup_analysis": "backup_analysis",
            "ctf_artifact_forensics": "artifact_forensics_summary",
        }
        if normalized_key in mapped_categories:
            return mapped_categories[normalized_key]
        return str(category or "").strip() or "artifact"


class NoteStoreMixin:
    """Thin delegation shell forwarding to the dispatcher's ``NoteStore``."""

    async def _store_secret_note(self, name: str, value: str, target: str) -> None:
        await self._note_store.store_secret_note(
            self.state,
            runtime=self.runtime,
            register_artifact_record=self._register_artifact_record,
            emit=self._emit,
            notes_log=self._notes_log,
            name=name,
            value=value,
            target=target,
        )

    async def _store_missing_tools(
        self,
        missing: list[str],
        install_commands: dict[str, str],
    ) -> None:
        await self._note_store.store_missing_tools(
            self.state,
            runtime=self.runtime,
            record_session_event=self._record_session_event,
            register_artifact_record=self._register_artifact_record,
            emit=self._emit,
            notes_log=self._notes_log,
            missing=missing,
            install_commands=install_commands,
        )

    async def _store_retrospective(self, reason: str, target: str, chain_name: str) -> None:
        await self._note_store.store_retrospective(
            self.state,
            runtime=self.runtime,
            reasoning_layer=self.reasoning_layer,
            select_hypothesis_for_chain=self._select_hypothesis_for_chain,
            register_artifact_record=self._register_artifact_record,
            emit=self._emit,
            notes_log=self._notes_log,
            reason=reason,
            target=target,
            chain_name=chain_name,
        )

    async def _store_note(self, key: str, value: str, category: str = "finding", **metadata) -> None:
        await self._note_store.store_note(
            self.state,
            runtime=self.runtime,
            register_artifact_record=self._register_artifact_record,
            emit=self._emit,
            notes_log=self._notes_log,
            key=key,
            value=value,
            category=category,
            **metadata,
        )

    def _derive_artifact_producer(
        self,
        *,
        key: str,
        category: str,
        metadata: dict[str, Any],
    ) -> str:
        return self._note_store.derive_artifact_producer(
            key=key,
            category=category,
            metadata=metadata,
        )

    def _derive_artifact_category(
        self,
        *,
        key: str,
        category: str,
        metadata: dict[str, Any],
    ) -> str:
        return self._note_store.derive_artifact_category(
            key=key,
            category=category,
            metadata=metadata,
        )
