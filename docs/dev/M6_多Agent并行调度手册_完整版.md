# M6 模块（性能优化加速）多Agent并行开发调度手册

> **使用方式**：将此文档上传到新对话，按Phase分批创建Agent并执行  
> **前置条件**：M1-M5全部已完成，M6依赖M1的ProviderManager和M2的工具执行层  
> **与其他模块关系**：M6是**透明增强层**，对M2-M5完全透明，不暴露接口  

---

## M6模块设计概要

### 解决什么问题

M1-M5功能齐全，但在**重复扫描、并发执行、资源消耗**方面没有优化：
- **重复扫描**：同一目标被多次nmap/sqlmap扫描，浪费Token和时间
- **串行执行**：工具一个一个跑，CPU/网络利用率低
- **内存泄漏**：长期运行后缓存累积不释放
- **连接开销**：每次HTTP请求新建连接，延迟高
- **冷启动慢**：pwntools/r2pipe等模块每次import都慢

M6是**透明性能层**——不增加新功能，只让现有功能跑得更快、更省资源。

### 核心设计原则

| 原则 | 说明 |
|------|------|
| **透明运行** | M2-M5完全感知不到M6存在，自动生效 |
| **默认开启** | CPA_M6_TURBO=true（性能优化应该是默认行为） |
| **安全降级** | 缓存失效时自动回退到原始执行 |
| **资源可控** | 内存上限、并发数上限、缓存大小上限均可配置 |
| **侵入最小** | 只在工具执行层加wrapper，不修改业务逻辑 |

### 架构设计

```
cpa_modules/m6_turbo/
├── __init__.py                  # 模块入口 + 全局wrapper注册（Agent-34实现）
├── result_cache.py              # 扫描结果缓存：Redis风格TTL + LRU淘汰（Agent-30）
├── parallel_scanner.py          # 并发扫描器：asyncio Semaphore控制并发（Agent-31）
├── lazy_loader.py               # 延迟加载统一封装：import hook + 预加载（Agent-32）
├── memory_optimizer.py          # 内存优化：缓存上限/定期GC/大对象检测（Agent-33）
└── turbo_commands.py            # /turbo命令：性能状态/缓存管理/GC触发（Agent-34）
```

### M6与其他模块的关系

```
M2工具执行层 ──► M6透明wrapper ──► 实际工具执行
                    │
                    ├─ result_cache: 先查缓存，命中直接返回
                    ├─ parallel_scanner: 批量任务并发执行
                    ├─ lazy_loader: 首次import延迟，后续复用
                    └─ memory_optimizer: 监控内存，超限告警/清理
```

**透明性保证**：M6在`__init__.py`中注册全局wrapper，M2-M5的工具函数被自动包裹，不需要改任何调用代码。

### 环境变量开关

```bash
# .env
CPA_M6_TURBO=true                # M6总开关（默认true）
CPA_M6_CACHE_ENABLED=true        # 结果缓存开关
CPA_M6_CACHE_MAX_SIZE=1000       # 缓存最大条目数
CPA_M6_CACHE_TTL_SECONDS=3600    # 缓存TTL（秒）
CPA_M6_CONCURRENT_LIMIT=5        # 最大并发扫描数
CPA_M6_CONCURRENT_PER_HOST=2     # 每主机最大并发数（防DoS）
CPA_M6_LAZY_PRELOAD=false        # 是否预加载常用模块（启动慢但运行快）
CPA_M6_MEMORY_LIMIT_MB=512       # 内存告警阈值（MB）
CPA_M6_GC_INTERVAL_SECONDS=300   # 定期GC间隔（秒）
```

---

## Phase 1：并行启动（3个Agent，无依赖）

### Agent-30：result_cache.py 扫描结果缓存

