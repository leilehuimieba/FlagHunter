# CTF Agent 开发规范总览 V1

> 适用范围：`D:\webstudy\FlagHunter` 中与 `/ctf`、`CTFTaskDispatcher`、`pa_agent`、CTF notes / 验证 / 恢复 / 测试层相关的全部后续改造。
>
> 本文档是 **先文档、后实现** 的总入口。后续开发必须以本文为主索引，不允许绕过规范直接堆功能。

---

## 1. 背景与目标

当前项目已经具备：

- 基础 `/ctf` 入口
- `ctf_planner.py` 的轻量判型
- `ctf_dispatcher.py` 的确定性执行链
- 局部 wrong-flag 恢复与 source-leak/runtime 区分
- 一组围绕 Web CTF 的 unit/integration acceptance 测试

但当前系统仍主要表现为：

> **“增强型 deterministic solver”**

而不是：

> **“真正的 hypothesis-driven CTF agent”**

本轮文档建设的目标，不是再增加一条题型补丁，而是为后续开发建立一套统一规范，让项目可以稳定地向以下目标演进：

1. 有明确的 **状态模型**
2. 有显式的 **假设、实验、验证、恢复** 机制
3. 有统一的 **协作边界**
4. 有可复用的 **测试层**
5. 有一套“先规范、后编码、再验收”的开发路径

---

## 2. 真正的 CTF Agent 定义

本项目对“真正的 agent”采用如下定义：

> **面对未知题目时，系统能够围绕“拿到真实 flag”这一目标，自主维护题目状态，生成可检验假设，选择最有信息增益的实验动作，读取结果后更新判断，并在必要时恢复、换路或诚实停止。**

满足下面 6 条，才可称为本项目意义上的“CTF Agent”：

1. **目标驱动**  
   不以“跑完一个链路”作为成功，而以“拿到经过验证的真实 flag”作为成功。

2. **状态显式化**  
   不把关键判断只留在上下文文本里，而要结构化保存观察、候选 flag、已拒绝 flag、假设、实验结果。

3. **假设显式化**  
   不靠大段 prompt 暗示路线，而要让系统知道“当前最强假设是什么、支持证据是什么、反证是什么”。

4. **实验最小化**  
   不把“多跑几个工具”当成思考，优先做最小、最便宜、最能缩小搜索空间的实验。

5. **验证独立化**  
   结果是否可信，必须有独立验证口径，尤其要区分 source-only flag 与 runtime flag。

6. **恢复可重复**  
   wrong flag、无进展、工具缺失、利用失败后，系统要按规则恢复，而不是随意扩散扫描。

---

## 3. 本轮文档包清单

后续开发必须同时遵循以下文档：

**核心规范（必读）**

1. `docs/dev/CTF_Agent_主干架构规范_V1.md`
   - 定义系统形状、责任边界、推荐架构
   - 组件：CTFCoordinator / CTFState / HypothesisEngine / StrategyRegistry / Verifier / RecoveryController / CollectorServer

2. `docs/dev/CTF_Agent_状态模型与接口契约_V1.md`
   - 定义 `CTFState / Hypothesis / Experiment / VerificationResult`
   - 定义各模块输入输出契约；HypothesisEngine 实现约束
   - 新增实体速查表（推理层 + 能力层全部实体）

3. `docs/dev/CTF_Agent_实现约束与协作规范_V1.md`
   - 定义代码约束、模块边界、文档先行规则、多人协作方式
   - 工具缺失安装流程约束（7 步，用户确认前置）

4. `docs/dev/CTF_Agent_测试层规范与验收矩阵_V1.md`
   - 定义测试金字塔、行为不变量、验收门槛
   - XSS / CollectorServer 测试场景（A7、A8）

5. `docs/dev/CTF_Agent_分阶段开发计划_V1.md`
   - Phase 0.5（live solve）→ Phase 1-5（主干）→ Phase 5.5（推理+能力+记忆）→ Phase 6（收口）
   - 完整优先级顺序

