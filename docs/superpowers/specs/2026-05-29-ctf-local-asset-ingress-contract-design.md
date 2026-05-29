# CTF Local Asset Ingress Contract — Minimal Design

## 背景

上一轮已经证明：

- 当 CTF dispatcher 获得本地 challenge 路径时
- 它可以利用 compose logs / 本地题包资产
- 把真实 `easy_login` 从 truthful stop 提升为真实拿 flag

但这个能力当前仍然依赖把路径塞进自由文本 `hint`。  
这会导致：

- Web / MCP / CLI 输入不稳定
- replay / retry / continue 无法可靠继承
- task detail 无法 truthfully 暴露本地题目资产上下文

## 目标

把“本地题目资产”升级成 task 的结构化真值字段，而不是散落在自然语言里。

本轮最小合同只包含：

- `challengePath: string | null`
- `artifactPaths: string[]`

## 非目标

本轮不做：

- 新的 dispatcher `run()` 参数签名
- MCP / CLI / 前端表单全量接线
- archivePath / composePath / datasetPath 等更多资产类型
- 大而全的本地题包上下文系统

## 最小合同

### ingress 输入

`POST /api/tasks` 接受：

```json
{
  "mode": "ctf",
  "ctfType": "web",
  "challengePath": "D:\\webstudy\\CTF\\2026\\CTF比赛题\\easy_login",
  "artifactPaths": [
    "D:\\webstudy\\CTF\\2026\\CTF比赛题\\easy_login\\docker-compose.yml",
    "D:\\webstudy\\CTF\\2026\\CTF比赛题\\easy_login\\src\\server.ts"
  ]
}
```

### task 持久化

task 需持久化：

- `challengePath`
- `artifactPaths`

### 派生任务

以下动作必须继承：

- replay
- retry
- continue（原 task 保持不变）

### dispatcher bridge

本轮先不改 `CTFTaskDispatcher.run()` 签名。  
仍通过 `hint` 桥接，但桥接内容不再只靠用户自由文本，而是拼接结构化片段：

```text
[local_ctf_assets]
challengePath=...
artifactPaths=...; ...
```

这样可以在保持最小改动的同时，把上游输入变成可持久化、可继承、可观测的 task truth。

## 设计取舍

### 为什么不直接改 dispatcher.run(...)

因为这轮主价值在于：

- 任务入口真值化
- task 生命周期继承
- detail / trace 可解释性

而不是马上重构 dispatcher contract。  
先把 ingress truth 固定住，后面再把 `hint` 桥升级成正式 `challenge_context` 参数会更稳。

## 验证口径

### RED

1. `POST /api/tasks` 持久化 `challengePath / artifactPaths`
2. `replay / retry` 继承这些字段
3. `_run_agent_task()` 调 CTF dispatcher 时，传入的 hint 中含结构化本地资产片段

### 回归

- `tests/unit/interface/test_web_server.py`
- `tests/unit/agents/test_ctf_dispatcher.py -k local_compose`

## 下一步

这轮完成后，下一条自然延伸主线是：

1. MCP ingress 也接受 `challengePath / artifactPaths`
2. 前端 New Task / Task Detail 直接展示这些字段
3. 再把 dispatcher bridge 从 `hint` 升级成显式 `challenge_context`
