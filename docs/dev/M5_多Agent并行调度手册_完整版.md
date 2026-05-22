# M5 模块（多Agent协作链）多Agent并行开发调度手册

> **使用方式**：将此文档上传到新对话，按Phase分批创建Agent并执行  
> **前置条件**：M1-M4已完成，M5依赖M1的ProviderManager和M4的AuditLogger  
> **借鉴来源**：Pentest Swarm AI的共享黑板（Postgres+pgvector）和信息素权重机制  

---

## M5模块设计概要

### 解决什么问题

原版PentestAgent有4种操作模式（Assist/Agent/Crew/Interact），但**Crew模式下的Agent间通信非常弱**——没有共享记忆、没有任务协调、没有优先级动态调整。M5借鉴Pentest Swarm AI的Stigmergy（信息素）机制，增强多Agent协作能力，让多个Agent可以像蜂群一样协同工作。

### 借鉴来源

| 借鉴对象 | 借鉴内容 | 改进点 |
|---------|---------|--------|
| **Pentest Swarm AI** | 共享黑板（Postgres+pgvector） | 用SQLite/内存替代PostgreSQL，保持轻量 |
| **Pentest Swarm AI** | 信息素权重（Pheromone） | 简化权重计算，增加CTF场景适配 |
| **Pentest Swarm AI** | 4自主Agent（侦察/分类/利用/报告） | 不做预设Agent角色，支持动态组队 |
| **PentestAgent原版** | Crew模式基础 | 增强通信层，不重构已有模式 |

### 核心概念

**共享黑板（Shared Blackboard）**：
- 所有Agent共享的消息板，任何Agent可以写入消息（发现、建议、警告），其他Agent可以订阅接收
- 类比：一群人在同一个白板上写笔记，所有人都能看到

**信息素（Pheromone）**：
- 来自蚁群算法的概念——Agent在某个路径上留下"信息素"，其他Agent闻到后倾向于跟随
- 在M5中：Agent在某个目标上发现漏洞 → 增加该目标的信息素权重 → 其他Agent优先处理该目标
- 信息素会随时间衰减（避免永久高权重）

**共识机制（Consensus）**：
- 多个Agent对同一个问题独立给出答案 → 投票机制选择最佳答案 → 提高决策可靠性

### 架构设计

```
cpa_modules/m5_swarm_link/
├── __init__.py                  # 模块入口 + 开关（Agent-29实现）
├── shared_blackboard.py         # 共享黑板：消息存储/查询/订阅（Agent-25）
├── pheromone_router.py          # 信息素路由器：任务优先级动态调整（Agent-26）
├── agent_messenger.py           # Agent信使：Agent间通信协议（Agent-27）
├── consensus_mechanism.py       # 共识机制：多Agent决策投票（Agent-28）
└── swarm_commands.py            # /swarm命令注册（Agent-29）
```

### 关键设计约束

1. **不重构Crew模式**：在PentestAgent已有的Crew模式基础上增加通信层，不改原有逻辑
2. **SQLite共享黑板**：用SQLite替代PostgreSQL（Pentest Swarm AI用Postgres），保持轻量
3. **可选加载**：M5是高级功能，默认关闭（CPA_M5_SWARM_LINK=false）
4. **向后兼容**：不启用M5时，Crew模式行为完全不变
5. **M0侵入<15行**：主要在Crew模式执行前后加消息同步钩子

### 环境变量开关

```bash
# .env
CPA_M5_SWARM_LINK=false          # M5总开关（默认关闭，高级功能）
CPA_M5_BLACKBOARD_DB=./logs/blackboard.db   # 共享黑板SQLite数据库路径
CPA_M5_PHEROMONE_DECAY=0.95      # 信息素衰减率（每秒乘以0.95）
CPA_M5_PHEROMONE_THRESHOLD=0.1   # 信息素最小阈值（低于此值忽略）
CPA_M5_CONSENSUS_AGENTS=3        # 共识机制最少Agent数
CPA_M5_CONSENSUS_THRESHOLD=0.6   # 共识通过阈值（60%Agent同意）
CPA_M5_MSG_RETENTION_HOURS=24    # 消息保留时间（小时）
```

