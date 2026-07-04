# FlagHunter Claim / VerificationRecord Schema Design v0.1

- 日期：2026-07-02
- 状态：Draft / 作为 `P1 统一 Claim / VerificationRecord` 的首版施工图
- 所属路线：[FlagHunter_CTF_Solver_Implementation_Roadmap_v0.1_2026-07-02.md](./FlagHunter_CTF_Solver_Implementation_Roadmap_v0.1_2026-07-02.md)
- 对照规格：[FlagHunter_CTF_Solver_Spec_v0.1_2026-07-02.md](./FlagHunter_CTF_Solver_Spec_v0.1_2026-07-02.md)
- 差距分析：[FlagHunter_CTF_Solver_Gap_Report_v0.1_2026-07-02.md](./FlagHunter_CTF_Solver_Gap_Report_v0.1_2026-07-02.md)
- 适用范围：FlagHunter 当前 CTF 单体主线、verifier、blackboard、trace、checkpoint，以及后续 crew 共用事实协议

---

## 0. 本文定位

本文不是愿景文，不是 gap report，也不是泛化 schema 草图。

本文要解决的是：

> 在当前 FlagHunter 代码现实下，如何定义一套足够硬、可迁移、可追责的 `Claim / VerificationRecord` 方案，让后续 `P1` 改造可以直接开工。

所谓“足够硬”，至少意味着：

- 字段语义不能含糊
- 状态迁移不能靠口头约定
- 写权限边界要能落到代码
- 必须能兼容当前 `candidate/runtime/verified/rejected` 结构
- 必须能对接 trace、checkpoint、blackboard、crew

---

## 1. 现状问题

当前代码中，“事实”被拆散在多套结构里：

- `observations`
- `artifacts`
- `hypotheses`
- `candidate_flags`
- `runtime_flags`
- `verified_flags`
- `rejected_flags`

其中只有 flag 近似拥有验证分级，而普通事实仍主要停留在 observation / note / model_fact 层。

代码现实表现为：

- [ctf_state.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/ctf_state.py:156) 中 `CTFState` 把 flags 单独维护为 4 个桶
- [verifier.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/verifier.py:81) 中 `CTFVerifier` 主要只验证 flag
- [blackboard_adapter.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/blackboard_adapter.py:138) 中 `record_fact()` 仍只是把模型结论写成 `model_fact` observation
- [session_ledger.py](/D:/webstudy/FlagHunter/flaghunter/harness/session_ledger.py:10) 已经有 append-only trace substrate，但当前事实对象本身还不统一

这会带来 5 个直接问题：

1. 普通事实和 flag 事实不是同一种对象，无法统一消费。
2. `verified` 只在 flag 上近似成立，无法推广到“凭据有效”“利用成功”“接口存在”等关键结论。
3. 无法表达事实依赖关系，导致污染传播和回退只能半结构化处理。
4. 无法统一把事实绑定到 trace 和 resume。
5. crew 未来即使并行，也缺乏共享事实纪律。

---

## 2. 设计目标

### 2.1 主目标

把所有“会被下游消费的结论”统一表示为 `Claim`，并把所有“对 Claim 的裁决记录”统一表示为 `VerificationRecord`。

### 2.2 次目标

- 兼容当前 flag 验证强项，不推倒重来
- 允许新旧结构双写过渡
- 让 blackboard / trace / checkpoint / crew 都围绕同一个事实协议工作

### 2.3 非目标

本设计稿当前不要求：

- 一次性统一 `Observation / Artifact / Hypothesis` 的全部生命周期
- 先设计完整的 `SolveNode`
- 先改 UI / MCP / Web 展示层
- 先把 strategy memory 变成统一知识库

---

## 3. 设计原则

### 3.1 Claim 是“可消费结论原子”

不是所有日志都要变成 Claim。只有满足下面任一条件的信息，才应该落 Claim：

- 会被后续决策引用
- 会影响 stop / switch / verify
- 会成为下游依赖链的一环
- 需要在 resume 后继续保留语义

### 3.2 VerificationRecord 是“裁决记录”，不是事实本身

Claim 负责表达“系统当前持有的一个结论”。

VerificationRecord 负责表达：

- 谁验证了
- 用什么方法验证
- 结果是什么
- 证据在哪里
- 这次验证是否足以升级状态

