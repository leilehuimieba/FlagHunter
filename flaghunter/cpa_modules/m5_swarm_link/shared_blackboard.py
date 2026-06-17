"""
shared_blackboard.py — PentestAgent M5 Swarm Link 共享黑板模块

基于 SQLite 的持久化消息总线，支持异步消息发布/订阅、
多维度查询过滤、消息过期自动清理、信息素优先级标记。

技术栈: Python 3.10+ / sqlite3 / asyncio (asyncio.to_thread 包装同步 IO)
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

# ── 数据模型 ──


@dataclass
class BlackboardMessage:
    """黑板消息实体。

    Attributes: msg_id(UUID), msg_type(finding|suggestion|warning|status|command|result),
    sender, content, target(IP/域名/URL), metadata(字典→JSON),
    pheromone_boost(信息素强度), timestamp, expires_at(None=不过期)。
    """
    msg_id: str
    msg_type: str
    sender: str
    content: str
    target: str = ""
    metadata: dict = field(default_factory=dict)
    pheromone_boost: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None


@dataclass
class MessageFilter:
    """消息查询过滤器，用于 query() 动态 SQL 条件拼接。"""
    msg_types: Optional[List[str]] = None
    senders: Optional[List[str]] = None
    target: Optional[str] = None
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    min_pheromone: float = 0.0


# ── SharedBlackboard 主类 ──


class SharedBlackboard:
    """M5 Swarm Link 共享黑板核心类。

    基于 SQLite 持久化 + 内存回调订阅的异步消息总线。
    Attributes: _db_path, _retention(保留小时), _lock(并发锁),
    _subscribers{msg_type: [(sub_id, callback), ...]}, _sub_counter。
    """
    def __init__(self, db_path: str = "./logs/blackboard.db", retention_hours: int = 24) -> None:
        self._db_path = db_path
        self._retention = retention_hours
        self._lock = asyncio.Lock()
        self._subscribers: Dict[str, List[tuple]] = {}
        self._sub_counter = 0
        self._init_db()

    # ── 内部工具 ──

    def _init_db(self) -> None:
        """初始化数据库: 创建 messages 表及索引。"""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    msg_id            TEXT PRIMARY KEY,
                    msg_type          TEXT NOT NULL,
                    sender            TEXT NOT NULL,
                    content           TEXT NOT NULL,
                    target            TEXT NOT NULL DEFAULT '',
                    metadata          TEXT NOT NULL DEFAULT '{}',
                    pheromone_boost   REAL NOT NULL DEFAULT 0.0,
                    timestamp         REAL NOT NULL,
                    expires_at        REAL
                )
            """)
            for col in ("timestamp", "msg_type", "target", "sender"):
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{col} ON messages({col})")
            conn.commit()
        finally:
            conn.close()

    def _cleanup_expired(self) -> int:
        """同步方法: 删除过期消息，返回删除数量。"""
        now = datetime.now().timestamp()
        conn = sqlite3.connect(self._db_path)
        try:
            cur = conn.execute(
                "DELETE FROM messages WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def _msg_to_dict(self, msg: BlackboardMessage) -> dict:
        """消息对象 → 可入库字典(datetime 转时间戳，metadata 转 JSON)。"""
        return {
            "msg_id": msg.msg_id,
            "msg_type": msg.msg_type,
            "sender": msg.sender,
            "content": msg.content,
            "target": msg.target,
            "metadata": json.dumps(msg.metadata, ensure_ascii=False),
            "pheromone_boost": msg.pheromone_boost,
            "timestamp": msg.timestamp.timestamp(),
            "expires_at": msg.expires_at.timestamp() if msg.expires_at else None,
        }

    def _dict_to_msg(self, row: sqlite3.Row) -> BlackboardMessage:
        """SQLite Row → 消息实体。"""
        expires = row["expires_at"]
        return BlackboardMessage(
            msg_id=row["msg_id"],
            msg_type=row["msg_type"],
            sender=row["sender"],
            content=row["content"],
            target=row["target"],
            metadata=json.loads(row["metadata"]),
            pheromone_boost=row["pheromone_boost"],
            timestamp=datetime.fromtimestamp(row["timestamp"]),
            expires_at=datetime.fromtimestamp(expires) if expires else None,
        )

    def _insert_sync(self, msg: BlackboardMessage) -> None:
        """同步方法: 将消息写入 SQLite。"""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """INSERT INTO messages (msg_id, msg_type, sender, content,
                target, metadata, pheromone_boost, timestamp, expires_at)
                VALUES (:msg_id, :msg_type, :sender, :content, :target,
                :metadata, :pheromone_boost, :timestamp, :expires_at)""",
                self._msg_to_dict(msg),
            )
            conn.commit()
        finally:
            conn.close()

    def _make_msg(
        self, msg_type: str, sender: str, content: str, target: str, metadata: dict
    ) -> BlackboardMessage:
        """工厂方法: 快速构造带默认过期时间的消息。"""
        return BlackboardMessage(
            msg_id=str(uuid.uuid4()),
            msg_type=msg_type,
            sender=sender,
            content=content,
            target=target,
            metadata=metadata,
            expires_at=datetime.now() + timedelta(hours=self._retention),
        )

    def _query_sync(
        self, filt: Optional[MessageFilter], limit: int, order: str
    ) -> List[BlackboardMessage]:
        """同步方法: 执行动态 SQL 查询。"""
        conditions: List[str] = []
        params: List[Any] = []
        if filt:
            if filt.msg_types:
                conditions.append(f"msg_type IN ({','.join('?' * len(filt.msg_types))})")
                params.extend(filt.msg_types)
            if filt.senders:
                conditions.append(f"sender IN ({','.join('?' * len(filt.senders))})")
                params.extend(filt.senders)
            if filt.target is not None:
                conditions.append("target = ?")
                params.append(filt.target)
            if filt.since:
                conditions.append("timestamp >= ?")
                params.append(filt.since.timestamp())
            if filt.until:
                conditions.append("timestamp <= ?")
                params.append(filt.until.timestamp())
            if filt.min_pheromone > 0:
                conditions.append("pheromone_boost >= ?")
                params.append(filt.min_pheromone)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sort = "DESC" if order.lower() == "desc" else "ASC"
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                f"SELECT * FROM messages {where} ORDER BY timestamp {sort} LIMIT ?",
                (*params, limit),
            )
            return [self._dict_to_msg(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # ── 发布 ──

    async def post(self, msg: BlackboardMessage) -> str:
        """发布消息到黑板: 写入 SQLite + 清理过期 + 通知订阅者。

        Args:
            msg: 待发布的消息实例。

        Returns:
            消息 msg_id。
        """
        if not msg.msg_id:
            msg.msg_id = str(uuid.uuid4())
        async with self._lock:
            await asyncio.to_thread(self._insert_sync, msg)
            await asyncio.to_thread(self._cleanup_expired)
        await self._notify_subscribers(msg)
        return msg.msg_id

    async def post_finding(self, sender: str, content: str, target: str = "",
                           metadata: Optional[dict] = None) -> str:
        """发布 finding(安全发现) 类型消息。"""
        return await self.post(self._make_msg("finding", sender, content, target, metadata or {}))

    async def post_suggestion(self, sender: str, content: str, target: str = "",
                              metadata: Optional[dict] = None) -> str:
        """发布 suggestion(建议) 类型消息。"""
        return await self.post(self._make_msg("suggestion", sender, content, target, metadata or {}))

    async def post_warning(self, sender: str, content: str, target: str = "",
                           metadata: Optional[dict] = None) -> str:
        """发布 warning(警告) 类型消息。"""
        return await self.post(self._make_msg("warning", sender, content, target, metadata or {}))

    async def post_status(self, sender: str, content: str, target: str = "",
                          metadata: Optional[dict] = None) -> str:
        """发布 status(状态) 类型消息。"""
        return await self.post(self._make_msg("status", sender, content, target, metadata or {}))

    async def post_command(self, sender: str, content: str, target: str = "",
                           recipient: str = "", metadata: Optional[dict] = None) -> str:
        """发布 command(命令) 类型消息。recipient 写入 metadata。"""
        meta = dict(metadata or {})
        if recipient:
            meta["recipient"] = recipient
        return await self.post(self._make_msg("command", sender, content, target, meta))

    async def post_result(self, sender: str, content: str, target: str = "",
                          command_id: str = "", metadata: Optional[dict] = None) -> str:
        """发布 result(结果) 类型消息。command_id 写入 metadata。"""
        meta = dict(metadata or {})
        if command_id:
            meta["command_id"] = command_id
        return await self.post(self._make_msg("result", sender, content, target, meta))

    # ── 查询 ──

    async def query(
        self, filter: Optional[MessageFilter] = None, limit: int = 100, order: str = "desc"
    ) -> List[BlackboardMessage]:
        """按过滤器动态查询消息。

        Args:
            filter: 消息过滤器，None 表示不过滤。
            limit: 返回最大数量。
            order: "desc" 或 "asc"。

        Returns:
            匹配的消息列表。
        """
        return await asyncio.to_thread(self._query_sync, filter, limit, order)

    async def get_recent(self, n: int = 50) -> List[BlackboardMessage]:
        """获取最近 n 条消息(按时间倒序)。"""
        return await self.query(limit=n, order="desc")

    async def get_by_target(self, target: str, limit: int = 50) -> List[BlackboardMessage]:
        """按目标精确匹配查询消息。"""
        return await self.query(filter=MessageFilter(target=target), limit=limit, order="desc")

    async def get_by_type(self, msg_type: str, limit: int = 50) -> List[BlackboardMessage]:
        """按消息类型查询消息。"""
        return await self.query(filter=MessageFilter(msg_types=[msg_type]), limit=limit, order="desc")

    async def get_timeline(self, target: str) -> List[BlackboardMessage]:
        """获取指定目标的完整时间线(按时间正序)。"""
        return await self.query(filter=MessageFilter(target=target), limit=1000, order="asc")

    async def get(self, msg_id: str) -> Optional[BlackboardMessage]:
        """按 msg_id 获取单条消息。"""
        def _get():
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.execute("SELECT * FROM messages WHERE msg_id = ?", (msg_id,))
                row = cur.fetchone()
                return self._dict_to_msg(row) if row else None
            finally:
                conn.close()
        return await asyncio.to_thread(_get)

    # ── 订阅 ──

    def subscribe(self, msg_type: str, callback: Callable) -> str:
        """订阅指定类型消息，"*" 表示订阅全部类型。

        Args:
            msg_type: 订阅的消息类型。
            callback: 回调函数，签名 callback(msg: BlackboardMessage)。

        Returns:
            订阅 ID(sub_id)。
        """
        self._sub_counter += 1
        sub_id = f"sub_{self._sub_counter}"
        self._subscribers.setdefault(msg_type, []).append((sub_id, callback))
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """取消指定订阅。

        Args:
            sub_id: 订阅时返回的 ID。

        Returns:
            是否成功找到并取消。
        """
        for msg_type, subs in list(self._subscribers.items()):
            for idx, (sid, _) in enumerate(subs):
                if sid == sub_id:
                    subs.pop(idx)
                    if not subs:
                        del self._subscribers[msg_type]
                    return True
        return False

    async def _notify_subscribers(self, msg: BlackboardMessage) -> None:
        """通知所有匹配订阅者，逐个捕获异常防止连锁故障。

        匹配规则: msg_type 精确匹配 或 通配符 "*" 订阅。
        支持同步和异步回调函数。
        """
        cbs = [cb for mt, subs in self._subscribers.items()
               if mt == msg.msg_type or mt == "*" for _, cb in subs]
        for cb in cbs:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(msg)
                else:
                    await asyncio.to_thread(cb, msg)
            except Exception:
                pass

    # ── 统计与清理 ──

    async def get_stats(self) -> dict:
        """获取黑板统计信息。

        Returns:
            包含 total_messages, by_type, by_sender, by_target,
            max_pheromone, avg_pheromone, expired_count 的字典。
        """
        def _stats():
            conn = sqlite3.connect(self._db_path)
            try:
                total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
                by_type = {r[0]: r[1] for r in conn.execute(
                    "SELECT msg_type, COUNT(*) FROM messages GROUP BY msg_type")}
                by_sender = {r[0]: r[1] for r in conn.execute(
                    "SELECT sender, COUNT(*) FROM messages GROUP BY sender")}
                by_target = {r[0]: r[1] for r in conn.execute(
                    "SELECT target, COUNT(*) FROM messages GROUP BY target")}
                phero = conn.execute(
                    "SELECT MAX(pheromone_boost), AVG(pheromone_boost) FROM messages"
                ).fetchone()
                expired = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE expires_at IS NOT NULL AND expires_at < ?",
                    (datetime.now().timestamp(),),
                ).fetchone()[0]
                return {
                    "total_messages": total, "by_type": by_type,
                    "by_sender": by_sender, "by_target": by_target,
                    "max_pheromone": phero[0] or 0.0,
                    "avg_pheromone": phero[1] or 0.0,
                    "expired_count": expired,
                }
            finally:
                conn.close()
        return await asyncio.to_thread(_stats)

    async def clear(self, older_than_hours: Optional[int] = None) -> int:
        """清理黑板消息。

        Args:
            older_than_hours: 仅删除超过指定小时数的消息; None 则清空全部。

        Returns:
            删除的消息数量。
        """
        def _clear():
            conn = sqlite3.connect(self._db_path)
            try:
                if older_than_hours is not None:
                    cutoff = (datetime.now() - timedelta(hours=older_than_hours)).timestamp()
                    cur = conn.execute("DELETE FROM messages WHERE timestamp < ?", (cutoff,))
                else:
                    cur = conn.execute("DELETE FROM messages")
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()
        return await asyncio.to_thread(_clear)
