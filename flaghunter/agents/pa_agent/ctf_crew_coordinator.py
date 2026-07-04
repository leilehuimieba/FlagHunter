"""Phase 7 CTFCrewCoordinator skeleton.

最小目标：
- 多 worker 共享同一个 CTFState
- worker 结果由 coordinator 统一合并
- 任一 worker 命中 verified flag 后，其他 worker 收到 cancel 信号
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal
from urllib.parse import urlparse

from ...knowledge.graph import ShadowGraph
from .claim_views import preferred_flag_summary
from .ctf_state import CTFState


WorkerType = Literal["recon", "exploit", "llm_explorer", "verifier"]
WorkerRunner = Callable[[dict[str, Any], CTFState, asyncio.Event], Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class CrewWorkerSpec:
    worker_id: str
    worker_type: WorkerType
    task: str
    target_filter: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "worker_type": self.worker_type,
            "task": self.task,
            "target_filter": self.target_filter,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class CrewRunSummary:
    started_workers: list[str] = field(default_factory=list)
    completed_workers: list[str] = field(default_factory=list)
    cancelled_workers: list[str] = field(default_factory=list)
    worker_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    verified_flag: str | None = None
    stop_reason: str = ""
    flag_summary: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_workers": list(self.started_workers),
            "completed_workers": list(self.completed_workers),
            "cancelled_workers": list(self.cancelled_workers),
            "worker_results": dict(self.worker_results),
            "verified_flag": self.verified_flag,
            "stop_reason": self.stop_reason,
            "flag_summary": {
                key: list(value)
                for key, value in dict(self.flag_summary or {}).items()
            },
        }


class CTFCrewCoordinator:
    """Minimal coordinator for Phase 7 B2.

    当前版本不重写现有 dispatcher，只提供：
    - 共享状态
    - 并发 worker 启动 / 收敛
    - verified 终止广播
    """

    def __init__(
        self,
        *,
        state: CTFState,
        verifier: Any,
        provider_manager: Any = None,
        shadow_graph: Any = None,
        worker_runner: WorkerRunner | None = None,
        progress_callback: Callable[[str], None] | None = None,
        timeout_seconds: int = 600,
    ) -> None:
        self.state = state
        self.verifier = verifier
        self.provider_manager = provider_manager
        self.shadow_graph = shadow_graph or ShadowGraph()
        self.worker_runner = worker_runner or self._default_worker_runner
        self.progress_callback = progress_callback
        self.timeout_seconds = max(0.001, float(timeout_seconds))
        self._cancel_event = asyncio.Event()
        self._next_worker_index = 0
        self._active_tasks: dict[str, asyncio.Task] = {}

    def build_worker_specs(
        self,
        *,
        target: str,
        page_features: dict[str, Any] | None = None,
    ) -> list[CrewWorkerSpec]:
        specs: list[CrewWorkerSpec] = []
        specs.extend(self._plan_recon_workers(target=target, page_features=page_features or {}))
        specs.extend(self._plan_exploit_workers())
        if not specs:
            specs.append(
                CrewWorkerSpec(
                    worker_id=self._allocate_worker_id("llm"),
                    worker_type="llm_explorer",
                    task=f"Explore unknown web surface for {target}",
                    metadata={"planned_by": "fallback"},
                )
            )
        return specs

    async def run_with_shadow_graph(
        self,
        *,
        target: str,
        page_features: dict[str, Any] | None = None,
    ) -> CrewRunSummary:
        """Run recon first, then let ShadowGraph shape the follow-up wave."""
        initial_specs = self.build_worker_specs(target=target, page_features=page_features or {})
        recon_specs = [item for item in initial_specs if item.worker_type == "recon"]
        non_recon_specs = [item for item in initial_specs if item.worker_type != "recon"]
        if not recon_specs:
            return await self.run(initial_specs)

        first_round = await self.run(recon_specs)
        if first_round.verified_flag:
            return first_round

        followup_specs = self.build_shadow_graph_followup_specs(
            target=target,
            page_features=page_features or {},
            base_specs=non_recon_specs,
        )
        if not followup_specs:
            return first_round

        self._emit(
            "[CTF crew] shadow-graph follow-up: "
            + ", ".join(
                f"{item.worker_id}:{item.metadata.get('planned_by', item.worker_type)}"
                for item in followup_specs
            )
        )
        second_round = await self.run(followup_specs)
        return self._merge_round_summaries(first_round, second_round)

    async def run(self, specs: list[CrewWorkerSpec]) -> CrewRunSummary:
        summary = CrewRunSummary()
        if not specs:
            summary.stop_reason = "no_worker_specs"
            return summary

        tasks: dict[str, asyncio.Task] = {}
        self._cancel_event = asyncio.Event()
        deadline = time.monotonic() + self.timeout_seconds
        for spec in specs:
            summary.started_workers.append(spec.worker_id)
            self._emit(f"[CTF crew] start {spec.worker_id} ({spec.worker_type})")
            tasks[spec.worker_id] = asyncio.create_task(self._run_one(spec))
        self._active_tasks = dict(tasks)

        try:
            pending = set(tasks.values())
            while pending:
                remaining_timeout = max(0.0, deadline - time.monotonic())
                done, pending = await asyncio.wait(
                    pending,
                    timeout=remaining_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    self._cancel_event.set()
                    for task in pending:
                        task.cancel()
                    summary.cancelled_workers.extend(
                        worker_id
                        for worker_id, task in tasks.items()
                        if task in pending
                    )
                    summary.stop_reason = "crew_timeout"
                    break

                for task in done:
                    worker_id = next(
                        (candidate_id for candidate_id, candidate_task in tasks.items() if candidate_task is task),
                        "unknown-worker",
                    )
                    try:
                        worker_id, result = await task
                    except asyncio.CancelledError:
                        if worker_id not in summary.cancelled_workers:
                            summary.cancelled_workers.append(worker_id)
                        continue
                    except Exception as exc:
                        summary.completed_workers.append(worker_id)
                        summary.worker_results[worker_id] = {
                            "error": str(exc),
                            "verified_flag": None,
                        }
                        if not summary.stop_reason:
                            summary.stop_reason = f"worker_error:{worker_id}"
                        continue
                    summary.completed_workers.append(worker_id)
                    summary.worker_results[worker_id] = dict(result)
                    if result.get("verified_flag"):
                        summary.verified_flag = str(result.get("verified_flag") or "").strip() or None
                        summary.stop_reason = "flag_verified"
                        self._cancel_event.set()
                        for other_id, other_task in tasks.items():
                            if other_task.done():
                                continue
                            other_task.cancel()
                            summary.cancelled_workers.append(other_id)
                        pending = set()
                        break
                    self._refresh_summary_flags(summary)
                    if summary.verified_flag:
                        summary.stop_reason = "flag_verified"
                        self._cancel_event.set()
                        for other_id, other_task in tasks.items():
                            if other_task.done():
                                continue
                            other_task.cancel()
                            summary.cancelled_workers.append(other_id)
                        pending = set()
                        break
            if not summary.stop_reason:
                summary.stop_reason = "workers_completed"
            self._refresh_summary_flags(summary)
            return summary
        finally:
            self._cancel_event.set()
            if tasks:
                await asyncio.gather(*tasks.values(), return_exceptions=True)
            self._active_tasks = {}

    async def cancel(self) -> None:
        self._cancel_event.set()
        for task in list(self._active_tasks.values()):
            if not task.done():
                task.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)

    async def _run_one(self, spec: CrewWorkerSpec) -> tuple[str, dict[str, Any]]:
        if self._cancel_event.is_set():
            return spec.worker_id, {"cancelled": True, "worker_type": spec.worker_type}

        payload = spec.to_dict()
        payload["started_at"] = time.time()
        result = await self.worker_runner(payload, self.state, self._cancel_event)
        result = dict(result or {})
        await self._merge_result(spec, result)
        return spec.worker_id, result

    async def _merge_result(self, spec: CrewWorkerSpec, result: dict[str, Any]) -> None:
        async with self.state.write_lock():
            for item in list(result.get("observations") or []):
                if not isinstance(item, dict):
                    continue
                self.state.add_observation(
                    str(item.get("kind") or "crew_observation"),
                    str(item.get("value") or ""),
                    source=str(item.get("source") or spec.worker_type),
                    metadata=dict(item.get("metadata") or {}),
                )

            for flag in list(result.get("candidate_flags") or []):
                normalized = self._extract_flag_value(flag)
                if not normalized:
                    continue
                existing = next(
                    (record for record in self.state.candidate_flags if record.value == normalized),
                    None,
                )
                confidence = 0.5
                metadata = {"worker_id": spec.worker_id}
                if existing is not None:
                    confidence = min(1.0, float(existing.confidence or 0.5) + 0.15)
                    worker_ids = list(existing.metadata.get("corroborated_worker_ids") or [])
                    if spec.worker_id not in worker_ids:
                        worker_ids.append(spec.worker_id)
                    metadata["corroborated_worker_ids"] = worker_ids
                    metadata["corroboration_count"] = len(worker_ids)
                else:
                    metadata["corroborated_worker_ids"] = [spec.worker_id]
                    metadata["corroboration_count"] = 1
                self.state.add_flag(
                    normalized,
                    level="candidate",
                    evidence_source=f"crew-{spec.worker_type}",
                    rationale=f"candidate reported by worker {spec.worker_id}",
                    confidence=confidence,
                    requires_followup=True,
                    metadata=metadata,
                )

        runtime_flags = list(result.get("runtime_flags") or [])
        if not runtime_flags:
            runtime_flags = list((result.get("state_diff") or {}).get("runtime_flags") or [])
        for runtime_flag in runtime_flags:
            normalized_runtime = self._extract_flag_value(runtime_flag)
            if not normalized_runtime:
                continue
            await self.verifier.verify_flag(
                self.state,
                flag=normalized_runtime,
                evidence_source="runtime-output",
                rationale=f"runtime candidate reported by worker {spec.worker_id}",
            )

        verified_flag = str(result.get("verified_flag") or "").strip()
        if verified_flag:
            verification = await self.verifier.verify_flag(
                self.state,
                flag=verified_flag,
                evidence_source=f"crew-{spec.worker_type}",
                rationale=f"verified candidate from worker {spec.worker_id}",
            )
            if verification.decision == "verified":
                result["verified_flag"] = verification.flag
            else:
                result["verified_flag"] = None

    def _refresh_summary_flags(self, summary: CrewRunSummary) -> None:
        flag_summary = preferred_flag_summary(self.state)
        summary.flag_summary = {
            key: list(value)
            for key, value in flag_summary.items()
        }
        verified = [
            str(item).strip()
            for item in list(flag_summary.get("verifiedFlags") or [])
            if str(item).strip()
        ]
        if verified and not summary.verified_flag:
            summary.verified_flag = verified[0]

    async def _default_worker_runner(
        self,
        spec: dict[str, Any],
        state: CTFState,
        cancel_event: asyncio.Event,
    ) -> dict[str, Any]:
        return {
            "worker_id": spec.get("worker_id"),
            "worker_type": spec.get("worker_type"),
            "cancelled": cancel_event.is_set(),
            "observations": [],
            "candidate_flags": [],
            "verified_flag": None,
        }

    def _plan_recon_workers(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
    ) -> list[CrewWorkerSpec]:
        endpoints = [
            str(item or "").strip()
            for item in list(page_features.get("endpoints") or [])
            if str(item or "").strip()
        ]
        if len(endpoints) < 10:
            return []

        prefix_groups: dict[str, list[str]] = {}
        for endpoint in endpoints:
            prefix = self._endpoint_prefix(endpoint)
            prefix_groups.setdefault(prefix, []).append(endpoint)

        ranked_groups = sorted(
            prefix_groups.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
        top_groups = [item for item in ranked_groups if item[0] != "/"][:2]
        if len(top_groups) < 2:
            return []

        specs: list[CrewWorkerSpec] = []
        for prefix, group_endpoints in top_groups:
            specs.append(
                CrewWorkerSpec(
                    worker_id=self._allocate_worker_id("recon"),
                    worker_type="recon",
                    task=f"Recon namespace {prefix} on {target}",
                    target_filter=prefix,
                    metadata={
                        "planned_by": "endpoint_prefix",
                        "endpoint_prefix": prefix,
                        "endpoint_count": len(group_endpoints),
                        "sample_endpoints": group_endpoints[:5],
                    },
                )
            )
        return specs

    def _plan_exploit_workers(self) -> list[CrewWorkerSpec]:
        hypotheses = [
            item
            for item in list(self.state.hypotheses or [])
            if getattr(item, "status", "active") in {"active", "supported"}
            and float(getattr(item, "confidence", 0.0) or 0.0) >= 0.4
        ]
        if len(hypotheses) < 2:
            return []

        ranked = sorted(
            hypotheses,
            key=lambda item: (-float(getattr(item, "confidence", 0.0) or 0.0), item.kind),
        )
        selected: list[Any] = []
        seen_conflict_keys: set[str] = set()
        for hypothesis in ranked:
            conflict_key = self._hypothesis_conflict_key(hypothesis.kind)
            if conflict_key in seen_conflict_keys:
                continue
            seen_conflict_keys.add(conflict_key)
            selected.append(hypothesis)
            if len(selected) >= 3:
                break

        if len(selected) < 2:
            return []

        specs: list[CrewWorkerSpec] = []
        for hypothesis in selected:
            specs.append(
                CrewWorkerSpec(
                    worker_id=self._allocate_worker_id("exploit"),
                    worker_type="exploit",
                    task=f"Exploit hypothesis {hypothesis.kind}",
                    metadata={
                        "planned_by": "hypothesis_confidence",
                        "hypothesis_kind": hypothesis.kind,
                        "hypothesis_confidence": hypothesis.confidence,
                        "supporting_observations": list(hypothesis.supporting_observations),
                    },
                )
            )
        return specs

    def build_shadow_graph_followup_specs(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
        base_specs: list[CrewWorkerSpec] | None = None,
    ) -> list[CrewWorkerSpec]:
        recommendations = self._shadow_graph_recommendations(
            target=target,
            page_features=page_features,
        )
        specs: list[CrewWorkerSpec] = []
        seen_filters: set[str] = set()
        seen_hypotheses: set[str] = set()

        for rec in recommendations[:2]:
            target_filter = str(rec.get("target_filter") or "").strip()
            if target_filter and target_filter in seen_filters:
                continue
            if target_filter:
                seen_filters.add(target_filter)
            specs.append(
                CrewWorkerSpec(
                    worker_id=self._allocate_worker_id("shadow"),
                    worker_type=str(rec.get("worker_type") or "llm_explorer"),
                    task=str(rec.get("task") or f"Follow ShadowGraph insight on {target}"),
                    target_filter=target_filter,
                    metadata=dict(rec.get("metadata") or {}),
                )
            )

        for spec in list(base_specs or []):
            hypothesis_kind = str(spec.metadata.get("hypothesis_kind") or "").strip()
            if hypothesis_kind:
                if hypothesis_kind in seen_hypotheses:
                    continue
                seen_hypotheses.add(hypothesis_kind)
            if spec.target_filter and spec.target_filter in seen_filters:
                continue
            specs.append(spec)
            if len(specs) >= 3:
                break

        if not specs:
            specs.append(
                CrewWorkerSpec(
                    worker_id=self._allocate_worker_id("llm"),
                    worker_type="llm_explorer",
                    task=f"ShadowGraph-guided free exploration for {target}",
                    metadata={"planned_by": "shadow_graph_fallback"},
                )
            )
        return specs

    @staticmethod
    def _endpoint_prefix(endpoint: str) -> str:
        parsed = urlparse(endpoint)
        path = str(parsed.path or endpoint or "").strip() or "/"
        if not path.startswith("/"):
            path = "/" + path
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            return "/"
        if len(segments) >= 2 and segments[0] == "api":
            return "/" + "/".join(segments[:2])
        return "/" + segments[0]

    @staticmethod
    def _hypothesis_conflict_key(kind: str) -> str:
        normalized = str(kind or "").strip().lower()
        if any(token in normalized for token in ("sqli", "sql")):
            return "sqli"
        if "xss" in normalized:
            return "xss"
        if "backup" in normalized or "source" in normalized:
            return "backup_source"
        if "upload" in normalized:
            return "upload"
        if "lfi" in normalized or "path_traversal" in normalized:
            return "file_read"
        return normalized

    def _allocate_worker_id(self, prefix: str) -> str:
        worker_id = f"{prefix}-{self._next_worker_index}"
        self._next_worker_index += 1
        return worker_id

    @staticmethod
    def _extract_flag_value(flag: Any) -> str:
        if isinstance(flag, dict):
            return str(flag.get("value") or flag.get("flag") or "").strip()
        return str(flag or "").strip()

    def _shadow_graph_recommendations(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self.shadow_graph.update_from_notes(
            self._build_shadow_graph_notes(target=target, page_features=page_features)
        )
        insights = self.shadow_graph.get_strategic_insights()

        endpoint_paths: list[str] = []
        for node, data in self.shadow_graph.graph.nodes(data=True):
            if data.get("type") != "endpoint":
                continue
            label = str(data.get("label") or "").strip()
            path = label.split(" ", 1)[0].strip()
            if path and path not in endpoint_paths:
                endpoint_paths.append(path)

        prefix_groups: dict[str, list[str]] = {}
        for path in endpoint_paths:
            prefix = self._endpoint_prefix(path)
            prefix_groups.setdefault(prefix, []).append(path)

        scored: list[tuple[int, str, list[str]]] = []
        for prefix, paths in prefix_groups.items():
            score = len(paths)
            normalized = prefix.lower()
            if "admin" in normalized:
                score += 6
            if any(token in normalized for token in ("backup", "source", ".git")):
                score += 5
            if any(token in normalized for token in ("login", "auth")):
                score += 4
            if "upload" in normalized:
                score += 3
            if normalized.startswith("/api"):
                score += 2
            scored.append((score, prefix, paths))
        scored.sort(key=lambda item: (-item[0], item[1]))

        recommendations: list[dict[str, Any]] = []
        insight_text = " | ".join(insights[:2]) if insights else "ShadowGraph endpoint hotspot"
        for score, prefix, paths in scored[:2]:
            lower_prefix = prefix.lower()
            if any(token in lower_prefix for token in ("admin", "login", "auth")):
                worker_type: WorkerType = "exploit"
                task = f"ShadowGraph recommended auth/admin focus on {prefix}"
            elif any(token in lower_prefix for token in ("backup", "source", ".git")):
                worker_type = "exploit"
                task = f"ShadowGraph recommended source-leak probe on {prefix}"
            else:
                worker_type = "recon"
                task = f"ShadowGraph recommended deep recon on {prefix}"
            recommendations.append(
                {
                    "worker_type": worker_type,
                    "target_filter": prefix,
                    "task": task,
                    "metadata": {
                        "planned_by": "shadow_graph",
                        "shadow_graph_reason": insight_text,
                        "shadow_graph_score": score,
                        "sample_endpoints": list(paths[:5]),
                    },
                }
            )

        if not recommendations and insights:
            recommendations.append(
                {
                    "worker_type": "llm_explorer",
                    "target_filter": "",
                    "task": f"ShadowGraph recommended strategic exploration for {target}",
                    "metadata": {
                        "planned_by": "shadow_graph",
                        "shadow_graph_reason": insight_text,
                    },
                }
            )
        return recommendations

    def _build_shadow_graph_notes(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        endpoint_paths: list[str] = []
        for endpoint in list(page_features.get("endpoints") or []):
            normalized = str(endpoint or "").strip()
            if normalized and normalized not in endpoint_paths:
                endpoint_paths.append(normalized)

        for observation in list(self.state.observations or []):
            metadata = dict(getattr(observation, "metadata", {}) or {})
            raw_endpoints = metadata.get("endpoints") or []
            if isinstance(raw_endpoints, list):
                for item in raw_endpoints:
                    if isinstance(item, dict):
                        normalized = str(item.get("path") or item.get("url") or "").strip()
                    else:
                        normalized = str(item or "").strip()
                    if normalized and normalized not in endpoint_paths:
                        endpoint_paths.append(normalized)

        note_endpoints = [{"path": path, "methods": []} for path in endpoint_paths[:50]]
        target_label = urlparse(target).netloc or target
        return {
            f"ctf_shadow_graph_{target_label}": {
                "content": f"Derived CTF web surface for {target}",
                "category": "finding",
                "metadata": {
                    "target": target_label,
                    "url": target,
                    "endpoints": note_endpoints,
                },
            }
        }

    @staticmethod
    def _merge_round_summaries(
        first_round: CrewRunSummary,
        second_round: CrewRunSummary,
    ) -> CrewRunSummary:
        return CrewRunSummary(
            started_workers=list(first_round.started_workers) + list(second_round.started_workers),
            completed_workers=list(first_round.completed_workers) + list(second_round.completed_workers),
            cancelled_workers=list(
                dict.fromkeys(list(first_round.cancelled_workers) + list(second_round.cancelled_workers))
            ),
            worker_results={
                **dict(first_round.worker_results),
                **dict(second_round.worker_results),
            },
            verified_flag=second_round.verified_flag or first_round.verified_flag,
            stop_reason=second_round.stop_reason or first_round.stop_reason,
            flag_summary=dict(second_round.flag_summary or first_round.flag_summary or {}),
        )

    def _emit(self, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message)


__all__ = [
    "CTFCrewCoordinator",
    "CrewRunSummary",
    "CrewWorkerSpec",
]