**系统提示词：**
```
你是PentestAgent M6模块的结果缓存开发专家。编写result_cache.py，实现带TTL和LRU淘汰的扫描结果缓存系统。

技术要求：Python 3.10+，标准库（threading, time, hashlib, json），零外部依赖。

数据模型定义（在文件中定义）：

@dataclass class CacheEntry:
    """缓存条目"""
    key: str                       # 缓存键（sha256(工具名+目标+参数)）
    tool_name: str                 # 工具名称
    target: str                    # 扫描目标
    params: dict                   # 执行参数（JSON序列化）
    result: dict                   # 执行结果（缓存的核心数据）
    created_at: float              # 创建时间（time.time()）
    ttl: int = 3600                # TTL（秒）
    hit_count: int = 0             # 命中次数
    size_bytes: int = 0            # 条目大小（估算）
    
    @property
    def is_expired(self) -> bool:
        """是否已过期"""
        return time.time() - self.created_at > self.ttl
    
    @property
    def age_seconds(self) -> float:
        """已存在时间（秒）"""
        return time.time() - self.created_at

@dataclass class CacheStats:
    """缓存统计"""
    total_entries: int = 0
    expired_entries: int = 0
    total_hits: int = 0
    total_misses: int = 0
    total_evictions: int = 0       # 被淘汰的条目数
    current_size_bytes: int = 0
    hit_rate: float = 0.0          # 命中率
    avg_entry_age: float = 0.0     # 平均条目年龄

请实现ResultCache类：

class ResultCache:
    """扫描结果缓存 — 带TTL过期和LRU淘汰的内存缓存"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600,
                 max_memory_mb: int = 100):
        """初始化缓存。
        max_size: 最大条目数，超限时按LRU淘汰
        default_ttl: 默认TTL（秒）
        max_memory_mb: 最大内存占用（MB），超限时激进淘汰"""
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()  # LRU用OrderedDict
        self._lock = threading.RLock()
        self._stats = CacheStats()
        self._cleanup_interval = 60  # 清理间隔（秒）
        self._cleanup_task: Optional[threading.Timer] = None
        self._start_cleanup_loop()
    
    # === 核心操作 ===
    def get(self, tool_name: str, target: str, params: dict = None) -> Optional[dict]:
        """查询缓存。如命中→移动条目到LRU尾部（最近使用）→返回result。
        如过期→删除→返回None。如未命中→返回None。"""
    
    def set(self, tool_name: str, target: str, result: dict, 
            params: dict = None, ttl: int = None) -> str:
        """写入缓存。
        1. 生成key = sha256(f'{tool_name}:{target}:{sorted(params.items())}')
        2. 如已有条目→覆盖并移到尾部
        3. 如新增条目且超max_size→淘汰最久未使用的（OrderedDict头部）
        4. 检查内存占用，超max_memory_bytes→激进淘汰（过期+LRU）
        5. 返回key"""
    
    def invalidate(self, tool_name: str = None, target: str = None) -> int:
        """使缓存失效。
        如指定tool_name只失效该工具的缓存；如指定target只失效该目标的缓存；
        如都指定只失效(tool, target)组合；如都不指定清空全部缓存。
        返回失效的条目数。"""
    
    def invalidate_expired(self) -> int:
        """清理所有过期条目。返回清理数量。"""
    
    # === 批量操作 ===
    def get_batch(self, queries: List[tuple]) -> List[Optional[dict]]:
        """批量查询。queries = [(tool_name, target, params), ...]
        返回结果列表，与queries顺序对应。"""
    
    def set_batch(self, entries: List[tuple]) -> List[str]:
        """批量写入。entries = [(tool_name, target, result, params, ttl), ...]
        返回key列表。"""
    
    # === 统计 ===
    def get_stats(self) -> CacheStats:
        """获取缓存统计。实时计算hit_rate = hits / (hits + misses)。"""
    
    def get_entries(self, tool_name: str = None, target: str = None,
                   include_expired: bool = False) -> List[CacheEntry]:
        """列出缓存条目。支持过滤。"""
    
    # === 维护 ===
    def _start_cleanup_loop(self) -> None:
        """启动后台定时清理线程（每_cleanup_interval秒清理一次过期条目）。"""
    
    def _cleanup(self) -> int:
        """执行清理：删除过期条目，如仍超max_size则LRU淘汰。
        返回清理/淘汰数量。"""
    
    def _check_memory(self) -> bool:
        """检查当前内存占用是否超限。返回是否超限。"""
    
    def _evict_lru(self, n: int = 1) -> int:
        """淘汰N个最久未使用的条目（OrderedDict头部）。返回实际淘汰数。"""
    
    def _evict_aggressive(self) -> int:
        """激进淘汰：先清过期，再清一半LRU，直到内存达标。"""
    
    def _estimate_size(self, entry: CacheEntry) -> int:
        """估算条目大小（字节）。简单策略：len(json.dumps(entry.result))。"""
    
    def _generate_key(self, tool_name: str, target: str, params: dict) -> str:
        """生成缓存键。sha256(f'{tool_name}:{target}:{json.dumps(sorted_params, sort_keys=True)}')"""
    
    def stop(self) -> None:
        """停止清理循环。用于程序退出时。"""
    
    # === 特殊缓存策略 ===
    def is_cacheable(self, tool_name: str, target: str, params: dict) -> bool:
        """判断某个操作是否适合缓存。
        不缓存的情况：
        - 工具名在DENYLIST中（如'rm', 'del', 'exploit'等破坏性操作）
        - 参数包含'_force'或'_nocache'
        - 目标是localhost/127.0.0.1且工具是网络扫描（结果不稳定）
        返回是否可缓存。"""

每个方法完整实现，中文docstring。
关键要求：
- 线程安全（用threading.RLock，因为M6可能被asyncio和sync代码同时调用）
- LRU用OrderedDict（move_to_end实现）
- 过期清理用后台线程（不是异步任务，因为缓存可能被同步代码调用）
- 内存估算用json.dumps长度近似
- 默认TTL按工具类型不同：nmap=300(5分钟，端口可能变)，sqlmap=3600(1小时)，crypto=86400(1天，密码不变)

输出：完整的result_cache.py文件。
```

