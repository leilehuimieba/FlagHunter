# M4 模块（审计合规守卫）多Agent并行开发调度手册

> **使用方式**：将此文档上传到新对话，按Phase分批创建Agent并执行  
> **前置条件**：M1+M2+M3已完成，M4可独立运行也可依赖M3的报告数据  
> **借鉴来源**：RedAmon的EvoGraph审计、RoE硬拦截、危险操作确认门  

---

## M4模块设计概要

### 解决什么问题

原版PentestAgent**零审计、零授权管理、零数据保护**。在企业合规渗透测试场景下，这直接导致：
- 操作无法追溯（客户要求留痕）
- 可能误攻击未授权目标（法律风险）
- 敏感信息泄露（报告中的API Key、密码未脱敏）

M4补齐**企业级合规安全**能力。

### 借鉴来源

| 借鉴对象 | 借鉴内容 | 改进点 |
|---------|---------|--------|
| **RedAmon** | EvoGraph审计日志（每步检查点持久化） | 简化为JSON Lines，无需PostgreSQL |
| **RedAmon** | RoE文档硬拦截 | 增加CIDR和通配符域名支持 |
| **RedAmon** | 危险操作确认门 | 增加可配置的策略规则 |
| **Pentest Swarm AI** | 双层范围强制 | 结合RoE解析和实时校验 |

### 合规能力矩阵

| 合规要求 | M4实现方式 | 企业价值 |
|---------|-----------|---------|
| **操作留痕** | audit_logger: JSON Lines审计日志，每条记录不可篡改 | 满足等保2.0/ISO27001 |
| **授权验证** | roe_engine: 解析RoE文档，提取授权IP/域名/时间窗口 | 法律风险防护 |
| **范围强制** | scope_enforcer: 硬拦截未授权目标（内核级阻断感） | 防止误操作 |
| **危险确认** | approval_gate: 删除/提权/横向移动需人工确认 | 防止失控 |
| **数据保护** | data_protection: API Key/密码/IP自动脱敏 | 防止敏感信息泄露 |
| **证据保全** | audit_logger.export(): 导出完整证据包（zip） | 可用于法律举证 |

### 架构设计

```
cpa_modules/m4_audit_guard/
├── __init__.py                  # 模块入口 + 开关（Agent-24实现）
├── audit_logger.py              # 审计日志核心（Agent-19）
│   └── logs/                    # 审计日志存储目录
│       ├── audit_20250121.jsonl # 按日期分文件
│       └── archive/             # 归档目录
├── roe_engine.py                # RoE规则引擎（Agent-20）
│   └── roe_templates/           # RoE文档模板
│       ├── standard_roe.txt     # 标准授权模板
│       └── minimal_roe.txt      # 最小授权模板
├── scope_enforcer.py            # 范围强制校验（Agent-21）
├── approval_gate.py             # 危险操作确认门（Agent-22）
├── data_protection.py           # 数据保护/脱敏（Agent-23）
└── ctf_commands.py              # /audit命令注册（Agent-24）
```

### 关键设计约束

1. **零外部依赖**：审计日志用JSON Lines（纯文本），不依赖PostgreSQL/Neo4j
2. **不可篡改**：审计日志文件只追加（append-only），写入后标记为只读
3. **硬拦截**：未授权目标的攻击在**执行前**被阻断（不是事后告警）
4. **可配置策略**：危险操作列表、确认方式、自动阻断阈值均可自定义
5. **透明运行**：合规检查对用户透明，不干扰正常操作流程
6. **M0侵入<15行**：主要在工具执行前加拦截钩子和执行后加记录钩子

### 环境变量开关

```bash
# .env
CPA_M4_AUDIT_GUARD=true          # M4总开关
CPA_M4_LOG_DIR=./logs/audit      # 审计日志存储目录
CPA_M4_LOG_RETENTION_DAYS=90     # 日志保留天数（超期自动归档）
CPA_M4_ROE_FILE=./roe.txt        # RoE授权文档路径
CPA_M4_STRICT_MODE=false         # 严格模式（true时无RoE文档则拒绝所有操作）
CPA_M4_DANGEROUS_TOOLS=rm,dd,format,mkfs,del,format-volume  # 危险工具列表
CPA_M4_AUTO_BLOCK_GOV=true       # 自动拦截.gov/.edu/.mil域名
CPA_M4_MASK_SENSITIVE=true       # 自动脱敏敏感信息
CPA_M4_APPROVAL_TIMEOUT=300      # 确认门超时时间（秒）
```

---

## Phase 1：并行启动（3个Agent，无依赖）

### Agent-19：audit_logger.py 审计日志核心

