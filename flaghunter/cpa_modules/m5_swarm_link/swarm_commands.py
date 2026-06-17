"""
M5 Swarm Link — /swarm 系列命令实现。

所有命令函数均返回 ``str``，供上层命令调度器直接回显给用户。
命令依赖 :func:`flaghunter.cpa_modules.m5_swarm_link.is_m5_enabled` 与各类 getter，
在模块未启用时返回友好提示而非抛出异常。

用法::
    from flaghunter.cpa_modules.m5_swarm_link.swarm_commands import cmd_swarm, cmd_swarm_status
    reply: str = await cmd_swarm(agent_id="agent-01")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import (
    get_blackboard,
    get_consensus_mechanism,
    get_messenger,
    get_pheromone_router,
    is_m5_enabled,
)

if TYPE_CHECKING:
    from .shared_blackboard import SharedBlackboard
    from .pheromone_router import PheromoneRouter
    from .agent_messenger import AgentMessenger
    from .consensus_mechanism import ConsensusMechanism

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_NOT_ENABLED: str = (
    "[M5 Swarm Link] 模块未启用。"
    "设置环境变量 CPA_M5_SWARM_LINK=true 后重启 Agent。"
)
_NOT_INITIALIZED: str = (
    "[M5 Swarm Link] 模块尚未初始化完成，请稍后再试。"
)
_HEADER: str = "\n╔══════════════════════════════════════════════════════════════╗\n║            🐜  M5 Swarm Link — 群体智能协作层              ║\n╚══════════════════════════════════════════════════════════════╝\n"


def _check() -> bool:
    """内部辅助：检查模块是否已启用且初始化完成。"""
    return is_m5_enabled()


# ═══════════════════════════════════════════════════════════════════════════
# 1. /swarm — 总览状态
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm(agent_id: str = "") -> str:
    """显示 Swarm Link 整体状态。

    Args:
        agent_id: 调用者 Agent 标识（用于上下文展示）。

    Returns:
        格式化状态字符串。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        router: PheromoneRouter = get_pheromone_router()
        board: SharedBlackboard = get_blackboard()

        stats = await router.get_stats()
        board_stats = await board.get_stats()

        lines: list[str] = [_HEADER]
        lines.append("● 模块状态: 运行中")
        lines.append(f"● 当前Agent: {agent_id or '未指定'}")
        lines.append(f"● 活跃目标: {stats['active_trails']}")
        lines.append(f"● 信息素总量: {stats['total_strength']:.3f}")
        lines.append(f"● 黑板消息数: {board_stats['total_messages']}")
        lines.append(f"● 衰减率: {stats['decay_rate']}")
        lines.append(f"● 阈值: {stats['threshold']}")
        lines.append("\n💡 提示: 使用 /swarm status 查看详情，/swarm top 查看优先级目标。\n")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("cmd_swarm 异常: %s", exc, exc_info=True)
        return f"[M5] 状态获取失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. /swarm status — 详细统计
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_status(agent_id: str = "") -> str:
    """显示信息素统计与活跃目标详情。

    Args:
        agent_id: 调用者 Agent 标识。

    Returns:
        包含表格格式的统计字符串。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        router: PheromoneRouter = get_pheromone_router()
        board: SharedBlackboard = get_blackboard()

        lines: list[str] = [
            "\n┌───────────────── M5 信息素统计 ─────────────────┐",
        ]

        trails = await router.get_active_trails()
        if trails:
            lines.append(f"\n{'目标':<20} {'信息素':>8}")
            lines.append("─" * 34)
            for trail in trails:
                lines.append(f"{trail.target:<20} {trail.current_strength:>8.3f}")
        else:
            lines.append("\n（暂无活跃目标）")

        board_stats = await board.get_stats()
        lines.append("\n\n┌───────────────── 黑板概览 ─────────────────┐")
        lines.append(f"  数据库: {board._db_path}")
        lines.append(f"  消息总数: {board_stats['total_messages']}")
        lines.append(f"  保留策略: {board._retention}h")

        lines.append("\n" + "─" * 46 + "\n")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("cmd_swarm_status 异常: %s", exc, exc_info=True)
        return f"[M5] 统计获取失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. /swarm top — Top 5 目标
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_top(agent_id: str = "", top_n: int = 5) -> str:
    """显示信息素值 Top N 的优先目标。

    Args:
        agent_id: 调用者 Agent 标识。
        top_n: 显示数量（默认 5）。

    Returns:
        排名表格字符串。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        router: PheromoneRouter = get_pheromone_router()
        top_targets = await router.get_top_targets(n=top_n)

        lines: list[str] = [
            f"\n┌────────────── 信息素 Top {top_n} 目标 ──────────────┐",
            f"\n{'排名':<4} {'目标':<22} {'信息素':>10} {'强度':>8}",
            "─" * 50,
        ]

        if not top_targets:
            lines.append("（暂无目标）")
        else:
            for rank, (target, value) in enumerate(top_targets, 1):
                strength: str = "■■■" if value > 1.0 else "■■" if value > 0.5 else "■"
                lines.append(f"{rank:<4} {target:<22} {value:>10.3f} {strength:>8}")

        lines.append("\n" + "─" * 50 + "\n")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("cmd_swarm_top 异常: %s", exc, exc_info=True)
        return f"[M5] Top 目标获取失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 4. /swarm deposit <target> — 手动释放信息素
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_deposit(agent_id: str, target: str, amount: float = 1.0) -> str:
    """手动向指定目标释放信息素。

    Args:
        agent_id: 调用者 Agent 标识。
        target: 目标标识（如域名、路径、IP）。
        amount: 释放量（默认 1.0）。

    Returns:
        操作结果字符串。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        router: PheromoneRouter = get_pheromone_router()
        await router.deposit(target=target, source=agent_id, strength=amount)
        return (
            f"[M5] ✅ Agent '{agent_id}' 已向目标 '{target}' "
            f"释放信息素 +{amount:.2f}。"
        )
    except Exception as exc:
        logger.warning("cmd_swarm_deposit 异常: %s", exc, exc_info=True)
        return f"[M5] 信息素释放失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. /swarm board — 查看黑板最近消息
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_board(agent_id: str = "", limit: int = 10) -> str:
    """查看共享黑板最近消息。

    Args:
        agent_id: 调用者 Agent 标识。
        limit: 返回消息数量上限（默认 10）。

    Returns:
        格式化消息列表。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        board: SharedBlackboard = get_blackboard()
        messages = await board.get_recent(n=limit)

        lines: list[str] = [
            f"\n┌────────────── 黑板最近 {limit} 条消息 ──────────────┐",
        ]

        if not messages:
            lines.append("\n（黑板为空）")
        else:
            for msg in messages:
                ts: str = str(msg.timestamp)
                sender: str = msg.sender
                content: str = msg.content
                lines.append(f"\n  [{ts}] <{sender}>")
                display: str = content[:120] + "..." if len(content) > 120 else content
                lines.append(f"      {display}")

        lines.append("\n" + "─" * 48 + "\n")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("cmd_swarm_board 异常: %s", exc, exc_info=True)
        return f"[M5] 黑板读取失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 6. /swarm board query <type> — 按类型查询黑板
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_board_query(agent_id: str, msg_type: str, limit: int = 10) -> str:
    """按消息类型查询黑板。

    Args:
        agent_id: 调用者 Agent 标识。
        msg_type: 消息类型（如 'finding', 'vote', 'status', 'command'）。
        limit: 返回数量上限（默认 10）。

    Returns:
        过滤后的消息列表。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        board: SharedBlackboard = get_blackboard()
        messages = await board.get_by_type(msg_type=msg_type, limit=limit)

        lines: list[str] = [
            f"\n┌────────────── 黑板查询: type={msg_type} ──────────────┐",
        ]

        if not messages:
            lines.append(f"\n（无类型为 '{msg_type}' 的消息）")
        else:
            for msg in messages:
                ts: str = str(msg.timestamp)
                sender: str = msg.sender
                content: str = msg.content
                lines.append(f"\n  [{ts}] <{sender}> {content[:100]}")

        lines.append(f"\n  共 {len(messages)} 条\n")
        lines.append("─" * 48 + "\n")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("cmd_swarm_board_query 异常: %s", exc, exc_info=True)
        return f"[M5] 黑板查询失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 7. /swarm propose <question> — 发起共识投票
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_propose(agent_id: str, question: str) -> str:
    """发起共识投票提案（二元 yes/no 投票）。

    Args:
        agent_id: 调用者 Agent 标识。
        question: 投票问题描述。

    Returns:
        包含投票结果摘要的字符串。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        consensus: ConsensusMechanism = get_consensus_mechanism(agent_id)
        result = await consensus.propose_binary(question=question)
        reached = result.get("consensus_reached", False)
        winner = result.get("winner", "N/A")
        agents = result.get("participating_agents", 0)
        return (
            f"[M5] 📋 共识投票已结束\n"
            f"     问题: {question}\n"
            f"     参与Agent数: {agents}\n"
            f"     获胜选项: {winner}\n"
            f"     共识达成: {'✅ 是' if reached else '❌ 否'}"
        )
    except Exception as exc:
        logger.warning("cmd_swarm_propose 异常: %s", exc, exc_info=True)
        return f"[M5] 提案发起失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 8. /swarm vote <vote_id> <choice> — 投票
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_vote(agent_id: str, vote_id: str, choice: str) -> str:
    """对指定提案投票。

    Args:
        agent_id: 调用者 Agent 标识。
        vote_id: 提案唯一ID。
        choice: 投票选项。

    Returns:
        投票结果字符串。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        consensus: ConsensusMechanism = get_consensus_mechanism(agent_id)
        await consensus.vote(vote_id=vote_id, choice=choice)
        return (
            f"[M5] 🗳️ 投票已记录\n"
            f"     Agent '{agent_id}' 对提案 '{vote_id}' 投票: '{choice}'"
        )
    except Exception as exc:
        logger.warning("cmd_swarm_vote 异常: %s", exc, exc_info=True)
        return f"[M5] 投票失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 9. /swarm consensus <targets...> — 目标优先级排序共识
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_consensus(agent_id: str, targets: list[str]) -> str:
    """发起目标优先级排序共识。

    Args:
        agent_id: 调用者 Agent 标识。
        targets: 待排序目标列表。

    Returns:
        排序结果或等待信息。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        consensus: ConsensusMechanism = get_consensus_mechanism(agent_id)
        result = await consensus.propose_priority_ranking(targets=targets)
        reached = result.get("consensus_reached", False)
        ranking: list[str] = result.get("ranking", targets)

        return (
            f"[M5] 📊 目标优先级共识已完成\n"
            f"     排序结果: {' > '.join(ranking)}\n"
            f"     共识达成: {'✅ 是' if reached else '❌ 否'}\n"
            f"     {result.get('details', '')}"
        )
    except Exception as exc:
        logger.warning("cmd_swarm_consensus 异常: %s", exc, exc_info=True)
        return f"[M5] 排序共识失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 10. /swarm msg <content> — 发送消息到黑板
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_msg(agent_id: str, content: str) -> str:
    """发送消息到共享黑板。

    Args:
        agent_id: 调用者 Agent 标识。
        content: 消息内容。

    Returns:
        发送结果字符串。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        messenger: AgentMessenger = get_messenger(agent_id)
        await messenger.send(msg_type="command", content=content)
        return f"[M5] 📢 消息已发送到黑板: '{content[:60]}{'...' if len(content) > 60 else ''}'"
    except Exception as exc:
        logger.warning("cmd_swarm_msg 异常: %s", exc, exc_info=True)
        return f"[M5] 消息发送失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 11. /swarm join <group> — 加入通信组
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_join(agent_id: str, group: str) -> str:
    """Agent 加入指定通信组。

    Args:
        agent_id: 调用者 Agent 标识。
        group: 通信组名称。

    Returns:
        加入结果字符串。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        messenger: AgentMessenger = get_messenger(agent_id)
        await messenger.join_group(group)
        return f"[M5] ✅ Agent '{agent_id}' 已加入通信组 '{group}'。"
    except Exception as exc:
        logger.warning("cmd_swarm_join 异常: %s", exc, exc_info=True)
        return f"[M5] 加入通信组失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 12. /swarm leave <group> — 离开通信组
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_leave(agent_id: str, group: str) -> str:
    """Agent 离开指定通信组。

    Args:
        agent_id: 调用者 Agent 标识。
        group: 通信组名称。

    Returns:
        离开结果字符串。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        messenger: AgentMessenger = get_messenger(agent_id)
        await messenger.leave_group(group)
        return f"[M5] ✅ Agent '{agent_id}' 已离开通信组 '{group}'。"
    except Exception as exc:
        logger.warning("cmd_swarm_leave 异常: %s", exc, exc_info=True)
        return f"[M5] 离开通信组失败: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 13. /swarm reset — 重置所有信息素
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_swarm_reset(agent_id: str = "") -> str:
    """重置所有信息素数据。

    警告：此操作不可撤销！

    Args:
        agent_id: 调用者 Agent 标识（用于审计日志）。

    Returns:
        重置结果字符串。
    """
    if not _check():
        return _NOT_ENABLED
    try:
        router: PheromoneRouter = get_pheromone_router()
        await router.reset()
        return (
            f"[M5] 🔄 所有信息素已重置（操作者: {agent_id or 'unknown'}）。\n"
            f"     活跃目标与信息素表已清空。"
        )
    except Exception as exc:
        logger.warning("cmd_swarm_reset 异常: %s", exc, exc_info=True)
        return f"[M5] 重置失败: {exc}"
