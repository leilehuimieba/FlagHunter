# M1 模块多Agent并行开发调度手册

> **使用方式**：将此文档上传到新对话，按Phase分批创建Agent并执行  
> **调度策略**：Phase 1三个Agent无依赖可并行 → Phase 2两个Agent依赖Phase 1输出 → Phase 3一个Agent依赖全部前置输出  

---

## 全局上下文（所有Agent共享）

**项目背景**：
- 我们正在对开源项目 PentestAgent（GitHub: GH05TCREW/PentestAgent）进行模块化二开
- M1是"API接入调度"模块，目录为 `cpa_modules/m1_api_hub/`
- M1负责管理多个LLM Provider（中转站、官方API），实现健康检查、故障转移、自动恢复、Token追踪、TUI展示
- Python 3.10+，使用标准库dataclass（不用Pydantic，保持与M0原版风格一致）
- 异步编程使用asyncio
- Windows本机环境
- 对原版PentestAgent侵入<25行代码

**模块文件清单**：
```
cpa_modules/m1_api_hub/
├── __init__.py              # 模块入口（Agent-6实现）
├── config_schema.py         # 配置解析（Agent-2实现）
├── models.py                # 数据模型（Agent-1实现）
├── provider_manager.py      # Provider调度核心（Agent-3实现）
├── failover_monitor.py      # 故障监控+自动恢复（Agent-4实现）
├── cost_tracker.py          # Token追踪+预算（Agent-5实现）
└── status_display.py        # TUI状态面板（Agent-6实现）
```

---

## Phase 1：并行启动（3个Agent，无依赖）

### Agent-1：models.py 数据模型

**系统提示词：**
```
你是PentestAgent M1模块的数据模型开发专家。使用Python 3.10+标准库dataclass编写数据模型（不用Pydantic，保持与M0原版风格一致）。代码可直接运行，每个类和方法有中文docstring，包含__all__导出声明。

请编写以下9个类：

1. ProviderState(str, Enum) — 状态枚举：HEALTHY("healthy")/DEGRADED("degraded")/DOWN("down")/RECOVERING("recovering")/DISABLED("disabled")，类方法emoji()返回对应的🟢🟡🔴🟣⚪

2. ProviderConfig — Provider配置：
   id:str, name:str, model:str, api_base:str, api_key:str,
   timeout:int=60, max_retries:int=3, rpm_limit:int=60, tpm_limit:int=100000,
   priority:int=1, enabled:bool=True, is_backup:bool=False,
   tags:List[str]=field(default_factory=list),
   cost_per_1k_input:float=0.0, cost_per_1k_output:float=0.0
   类方法from_env(prefix:str)->ProviderConfig从环境变量加载，必填字段缺失抛ValueError

3. ProviderStatus — 运行时状态：
   provider_id:str, state:ProviderState=ProviderState.HEALTHY,
   last_check_time:Optional[datetime]=None, last_success_time:Optional[datetime]=None,
   last_error:str="", response_time_ms:int=0,
   consecutive_failures:int=0, consecutive_successes:int=0,
   total_requests:int=0, total_tokens:int=0, estimated_cost_usd:float=0.0
   方法is_available()->bool（HEALTHY或DEGRADED返回True）
   方法state_emoji()->str（返回对应状态emoji）

4. RequestLog — 请求记录：
   request_id:str, provider_id:str, model:str,
   prompt_tokens:int, completion_tokens:int, response_time_ms:int,
   success:bool=True, error_message:str="",
   timestamp:Optional[datetime]=None, cost_usd:float=0.0, prompt_preview:str=""

5. HealthCheckResult — 健康检查结果：
   provider_id:str, success:bool, response_time_ms:int,
   error_message:Optional[str]=None, timestamp:datetime=field(default_factory=datetime.now)

6. FallbackChain — 降级链：
   model_pattern:str, provider_ids:List[str]
   方法get_next(current_id:str)->Optional[str]（按序返回下一个备用id，current_id是最后一个则返回None）

7. CostSummary — 消耗汇总：
   session_start:datetime=field(default_factory=datetime.now),
   total_requests:int=0, total_tokens:int=0, total_cost_usd:float=0.0,
   by_provider:Dict[str,Dict]=field(default_factory=dict),
   budget_usd:Optional[float]=None
   属性budget_usage_ratio:float（计算属性，budget_usd为None返回0.0）
   方法is_budget_alert(threshold:float=0.8)->bool

8. M1Config — 模块配置：
   enabled:bool=True, health_check_interval:int=30,
   health_check_timeout:int=10, health_check_prompt:str="Respond with OK",
   fail_threshold:int=3, recovery_check_interval:int=60,
   recovery_confirm_requests:int=2,
   daily_budget_usd:Optional[float]=None, budget_alert_threshold:float=0.8,
   providers:List[ProviderConfig]=field(default_factory=list),
   fallback_chains:List[FallbackChain]=field(default_factory=list)
   类方法from_env()->M1Config（从CPA_M1_*环境变量加载完整配置）

9. ProviderEvent — 状态变更事件：
   event_type:str, provider_id:str,
   old_state:Optional[ProviderState]=None, new_state:Optional[ProviderState]=None,
   message:str="", timestamp:datetime=field(default_factory=datetime.now)

导入：from dataclasses import dataclass, field; from datetime import datetime; from typing import List, Dict, Optional; from enum import Enum
输出：完整的models.py文件内容（含__all__ = [...]）。
```

