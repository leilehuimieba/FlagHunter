# CLI Local Asset + Mode Contract — Minimal Design

## 背景

目前 Web / MCP 入口已经支持：

- `mode / ctfType`
- `challengePath / artifactPaths`

但 `pentestagent run ...` 仍主要停留在旧的 headless 语义：

- `agent / crew`
- 无结构化本地题目资产入口

这会导致 CLI 无法与 Web / MCP 一样，把“题目目录 / 本地材料路径”稳定送进 CTF dispatcher。

## 目标

让 CLI `run` 入口具备最小统一合同：

- `--mode`
- `--ctf-type`
- `--challenge-path`
- `--artifact-path`（可重复）

并在执行侧：

1. 走统一 mode router
2. `mode=ctf` 时进入 `CTFTaskDispatcher`
3. 将本地资产桥接成结构化 `[local_ctf_assets]` hint block

## 非目标

本轮不做：

- TUI 参数对齐
- CLI 全量任务对象持久化
- 新的 `challenge_context` dataclass
- crew / playbook 全链路重构

## 最小设计

### 参数层

`pentestagent run` 新增：

- `--mode auto|pentest|ctf`
- `--ctf-type`
- `--challenge-path`
- `--artifact-path`（append）

### 路由层

`run_cli()` 内部：

- 旧 `mode=crew` 仍保留为 legacy execution mode
- 新 `mode=auto|pentest|ctf` 通过 `resolve_mode_contract(...)` 统一解析

### 执行层

- `resolved_mode == ctf`：走 dispatcher
- 其它：维持 pentest agent / crew 旧路径

### 本地资产桥接

CLI 新增 helper，把：

- `challenge_path`
- `artifact_paths`

转成：

```text
[local_ctf_assets]
challengePath=...
artifactPaths=...; ...
```

并传给 `CTFTaskDispatcher.run(..., hint=...)`

## 设计取舍

本轮仍沿用 hint bridge，而不是直接改 dispatcher 公共签名：

- 改动小
- 与 Web / MCP 当前行为一致
- 可以先让三入口合同对齐

## 验证口径

1. `parse_arguments()` 能解析 CLI 本地资产合同参数
2. `run_cli()` 在 CTF 路径会调用 dispatcher
3. dispatcher hint 中带有结构化 `[local_ctf_assets]`
4. pentest 路径仍走旧 `PentestAgentAgent`

## 下一步

这轮完成后，更值得继续的是：

1. 把 Web / MCP / CLI 的本地资产桥接统一升级为显式 `challenge_context`
2. 基于真实完整题目录做 headless CLI solve/eval 样例
