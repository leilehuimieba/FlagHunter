# SessionContextView resume/handoff payload 最小设计

日期：2026-05-30

## 目标

在已有 `session ledger / artifact registry / checkpoint` 基础上，给 harness 真相层补一个可直接消费的 `resume/handoff payload`，让 Web detail 与上下文装配都能读同一个事实摘要，而不是各自重新拼接。

## 最小合同

### 合同 1

`SessionContextView.build_run_context(run_id)` 新增：

- `resumeContext`

当 run 存在 harness 数据时，返回一个稳定对象；否则返回 `None`。

### 合同 2

`resumeContext` 至少包含：

- `runId`
- `checkpointLabel`
- `checkpointId`
- `stopReason`
- `verifiedFlags`
- `runtimeFlags`
- `recentEventTypes`
- `artifactRefs`
- `summary`

### 合同 3

`web_server._task_detail_payload(...)` 直接透传这份 `resumeContext`。

### 合同 4

`ContextAssembler` 的 session summary 优先复用 `resumeContext.summary`。

## 这轮不做什么

仍然先不做：

- TUI 直接从 harness payload 恢复自治 runner
- MCP resume API
- checkpoint diff / merge

## 验收

新增单测验证：

1. `SessionContextView` 能生成稳定的 `resumeContext`
2. 没有 run 数据时 `resumeContext is None`
3. `web_server` task detail 会暴露 `sessionContext.resumeContext`
4. `ContextAssembler` session summary 会复用 resume summary