### 3.3 verified 只能由验证层授予

无论是单体 solver 还是 crew worker，都可以产出候选 Claim，但都不能直接写 `verified`。

### 3.4 retracted 不删除，只回退

事实一旦被推翻，不物理删除，而是进入 `retracted`，以保留完整的历史与污染链。

### 3.5 先收敛少数高价值 ClaimKind

首阶段不追求“万物皆 claim”。先收敛最影响解题正确性的那几类。

---

## 4. Canonical Schema

### 4.1 Claim

```yaml
Claim:
  id: string
  run_id: string
  node_id: string?
  parent_claim_ids: [string]
  superseded_by: string?
  content: string
  normalized_content: string
  kind: ClaimKind
  level: ClaimLevel
  status: ClaimStatus
  producer_type: ProducerType
  producer_id: string
  source_channel: SourceChannel
  primary_trace_id: string
  evidence_trace_ids: [string]
  artifact_refs: [string]
  verification_record_ids: [string]
  confidence: float
  confidence_reason: string
  replayable: bool
  tainted_by: [string]
  tags: [string]
  metadata: object
  created_at: timestamp
  updated_at: timestamp
  retracted_at: timestamp?
```

### 4.2 VerificationRecord

```yaml
VerificationRecord:
  id: string
  run_id: string
  claim_id: string
  verifier_type: VerifierType
  verifier_id: string
  method: VerificationMethod
  decision: VerificationDecision
  passed: bool
  sufficient_for_upgrade: bool
  trace_id: string
  evidence_trace_ids: [string]
  artifact_refs: [string]
  rationale: string
  evidence_summary: string
  confidence_delta: float
  replayable: bool
  submitted_value: string?
  platform_receipt: object?
  metadata: object
  created_at: timestamp
```

---

## 5. 枚举定义

### 5.1 ClaimKind

P1 推荐先支持下面 8 类：

| Kind | 含义 | 当前代码映射 |
|---|---|---|
| `flag_found` | 找到 flag 值或候选 flag | 现有 `FlagRecord` |
| `endpoint_exists` | 某路径 / 接口 / 页面存在 | 现有 observation / tool result |
| `credential_valid` | 某凭据可用 | 现有 notes / browser login / runtime signal |
| `exploit_succeeded` | 某利用链达成关键效果 | 现有 experiment / runtime result |
| `file_disclosed` | 某源码包 / 文件可读可下 | 现有 artifact / observation |
| `parameter_controllable` | 某参数可控或进入敏感 sink | 现有 hypothesis + observation |
| `sink_reachable` | 某 sink 或 gadget 链路可达 | 现有 reverse / web 证据 |
| `platform_feedback` | 平台接受 / 拒绝 / 重复提交反馈 | 现有 submit metadata |

说明：

- `platform_feedback` 本身通常是辅助 claim，用于支撑 `flag_found` 的最终升级。
- 后续可以扩展 `service_reachable`、`vuln_confirmed` 等，但 P1 不要求一次加全。

### 5.2 ClaimLevel

```text
assumption -> conjecture -> verified
                 |
                 -> retracted
```

定义：

- `assumption`
  - 历史经验、规则推测、弱信号推断
  - 默认不应直接触发高风险终止
- `conjecture`
  - 有局部证据支持的候选结论
  - 可以驱动下一步验证动作
- `verified`
  - 已被验证层确认，可作为强依赖输入
- `retracted`
  - 曾经存在过，但现在被明确推翻或被新 Claim 取代

说明：

- `candidate/runtime/rejected` 不是未来的顶层事实等级，而是迁移期概念。
- `runtime` 未来应作为 `VerificationRecord.method + metadata.runtime_strength` 表达，而不是 ClaimLevel 本身。

### 5.3 ClaimStatus

定义：

- `active`
  - 当前有效，可被消费
- `superseded`
  - 被更好的同类 claim 取代，但不一定错误
- `retracted`
  - 被推翻，禁止继续作为依赖使用
- `archived`
  - 仅用于历史存档，当前运行态不再消费

建议关系：

- `level=retracted` 时，`status` 必须也是 `retracted`
- `status=superseded` 时，`level` 不一定是 `retracted`

### 5.4 VerificationMethod

