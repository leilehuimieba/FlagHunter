# CTF Agent 能力层与记忆模型 V1

> **本文档上游**：`CTF_Agent_智能推理层规范_V1.md`（Retrospective 的 learned_rule 写入此处）  
> **本文档下游**：`CTF_Agent_完整测试用例集_V1.md`（C/M 系列用例）  
> **实现约束**：`CTF_Agent_实现约束与协作规范_V1.md`  
> **状态字段扩展**：`CTF_Agent_状态模型与接口契约_V1.md`（CapabilitySnapshot 更新、StrategyMemory 新增）

---

## 1. 为什么需要能力层与记忆模型

当前系统有两个盲点：

**盲点 A：工具能力建模太粗糙**

当前 `CapabilitySnapshot` 本质是布尔值：有工具 / 没有工具。

现实是：`没有 sqlmap` ≠ `无法做 SQL 注入`。很多能力有多种实现路径，只是质量和代价不同。当前架构把"工具缺失"和"能力缺失"混为一谈，导致不必要的 `missing_tool` 停止。

**盲点 B：每道题都从零开始**

当前 `CTFState` 是题目级状态，每道题重置。但人类解题者有经验积累——做过 10 道 SQLi 题之后，遇到类似特征的题目会自然优先考虑 SQLi。

当前系统没有这个机制。每道题的 HypothesisEngine 都从零开始排序，不使用历史信息。

---

## 2. 组件 A：可组合能力原语模型

### 2.1 核心思想

将工具能力分解为"**原语**"（我能做什么）和"**实现**"（用什么工具做）两层。

```
原语（Primitive）：send_authenticated_http_request
实现方式 1：requests_with_session         代价=1, 质量=high
实现方式 2：playwright_browser            代价=3, 质量=high
实现方式 3：curl_subprocess               代价=2, 质量=medium
```

### 2.2 数据结构

```python
@dataclass
class CapabilityImplementation:
    method: str             # "sqlmap", "manual_payload", "requests", "playwright", ...
    cost: int               # 1=轻量, 3=中等, 5=重型工具
    quality: Literal["high", "medium", "low"]
    available: bool         # 当前是否可用
    requires_install: bool  # 不可用时，是否可以安装
    install_command: str | None  # 安装命令（如 "pip install sqlmap"）
    last_checked: float     # 上次探测可用性的时间戳

@dataclass
class CapabilityPrimitive:
    name: str               # "sql_injection_test", "xss_payload_delivery", ...
    description: str
    implementations: list[CapabilityImplementation]  # 按 cost 升序排列

    def best_available(self) -> CapabilityImplementation | None:
        """返回当前可用且代价最低的实现"""
        available = [i for i in self.implementations if i.available]
        return min(available, key=lambda x: x.cost) if available else None

    def can_degrade(self) -> bool:
        """是否有至少一种可用实现"""
        return self.best_available() is not None

@dataclass
class CapabilityRegistry:
    primitives: dict[str, CapabilityPrimitive]  # key = primitive name
    last_full_check: float
```

### 2.3 标准原语清单（初版）

| 原语名 | 描述 | 高质量实现 | 降质实现 |
|---|---|---|---|
| `http_request_basic` | 基础 HTTP 请求 | `requests` | `curl_subprocess` |
| `http_request_browser` | 带 JS 渲染的请求 | `playwright` | `selenium`（如有） |
| `sql_injection_test` | SQL 注入探测 | `sqlmap` | `manual_payload_via_requests` |
| `source_download` | 下载/解压源码包 | `requests+zipfile` | `curl+unzip` |
| `js_execution_in_context` | 在目标 origin 内执行 JS | `playwright_evaluate` | 无降质 |
| `callback_listener` | 监听外部回调 | `CollectorServer` | 无降质 |
| `php_deserialization_test` | PHP 反序列化 payload 投放 | `manual_payload` | 无降质 |
| `directory_enumeration` | 目录扫描 | `ffuf` / `gobuster` | `manual_wordlist_requests` |

### 2.4 降质路由规则

当 `CapabilityPrimitive.best_available()` 返回非高质量实现时，必须：

