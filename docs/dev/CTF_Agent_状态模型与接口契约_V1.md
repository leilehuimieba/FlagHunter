# CTF Agent 状态模型与接口契约 V1

---

## 1. 设计目标

本规范用于回答两个问题：

1. agent 现在“知道什么”？
2. 模块之间“如何对话”？

如果没有结构化状态与清晰契约，后续协作会迅速退化成：

- 靠 prompt 补
- 靠 notes 猜
- 靠日志拼
- 靠个人记忆维护流程

这在多人开发中不可接受。

---

## 2. 最小核心实体

后续实现必须围绕以下 4 个核心实体展开：

1. `CTFState`
2. `Hypothesis`
3. `Experiment`
4. `VerificationResult`

---

## 2.5 概念分层（Primitive / Strategy / Hypothesis）

为避免命名混乱，明确以下三层概念边界。**这是后续命名规则的强制基础**。

### Primitive（能力原语）

定义：agent 能直接执行的最小动作单元。

特征：
- 不可再分（不能由其他 primitive 组合而成）
- 与具体题目无关
- 有明确的输入输出 schema

示例：`send_http_request`、`execute_js_in_browser`、`extract_zip_archive`、`wait_for_callback`

实现位置：`CapabilityRegistry`

### Strategy（解题策略）

定义：将多个 primitive 按特定模式组合，实现某种利用路径。

特征：
- 由 primitive 组合而成
- 对应一类利用模式（不对应具体题目）
- 有明确的"前提"和"成功信号"

示例：`auth_form_sqli_strategy`、`backup_source_leak_strategy`、`xss_admin_bot_sid_strategy`

实现位置：`StrategyRegistry`

### Hypothesis（假设）

定义：agent 对"哪种策略最可能成功"的当前判断。

特征：
- 有 confidence
- 可被支持或反驳
- 触发对应 strategy 的执行

示例：`kind: "auth_form_sqli"`, `confidence: 0.7`

实现位置：`CTFState.hypotheses`

### 三者关系

```
Hypothesis（我相信这个有戏）
  └── 触发对应的 Strategy（怎么试）
        └── Strategy 调用一组 Primitives（具体动作）
              └── Primitive 执行（实际 HTTP / Browser / IO）
```

### 命名规则（强制）

| 层 | 命名约定 | 示例 |
|---|---|---|
| Primitive | `<动作>_<对象>` | `send_http_request`, `execute_js_in_browser` |
| Strategy | `<利用模式>_strategy` | `auth_form_sqli_strategy` |
| Hypothesis kind | `<利用模式>`（无后缀） | `auth_form_sqli` |

`Hypothesis.kind` 和对应 `Strategy` 名一一对应，去掉 `_strategy` 后缀即得 Hypothesis.kind。

---

## 2.6 Schema 版本管理

所有需要持久化的实体必须带版本号。

### 版本号字段

```python
class VersionedEntity:
    schema_version: str  # semver-like，例如 "1.0", "1.1", "2.0"

class CTFState(VersionedEntity):
    schema_version: str = "1.0"
    ...

class StrategyMemoryEntry(VersionedEntity):
    schema_version: str = "1.0"
    ...

class CapabilityRegistry(VersionedEntity):
    schema_version: str = "1.0"
    ...
```

### 版本号语义（semver-like）

| 变化类型 | 触发条件 | 兼容性 |
|---|---|---|
| **major**（1.x → 2.0） | 字段类型变更、字段删除、含义变更 | 不兼容，必须迁移 |
| **minor**（1.0 → 1.1） | 新增可选字段、新增枚举值 | 向后兼容 |
| **patch**（1.0.0 → 1.0.1） | 默认值调整、文档级修改 | 完全兼容 |

### 加载规则

```
读取持久化数据
  ├── schema_version 与当前完全匹配 → 直接加载
  ├── major 相同，minor/patch 不同 → 兼容加载，缺失字段填默认值
  ├── major 不同 → 查找 migrations[from_major][to_major] 函数
  │     ├── 找到 → 执行迁移函数后加载
  │     └── 未找到 → 拒绝加载，输出明确错误（让用户决定是否清空旧数据）
  └── 完全缺少 schema_version 字段 → 视为 "0.0"，按 0.x → 1.x 迁移
```

