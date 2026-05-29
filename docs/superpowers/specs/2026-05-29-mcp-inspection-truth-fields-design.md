# MCP Inspection Truth Fields Design

日期：2026-05-29

## 目标

在 MCP 已经把 CTF 任务通过 `CTFTaskDispatcher` 执行之后，继续把观察层也收口为真值输出。

本轮只解决一个问题：

> `list_tasks / get_task_status / get_task_result` 需要真实暴露 CTF 执行事实，而不是只显示通用 task 字段。

## 最小 truth fields

本轮只暴露下面 5 组事实：

- `mode`
- `modeSubtype`
- `goalStyle`
- `finalFlag`
- `ctfChainUsed`
- `ctfMissingTools`
- `ctfNotes`

这些字段都来自 CTF dispatcher 的真实返回值，不做推断拼装。

## 持久化位置

扩展 `TaskEntry`：

- `finalFlag: str | None`
- `ctfChainUsed: list[str]`
- `ctfMissingTools: list[str]`
- `ctfNotes: list[str]`

在 `_drive_task(entry)` 的 CTF 分支里，从 `solve_result` 同步写入。

## 输出面

### `list_tasks`
增加轻量摘要：

- `mode=ctf/web`
- `chain=xss,admin_bot`

只做简短一行事实，不展开 notes。

### `get_task_status`
增加结构化状态事实：

- `mode`
- `mode_subtype`
- `goal_style`
- `final_flag`
- `ctf_chain_used`
- `ctf_missing_tools`
- `ctf_notes`

其中 `ctf_notes` 只做单行 join 预览。

### `get_task_result`
增加完整结果区块：

- `mode`
- `mode_subtype`
- `goal_style`
- `final_flag`
- `[ctf_chain_used]`
- `[ctf_missing_tools]`
- `[ctf_notes]`

## 不做

本轮不做：

- 更复杂的 JSON 化结果合同
- traces / tool_result 结构大改
- 时间字段规范化（虽然仍看到 `utcnow()` deprecation warning）
- Pentest 模式专属 truth fields

## 验收

1. CTF blocking run 后，`TaskEntry` 持久化 dispatcher truth fields
2. `list_tasks` 能看到 mode + chain 摘要
3. `get_task_status` 能看到 status 级 truth fields
4. `get_task_result` 能看到完整 CTF truth blocks
5. `tests/unit/mcp -q` 通过
6. `tests/integration/test_local_asset_eval_pack.py -q` 通过