**系统提示词：**
```
你是PentestAgent M4模块的审计日志开发专家。编写audit_logger.py，实现不可篡改的操作审计日志系统。

技术要求：Python 3.10+，标准库（json, pathlib, datetime, hashlib, os），零外部依赖。

数据模型定义（在文件中定义）：

@dataclass class AuditEntry:
    """单条审计记录"""
    timestamp: datetime           # UTC时间戳
    entry_id: str                 # 唯一ID（UUID）
    session_id: str               # 所属会话ID
    action_type: str              # 操作类型: "command"|"tool"|"llm_request"|"llm_response"|"file_access"|"network"|"flag_submit"
    action_detail: dict           # 操作详情（不同类型不同结构）
    target: str = ""              # 操作目标（IP/域名/文件路径）
    user: str = "default"         # 操作用户
    source_ip: str = ""           # 源IP（如通过SSH代理）
    result: str = ""              # 执行结果: "success"|"failure"|"blocked"|"pending"
    duration_ms: int = 0          # 执行耗时
    hash_chain: str = ""          # 哈希链（上一条的hash+当前内容）
    
    # 不同类型action_detail示例：
    # command: {"command": "nmap -sS 192.168.1.1", "exit_code": 0, "output_preview": "..."}
    # tool: {"tool_name": "sqlmap", "args": {"url": "..."}, "finding": "SQL注入"}
    # llm_request: {"model": "claude-sonnet", "prompt_tokens": 100, "messages_preview": "..."}
    # llm_response: {"model": "claude-sonnet", "completion_tokens": 50, "response_preview": "..."}
    # file_access: {"file_path": "/etc/passwd", "operation": "read"}
    # network: {"dest_ip": "192.168.1.1", "dest_port": 80, "protocol": "tcp"}
    # flag_submit: {"flag": "flag{***}", "platform": "ctfd", "challenge_id": "123", "correct": true}

@dataclass class AuditSummary:
    """审计摘要"""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    total_commands: int = 0
    total_tools: int = 0
    total_llm_requests: int = 0
    total_findings: int = 0
    blocked_actions: int = 0          # 被拦截的操作数
    targets_accessed: List[str] = field(default_factory=list)
    risk_level: str = "low"           # low|medium|high|critical

请实现AuditLogger类：

class AuditLogger:
    """审计日志管理器 — 不可篡改的操作留痕系统"""
    
    def __init__(self, log_dir: str = "./logs/audit", retention_days: int = 90):
        """初始化日志目录，创建当日日志文件"""
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._retention_days = retention_days
        self._current_file: Optional[Path] = None
        self._last_hash: str = "0" * 64  # 创世hash
        self._load_last_hash()           # 从已有日志恢复最后hash
    
    # === 核心记录 ===
    def log(self, entry: AuditEntry) -> str:
        """记录一条审计日志。自动计算hash_chain保证不可篡改。
        返回entry_id。"""
        # 流程：
        # 1. 计算hash_chain = sha256(上一条hash + entry内容json)
        # 2. 写入当前日期的.jsonl文件（追加模式）
        # 3. 设置文件为只读（chmod 444 on Linux, 等效于Windows）
        # 4. 更新_last_hash
        # 5. 返回entry_id
    
    def log_command(self, command: str, target: str = "", exit_code: int = None, 
                   output_preview: str = "", session_id: str = "") -> str:
        """便捷方法：记录命令执行"""
    
    def log_tool(self, tool_name: str, args: dict, target: str = "", 
                finding: str = "", session_id: str = "") -> str:
        """便捷方法：记录工具调用"""
    
    def log_llm_request(self, model: str, prompt_tokens: int, messages_preview: str,
                       provider_id: str = "", session_id: str = "") -> str:
        """便捷方法：记录LLM请求"""
    
    def log_llm_response(self, model: str, completion_tokens: int, response_preview: str,
                        provider_id: str = "", session_id: str = "") -> str:
        """便捷方法：记录LLM响应"""
    
    def log_file_access(self, file_path: str, operation: str = "read", 
                       session_id: str = "") -> str:
        """便捷方法：记录文件访问"""
    
    def log_network(self, dest_ip: str, dest_port: int, protocol: str = "tcp",
                   session_id: str = "") -> str:
        """便捷方法：记录网络连接"""
    
    def log_flag_submit(self, flag: str, platform: str, challenge_id: str = "",
                       correct: bool = False, session_id: str = "") -> str:
        """便捷方法：记录Flag提交（Flag自动脱敏）"""
    
    # === 查询 ===
    def query(self, session_id: str = None, action_type: str = None, 
              target: str = None, start_time: datetime = None, 
              end_time: datetime = None, limit: int = 100) -> List[AuditEntry]:
        """查询审计日志。支持多条件组合过滤。"""
    
    def query_by_session(self, session_id: str) -> List[AuditEntry]:
        """查询指定会话的所有日志"""
    
    def get_session_summary(self, session_id: str) -> AuditSummary:
        """获取指定会话的审计摘要统计"""
    
    def get_recent(self, n: int = 50) -> List[AuditEntry]:
        """获取最近N条日志"""
    
    # === 完整性验证 ===
    def verify_chain(self, date: str = None) -> tuple:
        """验证指定日期的日志哈希链完整性。
        返回 (valid: bool, first_broken_id: str)。
        逐条计算hash_chain，与存储值对比。"""
    
    def verify_all(self) -> dict:
        """验证所有日志文件的完整性。
        返回 {filename: (valid, first_broken_id)}"""
    
    # === 导出 ===
    def export_session(self, session_id: str, output_path: str) -> str:
        """导出指定会话的完整审计日志为JSON文件（用于举证）。
        包含完整性验证报告。返回文件路径。"""
    
    def export_evidence_package(self, session_id: str, output_path: str) -> str:
        """导出证据包（zip文件），包含：
        - 审计日志JSON
        - 完整性验证报告
        - 摘要统计
        - 时间线可视化（HTML）
        返回zip文件路径。"""
    
    # === 维护 ===
    def archive_old_logs(self) -> int:
        """归档超过retention_days的旧日志到archive/目录。
        返回归档文件数量。"""
    
    def _get_current_logfile(self) -> Path:
        """获取当前日期的日志文件路径：log_dir/audit_YYYYMMDD.jsonl"""
    
    def _load_last_hash(self) -> None:
        """从当前日志文件的最后一条恢复_last_hash（保证重启后链式不中断）"""
    
    def _compute_hash(self, previous_hash: str, entry_data: str) -> str:
        """计算hash_chain = sha256(previous_hash + entry_data)"""

每个方法完整实现，中文docstring。
关键要求：
- 日志文件使用JSON Lines格式（每行一个JSON对象）
- hash_chain机制确保日志不可篡改（任何修改都会导致后续hash不匹配）
- 文件写入后立即flush，保证崩溃不丢数据
- Windows下用os.chmod设置只读权限

输出：完整的audit_logger.py文件。
```

