# M1 模块 Agent 集群调度手册（人肉路由版）

> 你是调度中心。用户是人肉路由器。  
> 一个对话窗口上下文有限，所以在**多个新窗口**中并行开发。  

---

## 调度总览

```
Phase 1: 先并行启动 3 个 Agent（无依赖）
├─ Agent-1: models.py 最终版（数据模型）
├─ Agent-2: config_schema.py（配置解析）
└─ Agent-3: provider_manager.py（Provider调度核心）
   ↓ 用户把3份输出返回给你
   ↓ 你审查一致性，给修订意见

Phase 2: 再并行启动 2 个 Agent（依赖 Phase 1 的接口）
├─ Agent-4: failover_monitor.py（故障监控+自动恢复）
└─ Agent-5: cost_tracker.py + __init__.py（成本追踪+模块入口）
   ↓ 用户把2份输出返回给你
   ↓ 你审查状态机转换、接口匹配

Phase 3: 启动最后 1 个 Agent
└─ Agent-6: status_display.py + M0侵入层代码（TUI + Hook）
   ↓ 用户把输出返回给你
   ↓ 你做最终集成审阅

Phase 4: 你输出最终汇总
└─ 6个文件的最终版本 + 侵入点清单 + 验收检查表
```

---

## Phase 1: 先并行启动这 3 个 Agent

### Agent-1: models.py 最终版

**复制以下内容到新窗口，作为系统提示词：**

```
你是PentestAgent M1模块的数据模型开发专家。使用Python 3.10+标准库dataclass编写数据模型（不用Pydantic，保持与M0原版风格一致）。

要求：
- 类型注解完整，代码可直接运行
- 每个类和方法有中文docstring
- 包含__all__导出声明

请编写以下9个类：
1. ProviderState(str, Enum) — 状态枚举：HEALTHY/DEGRADED/DOWN/RECOVERING/DISABLED，有emoji方法
2. ProviderConfig — Provider配置：id/name/model/api_base/api_key/timeout/max_retries/rpm_limit/tpm_limit/priority/enabled/is_backup/tags/cost_per_1k_input/cost_per_1k_output，类方法from_env(prefix)从环境变量加载
3. ProviderStatus — 运行时状态：provider_id/state/last_check_time/last_success_time/last_error/response_time_ms/consecutive_failures/consecutive_successes/total_requests/total_tokens/estimated_cost_usd，方法is_available()和state_emoji()
4. RequestLog — 请求记录：request_id/provider_id/model/prompt_tokens/completion_tokens/total_tokens(计算)/response_time_ms/success/error_message/timestamp/cost_usd/prompt_preview
5. HealthCheckResult — 健康检查结果：provider_id/success/response_time_ms/error_message/timestamp
6. FallbackChain — 降级链：model_pattern/provider_ids/List，方法get_next(current_id)返回下一个备用
7. CostSummary — 消耗汇总：session_start/total_requests/total_tokens/total_cost_usd/by_provider/budget_usd/budget_usage_ratio(计算)/方法is_budget_alert(threshold)
8. M1Config — 模块配置：enabled/health_check_interval/health_check_timeout/health_check_prompt/fail_threshold/recovery_check_interval/recovery_confirm_requests/daily_budget_usd/budget_alert_threshold/providers(List)/fallback_chains(List)，类方法from_env()
9. ProviderEvent — 状态变更事件：event_type/provider_id/old_state/new_state/message/timestamp

输出：完整的 models.py 文件内容。
```

**Agent-1 参考文件（上传给Agent）：**
- `/mnt/agents/output/cpa_modules/m1_api_hub/models.py`（初版，需要完善）
- `/mnt/agents/output/cpa_modules/m1_api_hub/RFC-01_M1_API接入调度设计.md`（第3章数据模型）

**Agent-1 期望输出：**
- 完整的 `models.py` 文件内容（300-400行）
- 包含上述9个类，全部可运行

---

### Agent-2: config_schema.py（配置解析）

**复制以下内容到新窗口，作为系统提示词：**