**智能化扩展（Phase 5.5 必读）**

6. `docs/dev/CTF_Agent_智能推理层规范_V1.md`
   - PreActionReasoning / Interpretation / AdversarialLens / Postmortem / StopReport
   - 五个组件的数据结构、控制流位置、实现约束、验收标准

7. `docs/dev/CTF_Agent_能力层与记忆模型_V1.md`
   - CapabilityRegistry + 降质路由
   - StrategyMemory + ChallengeFingerprint + FAISS 检索
   - 跨题学习机制

**性能与预算（Phase 5.5 必读）**

8. `docs/dev/CTF_Agent_性能与预算规范_V1.md`
   - 模型分层使用（轻量 vs 主模型）
   - 快速路径条件
   - 单题 token/时延硬上限
   - 推理层延迟预算与降级阈值

**测试（开发前必读）**

9. `docs/dev/CTF_Agent_完整测试用例集_V1.md`
   - 50+ 条测试用例（A、U、I、R、C、M、P、ADV 系列）
   - 门禁规则：每类改动最小通过用例集
   - 测试基础设施约定（fixture、mock、网络隔离）
   - 用例状态追踪表

**用户视角（Phase 6 必读）**

10. `docs/dev/CTF_Agent_用户操作手册_V1.md`
    - `/ctf` 命令族完整说明
    - 推理记录解读
    - 跨题记忆管理
    - 常见问题与排查

**能力扩展（Phase 5.7 / 5.8 / 7 必读）**

11. `docs/dev/CTF_Agent_自由探索与LLM驱动兜底_V1.md`
    - LLM-driven 兜底策略 `llm_driven_exploration`
    - PreActionReasoning Q1~Q4 强制规则
    - CapabilityRegistry 三路决策树（approved / degrade / unavailable）
    - LLM1~LLM8 测试用例
    - 解决"全新未知题型 agent 直接 stop_no_progress"的问题

12. `docs/dev/CTF_Agent_多Provider韧性与多Agent协作_V1.md`
    - Part A：API 额度耗尽 / 网络抖动的自动切换 + 自动恢复
    - Part B：CTFCrewCoordinator 多 worker 并行（Recon / Exploit / LLMExplorer / Verifier）
    - 6 类 LLM 错误的状态转换规则
    - PROV1~PROV6 + CREW1~CREW6 测试用例
    - 对比 codex 裸跑的不可替代价值表

---

## 4. 文档优先级

若文档之间存在冲突，按以下顺序解释：

1. 本总览文档
2. 主干架构规范
3. 状态模型与接口契约（含 Primitive/Strategy/Hypothesis 分层、Schema 版本管理、Verifier 判定算法）
4. 智能推理层规范
5. 能力层与记忆模型
6. 性能与预算规范
7. 实现约束与协作规范
8. 测试层规范与验收矩阵
9. 完整测试用例集
10. 分阶段开发计划
11. 用户操作手册
12. 自由探索与LLM驱动兜底
13. 多Provider韧性与多Agent协作
14. 旧版开发计划 / 旧攻略文档

---

## 5. 后续开发的强制规则

后续任何与 CTF Agent 主干有关的开发，都必须遵守：

### 5.1 文档先行

以下情况必须先更新文档，再允许写代码：

- 新增主干模块
- 更改状态模型
- 更改模块所有权
- 更改验证口径
- 更改测试层分级
- 更改停止/恢复策略

### 5.2 无契约不开发

如果一个功能无法回答以下 4 个问题，不允许进入实现：

1. 它读哪些状态？
2. 它写哪些状态？
3. 成功信号是什么？
4. 失败后由谁恢复？

### 5.3 测试先定义门槛

以下情况不允许直接 merge：

- 只加功能，不补对应回归
- 只跑 happy path，不覆盖恢复路径
- 只有 mock 测试，没有 integration / acceptance 证据

### 5.4 禁止题目特判漂移

允许写“原语级策略”，禁止写“平台/题目名特判”。

允许：

