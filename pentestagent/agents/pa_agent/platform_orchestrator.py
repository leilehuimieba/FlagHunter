"""Platform-aware challenge queue orchestration for /ctf workflows."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class PlatformTask:
    challenge_id: str
    name: str
    category: str
    solved: bool
    status: str
    url: str
    points: int = 0
    solve_count: int = 0
    priority_score: float = 0.0
    priority_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PlatformQueueSnapshot:
    platform_type: str
    base_url: str
    generated_at: float
    total: int
    solved_count: int
    unsolved_count: int
    rate_limited_until: float = 0.0
    next_challenge_id: str | None = None
    next_challenge_name: str | None = None
    next_challenge_url: str | None = None
    tasks: list[PlatformTask] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tasks"] = [task.to_dict() for task in self.tasks]
        return data


class PlatformTaskOrchestrator:
    def build_queue_snapshot(
        self,
        *,
        platform_type: str,
        base_url: str,
        challenge_briefs: list[dict[str, Any]],
        current_challenge_id: str | None = None,
        submit_attempts: list[dict[str, Any]] | None = None,
        rate_limited_until: float = 0.0,
    ) -> PlatformQueueSnapshot:
        tasks: list[PlatformTask] = []
        attempts = list(submit_attempts or [])
        rejected_ids = {
            str(item.get("challenge_id") or "").strip()
            for item in attempts
            if item.get("correct") is False and str(item.get("challenge_id") or "").strip()
        }
        current_id = str(current_challenge_id or "").strip()

        for item in challenge_briefs:
            raw = dict(item or {})
            challenge_id = str(raw.get("id") or "").strip()
            name = str(raw.get("name") or "").strip()
            category = str(raw.get("category") or "").strip()
            solved = bool(raw.get("solved"))
            status = str(raw.get("status") or "").strip()
            url = str(raw.get("url") or "").strip()
            points = _safe_int(raw.get("points") or raw.get("value") or raw.get("score"))
            solve_count = _safe_int(raw.get("solve_count") or raw.get("solves"))

            score = 0.0
            reasons: list[str] = []
            if not solved:
                score += 1000.0
                reasons.append("unsolved")
            else:
                reasons.append("solved")
            score += min(points, 500)
            if points:
                reasons.append(f"points={points}")
            score -= min(solve_count, 200) * 0.25
            if solve_count:
                reasons.append(f"solve_count={solve_count}")
            if current_id and challenge_id == current_id:
                score += 60.0
                reasons.append("current")
            if challenge_id and challenge_id in rejected_ids:
                score -= 200.0
                reasons.append("recent_rejected")
            if url:
                score += 5.0
                reasons.append("has_url")

            tasks.append(
                PlatformTask(
                    challenge_id=challenge_id,
                    name=name,
                    category=category,
                    solved=solved,
                    status=status,
                    url=url,
                    points=points,
                    solve_count=solve_count,
                    priority_score=round(score, 3),
                    priority_reason=", ".join(reasons),
                )
            )

        tasks.sort(
            key=lambda item: (
                item.solved,
                -item.priority_score,
                item.solve_count,
                item.name.lower(),
            )
        )

        next_task = next((item for item in tasks if not item.solved), None)
        solved_count = sum(1 for item in tasks if item.solved)
        snapshot = PlatformQueueSnapshot(
            platform_type=str(platform_type or "manual"),
            base_url=str(base_url or ""),
            generated_at=time.time(),
            total=len(tasks),
            solved_count=solved_count,
            unsolved_count=max(0, len(tasks) - solved_count),
            rate_limited_until=float(rate_limited_until or 0.0),
            next_challenge_id=next_task.challenge_id if next_task else None,
            next_challenge_name=next_task.name if next_task else None,
            next_challenge_url=next_task.url if next_task else None,
            tasks=tasks,
        )
        return snapshot

    def select_next_task(
        self,
        snapshot: PlatformQueueSnapshot | dict[str, Any],
        *,
        current_challenge_id: str | None,
        visited_keys: set[str] | None,
    ) -> dict[str, Any]:
        current_id = str(current_challenge_id or "").strip()
        seen = set(visited_keys or set())
        skipped_candidates: list[dict[str, Any]] = []

        raw_tasks = snapshot.tasks if isinstance(snapshot, PlatformQueueSnapshot) else list(snapshot.get("tasks") or [])
        normalized_tasks = [
            task.to_dict() if isinstance(task, PlatformTask) else dict(task or {})
            for task in raw_tasks
        ]

        for task in normalized_tasks:
            challenge_id = str(task.get("challenge_id") or task.get("id") or "").strip()
            task_url = str(task.get("url") or "").strip()
            visit_key = f"{challenge_id}|{task_url}"
            skip_reason = ""
            if bool(task.get("solved")):
                skip_reason = "solved"
            elif current_id and challenge_id == current_id:
                skip_reason = "current_challenge"
            elif visit_key in seen:
                skip_reason = "visited"
            elif not challenge_id and not task_url:
                skip_reason = "missing_locator"

            if skip_reason:
                skipped_candidates.append(
                    {
                        "challenge_id": challenge_id,
                        "name": str(task.get("name") or "").strip(),
                        "url": task_url,
                        "skip_reason": skip_reason,
                    }
                )
                continue

            return {
                "task": task,
                "switch_reason": "next_unsolved_highest_priority",
                "switch_source": "platform_queue",
                "skipped_candidates": skipped_candidates,
            }

        return {
            "task": None,
            "switch_reason": "",
            "switch_source": "platform_queue",
            "skipped_candidates": skipped_candidates,
            "blocked_reason": "queue_exhausted",
        }

    def assess_submit_rate_limit(
        self,
        submit_attempts: list[dict[str, Any]] | None,
        *,
        now: float | None = None,
        window_seconds: float = 30.0,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        attempts = []
        for item in list(submit_attempts or []):
            if not isinstance(item, dict):
                continue
            if item.get("type") != "flag_submit_attempt":
                continue
            created_at = float(item.get("created_at") or 0.0)
            if created_at <= 0:
                continue
            if current - created_at <= window_seconds:
                attempts.append(item)

        if len(attempts) < max_attempts:
            return {
                "throttled": False,
                "attempt_count": len(attempts),
                "rate_limited_until": 0.0,
                "reason": "",
            }

        latest = max(float(item.get("created_at") or 0.0) for item in attempts)
        limited_until = latest + window_seconds
        return {
            "throttled": True,
            "attempt_count": len(attempts),
            "rate_limited_until": limited_until,
            "reason": f"submit attempts exceeded {max_attempts} within {int(window_seconds)}s",
        }


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


__all__ = [
    "PlatformQueueSnapshot",
    "PlatformTask",
    "PlatformTaskOrchestrator",
]