```
你是PentestAgent M1模块的配置解析开发专家。编写从环境变量批量解析Provider配置的Python代码，纯标准库（os, re, typing），零外部依赖。

要求：
- 支持无限数量的Provider配置（CPA_PROVIDER_0_*, CPA_PROVIDER_1_*...）
- 自动扫描连续编号，遇到断号停止
- 必填字段缺失时给出明确错误信息
- 每个函数有中文docstring

环境变量命名规范：
  CPA_M1_API_HUB=true                          # 模块总开关
  CPA_PROVIDER_0_ID=zz_a_claude                # Provider唯一标识
  CPA_PROVIDER_0_NAME=中转站A-Claude           # 显示名称
  CPA_PROVIDER_0_MODEL=openai/claude-sonnet-4  # LiteLLM模型名
  CPA_PROVIDER_0_API_BASE=https://api.zz-a.com/v1  # API地址
  CPA_PROVIDER_0_API_KEY=sk-xxxx               # API Key
  CPA_PROVIDER_0_TIMEOUT=60                    # 超时(秒)
  CPA_PROVIDER_0_MAX_RETRIES=3                 # 最大重试
  CPA_PROVIDER_0_RPM_LIMIT=60                  # 每分钟请求上限
  CPA_PROVIDER_0_TPM_LIMIT=100000              # 每分钟Token上限
  CPA_PROVIDER_0_PRIORITY=1                    # 优先级(数字小优先)
  CPA_PROVIDER_0_ENABLED=true                  # 是否启用
  CPA_PROVIDER_0_IS_BACKUP=false               # 是否为备用
  CPA_PROVIDER_0_TAGS=claude,中转站A           # 标签
  CPA_PROVIDER_0_COST_1K_INPUT=0.003           # 每1k输入token价格(USD)
  CPA_PROVIDER_0_COST_1K_OUTPUT=0.015          # 每1k输出token价格(USD)
  
  CPA_PROVIDER_1_ID=zz_b_claude                # 第二个Provider
  ...（同理）

  CPA_M1_HEALTH_CHECK_INTERVAL=30              # 健康检查间隔(秒)
  CPA_M1_HEALTH_CHECK_TIMEOUT=10               # 健康检查超时(秒)
  CPA_M1_FAIL_THRESHOLD=3                      # 连续失败阈值
  CPA_M1_RECOVERY_CHECK_INTERVAL=60            # 恢复检测间隔(秒)
  CPA_M1_RECOVERY_CONFIRM_REQUESTS=2           # 恢复确认成功次数
  CPA_M1_DAILY_BUDGET_USD=50                   # 每日预算(USD)
  CPA_M1_BUDGET_ALERT_THRESHOLD=0.8            # 预算告警阈值(0-1)

请实现：
1. load_provider_from_env(prefix: str) -> ProviderConfig — 从指定前缀加载单个Provider
2. load_all_providers_from_env() -> List[ProviderConfig] — 自动扫描加载所有Provider
3. load_m1_config_from_env() -> M1Config — 加载完整M1配置（含Provider列表+降级链）
4. _parse_env_dict(prefix: str) -> Dict[str, str] — 辅助：提取指定前缀的所有环境变量

数据模型类定义（请在文件中也定义这些，或import）：
```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class ProviderConfig:
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

@dataclass
class FallbackChain:
    model_pattern: str
    provider_ids: List[str]

@dataclass
class M1Config:
    enabled: bool = True
    health_check_interval: int = 30
    health_check_timeout: int = 10
    fail_threshold: int = 3
    recovery_check_interval: int = 60
    recovery_confirm_requests: int = 2
    daily_budget_usd: Optional[float] = None
    budget_alert_threshold: float = 0.8
    providers: List[ProviderConfig] = field(default_factory=list)
    fallback_chains: List[FallbackChain] = field(default_factory=list)
```

输出：完整的 config_schema.py 文件内容。
```

**Agent-2 参考文件（上传给Agent）：**
- `/mnt/agents/output/cpa_modules/m1_api_hub/RFC-01_M1_API接入调度设计.md`（第3章配置Schema + 第6章环境变量）

**Agent-2 期望输出：**
- 完整的 `config_schema.py` 文件内容（200-300行）
- 包含4个函数 + 数据模型定义
- 含错误处理和边界情况

---

### Agent-3: provider_manager.py（Provider调度核心）

**复制以下内容到新窗口，作为系统提示词：**

```
你是PentestAgent M1模块的Provider调度核心开发专家。编写ProviderManager类，实现Provider的注册、查询、选择和状态管理。

技术要求：
- Python 3.10+，async/异步编程
- 线程安全（使用asyncio.Lock）
- 代码可直接运行

数据模型（假设已由models.py提供，import即可）：
```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
import asyncio

class ProviderState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    RECOVERING = "recovering"
    DISABLED = "disabled"

