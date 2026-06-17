#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FlagHunter M6 Turbo — 并发扫描器模块。

基于 asyncio.Semaphore 的并发工具执行系统：
- 双重信号量（全局 + 每主机）防止对单一目标 DoS
- 依赖图拓扑排序，确保前置任务先完成
- 指数退避重试、任务取消、进度回调（Python >= 3.10）
"""

from __future__ import annotations

import asyncio
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

# ──────────────────────────────── 数据模型 ────────────────────────────────

@dataclass
class ScanTask:
    """单个扫描任务的数据模型。"""

    task_id: str
    tool_name: str
    target: str
    params: dict = field(default_factory=dict)
    priority: int = 5
    timeout: int = 300
    retry_count: int = 0
    max_retries: int = 2
    depends_on: List[str] = field(default_factory=list)
    status: str = "pending"  # pending|running|completed|failed|cancelled
    result: dict = field(default_factory=dict)
    error: str = ""
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def duration_ms(self) -> int:
        """返回任务执行耗时（毫秒），未完成返回 0。"""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at) * 1000)
        return 0


@dataclass
class ScanBatchResult:
    """批量扫描的结果聚合。"""

    total: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    results: Dict[str, dict] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    total_duration_ms: int = 0


# ──────────────────────────────── 并发扫描器 ────────────────────────────────

class ParallelScanner:
    """基于 asyncio 的并发渗透测试工具执行器。

    双重 Semaphore 控制并发：全局限制总并发数，每主机限制防 DoS。
    参数: max_concurrent-全局最大并发; max_per_host-单主机最大并发。
    """

    def __init__(self, max_concurrent: int = 5, max_per_host: int = 2) -> None:
        self._max_concurrent = max_concurrent
        self._max_per_host = max_per_host
        self._global_sem = asyncio.Semaphore(max_concurrent)
        self._host_sems: Dict[str, asyncio.Semaphore] = {}
        self._scan_tasks: Dict[str, ScanTask] = {}
        self._lock = asyncio.Lock()
        self._dependency_events: Dict[str, asyncio.Event] = {}

    # ────────── 公共 API ──────────

    async def execute(
        self, tool_name: str, target: str, params: Optional[dict] = None,
        timeout: int = 300, priority: int = 5,
        actual_executor=None,
    ) -> dict:
        """执行单个扫描任务。自动分配 task_id，获取双重 Semaphore 后执行。"""
        task = ScanTask(
            task_id=str(uuid.uuid4()), tool_name=tool_name, target=target,
            params=params or {}, priority=priority, timeout=timeout,
        )
        async with self._lock:
            self._scan_tasks[task.task_id] = task
        if actual_executor is not None:
            # Wrap to Callable[[], Coroutine] expected by _execute_single
            executor = lambda: actual_executor(task.target, task.params)
        else:
            executor = self._default_executor(task)
        result = await self._execute_single(task, executor)
        return result

    async def execute_batch(
        self, tasks: List[ScanTask],
        progress_callback: Optional[Callable[[ScanTask], None]] = None,
        actual_executor=None,
    ) -> ScanBatchResult:
        """批量执行扫描任务，支持优先级与依赖拓扑排序。"""
        if not tasks:
            return ScanBatchResult()
        circular = self._has_circular_dependency(tasks)
        if circular[0]:
            raise ValueError(f"检测到循环依赖: {' -> '.join(circular[1])}")
        batch_result = ScanBatchResult(total=len(tasks))
        start_time = time.monotonic()
        task_map = {t.task_id: t for t in tasks}
        for t in tasks:
            async with self._lock:
                self._scan_tasks[t.task_id] = t
                self._dependency_events[t.task_id] = asyncio.Event()
        tasks_sorted = sorted(tasks, key=lambda t: t.priority)
        pending_ids: set = {t.task_id for t in tasks_sorted}
        running: Dict[str, asyncio.Task] = {}
        completed_ids: set = set()

        async def _run_one(st: ScanTask) -> None:
            for dep_id in st.depends_on:
                if dep_id in self._dependency_events:
                    await self._dependency_events[dep_id].wait()
            if st.status == "cancelled":
                batch_result.cancelled += 1
                self._dependency_events[st.task_id].set()
                completed_ids.add(st.task_id)
                if progress_callback:
                    progress_callback(st)
                return
            if actual_executor is not None:
                exec_fn = lambda: actual_executor(st.target, st.params)
            else:
                exec_fn = self._default_executor(st)
            res = await self._execute_single(st, exec_fn)
            if st.status == "completed":
                batch_result.completed += 1
                batch_result.results[st.task_id] = res
            elif st.status == "cancelled":
                batch_result.cancelled += 1
            else:
                batch_result.failed += 1
                batch_result.errors[st.task_id] = st.error
            self._dependency_events[st.task_id].set()
            completed_ids.add(st.task_id)
            if progress_callback:
                progress_callback(st)

        while pending_ids or running:
            # 按 tasks_sorted 的顺序筛选就绪任务，确保优先级高的先启动
            ready = [
                task_map[tid] for tid in (t.task_id for t in tasks_sorted)
                if tid in pending_ids
                and all(d in completed_ids for d in task_map[tid].depends_on)
            ]
            for st in ready:
                pending_ids.remove(st.task_id)
                running[st.task_id] = asyncio.create_task(_run_one(st))
            if running:
                aws = list(running.values())
                done, _ = await asyncio.wait(aws, return_when=asyncio.FIRST_COMPLETED)
                for d in done:
                    for tid, aio_task in list(running.items()):
                        if aio_task is d:
                            running.pop(tid, None)
                            break
        batch_result.total_duration_ms = int((time.monotonic() - start_time) * 1000)
        return batch_result

    async def execute_batch_simple(self, task_tuples: List[tuple]) -> ScanBatchResult:
        """简化版批量执行，无依赖关系，全部并发。

        task_tuples: [(tool_name, target, params, timeout), ...]
        params 与 timeout 可省略，timeout 默认 300。
        """
        tasks: List[ScanTask] = []
        for item in task_tuples:
            tool_name, target = item[0], item[1]
            params = item[2] if len(item) > 2 else {}
            timeout = item[3] if len(item) > 3 else 300
            tasks.append(ScanTask(
                task_id=str(uuid.uuid4()), tool_name=tool_name,
                target=target, params=params, timeout=timeout,
            ))
        return await self.execute_batch(tasks)

    async def cancel(self, task_id: str) -> bool:
        """取消指定任务。返回是否成功取消。"""
        async with self._lock:
            st = self._scan_tasks.get(task_id)
            if st is None or st.status not in ("pending", "running"):
                return False
            st.status = "cancelled"
            event = self._dependency_events.get(task_id)
            if event:
                event.set()
            return True

    async def cancel_all(self) -> int:
        """取消所有处于 pending 或 running 状态的任务，返回成功取消数。"""
        cancelled_count = 0
        async with self._lock:
            for tid, st in self._scan_tasks.items():
                if st.status in ("pending", "running"):
                    st.status = "cancelled"
                    event = self._dependency_events.get(tid)
                    if event:
                        event.set()
                    cancelled_count += 1
        return cancelled_count

    async def get_status(self, task_id: str) -> Optional[ScanTask]:
        """根据 task_id 返回任务状态深拷贝，不存在返回 None。"""
        async with self._lock:
            st = self._scan_tasks.get(task_id)
            return deepcopy(st) if st else None

    async def list_tasks(self, status: Optional[str] = None) -> List[ScanTask]:
        """列出所有任务，可按状态过滤。返回深拷贝列表。"""
        async with self._lock:
            result = list(self._scan_tasks.values())
            if status:
                result = [t for t in result if t.status == status]
            return [deepcopy(t) for t in result]

    # ────────── 核心内部方法 ──────────

    async def _execute_single(
        self, task: ScanTask, actual_executor: Callable[[], Coroutine[Any, Any, dict]]
    ) -> dict:
        """单任务执行核心。双重 Semaphore → 执行 → 指数退避重试(1s/2s/4s)。"""
        host = self._parse_host(task.target)
        host_sem = self._get_host_sem(host)
        async with self._global_sem:
            async with host_sem:
                if task.status == "cancelled":
                    return {"task_id": task.task_id, "status": "cancelled"}
                task.status = "running"
                task.started_at = time.monotonic()
                last_exception = ""
                for attempt in range(task.max_retries + 1):
                    try:
                        result = await asyncio.wait_for(
                            actual_executor(), timeout=task.timeout
                        )
                        task.result = result
                        task.status = "completed"
                        task.completed_at = time.monotonic()
                        return result
                    except asyncio.CancelledError:
                        task.status = "cancelled"
                        task.completed_at = time.monotonic()
                        raise
                    except asyncio.TimeoutError:
                        last_exception = f"超时 ({task.timeout}s)"
                    except Exception as exc:
                        last_exception = f"{type(exc).__name__}: {exc}"
                    task.retry_count = attempt + 1
                    if attempt < task.max_retries:
                        await asyncio.sleep(2 ** attempt)
                task.error = last_exception
                task.status = "failed"
                task.completed_at = time.monotonic()
                return {"task_id": task.task_id, "status": "failed", "error": last_exception}

    def _get_host_sem(self, host: str) -> asyncio.Semaphore:
        """获取或创建针对指定主机的 Semaphore。"""
        if host not in self._host_sems:
            self._host_sems[host] = asyncio.Semaphore(self._max_per_host)
        return self._host_sems[host]

    def _parse_host(self, target: str) -> str:
        """从目标地址中提取主机标识。

        解析规则：
        - 192.168.1.1:8080 → 192.168.1.1
        - http://example.com/path → example.com
        - https://sub.domain.com:443/api → sub.domain.com
        """
        t = target.strip()
        if "://" in t:
            t = t.split("://", 1)[1]
        if "/" in t:
            t = t.split("/", 1)[0]
        if ":" in t and t.count(":") == 1:
            host_part, port_part = t.rsplit(":", 1)
            if port_part.isdigit():
                t = host_part
        if t.startswith("[") and "]" in t:
            t = t[1 : t.index("]")]
        return t

    def _has_circular_dependency(self, tasks: List[ScanTask]) -> tuple:
        """使用 DFS 检测任务依赖图中是否存在环。

        返回 (True, 环路径) 若存在环，否则 (False, [])。
        """
        task_ids = {t.task_id for t in tasks}
        graph: Dict[str, List[str]] = {t.task_id: [] for t in tasks}
        for t in tasks:
            for dep in t.depends_on:
                if dep in task_ids:
                    graph[t.task_id].append(dep)
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in graph}

        def dfs(node: str, path: List[str]) -> tuple:
            color[node] = GRAY
            path.append(node)
            for neighbor in graph.get(node, []):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    cycle_start = path.index(neighbor)
                    return (True, path[cycle_start:] + [neighbor])
                if color[neighbor] == WHITE:
                    found, cycle = dfs(neighbor, path)
                    if found:
                        return (True, cycle)
            path.pop()
            color[node] = BLACK
            return (False, [])

        for tid in list(graph.keys()):
            if color[tid] == WHITE:
                found, cycle = dfs(tid, [])
                if found:
                    return (True, cycle)
        return (False, [])

    # ────────── 默认占位执行器 ──────────

    def _default_executor(
        self, task: ScanTask
    ) -> Callable[[], Coroutine[Any, Any, dict]]:
        """返回默认占位执行器协程。上层应替换为真实工具调用。"""
        async def _placeholder() -> dict:
            await asyncio.sleep(0.05)
            return {
                "task_id": task.task_id, "tool": task.tool_name,
                "target": task.target, "status": "completed",
                "output": f"[占位] {task.tool_name} @ {task.target}",
            }
        return _placeholder


# ──────────────────────────────── 快捷入口 ────────────────────────────────

async def run_parallel_scan(
    task_tuples: List[tuple], max_concurrent: int = 5, max_per_host: int = 2,
) -> ScanBatchResult:
    """快速执行批量扫描的函数级入口。"""
    scanner = ParallelScanner(max_concurrent, max_per_host)
    return await scanner.execute_batch_simple(task_tuples)

