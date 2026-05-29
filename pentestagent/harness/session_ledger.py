from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionLedger:
    """Append-only JSONL ledger keyed by run_id."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for_run(self, run_id: str) -> Path:
        normalized = re.sub(r"[^\w.-]", "_", str(run_id or "").strip()) or "run"
        return self.root / f"{normalized}.jsonl"

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": str(run_id or "").strip(),
            "event_type": str(event_type or "").strip(),
            "payload": dict(payload or {}),
        }
        path = self.path_for_run(run_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def read_events(self, run_id: str) -> list[dict[str, Any]]:
        path = self.path_for_run(run_id)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                events.append(json.loads(line))
        return events

    def tail_events(self, run_id: str, limit: int = 20) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return self.read_events(run_id)[-limit:]