**期望输出**：`result_cache.py`（300-400行）

---

### Agent-31：parallel_scanner.py 并发扫描器

**系统提示词：**
```
你是PentestAgent M6模块的并发扫描器开发专家。编写parallel_scanner.py，实现asyncio控制的并发工具执行。

技术要求：Python 3.10+，asyncio，Semaphore控制并发，中文docstring。

数据模型定义（在文件中定义）：

@dataclass class ScanTask:
    """扫描任务"""
    task_id: str                   # UUID
    tool_name: str                 # 工具名
    target: str                    # 目标
    params: dict = field(default_factory=dict)
    priority: int = 5              # 优先级（1-10，数字小优先）
    timeout: int = 300             # 超时（秒）
    retry_count: int = 0           # 已重试次数
    max_retries: int = 2           # 最大重试次数
    depends_on: List[str] = field(default_factory=list)  # 依赖的任务ID（先完成）
    
    status: str = "pending"        # pending|running|completed|failed|cancelled
    result: dict = field(default_factory=dict)
    error: str = ""
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    @property
    def duration_ms(self) -> int:
        """执行耗时（毫秒）"""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at) * 1000)
        return 0

@dataclass class ScanBatchResult:
    """批量扫描结果"""
    total: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    results: Dict[str, dict] = field(default_factory=dict)  # task_id -> result
    errors: Dict[str, str] = field(default_factory=dict)    # task_id -> error
    total_duration_ms: int = 0

请实现ParallelScanner类：

class ParallelScanner:
    """并发扫描器 — 控制多个扫描任务的并发执行"""
    
    def __init__(self, max_concurrent: int = 5, max_per_host: int = 2):
        """初始化。
        max_concurrent: 全局最大并发数（Semaphore）
        max_per_host: 每目标IP/域名最大并发数（防止对单个目标DoS）"""
        self._max_concurrent = max_concurrent
        self._max_per_host = max_per_host
        self._global_sem = asyncio.Semaphore(max_concurrent)
        self._host_sems: Dict[str, asyncio.Semaphore] = {}  # target -> Semaphore
        self._tasks: Dict[str, asyncio.Task] = {}           # task_id -> Task
        self._lock = asyncio.Lock()
    
    # === 单任务执行 ===
    async def execute(self, tool_name: str, target: str, params: dict = None,
                     timeout: int = 300, priority: int = 5) -> dict:
        """执行单个扫描任务。
        1. 获取全局Semaphore
        2. 获取目标专属Semaphore（防DoS）
        3. 调用实际工具执行
        4. 返回结果
        异常时自动重试（最多max_retries次）。"""
    
    # === 批量并发执行 ===
    async def execute_batch(self, tasks: List[ScanTask], 
                            progress_callback: Callable = None) -> ScanBatchResult:
        """批量执行扫描任务。
        1. 按优先级排序（priority升序，数字小优先）
        2. 按depends_on构建依赖图，先执行无依赖任务
        3. 创建asyncio.Task并发执行（受Semaphore限制）
        4. 如有progress_callback，定期调用报告进度
        5. 等待全部完成
        6. 返回ScanBatchResult
        
        依赖处理：如taskA depends_on taskB，taskA等taskB完成后才开始。
        循环依赖检测：如有循环依赖，报错并跳过相关任务。"""
    
    async def execute_batch_simple(self, task_tuples: List[tuple]) -> ScanBatchResult:
        """简化版批量执行。
        task_tuples = [(tool_name, target, params, timeout), ...]
        无依赖关系，全部并发（受Semaphore限制）。
        返回ScanBatchResult。"""
    
    # === 任务管理 ===
    async def cancel(self, task_id: str) -> bool:
        """取消指定任务。返回是否成功取消。"""
    
    async def cancel_all(self) -> int:
        """取消所有运行中的任务。返回取消数量。"""
    
    async def get_status(self, task_id: str) -> Optional[ScanTask]:
        """获取任务状态。"""
    
    async def list_tasks(self, status: str = None) -> List[ScanTask]:
        """列出所有任务。可按status过滤。"""
    
    # === 内部 ===
    async def _execute_single(self, task: ScanTask, 
                             actual_executor: Callable) -> dict:
        """执行单个任务的核心逻辑。
        1. 获取Semaphores
        2. 设置started_at
        3. 调用actual_executor(tool_name, target, params)
        4. 处理超时（asyncio.wait_for）
        5. 处理异常/重试
        6. 设置completed_at和result
        返回result dict。"""
    
    def _get_host_sem(self, target: str) -> asyncio.Semaphore:
        """获取/创建目标专属Semaphore。"""
    
    def _parse_host(self, target: str) -> str:
        """从target提取host（IP或域名）。
        '192.168.1.1:8080' -> '192.168.1.1'
        'http://example.com/path' -> 'example.com'"""
    
    def _has_circular_dependency(self, tasks: List[ScanTask]) -> tuple:
        """检测循环依赖。返回 (has_cycle: bool, cycle_task_ids: List[str])。"""

每个方法完整实现，中文docstring。
关键要求：
- 双重Semaphore：全局 + 每host（防对单目标DoS）
- 依赖图处理：拓扑排序 + 循环检测
- 超时控制：asyncio.wait_for + 工具级timeout
- 异常时自动重试（指数退避：1s, 2s, 4s）
- progress_callback签名：callback(completed, total, current_task_id, status)

输出：完整的parallel_scanner.py文件。
```