**期望输出**：`audit_logger.py`（350-450行）

---

### Agent-20：roe_engine.py RoE规则引擎

**系统提示词：**
```
你是PentestAgent M4模块的RoE规则引擎开发专家。编写roe_engine.py，实现授权范围文档的解析和规则提取。

RoE（Rules of Engagement）是渗透测试的授权文档，定义了：
- 授权目标（IP地址/CIDR/域名）
- 授权时间窗口
- 允许的测试方法
- 禁止的操作
- 紧急联系方式

技术要求：Python 3.10+，标准库（ipaddress, re, datetime, pathlib），零外部依赖。

数据模型定义（在文件中定义）：

@dataclass class RoERule:
    """RoE规则"""
    rule_type: str  # "allow_ip"|"allow_cidr"|"allow_domain"|"allow_wildcard_domain"|"allow_time"|"deny_ip"|"deny_domain"|"deny_tool"|"require_approval"
    value: str      # 规则值（IP/域名/时间/CIDR等）
    description: str = ""  # 规则说明
    priority: int = 1      # 优先级（deny规则优先级更高）

@dataclass class RoEConfig:
    """RoE配置（从文档解析出的完整配置）"""
    client_name: str = ""
    project_name: str = ""
    tester_name: str = ""
    allowed_ips: List[str] = field(default_factory=list)      # 允许的IP列表
    allowed_cidrs: List[str] = field(default_factory=list)    # 允许的CIDR
    allowed_domains: List[str] = field(default_factory=list)  # 允许的域名
    denied_ips: List[str] = field(default_factory=list)       # 明确禁止的IP
    denied_domains: List[str] = field(default_factory=list)   # 明确禁止的域名
    denied_tools: List[str] = field(default_factory=list)     # 禁止使用的工具
    time_window_start: Optional[datetime] = None              # 授权开始时间
    time_window_end: Optional[datetime] = None                # 授权结束时间
    require_approval_tools: List[str] = field(default_factory=list)  # 需确认的工具
    emergency_contact: str = ""
    raw_rules: List[RoERule] = field(default_factory=list)    # 原始规则列表

请实现RoEEngine类：

class RoEEngine:
    """RoE规则引擎 — 解析授权文档，提供授权校验"""
    
    def __init__(self, roe_file: str = None):
        """初始化。如指定roe_file则自动加载解析。"""
        self._config: Optional[RoEConfig] = None
        self._loaded = False
        if roe_file:
            self.load_roe(roe_file)
    
    # === RoE文档解析 ===
    def load_roe(self, file_path: str) -> RoEConfig:
        """从文件加载RoE文档。支持.txt/.md/.yaml格式。
        自动检测格式并调用对应解析器。"""
    
    def parse_txt(self, content: str) -> RoEConfig:
        """解析纯文本格式的RoE文档。
        支持的关键字（不区分大小写）：
        - ALLOW IP: 192.168.1.1, 10.0.0.0/24
        - ALLOW DOMAIN: example.com, *.test.com
        - DENY IP: 192.168.1.100
        - DENY DOMAIN: prod.example.com
        - DENY TOOL: sqlmap --dump-all
        - TIME WINDOW: 2026-01-01 00:00 to 2026-01-07 23:59
        - REQUIRE APPROVAL: metasploit, rm
        - CLIENT: 客户名称
        - PROJECT: 项目名称
        - TESTER: 测试人员
        - EMERGENCY: 紧急联系人
        返回RoEConfig。"""
    
    def parse_yaml(self, content: str) -> RoEConfig:
        """解析YAML格式的RoE文档（结构化程度更高）。"""
    
    def _parse_ip_list(self, value: str) -> tuple:
        """解析IP列表字符串，返回 (ips, cidrs)。
        例: '192.168.1.1, 10.0.0.0/24' -> (['192.168.1.1'], ['10.0.0.0/24'])"""
    
    def _parse_domain_list(self, value: str) -> List[str]:
        """解析域名列表。支持通配符 *.example.com"""
    
    # === 授权校验 ===
    def is_ip_allowed(self, ip: str) -> tuple:
        """检查IP是否在授权范围内。
        返回 (allowed: bool, reason: str)。
        检查顺序：
        1. 是否在denied_ips中 → False
        2. 是否在allowed_ips中 → True
        3. 是否在allowed_cidrs中 → True
        4. 无RoE配置且非严格模式 → True
        5. 无RoE配置且严格模式 → False
        6. 有RoE配置但IP不在任何allow规则中 → False"""
    
    def is_domain_allowed(self, domain: str) -> tuple:
        """检查域名是否在授权范围内。
        返回 (allowed: bool, reason: str)。
        支持通配符匹配（*.example.com匹配sub.example.com）。"""
    
    def is_tool_allowed(self, tool_name: str) -> tuple:
        """检查工具是否允许使用。
        返回 (allowed: bool, requires_approval: bool, reason: str)。"""
    
    def is_time_allowed(self, check_time: datetime = None) -> tuple:
        """检查当前时间是否在授权时间窗口内。
        返回 (allowed: bool, reason: str)。"""
    
    def check_target(self, target: str) -> tuple:
        """综合检查目标是否授权。
        自动识别target是IP还是域名，调用对应检查方法。
        返回 (allowed: bool, reason: str)。"""
    
    # === 规则管理 ===
    def add_rule(self, rule: RoERule) -> None:
        """动态添加规则（用于运行时调整）"""
    
    def remove_rule(self, rule_type: str, value: str) -> bool:
        """移除指定规则"""
    
    def get_config_summary(self) -> str:
        """获取RoE配置摘要（用于TUI显示）"""
        # 返回格式：
        # RoE配置: 客户-项目
        # 授权IP: 3个 + 2个CIDR
        # 授权域名: 5个 (含2个通配符)
        # 禁止工具: sqlmap --dump-all
        # 时间窗口: 2026-01-01 ~ 2026-01-07
        # 需确认工具: metasploit, rm
    
    @property
    def is_loaded(self) -> bool:
        """是否已加载RoE配置"""
    
    @property
    def config(self) -> Optional[RoEConfig]:
        """当前RoE配置"""

每个方法完整实现，中文docstring。
输出：完整的roe_engine.py文件 + 两个RoE模板文件（standard_roe.txt和minimal_roe.txt）。
```