### 迁移函数位置

所有迁移函数放在 `pentestagent/agents/pa_agent/migrations/`：

```
migrations/
  ├── __init__.py             # 注册表 MIGRATIONS = {("CTFState", "1", "2"): fn}
  ├── ctf_state_v1_to_v2.py
  ├── strategy_memory_v1_to_v2.py
  └── capability_registry_v1_to_v2.py
```

迁移函数签名：

```python
def migrate(old_dict: dict) -> dict:
    """输入旧版本 dict，返回新版本 dict。
    
    必须是纯函数，不能有副作用。
    必须设置返回值的 schema_version 字段。
    """
```

### Schema 变更流程

凡是修改任何 VersionedEntity 的 schema：

1. **先**更新 `CTF_Agent_状态模型与接口契约_V1.md` 中的实体定义
2. 在文档中标注新的 `schema_version`
3. 如果是 major 变更：必须同时提供 migration 函数和单元测试
4. 在 `CHANGELOG_schema.md` 中追加一行记录

---

## 3. `CTFState` 规范

### 3.1 必备字段

建议最小字段集：

```python
CTFState:
  target: str
  goal: str
  detected_type: str | None
  observations: list[Observation]
  artifacts: list[Artifact]
  hypotheses: list[Hypothesis]
  experiments: list[Experiment]
  candidate_flags: list[FlagRecord]
  runtime_flags: list[FlagRecord]
  verified_flags: list[FlagRecord]
  rejected_flags: list[FlagRecord]
  capabilities: CapabilityRegistry          # 升级：从 CapabilitySnapshot 到 CapabilityRegistry
  no_progress_count: int
  last_progress_marker: str | None
  stop_reason: str | None
  stop_report: StopReport | None            # 停止时生成

  # 探索议程（见 §3.8）
  exploration_agenda: list[ExplorationItem]  # 已发现但尚未分析的端点/文件列表

  # 推理层字段（见 CTF_Agent_智能推理层规范_V1.md）
  interpretations: list[Interpretation]     # 观察→解释层
  pre_action_reasonings: list[PreActionReasoning]  # 行动前推理
  meta_reasonings: list[MetaReasoning]      # 挑战设计者视角分析
  retrospectives: list[Retrospective]       # 失败事后分析
  surprises: list[SurpriseEvent]            # 意外结果记录
  hypothesis_memory_adjustments: dict[str, float]  # 记忆层对假设分数的调整记录
```

### 3.2 规则

#### 规则 A：一个事实只能有一个主归属

例如：

- “发现 `/www.zip`” → `artifacts`
- “怀疑这是 PHP unserialize” → `hypotheses`
- “试过 payload X” → `experiments`
- “源码中看到 `Syc{...}`” → `candidate_flags`

不允许：

- 同时散落在 notes 文本、局部变量、prompt 片段里而无主归属

#### 规则 B：flag 必须分级

至少区分：

- `candidate`
- `runtime`
- `verified`
- `rejected`

#### 规则 C：观察与推断必须分离

允许：

- observation: “返回里有 `/www.zip`”
- hypothesis: “这题可能是 backup/source leak”

禁止：

- 把推断直接写成 observation

### 3.8 `ExplorationItem`（探索议程条目）

侦察阶段发现但尚未深入分析的端点或资源，必须进入 `exploration_agenda`，由 `RecoveryController` 在切换假设前优先消耗（见主干架构规范 §4）。

```python
@dataclass
class ExplorationItem:
    id: str                        # 唯一标识
    url_or_path: str               # 待访问的 URL、路径或资源标识
    discovery_source: str          # 发现来源（”response_body”, “hints_txt”,
                                   #   “link_href”, “recon_header”, ...）
    hint_strength: int             # 1=强线索（明确链接到 flag 路径）
                                   # 2=中等（可能相关）
                                   # 3=弱线索（仅顺手发现）
    explored: bool = False         # 是否已经分析过
    exploration_result: str | None = None   # 分析结果摘要（简短）
    added_at: float = 0.0          # 写入时间戳
```