**期望输出**：`parallel_scanner.py`（250-350行）

---

### Agent-32：lazy_loader.py + memory_optimizer.py

**系统提示词：**
```
你是PentestAgent M6模块的延迟加载和内存优化开发专家。编写两个文件：lazy_loader.py和memory_optimizer.py。

【文件1：lazy_loader.py】

技术要求：Python 3.10+，标准库（importlib, sys, types, gc），零外部依赖。

实现LazyLoader类：

class LazyLoader:
    """延迟加载统一封装 — 让重量级模块首次使用时才加载，并复用已加载的模块"""
    
    # 已知需要延迟加载的模块及其用途
    LAZY_MODULES = {
        "pwn": {"purpose": "pwn_tools", "weight": "heavy", "used_by": "m2_ctf_kit.pwn_tools"},
        "r2pipe": {"purpose": "reverse_tools", "weight": "heavy", "used_by": "m2_ctf_kit.reverse_tools"},
        "pycryptodome": {"purpose": "crypto_tools", "weight": "medium", "used_by": "m2_ctf_kit.crypto_tools"},
        "jinja2": {"purpose": "templates", "weight": "medium", "used_by": "m3_reporter.template_engine"},
        "playwright": {"purpose": "pdf_export", "weight": "heavy", "used_by": "m3_reporter.pdf_exporter"},
        "aiosqlite": {"purpose": "blackboard", "weight": "light", "used_by": "m5_swarm_link.shared_blackboard"},
    }
    
    _loaded: Dict[str, Any] = {}       # 已加载的模块缓存
    _loading: Dict[str, asyncio.Lock] = {}  # 正在加载的锁（防重复加载）
    _load_times: Dict[str, float] = {}      # 各模块加载耗时记录
    
    @classmethod
    def get(cls, module_name: str) -> Any:
        """获取模块。如未加载→延迟加载→缓存→返回。
        如已加载→直接返回缓存。
        线程安全（用asyncio.Lock防并发重复加载）。"""
    
    @classmethod
    def preload(cls, module_names: List[str] = None) -> dict:
        """预加载指定模块。如不指定，预加载所有weight='light'的模块。
        返回 {module_name: load_time_ms}。"""
    
    @classmethod
    def unload(cls, module_name: str) -> bool:
        """卸载模块（从sys.modules和缓存中移除）。释放内存。
        返回是否成功卸载。"""
    
    @classmethod
    def is_loaded(cls, module_name: str) -> bool:
        """检查模块是否已加载。"""
    
    @classmethod
    def get_load_stats(cls) -> dict:
        """获取加载统计：
        {"loaded_modules": [...], "total_load_time_ms": ..., "avg_load_time_ms": ...}"""
    
    @classmethod
    def wrap_import(cls, module_name: str, alias: str = None) -> types.ModuleType:
        """包装import语句，使其变成延迟加载。
        用法：
        pwn = LazyLoader.wrap_import("pwn")  # 不是立即import，而是返回代理对象
        # 第一次访问pwn.remote()时才真正import pwn
        
        实现思路：返回一个代理模块对象，第一次属性访问时触发真实import。
        """

    @classmethod
    def install_import_hook(cls) -> None:
        """安装全局import hook。
        对LAZY_MODULES中的模块，拦截import使其变成延迟加载。
        谨慎使用，可能影响调试。"""

【文件2：memory_optimizer.py】

实现MemoryOptimizer类：

class MemoryOptimizer:
    """内存优化器 — 监控内存使用，超限时告警/清理"""
    
    def __init__(self, limit_mb: int = 512, gc_interval: int = 300,
                 cache_modules: List[str] = None):
        """初始化。
        limit_mb: 内存告警阈值（MB）
        gc_interval: 定期GC间隔（秒）
        cache_modules: 需要监控的缓存模块列表（如['m1_api_hub', 'm3_reporter']）"""
        self._limit_bytes = limit_mb * 1024 * 1024
        self._gc_interval = gc_interval
        self._cache_modules = cache_modules or []
        self._monitor_task: Optional[asyncio.Task] = None
        self._peak_bytes = 0
        self._alert_callbacks: List[Callable] = []
    
    # === 内存监控 ===
    async def start_monitoring(self) -> None:
        """启动内存监控循环（每gc_interval秒检查一次）。"""
        self._monitor_task = asyncio.create_task(self._monitor_loop())
    
    async def stop_monitoring(self) -> None:
        """停止监控循环。"""
        if self._monitor_task:
            self._monitor_task.cancel()
    
    async def _monitor_loop(self) -> None:
        """监控循环：
        1. 获取当前内存占用
        2. 如超过limit → 触发告警 → 执行清理
        3. 更新peak
        4. sleep(interval)"""
    
    def get_current_memory(self) -> int:
        """获取当前进程内存占用（字节）。
        使用psutil（如有）或/proc/self/status（Linux）或GetProcessMemoryInfo（Windows）。
        如都不可用，用sys.getsizeof估算主要对象。"""
    
    def get_peak_memory(self) -> int:
        """获取峰值内存占用。"""
    
    # === 清理 ===
    def trigger_gc(self, generation: int = 2) -> dict:
        """手动触发GC。返回清理统计：{"collected": N, "uncollectable": N}。"""
    
    async def cleanup_caches(self) -> dict:
        """清理所有缓存模块的过期/旧条目。
        调用各模块的清理方法（如ResultCache.invalidate_expired()）。
        返回各模块清理统计。"""
    
    def on_alert(self, callback: Callable[[int, int], None]) -> None:
        """注册内存告警回调。签名：callback(current_bytes, limit_bytes)。"""
    
    # === 报告 ===
    def get_memory_report(self) -> dict:
        """获取内存使用报告：
        {
            "current_mb": ...,
            "peak_mb": ...,
            "limit_mb": ...,
            "usage_ratio": ...,      # current/limit
            "gc_stats": {...},
            "module_caches": {      # 各模块缓存大小
                "m1_api_hub": {...},
                "m3_reporter": {...}
            }
        }"""

每个方法完整实现，中文docstring。
关键要求：
- lazy_loader的wrap_import返回代理对象（用types.ModuleType或自定义类）
- memory_optimizer的get_current_memory()优先用psutil（延迟加载），不可用则用系统特定方法
- 内存监控用asyncio.Task后台运行
- cleanup_caches通过反射调用各模块的清理方法

输出：两个文件的完整代码，用"=== lazy_loader.py ==="和"=== memory_optimizer.py ==="分隔。
```