**期望输出**：`roe_engine.py`（300-400行）+ 2个模板文件

---

### Agent-21：scope_enforcer.py 范围强制校验

**系统提示词：**
```
你是PentestAgent M4模块的范围强制校验开发专家。编写scope_enforcer.py，实现对未授权目标的硬拦截。

你依赖的接口（假设已由Agent-20提供）：

class RoEEngine:
    def is_ip_allowed(self, ip: str) -> tuple: ...       # (bool, reason)
    def is_domain_allowed(self, domain: str) -> tuple: ...
    def is_tool_allowed(self, tool: str) -> tuple: ...     # (bool, requires_approval, reason)
    def is_time_allowed(self, t: datetime) -> tuple: ...
    def check_target(self, target: str) -> tuple: ...      # (bool, reason)

class AuditLogger:
    def log(self, entry: AuditEntry) -> str: ...
    def log_command(self, command: str, target: str, result: str, ...) -> str: ...

请实现ScopeEnforcer类：

class ScopeEnforcer:
    """范围强制校验器 — 在执行前拦截未授权操作"""
    
    def __init__(self, roe_engine: RoEEngine, audit_logger: AuditLogger,
                 auto_block_gov: bool = True, strict_mode: bool = False):
        """初始化。
        auto_block_gov: 是否自动拦截.gov/.edu/.mil域名
        strict_mode: 严格模式（无RoE时拒绝所有操作）"""
        self._roe = roe_engine
        self._audit = audit_logger
        self._auto_block_gov = auto_block_gov
        self._strict_mode = strict_mode
        self._blocked_count = 0
        self._allowed_count = 0
    
    # === 核心校验 ===
    async def validate(self, action: str, target: str, tool: str = "", 
                      command: str = "") -> dict:
        """校验操作是否授权。在工具执行前调用。
        
        返回结果字典：
        {
            "allowed": bool,           # 是否允许执行
            "blocked": bool,           # 是否被拦截
            "reason": str,             # 说明原因
            "requires_approval": bool, # 是否需要人工确认
            "auto_blocked": bool       # 是否被自动规则拦截
        }
        
        校验流程：
        1. 如target为空 → 允许（可能是本地操作）
        2. 解析target提取所有IP和域名
        3. 检查是否命中自动拦截规则（.gov/.edu/.mil）
        4. 调用RoEEngine.check_target()检查授权
        5. 检查工具是否在禁止列表中
        6. 检查时间窗口
        7. 记录审计日志（allowed或blocked）
        8. 返回校验结果
        """
    
    def validate_sync(self, action: str, target: str, tool: str = "", 
                     command: str = "") -> dict:
        """同步版本的validate（用于非异步上下文）"""
    
    # === 目标解析 ===
    def extract_targets(self, text: str) -> dict:
        """从命令文本中提取所有目标。
        返回 {"ips": [...], "domains": [...], "urls": [...]}
        使用正则表达式提取：
        - IP: \d+\.\d+\.\d+\.\d+
        - CIDR: \d+\.\d+\.\d+\.\d+/\d+
        - Domain: [a-zA-Z0-9.-]+\.[a-zA-Z]{2,}
        - URL: https?://[^\s]+
        """
    
    def _is_gov_domain(self, domain: str) -> bool:
        """检查是否为.gov/.edu/.mil域名或其子域名"""
    
    def _is_private_ip(self, ip: str) -> bool:
        """检查是否为内网IP（RFC1918）"""
    
    # === 拦截记录 ===
    def get_stats(self) -> dict:
        """返回拦截统计：
        {"allowed": N, "blocked": N, "auto_blocked": N, "approval_required": N}"""
    
    def get_blocked_log(self, limit: int = 50) -> List[dict]:
        """返回被拦截的操作记录"""
    
    # === 装饰器（方便使用）===
    @staticmethod
    def enforce(action_name: str = ""):
        """装饰器：自动对函数进行范围校验。
        用法：
        @ScopeEnforcer.enforce(action_name="端口扫描")
        async def nmap_scan(target: str, ...):
            ...
        
        装饰器会自动：
        1. 提取target参数
        2. 调用validate()
        3. 如blocked → 记录审计日志并抛出ScopeBlockedException
        4. 如requires_approval → 等待确认（或记录待确认）
        5. 如allowed → 正常执行函数
        """

自定义异常：
class ScopeBlockedException(Exception):
    """操作被范围强制拦截时抛出"""
    def __init__(self, target: str, reason: str, action: str = ""):
        self.target = target
        self.reason = reason
        self.action = action

每个方法完整实现，中文docstring。
输出：完整的scope_enforcer.py文件。
```