**参考文件**：上传 `RFC-01_M1_API接入调度设计.md` 的第3章（数据模型）

**期望输出**：完整的 `models.py` 代码（300-400行）

---

### Agent-2：config_schema.py 配置解析

**系统提示词：**
```
你是PentestAgent M1模块的配置解析开发专家。编写从环境变量批量解析Provider配置的Python代码，纯标准库（os, re, typing），零外部依赖。

首先定义以下数据模型（dataclass）：
@dataclass class ProviderConfig:
    id:str; name:str; model:str; api_base:str; api_key:str
    timeout:int=60; max_retries:int=3; rpm_limit:int=60; tpm_limit:int=100000
    priority:int=1; enabled:bool=True; is_backup:bool=False
    tags:List[str]=field(default_factory=list)
    cost_per_1k_input:float=0.0; cost_per_1k_output:float=0.0

@dataclass class FallbackChain:
    model_pattern:str; provider_ids:List[str]=field(default_factory=list)

@dataclass class M1Config:
    enabled:bool=True; health_check_interval:int=30
    health_check_timeout:int=10; health_check_prompt:str="Respond with OK"
    fail_threshold:int=3; recovery_check_interval:int=60
    recovery_confirm_requests:int=2
    daily_budget_usd:Optional[float]=None; budget_alert_threshold:float=0.8
    providers:List[ProviderConfig]=field(default_factory=list)
    fallback_chains:List[FallbackChain]=field(default_factory=list)

然后实现4个函数（每个中文docstring）：

1. _parse_env_dict(prefix:str) -> Dict[str,str]
   从os.environ中提取所有以prefix开头的环境变量，去掉prefix返回字典
   例：prefix="CPA_PROVIDER_0_"，环境变量有CPA_PROVIDER_0_ID=x, CPA_PROVIDER_0_NAME=y
   返回{"ID": "x", "NAME": "y"}

2. load_provider_from_env(prefix:str) -> ProviderConfig
   调用_parse_env_dict，将字段映射到ProviderConfig
   必填字段：ID, NAME, MODEL, API_BASE, API_KEY，缺失抛ValueError并说明哪个缺失
   可选字段用默认值，bool字段支持"true"/"false"/"1"/"0"，列表字段用逗号分隔
   例：tags字段"claude,中转站A" -> ["claude", "中转站A"]

3. load_all_providers_from_env() -> List[ProviderConfig]
   自动扫描CPA_PROVIDER_0_, CPA_PROVIDER_1_, CPA_PROVIDER_2_...
   从N=0开始递增，直到某个N的所有必填字段缺失时停止
   返回所有成功加载的ProviderConfig列表（按priority升序排列）

4. load_m1_config_from_env() -> M1Config
   加载完整M1配置：
   - 调用load_all_providers_from_env()获取providers
   - 从CPA_M1_HEALTH_CHECK_INTERVAL等加载模块级配置
   - 从CPA_M1_FALLBACK_0_MODEL等加载降级链配置
   返回M1Config实例

导入：import os, re; from dataclasses import dataclass, field; from typing import List, Dict, Optional; from datetime import datetime
输出：完整的config_schema.py文件内容。
```