**期望输出**：`lazy_loader.py`（150-200行）+ `memory_optimizer.py`（150-200行）

---

## Phase 1 返回检查点

**三个Agent完成后，把代码复制回主控。主控审查：**
1. ResultCache的LRU淘汰是否正确（OrderedDict.move_to_end）
2. ParallelScanner的双重Semaphore是否正确（全局+每host）
3. LazyLoader的wrap_import代理对象是否能正确拦截属性访问

---

## Phase 2：启动（1个Agent，依赖全部前置输出）

### Agent-33：__init__.py + turbo_commands.py + M0透明wrapper

**系统提示词：**
```
你是PentestAgent M6模块的系统集成开发专家。编写__init__.py、turbo_commands.py和M0透明wrapper代码。

【Part 1：__init__.py】

实现M6模块入口：
1. 开关控制：CPA_M6_TURBO环境变量（默认true）
2. 初始化函数init_m6()：创建ResultCache、ParallelScanner、MemoryOptimizer
3. 全局wrapper注册：在M2-M5的工具执行函数上自动包裹缓存和并发
4. 公共API导出：get_result_cache(), get_parallel_scanner(), get_memory_optimizer(), get_lazy_loader()
5. is_m6_enabled() -> bool

关键：全局wrapper注册逻辑

```python
def _wrap_tool_execution():
    """全局包裹M2-M5的工具执行函数，自动加缓存和并发控制。
    不修改被包裹函数的签名和行为，对调用者完全透明。"""
    
    # 被包裹的函数列表（按模块）
    WRAPPED_FUNCTIONS = {
        "m2_ctf_kit.pwn_tools": ["pwn_remote", "pwn_interactive_send", "pwn_leak_info"],
        "m2_ctf_kit.crypto_tools": ["crypto_auto_solve", "crypto_caesar", "crypto_xor"],
        "m2_ctf_kit.reverse_tools": ["rev_analyze", "rev_strings", "rev_functions"],
        "m3_reporter.screenshot_catcher": ["capture", "capture_element"],
    }
    
    # 对每个函数：
    # 1. 保存原始函数引用 original = func
    # 2. 创建wrapper：
    #    async def wrapper(*args, **kwargs):
    #        # 1. 检查缓存（如ResultCache.get命中且未过期→直接返回）
    #        # 2. 调用ParallelScanner.execute控制并发（如当前并发已满→等待）
    #        # 3. 执行original(*args, **kwargs)
    #        # 4. 写入ResultCache.set（如结果可缓存）
    #        # 5. 返回结果
    # 3. wrapper.__wrapped__ = original（保存原始引用，方便unwrap）
    # 4. 替换模块中的函数引用
    
    # 注意：wrapper需要处理async和sync函数两种情况
