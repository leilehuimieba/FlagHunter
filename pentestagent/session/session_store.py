"""Full-session persistence: conversation + plan + findings + runtime state.

Saves agent state snapshots as JSON files under loot/sessions/.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent


@dataclass
class SessionSnapshot:
    session_id: str
    created_at: str
    updated_at: str
    target: str
    conversation: list[dict[str, Any]] = field(default_factory=list)
    plan: dict[str, Any] = field(default_factory=dict)
    findings: dict[str, Any] = field(default_factory=dict)
    permission_mode: int = 99
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "target": self.target,
            "conversation": self.conversation,
            "plan": self.plan,
            "findings": self.findings,
            "permission_mode": self.permission_mode,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionSnapshot:
        return cls(
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            target=data.get("target", ""),
            conversation=data.get("conversation", []),
            plan=data.get("plan", {}),
            findings=data.get("findings", {}),
            permission_mode=data.get("permission_mode", 99),
            metadata=data.get("metadata", {}),
        )


_DEFAULT_SESSIONS_DIR = Path("loot") / "sessions"
_MAX_SESSIONS = 20


class SessionStore:
    """Full session persistence: conversation + plan + findings + state."""

    def __init__(self, base_path: Path | None = None):
        self._base = Path(base_path) if base_path else _DEFAULT_SESSIONS_DIR
        self._base.mkdir(parents=True, exist_ok=True)

    def save(self, agent: BaseAgent, session_id: str | None = None) -> str:
        """Snapshot entire agent state to disk. Returns session_id."""
        now = datetime.now(timezone.utc).isoformat()

        if session_id is None:
            session_id = uuid.uuid4().hex[:12]

        # Serialize conversation
        conversation = [msg.to_dict() for msg in agent.conversation_history]

        # Serialize plan
        plan_data: dict[str, Any] = {}
        if hasattr(agent, "_task_plan") and agent._task_plan is not None:
            plan_data = {
                "original_request": agent._task_plan.original_request,
                "steps": [s.to_dict() for s in agent._task_plan.steps],
            }

        # Snapshot findings (notes)
        findings: dict[str, Any] = {}
        try:
            from ..tools.notes import get_all_notes_sync
            findings = get_all_notes_sync()
        except Exception:
            pass

        # Resolve target
        target = getattr(agent, "target", "") or ""
        if isinstance(target, list):
            target = ", ".join(str(t) for t in target)

        snapshot = SessionSnapshot(
            session_id=session_id,
            created_at=now,
            updated_at=now,
            target=target,
            conversation=conversation,
            plan=plan_data,
            findings=findings,
            permission_mode=agent.permission_enforcer.mode.value,
            metadata={
                "max_iterations": agent.max_iterations,
                "message_count": len(agent.conversation_history),
            },
        )

        session_path = self._base / f"{session_id}.json"
        session_path.write_text(
            json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        self._update_index(session_id, target, now, len(conversation))
        self._prune()
        return session_id

    def load(self, session_id: str) -> SessionSnapshot | None:
        """Load a saved session. Returns None if not found."""
        session_path = self._base / f"{session_id}.json"
        if not session_path.exists():
            return None
        try:
            data = json.loads(session_path.read_text(encoding="utf-8"))
            return SessionSnapshot.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return list of saved sessions (newest first)."""
        index_path = self._base / "index.json"
        if not index_path.exists():
            return []
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8"))
            entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
            return entries
        except (json.JSONDecodeError, OSError):
            return []

    def resume(self, agent: BaseAgent, session_id: str) -> bool:
        """Restore conversation history and plan into agent. Returns success."""
        snapshot = self.load(session_id)
        if snapshot is None:
            return False

        from ..agents.base_agent import AgentMessage

        agent.conversation_history = [
            AgentMessage.from_dict(m) for m in snapshot.conversation
        ]

        if snapshot.plan and snapshot.plan.get("steps"):
            from ..tools.finish import PlanStep

            agent._task_plan.original_request = snapshot.plan.get("original_request", "")
            agent._task_plan.steps = [
                PlanStep.from_dict(s)
                for s in snapshot.plan.get("steps", [])
            ]

        return True

    def _update_index(self, session_id: str, target: str, created_at: str, message_count: int) -> None:
        index_path = self._base / "index.json"
        entries: list[dict[str, Any]] = []
        if index_path.exists():
            try:
                entries = json.loads(index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        existing = next((i for i, e in enumerate(entries) if e.get("id") == session_id), None)
        entry = {
            "id": session_id,
            "target": target,
            "created_at": created_at,
            "message_count": message_count,
        }
        if existing is not None:
            entries[existing] = entry
        else:
            entries.insert(0, entry)

        index_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def _prune(self) -> None:
        entries = self.list_sessions()
        if len(entries) <= _MAX_SESSIONS:
            return
        for entry in entries[_MAX_SESSIONS:]:
            sid = entry.get("id", "")
            if sid:
                p = self._base / f"{sid}.json"
                if p.exists():
                    p.unlink()
