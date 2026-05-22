"""
PentestAgent M5 Swarm Link - Pheromone Router Module
借鉴蚁群算法实现任务优先级动态调整的信息素路由器。
Python 3.10+ 标准库（asyncio, datetime, heapq），零外部依赖。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import asyncio
import heapq


@dataclass
class PheromoneTrail:
    """单条信息素轨迹，记录目标节点上的信息素沉积历史。"""
    target: str
    strength: float = 1.0
    source: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    decay_rate: float = 0.95

    @property
    def current_strength(self) -> float:
        """动态计算当前信息素强度，基于时间衰减。"""
        elapsed = (datetime.now() - self.last_updated).total_seconds()
        return self.strength * (self.decay_rate ** elapsed)

    @property
    def is_active(self) -> bool:
        """判断该轨迹是否仍有效（当前强度高于阈值 0.1）。"""
        return self.current_strength > 0.1


@dataclass
class TaskPriority:
    """任务优先级封装，融合信息素奖励、负载惩罚与截止时间奖励。"""
    target: str
    base_priority: int = 5
    pheromone_bonus: float = 0.0
    agent_load: int = 0
    deadline: Optional[datetime] = None

    @property
    def final_score(self) -> float:
        """计算最终评分：基础分 + 信息素奖励 - 负载惩罚 + 截止时间奖励。"""
        load_penalty = self.agent_load * 0.5
        deadline_bonus = 0.0
        if self.deadline:
            seconds_to_deadline = (self.deadline - datetime.now()).total_seconds()
            if seconds_to_deadline < 0:
                deadline_bonus = 5.0
            elif seconds_to_deadline < 3600:
                deadline_bonus = 3.0
            elif seconds_to_deadline < 86400:
                deadline_bonus = 1.0
        return self.base_priority + self.pheromone_bonus - load_penalty + deadline_bonus


class PheromoneRouter:
    """信息素路由器核心类，基于蚁群算法实现目标动态优先级调整。"""

    def __init__(self, decay_rate: float = 0.95, threshold: float = 0.1,
                 boost_per_finding: float = 2.0) -> None:
        """初始化路由器。

        Args:
            decay_rate: 每秒衰减系数。
            threshold: 信息素失效阈值。
            boost_per_finding: 每次发现的默认强度增量。
        """
        self._trails: Dict[str, PheromoneTrail] = {}
        self._decay_rate = decay_rate
        self._threshold = threshold
        self._boost = boost_per_finding
        self._lock = asyncio.Lock()
        self._decay_task: Optional[asyncio.Task] = None

    async def deposit(self, target: str, source: str = "",
                      strength: Optional[float] = None) -> None:
        """在目标上沉积信息素（累加模式）。新target创建trail，已有则累加。

        Args:
            target: 目标节点标识。
            source: 信息素来源。
            strength: 本次沉积强度，默认 self._boost。
        """
        add = strength if strength is not None else self._boost
        now = datetime.now()
        async with self._lock:
            if target in self._trails:
                trail = self._trails[target]
                trail.strength = trail.current_strength + add
                trail.source = source or trail.source
                trail.last_updated = now
            else:
                self._trails[target] = PheromoneTrail(
                    target=target, strength=add, source=source,
                    created_at=now, last_updated=now, decay_rate=self._decay_rate)

    async def deposit_finding(self, target: str, finding_type: str,
                              severity: str = "medium") -> None:
        """根据发现结果类型与严重级别沉积信息素。

        严重度: critical=+5, high=+3, medium=+2, low=+1, info=+0.5。
        额外加成: web_vuln+1, pwn_shell+3, crypto_solved+2。

        Args:
            target: 目标节点标识。
            finding_type: 发现类型。
            severity: 严重级别。
        """
        severity_map = {"critical": 5.0, "high": 3.0, "medium": 2.0,
                        "low": 1.0, "info": 0.5}
        type_bonus = {"web_vuln": 1.0, "pwn_shell": 3.0, "crypto_solved": 2.0}
        total = severity_map.get(severity.lower(), 2.0) + type_bonus.get(finding_type.lower(), 0.0)
        await self.deposit(target, source=finding_type, strength=total)

    async def evaporate(self, target: Optional[str] = None) -> None:
        """手动触发信息素蒸发。指定target衰减单个，None则衰减全部。

        Args:
            target: 目标节点标识，None 则作用于全部。
        """
        async with self._lock:
            if target is not None:
                trail = self._trails.get(target)
                if trail:
                    trail.strength = trail.current_strength
                    trail.last_updated = datetime.now()
                    if trail.strength <= self._threshold:
                        del self._trails[target]
            else:
                to_remove = []
                for key, trail in self._trails.items():
                    trail.strength = trail.current_strength
                    trail.last_updated = datetime.now()
                    if trail.strength <= self._threshold:
                        to_remove.append(key)
                for key in to_remove:
                    del self._trails[key]

    async def get_strength(self, target: str) -> float:
        """获取目标当前信息素强度（动态计算）。不存在返回0.0。"""
        async with self._lock:
            trail = self._trails.get(target)
            return trail.current_strength if trail else 0.0

    async def get_active_trails(self) -> List[PheromoneTrail]:
        """获取所有活跃轨迹，按 current_strength 降序排列。"""
        async with self._lock:
            active = [t for t in self._trails.values() if t.is_active]
        active.sort(key=lambda x: x.current_strength, reverse=True)
        return active

    async def get_top_targets(self, n: int = 5) -> List[Tuple[str, float]]:
        """获取信息素强度最高的前 n 个目标。

        Returns:
            [(target, strength), ...] 按强度降序。
        """
        active = await self.get_active_trails()
        return [(t.target, t.current_strength) for t in active[:n]]

    async def calculate_priority(self, target: str, base_priority: int = 5,
                                 agent_count: int = 0) -> TaskPriority:
        """计算指定目标的综合任务优先级。

        Args:
            target: 目标节点标识。
            base_priority: 基础优先级。
            agent_count: 当前智能体数量。

        Returns:
            TaskPriority 实例，pheromone_bonus=min(strength/10, 5.0)。
        """
        strength = await self.get_strength(target)
        return TaskPriority(target=target, base_priority=base_priority,
                            pheromone_bonus=min(strength / 10.0, 5.0),
                            agent_load=agent_count)

    async def get_prioritized_queue(
        self, targets: List[str],
        base_priorities: Optional[Dict[str, int]] = None,
    ) -> List[TaskPriority]:
        """核心方法：构建按 final_score 降序排列的优先级队列。使用heapq排序。

        Args:
            targets: 待排序目标列表。
            base_priorities: 目标->基础优先级映射，缺省值5。

        Returns:
            按 final_score 降序排列的 TaskPriority 列表。
        """
        bp = base_priorities or {}
        entries = []
        for tgt in targets:
            prio = await self.calculate_priority(tgt, base_priority=bp.get(tgt, 5))
            heapq.heappush(entries, (-prio.final_score, prio))
        return [heapq.heappop(entries)[1] for _ in range(len(entries))]

    async def recommend_next_target(
        self, available_targets: List[str],
        current_agents: Optional[Dict[str, int]] = None,
    ) -> Tuple[str, str]:
        """推荐下一个攻击目标，返回(target, reason)。

        Args:
            available_targets: 可用目标列表。
            current_agents: 目标->当前智能体数量的映射。

        Returns:
            (推荐目标, 推荐理由)；无可用目标返回("", "无可用目标")。
        """
        if not available_targets:
            return ("", "无可用目标")
        agents = current_agents or {}
        scored = []
        for tgt in available_targets:
            strength = await self.get_strength(tgt)
            load = agents.get(tgt, 0)
            scored.append((strength - load * 0.8, tgt, strength, load))
        scored.sort(key=lambda x: x[0], reverse=True)
        _, best_tgt, best_strength, best_load = scored[0]
        if best_strength > 0:
            reason = f"信息素强度 {best_strength:.2f}，负载 {best_load} 智能体"
        else:
            reason = f"无信息素历史，负载最低 ({best_load})，默认选择"
        return (best_tgt, reason)

    async def start_decay_loop(self, interval: int = 60) -> None:
        """启动后台自动衰减循环。

        Args:
            interval: 蒸发周期（秒），默认60秒。
        """
        if self._decay_task is not None:
            return
        self._decay_task = asyncio.create_task(self._decay_loop(interval))

    async def stop_decay_loop(self) -> None:
        """停止后台自动衰减循环。"""
        if self._decay_task is not None:
            self._decay_task.cancel()
            try:
                await self._decay_task
            except asyncio.CancelledError:
                pass
            self._decay_task = None

    async def _decay_loop(self, interval: int) -> None:
        """后台协程：周期性蒸发并删除低于阈值的trail。

        Args:
            interval: 蒸发周期（秒）。
        """
        try:
            while True:
                await asyncio.sleep(interval)
                await self.evaporate()
        except asyncio.CancelledError:
            raise

    async def get_stats(self) -> Dict[str, Any]:
        """获取路由器统计信息。

        Returns:
            包含轨迹数、总强度、活跃轨迹数、最强目标等信息的字典。
        """
        async with self._lock:
            total = len(self._trails)
            if total == 0:
                return {"total_trails": 0, "total_strength": 0.0,
                        "active_trails": 0, "strongest_target": None,
                        "strongest_strength": 0.0, "decay_rate": self._decay_rate,
                        "threshold": self._threshold,
                        "decay_running": self._decay_task is not None}
            strengths = [(t.target, t.current_strength)
                         for t in self._trails.values()]
        active = sum(1 for _, s in strengths if s > self._threshold)
        total_strength = sum(s for _, s in strengths)
        strongest_target, strongest_strength = max(strengths, key=lambda x: x[1])
        return {"total_trails": total, "total_strength": round(total_strength, 4),
                "active_trails": active, "strongest_target": strongest_target,
                "strongest_strength": round(strongest_strength, 4),
                "decay_rate": self._decay_rate, "threshold": self._threshold,
                "decay_running": self._decay_task is not None}

    async def reset(self) -> None:
        """清空所有信息素轨迹并停止后台衰减循环。"""
        await self.stop_decay_loop()
        async with self._lock:
            self._trails.clear()