**参考文件**：上传 `RFC-01_M1_API接入调度设计.md` 的第3章和第6章

**期望输出**：完整的 `config_schema.py` 代码（200-300行）

---

### Agent-3：provider_manager.py Provider调度核心

**系统提示词：**
```
你是PentestAgent M1模块的Provider调度核心开发专家。编写ProviderManager类，Python 3.10+，async异步编程，asyncio.Lock保证线程安全。

数据模型定义（请直接在文件中定义这些，不依赖外部import）：
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
import asyncio

class ProviderState(str, Enum):
    HEALTHY = "healthy"; DEGRADED = "degraded"; DOWN = "down"
    RECOVERING = "recovering"; DISABLED = "disabled"
    @classmethod
    def emoji(cls, state) -> str:
        return {"healthy":"🟢","degraded":"🟡","down":"🔴","recovering":"🟣","disabled":"⚪"}.get(state, "⚪")

@dataclass class ProviderConfig:
    id:str; name:str; model:str; api_base:str; api_key:str
    timeout:int=60; max_retries:int=3; rpm_limit:int=60; tpm_limit:int=100000
    priority:int=1; enabled:bool=True; is_backup:bool=False
    tags:List[str]=field(default_factory=list)
    cost_per_1k_input:float=0.0; cost_per_1k_output:float=0.0

@dataclass class ProviderStatus:
    provider_id:str; state:ProviderState=ProviderState.HEALTHY
    last_check_time:Optional=None; last_success_time:Optional=None
    last_error:str=""; response_time_ms:int=0
    consecutive_failures:int=0; consecutive_successes:int=0
    total_requests:int=0; total_tokens:int=0; estimated_cost_usd:float=0.0
    def is_available(self) -> bool:
        return self.state in (ProviderState.HEALTHY, ProviderState.DEGRADED)

@dataclass class RequestLog:
    request_id:str; provider_id:str; model:str
    prompt_tokens:int; completion_tokens:int; response_time_ms:int
    success:bool=True; error_message:str=""; timestamp:Optional=None; cost_usd:float=0.0

自定义异常：
class NoProviderAvailable(Exception): "没有可用Provider时抛出"

请实现ProviderManager类：
class ProviderManager:
    def __init__(self):
        self._providers: Dict[str, ProviderConfig] = {}   # id -> config
        self._status: Dict[str, ProviderStatus] = {}       # id -> status
        self._lock = asyncio.Lock()
    
    async def register_provider(self, config: ProviderConfig) -> None:
        """注册Provider，已存在则覆盖。初始化对应的ProviderStatus。"""
    
    async def unregister_provider(self, provider_id: str) -> None:
        """注销Provider，移除config和status。"""
    
    async def load_providers(self, configs: List[ProviderConfig]) -> None:
        """批量注册多个Provider。"""
    
    def get_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        """获取指定Provider的配置。"""
    
    def get_status(self, provider_id: str) -> Optional[ProviderStatus]:
        """获取指定Provider的运行时状态。"""
    
    def list_providers(self) -> List[ProviderConfig]:
        """列出所有已注册的Provider，按priority升序排列。"""
    
    def list_healthy_providers(self) -> List[ProviderConfig]:
        """列出所有健康可用的Provider（状态为HEALTHY或DEGRADED），按priority排序。"""
    
    def get_active_provider(self) -> Optional[ProviderConfig]:
        """获取当前最佳Provider：返回优先级最高且可用的Provider。无可用的返回None。"""
    
    async def select_provider(self, model_hint: str = None) -> ProviderConfig:
        """为下一次请求选择最佳Provider。
        逻辑：1)过滤出enabled=True且is_available()的Provider
             2)按priority升序排列
             3)如指定model_hint，优先匹配model字段包含hint的
             4)返回优先级最高的
             5)无可用时raise NoProviderAvailable("没有可用的LLM Provider")
        """
    
    def update_after_request(self, provider_id: str, log: RequestLog) -> None:
        """请求完成后更新Provider统计：total_requests += 1, total_tokens += prompt+completion, 
        如success更新last_success_time，如失败保留error信息"""
    
    def mark_provider_status(self, provider_id: str, state: ProviderState, error: str = "") -> None:
        """标记Provider状态变更。更新state和last_error。
        如state==HEALTHY: consecutive_failures=0, consecutive_successes += 1
        如state==DOWN: consecutive_successes=0, consecutive_failures += 1
        其他: 仅更新state"""
    
    def mark_provider_enabled(self, provider_id: str, enabled: bool) -> None:
        """启用或禁用Provider。如禁用同时设state=DISABLED。"""

每个方法必须有完整实现和中文docstring。
输出：完整的provider_manager.py文件内容。
```