---

## Phase 1：并行启动（3个Agent，无依赖）

### Agent-25：shared_blackboard.py 共享黑板

**系统提示词：**
```
你是PentestAgent M5模块的共享黑板开发专家。编写shared_blackboard.py，实现多Agent共享的消息存储和订阅系统。

技术要求：Python 3.10+，使用SQLite（sqlite3模块，零外部依赖），async异步，中文docstring。

数据模型定义（在文件中定义）：

@dataclass class BlackboardMessage:
    """黑板消息"""
    msg_id: str                    # UUID
    msg_type: str                  # "finding"|"suggestion"|"warning"|"status"|"command"|"result"
    sender: str                    # 发送Agent的ID
    content: str                   # 消息内容
    target: str = ""               # 关联目标（IP/域名）
    metadata: dict = field(default_factory=dict)  # 额外元数据
    pheromone_boost: float = 0.0   # 信息素加成（0-1，由pheromone_router设置）
    timestamp: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None  # 过期时间
    
    # msg_type说明：
    # finding:     发现漏洞（如"发现SQL注入 at /login"）
    # suggestion:  建议操作（如"建议使用sqlmap进一步探测"）
    # warning:     警告（如"检测到WAF，建议降低请求频率"）
    # status:      状态更新（如"Agent-1完成端口扫描，发现3个开放端口"）
    # command:     指令（如"Agent-2请对8080端口进行Web扫描"）
    # result:      执行结果（如"sqlmap执行完成，确认存在盲注"）

@dataclass class MessageFilter:
    """消息过滤器"""
    msg_types: List[str] = None     # 按类型过滤
    senders: List[str] = None       # 按发送者过滤
    target: str = None              # 按目标过滤
    since: datetime = None          # 时间范围开始
    until: datetime = None          # 时间范围结束
    min_pheromone: float = 0.0      # 最小信息素值

请实现SharedBlackboard类：

class SharedBlackboard:
    """共享黑板 — 多Agent共享的消息存储和订阅系统"""
    
    def __init__(self, db_path: str = "./logs/blackboard.db", 
                 retention_hours: int = 24):
        """初始化。创建SQLite数据库和表。"""
        self._db_path = db_path
        self._retention = retention_hours
        self._lock = asyncio.Lock()
        self._subscribers: Dict[str, List[Callable]] = {}  # msg_type -> callbacks
        self._init_db()
    
    # === 数据库初始化 ===
    def _init_db(self) -> None:
        """创建SQLite表：
        messages表: msg_id, msg_type, sender, content, target, metadata(json), 
                     pheromone_boost, timestamp, expires_at
        索引: timestamp, msg_type, target, sender
        """
    
    def _cleanup_expired(self) -> int:
        """清理过期消息。返回删除数量。"""
    
    # === 消息写入 ===
    async def post(self, msg: BlackboardMessage) -> str:
        """发布消息到黑板。
        1. 写入SQLite
        2. 通知所有订阅者
        3. 返回msg_id
        """
    
    async def post_finding(self, sender: str, content: str, target: str,
                          metadata: dict = None) -> str:
        """便捷方法：发布发现"""
        return await self.post(BlackboardMessage(...))
    
    async def post_suggestion(self, sender: str, content: str, target: str = "",
                             metadata: dict = None) -> str:
        """便捷方法：发布建议"""
    
    async def post_warning(self, sender: str, content: str, target: str = "",
                          metadata: dict = None) -> str:
        """便捷方法：发布警告"""
    
    async def post_status(self, sender: str, content: str, target: str = "",
                         metadata: dict = None) -> str:
        """便捷方法：发布状态更新"""
    
    async def post_command(self, sender: str, content: str, target: str = "",
                          recipient: str = "", metadata: dict = None) -> str:
        """便捷方法：发布指令（recipient指定接收Agent）"""
    
    async def post_result(self, sender: str, content: str, target: str = "",
                         command_id: str = "", metadata: dict = None) -> str:
        """便捷方法：发布执行结果"""
    
    # === 消息查询 ===
    async def query(self, filter: MessageFilter = None, limit: int = 100,
                   order: str = "desc") -> List[BlackboardMessage]:
        """查询消息。支持多种过滤条件组合。"""
    
    async def get_recent(self, n: int = 50) -> List[BlackboardMessage]:
        """获取最近N条消息"""
    
    async def get_by_target(self, target: str, limit: int = 50) -> List[BlackboardMessage]:
        """获取与指定目标相关的所有消息"""
    
    async def get_by_type(self, msg_type: str, limit: int = 50) -> List[BlackboardMessage]:
        """获取指定类型的消息"""
    
    async def get_timeline(self, target: str) -> List[BlackboardMessage]:
        """获取指定目标的时间线（按时间排序的所有消息）"""
    
    async def get(self, msg_id: str) -> Optional[BlackboardMessage]:
        """根据ID获取单条消息"""
    
    # === 消息订阅 ===
    def subscribe(self, msg_type: str, callback: Callable[[BlackboardMessage], None]) -> str:
        """订阅指定类型的消息。新消息到达时自动调用callback。
        返回订阅ID（用于取消订阅）。"""
    
    def unsubscribe(self, sub_id: str) -> bool:
        """取消订阅"""
    
    async def _notify_subscribers(self, msg: BlackboardMessage) -> None:
        """通知所有订阅了该消息类型的订阅者"""
    
    # === 统计 ===
    async def get_stats(self) -> dict:
        """返回黑板统计：
        {"total_messages": N, "by_type": {...}, "by_sender": {...}, "active_targets": [...]}"""
    
    async def clear(self, older_than_hours: int = None) -> int:
        """清空消息。如指定older_than_hours只清理 older_than_hours 小时之前的。
        返回删除数量。"""
    
    # === 辅助 ===
    def _dict_to_msg(self, row: sqlite3.Row) -> BlackboardMessage:
        """SQLite行转BlackboardMessage"""
    
    def _msg_to_dict(self, msg: BlackboardMessage) -> dict:
        """BlackboardMessage转字典（用于SQLite插入）"""

每个方法完整实现，中文docstring。
关键要求：
- 使用SQLite的async包装（aiosqlite或asyncio.to_thread）
- metadata字段用JSON字符串存储
- 消息订阅是内存中的回调机制（不走数据库）
- 自动清理过期消息（post时检查）

输出：完整的shared_blackboard.py文件。
```

