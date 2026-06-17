"""
FlagHunter M1 API Hub - TUI状态面板渲染器

纯文本输出（不依赖rich库），使用Unicode框线字符渲染
API Hub的完整状态面板与紧凑状态行，支持事件日志显示。

Python 3.10+
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import List, Optional

from .models import ProviderConfig, ProviderState, ProviderStatus
from .provider_manager import ProviderManager
from .cost_tracker import CostTracker


class StatusDisplay:
    """M1模块TUI状态面板渲染器 — 纯文本输出，不依赖rich库。"""

    # 面板列宽定义（不含边框和间距）
    _COL_NAME_W = 18       # Provider名称
    _COL_STATE_W = 7       # 状态(emoji+中文)
    _COL_RESP_W = 6        # 响应时间
    _COL_REQ_W = 6         # 请求数
    _COL_TOK_W = 7         # Tokens
    _COL_COST_W = 8        # 消耗金额

    # 中文状态名映射
    _STATE_NAME = {
        ProviderState.HEALTHY:    "健康",
        ProviderState.DEGRADED:   "降级",
        ProviderState.DOWN:       "故障",
        ProviderState.RECOVERING: "恢复中",
        ProviderState.DISABLED:   "禁用",
    }

    def __init__(self, provider_manager: ProviderManager, cost_tracker: CostTracker) -> None:
        """
        初始化StatusDisplay。

        Args:
            provider_manager: Provider调度管理器实例
            cost_tracker: 成本追踪器实例
        """
        self._pm = provider_manager
        self._ct = cost_tracker
        self._event_log: deque = deque(maxlen=50)  # 最多50条事件记录

    # ──────────────────────────────────────────────────────────
    # 公共接口
    # ──────────────────────────────────────────────────────────

    def render_full_panel(self) -> str:
        """
        渲染完整的API Hub状态面板。

        使用Unicode框线字符绘制表格，包含：
        - Provider列表（名称/状态/响应时间/请求数/Tokens/消耗）
        - 当前活跃Provider信息
        - 会话消耗统计
        - 预算状态
        - 最近事件日志

        Returns:
            str: 多行字符串，可直接打印到终端
        """
        lines: List[str] = []

        # ── 顶部标题 ──
        lines.append(self._header("API Hub 状态面板"))

        # ── 表头 ──
        header = (
            f"{'Provider':^{self._COL_NAME_W}}"
            f"{'状态':^{self._COL_STATE_W}}"
            f"{'响应':^{self._COL_RESP_W}}"
            f"{'请求':^{self._COL_REQ_W}}"
            f"{'Tokens':^{self._COL_TOK_W}}"
            f"{'消耗':^{self._COL_COST_W}}"
        )
        lines.append(self._row(header))
        lines.append(self._sep_line())

        # ── Provider数据行 ──
        providers = self._pm.list_providers()
        for config in providers:
            status = self._pm.get_status(config.id)
            if status is not None:
                lines.append(self._row(self._format_provider_row(config, status)))
            else:
                # 状态缺失时显示为未知
                lines.append(
                    self._row(
                        f"{config.name:<{self._COL_NAME_W}}"
                        f"{'⚪未知':^{self._COL_STATE_W}}"
                        f"{'---':^{self._COL_RESP_W}}"
                        f"{'0':^{self._COL_REQ_W}}"
                        f"{'0':^{self._COL_TOK_W}}"
                        f"{'$0.00':^{self._COL_COST_W}}"
                    )
                )

        # ── 分隔线 ──
        lines.append(self._double_sep_line())

        # ── 当前活跃Provider ──
        active = self._pm.get_active_provider()
        active_name = active.name if active else "无可用Provider"
        lines.append(self._row(f"当前使用: {active_name}"))

        # ── 会话消耗统计 ──
        summary = self._ct.get_session_summary()
        total_req = summary.get("total_requests", 0)
        total_tok = summary.get("total_tokens", 0)
        total_cost = summary.get("total_cost", 0.0)
        tok_str = self._format_tokens(total_tok)
        lines.append(
            self._row(
                f"会话消耗: {total_req}次请求 / {tok_str} tokens / ${total_cost:.2f}"
            )
        )

        # ── 预算状态 ──
        consumed_usd, budget_usd, _ = self._ct.get_daily_usage()
        budget_line = self._format_budget_line(consumed_usd, budget_usd)
        lines.append(self._row(budget_line))

        # ── 事件日志分隔线 ──
        lines.append(self._double_sep_line())

        # ── 事件日志 ──
        if self._event_log:
            for evt in self._event_log:
                lines.append(self._row(evt))
        else:
            lines.append(self._row("暂无事件记录"))

        # ── 底部边框 ──
        lines.append(self._footer())

        return "\n".join(lines)

    def render_compact_line(self) -> str:
        """
        渲染紧凑状态行（适合显示在TUI底部状态栏）。

        格式如: [API:🟢中转站A-Claude $5.00/$50 89req]

        Returns:
            str: 单行紧凑状态字符串
        """
        active = self._pm.get_active_provider()
        if active is None:
            return "[API:⚪无可用Provider]"

        # 活跃Provider状态
        status = self._pm.get_status(active.id)
        emoji = ProviderState.emoji(status.state) if status else "⚪"

        # 消耗信息
        summary = self._ct.get_session_summary()
        total_cost = summary.get("total_cost", 0.0)
        total_req = summary.get("total_requests", 0)

        # 预算
        _, budget_usd, _ = self._ct.get_daily_usage()
        budget_str = f"/{budget_usd:.0f}" if budget_usd else "/∞"

        return (
            f"[API:{emoji}{active.name} "
            f"${total_cost:.2f}{budget_str} {total_req}req]"
        )

    def add_event(self, message: str) -> None:
        """
        添加一条事件记录到事件日志，带时间戳。

        事件日志最多保留50条（deque maxlen=50），
        超出时自动丢弃最旧记录。

        Args:
            message: 事件描述文本
        """
        ts = datetime.now().strftime("%H:%M:%S")
        self._event_log.append(f"[{ts}] {message}")

    # ──────────────────────────────────────────────────────────
    # 格式化辅助方法
    # ──────────────────────────────────────────────────────────

    def _format_provider_row(self, config: ProviderConfig, status: ProviderStatus) -> str:
        """
        格式化单个Provider的数据行，供render_full_panel使用。

        将Provider配置和运行时状态格式化为对齐的文本行，包含：
        - Provider显示名称
        - 状态（emoji + 中文）
        - 响应时间（秒，如 "1.2s"）
        - 累计请求数
        - 累计Tokens（K为单位）
        - 累计消耗金额

        Args:
            config: Provider静态配置
            status: Provider运行时状态

        Returns:
            str: 对齐后的数据行字符串（不含边框）
        """
        name = config.name[:self._COL_NAME_W]  # 截断过长名称
        state_str = self._format_state(status.state)

        # 响应时间：ms 转 s 显示
        if status.response_time_ms > 0:
            resp_s = status.response_time_ms / 1000.0
            resp_str = f"{resp_s:.1f}s"
        else:
            resp_str = "---"

        req_str = f"{status.total_requests}"
        tok_str = self._format_tokens(status.total_tokens)
        cost_str = f"${status.estimated_cost_usd:.2f}"

        return (
            f"{name:<{self._COL_NAME_W}}"
            f"{state_str:^{self._COL_STATE_W}}"
            f"{resp_str:^{self._COL_RESP_W}}"
            f"{req_str:^{self._COL_REQ_W}}"
            f"{tok_str:^{self._COL_TOK_W}}"
            f"{cost_str:^{self._COL_COST_W}}"
        )

    def _format_state(self, state: ProviderState) -> str:
        """
        格式化状态显示。

        将ProviderState枚举转换为 emoji+中文 的显示形式：
        - HEALTHY    -> 🟢健康
        - DEGRADED   -> 🟡降级
        - DOWN       -> 🔴故障
        - RECOVERING -> 🟣恢复中
        - DISABLED   -> ⚪禁用

        Args:
            state: Provider状态枚举值

        Returns:
            str: 格式化后的状态字符串
        """
        emoji = ProviderState.emoji(state)
        name = self._STATE_NAME.get(state, "未知")
        return f"{emoji}{name}"

    # ──────────────────────────────────────────────────────────
    # 面板绘制辅助方法
    # ──────────────────────────────────────────────────────────

    def _header(self, title: str) -> str:
        """生成顶部标题框线。"""
        inner_w = self._inner_width()
        # 标题居中，左右用═填充
        pad = inner_w - len(title) - 2  # 左右各留一个空格
        left = pad // 2
        right = pad - left
        return f"╔{'═' * left} {title} {'═' * right}╗"

    def _footer(self) -> str:
        """生成底部框线。"""
        inner_w = self._inner_width()
        return f"╚{'═' * inner_w}╝"

    def _row(self, content: str) -> str:
        """将内容包装为║ ... ║ 形式，不足宽度时右补空格。"""
        inner_w = self._inner_width()
        # 处理ANSI转义序列宽度计算（简单处理，假设无ANSI）
        visible_len = len(content)
        pad = inner_w - visible_len
        if pad < 0:
            # 内容超长时截断
            content = content[:inner_w]
            pad = 0
        return f"║{content}{' ' * pad}║"

    def _sep_line(self) -> str:
        """生成内部分隔线（单线）。"""
        inner_w = self._inner_width()
        return f"║{'─' * inner_w}║"

    def _double_sep_line(self) -> str:
        """生成双线分隔线（╠...╣）。"""
        inner_w = self._inner_width()
        return f"╠{'═' * inner_w}╣"

    def _inner_width(self) -> int:
        """
        计算面板内部可用宽度。

        为所有列宽之和加上列间间距（每列间1个空格）。

        Returns:
            int: 内部宽度（字符数）
        """
        cols = [
            self._COL_NAME_W,
            self._COL_STATE_W,
            self._COL_RESP_W,
            self._COL_REQ_W,
            self._COL_TOK_W,
            self._COL_COST_W,
        ]
        # 列之间1个空格
        return sum(cols) + len(cols) - 1

    # ──────────────────────────────────────────────────────────
    # 工具方法
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _format_tokens(token_count: int) -> str:
        """
        将Token数格式化为人类可读形式。

        - 小于1000时直接返回数字
        - 大于等于1000时转为K单位（如 12000 -> "12K"）

        Args:
            token_count: Token数量

        Returns:
            str: 格式化后的Token字符串
        """
        if token_count < 1000:
            return str(token_count)
        return f"{token_count // 1000}K"

    def _format_budget_line(self, consumed_usd: float, budget_usd: Optional[float]) -> str:
        """
        格式化预算状态行。

        根据消耗与预算比例返回带状态指示的字符串：
        - 预算使用率 < 80% : 🟢 正常
        - 预算使用率 >= 80% : 🟡 告警
        - 预算使用率 >= 100%: 🔴 超支
        - 无预算限制       : ⚪ 无预算

        Args:
            consumed_usd: 已消耗金额（USD）
            budget_usd: 预算上限（USD），None表示无限制

        Returns:
            str: 格式化的预算状态行
        """
        if budget_usd is None or budget_usd <= 0:
            return f"预算状态: ⚪ 无预算 (已用 ${consumed_usd:.2f})"

        ratio = consumed_usd / budget_usd
        pct = ratio * 100

        if ratio >= 1.0:
            emoji, status = "🔴", "超支"
        elif ratio >= 0.8:
            emoji, status = "🟡", "告警"
        else:
            emoji, status = "🟢", "正常"

        return (
            f"预算状态: {emoji} {status} "
            f"(已用 {pct:.0f}% / 限额 ${budget_usd:.0f})"
        )