```

【Part 2：turbo_commands.py】

实现/turbo命令系列：

/turbo                         — 显示Turbo状态（缓存命中/并发数/内存）
/turbo cache stats             — 缓存统计
/turbo cache clear             — 清空缓存
/turbo cache clear <tool>      — 清空指定工具的缓存
/turbo scan status             — 显示当前并发扫描状态
/turbo scan cancel             — 取消所有扫描
/turbo memory                  — 内存使用报告
/turbo memory gc               — 手动触发GC
/turbo memory cleanup          — 清理所有缓存
/turbo preload                 — 预加载常用模块
/turbo preload status          — 预加载状态

【Part 3：M0侵入层代码】

提供以下HOOK点（用 === CPA M6 HOOK BEGIN/END === 包裹）：

侵入点1：pentestagent/__main__.py — main()函数
```python
# === CPA M6 HOOK BEGIN ===
if os.getenv("CPA_M6_TURBO", "true").lower() == "true":
    try:
        from cpa_modules.m6_turbo import init_m6
        import asyncio
        asyncio.run(init_m6())
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"M6模块初始化失败: {e}")
# === CPA M6 HOOK END ===
```

侵入点2：pentestagent/interface/commands.py — 命令注册
```python
# === CPA M6 HOOK BEGIN ===
if os.getenv("CPA_M6_TURBO", "true").lower() == "true":
    try:
        from cpa_modules.m6_turbo.turbo_commands import (
            cmd_turbo, cmd_turbo_cache, cmd_turbo_scan, cmd_turbo_memory
        )
        # 注册 /turbo 系列命令
    except Exception:
        pass