**期望输出**：`shared_blackboard.py`（350-450行）

---

### Agent-26：pheromone_router.py 信息素路由器

**系统提示词：**
```
你是PentestAgent M5模块的信息素路由器开发专家。编写pheromone_router.py，实现任务优先级的动态调整。

概念：借鉴蚁群算法的信息素机制——Agent在某个目标上发现价值信息 → 释放信息素 → 其他Agent被吸引优先处理该目标 → 信息素随时间自然衰减。

技术要求：Python 3.10+，标准库（asyncio, datetime, heapq），零外部依赖。

数据模型定义（在文件中定义）：

@dataclass class PheromoneTrail:
    """信息素痕迹"""
    target: str                    # 目标（IP/域名/URL路径）
    strength: float = 1.0          # 信息素强度（0-100）
    source: str = ""               # 释放源（Agent ID + 发现类型）
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    decay_rate: float = 0.95       # 每秒衰减率
    
    @property
    def current_strength(self) -> float:
        """计算当前信息素强度（考虑时间衰减）"""
        elapsed = (datetime.now() - self.last_updated).total_seconds()
        return self.strength * (self.decay_rate ** elapsed)
    
    @property
    def is_active(self) -> bool:
        """是否仍有效（强度高于阈值）"""
        return self.current_strength > 0.1  # 默认阈值0.1

@dataclass class TaskPriority:
    """任务优先级"""
    target: str
    base_priority: int = 5         # 基础优先级（1-10，用户设定）
    pheromone_bonus: float = 0.0   # 信息素加成（由信息素强度计算）
    agent_load: int = 0            # 当前处理该目标的Agent数（负载惩罚）
    deadline: Optional[datetime] = None  # 截止时间（紧急加成）
    
    @property
    def final_score(self) -> float:
        """最终优先级分数 = base_priority + pheromone_bonus - load_penalty + deadline_bonus"""

请实现PheromoneRouter类：

class PheromoneRouter:
    """信息素路由器 — 动态调整任务优先级"""
    
    def __init__(self, decay_rate: float = 0.95, threshold: float = 0.1,
                 boost_per_finding: float = 2.0):
        """初始化。
        decay_rate: 每秒衰减率（0.95表示每秒衰减5%）
        threshold: 信息素最小有效值
        boost_per_finding: 每次发现增加的信息素强度
        """
        self._trails: Dict[str, PheromoneTrail] = {}  # target -> PheromoneTrail
        self._decay_rate = decay_rate
        self._threshold = threshold
        self._boost_per_finding = boost_per_finding
        self._lock = asyncio.Lock()
        self._decay_task: Optional[asyncio.Task] = None
    
    # === 信息素管理 ===
    async def deposit(self, target: str, source: str = "", 
                     strength: float = None) -> None:
        """在目标上释放信息素。
        如果该目标已有信息素 → 累加（不是覆盖）。
        如果这是新目标 → 创建新的PheromoneTrail。"""
    
    async def deposit_finding(self, target: str, finding_type: str,
                             severity: str = "medium") -> None:
        """便捷方法：根据发现类型和严重程度自动计算信息素强度。
        severity: critical=+5, high=+3, medium=+2, low=+1, info=+0.5
        finding_type: web_vuln=额外+1, pwn_shell=额外+3, crypto_solved=额外+2"""
    
    async def evaporate(self, target: str = None) -> None:
        """手动触发信息素衰减。
        如指定target只衰减该目标，否则衰减所有目标。"""
    
    async def get_strength(self, target: str) -> float:
        """获取指定目标的当前信息素强度（考虑衰减）"""
    
    async def get_active_trails(self) -> List[PheromoneTrail]:
        """获取所有活跃的信息素痕迹（按强度降序）"""
    
    async def get_top_targets(self, n: int = 5) -> List[tuple]:
        """获取信息素强度最高的N个目标。
        返回 [(target, strength), ...]"""
    
    # === 任务优先级 ===
    async def calculate_priority(self, target: str, base_priority: int = 5,
                                agent_count: int = 0) -> TaskPriority:
        """计算指定目标的最终优先级。
        pheromone_bonus = min(信息素强度 / 10, 5.0)  # 最高+5
        load_penalty = agent_count * 0.5  # 每个Agent减0.5
        deadline_bonus = 根据deadline计算（快到期+3，已过期+5）"""
    
    async def get_prioritized_queue(self, targets: List[str],
                                   base_priorities: dict = None) -> List[TaskPriority]:
        """对目标列表按优先级排序。
        返回按final_score降序排列的TaskPriority列表。
        这是核心方法——Crew模式调用它决定下一个处理哪个目标。"""
    
    async def recommend_next_target(self, available_targets: List[str],
                                   current_agents: dict = None) -> tuple:
        """推荐下一个应该处理的目标。
        返回 (target, reason)，reason说明为什么推荐这个目标。"""
    
    # === 衰减循环 ===
    async def start_decay_loop(self, interval: int = 60) -> None:
        """启动后台衰减循环（每interval秒衰减一次）。"""
        self._decay_task = asyncio.create_task(self._decay_loop(interval))
    
    async def stop_decay_loop(self) -> None:
        """停止衰减循环。"""
        if self._decay_task:
            self._decay_task.cancel()
    
    async def _decay_loop(self, interval: int) -> None:
        """后台循环：每隔interval秒对所有信息素进行衰减计算。
        删除已衰减到阈值以下的痕迹。"""
    
    # === 统计 ===
    async def get_stats(self) -> dict:
        """返回信息素统计：
        {"total_trails": N, "active_trails": N, "top_target": str, "avg_strength": float}"""
    
    async def reset(self) -> None:
        """重置所有信息素（用于新任务开始）。"""

每个方法完整实现，中文docstring。
关键要求：
- 信息素使用current_strength属性动态计算（不存储衰减后的值）
- 衰减循环是后台asyncio.Task
- get_prioritized_queue是核心方法，算法要清晰
- deposit_finding根据发现类型自动计算强度

输出：完整的pheromone_router.py文件。
```

