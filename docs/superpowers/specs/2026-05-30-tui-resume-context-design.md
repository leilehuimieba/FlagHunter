# TUI resumeContext 最小恢复桥设计

日期：2026-05-30

## 目标

在已有 `sessionContext.resumeContext` 基础上，让 TUI 的 `/ctf hint` 与 `/ctf wrong` 在没有 `autonomy_state` 时，仍然可以把 harness 真相摘要转换成 runner 可消费的 `_autonomy_resume_state`，从而继续基于上次上下文恢复，而不是完全重跑。

## 最小合同

### 合同 1

当 `_last_ctf_context` 已有：

- `url`
- `goal`
- `type`
- `hint`
- `submit_profile`
- `runner_config`
- `sessionContext.resumeContext`

但缺少 `autonomy_state` 时，TUI 应该能从 `resumeContext` 生成一个最小的 `_autonomy_resume_state`。

### 合同 2

生成的 `_autonomy_resume_state` 至少能被 `PlatformAutonomyRunner.restore(...)` 接受，并保留：

- `records`
- `visited_keys`
- `consecutive_stops`
- `resume_count`
- `resume_reason`
- `last_resumed_at`

### 合同 3

`/ctf hint` 和 `/ctf wrong` 共享同一恢复桥：

- `autonomy_state` 存在时，优先复用原状态
- `autonomy_state` 不存在时，回退到 `sessionContext.resumeContext`

## 最小行为

### hint 场景

当 operator 输入 `/ctf hint ...` 并且上次上下文只有 `sessionContext.resumeContext` 时：

- 继续执行
- `runner_config` 中应带上 `_autonomy_resume_state`
- `_autonomy_resume_reason = "operator_hint_restart"`

### wrong 场景

当 operator 输入 `/ctf wrong ...` 并且上次上下文只有 `sessionContext.resumeContext` 时：

- 继续执行
- `runner_config` 中应带上 `_autonomy_resume_state`
- `_autonomy_resume_reason = "wrong_flag_feedback_restart"`

## 这轮不做什么

仍然先不做：

- MCP resume API
- Web 详情页一键恢复按钮
- checkpoint diff / merge
- 多 run 统一恢复服务
- 脱离 TUI 的统一恢复入口

## 验收

新增单测验证：

1. `/ctf hint` 可以从 `sessionContext.resumeContext` 启动恢复
2. 现有 `autonomy_state` 路径不回退
3. 现有 `/ctf wrong` 路径继续可用
4. `PlatformAutonomyRunner` 的既有恢复语义不受影响

