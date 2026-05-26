# CTF Agent 测试层规范与验收矩阵 V1

---

## 1. 测试目标

本项目后续测试不应以“试过多少题”为核心指标，而应以：

> **是否覆盖关键行为不变量**

为核心指标。

原因：

- 题目无限
- 行为不变量有限
- 真正 agent 的质量，取决于行为稳定性，不取决于题目样本数

---

## 2. 测试分层

推荐测试层如下：

### L1. Unit

目标：

- 纯函数
- 小模块
- 状态转换
- regex / 判型 / payload 生成

当前目录：

- `tests/unit/agents/`

### L2. Contract

目标：

- 模块接口是否符合约定
- notes schema
- state/verifier 输入输出契约

可落点：

- `tests/unit/...`
- 或单独 `tests/contracts/`

### L3. Integration

目标：

- `LocalRuntime`
- 本地临时 HTTP server
- 多模块协同

当前目录：

- `tests/integration/`

### L4. Acceptance

目标：

- 从目标输入到成功/恢复的完整行为闭环
- 覆盖真实能力，不只验证内部函数

当前目录：

- `tests/integration/test_ctf_dispatcher_*_acceptance.py`

### L5. Adversarial / Regression

目标：

- wrong flag
- misleading hint
- missing tools
- no progress
- decoy source artifacts

当前已存在相关方向：

- `test_ctf_adversarial_grounding.py`

---

## 3. 必测行为不变量

不按题库列，而按行为列。

### A. 正常成功闭环

示例：

- auth-form SQLi
- backup/source leak

要求：

- 必须在最短可行路径上收敛

### B. 浏览器缺失下的 HTTP 回退

要求：

- 无 Playwright 时仍可做基本 Web 侦察与表单解析

### C. 可选工具缺失不应阻塞当前最短链

要求：

- 缺 `sqlmap` 不应阻塞 `auth_form_sqli`

### D. 核心依赖缺失时诚实失败

要求：

- 缺 `http_request` / `browser` 时必须返回 `missing_tools`

### E. source-only flag 不应提前 stop

要求：

- 源码里看到 flag-like 字符串时，至少先降级为 candidate

### F. runtime exploit escalation

要求：

- source leak 后如果出现 exploit primitive，必须继续向 runtime 利用推进

### G. wrong flag recovery

要求：

- 被明确拒绝的 flag 不能再次导致 success

### H. no-progress 收敛

要求：

- 连续无新信息不能无限乱扫

### I. XSS bot 回调路径

要求：

- `xss_admin_bot_sid` 类题目，必须能启动 CollectorServer，向 bot 注入包含回调 URL 的 payload，收到 cookie 后写入 state

### J. CollectorServer 超时后正确恢复

要求：

- CollectorServer 60 秒未收到回调时，必须上报 `callback_timeout` 并由 RecoveryController 处理，而不是挂起主循环

---

## 4. 当前最小验收矩阵

建议后续主干改造至少维持以下矩阵：

| 编号 | 行为 | 层级 | 当前建议 |
|---|---|---:|---|
| A1 | GET auth-form SQLi 成功 | Acceptance | 必须保留 |
| A2 | browserless HTTP fallback | Acceptance | 必须保留 |
| A3 | missing recon deps 诚实失败 | Acceptance | 必须保留 |
| A4 | backup/source leak 提取 | Acceptance | 必须保留 |
| A5 | source flag → runtime exploit escalation | Acceptance | 必须保留 |
| A6 | wrong flag 被 reject 后继续深挖 | Acceptance | 新增重点 |
| A7 | XSS bot cookie theft via CollectorServer | Acceptance | 新增重点 |
| A8 | CollectorServer 超时 → RecoveryController 正确恢复 | Integration | 新增重点 |
| U1 | detect_type 不误判普通 `<script>` 页面 | Unit | 必须保留 |
| U2 | flag regex 不误识别 PHP 代码片段 | Unit | 必须保留 |
| U3 | HypothesisEngine 规则层生成 > LLM 兜底层 | Unit | 新增 |
| U4 | 连续 3 次 none progress → hypothesis 进入 exhausted | Unit | 新增 |

---

## 5. 判定规则

### Pass

- 达到目标行为
- 无错误提前停止
- notes / 状态记录与验证口径一致

### Concern

- 成功了，但路径不稳定
- 或 evidence 落盘不完整
- 或恢复行为过于隐式

### Fail

- source candidate 被当作 verified flag
- wrong flag 后仍再次误判成功
- missing tool 被误报为“只是没拿到 flag”
- 无进展时无限发散

---

## 6. 每次开发至少要补哪类测试

### 改判型

至少补：

- 1 条 unit
- 1 条 acceptance 或 integration

### 改验证器

至少补：

- 1 条 wrong-flag / candidate-flag 相关 acceptance

### 改恢复路径

至少补：

- 1 条恢复 acceptance

### 改状态模型

至少补：

- 1 条 contract 测试
- 1 条 integration

---

## 7. 测试命名规范

推荐：

- `test_ctf_dispatcher_acceptance_*`
- `test_ctf_state_*`
- `test_verifier_*`
- `test_recovery_*`

命名应明确描述行为，不应只写题名。

允许：

- `test_ctf_dispatcher_acceptance_escalates_past_source_flag_to_runtime_flag`

不推荐：

- `test_geek_challenge_php`

---

## 8. 测试层门禁

任何 CTF Agent 主干相关变更，如不满足以下条件，不得视为完成：

1. 相关 unit 通过
2. 至少 1 条 integration / acceptance 通过
3. 至少 1 条恢复类场景被覆盖
4. 新行为已进入矩阵或解释为何不进入