**写入规则**：
- recon 阶段发现的每个子端点、文本文件（`/hints.txt`、`/welcome.txt`、`/flag.txt` 等）都必须写入
- URL 参数中发现的 `filename`/`filehash` 等结构化参数，以解析后的参数名为条目，`hint_strength=1`
- 重复 URL 不写入（以 `url_or_path` 去重）

**消耗规则**（由 RecoveryController 执行）：
- 在切换假设之前，必须先将 `hint_strength <= 2` 的未探索条目全部访问并记录结果
- 访问后将对应条目 `explored = True`，并将发现写入 `CTFState.observations`

---

## 4. `Hypothesis` 规范

### 4.1 最小字段

```python
Hypothesis:
  id: str
  kind: str
  description: str
  confidence: float
  status: Literal["active", "supported", "rejected", "exhausted"]
  supporting_observations: list[str]
  counter_evidence: list[str]
  next_experiments: list[str]
```

### 4.2 `kind` 命名规则

必须使用**原语级名字**：

- `auth_form_sqli`
- `backup_source_leak`
- `php_unserialize_magic_method`
- `xss_admin_bot_sid`

禁止：

- `buu_php_2019`
- `极客大挑战php`

---

## 5. `Experiment` 规范

### 5.1 最小字段

```python
Experiment:
  id: str
  hypothesis_id: str
  action_type: str
  inputs: dict
  expected_signal: str
  observed_signal: str | None
  progress_delta: Literal["none", "weak", "strong", "terminal"]
  status: Literal["planned", "running", "completed", "failed"]
```

### 5.2 规则

每个实验必须回答：

1. 为了验证哪个假设？
2. 期待看到什么？
3. 如果没看到，说明什么？
4. 如果成功，是否允许停止？

---

## 6. `VerificationResult` 规范

### 6.1 最小字段

```python
VerificationResult:
  decision: Literal["candidate", "runtime", "verified", "rejected", "insufficient"]
  flag: str | None
  evidence_source: str
  confidence: float
  rationale: str
  requires_followup: bool
```

### 6.2 验证规则

#### source-only flag

来源：

- zip
- 源码
- 注释
- 备份文件

默认输出：

- `decision = "candidate"`

除非额外满足运行时证据，否则不允许直接 stop。

#### runtime flag

来源：

- HTTP 响应
- 页面渲染
- 命令执行输出
- exploit 回显

默认输出：

- `decision = "runtime"`

#### rejected flag

来源：

- 平台提交错误反馈
- 用户显式 `/ctf wrong <flag>`

输出：

- `decision = "rejected"`

并将该 flag 加入 `CTFState.rejected_flags`

---

### 6.3 Verifier 判定算法（具体 how）

`VerificationResult.decision` 不是凭感觉打的，必须经过以下五条判定路径之一。**按顺序检查，先到先得**：

#### 路径 E：明确拒绝（最高优先级）

触发条件（任一）：
- flag 字符串已在 `CTFState.rejected_flags` 中
- 用户执行 `/ctf wrong <flag>`
- 平台提交端点返回"错误"

输出：`decision = "rejected"`

#### 路径 A：正则匹配 → 生成 candidate

触发条件：在任何文本中检测到符合已知 flag 格式的字符串。

默认 flag 格式（可配置）：
```python
FLAG_PATTERNS = [
    r"flag\{[^}]{4,128}\}",
    r"FLAG\{[^}]{4,128}\}",
    r"ctfshow\{[^}]+\}",
    r"SYC\{[^}]+\}",
    r"BUUCTF\{[^}]+\}",
    # 用户可通过 .env 的 CTF_FLAG_PATTERNS 追加
]
```

输出：`decision = "candidate"`，必填 `evidence_source`。

#### 路径 B：运行时回显 → 升级到 runtime