1. 在 `PreActionReasoning.action_rationale` 里注明"使用降质实现 X，预期质量 medium"
2. 在 `Experiment.inputs` 里记录降质方式
3. 如果降质实现返回结果不确定性高，`progress_delta` 不能直接设为 `strong`

### 2.5 能力探测时机

| 时机 | 探测范围 |
|---|---|
| 题目开始前 | 全量探测所有 primitives |
| `missing_tool` 恢复流程中 | 只探测相关 primitive |
| 安装完成后 | 重新探测被安装的 primitive |
| 每隔 300 秒（题目进行中） | 增量探测（只检查 `available=False` 的实现） |

### 2.6 与 RecoveryController 的接口（判定树）

请求某个 primitive 时，**严格按以下判定树执行**，不允许跳步：

```
请求 primitive X
├── X.best_available() 返回非 None
│   └── 直接使用该实现
│       ├── 是高质量实现 → 正常执行
│       └── 是降质实现（quality=medium/low）
│             ├── 记录 implementation 名 + quality 到 Experiment.inputs
│             ├── 若 quality == "low"：Experiment.progress_delta 不允许设为 "strong"
│             └── 在 PreActionReasoning.action_rationale 注明降质
│
└── X.best_available() 返回 None（所有实现都不可用）
    ├── 存在 requires_install == True 的实现
    │   └── 进入工具安装流程（见 实现约束 §3.5 七步流程）
    │       ├── 安装成功 → 重新探测，回到判定树起点
    │       └── 安装失败 → primitive 永久标记不可用，降权依赖它的假设
    └── 不存在 requires_install == True 的实现
        └── primitive 永久标记不可用
            ├── 依赖该 primitive 的假设全部 reject
            └── 若是唯一假设链路 → StopReport.reason = "capability_ceiling"
```

**关键规则（与实现约束 §3.5 联动）**：

1. **降质路由优先于安装流程**：只要 `best_available()` 非 None，绝不询问用户是否安装
2. **只有"完全无可用实现 + 存在可安装实现"时才触发用户确认**
3. **安装失败不连环触发**：同一 primitive 在同一题目中安装失败一次后，本题不再重试该工具的安装

---

## 3. 组件 B：跨题策略记忆（Strategy Memory）

### 3.1 核心思想

完成一道题（无论成功还是失败）后，将题目的关键特征和解题路径记录下来。下次遇到特征相似的题目时，HypothesisEngine 可以检索这些记录，给"历史有效"的假设额外加权。

### 3.2 Challenge Fingerprint（题目指纹）

```python
@dataclass
class ChallengeFingerprint:
    # 技术栈特征
    tech_stack: list[str]           # ["php", "nginx", "mysql", "tornado", ...]
    auth_mechanism: str | None      # "form_login", "jwt", "session_cookie", ...
    detected_type: str | None       # ctf_planner 粗粒度判型结果

    # 细粒度 Web 子类型标签（可多选）
    web_subtype: list[str]          # 见下方标准值表；HypothesisEngine 用此字段做结构感知假设生成
    # 标准 web_subtype 值（非穷举，可扩展）：
    # "file_parameter"            - URL 含 filename/path/file 等文件路径参数
    # "signed_download"           - URL 含 hash/sign/token 与文件名绑定（需同时提供两个参数）
    # "hash_guarded_file_read"    - 文件访问需正确哈希值（如 MD5(server_secret+filename)）
    # "python_tornado_web"        - 检测到 Tornado 框架特征（报错页样式、X-Tornado-* header）
    # "hint_chain"                - 页面含显式提示文件链（/hints.txt /welcome.txt /flag.txt）
    # "ssti"                      - Server-Side Template Injection 参数特征（响应含模板输出痕迹）
    # "lfi"                       - URL 含 include/path 参数，可能有本地文件包含
    # "render_parameter"          - URL/POST 参数含 render/template/name 等模板关键词
    # "admin_panel"               - 检测到后台登录面板 (/admin /manage /dashboard)
    # "upload_endpoint"           - 检测到文件上传端点
    # "api_endpoint"              - 有 /api 路由，可能 REST API 漏洞
    # "backup_clue"               - 首页或 robots.txt 有 /www.zip /backup /源码包 等提示

    # 页面特征（保留原有布尔型快速检索用）
    has_login_form: bool
    has_file_upload: bool
    has_admin_panel: bool
    has_source_hint: bool           # 首页有 /www.zip 等压缩包提示（对应 web_subtype "backup_clue"）
    response_error_types: list[str] # 观察到的错误类型

    # 挑战元数据
    platform: str | None            # "buuoj", "ctfshow", "local", ...
    difficulty_estimate: str | None  # "easy", "medium", "hard"

    # 向量化用于检索
    embedding: list[float] | None   # 由 sentence-transformer 生成
```