P1 推荐：

- `runtime_http`
- `runtime_command`
- `runtime_browser`
- `deterministic_parser`
- `cross_check`
- `platform_submit`
- `local_challenge_auto_verify`
- `operator_confirm`
- `prior_submit_lookup`

### 5.5 VerificationDecision

- `insufficient`
- `candidate`
- `runtime_supported`
- `verified`
- `rejected`
- `duplicate`

说明：

- `decision` 反映这次验证动作本身的裁决。
- Claim 的最终 `level` 由 Claim 当前累计状态决定，不完全等于某一次 decision。

### 5.6 ProducerType / VerifierType / SourceChannel

推荐值：

- `ProducerType`
  - `solver`
  - `orchestrator`
  - `tool_adapter`
  - `verifier`
  - `memory_projection`
- `VerifierType`
  - `ctf_verifier`
  - `platform_submitter`
  - `local_checker`
  - `operator`
- `SourceChannel`
  - `model_output`
  - `tool_stdout`
  - `browser_dom`
  - `http_response`
  - `artifact_parse`
  - `memory_hit`
  - `platform_receipt`

---

## 6. 字段语义硬约束

### 6.1 Claim 必填约束

- `id` 必须全局唯一，至少在一个 `run_id` 内唯一
- `kind` 不能为空
- `level` 不能为空
- `status` 不能为空
- `producer_type` / `producer_id` 必须可追溯
- `primary_trace_id` 不能为空
- `created_at` / `updated_at` 必须存在

### 6.2 VerificationRecord 必填约束

- `claim_id` 必须指向已存在 Claim
- `method` 不能为空
- `decision` 不能为空
- `trace_id` 不能为空
- `verifier_type` / `verifier_id` 必须存在

### 6.3 verified 升级约束

Claim 只有在同时满足下面条件时才能成为 `verified`：

1. 至少存在 1 条 `passed=true` 的 VerificationRecord
2. 至少存在 1 条 `sufficient_for_upgrade=true` 的 VerificationRecord
3. 升级动作由 verifier 路径执行

### 6.4 retracted 约束

Claim 进入 `retracted` 时必须：

1. 写入 `retracted_at`
2. 写入导致其失效的原因到 `metadata`
3. 触发依赖污染检查
4. 写 trace

### 6.5 superseded 约束

Claim 被新 Claim 取代但并非“错误”时：

- 旧 Claim 可变为 `status=superseded`
- `superseded_by` 指向新 Claim
- 不要求旧 Claim 进入 `retracted`

---

## 7. 状态机

### 7.1 ClaimLevel 状态迁移

```text
assumption -> conjecture -> verified
assumption -> retracted
conjecture -> retracted
verified   -> retracted
verified   -> superseded (status)
conjecture -> superseded (status)
```

禁止迁移：

- `assumption -> verified` 直接跳升，除非走 verifier 且有强验证记录
- `retracted -> conjecture`
- `retracted -> verified`

说明：

- 如果一个被推翻的事实要重新成立，应新建一个新 Claim，而不是把旧 Claim 改回去。

### 7.2 VerificationDecision 对 ClaimLevel 的推荐影响

| Decision | 默认影响 |
|---|---|
| `insufficient` | 不升级，只补记录 |
| `candidate` | 若 Claim 不存在则建 `conjecture`；已存在则补验证记录 |
| `runtime_supported` | 维持 `conjecture`，但提高 confidence，并标记高价值待验证 |
| `verified` | 可升级 Claim 为 `verified` |
| `rejected` | 可把 Claim 置为 `retracted` 或创建反向 claim |
| `duplicate` | 不新建事实，只挂验证记录 |

### 7.3 Flag 迁移映射

当前 flags 到新 Claim 的建议映射：

| 旧结构 | 新 Claim |
|---|---|
| `candidate_flags` | `kind=flag_found, level=conjecture` |
| `runtime_flags` | `kind=flag_found, level=conjecture` + `runtime_supported` verification |
| `verified_flags` | `kind=flag_found, level=verified` |
| `rejected_flags` | `kind=flag_found, level=retracted` |

关键点：

- `runtime` 不再是 ClaimLevel，而是验证性质
- `rejected_flags` 语义迁移到 `level=retracted`

---

## 8. 归一化规则

