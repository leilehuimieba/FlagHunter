# CTF Agent 主干架构规范 V1

---

## 1. 架构目标

本项目后续不再以“题型 if-else 扩容”为主要方向，而是以：

> **单 agent 主循环 + 结构化状态模型 + 假设驱动实验 + 独立验证器 + 恢复控制器**

作为推荐架构。

该架构要解决的核心问题：

1. 避免被单个 case 牵着走
2. 避免 source-only 结果误判为最终成功
3. 让系统能够解释“为什么做这一步”
4. 让错误路线可恢复、可测试、可协作

---

## 2. 推荐系统形状

### 2.1 顶层形状

采用：

> **单主 agent + helper modules**

不采用：

- 为了“看起来更智能”而过早拆多 agent
- 把题型分支直接塞满 `ctf_dispatcher.py`
- 让 LLM 自由漫游式地无限探索

原因：

1. 当前问题的主要压力不在“并行智能体数量”，而在：
   - 状态不显式
   - 验证不独立
   - 恢复不可预测
   - 测试层不足

2. 单主 agent 更容易：
   - 收紧边界
   - 做状态治理
   - 建立稳定测试层

3. 多 agent 只能在以下条件满足后再讨论：
   - 主状态模型稳定
   - 单 agent 的实验/恢复主干稳定
   - 模块边界足够清晰

---

## 3. 组件划分

建议后续演进为以下组件：

### A. `CTFCoordinator`

职责：

- 接收 `/ctf` 目标与目标函数
- 驱动主循环
- 选择当前最强假设
- 调度策略执行
- 将实验结果送给验证器与恢复器
- 决定继续 / 停止 / 进入恢复

当前落点建议：

- 从 `pentestagent/agents/pa_agent/ctf_dispatcher.py` 演化

禁止承担的职责：

- 不直接存储全部状态细节
- 不直接写具体 exploit payload 生成细节
- 不直接决定 flag 是否可信（交给 Verifier）

---

### B. `CTFState`

职责：

- 保存结构化题目状态
- 保存观察、artifact、假设、实验、flag 分级
- 作为协调器与策略层之间的唯一共享状态

当前落点建议：

- 新建：`pentestagent/agents/pa_agent/ctf_state.py`

---

### C. `HypothesisEngine`

职责：

- 根据当前状态生成候选假设
- 对假设打分
- 更新支持证据 / 反证
- 选出下一步最有信息增益的实验方向

当前落点建议：

- 新建：`pentestagent/agents/pa_agent/hypothesis_engine.py`

---

### D. `StrategyRegistry`

职责：

- 注册原语级策略
- 对外暴露“适用前提 / 最小实验 / 成功信号 / 失败信号 / 升级条件”
- 被协调器按状态调用

当前落点建议：

- 新建：`pentestagent/agents/pa_agent/strategy_registry.py`
- 后续可拆 `strategies/`

策略粒度要求：

- 以“利用原语”划分
- 不以具体题名 / 平台 / WP 划分

允许示例：

- `auth_form_sqli`
- `backup_source_leak`
- `php_unserialize_magic_method`
- `xss_bot_visit_sid`

禁止示例：

- `buu_easyphp_2019_special_case`

---

### E. `Verifier`

职责：

- 区分 candidate flag、runtime flag、verified flag、rejected flag
- 判断 exploit 是否真正闭环
- 输出可信度与停止建议

当前落点建议：

- 新建：`pentestagent/agents/pa_agent/verifier.py`

它必须独立于策略层：

- 策略层负责“怎么试”
- 验证器负责“试出来的东西是否可信”

---

### F. `RecoveryController`

职责：

- 处理 no-progress、wrong flag、工具缺失、路线失败
- 降权当前假设
- 升权备选假设（基于 HypothesisEngine 排序结果）
- 决定是否切链、暂停或诚实停止

当前落点建议：

- 新建：`pentestagent/agents/pa_agent/recovery.py`

---

### G. `CollectorServer`

职责：

- 在本地监听一个临时 HTTP 端口（默认随机高端口）
- 等待 XSS / CSRF / SSRF 等利用路径中，目标 bot 主动回调
- 收到回调后，提取 cookie / token / flag 并写入 `CTFState`
- 超时（默认 60 秒）后主动关闭并向 RecoveryController 上报 `callback_timeout`

当前落点建议：

- 新建：`pentestagent/agents/pa_agent/collector_server.py`

生命周期约束：