**期望输出**：`scope_enforcer.py`（250-350行）

---

## Phase 1 返回检查点

**三个Agent完成后，把代码复制回主控。主控审查：**
1. audit_logger的hash_chain计算是否正确（用sha256链式）
2. roe_engine的通配符域名匹配是否正确（*.example.com匹配sub.example.com但不匹配example.com）
3. scope_enforcer的validate()返回值结构是否与approval_gate期望的一致

---

## Phase 2：并行启动（2个Agent，依赖Phase 1的接口）

### Agent-22：approval_gate.py 危险操作确认门

**系统提示词：**
```
你是PentestAgent M4模块的危险操作确认门开发专家。编写approval_gate.py，实现对危险操作的人工确认机制。

你依赖的接口（假设已由Agent-19和Agent-21提供）：

class AuditLogger:
    def log(self, entry: AuditEntry) -> str: ...

class ScopeEnforcer:
    def validate(self, action: str, target: str, tool: str, command: str) -> dict:
        # 返回 {"allowed": bool, "blocked": bool, "reason": str, 
        #        "requires_approval": bool, "auto_blocked": bool}

请实现ApprovalGate类：

class ApprovalGate:
    """危险操作确认门 — 高风险操作需人工确认后执行"""
    
    # 默认危险操作配置
    DEFAULT_DANGEROUS_TOOLS = [
        "rm", "del", "remove", "delete",
        "dd", "format", "mkfs", "fdisk",
        "format-volume", "remove-item",
        "msfvenom", "exploit", "exploit -j",
        "sqlmap --dump-all", "sqlmap --os-shell",
        "hydra -t", "john --wordlist",
    ]
    
    DEFAULT_DANGEROUS_PATTERNS = [
        r"rm\s+-rf\s+/",           # rm -rf /
        r">\s*/dev/sd[a-z]",       # 覆盖磁盘
        r"DROP\s+DATABASE",        # 删除数据库
        r"DELETE\s+FROM",          # 删除数据
        r"shutdown\s+-h",          # 关机
        r"reboot",                 # 重启
    ]
    
    def __init__(self, audit_logger: AuditLogger, 
                 dangerous_tools: List[str] = None,
                 dangerous_patterns: List[str] = None,
                 approval_timeout: int = 300,
                 auto_approve_below_risk: str = "low"):
        """初始化确认门。
        dangerous_tools: 需要确认的工具列表
        dangerous_patterns: 需要确认的命令正则模式
        approval_timeout: 确认超时时间（秒）
        auto_approve_below_risk: 低于此风险等级的操作自动通过（low/medium/none）
        """
        self._audit = audit_logger
        self._dangerous_tools = dangerous_tools or self.DEFAULT_DANGEROUS_TOOLS[:]
        self._dangerous_patterns = dangerous_patterns or self.DEFAULT_DANGEROUS_PATTERNS[:]
        self._timeout = approval_timeout
        self._auto_approve = auto_approve_below_risk
        self._pending_approvals: Dict[str, dict] = {}  # 待确认的操作
        self._approved_count = 0
        self._denied_count = 0
    
    # === 核心确认流程 ===
    async def check(self, action: str, target: str, tool: str = "", 
                   command: str = "", context: dict = None) -> dict:
        """检查操作是否需要确认。
        
        返回结果：
        {
            "approved": bool,       # 是否已通过（或无需确认）
            "requires_input": bool, # 是否需要用户输入确认
            "approval_id": str,     # 确认ID（需确认时）
            "risk_level": str,      # 风险等级: low/medium/high/critical
            "reason": str,          # 说明
            "suggested_action": str # 建议操作
        }
        
        判断流程：
        1. 检查tool是否在dangerous_tools中 → requires_approval
        2. 检查command是否匹配dangerous_patterns → requires_approval
        3. 检查scope_enforcer是否返回requires_approval
        4. 计算risk_level（基于工具+目标+模式匹配）
        5. 如risk_level <= auto_approve → 自动通过
        6. 如需要确认 → 生成approval_id，记录待确认，返回requires_input=true
        7. 如不需要确认 → 自动通过
        """
    
    async def approve(self, approval_id: str, approved: bool = True, 
                     notes: str = "") -> dict:
        """用户响应确认请求。
        approved=True: 允许执行
        approved=False: 拒绝执行
        返回 {"success": bool, "message": str}"""
    
    def check_sync(self, action: str, target: str, tool: str = "", 
                  command: str = "") -> dict:
        """同步版本（自动判断，不等待用户输入）
        如需要确认且无法等待输入 → 返回approved=false（保守策略）"""
    
    # === 风险评估 ===
    def assess_risk(self, tool: str, command: str, target: str) -> str:
        """评估操作风险等级。
        返回 low/medium/high/critical。
        评估因素：
        - 工具危险程度（rm=critical, nmap=low）
        - 目标重要性（生产环境=critical, 测试环境=low）
        - 命令破坏性（--dump-all=high, --banner=low）
        """)
    
    def _tool_risk_score(self, tool: str) -> int:
        """工具风险评分 0-10"""
        # rm=10, dd=10, sqlmap=6, nmap=3, curl=2, ping=1
    
    def _target_risk_score(self, target: str) -> int:
        """目标风险评分 0-10"""
        # 生产域名=10, .gov=10, 测试IP=2, localhost=1
    
    def _pattern_risk_score(self, command: str) -> int:
        """命令模式风险评分 0-10"""
        # 匹配dangerous_patterns则高分
    
    # === 查询 ===
    def get_pending_approvals(self) -> List[dict]:
        """获取所有待确认的操作"""
    
    def get_stats(self) -> dict:
        """返回统计：{approved, denied, pending, auto_approved}"""
    
    # === 配置管理 ===
    def add_dangerous_tool(self, tool: str) -> None:
        """动态添加危险工具"""
    
    def remove_dangerous_tool(self, tool: str) -> None:
        """移除危险工具"""
    
    def add_dangerous_pattern(self, pattern: str) -> None:
        """动态添加危险模式（正则表达式）"""

每个方法完整实现，中文docstring。
输出：完整的approval_gate.py文件。
```