# === CPA M6 HOOK END ===
```

侵入点3：pentestagent/config/settings.py — Settings类
```python
# === CPA M6 HOOK BEGIN ===
cpa_m6_turbo: bool = field(default_factory=lambda: os.getenv("CPA_M6_TURBO", "true").lower() == "true")
cpa_m6_cache_enabled: bool = field(default_factory=lambda: os.getenv("CPA_M6_CACHE_ENABLED", "true").lower() == "true")
cpa_m6_cache_max_size: int = field(default_factory=lambda: int(os.getenv("CPA_M6_CACHE_MAX_SIZE", "1000")))
cpa_m6_concurrent_limit: int = field(default_factory=lambda: int(os.getenv("CPA_M6_CONCURRENT_LIMIT", "5")))
cpa_m6_memory_limit_mb: int = field(default_factory=lambda: int(os.getenv("CPA_M6_MEMORY_LIMIT_MB", "512")))
# === CPA M6 HOOK END ===
```

侵入点4：pentestagent/tools/ 或 M2工具执行入口 — 透明wrapper注册
```python
# === CPA M6 HOOK BEGIN ===
# 在M2-M5模块全部加载完成后，调用：
if is_m6_enabled():
    try:
        from cpa_modules.m6_turbo import _wrap_tool_execution
        _wrap_tool_execution()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"M6 wrapper注册失败: {e}")
# === CPA M6 HOOK END ===
```

输出：三个部分的完整代码，用"=== Part 1/2/3 ==="分隔。
```

**期望输出**：`__init__.py`（100-150行）+ `turbo_commands.py`（150-200行）+ 4个M0侵入点

---

## 最终集成清单

**Agent-33完成后，全部到齐。主控做最终集成审阅：**

1. **文件完整性**：4个文件（result_cache.py, parallel_scanner.py, lazy_loader.py, memory_optimizer.py, __init__.py, turbo_commands.py）
2. **缓存正确性**：ResultCache.set→get是否命中同一key
3. **并发安全性**：ParallelScanner的Semaphore是否正确限制并发数
4. **透明wrapper**：_wrap_tool_execution是否不改变被包裹函数的签名
5. **内存监控**：MemoryOptimizer.get_current_memory()是否能在Windows本机正确获取内存
6. **M0侵入量**：4个HOOK点，预计<15行
7. **默认开启**：CPA_M6_TURBO默认true

**审阅通过后，M6模块开发完成，整个PentestAgent-CPA项目6个模块全部完成！**
