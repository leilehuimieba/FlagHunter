# CTF Dispatcher Local Asset Parsing Contract — Minimal Design

## 背景

Web / MCP 已经把本地题目资产结构化成：

- `challengePath`
- `artifactPaths`

并通过 hint bridge 传给 CTF dispatcher：

```text
[local_ctf_assets]
challengePath=...
artifactPaths=...; ...
```

但 dispatcher 侧此前仍主要依赖“从 hint 文本里猜路径”，对结构化 block 没有正式解析合同。

## 目标

让 dispatcher 对 `[local_ctf_assets]` 有最小显式解析能力：

1. 能解析 `challengePath`
2. 能解析分号分隔的 `artifactPaths`
3. `challengePath` 缺失时，可从 `artifactPaths` 中的 `docker-compose.yml` 反推出 challenge root

## 非目标

本轮不做：

- 修改 `CTFTaskDispatcher.run()` 公共签名
- 引入新的跨层 dataclass
- 移除 Web / MCP 当前 hint bridge
- 做 artifact 文件类型的全面识别

## 最小设计

### 新 helper

新增：

- `_extract_local_ctf_assets_from_hint(hint)`

返回：

- `challengePath`
- `artifactPaths`

### challenge root 解析顺序

`_extract_local_challenge_root_from_hint(hint)` 调整为：

1. 先读结构化 `challengePath`
2. 再读结构化 `artifactPaths`
3. 最后才回退到原有自由文本路径猜测

## 设计取舍

这一步不直接替换 hint bridge，而是先把 dispatcher 端的消费收成明确 helper：

- 改动小
- 兼容现有 Web / MCP 行为
- 立即提升“只有 artifactPaths 也能工作”的稳定性

## 验证口径

1. 能从 `[local_ctf_assets]` block 提取 `challengePath / artifactPaths`
2. 结构化 `challengePath` 优先于自由文本中的干扰路径
3. 只有结构化 `artifactPaths` 时，仍可通过 `docker-compose.yml` 找到 challenge root
4. 既有 `local compose pivot` 测试继续通过

## 下一步

这轮完成后，后续更值得做的是：

1. 将 Web / MCP / CLI 的本地资产桥接进一步升级为显式 `challenge_context`
2. 让 dispatcher 的 misc / artifact 题型也消费同一结构化资产合同