**期望输出**：`approval_gate.py`（250-350行）

---

### Agent-23：data_protection.py 数据保护/脱敏

**系统提示词：**
```
你是PentestAgent M4模块的数据保护开发专家。编写data_protection.py，实现敏感信息的自动检测和脱敏。

技术要求：Python 3.10+，标准库（re, hashlib, ipaddress），零外部依赖。

实现DataProtector类：

class DataProtector:
    """数据保护器 — 自动检测和脱敏敏感信息"""
    
    # 敏感信息类型和检测正则
    SENSITIVE_PATTERNS = {
        "api_key": {
            "pattern": r"(sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36})",
            "mask": lambda m: m.group(1)[:4] + "****" + m.group(1)[-4:] if len(m.group(1)) > 12 else "****"
        },
        "password": {
            "pattern": r"(password\s*[=:]\s*)([^\s&]+)",
            "mask": lambda m: m.group(1) + "****"
        },
        "token": {
            "pattern": r"(token\s*[=:]\s*|Bearer\s+)([a-zA-Z0-9_\-\.]+)",
            "mask": lambda m: m.group(1) + "****"
        },
        "ip_address": {
            "pattern": r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
            "mask": lambda m: _mask_ip(m.group(1)),
            "configurable": True  # 可在配置中开关
        },
        "email": {
            "pattern": r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
            "mask": lambda m: _mask_email(m.group(1)),
            "configurable": True
        },
        "flag": {
            "pattern": r"(flag\{[a-zA-Z0-9_\-]+\})",
            "mask": lambda m: "flag{***}",
            "configurable": True
        },
        "credit_card": {
            "pattern": r"\b(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b",
            "mask": lambda m: "****-****-****-" + m.group(1)[-4:]
        },
    }
    
    def __init__(self, mask_ips: bool = False, mask_emails: bool = True, 
                 mask_flags: bool = False):
        """初始化。configurable类型的敏感信息可通过参数开关。"""
        self._config = {
            "ip_address": mask_ips,
            "email": mask_emails,
            "flag": mask_flags,
        }
    
    # === 脱敏 ===
    def mask(self, text: str, extra_patterns: dict = None) -> str:
        """对文本进行全量脱敏。返回脱敏后的文本。
        按SENSITIVE_PATTERNS顺序逐个匹配替换。
        extra_patterns: 额外的自定义脱敏规则。"""
    
    def mask_file(self, file_path: str, output_path: str = None) -> str:
        """对文件内容进行脱敏。如指定output_path则写入新文件，否则覆盖原文件。
        返回输出文件路径。"""
    
    def mask_structured(self, data: dict, fields_to_mask: List[str] = None) -> dict:
        """对结构化数据（字典）进行脱敏。
        递归遍历所有字段值，对字符串值调用mask()。
        fields_to_mask: 指定需要脱敏的字段名列表（如 ["api_key", "password"]）。
        返回脱敏后的新字典（不修改原字典）。"""
    
    # === 检测 ===
    def scan(self, text: str) -> List[dict]:
        """扫描文本中的敏感信息，不替换只检测。
        返回检测结果列表：
        [{"type": "api_key", "position": (start, end), "preview": "sk-ab****cd", "severity": "high"}, ...]
        """
    
    def scan_file(self, file_path: str) -> List[dict]:
        """扫描文件中的敏感信息"""
    
    def has_sensitive(self, text: str) -> bool:
        """快速检查文本是否包含敏感信息"""
    
    # === 报告脱敏专用 ===
    def sanitize_for_report(self, report_data: dict) -> dict:
        """对报告数据进行脱敏（专用于导出报告前的处理）。
        脱敏规则：
        - api_key/password/token: 始终脱敏
        - ip_address: 根据mask_ips配置
        - email: 根据mask_emails配置
        - flag: 根据mask_flags配置（CTF报告通常不脱敏Flag）
        - command输出中的敏感信息: 脱敏
        返回脱敏后的报告数据。"""
    
    def sanitize_audit_log(self, log_entry: dict) -> dict:
        """对审计日志进行脱敏（用于日志展示）。
        与sanitize_for_report的区别：审计日志中保留更多原始信息，只脱敏极高危的（如API Key）。"""
    
    # === 辅助函数 ===
    @staticmethod
    def _mask_ip(ip: str) -> str:
        """IP脱敏：192.168.1.100 → 192.168.x.x"""
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.x.x" if len(parts) == 4 else "x.x.x.x"
    
    @staticmethod
    def _mask_email(email: str) -> str:
        """邮箱脱敏：user@example.com → u***@example.com"""
        if "@" not in email:
            return "***"
        local, domain = email.split("@", 1)
        masked_local = local[0] + "***" if len(local) > 1 else "***"
        return f"{masked_local}@{domain}"
    
    @staticmethod
    def hash_identifier(value: str) -> str:
        """对标识符进行哈希（用于匿名化，保留可匹配性）。
        返回sha256(value)[:16]（16字符hex前缀，足够区分不泄露原始值）。"""

每个方法完整实现，中文docstring。
输出：完整的data_protection.py文件。
```

