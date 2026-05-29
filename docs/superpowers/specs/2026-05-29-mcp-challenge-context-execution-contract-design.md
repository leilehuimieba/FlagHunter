# MCP Challenge Context Execution Contract Design

日期：2026-05-29

## 目标

把 MCP ingress 已经持久化下来的本地 CTF 资产合同，真正接进执行链。

上一阶段 MCP 已支持：

- `challengePath`
- `artifactPaths`
- `mode / modeSubtype / goalStyle`

但执行阶段仍统一走 `agent.run_mcp(task)`，没有在 `mode=ctf` 时显式切到 `CTFTaskDispatcher`，导致：

- challenge context 只存在于 entry 元数据
- CTF 本地题目目录 / zip 资产不能沿 MCP 执行链进入 dispatcher truth source

## 最小设计

只做一条最小执行分支：

- `TaskEntry.mode == "ctf"` 时
- `_drive_task(entry)` 不再走 `entry.agent.run_mcp(entry.task)`
- 改为直接实例化 `CTFTaskDispatcher(runtime=entry.agent.runtime)`
- 调用：

```python
await dispatcher.run(
    target=entry.target or "",
    goal=entry.task,
    type=entry.modeSubtype or "auto",
    hint=_ctf_dispatcher_hint(entry),
    challenge_context={
        "challengePath": entry.challengePath,
        "artifactPaths": entry.artifactPaths,
    },
)
```

## 兼容策略

为了不打破旧 hint 行为，本轮保留：

- `_ctf_dispatcher_hint(entry)`
  - 以 `entry.task` 为 base hint
  - 若存在本地资产，再追加：

```text
[local_ctf_assets]
challengePath=...
artifactPaths=...; ...
```

也就是说：

- **truth source：显式 `challenge_context`**
- **compatibility：structured hint fallback**

## 影响范围

### 会改
- `D:\webstudy\FlagHunter\pentestagent\mcp\server\mcp_tools.py`
- `D:\webstudy\FlagHunter\tests\unit\mcp\test_mcp_ingress_mode_contract.py`

### 不改
- MCP schema
- MCP task/status/result 文本展示合同
- CLI / Web / dispatcher 本身
- local zip 解析与 verifier 逻辑

## 验收

1. `run_task` 的 blocking CTF 路径直接走 dispatcher
2. `run_task_async` 的后台 CTF 路径也直接走 dispatcher
3. 两条路径都显式传 `challenge_context`
4. 非 CTF 任务继续走原 `agent.run_mcp(...)`
5. `tests/unit/mcp -q` 保持绿
6. `tests/integration/test_local_asset_eval_pack.py -q` 保持绿