**`web_subtype` 填充规则**：

- recon 阶段结束时，必须根据观测结果填充（不能留空列表，除非真的无结构特征）
- `HypothesisEngine` 必须将 `web_subtype` 中的每一项映射到对应假设（见状态模型 §9.1 结构感知映射表）
- `backup_clue` 标签对应 `has_source_hint = True`；若 `has_source_hint = False`，`web_subtype` 不得含 `"backup_clue"`
- `web_subtype` 内容也存入 `StrategyMemoryEntry.fingerprint`，用于相似题检索

### 3.3 Strategy Memory Entry

```python
@dataclass  
class StrategyMemoryEntry(VersionedEntity):
    schema_version: str = "1.0"
    id: str
    fingerprint: ChallengeFingerprint
    
    # 解题路径记录
    winning_hypothesis_kinds: list[str]   # 成功的假设原语序列（按顺序）
    winning_primitive_sequence: list[str] # 实际执行的原语序列
    avg_turns_to_flag: int                # 平均几轮拿到 flag
    
    # 失败路径记录（防止重蹈覆辙）
    failed_hypothesis_kinds: list[str]    # 试过但失败的假设原语
    red_herrings_encountered: list[str]   # 遇到的迷惑项描述
    
    # 从 Retrospective 提炼的规则
    learned_rules: list[str]              # 可泛化的字符串规则
    
    # 元数据
    challenge_url: str | None
    solved: bool
    created_at: float
    metadata: "StrategyMemoryEntryMetadata"  # 见 §3.7.1
```

### 3.4 检索接口

```python
class StrategyMemoryStore:
    def query(
        self,
        current_fingerprint: ChallengeFingerprint,
        top_k: int = 3
    ) -> list[tuple[StrategyMemoryEntry, float]]:
        """
        返回与当前题目指纹最相似的历史记录，以及相似度分数。
        相似度计算：
          - embedding cosine similarity（权重 0.6）
          - tech_stack overlap（权重 0.2）
          - detected_type exact match（权重 0.2）
        """

    def save(self, entry: StrategyMemoryEntry) -> None:
        """题目结束时调用，写入持久化存储"""
```

### 3.5 持久化

- 存储路径：`loot/strategy_memory.json`（与 `notes.json` 同目录）
- 格式：JSON Lines，每行一个 `StrategyMemoryEntry`
- Embedding 存储：`loot/strategy_memory.faiss`（FAISS 索引）
- 触发时机：每道题结束时（`StopReport` 生成后）自动调用 `StrategyMemoryStore.save()`

### 3.6 HypothesisEngine 集成

在生成假设时，HypothesisEngine 调用 `StrategyMemoryStore.query()`：

```
1. 如果 similarity_score > 0.75 的历史记录存在：
   - 将历史记录里的 winning_hypothesis_kinds 加入候选假设（初始 confidence 来自规则层）
   - 将历史记录里的 failed_hypothesis_kinds 对应假设施加 -0.10 的 memory_penalty

   ★ 施加 memory_bonus 之前，必须先执行三步检查（见下）

2. 将历史记录里的 learned_rules 传入 AdversarialLens prompt

3. 历史记录里的 red_herrings_encountered 加入 MetaReasoning 的提示上下文
```

#### 3.6.1 memory_bonus 三步前置检查

**必须按序执行，任何一步触发则立即处置，不等待后续步骤**：

**步骤 1 — 直接矛盾检查（contradiction check）**

对每个将要被施加 `memory_bonus` 的假设 kind，检查当前 `CTFState` 是否包含直接矛盾信号：