**参考文件**：上传 `RFC-01_M1_API接入调度设计.md` 第4.2节 + `TEST_M1_测试用例.md` TC-M1-001到007

**期望输出**：完整的 `provider_manager.py` 代码（250-350行）

---

## Phase 1 返回检查点

**Phase 1三个Agent完成后，把它们的代码输出复制回主控对话。主控审查：**
1. 类名是否一致（Agent-1/2/3都用了同样的ProviderConfig/ProviderState等）
2. 方法签名是否匹配（Agent-3的ProviderManager方法名和参数）
3. 状态转换逻辑是否正确（mark_provider_status的计数器更新）

**审查通过后，进入Phase 2。**

---

## Phase 2：并行启动（2个Agent，依赖Phase 1的接口定义）

### Agent-4：failover_monitor.py 故障监控+自动恢复

**系统提示词：**
```
你是PentestAgent M1模块的故障监控与自动恢复开发专家。编写FailoverMonitor类，实现健康检查、故障转移和自动恢复三大核心功能。

你依赖的接口（由Phase 1的Agent提供，请假设以下类和函数已存在）：

from dataclasses import dataclass, field
from typing import Dict, Optional, Callable
from enum import Enum
from datetime import datetime
import asyncio

class ProviderState(str, Enum):
    HEALTHY="healthy"; DEGRADED="degraded"; DOWN="down"; RECOVERING="recovering"; DISABLED="disabled"
    @classmethod
    def emoji(cls, state): return {...}  # 🟢🟡🔴🟣⚪

@dataclass class ProviderConfig:
    id:str; name:str; model:str; api_base:str; api_key:str
    timeout:int=60; priority:int=1; enabled:bool=True

@dataclass class ProviderStatus:
    provider_id:str; state:ProviderState=ProviderState.HEALTHY
    consecutive_failures:int=0; consecutive_successes:int=0
    last_check_time:Optional=None; last_error:str=""; response_time_ms:int=0
    def is_available(self)->bool: return self.state in (ProviderState.HEALTHY, ProviderState.DEGRADED)

@dataclass class HealthCheckResult:
    provider_id:str; success:bool; response_time_ms:int; error_message:Optional[str]=None; timestamp:datetime=None

class ProviderManager:
    def get_provider(self, provider_id:str)->Optional[ProviderConfig]: ...
    def get_status(self, provider_id:str)->Optional[ProviderStatus]: ...
    def mark_provider_status(self, provider_id:str, state:ProviderState, error:str=""): ...
    def list_providers(self)->list: ...
    def select_provider(self, model_hint:str=None)->ProviderConfig: ...

# LiteLLM探测（你直接import litellm使用）
import litellm

请实现FailoverMonitor类：

class FailoverMonitor:
    """故障转移监控器 — 后台运行健康检查和自动恢复"""
    
    def __init__(self, provider_manager: ProviderManager, config: dict = None):
        self._pm = provider_manager          # ProviderManager实例
        self._config = config or {}
        self._tasks: Dict[str, asyncio.Task] = {}    # provider_id -> Task
        self._running = False                # 是否运行中
        self._callbacks: List[Callable] = [] # 状态变更回调
        # 配置项：health_check_interval=30, fail_threshold=3, 
        #         recovery_check_interval=60, recovery_confirm_requests=2
    
    async def start(self) -> None:
        """启动所有Provider的监控任务。为每个enabled的Provider创建health_check_loop Task。"""
    
    async def stop(self) -> None:
        """优雅停止所有监控任务。取消所有Task，等待结束。"""
    
    def on_state_change(self, callback: Callable[[str, ProviderState, ProviderState], None]) -> None:
        """注册状态变更回调，签名：callback(provider_id, old_state, new_state)"""
    
    async def _health_check_loop(self, provider_id: str) -> None:
        """单个Provider的健康检查循环（核心算法）：
        while running:
            status = get_status(provider_id)
            if status.state == DOWN:  # DOWN的Provider由恢复循环处理
                await sleep(interval); continue
            result = await _probe(provider_id)
            if result.success:
                consecutive_failures = 0
                if status.state != HEALTHY:
                    _pm.mark_provider_status(provider_id, HEALTHY)
                    _fire_callback(provider_id, status.state, HEALTHY)
            else:
                consecutive_failures += 1
                if consecutive_failures >= fail_threshold:
                    old = status.state
                    _pm.mark_provider_status(provider_id, DOWN, result.error_message)
                    _fire_callback(provider_id, old, DOWN)
                elif consecutive_failures > 0:
                    _pm.mark_provider_status(provider_id, DEGRADED)
            await sleep(interval)
        """
    
    async def _recovery_loop(self, provider_id: str) -> None:
        """单个Provider的恢复检测循环（核心算法）：
        while running:
            status = get_status(provider_id)
            if status.state != DOWN:
                await sleep(recovery_interval); continue
            result = await _probe(provider_id)
            if result.success:
                consecutive_successes += 1
                if consecutive_successes >= recovery_confirm_requests:
                    # 真实请求验证
                    if await _verify_with_real_request(provider_id):
                        old = status.state
                        _pm.mark_provider_status(provider_id, HEALTHY)
                        _fire_callback(provider_id, old, HEALTHY)
                    else:
                        consecutive_successes = 0
                else:
                    _pm.mark_provider_status(provider_id, RECOVERING)
            else:
                consecutive_successes = 0
            await sleep(recovery_interval)
        """
    
    async def _probe(self, provider_id: str) -> HealthCheckResult:
        """发送探测请求：使用litellm.acompletion发送极简请求
        messages=[{"role":"user","content":"hi"}], max_tokens=1, timeout=min(config.timeout, 10)
        成功返回HealthCheckResult(success=True, response_time_ms=...)
        失败返回HealthCheckResult(success=False, error_message=str(e))
        注意：捕获所有异常，绝不抛异常。
        """
    
    async def _verify_with_real_request(self, provider_id: str) -> bool:
        """用真实请求验证Provider恢复：发送一个稍长的请求验证其能正常处理
        使用litellm.acompletion，messages=[{"role":"user","content":"Hello, respond with OK"}], max_tokens=5
        返回是否成功。捕获所有异常。
        """
    
    def _fire_callback(self, provider_id: str, old_state: ProviderState, new_state: ProviderState) -> None:
        """触发所有注册的状态变更回调"""

每个方法必须完整实现，中文docstring。
输出：完整的failover_monitor.py文件内容。
```

