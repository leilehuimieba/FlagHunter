"""
PentestAgent M1 API Hub - 数据模型定义

本模块定义了M1 API Hub（多Provider管理与健康检查模块）所需的全部数据模型，
包括Provider配置、状态枚举、运行时状态、请求日志、健康检查结果、降级链、
消耗汇总、模块配置以及状态变更事件。

使用Python标准库dataclass实现，无需外部依赖。
"""

from __future__ import annotations

__all__ = [
    "ProviderState",
    "ProviderConfig",
    "ProviderStatus",
    "RequestLog",
    "HealthCheckResult",
    "FallbackChain",
    "CostSummary",
    "M1Config",
    "ProviderEvent",
]

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class ProviderState(str, Enum):
    """Provider健康状态枚举。

    用于表示各个API Provider的当前运行状态，支持状态间的有序转换。

    Members:
        HEALTHY:    健康状态，服务正常运行
        DEGRADED:   降级状态，服务可用但响应变慢或不稳定
        DOWN:       宕机状态，服务不可用
        RECOVERING: 恢复中状态，正在进行恢复检查
        DISABLED:   已禁用状态，被人为禁用不参与调度
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    RECOVERING = "recovering"
    DISABLED = "disabled"

    @classmethod
    def emoji(cls, state: Optional[ProviderState] = None) -> str:
        """返回状态对应的emoji图标。

        Args:
            state: ProviderState枚举值，为None时返回空字符串

        Returns:
            str: 对应状态的emoji，🟢🟡🔴🟣⚪ 分别代表五种状态
        """
        mapping = {
            cls.HEALTHY: "🟢",
            cls.DEGRADED: "🟡",
            cls.DOWN: "🔴",
            cls.RECOVERING: "🟣",
            cls.DISABLED: "⚪",
        }
        if state is None:
            return ""
        return mapping.get(state, "⚪")


@dataclass
class ProviderConfig:
    """Provider配置信息。

    定义单个LLM API Provider的完整连接与调度参数，
    支持从环境变量批量加载配置。

    Attributes:
        id: Provider唯一标识符
        name: 显示名称
        model: 模型名称，如 "gpt-4"
        api_base: API基础URL
        api_key: API密钥
        timeout: 单次请求超时时间（秒），默认60
        max_retries: 最大重试次数，默认3
        rpm_limit: 每分钟最大请求数，默认60
        tpm_limit: 每分钟最大Token数，默认100000
        priority: 调度优先级（数字越小优先级越高），默认1
        enabled: 是否启用该Provider，默认True
        is_backup: 是否为备用Provider，默认False
        tags: 标签列表，用于分组与筛选
        cost_per_1k_input: 每1K输入Token的成本（美元），默认0.0
        cost_per_1k_output: 每1K输出Token的成本（美元），默认0.0
    """

    id: str
    name: str
    model: str
    api_base: str
    api_key: str
    timeout: int = 60
    max_retries: int = 3
    rpm_limit: int = 60
    tpm_limit: int = 100000
    priority: int = 1
    enabled: bool = True
    is_backup: bool = False
    tags: List[str] = field(default_factory=list)
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0

    @classmethod
    def from_env(cls, prefix: str) -> ProviderConfig:
        """从环境变量加载Provider配置。

        读取以指定前缀开头的环境变量作为配置项，
        必填字段缺失时抛出ValueError。

        Args:
            prefix: 环境变量前缀，如 "CPA_M1_PROVIDER_OPENAI_"

        Returns:
            ProviderConfig: 从环境变量构建的配置对象

        Raises:
            ValueError: 必填字段（id, name, model, api_base, api_key）缺失时抛出

        Example:
            >>> # 环境变量 CPA_M1_PROVIDER_OPENAI_ID=gpt4-provider
            >>> cfg = ProviderConfig.from_env("CPA_M1_PROVIDER_OPENAI_")
        """
        def _env(key: str, default: Optional[str] = None) -> Optional[str]:
            """辅助函数：读取指定环境变量。"""
            return os.environ.get(f"{prefix}{key}", default)

        # 必填字段
        required_fields = {
            "id": _env("ID"),
            "name": _env("NAME"),
            "model": _env("MODEL"),
            "api_base": _env("API_BASE"),
            "api_key": _env("API_KEY"),
        }
        missing = [k for k, v in required_fields.items() if not v]
        if missing:
            raise ValueError(
                f"ProviderConfig环境变量缺失: 前缀 '{prefix}' 缺少字段 {missing}"
            )

        # 解析tags
        tags_str = _env("TAGS", "")
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        return cls(
            id=required_fields["id"],  # type: ignore[arg-type]
            name=required_fields["name"],  # type: ignore[arg-type]
            model=required_fields["model"],  # type: ignore[arg-type]
            api_base=required_fields["api_base"],  # type: ignore[arg-type]
            api_key=required_fields["api_key"],  # type: ignore[arg-type]
            timeout=int(_env("TIMEOUT", "60")),  # type: ignore[arg-type]
            max_retries=int(_env("MAX_RETRIES", "3")),  # type: ignore[arg-type]
            rpm_limit=int(_env("RPM_LIMIT", "60")),  # type: ignore[arg-type]
            tpm_limit=int(_env("TPM_LIMIT", "100000")),  # type: ignore[arg-type]
            priority=int(_env("PRIORITY", "1")),  # type: ignore[arg-type]
            enabled=(_env("ENABLED", "true").lower() == "true"),  # type: ignore[arg-type]
            is_backup=(_env("IS_BACKUP", "false").lower() == "true"),  # type: ignore[arg-type]
            tags=tags,
            cost_per_1k_input=float(_env("COST_PER_1K_INPUT", "0.0")),  # type: ignore[arg-type]
            cost_per_1k_output=float(_env("COST_PER_1K_OUTPUT", "0.0")),  # type: ignore[arg-type]
        )


@dataclass
class ProviderStatus:
    """Provider运行时状态。

    记录单个Provider的实时运行指标与状态信息，
    用于健康检查与调度决策。

    Attributes:
        provider_id: 关联的Provider唯一标识符
        state: 当前健康状态，默认HEALTHY
        last_check_time: 最近一次健康检查时间
        last_success_time: 最近一次成功请求时间
        last_error: 最近一次错误信息
        response_time_ms: 最近一次响应耗时（毫秒）
        consecutive_failures: 连续失败次数
        consecutive_successes: 连续成功次数
        total_requests: 累计请求次数
        total_tokens: 累计Token消耗量
        estimated_cost_usd: 累计预估成本（美元）
    """

    provider_id: str
    state: ProviderState = ProviderState.HEALTHY
    last_check_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_error: str = ""
    response_time_ms: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_requests: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def is_available(self) -> bool:
        """判断Provider是否可用。

        当状态为HEALTHY或DEGRADED时认为Provider可用，
        可以参与请求调度。

        Returns:
            bool: Provider是否可用
        """
        return self.state in (ProviderState.HEALTHY, ProviderState.DEGRADED)

    def state_emoji(self) -> str:
        """返回当前状态对应的emoji图标。

        Returns:
            str: 状态emoji，如 🟢🟡🔴🟣⚪
        """
        return ProviderState.emoji(self.state)


@dataclass
class RequestLog:
    """API请求记录。

    记录单次API调用的完整信息，用于审计、监控与成本分析。

    Attributes:
        request_id: 请求唯一标识符
        provider_id: 使用的Provider ID
        model: 实际调用的模型名称
        prompt_tokens: 输入Token数量
        completion_tokens: 输出Token数量
        response_time_ms: 响应耗时（毫秒）
        success: 请求是否成功，默认True
        error_message: 错误信息（失败时填写）
        timestamp: 请求时间戳
        cost_usd: 该请求预估成本（美元）
        prompt_preview: 输入Prompt的预览文本（用于调试）
    """

    request_id: str
    provider_id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    response_time_ms: int
    success: bool = True
    error_message: str = ""
    timestamp: Optional[datetime] = None
    cost_usd: float = 0.0
    prompt_preview: str = ""


@dataclass
class HealthCheckResult:
    """健康检查结果。

    记录单次健康检查的详细结果，用于更新Provider状态。

    Attributes:
        provider_id: 被检查的Provider ID
        success: 检查是否通过
        response_time_ms: 检查请求的响应耗时（毫秒）
        error_message: 失败时的错误信息
        timestamp: 检查时间戳
    """

    provider_id: str
    success: bool
    response_time_ms: int
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class FallbackChain:
    """Provider降级链。

    定义当某个Provider不可用时，按序尝试的备用Provider列表。
    降级链按model_pattern匹配，支持精确匹配或通配符匹配。

    Attributes:
        model_pattern: 模型匹配模式，如 "gpt-4*" 或 "*"
        provider_ids: 有序的Provider ID列表，优先级从高到低
    """

    model_pattern: str
    provider_ids: List[str]

    def get_next(self, current_id: str) -> Optional[str]:
        """获取当前Provider的下一个备用Provider。

        在降级链中按顺序查找当前ID的下一个Provider，
        如果当前ID是列表中的最后一个，则返回None。

        Args:
            current_id: 当前Provider的唯一标识符

        Returns:
            Optional[str]: 下一个备用Provider的ID，若无则返回None

        Example:
            >>> chain = FallbackChain("gpt-4", ["p1", "p2", "p3"])
            >>> chain.get_next("p1")
            'p2'
            >>> chain.get_next("p3")
            None
        """
        try:
            idx = self.provider_ids.index(current_id)
        except ValueError:
            return None
        if idx + 1 < len(self.provider_ids):
            return self.provider_ids[idx + 1]
        return None


@dataclass
class CostSummary:
    """API调用消耗汇总。

    汇总一个会话周期内的API调用消耗情况，
    支持按Provider细分与预算告警。

    Attributes:
        session_start: 会话开始时间
        total_requests: 累计请求次数
        total_tokens: 累计Token消耗
        total_cost_usd: 累计成本（美元）
        by_provider: 按Provider汇分的消耗明细
        budget_usd: 预算上限（美元），None表示无限制
    """

    session_start: datetime = field(default_factory=datetime.now)
    total_requests: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    by_provider: Dict[str, Dict] = field(default_factory=dict)
    budget_usd: Optional[float] = None

    @property
    def budget_usage_ratio(self) -> float:
        """预算使用率（计算属性）。

        计算当前消耗占预算的百分比，
        当budget_usd为None时返回0.0。

        Returns:
            float: 预算使用比例，范围 [0.0, 1.0+]
        """
        if self.budget_usd is None or self.budget_usd <= 0:
            return 0.0
        return min(self.total_cost_usd / self.budget_usd, 1.0)

    def is_budget_alert(self, threshold: float = 0.8) -> bool:
        """检查是否触发预算告警。

        当预算使用率超过指定阈值时返回True。

        Args:
            threshold: 告警阈值，范围 (0.0, 1.0]，默认0.8

        Returns:
            bool: 是否超过告警阈值
        """
        if self.budget_usd is None:
            return False
        return self.budget_usage_ratio >= threshold


@dataclass
class M1Config:
    """M1 API Hub模块配置。

    定义M1模块的完整运行参数，包括健康检查策略、
    预算控制、Provider列表与降级链配置。

    Attributes:
        enabled: 模块是否启用，默认True
        health_check_interval: 健康检查间隔（秒），默认30
        health_check_timeout: 健康检查超时（秒），默认10
        health_check_prompt: 健康检查使用的Prompt文本
        fail_threshold: 触发降级的连续失败阈值，默认3
        recovery_check_interval: 恢复检查间隔（秒），默认60
        recovery_confirm_requests: 恢复确认所需的成功请求数，默认2
        daily_budget_usd: 每日预算上限（美元），None表示无限制
        budget_alert_threshold: 预算告警阈值，默认0.8
        providers: Provider配置列表
        fallback_chains: 降级链配置列表
    """

    enabled: bool = True
    health_check_interval: int = 30
    health_check_timeout: int = 10
    health_check_prompt: str = "Respond with OK"
    fail_threshold: int = 3
    recovery_check_interval: int = 60
    recovery_confirm_requests: int = 2
    daily_budget_usd: Optional[float] = None
    budget_alert_threshold: float = 0.8
    providers: List[ProviderConfig] = field(default_factory=list)
    fallback_chains: List[FallbackChain] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> M1Config:
        """从CPA_M1_*环境变量加载完整配置。

        读取所有以CPA_M1_为前缀的环境变量，
        自动解析Provider配置与降级链配置。

        Provider配置通过 _PROVIDER_ 前缀标识，
        如 CPA_M1_PROVIDER_OPENAI_ID, CPA_M1_PROVIDER_ANTHROPIC_ID 等。

        Returns:
            M1Config: 从环境变量构建的完整模块配置

        Example:
            >>> # export CPA_M1_ENABLED=true
            >>> # export CPA_M1_HEALTH_CHECK_INTERVAL=30
            >>> # export CPA_M1_PROVIDER_OPENAI_ID=openai-primary
            >>> cfg = M1Config.from_env()
        """
        prefix = "CPA_M1_"

        def _env(key: str, default: Optional[str] = None) -> Optional[str]:
            """辅助函数：读取CPA_M1_前缀的环境变量。"""
            return os.environ.get(f"{prefix}{key}", default)

        # 基础配置
        enabled = _env("ENABLED", "true").lower() == "true"  # type: ignore[union-attr]
        health_check_interval = int(_env("HEALTH_CHECK_INTERVAL", "30"))  # type: ignore[arg-type]
        health_check_timeout = int(_env("HEALTH_CHECK_TIMEOUT", "10"))  # type: ignore[arg-type]
        health_check_prompt = _env("HEALTH_CHECK_PROMPT", "Respond with OK")
        fail_threshold = int(_env("FAIL_THRESHOLD", "3"))  # type: ignore[arg-type]
        recovery_check_interval = int(_env("RECOVERY_CHECK_INTERVAL", "60"))  # type: ignore[arg-type]
        recovery_confirm_requests = int(_env("RECOVERY_CONFIRM_REQUESTS", "2"))  # type: ignore[arg-type]

        daily_budget = _env("DAILY_BUDGET_USD")
        daily_budget_usd = float(daily_budget) if daily_budget else None  # type: ignore[arg-type]
        budget_alert_threshold = float(_env("BUDGET_ALERT_THRESHOLD", "0.8"))  # type: ignore[arg-type]

        # 解析Provider配置
        providers: List[ProviderConfig] = []
        provider_prefixes = set()
        for key in os.environ:
            if key.startswith(f"{prefix}PROVIDER_") and key.endswith("_ID"):
                provider_name = key[len(f"{prefix}PROVIDER_") : -len("_ID")]
                provider_prefix = f"{prefix}PROVIDER_{provider_name}_"
                provider_prefixes.add(provider_name)

        for name in provider_prefixes:
            try:
                provider_cfg = ProviderConfig.from_env(
                    f"{prefix}PROVIDER_{name}_"
                )
                providers.append(provider_cfg)
            except ValueError:
                # 配置不完整时跳过
                continue

        # 解析降级链（通过逗号分隔的Provider ID列表）
        fallback_chains: List[FallbackChain] = []
        fb_index = 1
        while True:
            pattern = _env(f"FALLBACK_{fb_index}_PATTERN")
            ids_str = _env(f"FALLBACK_{fb_index}_IDS")
            if not pattern or not ids_str:
                break
            provider_ids = [pid.strip() for pid in ids_str.split(",") if pid.strip()]
            if provider_ids:
                fallback_chains.append(
                    FallbackChain(model_pattern=pattern, provider_ids=provider_ids)
                )
            fb_index += 1

        return cls(
            enabled=enabled,
            health_check_interval=health_check_interval,
            health_check_timeout=health_check_timeout,
            health_check_prompt=health_check_prompt,  # type: ignore[arg-type]
            fail_threshold=fail_threshold,
            recovery_check_interval=recovery_check_interval,
            recovery_confirm_requests=recovery_confirm_requests,
            daily_budget_usd=daily_budget_usd,
            budget_alert_threshold=budget_alert_threshold,
            providers=providers,
            fallback_chains=fallback_chains,
        )


@dataclass
class ProviderEvent:
    """Provider状态变更事件。

    记录Provider状态转换的完整信息，用于事件通知与审计追踪。

    Attributes:
        event_type: 事件类型，如 "state_changed", "health_check_failed" 等
        provider_id: 发生事件的Provider ID
        old_state: 变更前的状态（可选）
        new_state: 变更后的状态（可选）
        message: 事件描述信息
        timestamp: 事件发生时间
    """

    event_type: str
    provider_id: str
    old_state: Optional[ProviderState] = None
    new_state: Optional[ProviderState] = None
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


# ──────────────────────────────────────────────────────────────
# 便捷辅助函数
# ──────────────────────────────────────────────────────────────

def calculate_request_cost(
    prompt_tokens: int,
    completion_tokens: int,
    cost_per_1k_input: float,
    cost_per_1k_output: float,
) -> float:
    """计算单次请求的成本。

    根据输入输出Token数量及单价计算请求成本。

    Args:
        prompt_tokens: 输入Token数量
        completion_tokens: 输出Token数量
        cost_per_1k_input: 每1K输入Token单价（美元）
        cost_per_1k_output: 每1K输出Token单价（美元）

    Returns:
        float: 预估请求成本（美元）
    """
    input_cost = (prompt_tokens / 1000.0) * cost_per_1k_input
    output_cost = (completion_tokens / 1000.0) * cost_per_1k_output
    return round(input_cost + output_cost, 6)