触发条件：candidate flag 的 `evidence_source` 属于以下来源之一：
- 目标服务的 HTTP 响应 body（非源码、非注释、非 README）
- 命令执行（RCE）的回显输出
- 浏览器渲染后的页面文本（非 `view-source:` 协议）
- CollectorServer 收到的回调内容

**反例**（不允许升级到 runtime）：
- 从 `.zip` 解压出的源码文件中找到的字符串
- HTML 注释 `<!-- flag{...} -->`
- robots.txt / README / LICENSE 中的字符串
- notes.json 中的字符串（即使是历史记录）

输出：`decision = "runtime"`

#### 路径 C：平台提交 → 升级到 verified

触发条件：目标支持 flag 提交端点（由 `CTFState.submit_endpoint` 指定）。

判定流程：
1. 调用 submit_endpoint，POST flag
2. 解析响应判定（按配置的成功/失败正则）
3. 平台返回"正确" → `decision = "verified"`
4. 平台返回"错误" → 进入路径 E（rejected）
5. 端点超时或异常 → 保持 runtime，不升级也不降级

#### 路径 D：用户确认 → 升级到 verified

触发条件：没有自动提交端点，但存在 runtime flag。

判定流程：
1. 通过 TUI 询问：`"检测到 runtime flag: <flag>，请确认是否正确？(yes/no/skip)"`
2. 用户 `yes` → `decision = "verified"`
3. 用户 `no` → 进入路径 E（rejected）
4. 用户 `skip` → 保持 runtime，进入 `requires_followup = True`

#### 判定顺序总图

```
新观察到的 flag 字符串
  ├── 在 rejected_flags 中？ → rejected（路径 E）
  ├── 符合 flag 正则？ → candidate（路径 A）
  │      ├── evidence_source 是运行时来源？ → 升级到 runtime（路径 B）
  │      │      ├── 有 submit_endpoint？ → 提交并按平台响应判定（路径 C）
  │      │      └── 无 submit_endpoint？ → 询问用户（路径 D）
  │      └── evidence_source 是源码/注释？ → 保持 candidate，requires_followup=True
  └── 不符合任何正则 → 不进入 Verifier
```

#### 重要约束

1. 同一 flag 字符串可能多次进入判定，**以最高层级为准**（rejected > verified > runtime > candidate）
2. `runtime` flag 默认**不允许直接 stop**，必须经过路径 C 或 D 升级为 verified
3. `candidate` 不允许直接成功，除非用户 `/ctf override <flag>` 强制升级
4. 升级路径必须是单调的：`candidate → runtime → verified`，不允许跳级
5. 任何 verified flag 都可以被后续路径 E 降级为 rejected（用户随时可以纠正）

---

## 7. 模块接口契约

---

### 7.1 `Coordinator -> HypothesisEngine`

输入：

- `CTFState`

输出：

- `list[Hypothesis]`
- 当前优先假设

要求：

- 不得修改 artifacts / flags
- 只负责假设生成与排序

---

### 7.2 `Coordinator -> StrategyRegistry`

输入：

- 当前优先假设
- `CTFState`

输出：

- `Experiment` 或实验计划

要求：

- 策略层不得直接宣布 verified flag

---

### 7.3 `Strategy -> Verifier`

输入：

- 原始响应
- 当前上下文
- 触发该响应的实验信息

输出：

- `VerificationResult`

要求：

- 不得只回传裸文本
- 必须说明 flag 来源

---

### 7.4 `Verifier -> RecoveryController`

触发条件：

- candidate flag
- rejected flag
- insufficient
- no-progress

输出：

- 恢复动作建议

---

## 8. notes 与状态的关系

`notes` 仍保留，但定位应调整为：

> **外部可观察证据与持久化记录层**

而不是：

> **系统唯一真实状态**

规则：

1. 结构化状态优先存在 `CTFState`
2. notes 用于：
   - 审计
   - 持久化证据
   - 跨会话提示
3. 不允许仅靠 notes 重建全部主循环语义

---

## 9. `HypothesisEngine` 实现约束

### 9.1 生成策略：规则优先，LLM 兜底

生成假设时必须遵守以下优先级：

