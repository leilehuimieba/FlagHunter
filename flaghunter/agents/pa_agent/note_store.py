"""Note / artifact persistence mixin extracted from ctf_dispatcher.py.

P5 / Workstream A: the contiguous note/artifact storage cluster (6 methods,
_store_secret_note .. _derive_artifact_category) is physically moved out of
CTFTaskDispatcher into a behaviour-preserving mixin. Method bodies are identical;
self.* (state, runtime, reasoning_layer, _record_session_event,
_select_hypothesis_for_chain, _register_artifact_record, _notes_log, _emit)
resolves at runtime against the dispatcher that mixes this in, so call sites are
unchanged. Pure code relocation, near-zero risk.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ...harness.audit_events import build_missing_tools_recorded_event
from ...tools.notes import notes as notes_tool


class NoteStoreMixin:
    """Persist findings/credentials/artifacts to the notes tool and agent state."""

    async def _store_secret_note(self, name: str, value: str, target: str) -> None:
        await self._store_note(
            key=f"ctf_{name}",
            value=f"Recovered {name}: {value}",
            category="credential",
            target=urlparse(target).netloc or target,
            username=name,
            password=value,
        )

    async def _store_missing_tools(
        self,
        missing: list[str],
        install_commands: dict[str, str],
    ) -> None:
        missing_tools_event = build_missing_tools_recorded_event(
            missing_tools=list(missing),
            install_commands=dict(install_commands),
        )
        self._record_session_event(
            str(missing_tools_event.get("event_type") or "missing_tools_recorded"),
            dict(missing_tools_event.get("payload") or {}),
        )
        message = "缺少: " + ", ".join(missing) + "\n建议:\n" + "\n".join(
            f"- {name}: {cmd}" for name, cmd in install_commands.items()
        )
        await self._store_note(
            key="tool_missing_ctf_chain",
            value=message,
            category="artifact",
            target="ctf",
        )

    async def _store_retrospective(self, reason: str, target: str, chain_name: str) -> None:
        if self.state is not None:
            active_hypothesis = self._select_hypothesis_for_chain(chain_name)
            self.reasoning_layer.record_retrospective(
                self.state,
                trigger=chain_name,
                reason=reason,
                active_hypothesis=active_hypothesis,
            )
        await self._store_note(
            key="ctf_retrospective",
            value=f"chain={chain_name}; reason={reason}",
            category="task",
            target=urlparse(target).netloc or target,
        )

    async def _store_note(self, key: str, value: str, category: str = "finding", **metadata) -> None:
        await notes_tool(
            {
                "action": "update",
                "key": key,
                "value": value,
                "category": category,
                "confidence": "high",
                **metadata,
            },
            runtime=self.runtime,
        )
        if self.state is not None and category in {"artifact", "credential"}:
            artifact_producer = self._derive_artifact_producer(
                key=key,
                category=category,
                metadata=metadata,
            )
            artifact_category = self._derive_artifact_category(
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
            self.state.add_artifact(
                key,
                location=str(location) if location is not None else None,
                source=artifact_producer,
                metadata=artifact_metadata,
            )
            self._register_artifact_record(
                kind=category,
                title=key,
                path=str(path) if path is not None else None,
                location=str(location) if location is not None else None,
                producer=artifact_producer,
                metadata=artifact_metadata,
            )
        line = f"[{category}] {key}: {value}"
        self._notes_log.append(line)
        self._emit(f"[CTF dispatcher] note saved: {key}")

    def _derive_artifact_producer(
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

    def _derive_artifact_category(
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