- `backup_source_leak`
- `php_unserialize_magic_method`
- `auth_form_sqli`

禁止：

- `if challenge_name == "极客大挑战2019PHP": ...`
- `if buuoj and www.zip then ...`

---

## 6. 本轮文档之后的开发入口

后续代码开发统一从下面 4 个入口之一开始，进入前先确认当前处于哪个 Phase：

1. **状态主干开发**（Phase 1）
   - 先看：`CTF_Agent_状态模型与接口契约_V1.md`

2. **执行主循环改造**（Phase 2-5）
   - 先看：`CTF_Agent_主干架构规范_V1.md`

3. **推理层 + 能力层 + 记忆层**（Phase 5.5）
   - 先看：`CTF_Agent_智能推理层规范_V1.md`
   - 再看：`CTF_Agent_能力层与记忆模型_V1.md`
   - 对照：`CTF_Agent_完整测试用例集_V1.md` R/C/M 系列

4. **测试层补强**（贯穿所有 Phase）
   - 先看：`CTF_Agent_完整测试用例集_V1.md`（确认要覆盖哪些用例）
   - 再看：`CTF_Agent_测试层规范与验收矩阵_V1.md`（门禁规则）

---

## 7. 当前判断

当前项目不应再以”补某一道题”为主要驱动方式。  
从本轮开始，后续开发应当按：

> **live solve proof → 行为不变量 → 状态模型 → 假设/实验/验证/恢复 → 策略实现 → 测试回归**

这一顺序推进。

补充说明：

- **Phase 0.5 (live solve proof) 是所有主干改造的前置**：先让当前系统跑一道真实题，找到卡点，再决定改哪里。不允许在没有任何实战依据的情况下进入 Phase 1。
- **回溯→假设反馈是主循环的必要环节**：每次实验结束，无论成功还是失败，都必须将结果反馈给 HypothesisEngine，更新对应假设的置信度。这是系统能”解释自己为什么换路”的基础。
- **CollectorServer 是 XSS 类题目的基础设施**：不能用临时 HTTP server 的临时代码凑合，必须作为独立组件管理生命周期和超时。

这就是本项目从”会做题的调度器”演进成”真正 CTF Agent”的基础规范。

---

## 8. Phase 6 系列入口（已完成）

> Phase 0–6 已完成（980 tests passing）。Phase 6 最终验收审计已通过。

Phase 6 核心文档（只读参考）：

```
docs/dev/CTF_Agent_Phase6_规划与主控决策_V1.md
docs/dev/CTF_Agent_Phase6_最终验收审计_V1.md
```

**文档优先级**：Phase 6 规划文档高于 §4 中所有之前的文档，不一致时以 Phase 6 文档为准。

---

## 9. Phase 7 系列入口（当前最高优先级）

> Phase 6 已完成（980 tests passing）。当前进入 Phase 7 能力增强阶段。

所有进入 Phase 7 系列的开发 agent，**必须优先阅读**：

```
docs/dev/CTF_Agent_Phase7_改造建议清单_V1.md
```

该文档包含：
- 25 条知识库新条目（BB-300~BB-324）的设计翻译
- §1 HypothesisEngine — 树形假设图 + abort condition（LATS / Devil's Advocate）
- §2 RecoveryController — verbal reflection（Reflexion / CRITIC）
- §3 StrategyMemory — 失败轨迹保存与检索（BB-311 / Retrospex）
- §4 stop_no_progress — 在线风险评分替代静态计数器（AgentForesight）
- §5 SSTI 分层 — Detect → Identify → Exploit（PortSwigger / Tplmap）
- §6 ReplayEvalHarness — 失败标签细化（NYU CTF Bench）
- §7 hash_guarded_access 策略泛化（SignSaboteur）
- §8 FlagProof 结构增强（OWASP / SARIF）
- 执行优先级表 + 门禁规则 + 冻结声明

**文档优先级**：Phase 7 改造建议清单高于 §4 和 §8 中所有之前的文档，不一致时以本文档为准。

