# Handoff metadata 与 MCP run artifacts 最小设计

日期：2026-05-30

## 目标

沿着 Task 7 继续把 handoff / resume 主线往前推进两小步：

1. `ConversationStore` 不再只保存聊天消息，也保存最新 handoff metadata
2. MCP `run_task_async` 直接暴露 `run_id / ledger_path / checkpoint_path`

## A. ConversationStore handoff metadata

### 最小合同

`ConversationStore.save(...)` 增加可选 `handoff` 参数。

当 handoff 存在时，会话 JSON 附带：

- `last_run_id`
- `last_checkpoint`
- `last_ledger`
- `last_resume_summary`
- `ctf_context`

其中 `ctf_context` 只保留恢复最需要的最小字段：

- `url`
- `goal`
- `type`
- `hint`
- `submit_profile`
- `runner_config`
- `execution_mode`
- `autonomy_state`
- `autonomy_end_reason`
- `sessionContext`

### 读路径

新增一个读取会话元数据的小入口，返回保存过的 handoff metadata；旧的 `load(...)` 继续只返回 messages，不破坏现有调用。

### TUI 接入

TUI autosave 在保存会话时，把当前 `_last_ctf_context` 映射成 handoff metadata 一并写入。

TUI 恢复会话时：

- 先恢复消息
- 再读取 handoff metadata
- 如存在 `ctf_context`，则恢复到 `_last_ctf_context`

这样 `/ctf hint`、`/ctf wrong` 在跨会话恢复后仍可继续接上。

## B. MCP async run artifact contract

### 最小合同

`TaskEntry` 增加：

- `runId`
- `ledgerPath`
- `checkpointPath`

### 写入规则

对于 MCP CTF 任务：

- 在任务创建时生成稳定 `runId`
- 预先计算 `ledgerPath`
- 预先计算 `checkpointPath`
- 后台 dispatcher 执行时显式复用这个 `runId`

### 读路径

以下接口同步暴露这些字段：

- `run_task_async`
- `get_task_status`
- `get_task_result`

第一轮先只做合同暴露，不做完整 MCP resume API。

## 这轮不做什么

仍然先不做：

- Web detail 一键恢复按钮
- MCP resume / replay 控制接口
- 多 run merge / checkpoint diff
- pentest mode 的统一 harness run artifact

## 验收

新增单测验证：

1. `ConversationStore` 可持久化并读取 handoff metadata
2. TUI autosave 会把 `_last_ctf_context` 写入 handoff metadata
3. TUI restore 会把 handoff metadata 恢复回 `_last_ctf_context`
4. MCP `run_task_async` 返回 `run_id / ledger_path / checkpoint_path`
5. `get_task_status` / `get_task_result` 也暴露相同字段