1. 每次 XSS 类实验启动时，由 `CTFCoordinator` 调用 `CollectorServer.start(timeout=60)`
2. 收到有效回调 → 立即关闭，结果写入 `CTFState.runtime_flags`（或 `artifacts`）
3. 超时未收到回调 → 关闭，向 `RecoveryController` 报告 `{signal: "callback_timeout", hypothesis_id: ...}`
4. 禁止复用同一个端口跨实验轮次（每次 start 申请新端口）

典型场景：

- `xss_admin_bot_sid`：bot 访问攻击者页面 → 页面 JS 将 `document.cookie` POST 到 CollectorServer → CollectorServer 提取 sid → 写入 state

---

## 4. 推荐控制流

推荐统一控制流：

```text
Input Goal
  -> Recon / Observe
  -> Update CTFState (含 web_subtype 填充)
  -> Fill ExplorationAgenda          ← 把发现的子端点/文件写入 exploration_agenda
  -> Generate / Rank Hypotheses      ← HypothesisEngine（含结构感知映射 + memory 三步检查）
  -> Pick Next Experiment
  -> Execute Strategy
  -> [Start CollectorServer if XSS/callback type]
  -> Verify Result                   ← Verifier
  -> Update State
  -> Recover / Continue / Stop       ← RecoveryController
       -> if no-progress:
            -> Check exploration_agenda (hint_strength<=2, unexplored)
                 -> if items exist: ExploreAgendaAction（不切假设）
                 -> if agenda exhausted: SwitchHypothesisAction
       -> if recovering: re-rank Hypotheses (回溯反馈 + 三步 memory 检查)
```

必须保证：

1. 每一步都有结构化输入输出
2. 每一步都能被测试观察
3. 每一步都能说明”为什么做”

### 回溯→假设反馈（Retrospective Feedback）

每次实验结束后，无论成功还是失败，都必须将结果反馈给 `HypothesisEngine`：

- **失败 / 无进展**：对应假设的 `confidence` 降权；该假设的 `counter_evidence` 追加本次实验 ID
- **成功（runtime/verified）**：对应假设的 `confidence` 升至 1.0，`status` 更新为 `supported`
- **partial（candidate-only）**：`confidence` 小幅提升，`status` 保持 `active`，`requires_followup=True`

禁止：

- 跳过反馈，直接开始下一实验
- 只在 log 里记结果，不更新 `HypothesisEngine` 内部排序

---

## 5. 当前代码映射建议

### 当前保留

- `ctf_planner.py`
  - 暂时保留轻量判型与 prompt 辅助
  - 后续逐步弱化“题型分发中心”角色

- `ctf_dispatcher.py`
  - 暂时保留为主循环入口
  - 逐步演化为协调器

### 后续拆分建议

从 `ctf_dispatcher.py` 拆出：

- 状态更新逻辑 → `ctf_state.py`
- 假设与优先级 → `hypothesis_engine.py`
- flag 分级验证 → `verifier.py`
- 恢复逻辑 → `recovery.py`
- 原语级策略 → `strategy_registry.py` / `strategies/`

---

## 6. 不采用的架构

### 6.1 不采用“纯 LLM 自由代理”

原因：

- 不可控
- 不可验证
- 不利于 wrong-flag 恢复
- 不利于测试层建设

### 6.2 不采用“全题型大分支调度器”继续膨胀

原因：

- 可维护性差
- 会不断题目特判化
- 不利于多人协作

### 6.3 不采用“先上多 agent”

原因：

- 当前最大问题不是并行度
- 而是主干状态、验证、恢复不够成熟

---

## 7. 易错边界

下面这些是后续实现最容易失稳的 seam：

1. **状态 ownership 混乱**
   - notes、memory、dispatcher 局部变量同时保存同类事实

2. **验证器职责外溢**
   - 策略层直接宣布成功
   - source candidate 绕过 verifier

3. **恢复路径写成散落 if-else**
   - wrong flag / no progress / missing tool 分散在多文件

4. **策略粒度失控**
   - 从“原语级”滑向“题目级”

5. **测试只覆盖 happy path**
   - 不测 candidate flag
   - 不测 rejected flag
   - 不测 recovery

---

## 8. 架构验收标准

后续可以称“主干架构落地”的最低标准：

1. 有独立 `CTFState`
2. 有独立 `Verifier`
3. wrong flag 不再通过临时 notes 旁路实现，而是主干能力
4. 至少 3 类策略已迁移到统一策略接口
5. integration / acceptance 能覆盖成功、错误 flag、恢复三类路径