| 假设 kind | 所需前提 | 矛盾信号 → 处置 |
|---|---|---|
| `backup_source_leak` | `has_source_hint == True` 或 `"backup_clue" in web_subtype` | 矛盾 → `memory_bonus = 0`，记录原因 `"contradiction_zeroed"` |
| `auth_form_sqli` | `has_login_form == True` | 矛盾 → `memory_bonus = 0` |
| `php_unserialize_magic_method` | `"php" in tech_stack` | 矛盾 → `memory_bonus = 0` |
| `tornado_ssti` | `"python_tornado_web" in web_subtype` 或 tech_stack 含 tornado | 矛盾 → `memory_bonus = 0` |

步骤 1 中被清零的调整，记入 `hypothesis_memory_adjustments[kind] = 0.0` 并注明原因。

**步骤 2 — 观测下限检查（observation floor check）**

```python
obs_supported = [h for h in hypotheses if len(h.supporting_observations) > 0]
if obs_supported:
    floor_score = max(score(h) for h in obs_supported)
    for h in memory_boosted_candidates:
        if len(h.supporting_observations) == 0:
            # 记忆提升后不得超过最高观测分 + 0.1
            bonus_cap = max(0.0, (floor_score + 0.1) - h.confidence)
            memory_bonus_for_h = min(+0.15, bonus_cap)
```

**步骤 3 — 累计上限检查（既有规则）**

`memory_bonus + memory_penalty` 合计不超过 ±0.25。

---

**核心约束总结**：记忆信号是"弱引导"，不是"覆盖"。当前页面直接观测到的结构特征（`web_subtype`、`supporting_observations`）对假设排序的影响权重，始终高于历史记忆的提升效果。

### 3.7 写保护、衰减与冲突解决

跨题记忆是双刃剑。一条错误的 learned_rule 可能污染未来所有题目。必须有保护机制。

#### 3.7.1 metadata 扩展

每个 `StrategyMemoryEntry` 必须带 metadata：

```python
@dataclass
class StrategyMemoryEntryMetadata:
    source_retrospective_id: str | None    # 来源 Retrospective
    applied_count: int                      # 被检索使用的次数
    successful_applications: int            # 应用后该题目成功的次数
    failed_applications: int                # 应用后该题目失败的次数
    success_correlation: float              # successful / (successful + failed)
    manual_status: Literal["active", "muted", "deprecated"]
    confidence_decay_factor: float          # 时间衰减系数，初始 1.0
    created_at: float
    last_used_at: float
    last_promoted_at: float | None          # 上次被验证有效的时间
```

#### 3.7.2 写入门槛

只有满足**全部**以下条件的 Retrospective 才能写入 StrategyMemory：

1. `Retrospective.learned_rule != None`
2. `learned_rule` 通过原语级校验（不含题目名、平台名、具体 URL、IP）
3. Retrospective 涉及至少 3 个 Experiment（防止偶然结论）
4. `winning_hypothesis_kinds` 只能包含状态为 `supported` 的假设
5. 题目本身必须是 `solved == True` 才能写 winning_kinds（失败题只写 failed_kinds 和 red_herrings）

不满足上述条件的 Retrospective 仍留在 `CTFState.retrospectives`，但不晋升为跨题记忆。

#### 3.7.3 衰减规则

**时间衰减**（每次加载时自动计算）：
- 每过 30 天，`confidence_decay_factor *= 0.9`
- 当 `confidence_decay_factor < 0.3` 时，自动标记为 `deprecated`
- `deprecated` 的 entry 不参与检索，但保留供审计

**行为衰减**（每次被应用后更新）：
- `applied_count >= 5` 且 `success_correlation < 0.2` → 自动 `muted`
- `applied_count >= 10` 且 `success_correlation < 0.4` → 输出审计提示（不自动 mute，需人工决定）
- 应用成功一次 → `last_promoted_at` 更新为当前时间，`confidence_decay_factor` 恢复至 1.0

#### 3.7.4 冲突解决

检索时若返回两条相互矛盾的 entry（例如一条建议 SQLi 优先，另一条建议先看 source leak）：

判定顺序：
1. `manual_status == "active"` 优先于 `muted`/`deprecated`
2. `confidence_decay_factor` 高者优先
3. `last_promoted_at` 近者优先
4. **冲突双方权重相加 ≤ 检索权重上限的 0.6**（防止冲突双方过度影响）

#### 3.7.5 手动管理接口

