"""
FlagHunter M1 API Hub — 配置解析模块 (config_schema.py)

功能：
    - 定义 ProviderConfig / FallbackChain / M1Config 三个数据模型
    - 从环境变量批量解析 Provider 配置
    - 自动扫描编号递增的 Provider 前缀（CPA_PROVIDER_0_, CPA_PROVIDER_1_ …）
    - 解析模块级配置（健康检查、预算、降级链等）

约束：
    - Python 3.10+, 纯标准库（os, re, typing），零外部依赖
    - 每个函数均带有中文 docstring

用法示例：
    >>> from config_schema import load_m1_config_from_env
    >>> config = load_m1_config_from_env()
    >>> print(config.providers[0].name)
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ===========================================================================
# 数据模型
# ===========================================================================

@dataclass
class ProviderConfig:
    """单个 LLM Provider 的完整配置。"""
    id: str; name: str; model: str; api_base: str; api_key: str
    timeout: int = 60; max_retries: int = 3; rpm_limit: int = 60; tpm_limit: int = 100000
    priority: int = 1; enabled: bool = True; is_backup: bool = False
    tags: List[str] = field(default_factory=list)
    cost_per_1k_input: float = 0.0; cost_per_1k_output: float = 0.0
    headers: Dict[str, str] = field(default_factory=dict)  # 额外 HTTP 请求头（如 User-Agent）


@dataclass
class FallbackChain:
    """降级链路：当某类模型不可用时按序切换的 Provider 列表。"""
    model_pattern: str; provider_ids: List[str] = field(default_factory=list)


@dataclass
class M1Config:
    """M1 API Hub 的全局模块配置。"""
    enabled: bool = True; health_check_interval: int = 30; health_check_timeout: int = 10
    health_check_prompt: str = "Respond with OK"; fail_threshold: int = 3
    recovery_check_interval: int = 60; recovery_confirm_requests: int = 2
    daily_budget_usd: Optional[float] = None; budget_alert_threshold: float = 0.8
    providers: List[ProviderConfig] = field(default_factory=list)
    fallback_chains: List[FallbackChain] = field(default_factory=list)


# ===========================================================================
# 内部工具函数
# ===========================================================================

def _str_to_bool(value: str) -> bool:
    """将字符串转换为布尔值，支持 "true"/"false"/"1"/"0"/"yes"/"on"（不区分大小写）。"""
    return value.strip().lower() in ("true", "1", "yes", "on")


def _safe_int(value: str, default: int) -> int:
    """安全地将字符串转为整数，失败时返回默认值。"""
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return default


def _safe_float(value: str, default: float) -> float:
    """安全地将字符串转为浮点数，失败时返回默认值。"""
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return default


def _str_to_list(value: str) -> List[str]:
    """将逗号分隔的字符串转为列表，去除空白并过滤空串。例："claude,中转站A" -> ["claude", "中转站A"。]"""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


# ===========================================================================
# 环境变量解析函数
# ===========================================================================

def _parse_env_dict(prefix: str) -> Dict[str, str]:
    """从 os.environ 中提取所有以 prefix 开头的环境变量，去掉 prefix 后返回字典。

    遍历所有环境变量键，若键名以 prefix 开头，则去掉 prefix 后转为大写作为键。

    参数:
        prefix: 环境变量前缀，例如 "CPA_PROVIDER_0_"。

    返回:
        去掉前缀后的键值字典。例如 {"ID": "x", "NAME": "y"。}
    """
    result: Dict[str, str] = {}
    for key, val in os.environ.items():
        if key.startswith(prefix):
            result[key[len(prefix):].upper()] = val
    return result


def load_provider_from_env(prefix: str) -> ProviderConfig:
    """从环境变量中加载单个 ProviderConfig。

    调用 _parse_env_dict 提取字段后映射到 ProviderConfig。
    必填字段（ID, NAME, MODEL, API_BASE, API_KEY）缺失时抛出 ValueError。
    可选字段使用默认值；布尔字段支持 "true"/"false"/"1"/"0"；列表字段（tags）按逗号拆分。

    参数:
        prefix: Provider 的环境变量前缀，例如 "CPA_PROVIDER_0_"。

    返回:
        解析后的 ProviderConfig 实例。

    异常:
        ValueError: 任一必填字段缺失时抛出，并指明缺失字段名。
    """
    env = _parse_env_dict(prefix)
    required = ["ID", "NAME", "MODEL", "API_BASE", "API_KEY"]
    missing = [f for f in required if f not in env]
    if missing:
        raise ValueError(f"Provider 前缀 '{prefix}' 缺少必填字段: {', '.join(missing)}")

    # 解析 HEADERS: "User-Agent:claude-code/1.0,X-Foo:bar"
    headers: Dict[str, str] = {}
    for pair in _str_to_list(env.get("HEADERS", "")):
        if ":" in pair:
            hk, _, hv = pair.partition(":")
            headers[hk.strip()] = hv.strip()

    return ProviderConfig(
        id=env["ID"], name=env["NAME"], model=env["MODEL"],
        api_base=env["API_BASE"], api_key=env["API_KEY"],
        timeout=_safe_int(env.get("TIMEOUT", ""), 60),
        max_retries=_safe_int(env.get("MAX_RETRIES", ""), 3),
        rpm_limit=_safe_int(env.get("RPM_LIMIT", ""), 60),
        tpm_limit=_safe_int(env.get("TPM_LIMIT", ""), 100000),
        priority=_safe_int(env.get("PRIORITY", ""), 1),
        enabled=_str_to_bool(env.get("ENABLED", "true")),
        is_backup=_str_to_bool(env.get("IS_BACKUP", "false")),
        tags=_str_to_list(env.get("TAGS", "")),
        cost_per_1k_input=_safe_float(env.get("COST_PER_1K_INPUT", ""), 0.0),
        cost_per_1k_output=_safe_float(env.get("COST_PER_1K_OUTPUT", ""), 0.0),
        headers=headers,
    )


def load_all_providers_from_env() -> List[ProviderConfig]:
    """自动扫描并加载所有 Provider 配置。

    从 N=0 开始，依次检查 CPA_PROVIDER_0_, CPA_PROVIDER_1_, …
    当某个 N 的全部必填字段（ID, NAME, MODEL, API_BASE, API_KEY）均缺失时停止。
    中间编号缺失部分必填字段时会跳过，继续扫描下一个编号。

    返回:
        所有成功加载的 ProviderConfig 列表，按 priority 升序排列。
    """
    providers: List[ProviderConfig] = []
    n = 0
    required = ["ID", "NAME", "MODEL", "API_BASE", "API_KEY"]
    while True:
        prefix = f"CPA_PROVIDER_{n}_"
        env = _parse_env_dict(prefix)
        if not any(f in env for f in required):
            break
        try:
            providers.append(load_provider_from_env(prefix))
        except ValueError:
            pass  # 部分必填字段缺失，跳过当前编号
        n += 1
    providers.sort(key=lambda p: p.priority)
    return providers


def load_m1_config_from_env() -> M1Config:
    """加载完整的 M1 模块配置。

    包含三部分：
      1. 调用 load_all_providers_from_env() 获取所有 Provider。
      2. 从 CPA_M1_* 前缀环境变量加载模块级配置。
      3. 从 CPA_M1_FALLBACK_N_* 前缀环境变量加载降级链。

    返回:
        完整的 M1Config 实例。
    """
    providers = load_all_providers_from_env()
    m = _parse_env_dict("CPA_M1_")

    # 模块级配置
    daily_raw = m.get("DAILY_BUDGET_USD", "")
    daily_budget = _safe_float(daily_raw, 0.0) if daily_raw else None

    # 降级链扫描
    fallbacks: List[FallbackChain] = []
    fn = 0
    while True:
        fenv = _parse_env_dict(f"CPA_M1_FALLBACK_{fn}_")
        if "MODEL" not in fenv:
            break
        fallbacks.append(FallbackChain(
            model_pattern=fenv["MODEL"],
            provider_ids=_str_to_list(fenv.get("PROVIDER_IDS", "")),
        ))
        fn += 1

    return M1Config(
        enabled=_str_to_bool(m.get("ENABLED", "true")),
        health_check_interval=_safe_int(m.get("HEALTH_CHECK_INTERVAL", ""), 30),
        health_check_timeout=_safe_int(m.get("HEALTH_CHECK_TIMEOUT", ""), 10),
        health_check_prompt=m.get("HEALTH_CHECK_PROMPT", "Respond with OK"),
        fail_threshold=_safe_int(m.get("FAIL_THRESHOLD", ""), 3),
        recovery_check_interval=_safe_int(m.get("RECOVERY_CHECK_INTERVAL", ""), 60),
        recovery_confirm_requests=_safe_int(m.get("RECOVERY_CONFIRM_REQUESTS", ""), 2),
        daily_budget_usd=daily_budget,
        budget_alert_threshold=_safe_float(m.get("BUDGET_ALERT_THRESHOLD", ""), 0.8),
        providers=providers,
        fallback_chains=fallbacks,
    )


# ===========================================================================
# 直接运行时的快速自检
# ===========================================================================

if __name__ == "__main__":
    os.environ["CPA_PROVIDER_0_ID"] = "openai-gpt4"
    os.environ["CPA_PROVIDER_0_NAME"] = "OpenAI GPT-4"
    os.environ["CPA_PROVIDER_0_MODEL"] = "gpt-4"
    os.environ["CPA_PROVIDER_0_API_BASE"] = "https://api.openai.com/v1"
    os.environ["CPA_PROVIDER_0_API_KEY"] = "sk-test"
    os.environ["CPA_PROVIDER_0_PRIORITY"] = "2"
    os.environ["CPA_PROVIDER_0_TAGS"] = "gpt,official"

    os.environ["CPA_PROVIDER_1_ID"] = "anthropic-claude"
    os.environ["CPA_PROVIDER_1_NAME"] = "Anthropic Claude"
    os.environ["CPA_PROVIDER_1_MODEL"] = "claude-3-opus"
    os.environ["CPA_PROVIDER_1_API_BASE"] = "https://api.anthropic.com/v1"
    os.environ["CPA_PROVIDER_1_API_KEY"] = "sk-ant"
    os.environ["CPA_PROVIDER_1_PRIORITY"] = "1"
    os.environ["CPA_PROVIDER_1_IS_BACKUP"] = "1"
    os.environ["CPA_PROVIDER_1_COST_PER_1K_INPUT"] = "0.015"

    os.environ["CPA_M1_HEALTH_CHECK_INTERVAL"] = "20"
    os.environ["CPA_M1_DAILY_BUDGET_USD"] = "50.0"
    os.environ["CPA_M1_FALLBACK_0_MODEL"] = "gpt-4*"
    os.environ["CPA_M1_FALLBACK_0_PROVIDER_IDS"] = "openai-gpt4,anthropic-claude"

    cfg = load_m1_config_from_env()
    print(f"enabled={cfg.enabled}, health_interval={cfg.health_check_interval}")
    print(f"budget={cfg.daily_budget_usd}, providers={len(cfg.providers)}")
    for p in cfg.providers:
        print(f"  [{p.priority}] {p.id}: {p.name} (backup={p.is_backup}, tags={p.tags})")
    print(f"fallbacks={len(cfg.fallback_chains)}: {[(fc.model_pattern, fc.provider_ids) for fc in cfg.fallback_chains]}")