**期望输出**：`pheromone_router.py`（250-350行）

---

### Agent-27：agent_messenger.py Agent信使

**系统提示词：**
```
你是PentestAgent M5模块的Agent通信协议开发专家。编写agent_messenger.py，实现Agent间的消息发送和接收协议。

技术要求：Python 3.10+，async异步，使用SharedBlackboard作为底层传输。

你依赖的接口（假设已由Agent-25提供）：

class SharedBlackboard:
    async def post(self, msg: BlackboardMessage) -> str: ...
    async def query(self, filter: MessageFilter = None, ...) -> List[BlackboardMessage]: ...
    def subscribe(self, msg_type: str, callback) -> str: ...
    def unsubscribe(self, sub_id: str) -> bool: ...

@dataclass class BlackboardMessage:
    msg_id: str; msg_type: str; sender: str; content: str
    target: str = ""; metadata: dict = None; pheromone_boost: float = 0.0
    timestamp: datetime = None; expires_at: datetime = None

请实现AgentMessenger类：

class AgentMessenger:
    """Agent信使 — 封装Agent间的通信协议"""
    
    def __init__(self, agent_id: str, blackboard: SharedBlackboard,
                 pheromone_router: PheromoneRouter = None):
        """初始化。
        agent_id: 本Agent的唯一标识
        blackboard: 共享黑板实例
        pheromone_router: 信息素路由器（可选，用于自动调整消息优先级）"""
        self._agent_id = agent_id
        self._bb = blackboard
        self._pheromone = pheromone_router
        self._subscriptions: List[str] = []  # 本Agent的订阅ID列表
        self._inbox: asyncio.Queue = asyncio.Queue()  # 收件箱队列
        self._handlers: Dict[str, Callable] = {}  # 消息类型 -> 处理函数
    
    # === 发送消息 ===
    async def send(self, msg_type: str, content: str, target: str = "",
                  metadata: dict = None, to_agent: str = None) -> str:
        """发送消息。
        如指定to_agent → 在metadata中标记recipient，只有该Agent处理
        如不指定 → 广播给所有Agent"""
    
    async def report_finding(self, target: str, finding: str, 
                            severity: str = "medium", details: dict = None) -> str:
        """报告发现。自动：
        1. 发布finding消息到黑板
        2. 如pheromone_router存在 → deposit_finding增加信息素
        3. 返回msg_id"""
    
    async def request_help(self, target: str, problem: str,
                          required_skill: str = "") -> str:
        """请求其他Agent协助。
        发送suggestion类型消息，metadata中标记help_request=true。"""
    
    async def notify_status(self, status: str, target: str = "",
                           progress: float = 0.0) -> str:
        """通知状态更新。progress: 0.0-1.0。"""
    
    async def acknowledge(self, msg_id: str, result: str = "ack") -> str:
        """确认收到某条消息。发送ack类型消息。"""
    
    # === 接收消息 ===
    async def start_listening(self) -> None:
        """开始监听黑板消息。订阅所有消息类型，收到后写入_inbox队列。"""
    
    async def stop_listening(self) -> None:
        """停止监听。取消所有订阅。"""
    
    async def receive(self, timeout: float = None) -> Optional[BlackboardMessage]:
        """从收件箱取出一条消息。如为空则等待（带超时）。"""
        return await asyncio.wait_for(self._inbox.get(), timeout=timeout)
    
    async def receive_all(self, limit: int = 100) -> List[BlackboardMessage]:
        """取出收件箱中所有消息。"""
    
    def register_handler(self, msg_type: str, handler: Callable) -> None:
        """注册消息类型处理函数。
        handler签名：async def handler(msg: BlackboardMessage) -> None"""
    
    async def _dispatch(self, msg: BlackboardMessage) -> None:
        """分发消息到对应handler（如有）或放入inbox"""
    
    # === 组通信 ===
    async def join_group(self, group_id: str) -> None:
        """加入通信组（如"web_scan_team"）。后续消息可发送到组。"""
    
    async def leave_group(self, group_id: str) -> None:
        """离开通信组。"""
    
    async def send_to_group(self, group_id: str, content: str,
                           msg_type: str = "status") -> str:
        """发送消息到指定组。"""
    
    # === 查询 ===
    async def get_conversation(self, target: str, 
                               since: datetime = None) -> List[BlackboardMessage]:
        """获取关于某个目标的所有对话消息。"""
    
    async def wait_for_response(self, command_msg_id: str, 
                                timeout: float = 30.0) -> Optional[BlackboardMessage]:
        """等待对某条command消息的response。"""
    
    @property
    def agent_id(self) -> str:
        """本Agent的ID"""
    
    @property
    def unread_count(self) -> int:
        """未读消息数"""

每个方法完整实现，中文docstring。
关键要求：
- AgentMessenger是对SharedBlackboard的封装，不直接操作数据库
- 每个Agent有自己的AgentMessenger实例（agent_id区分）
- 消息分发优先调用handler，无handler则放入inbox
- wait_for_response是同步等待异步回复的模式

输出：完整的agent_messenger.py文件。
```