**期望输出**：`data_protection.py`（200-300行）

---

## Phase 2 返回检查点

**两个Agent完成后，把代码复制回主控。主控审查：**
1. approval_gate的risk_level计算逻辑是否与scope_enforcer的预期一致
2. data_protection的mask_structured()是否能正确处理嵌套字典
3. approval_gate的check()返回值是否与Agent执行流程兼容

---

## Phase 3：启动（1个Agent，依赖全部前置输出）

### Agent-24：__init__.py + M0侵入层代码

**系统提示词：**
```
你是PentestAgent M4模块的系统集成开发专家。编写__init__.py和M0侵入层代码。

【Part 1：__init__.py】

实现M4模块入口：
1. 开关控制：CPA_M4_AUDIT_GUARD环境变量（默认true）
2. 初始化函数init_m4()：创建AuditLogger、RoEEngine、ScopeEnforcer、ApprovalGate、DataProtector
3. 从环境变量加载配置（log_dir, roe_file, strict_mode等）
4. 如配置了roe_file则自动加载RoE
5. 公共API导出：get_audit_logger(), get_roe_engine(), get_scope_enforcer(), get_approval_gate(), get_data_protector()
6. is_m4_enabled() -> bool

导入：
from .audit_logger import AuditLogger
from .roe_engine import RoEEngine
from .scope_enforcer import ScopeEnforcer, ScopeBlockedException
from .approval_gate import ApprovalGate
from .data_protection import DataProtector

【Part 2：M0侵入层代码】

提供以下HOOK点（用 === CPA M4 HOOK BEGIN/END === 包裹）：

侵入点1：pentestagent/__main__.py — main()函数
```python
# === CPA M4 HOOK BEGIN ===
if os.getenv("CPA_M4_AUDIT_GUARD", "true").lower() == "true":
    try:
        from pentestagent.cpa_modules.m4_audit_guard import init_m4
        import asyncio
        asyncio.run(init_m4())
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"M4模块初始化失败: {e}")
# === CPA M4 HOOK END ===
```

侵入点2：pentestagent/tools/ — 工具执行前拦截
```python
# === CPA M4 HOOK BEGIN ===
# 在每个工具执行函数的最开头插入：
async def tool_execute_with_guard(tool_name, target, command, ...):
    from pentestagent.cpa_modules.m4_audit_guard import get_scope_enforcer, get_approval_gate, get_audit_logger
    
    se = get_scope_enforcer()
    ag = get_approval_gate()
    al = get_audit_logger()
    
    # 1. 范围校验
    result = await se.validate(action=tool_name, target=target, tool=tool_name, command=command)
    if result["blocked"]:
        al.log_command(command, target, result="blocked")
        raise ScopeBlockedException(target, result["reason"], tool_name)
    
    # 2. 危险确认
    approval = await ag.check(action=tool_name, target=target, tool=tool_name, command=command)
    if approval["requires_input"]:
        # TUI显示确认请求，等待用户输入
        # ...（具体TUI集成代码）
        pass
    
    # 3. 记录审计日志
    entry_id = al.log_tool(tool_name, {"command": command}, target, session_id=...)
    
    # 4. 执行原始工具
    return await original_tool_execute(...)