1. **规则层（必须先跑）**  
   根据 `CTFState` 中的 `detected_type`、`artifacts`、`observations`、`web_subtype` 等字段，用确定性规则生成候选假设。  
   示例：`detected_type == "login_form"` → 自动生成 `auth_form_sqli` 假设

2. **结构感知映射（规则层的核心组成）**  
   以下页面结构特征必须触发对应假设生成，不得跳过：

   | 观测到的结构特征 | 必须生成的假设 kind | 初始 confidence |
   |---|---|---|
   | URL 含 `filename` + `filehash` 参数 | `hash_guarded_file_read`, `hash_reconstruction_attack` | 0.6 |
   | 响应头或错误页含 Tornado 框架特征 | `tornado_ssti`, `tornado_template_path_injection` | 0.55 |
   | 发现 `/hints.txt`、`/welcome.txt`、`/flag.txt` 等提示文件 | `hint_chain_followup` | 0.65 |
   | URL 参数含 `render`/`template`/`name` 且响应可见输出变化 | `ssti_via_render_parameter` | 0.6 |
   | `backup_clue == False` 且无任何 `.zip`/`.tar`/`.bak` 发现 | `backup_source_leak` **不生成**（或 confidence ≤ 0.2） | ≤ 0.2 |
   | 发现 `/file?filename=...` 或 `/download?name=...` 结构 | `path_traversal`, `file_read_endpoint` | 0.55 |
   | 检测到 server-sent set-cookie 含可解析结构 | `session_forgery`, `cookie_tampering` | 0.5 |

   **关键约束**：若 `backup_clue == False`（即所有 observations 中无 backup 相关 artifact），禁止将 `backup_source_leak` 排在假设列表首位，其 confidence 上限为 0.2。

3. **LLM 扩展（规则层结果不足时才触发）**  
   若规则层生成的候选假设 < 2 条，可调用 LLM 根据当前 state 补充新假设。  
   LLM 扩展结果必须满足 `Hypothesis` schema，`kind` 必须是原语级名字。

4. **禁止纯 LLM 自由生成**  
   不允许跳过规则层直接让 LLM 决定下一步做什么。

### 9.2 排序规则

假设列表按以下权重降序排列：

```
score = confidence * 0.6
      + (len(supporting_observations) / max(max_obs, 1)) * 0.3
      + novelty_bonus * 0.1
```

- `confidence`：当前可信度（0.0 ~ 1.0）
- `supporting_observations`：支持证据数量（归一化）
- `novelty_bonus`：若该假设从未被实验过，+0.1；否则 0

**观测下限约束（observation floor）**：

排序完成后，必须执行以下后处理：
```
obs_supported = [h for h in hypotheses if len(h.supporting_observations) > 0]
if obs_supported:
    floor_score = max(score(h) for h in obs_supported)
    for h in hypotheses:
        if len(h.supporting_observations) == 0 and score(h) > floor_score:
            # 无直接观测支撑的假设不得排在有观测支撑的假设前面
            h.rank_capped = True  # 标记但不修改 confidence，仅压低排名
```

效果：当前页面直接观察到的结构特征（如 `filename+filehash` 参数）所对应的假设，排名始终高于仅靠记忆 bonus 提升的假设。

### 9.3 反馈更新规则（回溯）

实验结束后，`HypothesisEngine` 必须根据 `Experiment.progress_delta` 更新对应假设：

| progress_delta | confidence 变化 | status 变化 |
|---|---|---|
| `terminal`（verified flag） | 置 1.0 | → `supported` |
| `strong`（runtime 明确进展） | +0.2（上限 1.0） | 保持 `active` |
| `weak`（candidate 或弱信号） | +0.05 | 保持 `active` |
| `none`（无新信息） | -0.15（下限 0.0） | 连续 3 次 `none` → `exhausted` |
| 手动 rejected | 置 0.0 | → `rejected` |

### 9.4 假设穷尽判定

当以下全部条件满足时，假设进入 `exhausted`：

1. `progress_delta == "none"` 连续出现 ≥ 3 次
2. 没有未尝试的 `next_experiments`
3. 当前 `confidence < 0.15`