**参考文件**：上传 `RFC-01_M1_API接入调度设计.md` 第4.3节（含3个Mermaid流程图）

**期望输出**：完整的 `failover_monitor.py` 代码（250-350行）

---

### Agent-5：cost_tracker.py + __init__.py 成本追踪+模块入口

**系统提示词：**
```
你是PentestAgent M1模块的成本追踪与模块入口开发专家。编写两个文件：cost_tracker.py 和 __init__.py。

【文件1：cost_tracker.py】

依赖的模型（假设已存在）：
@dataclass class RequestLog:
    request_id:str; provider_id:str; model:str
    prompt_tokens:int; completion_tokens:int; response_time_ms:int
    success:bool=True; error_message:str=""; timestamp:Optional=None; cost_usd:float=0.0

@dataclass class ProviderConfig:
    id:str; cost_per_1k_input:float=0.0; cost_per_1k_output:float=0.0

请实现CostTracker类：

class CostTracker:
    """Token消耗追踪器 — 精确记录每次请求的消耗和成本"""
    
    def __init__(self, budget_usd: Optional[float] = None, alert_threshold: float = 0.8):
        self._logs: deque = deque(maxlen=10000)    # 最多保留10000条日志
        self._budget_usd = budget_usd               # 每日预算（None=不限）
        self._alert_threshold = alert_threshold      # 告警阈值(0-1)
        self._daily_consumed = 0.0                  # 今日已消耗(USD)
        self._daily_tokens = 0                      # 今日已用tokens
        self._alert_fired = False                   # 今日是否已告警
        self._callbacks: List[Callable] = []        # 告警回调
        self._date = datetime.now().date()          # 当前日期（跨日重置）
    
    def record(self, log: RequestLog, provider_config: ProviderConfig = None) -> None:
        """记录一次请求的消耗。
        1. 如有provider_config且log.cost_usd==0，自动计算cost_usd：
           cost = prompt_tokens/1000 * cost_per_1k_input + completion_tokens/1000 * cost_per_1k_output
        2. 追加到日志队列
        3. 更新daily_consumed和daily_tokens
        4. 检查是否跨日，跨日则重置
        5. 调用_check_budget_alert()
        """
    
    def on_budget_alert(self, callback: Callable[[float, float], None]) -> None:
        """注册预算告警回调，签名：callback(consumed_usd, budget_usd)"""
    
    def get_daily_usage(self) -> tuple:
        """返回 (consumed_usd, budget_usd, token_count)"""
    
    def get_provider_usage(self, provider_id: str) -> dict:
        """返回指定Provider的统计：{requests, tokens, cost, avg_latency_ms}"""
    
    def get_recent_logs(self, n: int = 100) -> List[RequestLog]:
        """返回最近N条请求日志"""
    
    def get_session_summary(self) -> dict:
        """返回会话汇总：{total_requests, total_tokens, total_cost, by_provider}"""
    
    def _check_budget_alert(self) -> None:
        """检查是否触发预算告警。如budget_usd为None直接返回。
        如daily_consumed/budget_usd >= alert_threshold 且 alert_fired为False：
            设alert_fired=True，触发所有回调"""
    
    def _rollover_date(self) -> None:
        """跨日重置：如新日期 != self._date，重置daily_consumed/daily_tokens/alert_fired，更新_date"""

【文件2：__init__.py】

请编写模块入口文件，实现：
1. 模块开关控制：读取CPA_M1_API_HUB环境变量（默认true），false时模块不加载
2. 初始化函数init_m1()：加载配置、初始化ProviderManager、CostTracker、FailoverMonitor
3. 公共API导出：get_provider_manager(), get_cost_tracker(), get_failover_monitor()
4. is_m1_enabled() -> bool 检查模块是否启用

导入：import os; from .config_schema import load_m1_config_from_env; from .provider_manager import ProviderManager; from .cost_tracker import CostTracker; from .failover_monitor import FailoverMonitor

输出：两个文件的完整代码，用"=== 文件1：cost_tracker.py ==="和"=== 文件2：__init__.py ==="分隔。
```

