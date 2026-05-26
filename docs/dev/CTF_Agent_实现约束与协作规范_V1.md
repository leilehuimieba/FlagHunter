# CTF Agent 实现约束与协作规范 V1

---

## 1. 目标

本规范用于约束：

- 后续代码如何写
- 多人如何协作
- 什么可以改
- 什么必须先改文档

避免出现：

- 代码能跑，但主干不可维护
- 不同人各自补题，最后逻辑互相打架
- 测试层和实现层长期脱节

---

## 2. 实现原则

### 2.1 文档优先

以下类型改动必须先更文档：

- 新增模块
- 修改状态模型
- 修改验证口径
- 修改 wrong-flag 恢复路径
- 修改测试分层

### 2.2 小步改造

每次改造应尽量只完成一个主责：

- 状态主干
- 验证器
- 恢复器
- 某一类策略迁移
- 测试层补强

禁止在一个变更中同时：

- 重写 dispatcher
- 加 4 类策略
- 改 notes schema
- 改 TUI 流程

### 2.3 原语级抽象

后续策略只能按“漏洞原语 / 解题原语”抽象，不能按题名抽象。

---

## 3. 代码约束

### 3.1 主循环约束

`Coordinator` / `ctf_dispatcher.py`：

- 负责驱动，不负责承载全部细节
- 不允许继续无限膨胀成千行题型大杂烩
- 新逻辑优先抽到独立模块

### 3.2 工具层约束

工具层只负责：

- 执行
- 回传
- 记录原始输出

工具层不负责：

- 判定最终成功
- 决定假设优先级

### 3.3 notes 约束

`notes` 调用必须：

1. 使用符合 schema 的 category
2. 调用方必须检查返回值
3. 不允许把验证失败悄悄吞掉

### 3.4 wrong-flag 约束

wrong flag 只能进入：

- `rejected_flags`
- 或持久化 notes 中的 rejected 类记录

禁止：

- 只在 prompt 里提醒一下
- 只在日志里记一下

---

### 3.5 工具缺失安装流程约束

**触发条件（严格）**：

仅当满足**全部**以下条件时触发本流程：

1. `CapabilityPrimitive.best_available()` 返回 None（没有任何可用实现，包括降质）
2. 至少存在一个 `requires_install == True` 的实现

**降质实现存在时绝不触发本流程**（详见 `CTF_Agent_能力层与记忆模型_V1.md` §2.6 判定树）。

当 `RecoveryController` 在上述条件下收到 `missing_tool` 信号时，必须按以下顺序处理，**不允许跳步**：

1. **确认工具名**：从 `CTFState.capabilities` 中取缺失工具名
2. **查磁盘可用空间**：调用系统接口查可用空间，若 < 200MB 则停止并向用户报告 `disk_insufficient`
3. **向用户提示**：在 TUI 或输出中显示"检测到缺失工具 `<name>`，是否允许安装？"并**等待用户响应**
4. **用户确认后**：执行最小安装命令（pip / apt / brew 视平台而定）
5. **安装后验证**：重新探测工具是否可用（`shutil.which` 或直接调用 `--version`）
6. **验证失败**：向 `RecoveryController` 上报 `tool_install_failed`，降权当前假设，选下一最强假设
7. **验证成功**：更新 `CTFState.capabilities`，继续当前假设的下一实验

禁止：

- 跳过用户确认直接安装
- 安装失败后默默继续，不上报状态
- 把安装动作写死在策略层，应只在 `RecoveryController` 里统一处理

---

## 4. 协作边界

建议按以下 ownership 协作：

### A. 主循环所有者

负责：

- `ctf_dispatcher.py`
- 后续 `CTFCoordinator`
- 与 TUI `/ctf` 的主入口衔接

### B. 状态/验证所有者

负责：

- `ctf_state.py`
- `verifier.py`
- candidate/runtime/rejected flag 口径

### C. 策略所有者

负责：

- `strategy_registry.py`
- 原语级策略实现

### D. 测试层所有者

负责：

- unit
- integration
- acceptance
- regression pack

### E. 文档与契约所有者

负责：

- docs 一致性
- 接口约束同步
- 开发计划与 DoD 更新

---

## 5. 提交流程约束

每个与 CTF Agent 主干相关的变更必须包含：

1. **变更说明**
   - 改了什么
   - 为什么改
   - 对应哪条文档规范

2. **边界说明**
   - 不改什么
   - 哪些问题明确后置

3. **测试证据**
   - 至少列出本次跑过哪些 test

4. **风险说明**
   - 这次最容易回归的点是什么

---

## 6. Definition of Done

任何主干改动，只有满足下面全部条件才算完成：

1. 文档已更新
2. 代码边界清晰
3. unit test 通过
4. integration / acceptance 至少一条相关用例通过
5. wrong-flag / no-progress / missing-tool 中至少有一类恢复路径被验证
6. 无题目名特判

---

## 7. 明确禁止事项

### 禁止 1：题目名硬编码

禁止：

```python
if "极客大挑战 2019" in challenge_name:
    ...
```

### 禁止 2：绕过 verifier 直接成功

禁止策略层直接：

- 见到源码里的 flag 就 `success=True`

### 禁止 3：只加日志不加状态

关键事实必须入结构化状态，不允许只留在 log / prompt / notes 文本里。

### 禁止 4：只补 happy path

任何主干改动不补恢复路径测试，视为未完成。