### 9.5 记忆-观测冲突解决规则

HypothesisEngine 在接收 `StrategyMemory` 检索结果并准备施加 `memory_bonus` 之前，必须按顺序执行以下三步检查：

**步骤 1：直接矛盾检查（contradiction check）**

对每个将要被施加 `memory_bonus` 的假设 kind，检查当前 `CTFState` 是否存在直接矛盾信号：

| 假设 kind | 所需前提 | 矛盾信号示例 |
|---|---|---|
| `backup_source_leak` | 存在 backup/zip/tar 相关 artifact 或提示 | `backup_clue == False` 且 observations 无任何压缩包发现 |
| `auth_form_sqli` | 存在登录表单 | observations 无任何 form/input 发现 |
| `php_unserialize_magic_method` | PHP 相关特征 | tech_stack 不含 PHP |

→ **矛盾检查未通过**：该假设的 `memory_bonus` 清零（置 0.0），并在 `hypothesis_memory_adjustments` 里记录 `"contradiction_zeroed"` 原因。

**步骤 2：观测下限检查（observation floor check）**

```
max_obs_score = max(score(h) for h in hypotheses if len(h.supporting_observations) > 0)
# 如果存在有直接观测支撑的假设：
for h in memory_boosted_hypotheses:
    if len(h.supporting_observations) == 0:
        new_score = min(score(h) + memory_bonus, max_obs_score + 0.1)
        # 记忆提升后的分数不得超过最高观测支撑假设的分数 + 0.1
```

→ 记忆只能"从下面拉高"无观测支撑的假设，不能让它凌驾于有直接页面观测支撑的假设之上。

**步骤 3：累计上限检查（既有规则）**

`memory_bonus + memory_penalty` 累计不超过 ±0.25（此规则不变）。

---

### 9.6 探索议程先行规则

在 `RecoveryController` 触发"切换假设"之前，必须先检查 `CTFState.exploration_agenda`：

```
priority_1_2_unexplored = [
    item for item in state.exploration_agenda
    if item.hint_strength <= 2 and not item.explored
]

if priority_1_2_unexplored:
    # 不切换假设，先消耗探索议程
    next_action = ExploreAgendaAction(items=priority_1_2_unexplored)
else:
    # 探索议程已耗尽，才允许切换假设
    next_action = SwitchHypothesisAction(...)
```

**意义**：避免在没有充分挖掘当前页面线索（`/hints.txt`、`/welcome.txt`、`/file?filename=...` 等）的情况下就切换假设方向。探索议程是 HypothesisEngine 的"证据扩充前置"，而不是 recovery 的兜底。

---

## 10. 新增实体速查

本文档新增以下实体，详细 schema 见对应专项规范：

| 实体 | 定义位置 |
|---|---|
| `Interpretation` | `CTF_Agent_智能推理层规范_V1.md` §4 |
| `PreActionReasoning` | `CTF_Agent_智能推理层规范_V1.md` §3 |
| `MetaReasoning` | `CTF_Agent_智能推理层规范_V1.md` §5 |
| `Retrospective` | `CTF_Agent_智能推理层规范_V1.md` §6 |
| `StopReport` | `CTF_Agent_智能推理层规范_V1.md` §7 |
| `SurpriseEvent` | `CTF_Agent_智能推理层规范_V1.md` §3.4 |
| `CapabilityPrimitive` / `CapabilityRegistry` | `CTF_Agent_能力层与记忆模型_V1.md` §2 |
| `ChallengeFingerprint` / `StrategyMemoryEntry` | `CTF_Agent_能力层与记忆模型_V1.md` §3 |

---

## 11. 契约变更规则

凡是改动以下任一内容，都必须先更新本文档：

- 新增状态字段
- 更改 flag 分级规则
- 更改假设命名
- 更改实验结果分级
- 更改模块所有权
- 更改 HypothesisEngine 排序权重或反馈规则
- 更改推理层任意实体的 schema
- 更改 CapabilityRegistry 的探测规则

