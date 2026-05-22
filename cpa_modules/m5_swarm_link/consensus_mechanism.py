#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""consensus_mechanism.py — 多Agent投票共识机制

支持多选项投票（加权计数）、二元投票（是/否）、优先级排序（Borda计数法），
基于 asyncio 异步驱动，仅使用 Python 标准库。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .agent_messenger import AgentMessenger
    from .shared_blackboard import BlackboardMessage


class ConsensusMechanism:
    """共识机制 — 多Agent对同一问题独立决策，投票选出最佳答案。"""

    def __init__(
        self,
        messenger: "AgentMessenger",
        min_agents: int = 3,
        threshold: float = 0.6,
    ) -> None:
        self._messenger: "AgentMessenger" = messenger
        self._min_agents: int = min_agents
        self._threshold: float = threshold
        self._active_votes: Dict[str, dict] = {}

    # ──────────────── 发起共识 ────────────────

    async def propose(self, question: str, options: List[str], timeout: float = 30.0) -> dict:
        """发起多选项投票并等待结果。

        流程：生成vote_id → 创建投票记录 → 广播请求 → 等待收集 → 统计 → 检查共识。

        Args:
            question: 投票问题描述。
            options: 候选选项列表。
            timeout: 等待投票的超时时间（秒）。

        Returns:
            包含 consensus_reached, winner, vote_count, agreement_ratio,
            participating_agents, details 的结果字典。
        """
        vote_id = f"vote_{uuid.uuid4().hex[:8]}"
        self._active_votes[vote_id] = {
            "question": question, "options": options, "votes": [],
            "start_time": time.time(), "timeout": timeout, "status": "open",
        }
        # 广播投票请求
        await self._messenger.send(
            msg_type="vote_request",
            content={"question": question, "options": options, "vote_id": vote_id},
            metadata={"vote_request": True, "vote_id": vote_id, "options": options},
        )
        # 收集投票并统计
        votes = await self._simulate_vote_collection(vote_id, timeout)
        self._active_votes[vote_id]["votes"] = votes
        self._active_votes[vote_id]["status"] = "closed"
        return self._build_result(votes, question)

    async def propose_binary(self, question: str, timeout: float = 30.0) -> dict:
        """发起二元投票（是/否）。参数与 propose() 相同。"""
        return await self.propose(question, options=["yes", "no"], timeout=timeout)

    async def propose_priority_ranking(self, targets: List[str], timeout: float = 30.0) -> dict:
        """发起优先级排序投票，使用Borda计数法综合排序。

        每个Agent对targets排序，第1名得N-1分，第2名得N-2分...最后得0分；
        累加所有Agent得分后按总分降序排列。

        Args:
            targets: 待排序的目标列表。
            timeout: 等待投票的超时时间（秒）。

        Returns:
            包含 consensus_reached, ranking, scores, participating_agents, details 的字典。
        """
        vote_id = f"rank_{uuid.uuid4().hex[:8]}"
        self._active_votes[vote_id] = {
            "question": f"优先级排序: {targets}", "options": targets, "votes": [],
            "start_time": time.time(), "timeout": timeout, "status": "open", "mode": "ranking",
        }
        await self._messenger.send(
            msg_type="ranking_request",
            content={"targets": targets, "vote_id": vote_id},
            metadata={"ranking_request": True, "vote_id": vote_id, "targets": targets},
        )
        votes = await self._simulate_vote_collection(vote_id, timeout)
        self._active_votes[vote_id]["votes"] = votes
        self._active_votes[vote_id]["status"] = "closed"
        # 提取排序列表
        rankings: List[List[str]] = [
            v["choice"] for v in votes
            if isinstance(v.get("choice"), list) and len(v["choice"]) == len(targets)
        ]
        ranked = self._borda_count(rankings) if rankings else targets
        # 计算各项得分
        scores: Dict[str, float] = {}
        if rankings:
            n = len(targets)
            for r in rankings:
                for idx, item in enumerate(r):
                    scores[item] = scores.get(item, 0.0) + (n - 1 - idx)
        total_agents = len({v.get("voter") for v in votes if v.get("voter")})
        top_score = scores.get(ranked[0], 0.0) if ranked and scores else 0.0
        total_score = sum(scores.values()) if scores else 0.0
        ratio = top_score / total_score if total_score > 0 else 0.0
        reached = (total_agents >= self._min_agents) and (ratio >= self._threshold)
        return {
            "consensus_reached": reached, "ranking": ranked, "scores": scores,
            "participating_agents": total_agents,
            "details": f"优先级排序投票已结束，参与Agent数={total_agents}, "
                       f"最终排序={ranked}, 共识={'达成' if reached else '未达成'}",
        }

    # ──────────────── 参与投票 ────────────────

    async def vote(self, vote_id: str, choice: str, confidence: float = 1.0) -> None:
        """Agent主动投出一票。

        Args:
            vote_id: 投票标识符。
            choice: 所选选项（排序投票时choice可以是列表）。
            confidence: 置信度权重（0~1），默认1.0。
        """
        ballot = {
            "vote_id": vote_id, "choice": choice, "confidence": confidence,
            "voter": getattr(self._messenger, "agent_id", "unknown"),
            "timestamp": time.time(),
        }
        if vote_id in self._active_votes:
            self._active_votes[vote_id]["votes"].append(ballot)
        await self._messenger.send(
            msg_type="vote_reply", content=ballot,
            metadata={"vote_reply": True, "vote_id": vote_id},
        )

    async def auto_vote(self, vote_id: str, context: Optional[dict] = None) -> None:
        """Agent自动投票。当前简化实现：选择第一个可用选项。

        Args:
            vote_id: 投票标识符。
            context: 额外上下文信息，供后续智能决策扩展。
        """
        options = self._active_votes.get(vote_id, {}).get("options", [])
        choice = options[0] if options else ""
        await self.vote(vote_id, choice, confidence=1.0)

    # ──────────────── 投票管理 ────────────────

    def get_vote_status(self, vote_id: str) -> dict:
        """查询指定投票的当前状态。

        Returns:
            包含 total_votes, options, deadline, is_open 的状态字典。
        """
        info = self._active_votes.get(vote_id, {})
        if not info:
            return {"total_votes": 0, "options": [], "deadline": 0.0, "is_open": False}
        start = info.get("start_time", 0.0)
        return {
            "total_votes": len(info.get("votes", [])),
            "options": info.get("options", []),
            "deadline": start + info.get("timeout", 0.0),
            "is_open": info.get("status") == "open",
        }

    async def close_vote(self, vote_id: str) -> dict:
        """手动关闭投票并立即统计结果。返回格式与 propose() 相同。"""
        if vote_id not in self._active_votes:
            return {
                "consensus_reached": False, "winner": "", "vote_count": {},
                "agreement_ratio": 0.0, "participating_agents": 0,
                "details": f"投票 {vote_id} 不存在",
            }
        self._active_votes[vote_id]["status"] = "closed"
        votes = self._collect_votes_from_blackboard(vote_id)
        self._active_votes[vote_id]["votes"] = votes
        return self._build_result(votes, self._active_votes[vote_id].get("question", ""))

    # ──────────────── 内部统计 ────────────────

    def _build_result(self, votes: List[dict], question: str) -> dict:
        """根据投票列表构建结果字典。"""
        vote_counts = self._count_votes(votes)
        total_agents = len({v.get("voter") for v in votes if v.get("voter")})
        reached, winner, ratio = self._check_consensus(vote_counts, total_agents)
        return {
            "consensus_reached": reached, "winner": winner or "",
            "vote_count": vote_counts, "agreement_ratio": ratio,
            "participating_agents": total_agents,
            "details": f"投票 '{question}' 已结束，参与Agent数={total_agents}, "
                       f"获胜选项='{winner or '无'}', 共识={'达成' if reached else '未达成'}",
        }

    def _count_votes(self, votes: List[dict]) -> Dict[str, float]:
        """加权计票：按置信度累加各选项得票数。

        Returns:
            {选项: 加权得票数}
        """
        counts: Dict[str, float] = {}
        for v in votes:
            choice = v.get("choice")
            if isinstance(choice, str):
                counts[choice] = counts.get(choice, 0.0) + v.get("confidence", 1.0)
        return counts

    def _check_consensus(self, vote_counts: Dict[str, float], total_agents: int) -> Tuple[bool, str, float]:
        """检查是否达成共识。

        共识条件：
        1. 参与Agent数 >= min_agents
        2. 最高票选项得票比例 >= threshold

        Returns:
            (consensus_reached, winner, agreement_ratio)
        """
        if not vote_counts or total_agents == 0:
            return (False, "", 0.0)
        winner = max(vote_counts, key=lambda k: vote_counts[k])
        total = sum(vote_counts.values())
        ratio = vote_counts[winner] / total if total > 0 else 0.0
        reached = (total_agents >= self._min_agents) and (ratio >= self._threshold)
        return (reached, winner, ratio)

    def _borda_count(self, rankings: List[List[str]]) -> List[str]:
        """Borda计数法综合排序。

        每个Agent对N个目标排序：第1名得N-1分，第2名得N-2分...第N名得0分；
        累加所有Agent得分后按总分降序返回。

        Example:
            >>> cm = ConsensusMechanism.__new__(ConsensusMechanism)
            >>> rankings = [["A","B","C"],["A","C","B"],["B","A","C"]]
            >>> cm._borda_count(rankings)
            ['A', 'B', 'C']   # A=5分, B=3分, C=1分

        Args:
            rankings: 每个Agent的排序结果列表。

        Returns:
            按Borda总分降序排列的目标列表。
        """
        if not rankings:
            return []
        n = len(rankings[0])
        scores: Dict[str, float] = {}
        for r in rankings:
            for idx, item in enumerate(r):
                scores[item] = scores.get(item, 0.0) + (n - 1 - idx)
        return sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    def _collect_votes_from_blackboard(self, vote_id: str) -> List[dict]:
        """从黑板查询所有回复指定vote_id的投票消息。

        Returns:
            收集到的投票列表。
        """
        votes: List[dict] = []
        bb = getattr(self._messenger, "blackboard", None)
        if bb is None:
            return votes
        messages = getattr(bb, "query", lambda **kwargs: [])()
        for msg in messages:
            meta = getattr(msg, "metadata", {}) if hasattr(msg, "metadata") else msg.get("metadata", {})
            if meta.get("vote_reply") and meta.get("vote_id") == vote_id:
                content = getattr(msg, "content", {}) if hasattr(msg, "content") else msg.get("content", {})
                if isinstance(content, dict) and content.get("vote_id") == vote_id:
                    votes.append(content)
        return votes

    async def _simulate_vote_collection(self, vote_id: str, timeout: float) -> List[dict]:
        """模拟收集投票：在超时时间内轮询黑板收集vote_reply消息。

        Args:
            vote_id: 投票标识符。
            timeout: 最长等待时间（秒）。

        Returns:
            收集期间累积的投票列表。
        """
        deadline = time.time() + timeout
        collected: List[dict] = []
        last_len = 0
        while time.time() < deadline:
            new_votes = self._collect_votes_from_blackboard(vote_id)
            if len(new_votes) > last_len:
                collected = new_votes
                last_len = len(collected)
            if last_len >= self._min_agents:  # 提前满足
                break
            await asyncio.sleep(min(1.0, deadline - time.time()))
        return collected


# ──────────────── 接口存根 ────────────────

try:
    from .agent_messenger import AgentMessenger  # noqa: F401,F811
    from .shared_blackboard import BlackboardMessage  # noqa: F401,F811
except ImportError:

    class AgentMessenger:  # type: ignore[no-redef]
        """AgentMessenger接口存根。"""

        def __init__(self, agent_id: str = "stub_agent") -> None:
            self.agent_id = agent_id
            self.blackboard: Optional[Any] = None

        async def send_message(
            self, command: str, content: dict, metadata: Optional[dict] = None
        ) -> None:
            """发送消息存根。"""
            pass

    @dataclass
    class BlackboardMessage:  # type: ignore[no-redef]
        """BlackboardMessage数据存根。"""

        msg_id: str = ""
        command: str = ""
        content: dict = field(default_factory=dict)
        metadata: dict = field(default_factory=dict)
        timestamp: float = field(default_factory=time.time)
