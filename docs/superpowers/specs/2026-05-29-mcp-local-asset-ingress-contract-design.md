# MCP Local Asset Ingress Contract — Minimal Design

## 背景

Web ingress 已经支持：

- `challengePath`
- `artifactPaths`

并把它们持久化到 task truth，再桥接给 CTF dispatcher。  
如果 MCP 入口不对齐，这条能力就只能在 Web 侧可用，无法满足“给 agent 一个题目路径 / 压缩包路径，它自己分析”的通用目标。

## 目标

让 MCP 的：

- `run_task`
- `run_task_async`

也接受并持久化：

- `challengePath`
- `artifactPaths`

## 非目标

本轮不做：

- MCP 直接驱动新的 dispatcher 显式 `challenge_context`
- artifact metadata 复杂对象
- 与 Web 完全统一的 task JSON API

## 最小合同

### schema

`run_task` / `run_task_async` 新增：

- `challengePath: string`
- `artifactPaths: string[]`

### task entry

`TaskEntry` 持久化：

- `challengePath`
- `artifactPaths`

### 返回摘要

最小返回中附带：

- `challenge_path: ...`
- `artifact_paths: ...`

用于让调用方明确看到本地题目资产已进入任务上下文。

## 设计取舍

本轮只做 MCP ingress truth，不额外改 agent 执行签名。  
也就是说：

- Web 与 MCP 都先把本地资产变成结构化任务真值
- 执行侧后续仍可通过已有桥接逻辑消费

## 验证口径

1. schema 含 `challengePath / artifactPaths`
2. `run_task_async` 调 mode contract 前后不丢这些字段
3. `TaskEntry` 持久化这些字段
4. MCP 返回摘要能看到这些字段

## 下一步

完成后，下一条最自然的主线是：

1. 前端 New Task / Task Detail 直接展示 challengePath / artifactPaths
2. 再把 Web / MCP / CLI 共用的本地资产 contract 从“hint bridge”升级到显式 `challenge_context`
