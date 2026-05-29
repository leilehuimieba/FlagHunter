from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ArtifactRegistry:
    """Append-only JSONL artifact registry keyed by run_id."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for_run(self, run_id: str) -> Path:
        normalized = re.sub(r"[^\w.-]", "_", str(run_id or "").strip()) or "run"
        return self.root / f"{normalized}.jsonl"

    def register_artifact(
        self,
        *,
        run_id: str,
        kind: str,
        title: str,
        path: str | None = None,
        location: str | None = None,
        producer: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "artifact_id": f"artifact-{uuid.uuid4().hex[:12]}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": str(run_id or "").strip(),
            "kind": str(kind or "").strip(),
            "title": str(title or "").strip(),
            "path": str(path).strip() if path is not None and str(path).strip() else None,
            "location": (
                str(location).strip()
                if location is not None and str(location).strip()
                else None
            ),
            "producer": str(producer or "").strip(),
            "metadata": dict(metadata or {}),
        }
        target = self.path_for_run(run_id)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        target = self.path_for_run(run_id)
        if not target.exists():
            return []
        records: list[dict[str, Any]] = []
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
        return records

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        normalized = str(artifact_id or "").strip()
        if not normalized:
            return None
        for candidate in sorted(self.root.glob("*.jsonl")):
            with candidate.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if str(record.get("artifact_id") or "").strip() == normalized:
                        return record
        return None