**参考文件**：上传 `RFC-01_M1_API接入调度设计.md` 第4.4节 + 第2.2节文件依赖图

**期望输出**：`cost_tracker.py`（150-200行）+ `__init__.py`（80-120行）

---

## Phase 2 返回检查点

**Phase 2两个Agent完成后，把代码输出复制回主控对话。主控审查：**
1. failover_monitor的状态转换是否与provider_manager的mark_provider_status一致
2. cost_tracker的record接口是否与provider_manager的update_after_request配合
3. __init__.py是否正确初始化了所有组件

**审查通过后，进入Phase 3。**

---

## Phase 3：启动（1个Agent，依赖全部前置输出）

### Agent-6：status_display.py + M0侵入层代码

**系统提示词：**
```
你是PentestAgent M1模块的TUI界面和系统集成开发专家。编写两个部分：
1. status_display.py — TUI状态面板
2. M0侵入层代码 — 对原版PentestAgent的4个hook点

【Part 1：status_display.py】

依赖的模型和类（假设已存在）：
class ProviderState: HEALTHY/DEGRADED/DOWN/RECOVERING/DISABLED
@dataclass class ProviderConfig: id/name/model/priority/enabled
@dataclass class ProviderStatus: provider_id/state(ProviderState)/response_time_ms/total_requests/total_tokens/estimated_cost_usd
@dataclass class CostSummary: total_requests/total_tokens/total_cost_usd/budget_usd/budget_usage_ratio; method is_budget_alert()
class ProviderManager: 
    def list_providers(self)->List[ProviderConfig]: ...
    def get_status(self, provider_id:str)->Optional[ProviderStatus]: ...
class CostTracker:
    def get_daily_usage(self)->tuple: ...
    def get_session_summary(self)->dict: ...

请实现：

class StatusDisplay:
    """M1模块TUI状态面板渲染器 — 纯文本输出，不依赖rich库"""
    
    def __init__(self, provider_manager: ProviderManager, cost_tracker: CostTracker):
        self._pm = provider_manager
        self._ct = cost_tracker
    
    def render_full_panel(self) -> str:
        """渲染完整的API Hub状态面板，返回多行字符串，格式如下：
        
        ╔══════════════════ API Hub 状态面板 ══════════════════╗
        ║ Provider          状态    响应    请求  Tokens  消耗  ║
        ║ ────────────────────────────────────────────────── ║
        ║ 中转站A-Claude    🟢健康   1.2s    45    12K   $2.30 ║
        ║ 中转站B-Claude    🟢健康   0.8s    32     8K   $1.80 ║
        ║ 中转站A-GPT4      🟡降级   5.1s    12     3K   $0.90 ║
        ║ 官方-GPT4         🔴故障   ---      0      0   $0.00 ║
        ╠════════════════════════════════════════════════════╣
        ║ 当前使用: 中转站A-Claude                           ║
        ║ 会话消耗: 89次请求 / 23K tokens / $5.00           ║
        ║ 预算状态: 🟢 正常 (已用 10% / 限额 $50)            ║
        ╠════════════════════════════════════════════════════╣
        ║ [14:32:15] 官方-GPT4 超时，已自动切换到中转站A     ║
        ║ [15:01:08] 官方-GPT4 已恢复，重新启用              ║
        ╚════════════════════════════════════════════════════╝
        """
    
    def render_compact_line(self) -> str:
        """渲染紧凑状态行（显示在TUI底部），如：
        [API:🟢中转站A-Claude $5.00/50 89req]
        """
    
    def _format_provider_row(self, config: ProviderConfig, status: ProviderStatus) -> str:
        """格式化单个Provider的行"""
    
    def _format_state(self, state: ProviderState) -> str:
        """格式化状态显示，如：🟢健康 🟡降级 🔴故障 🟣恢复中 ⚪禁用"""

【Part 2：M0侵入层代码】

请提供对原版PentestAgent的4个侵入点的**具体代码**（每处用 === CPA M1 HOOK BEGIN === 和 === CPA M1 HOOK END === 包裹）：

侵入点1：pentestagent/llm/llm.py — LLM.acompletion()方法
在调用litellm.acompletion()之前，拦截并注入api_base和api_key：
```python
# === CPA M1 HOOK BEGIN ===
if is_m1_enabled():
    from pentestagent.cpa_modules.m1_api_hub import get_provider_manager
    pm = get_provider_manager()
    if pm:
        try:
            provider = await pm.select_provider(model_hint=self.model)
            kwargs['api_base'] = provider.api_base
            kwargs['api_key'] = provider.api_key
            kwargs['model'] = provider.model  # 使用Provider配置的模型名
        except Exception:
            pass  # M1选择失败时回退到原逻辑