# === CPA M4 HOOK END ===
```

侵入点3：pentestagent/interface/commands.py — 命令注册
```python
# === CPA M4 HOOK BEGIN ===
if os.getenv("CPA_M4_AUDIT_GUARD", "true").lower() == "true":
    try:
        from pentestagent.cpa_modules.m4_audit_guard import (
            get_audit_logger, get_roe_engine, get_scope_enforcer, get_approval_gate
        )
        # 注册命令：
        # /audit              — 显示审计状态
        # /audit log          — 查看最近审计日志
        # /audit verify       — 验证日志完整性
        # /audit export       — 导出证据包
        # /audit roe          — 显示RoE配置
        # /audit stats        — 显示拦截统计
        # /audit pending      — 显示待确认操作
        # /audit approve <id> — 确认操作
        # /audit deny <id>    — 拒绝操作
    except Exception:
        pass
# === CPA M4 HOOK END ===
```

侵入点4：pentestagent/config/settings.py — Settings类
```python
# === CPA M4 HOOK BEGIN ===
cpa_m4_audit_guard: bool = field(default_factory=lambda: os.getenv("CPA_M4_AUDIT_GUARD", "true").lower() == "true")
cpa_m4_log_dir: str = field(default_factory=lambda: os.getenv("CPA_M4_LOG_DIR", "./logs/audit"))
cpa_m4_roe_file: str = field(default_factory=lambda: os.getenv("CPA_M4_ROE_FILE", ""))
cpa_m4_strict_mode: bool = field(default_factory=lambda: os.getenv("CPA_M4_STRICT_MODE", "false").lower() == "true")
# === CPA M4 HOOK END ===
```

输出：__init__.py完整代码 + 4个侵入点代码和位置说明。
```

**期望输出**：`__init__.py`（80-120行）+ 4个M0侵入点

---

## 最终集成清单

**Agent-24完成后，全部到齐。主控做最终集成审阅：**

1. **文件完整性**：5个文件（audit_logger.py, roe_engine.py, scope_enforcer.py, approval_gate.py, data_protection.py, __init__.py, 2个RoE模板）
2. **hash_chain验证**：audit_logger的不可篡改机制是否正确
3. **RoE解析**：通配符域名、CIDR、时间窗口的解析和匹配
4. **拦截链路**：tool_execute → scope_enforcer.validate → approval_gate.check → audit_logger.log，完整通路
5. **脱敏覆盖**：8类敏感信息的检测和脱敏是否正确
6. **M0侵入量**：4个HOOK点，预计<15行

**审阅通过后，M4模块开发完成。**
