"""Audit / persistence infrastructure mixin extracted from ctf_dispatcher.py.

P5 / twelfth cut: the contiguous audit-substrate block (13 methods, ~298
lines) is physically moved out of CTFTaskDispatcher into a
behaviour-preserving mixin. This is the bottom layer everything above it
calls — the three ``_setup_*`` store constructors, the single
``_record_session_event`` sink, the audit-event emitters
(``_write_checkpoint`` / ``_register_artifact_record`` /
``_record_recovery_decision``), the artifact-registry readbacks
(``_resolve_registered_local_*`` / ``_ingest_registered_local_source_hints``)
and the three instrumented ``_runtime_*_action`` passthroughs.

L3e / cut A: the RT cluster (``_runtime_*_action``) was object-ified into the
independent stateless ``RuntimeAuditedActions`` class; the mixin retains thin
delegation shells.

L3f-2 / cut A: the remaining ~10 store methods (session-ledger / artifact /
checkpoint setup, the ``_record_session_event`` sink, the audit-event emitters,
the artifact-registry readbacks and source-hint ingestion) are object-ified
into the single independent stateless ``AuditStore`` class. ``AuditInfraMixin``
keeps every method as a thin delegation shell (original names + signatures) so
the MRO and every call site are unchanged. Method bodies are byte-for-byte
identical; the only mechanical change is that the backing store objects
(``_session_ledger`` / ``_artifact_registry`` / ``_checkpoint_store``), their
run ids and the per-turn collaborators (``state``, the sibling
``_record_session_event`` sink) are passed per-call rather than resolved via
``self.*``. The backing attributes stay initialised in — and owned by — the
dispatcher's ``__init__`` (``coordinator`` reads ``dispatcher._ledger_run_id``
and writes ``_registered_local_source_hints_loaded``; ``_restore_context``
reads ``self._checkpoint_store``), so ``AuditStore`` never holds them. The
``_setup_*`` shells write the constructed store / run id back onto ``self``;
the source-hint loaded-flag guard stays in the shell. Pure code relocation,
near-zero risk.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ...harness.artifact_registry import ArtifactRegistry
from ...harness.audit_events import (
    build_artifact_registered_event,
    build_checkpoint_written_event,
    build_recovery_decision_event,
    build_tool_called_event,
    build_tool_finished_event,
)
from ...harness.checkpoint_store import CheckpointStore
from ...harness.session_ledger import SessionLedger

# Process-level default base directory for the audit stores' *_root fallback.
# Mirrors the ``notes`` tool's ``set_notes_file`` override hook: the three
# ``build_*`` helpers fall back to ``<default_loot_root>/<store-subdir>`` only
# when no explicit ``*_root`` is passed. The default stays ``Path("loot")`` so
# production behaviour is byte-for-byte unchanged; only tests (via an autouse
# fixture) call ``set_default_loot_root`` to redirect stray, root-less store
# constructions into a tmp dir instead of the real ``loot/`` tree.
_default_loot_root: Path = Path("loot")


def set_default_loot_root(path: str | Path) -> None:
    """Override the process-level default loot base dir for store fallbacks."""
    global _default_loot_root
    _default_loot_root = Path(path)


def get_default_loot_root() -> Path:
    """Return the current process-level default loot base dir."""
    return _default_loot_root


class RuntimeAuditedActions:
    """Instrumented runtime passthroughs (browser / proxy / execute_command).

    Object-ified (L3e, cut A): the RT cluster — the three
    ``_runtime_*_action`` methods — is the most self-contained slice of
    ``AuditInfraMixin`` (each wraps one ``runtime.*`` I/O call between a
    ``tool_called`` and a ``tool_finished`` session event). It is independent
    of ``CTFTaskDispatcher`` and unit-testable fully detached. It has no
    ``__init__`` and holds **no** eager reference to ``runtime`` or the session
    event sink — those are rebound per turn / on resume by the dispatcher, so
    they are passed per-call. Behaviour is byte-for-byte identical to the
    previous inline implementation.
    """

    async def browser_action(
        self,
        action: str,
        *,
        runtime,
        record_session_event,
        audit_target: str,
        audit_metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        called_event = build_tool_called_event(
            tool_name="browser_action",
            action=action,
            target=audit_target,
            metadata=audit_metadata,
        )
        record_session_event(
            str(called_event.get("event_type") or "tool_called"),
            dict(called_event.get("payload") or {}),
        )
        result = await runtime.browser_action(action, **kwargs)
        finished_event = build_tool_finished_event(
            tool_name="browser_action",
            action=action,
            ok=isinstance(result, dict) and not bool(result.get("error")),
            status_code=result.get("status_code") if isinstance(result, dict) else None,
            target=audit_target,
            metadata=audit_metadata,
        )
        record_session_event(
            str(finished_event.get("event_type") or "tool_finished"),
            dict(finished_event.get("payload") or {}),
        )
        return result

    async def proxy_action(
        self,
        action: str,
        *,
        runtime,
        record_session_event,
        audit_target: str,
        audit_metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        called_event = build_tool_called_event(
            tool_name="proxy_action",
            action=action,
            target=audit_target,
            metadata=audit_metadata,
        )
        record_session_event(
            str(called_event.get("event_type") or "tool_called"),
            dict(called_event.get("payload") or {}),
        )
        result = await runtime.proxy_action(action, **kwargs)
        finished_event = build_tool_finished_event(
            tool_name="proxy_action",
            action=action,
            ok=isinstance(result, dict) and not bool(result.get("error")),
            status_code=result.get("status_code") if isinstance(result, dict) else None,
            target=audit_target,
            metadata=audit_metadata,
        )
        record_session_event(
            str(finished_event.get("event_type") or "tool_finished"),
            dict(finished_event.get("payload") or {}),
        )
        return result

    async def execute_command(
        self,
        command: str,
        *,
        runtime,
        record_session_event,
        timeout: int,
        audit_target: str,
        audit_metadata: dict[str, Any] | None = None,
    ) -> Any:
        called_metadata = dict(audit_metadata or {})
        called_metadata.setdefault("command", command[:240])
        called_event = build_tool_called_event(
            tool_name="execute_command",
            action="shell",
            target=audit_target,
            metadata=called_metadata,
        )
        record_session_event(
            str(called_event.get("event_type") or "tool_called"),
            dict(called_event.get("payload") or {}),
        )
        result = await runtime.execute_command(command, timeout=timeout)
        finished_metadata = dict(audit_metadata or {})
        finished_metadata.setdefault("command", command[:240])
        exit_code = getattr(result, "exit_code", None)
        finished_event = build_tool_finished_event(
            tool_name="execute_command",
            action="shell",
            ok=(exit_code is not None and int(exit_code) == 0),
            status_code=exit_code,
            target=audit_target,
            metadata=finished_metadata,
        )
        record_session_event(
            str(finished_event.get("event_type") or "tool_finished"),
            dict(finished_event.get("payload") or {}),
        )
        return result


class AuditStore:
    """Session ledger, artifact registry and checkpoint store operations.

    Object-ified (L3f-2, cut A): independent of ``CTFTaskDispatcher`` and
    unit-testable fully detached. Has no ``__init__`` and holds **no** eager
    reference to the backing store objects (``_session_ledger`` /
    ``_artifact_registry`` / ``_checkpoint_store``), their run ids, the agent
    ``state`` or the sibling ``record_session_event`` sink — those are owned by
    the dispatcher (read by ``coordinator`` / ``_restore_context``) and rebound
    each run / on resume, so they are passed per-call. The ``build_*`` setup
    helpers *return* the constructed store and resolved run id for the mixin
    shell to write back onto ``self``; the write-event helpers receive the
    store reference + run id + state + sink per call. This class only calls
    ``.append_event`` / ``.save_checkpoint`` / ``.register_artifact`` /
    ``.list_artifacts`` on the injected stores — it never mutates external
    state of its own. Behaviour is byte-for-byte identical to the previous
    inline implementation.
    """

    def build_session_ledger(
        self,
        *,
        run_id: str | None,
        ledger_root: str | Path | None,
    ) -> tuple[str, SessionLedger]:
        ledger_run_id = str(run_id or "").strip() or f"ctf-{uuid.uuid4().hex[:12]}"
        session_ledger = SessionLedger(
            ledger_root or (_default_loot_root / "session_ledgers")
        )
        return (ledger_run_id, session_ledger)

    def build_artifact_registry(
        self,
        *,
        run_id: str | None,
        fallback_run_id: str | None,
        registry_root: str | Path | None,
    ) -> tuple[str, ArtifactRegistry]:
        artifact_run_id = str(run_id or "").strip() or fallback_run_id
        if not artifact_run_id:
            artifact_run_id = f"ctf-{uuid.uuid4().hex[:12]}"
        artifact_registry = ArtifactRegistry(
            registry_root or (_default_loot_root / "artifact_registry")
        )
        return (artifact_run_id, artifact_registry)

    def build_checkpoint_store(
        self,
        *,
        run_id: str | None,
        fallback_run_id: str | None,
        checkpoint_root: str | Path | None,
    ) -> tuple[str, CheckpointStore]:
        checkpoint_run_id = str(run_id or "").strip() or fallback_run_id
        if not checkpoint_run_id:
            checkpoint_run_id = f"ctf-{uuid.uuid4().hex[:12]}"
        checkpoint_store = CheckpointStore(
            checkpoint_root or (_default_loot_root / "checkpoints")
        )
        return (checkpoint_run_id, checkpoint_store)

    def record_session_event(
        self,
        session_ledger,
        ledger_run_id: str | None,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if session_ledger is None or not ledger_run_id:
            return
        try:
            session_ledger.append_event(
                ledger_run_id,
                event_type,
                payload,
            )
        except Exception:
            pass

    def write_checkpoint(
        self,
        checkpoint_store,
        checkpoint_run_id: str | None,
        state,
        record_session_event,
        label: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if checkpoint_store is None or not checkpoint_run_id or state is None:
            return
        try:
            record = checkpoint_store.save_checkpoint(
                run_id=checkpoint_run_id,
                label=label,
                state_snapshot=state.to_snapshot(),
                metadata=metadata,
            )
            checkpoint_event = build_checkpoint_written_event(record)
            record_session_event(
                str(checkpoint_event.get("event_type") or "checkpoint_written"),
                dict(checkpoint_event.get("payload") or {}),
            )
        except Exception:
            pass

    def register_artifact_record(
        self,
        artifact_registry,
        artifact_run_id: str | None,
        record_session_event,
        *,
        kind: str,
        title: str,
        path: str | None = None,
        location: str | None = None,
        producer: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if artifact_registry is None or not artifact_run_id:
            return
        try:
            record = artifact_registry.register_artifact(
                run_id=artifact_run_id,
                kind=kind,
                title=title,
                path=path,
                location=location,
                producer=producer,
                metadata=metadata,
            )
            artifact_event = build_artifact_registered_event(record)
            record_session_event(
                str(artifact_event.get("event_type") or "artifact_registered"),
                dict(artifact_event.get("payload") or {}),
            )
        except Exception:
            pass

    def record_recovery_decision(
        self,
        record_session_event,
        decision: Any,
        *,
        chain_name: str = "",
    ) -> None:
        recovery_event = build_recovery_decision_event(decision, chain_name=chain_name)
        record_session_event(
            str(recovery_event.get("event_type") or "recovery_decision"),
            dict(recovery_event.get("payload") or {}),
        )

    def resolve_registered_local_challenge_paths(
        self,
        artifact_registry,
        artifact_run_id: str | None,
    ) -> tuple[Path | None, Path | None]:
        if artifact_registry is None or not artifact_run_id:
            return (None, None)
        try:
            records = artifact_registry.list_artifacts(artifact_run_id)
        except Exception:
            return (None, None)

        challenge_root: Path | None = None
        compose_file: Path | None = None
        for record in reversed(records):
            if not isinstance(record, dict):
                continue
            kind = str(record.get("kind") or "").strip()
            raw_path = str(record.get("path") or record.get("location") or "").strip()
            if not raw_path:
                continue
            candidate = Path(raw_path)
            if compose_file is None and kind == "local_challenge_compose_file" and candidate.is_file():
                compose_file = candidate
            if (
                challenge_root is None
                and kind in {"local_challenge_extracted_root", "local_challenge_root"}
                and candidate.is_dir()
            ):
                challenge_root = candidate
            if challenge_root is not None and compose_file is not None:
                break

        if challenge_root is None and compose_file is not None:
            challenge_root = compose_file.parent
        return (challenge_root, compose_file)

    def resolve_registered_local_key_files(
        self,
        artifact_registry,
        artifact_run_id: str | None,
    ) -> list[Path]:
        if artifact_registry is None or not artifact_run_id:
            return []
        try:
            records = artifact_registry.list_artifacts(artifact_run_id)
        except Exception:
            return []

        seen: set[str] = set()
        files: list[Path] = []
        for record in reversed(records):
            if not isinstance(record, dict):
                continue
            if str(record.get("kind") or "").strip() != "local_challenge_key_file":
                continue
            raw_path = str(record.get("path") or record.get("location") or "").strip()
            if not raw_path or raw_path in seen:
                continue
            candidate = Path(raw_path)
            if not candidate.exists() or not candidate.is_file():
                continue
            seen.add(raw_path)
            files.append(candidate)
        files.reverse()
        return files

    def ingest_registered_local_source_hints(
        self,
        state,
        resolve_registered_local_key_files,
        *,
        max_files: int = 3,
        max_chars: int = 400,
    ) -> None:
        for path in resolve_registered_local_key_files()[:max_files]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            snippet = str(content or "").strip()
            if not snippet:
                continue
            if len(snippet) > max_chars:
                snippet = snippet[: max_chars - 3].rstrip() + "..."
            state.add_observation(
                "local_challenge_source_hint",
                f"{path.name}: {snippet}",
                source="local_challenge_context",
                metadata={
                    "path": str(path),
                    "file_name": path.name,
                },
            )


class AuditInfraMixin:
    """Session ledger, artifact registry, checkpoint store and audited runtime calls."""

    def _setup_session_ledger(
        self,
        *,
        run_id: str | None,
        ledger_root: str | Path | None,
    ) -> None:
        self._ledger_run_id, self._session_ledger = self._audit_store.build_session_ledger(
            run_id=run_id,
            ledger_root=ledger_root,
        )

    def _setup_artifact_registry(
        self,
        *,
        run_id: str | None,
        registry_root: str | Path | None,
    ) -> None:
        self._artifact_run_id, self._artifact_registry = self._audit_store.build_artifact_registry(
            run_id=run_id,
            fallback_run_id=self._ledger_run_id,
            registry_root=registry_root,
        )

    def _setup_checkpoint_store(
        self,
        *,
        run_id: str | None,
        checkpoint_root: str | Path | None,
    ) -> None:
        self._checkpoint_run_id, self._checkpoint_store = self._audit_store.build_checkpoint_store(
            run_id=run_id,
            fallback_run_id=self._ledger_run_id,
            checkpoint_root=checkpoint_root,
        )

    def _record_session_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._audit_store.record_session_event(
            self._session_ledger,
            self._ledger_run_id,
            event_type,
            payload,
        )

    def _write_checkpoint(
        self,
        label: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._audit_store.write_checkpoint(
            self._checkpoint_store,
            self._checkpoint_run_id,
            self.state,
            self._record_session_event,
            label,
            metadata,
        )

    def _register_artifact_record(
        self,
        *,
        kind: str,
        title: str,
        path: str | None = None,
        location: str | None = None,
        producer: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._audit_store.register_artifact_record(
            self._artifact_registry,
            self._artifact_run_id,
            self._record_session_event,
            kind=kind,
            title=title,
            path=path,
            location=location,
            producer=producer,
            metadata=metadata,
        )

    def _record_recovery_decision(self, decision: Any, *, chain_name: str = "") -> None:
        self._audit_store.record_recovery_decision(
            self._record_session_event,
            decision,
            chain_name=chain_name,
        )

    def _resolve_registered_local_challenge_paths(self) -> tuple[Path | None, Path | None]:
        return self._audit_store.resolve_registered_local_challenge_paths(
            self._artifact_registry,
            self._artifact_run_id,
        )

    def _resolve_registered_local_key_files(self) -> list[Path]:
        return self._audit_store.resolve_registered_local_key_files(
            self._artifact_registry,
            self._artifact_run_id,
        )

    def _ingest_registered_local_source_hints(self, *, max_files: int = 3, max_chars: int = 400) -> None:
        if self.state is None:
            return
        if self._registered_local_source_hints_loaded:
            return
        self._audit_store.ingest_registered_local_source_hints(
            self.state,
            self._resolve_registered_local_key_files,
            max_files=max_files,
            max_chars=max_chars,
        )
        self._registered_local_source_hints_loaded = True

    async def _runtime_browser_action(
        self,
        action: str,
        *,
        audit_target: str,
        audit_metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return await self._runtime_actions.browser_action(
            action,
            runtime=self.runtime,
            record_session_event=self._record_session_event,
            audit_target=audit_target,
            audit_metadata=audit_metadata,
            **kwargs,
        )

    async def _runtime_proxy_action(
        self,
        action: str,
        *,
        audit_target: str,
        audit_metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return await self._runtime_actions.proxy_action(
            action,
            runtime=self.runtime,
            record_session_event=self._record_session_event,
            audit_target=audit_target,
            audit_metadata=audit_metadata,
            **kwargs,
        )

    async def _runtime_execute_command(
        self,
        command: str,
        *,
        timeout: int,
        audit_target: str,
        audit_metadata: dict[str, Any] | None = None,
    ) -> Any:
        return await self._runtime_actions.execute_command(
            command,
            runtime=self.runtime,
            record_session_event=self._record_session_event,
            timeout=timeout,
            audit_target=audit_target,
            audit_metadata=audit_metadata,
        )
