"""
PentestAgent M5 Swarm Link — Agent 间通信协议

AgentMessenger 封装 Agent 间异步消息收发，以 SharedBlackboard 为底层传输，
支持点对点消息、组播、发现上报、状态通知、帮助请求、应答确认、对话追溯及
异步响应等待。每个 Agent 独立实例；消息分发优先 handler，无 handler 则入 inbox。

技术约束: Python 3.10+, async/await, 依赖 SharedBlackboard + PheromoneRouter
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .shared_blackboard import SharedBlackboard, BlackboardMessage, MessageFilter
from .pheromone_router import PheromoneRouter


class AgentMessenger:
    """Agent 异步通信协议封装

    高阶发送/接收/组播/查询接口，底层基于 SharedBlackboard。
    消息到达时优先调用已注册的 handler，无匹配则落入 inbox 队列。

    Attributes:
        agent_id: 当前 Agent 唯一标识
        unread_count: inbox 中未消费消息数量
    """

    def __init__(
        self,
        agent_id: str,
        blackboard: SharedBlackboard,
        pheromone_router: Optional[PheromoneRouter] = None,
    ) -> None:
        """初始化 AgentMessenger

        参数:
            agent_id: 当前 Agent 唯一标识
            blackboard: SharedBlackboard 底层传输实例
            pheromone_router: 可选的信息素路由器
        """
        self._agent_id = agent_id
        self._bb = blackboard
        self._pheromone = pheromone_router
        self._subscriptions: List[str] = []
        self._inbox: asyncio.Queue[BlackboardMessage] = asyncio.Queue()
        self._handlers: Dict[str, Callable[[BlackboardMessage], Any]] = {}
        self._groups: set[str] = set()

    # ── 属性 ──────────────────────────────────────────

    @property
    def agent_id(self) -> str:
        """当前 Agent 唯一标识"""
        return self._agent_id

    @property
    def unread_count(self) -> int:
        """inbox 中未消费消息数量"""
        return self._inbox.qsize()

    # ── 发送 ──────────────────────────────────────────

    async def send(
        self,
        msg_type: str,
        content: Any,
        target: str = "",
        metadata: Optional[dict] = None,
        to_agent: Optional[str] = None,
    ) -> str:
        """发送通用消息到黑板

        指定 to_agent 时 metadata 标记 recipient 实现点对点寻址。

        参数:
            msg_type: 消息类型标识
            content: 消息正文
            target: 操作目标上下文
            metadata: 额外元数据字典
            to_agent: 指定接收方 Agent ID，空表示广播

        返回: 发送消息的唯一 msg_id
        """
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        meta = dict(metadata) if metadata else {}
        if to_agent:
            meta["recipient"] = to_agent
        if target:
            meta["target"] = target
        from .shared_blackboard import BlackboardMessage
        msg = BlackboardMessage(
            msg_id="", msg_type=msg_type, sender=self._agent_id,
            content=content, target=target or "", metadata=meta
        )
        return await self._bb.post(msg)

    async def report_finding(
        self,
        target: str,
        finding: str,
        severity: str = "medium",
        details: Optional[dict] = None,
    ) -> str:
        """上报安全发现，自动 post finding + deposit_finding

        参数:
            target: 发现所在目标
            finding: 发现描述文本
            severity: 严重等级 critical|high|medium|low|info
            details: 技术详情字典

        返回: 发送消息的唯一 msg_id
        """
        content = json.dumps({"finding": finding, "severity": severity, "target": target,
                   "timestamp": datetime.now(timezone.utc).isoformat(), "details": details or {}}, ensure_ascii=False)
        msg_id = await self.send(msg_type="finding", content=content,
                                 target=target, metadata={"severity": severity})
        if self._pheromone is not None:
            await self._pheromone.deposit_finding(target=target, finding=finding,
                                                  severity=severity, details=details)
        return msg_id

    async def request_help(
        self, target: str, problem: str, required_skill: str = ""
    ) -> str:
        """请求其他 Agent 协助

        参数:
            target: 相关操作目标
            problem: 问题描述
            required_skill: 所需技能标签（如 web, crypto, pwn）

        返回: 发送消息的唯一 msg_id
        """
        content = json.dumps({"problem": problem, "required_skill": required_skill,
                   "target": target, "requester": self._agent_id,
                   "timestamp": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False)
        return await self.send(msg_type="help_request", content=content,
                               target=target, metadata={"required_skill": required_skill})

    async def notify_status(
        self, status: str, target: str = "", progress: float = 0.0
    ) -> str:
        """通知当前 Agent 运行状态

        参数:
            status: 状态字符串 idle|running|completed|failed
            target: 当前操作目标
            progress: 进度百分比 0.0~1.0

        返回: 发送消息的唯一 msg_id
        """
        content = json.dumps({"status": status, "progress": max(0.0, min(1.0, progress)),
                   "target": target, "agent_id": self._agent_id,
                   "timestamp": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False)
        return await self.send(msg_type="status", content=content, target=target,
                               metadata={"status": status, "progress": progress})

    async def acknowledge(self, msg_id: str, result: str = "ack") -> str:
        """对指定消息发送应答确认

        metadata 中携带 in_reply_to 字段关联原消息 ID。

        参数:
            msg_id: 待确认的原消息 ID
            result: 应答结果 ack|done|error

        返回: 发送应答消息的唯一 msg_id
        """
        content = json.dumps({"result": result, "original_msg_id": msg_id,
                   "responder": self._agent_id,
                   "timestamp": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False)
        return await self.send(msg_type="ack", content=content,
                               metadata={"in_reply_to": msg_id, "ack_result": result})

    # ── 接收 ──────────────────────────────────────────

    async def start_listening(self) -> None:
        """启动消息监听

        订阅黑板所有消息类型（通配 *），收到后通过 _dispatch 分发：
        优先匹配 handler，无匹配则写入 inbox。
        """
        sub_id = await self._bb.subscribe(msg_type="*", callback=self._dispatch,
                                          subscriber_id=self._agent_id)
        self._subscriptions.append(sub_id)

    async def stop_listening(self) -> None:
        """停止消息监听，取消所有已注册订阅"""
        for sub_id in self._subscriptions:
            await self._bb.unsubscribe(sub_id)
        self._subscriptions.clear()

    async def receive(self, timeout: Optional[float] = None) -> Optional[BlackboardMessage]:
        """从 inbox 队列取一条消息

        参数:
            timeout: 等待超时秒数，None 表示无限等待

        返回: BlackboardMessage 实例，超时返回 None
        """
        try:
            if timeout is not None:
                return await asyncio.wait_for(self._inbox.get(), timeout=timeout)
            return await self._inbox.get()
        except asyncio.TimeoutError:
            return None

    async def receive_all(self, limit: int = 100) -> List[BlackboardMessage]:
        """批量取出 inbox 中的消息（非阻塞）

        参数:
            limit: 最大取出数量

        返回: BlackboardMessage 列表
        """
        results: List[BlackboardMessage] = []
        for _ in range(limit):
            try:
                results.append(self._inbox.get_nowait())
            except asyncio.QueueEmpty:
                break
        return results

    def register_handler(
        self, msg_type: str, handler: Callable[[BlackboardMessage], Any]
    ) -> None:
        """注册指定消息类型的处理函数，同类型覆盖前 handler

        参数:
            msg_type: 消息类型标识
            handler: 回调函数，接收 BlackboardMessage 参数
        """
        self._handlers[msg_type] = handler

    async def _dispatch(self, msg: BlackboardMessage) -> None:
        """消息分发器：sender 为自身忽略 → recipient 不匹配忽略 →
        有 handler 调用 handler（兼容异步/同步，异常兜底入 inbox）→ 无 handler 入 inbox
        """
        if getattr(msg, "sender", "") == self._agent_id:
            return
        meta = getattr(msg, "metadata", {}) or {}
        if isinstance(meta, dict):
            rcpt = meta.get("recipient", "")
            if rcpt and rcpt != self._agent_id:
                return
        handler = self._handlers.get(getattr(msg, "msg_type", ""))
        if handler is not None:
            try:
                result = handler(msg)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                await self._inbox.put(msg)
        else:
            await self._inbox.put(msg)

    # ── 组通信 ────────────────────────────────────────

    async def join_group(self, group_id: str) -> None:
        """加入指定通信组"""
        self._groups.add(group_id)
        await self.send(msg_type="group_join",
                        content=json.dumps({"group_id": group_id, "agent_id": self._agent_id}, ensure_ascii=False),
                        metadata={"group": group_id})

    async def leave_group(self, group_id: str) -> None:
        """离开指定通信组"""
        self._groups.discard(group_id)
        await self.send(msg_type="group_leave",
                        content=json.dumps({"group_id": group_id, "agent_id": self._agent_id}, ensure_ascii=False),
                        metadata={"group": group_id})

    async def send_to_group(
        self, group_id: str, content: Any, msg_type: str = "status"
    ) -> str:
        """向指定组发送组播消息，metadata 标记 group 字段

        参数:
            group_id: 目标组标识
            content: 消息正文
            msg_type: 消息类型，默认 status

        返回: 发送消息的唯一 msg_id
        """
        return await self.send(msg_type=msg_type, content=content,
                               metadata={"group": group_id})

    # ── 查询 ──────────────────────────────────────────

    async def get_conversation(
        self, target: str, since: Optional[float] = None
    ) -> List[BlackboardMessage]:
        """获取与指定目标相关的对话历史

        参数:
            target: 目标标识（IP / 域名）
            since: 仅返回此后消息的 Unix 时间戳，None 返回全部

        返回: 匹配的 BlackboardMessage 列表
        """
        filt = MessageFilter(msg_types=None, senders=None, target=target, since=since)
        return await self._bb.query(filt)

    async def wait_for_response(
        self, command_msg_id: str, timeout: float = 30.0
    ) -> Optional[BlackboardMessage]:
        """轮询黑板等待指定命令消息的响应

        参数:
            command_msg_id: 原始命令消息的 ID
            timeout: 最长等待秒数，默认 30.0

        返回: 响应 BlackboardMessage，超时返回 None
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            filt = MessageFilter(msg_type="result",
                                 metadata_query={"in_reply_to": command_msg_id})
            results = await self._bb.query(filt)
            if results:
                return results[0]
            await asyncio.sleep(0.3)
        return None
