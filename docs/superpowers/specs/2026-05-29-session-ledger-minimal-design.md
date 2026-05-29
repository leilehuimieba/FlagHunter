# Session Ledger Minimal Design

日期：2026-05-29

## 目标

为 FlagHunter 当前已接通的 CTF 执行链补上一层最小统一事件真相：

- append-only
- run_id 级别
- JSONL 可回放
- 不依赖聊天 summary

本轮只做最小 Phase A，不引入 artifact registry / checkpoint / resume。

## 最小模块

新增：

- `D:\webstudy\FlagHunter\pentestagent\harness\__init__.py`
- `D:\webstudy\FlagHunter\pentestagent\harness\session_ledger.py`

## SessionLedger 最小能力

```python
SessionLedger(root)
```

支持：

- `path_for_run(run_id)`
- `append_event(run_id, event_type, payload)`
- `read_events(run_id)`
- `tail_events(run_id, limit)`

存储格式：

- 每个 `run_id` 一个 `jsonl`
- 每行一个事件对象

最小事件形状：

```json
{
  "ts": "2026-05-29T...+00:00",
  "run_id": "run-123",
  "event_type": "dispatcher_started",
  "payload": {...}
}
```

## Dispatcher 最小接入

本轮只接入：

- `CTFTaskDispatcher.run(...)`

新增可选参数：

- `run_id: str | None = None`
- `ledger_root: str | Path | None = None`

规则：

- 调用方传 `run_id` 时优先使用调用方 run_id
- 未传时 dispatcher 自行生成 `ctf-xxxxxxxxxxxx`
- 未传 `ledger_root` 时默认写到：
  - `loot/session_ledgers/`

## 本轮事件类型

只记录最关键 5 类事件：

1. `dispatcher_started`
2. `verification_decision`
3. `recovery_decision`
4. `missing_tools_recorded`
5. `task_finished`

### dispatcher_started
记录：
- target
- goal
- requested_type
- local_challenge_auto_verify
- has_challenge_context

### verification_decision
记录：
- decision
- flag
- evidence_source
- rationale
- confidence

### recovery_decision
记录：
- action
- reason
- should_stop
- chain_name
- next_chain_order

### missing_tools_recorded
记录：
- missing_tools
- install_commands

### task_finished
记录：
- success
- flag
- reason
- chain_used
- missing_tools

## 本轮不做

- 不改 Web / CLI / MCP 调用方去主动传 run_id
- 不做 artifact handle
- 不做 checkpoint snapshot
- 不做 resume
- 不把 Web / MCP / TUI 全部改成消费 ledger

## 验收

1. `SessionLedger` append/read/tail 可用
2. dispatcher verified 路径会写：
   - `dispatcher_started`
   - `verification_decision`
   - `task_finished`
3. dispatcher missing-tools 路径会写：
   - `dispatcher_started`
   - `missing_tools_recorded`
   - `task_finished`
4. `tests/unit/harness/test_session_ledger.py` 通过
5. 新增 dispatcher ledger 单测通过
6. `tests/integration/test_local_asset_eval_pack.py -q` 继续通过