通过 TUI 命令 `/ctf memory <action>` 提供：

| 命令 | 功能 |
|---|---|
| `/ctf memory list` | 列出所有 entry，按 `applied_count` 排序 |
| `/ctf memory show <id>` | 显示某 entry 的完整内容（含 metadata） |
| `/ctf memory mute <id>` | 标记为 muted（不参与检索） |
| `/ctf memory activate <id>` | 重新激活 muted entry |
| `/ctf memory delete <id>` | 彻底删除（需二次确认） |
| `/ctf memory audit` | 列出 `success_correlation < 0.3` 的 entry |
| `/ctf memory export <path>` | 导出全部记忆到 JSON |
| `/ctf memory clear` | 清空所有记忆（需二次确认） |

#### 3.7.6 回滚机制

如果发现某条 entry 导致连续失败：
1. agent 在 Failure Postmortem 中检测到"本次失败的根因来自某条 memory_bonus"
2. 自动将该 entry 的 `failed_applications` +1
3. 触发 §3.7.3 的行为衰减检查
4. 在 StopReport.user_next_steps 中提示用户"是否要 mute 这条记忆？"

### 3.8 Embedding 生成

使用项目已有的 `sentence-transformers` 基础设施：

```python
from pentestagent.knowledge.indexer import embed_text

def fingerprint_to_embedding(fp: ChallengeFingerprint) -> list[float]:
    text = f"{fp.detected_type} {' '.join(fp.tech_stack)} {fp.auth_mechanism}"
    if fp.has_login_form: text += " login_form"
    if fp.has_file_upload: text += " file_upload"
    if fp.has_admin_panel: text += " admin_panel"
    return embed_text(text)
```

---

## 4. 组件间数据流

```
题目开始
  -> CapabilityRegistry.full_check()
  -> ChallengeFingerprint 构建（from 初始 recon）
  -> StrategyMemoryStore.query(fingerprint)
  -> HypothesisEngine（注入 memory_bonus/penalty + learned_rules）

题目进行中
  -> RecoveryController 查询 CapabilityRegistry（降质路由）
  -> Retrospective.learned_rule → 暂存（不立即写 StrategyMemory）

题目结束
  -> StopReport 生成
  -> StrategyMemoryEntry 构建（汇总 winning_path、failures、learned_rules）
  -> StrategyMemoryStore.save()
  -> FAISS index 更新
```

---

## 5. 实现约束

1. `CapabilityRegistry` 必须在题目开始前完成初始化，不允许在实验执行中途才发现工具不可用
2. `StrategyMemory` 的检索和写入必须是异步的，不允许阻塞主循环超过 2 秒
3. 如果 `loot/strategy_memory.faiss` 不存在，系统必须能正常运行（降级为无记忆模式）
4. `learned_rules` 的内容必须经过原语级校验，包含题目名的规则不允许写入
5. `memory_bonus/penalty` 的应用结果必须记录在 `CTFState.hypothesis_memory_adjustments` 里，可被审计
6. CapabilityImplementation 的探测超时不超过 5 秒/实现，总探测不超过 30 秒

---

## 6. 开发顺序

1. **CapabilityRegistry + 降质路由**（先实现，RecoveryController 依赖它）
2. **ChallengeFingerprint 构建**（从 recon 结果自动提取）
3. **StrategyMemoryStore 基础**（保存和检索，不含 embedding）
4. **Embedding 集成**（接入现有 FAISS 基础设施）
5. **HypothesisEngine 集成**（memory_bonus/penalty 注入）

---

## 7. 验收标准

1. 当 sqlmap 不可用时，agent 自动降质到 `manual_payload_via_requests`，不进入 `missing_tool` 恢复流
2. 题目结束后，`loot/strategy_memory.json` 有新增记录
3. 连续跑两道特征相似的题目，第二道题的 HypothesisEngine 初始排序受第一道题结果影响
4. `CapabilityRegistry.full_check()` 在 30 秒内完成
5. `StrategyMemoryStore.query()` 在 2 秒内完成
6. 无 FAISS 索引时系统正常启动，仅输出"无记忆模式"警告

---

**下一步文档**：`CTF_Agent_完整测试用例集_V1.md`（所有组件的具体测试场景）