**期望输出**：`agent_messenger.py`（250-350行）

---

## Phase 1 返回检查点

**三个Agent完成后，把代码复制回主控。主控审查：**
1. shared_blackboard的metadata字段JSON序列化是否正确
2. pheromone_router的current_strength动态计算是否正确（时间衰减公式）
3. agent_messenger的receive()超时处理是否正确

---

## Phase 2：启动（1个Agent，依赖Phase 1的接口）

### Agent-28：consensus_mechanism.py 共识机制

**系统提示词：**
```
你是PentestAgent M5模块的共识机制开发专家。编写consensus_mechanism.py，实现多Agent对同一问题的投票决策。

你依赖的接口（假设已由Agent-27提供）：

class AgentMessenger:
    async def send(self, msg_type: str, content: str, target: str = "", ...) -> str: ...
    async def receive(self, timeout: float = None) -> Optional[BlackboardMessage]: ...
    @property
    def agent_id(self) -> str: ...

@dataclass class BlackboardMessage:
    msg_id: str; msg_type: str; sender: str; content: str
    metadata: dict = None

请实现ConsensusMechanism类：

class ConsensusMechanism:
    """共识机制 — 多Agent对同一问题独立决策，投票选出最佳答案"""
    
    def __init__(self, messenger: AgentMessenger, 
                 min_agents: int = 3, threshold: float = 0.6):
        """初始化。
        min_agents: 最少需要的Agent数才能发起共识
        threshold: 共识通过阈值（如0.6表示60%Agent同意则通过）"""
        self._messenger = messenger
        self._min_agents = min_agents
        self._threshold = threshold
        self._active_votes: Dict[str, dict] = {}  # vote_id -> vote_data
    
    # === 发起共识 ===
    async def propose(self, question: str, options: List[str],
                     timeout: float = 30.0) -> dict:
        """发起共识投票。
        
        流程：
        1. 生成vote_id
        2. 广播question和options给所有Agent
        3. 等待各Agent回复（带timeout）
        4. 统计投票结果
        5. 返回共识结果
        
        返回结果：
        {
            "consensus_reached": bool,    # 是否达成共识
            "winner": str,                # 获胜选项
            "vote_count": dict,           # {option: count}
            "agreement_ratio": float,     # 同意比例
            "participating_agents": int,  # 参与的Agent数
            "details": str                # 结果说明
        }
        """
    
    async def propose_binary(self, question: str, timeout: float = 30.0) -> dict:
        """发起二元共识（是/否）。options自动设为 ["yes", "no"。
        返回同上格式。"""
    
    async def propose_priority_ranking(self, targets: List[str],
                                      timeout: float = 30.0) -> dict:
        """发起目标优先级排序共识。
        让每个Agent对targets排序，用Borda计数法综合得出最终排序。
        返回 {"consensus_reached": bool, "ranking": List[str], ...}"""
    
    # === 参与投票 ===
    async def vote(self, vote_id: str, choice: str, confidence: float = 1.0) -> None:
        """对指定投票投一票。confidence: 0.0-1.0（置信度，用于加权）。"""
    
    async def auto_vote(self, vote_id: str, context: dict = None) -> None:
        """自动投票——基于本Agent的分析能力自动选择最佳选项。
        当前版本：简单选择（后续可接入LLM做分析）。"""
    
    # === 投票管理 ===
    def get_vote_status(self, vote_id: str) -> dict:
        """获取投票状态：{total_votes, options, deadline, is_open}"""
    
    async def close_vote(self, vote_id: str) -> dict:
        """手动关闭投票并计算结果。"""
    
    # === 统计方法 ===
    def _count_votes(self, votes: List[dict]) -> dict:
        """统计投票。返回 {option: weighted_count}。"""
    
    def _check_consensus(self, vote_counts: dict, total_agents: int) -> tuple:
        """检查是否达成共识。
        返回 (reached: bool, winner: str, ratio: float)。"""
    
    def _borda_count(self, rankings: List[List[str]]) -> List[str]:
        """Borda计数法：对多个排序列表综合排序。
        例：3个Agent对[A,B,C]排序
        Agent1: [A,B,C] → A=2分, B=1分, C=0分
        Agent2: [A,C,B] → A=2分, C=1分, B=0分
        Agent3: [B,A,C] → B=2分, A=1分, C=0分
        总分: A=5, B=3, C=1 → 最终排序 [A,B,C]"""

每个方法完整实现，中文docstring。
关键要求：
- propose()的投票收集使用timeout机制，不无限等待
- _borda_count()实现正确的Borda计数算法
- 投票结果考虑confidence加权
- 少于min_agents参与时consensus_reached=false

输出：完整的consensus_mechanism.py文件。
```

