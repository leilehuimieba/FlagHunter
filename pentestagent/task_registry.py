"""Task registry for batch pentest/CTF operations.

Provides JSON-backed task tracking: create tasks, update status, record
sub-agent results and findings. Persisted to loot/tasks.json.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class TaskStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class Task:
    task_id: str
    description: str
    status: TaskStatus = TaskStatus.CREATED
    sub_tasks: list[str] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    target: str = ""
    created_at: str = ""
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "status": self.status.value,
            "sub_tasks": self.sub_tasks,
            "findings": self.findings,
            "target": self.target,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        return cls(
            task_id=data.get("task_id", ""),
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "created")),
            sub_tasks=data.get("sub_tasks", []),
            findings=data.get("findings", []),
            target=data.get("target", ""),
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at"),
        )


_DEFAULT_PATH = Path("loot") / "tasks.json"


class TaskRegistry:
    """JSON-backed task registry for batch pentest/CTF operations."""

    def __init__(self, base_path: Path | None = None):
        self._path = Path(base_path) if base_path else _DEFAULT_PATH
        self._tasks: dict[str, Task] = {}
        self._load()

    def create_task(self, description: str, target: str = "") -> Task:
        task = Task(
            task_id=uuid.uuid4().hex[:12],
            description=description,
            target=target,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._tasks[task.task_id] = task
        self._persist()
        return task

    def update_status(self, task_id: str, status: TaskStatus) -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.status = status
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED):
            task.completed_at = datetime.now(timezone.utc).isoformat()
        self._persist()
        return True

    def add_subtask(self, task_id: str, subtask_summary: str) -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.sub_tasks.append(subtask_summary)
        self._persist()
        return True

    def add_finding(self, task_id: str, finding: dict[str, Any]) -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            return False
        finding["recorded_at"] = datetime.now(timezone.utc).isoformat()
        task.findings.append(finding)
        self._persist()
        return True

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "tasks": [t.to_dict() for t in self._tasks.values()],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for item in data.get("tasks", []):
                task = Task.from_dict(item)
                self._tasks[task.task_id] = task
        except (json.JSONDecodeError, OSError):
            pass