### 8.1 内容归一化

- `content` 保留原始人类可读表达
- `normalized_content` 用于判重、去重、升级、supersede 判断

例如：

- flag：去首尾空白，保留大小写
- endpoint：标准化 host/path/query 排序
- credential：用户名原样，密码不做全量展开到 normalized key，避免过度泄露

### 8.2 判重 key

推荐组合：

`(kind, normalized_content, node_id?)`

说明：

- 某些 claim 应全局去重，例如 `flag_found`
- 某些 claim 可以节点内去重，例如某参数可控结论在不同 node 内独立存在

### 8.3 置信度

- `confidence` 取值范围 `[0.0, 1.0]`
- solver 可写初值
- verifier 可以上调或下调
- `confidence` 不能替代 `verified`

---

## 9. 与当前代码的映射

### 9.1 现有 FlagRecord 如何接入

当前 [ctf_state.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/ctf_state.py:104) 的 `FlagRecord` 已经有一部分可复用字段：

- `value` -> `content`
- `level` -> 迁移期映射
- `evidence_source` -> `SourceChannel` / metadata
- `rationale` -> `confidence_reason` 或 verification rationale
- `proof` -> `VerificationRecord` 的 evidence 部分
- `metadata` -> 保留

不建议直接把 `FlagRecord` 扩成 `Claim`，更建议：

- 新建 canonical `Claim`
- 让旧 flags 桶成为过渡投影

### 9.2 Observation 如何接入

Observation 不直接等于 Claim。

推荐规则：

- 工具输出、DOM 片段、HTTP 响应先作为 trace / observation / artifact
- 只有在被“解释成一个可消费结论”后，才升为 Claim

### 9.3 record_fact 如何接入

当前 [blackboard_adapter.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/blackboard_adapter.py:138) 的 `record_fact()` 只是记 `model_fact`。

迁移后建议：

- `record_fact()` 默认只能写 `Claim(level=assumption or conjecture)`
- 不得直接写 `verified`
- 若内容无法结构化，就仍回退为 observation，而不是强行造 Claim

### 9.4 Verifier 如何接入

当前 [verifier.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/verifier.py:81) 已有最强雏形。

建议扩法：

- 保留 `verify_flag()` 作为 `verify_claim(kind=flag_found)` 的专门入口
- 后续新增：
  - `verify_credential_claim()`
  - `verify_endpoint_claim()`
  - `verify_exploit_claim()`

但对外统一语义应是：

- 任何验证动作最终都产生 `VerificationRecord`
- 任何 verified 升级都通过同一套 claim mutation 规则

---

## 10. 持久化与投影

### 10.1 CTFState 内部表示

P1 推荐在 `CTFState` 中新增：

```yaml
claims_by_id: {claim_id: Claim}
claim_index_by_kind: {kind: [claim_id]}
verification_records_by_id: {verification_id: VerificationRecord}
verification_index_by_claim: {claim_id: [verification_id]}
```

旧结构暂时保留：

- `candidate_flags`
- `runtime_flags`
- `verified_flags`
- `rejected_flags`

但这些旧桶不再是 canonical source of truth。

### 10.2 Checkpoint 表示

checkpoint 中建议同时保存：

- canonical claims
- verification records
- 旧 flag 投影

以支持：

- 新代码恢复
- 旧逻辑回退
- 阶段内兼容

### 10.3 Blackboard 投影

blackboard 不直接存储 Claim，而是读取 canonical claim store 后投影出：

- strongest verified facts
- active conjectures
- recently retracted claims
- high-value claims pending verification

---

## 11. 写权限与职责边界

### 11.1 谁可以创建 Claim

允许：

- solver
- orchestrator
- tool adapter
- verifier

但默认只能创建：

- `assumption`
- `conjecture`

### 11.2 谁可以升级为 verified

只允许：

- verifier 路径

包括：

- `CTFVerifier`
- 平台提交验证子路径
- 本地 deterministic checker
- operator confirmation

### 11.3 谁可以 retracted

允许：

- verifier
- orchestrator 污染回退路径

不允许：

- 普通 solver 直接自删或自改旧事实等级

---

## 12. 最小 API 契约

这里先定义行为，不限定最终必须是哪个类的方法名。

### 12.1 Claim 创建