**期望输出**：`consensus_mechanism.py`（200-300行）

---

## Phase 2 返回检查点

**Agent-28完成后，把代码复制回主控。主控审查：**
1. _borda_count()的算法是否正确（标准Borda计数）
2. propose()的timeout机制是否合理（不阻塞）
3. _check_consensus()的阈值判断是否正确

---

## Phase 3：启动（1个Agent，依赖全部前置输出）

### Agent-29：__init__.py + swarm_commands.py + M0侵入层

**系统提示词：**
```
你是PentestAgent M5模块的系统集成开发专家。编写__init__.py、swarm_commands.py和M0侵入层代码。

【Part 1：__init__.py】

实现M5模块入口：
1. 开关控制：CPA_M5_SWARM_LINK环境变量（默认false）
2. 初始化函数init_m5()：创建SharedBlackboard、PheromoneRouter、并为当前Agent创建AgentMessenger
3. 公共API导出：get_blackboard(), get_pheromone_router(), get_messenger(agent_id), get_consensus_mechanism(agent_id)
4. is_m5_enabled() -> bool

注意：M5默认关闭（CPA_M5_SWARM_LINK=false），只有用户明确开启时才加载。

导入：
from .shared_blackboard import SharedBlackboard
from .pheromone_router import PheromoneRouter
from .agent_messenger import AgentMessenger
from .consensus_mechanism import ConsensusMechanism

【Part 2：swarm_commands.py】

实现/swarm命令系列：

/swarm                         — 显示Swarm Link状态
/swarm status                  — 显示信息素统计和活跃目标
/swarm top                     — 显示信息素Top 5目标
/swarm deposit <target>        — 手动在目标上释放信息素
/swarm board                   — 查看共享黑板最近消息
/swarm board query <type>      — 按类型查询黑板消息
/swarm propose <question>      — 发起共识投票
/swarm vote <vote_id> <choice> — 对指定投票投一票
/swarm consensus <targets...>  — 对目标列表发起优先级排序共识
/swarm msg <content>           — 发送消息到黑板
/swarm join <group>            — 加入通信组
/swarm leave <group>           — 离开通信组
/swarm reset                   — 重置所有信息素

每个命令返回str（TUI显示内容）。

需要导入的模块（假设由Phase 1/2的Agent提供）：
from .shared_blackboard import SharedBlackboard, MessageFilter
from .pheromone_router import PheromoneRouter
from .agent_messenger import AgentMessenger
from .consensus_mechanism import ConsensusMechanism

【Part 3：M0侵入层代码】

提供以下HOOK点（用 === CPA M5 HOOK BEGIN/END === 包裹）：

侵入点1：pentestagent/__main__.py — main()函数
```python
# === CPA M5 HOOK BEGIN ===
if os.getenv("CPA_M5_SWARM_LINK", "false").lower() == "true":
    try:
        from cpa_modules.m5_swarm_link import init_m5
        import asyncio
        asyncio.run(init_m5())
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"M5模块初始化失败: {e}")
# === CPA M5 HOOK END ===
```

侵入点2：pentestagent/agents/crew.py（或Crew模式执行处）— Crew模式执行前后
```python
# === CPA M5 HOOK BEGIN ===
# 在Crew模式开始执行任务前：
if is_m5_enabled():
    from cpa_modules.m5_swarm_link import get_pheromone_router
    router = get_pheromone_router()
    # 调用router.get_prioritized_queue()调整任务顺序
    # 调用router.deposit_finding()记录Agent的发现