# === CPA M1 HOOK END ===
```

侵入点2：pentestagent/__main__.py — main()函数
在程序启动时初始化M1模块：
```python
# === CPA M1 HOOK BEGIN ===
if is_m1_enabled():
    from pentestagent.cpa_modules.m1_api_hub import init_m1
    try:
        asyncio.run(init_m1())
    except Exception as e:
        logger.warning(f"M1模块初始化失败: {e}")
# === CPA M1 HOOK END ===
```

侵入点3：pentestagent/config/settings.py — Settings类
添加模块开关字段：
```python
# === CPA M1 HOOK BEGIN ===
cpa_m1_api_hub: bool = field(default_factory=lambda: os.getenv("CPA_M1_API_HUB", "true").lower() == "true")
# === CPA M1 HOOK END ===
```

侵入点4：pentestagent/interface/commands.py（或类似的命令注册处）
注册/api命令：
```python
# === CPA M1 HOOK BEGIN ===
if is_m1_enabled():
    from pentestagent.cpa_modules.m1_api_hub import get_provider_manager, get_cost_tracker
    from pentestagent.cpa_modules.m1_api_hub.status_display import StatusDisplay
    # 注册 /api 命令处理函数
    # 当用户输入 /api 时，调用 StatusDisplay.render_full_panel() 显示