输入：

- kind
- content
- producer
- primary_trace_id
- optional node_id / parent_claim_ids / confidence / metadata

输出：

- canonical Claim
- 若命中同类同内容旧 Claim，则返回 existing 或 supersede 决策

### 12.2 Verification 追加

输入：

- claim_id
- method
- decision
- trace_id
- rationale

输出：

- VerificationRecord
- 若满足升级条件，返回 claim mutation result

### 12.3 Claim 升级

输入：

- claim_id
- target_level=`verified`
- verification_record_id

输出：

- 升级后的 Claim
- 对应 trace event

### 12.4 Claim 回退

输入：

- claim_id
- reason
- caused_by_claim_id?
- trace_id

输出：

- `retracted` Claim
- downstream taint set

---

## 13. 迁移方案

### 13.1 阶段 A：双写上线

目标：

- 新 schema 入场
- 旧逻辑不崩

动作：

- verifier 写旧 flag 桶时同步写 Claim / VerificationRecord
- checkpoint 同步保存新旧结构
- blackboard 优先读 claim，读不到时回退旧结构

### 13.2 阶段 B：写入口收口

目标：

- 非 verifier 路径不再能产出 verified

动作：

- `record_fact()` 改为只产出 `assumption/conjecture`
- runtime 发现 flag 时不再直接把“runtime”当最终事实等级
- 终止条件优先读取 verified claim

### 13.3 阶段 C：旧结构降级为投影

目标：

- 旧 flag 桶只作为兼容层

动作：

- 所有新逻辑只读 claim store
- 旧 bucket 由 claim store 反向投影生成

### 13.4 阶段 D：清理历史债

目标：

- 删除旧写路径
- 更新测试、context summary、crew merge 逻辑

---

## 14. 测试与验收不变量

### 14.1 I-C1

任一 `verified` Claim 都至少绑定一条 `passed=true && sufficient_for_upgrade=true` 的 VerificationRecord。

### 14.2 I-C2

任一 `retracted` Claim 都保留原始 trace 链，不允许静默删除。

### 14.3 I-C3

同一 `flag_found` 在同一 run 内，不允许同时以 `verified` 与 `retracted` 两种 active 形态并存。

### 14.4 I-C4

solver 直接创建的 Claim，默认不得是 `verified`。

### 14.5 I-C5

checkpoint 恢复后，Claim 与 VerificationRecord 的引用关系保持完整。

### 14.6 I-C6

blackboard 展示出来的 strongest verified facts，必须能反查到 canonical claim。

---

## 15. 推荐首批实现范围

为了降低 P1 风险，第一批只建议落下面 4 类 verified 流程：

1. `flag_found`
2. `credential_valid`
3. `endpoint_exists`
4. `exploit_succeeded`

原因是：

- 这 4 类最影响 stop / switch / verify
- 当前代码已经部分具备验证入口或运行信号
- 它们能覆盖 web / misc / reverse / pwn 的共同主干

---

## 16. 开放问题

下面这些问题可以在实现前进一步定版，但不应阻塞本文生效：

1. `Claim` 是否采用 `dataclass(slots=True)` 还是 `TypedDict + validator`。
2. `normalized_content` 的各 kind 专用归一化器是否放在 verifier 还是独立 registry。
3. `platform_feedback` 是独立 Claim，还是纯粹只作为 `VerificationRecord.metadata`。
4. `superseded` 是否需要单独 trace event，还是复用 claim mutation 事件。

我的建议是：

- P1 先选最轻实现路径，不要因为对象框架争论拖慢事实纪律落地。

---

## 17. 一页纸结论

这份施工图的核心只有 8 句话：

1. 以后所有可消费结论，统一落为 `Claim`。
2. 以后所有验证动作，统一落为 `VerificationRecord`。
3. `verified` 不再是“谁都能写”的状态，只能由 verifier 授予。
4. `runtime` 从顶层事实等级降为验证语义。
5. `retracted` 不删除事实，只保留历史并触发污染回退。
6. 旧 `candidate/runtime/verified/rejected` flags 先兼容双写，后降级为投影。
7. blackboard、checkpoint、trace、crew 都围绕 canonical claim store 接入。
8. P1 不追求万物统一，只先把最关键的高价值事实协议钉稳。
