# Checkpoint Store 最小设计（Harness Phase A-3）

日期：2026-05-29  
仓库：`D:\webstudy\FlagHunter`

---

## 目标

在已有：

- `session_ledger`
- `artifact_registry`

之后，补上**可恢复的结构化状态快照**，让 CTF 主链路至少具备：

1. 运行开始时有初始 checkpoint
2. 运行结束时有最终 checkpoint
3. `CTFState` 能稳定 snapshot / restore
4. 后续 resume / handoff / session_context 有可消费的状态真相

本轮仍然保持最小范围，不做：

- 自动 resume
- UI checkpoint 浏览
- MCP checkpoint inspection
- 多 checkpoint 策略调优

---

## 最小数据合同

每条 checkpoint record 先统一成：

```json
{
  "checkpoint_id": "checkpoint-xxxxxxxxxxxx",
  "ts": "2026-05-29T00:00:00+00:00",
  "run_id": "ctf-run-1",
  "label": "dispatcher_started | task_finished",
  "state": {},
  "metadata": {}
}
```

说明：

- `run_id`：与 ledger / artifact registry 对齐
- `label`：先只做阶段标签
- `state`：保存 `CTFState` 的结构化 snapshot
- `metadata`：保存最关键的轻量执行信息，如 success / flag / reason

---

## 最小模块落点

新增：

- `D:\webstudy\FlagHunter\pentestagent\harness\checkpoint_store.py`

最小能力：

1. `save_checkpoint(...)`
2. `list_checkpoints(run_id)`
3. `latest_checkpoint(run_id)`

---

## CTFState 最小补强

为：

- `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_state.py`

补两个最小接口：

1. `to_snapshot()`
2. `from_snapshot(snapshot)`

要求：

- 保留现有 `to_dict()` 语义
- roundtrip 后至少保持：
  - observations
  - artifacts
  - flags
  - stop_reason

---

## Dispatcher 最小接入点

### 1. `dispatcher_started`

在 `CTFTaskDispatcher.run(...)` 初始化 `self.state` 后写一条 checkpoint。

### 2. `task_finished`

在 `_finalize_solve_result(...)` 记录最终 stop state 后写一条 checkpoint。

这样本轮至少能证明：

- run 起点可恢复
- run 终点可恢复

---

## 为什么这一刀值高

当前系统虽然已经能记录：

- 事件
- artifact

但还不能可靠回答：

- “这次 run 停下时的结构化状态是什么？”
- “如果下次 resume，要从哪个 state 接？”

checkpoint_store 是把这些问题从“看 notes / 看日志 / 看 prompt summary”变成“看结构化快照”的最小前提。

---

## 验证口径

本轮通过标准：

1. `CTFState` snapshot roundtrip 单测通过
2. `CheckpointStore` 能写入并返回 latest checkpoint
3. dispatcher 单测能证明：
   - `dispatcher_started` 写 checkpoint
   - `task_finished` 写 checkpoint
   - latest checkpoint 可还原出最终 `CTFState`
4. 既有 `session_ledger` / `artifact_registry` / local asset eval 回归不退化