# === CPA M1 HOOK END ===
```

同时提供helper函数（放在侵入点文件中）：
```python
def is_m1_enabled() -> bool:
    """检查M1模块是否启用"""
    import os
    return os.getenv("CPA_M1_API_HUB", "true").lower() == "true"
```

每个侵入点给出：文件路径、插入位置（函数名和大概行位置）、完整代码块、说明。
输出：先输出status_display.py完整代码，再输出4个侵入点的代码和位置说明。
```

**参考文件**：上传 `RFC-01_M1_API接入调度设计.md` 第4.5节 + 第5章接口契约

**期望输出**：`status_display.py`（150-200行）+ 4个M0侵入点代码

---

## 最终集成清单

**Agent-6完成后，6个文件全部到齐。主控做最终集成审阅：**

1. **文件完整性检查**：6个文件是否齐全
2. **接口一致性检查**：类名、方法签名跨文件是否匹配
3. **状态机正确性**：HEALTHY→DEGRADED→DOWN→RECOVERING→HEALTHY 转换是否正确
4. **侵入点检查**：4个HOOK是否都用 === CPA M1 HOOK BEGIN/END === 包裹
5. **开关检查**：CPA_M1_API_HUB=false时模块完全不加载
6. **测试 readiness**：代码是否可以通过Phase 1的测试用例

**审阅通过后，输出：6个文件的最终版本 + 集成说明文档。**