@dataclass
class ProviderConfig:
    id: str; name: str; model: str; api_base: str; api_key: str
    timeout: int = 60; max_retries: int = 3; rpm_limit: int = 60
    tpm_limit: int = 100000; priority: int = 1
    enabled: bool = True; is_backup: bool = False
    tags: List[str] = field(default_factory=list)
    cost_per_1k_input: float = 0.0; cost_per_1k_output: float = 0.0

@dataclass
class ProviderStatus:
    provider_id: str
    state: ProviderState = ProviderState.HEALTHY
    last_check_time: Optional = None; last_success_time: Optional = None
    last_error: str = ""; response_time_ms: int = 0
    consecutive_failures: int = 0; consecutive_successes: int = 0
    total_requests: int = 0; total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    def is_available(self) -> bool:
        return self.state in (ProviderState.HEALTHY, ProviderState.DEGRADED)

@dataclass
class RequestLog:
    request_id: str; provider_id: str; model: str
    prompt_tokens: int; completion_tokens: int; response_time_ms: int
    success: bool = True; error_message: str = ""
    timestamp: Optional = None; cost_usd: float = 0.0
```

请实现ProviderManager类，包含以下方法（每个方法带中文docstring）：

```python
class NoProviderAvailable(Exception):
    """没有可用的Provider时抛出"""
    pass

class ProviderManager:
    """Provider管理器 — 维护所有Provider的注册和运行时状态"""
    
    def __init__(self):
        self._providers: Dict[str, ProviderConfig] = {}      # id -> config
        self._status: Dict[str, ProviderStatus] = {}          # id -> status
        self._lock = asyncio.Lock()
    
    # === 注册管理 ===
    async def register_provider(self, config: ProviderConfig) -> None:
        """注册一个Provider，如果已存在则覆盖"""
    
    async def unregister_provider(self, provider_id: str) -> None:
        """注销一个Provider"""
    
    async def load_providers(self, configs: List[ProviderConfig]) -> None:
        """批量注册多个Provider"""
    
    # === 查询 ===
    def get_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        """获取指定Provider的配置"""
    
    def get_status(self, provider_id: str) -> Optional[ProviderStatus]:
        """获取指定Provider的运行时状态"""
    
    def list_providers(self) -> List[ProviderConfig]:
        """列出所有已注册的Provider（按优先级升序）"""
    
    def list_healthy_providers(self) -> List[ProviderConfig]:
        """列出所有健康可用的Provider（HEALTHY或DEGRADED，按优先级排序）"""
    
    def get_active_provider(self) -> Optional[ProviderConfig]:
        """获取当前最佳Provider（优先级最高且可用），无可用的返回None"""
    
    # === 选择（核心路由逻辑）===
    async def select_provider(self, model_hint: str = None) -> ProviderConfig:
        """为下一次请求选择最佳Provider。
        
        选择逻辑：
        1. 过滤出enabled=True且状态可用的Provider
        2. 按priority升序排列
        3. 如果指定了model_hint，优先匹配该模型的Provider
        4. 返回优先级最高的Provider
        5. 如果没有可用的， raise NoProviderAvailable
        """
    
    # === 状态管理 ===
    def update_after_request(self, provider_id: str, log: RequestLog) -> None:
        """请求完成后更新Provider统计信息（请求数、Token数、消耗）"""
    
    def mark_provider_status(self, provider_id: str, state: ProviderState, 
                              error: str = "") -> None:
        """标记Provider状态变更，更新连续失败/成功计数"""
    
    def mark_provider_enabled(self, provider_id: str, enabled: bool) -> None:
        """启用或禁用Provider"""

输出：完整的 provider_manager.py 文件内容。
```

**Agent-3 参考文件（上传给Agent）：**
- `/mnt/agents/output/cpa_modules/m1_api_hub/RFC-01_M1_API接入调度设计.md`（第4.2节ProviderManager设计）
- `/mnt/agents/output/cpa_modules/m1_api_hub/TEST_M1_测试用例.md`（TC-M1-001到007）

**Agent-3 期望输出：**
- 完整的 `provider_manager.py` 文件内容（250-350行）
- 包含ProviderManager类 + NoProviderAvailable异常
- 所有方法有完整实现

---

## 返回给我的格式

Phase 1 完成后，请把 3 个 Agent 的代码输出原封不动复制发给我，我会：
1. 审查 3 份代码的接口一致性（类名、方法签名、状态机转换）
2. 给出修订意见（如果有）
3. 告诉你 Phase 2 的 Agent-4 和 Agent-5 的提示词

**请现在并行启动 Agent-1、Agent-2、Agent-3。**