# 在Crew模式的Agent完成一个发现后：
if is_m5_enabled():
    from cpa_modules.m5_swarm_link import get_messenger
    messenger = get_messenger(agent_id)
    # 调用messenger.report_finding()通知其他Agent
# === CPA M5 HOOK END ===
```

侵入点3：pentestagent/interface/commands.py — 命令注册
```python
# === CPA M5 HOOK BEGIN ===
if os.getenv("CPA_M5_SWARM_LINK", "false").lower() == "true":
    try:
        from cpa_modules.m5_swarm_link.swarm_commands import (
            cmd_swarm, cmd_swarm_status, cmd_swarm_top, cmd_swarm_deposit,
            cmd_swarm_board, cmd_swarm_propose, cmd_swarm_vote, ...
        )
        # 注册 /swarm 系列命令
    except Exception:
        pass
# === CPA M5 HOOK END ===
```

侵入点4：pentestagent/config/settings.py — Settings类
```python
# === CPA M5 HOOK BEGIN ===
cpa_m5_swarm_link: bool = field(default_factory=lambda: os.getenv("CPA_M5_SWARM_LINK", "false").lower() == "true")
cpa_m5_blackboard_db: str = field(default_factory=lambda: os.getenv("CPA_M5_BLACKBOARD_DB", "./logs/blackboard.db"))
cpa_m5_pheromone_decay: float = field(default_factory=lambda: float(os.getenv("CPA_M5_PHEROMONE_DECAY", "0.95")))
cpa_m5_consensus_agents: int = field(default_factory=lambda: int(os.getenv("CPA_M5_CONSENSUS_AGENTS", "3")))
# === CPA M5 HOOK END ===
```

输出：三个部分的完整代码，用"=== Part 1/2/3 ==="分隔。
```

**期望输出**：`__init__.py`（80-120行）+ `swarm_commands.py`（200-300行）+ 4个M0侵入点

---

## 最终集成清单

**Agent-29完成后，全部到齐。主控做最终集成审阅：**

1. **文件完整性**：5个文件（shared_blackboard.py, pheromone_router.py, agent_messenger.py, consensus_mechanism.py, __init__.py, swarm_commands.py）
2. **信息素衰减公式**：current_strength = strength × decay_rate^elapsed_seconds，是否正确
3. **Borda计数**：_borda_count()对多个排序列表的综合排序是否正确
4. **消息链路**：Agent发现 → messenger.report_finding() → blackboard.post() → 其他Agent订阅收到
5. **共识流程**：propose() → 广播 → 收集投票 → _count_votes() → _check_consensus() → 返回结果
6. **M0侵入量**：4个HOOK点，预计<15行
7. **默认关闭**：CPA_M5_SWARM_LINK默认false，不启用时不影响任何已有功能

**审阅通过后，M5模块开发完成。**
