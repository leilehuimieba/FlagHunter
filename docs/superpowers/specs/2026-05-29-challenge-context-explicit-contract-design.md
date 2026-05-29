# Challenge Context Explicit Contract Design

日期：2026-05-29

## 目标

把本地 CTF 资产从字符串 hint bridge 升级为显式上下文合同，避免 `CTFTaskDispatcher` 只能通过解析：

```text
[local_ctf_assets]
challengePath=...
artifactPaths=...
```

来拿到本地题目目录或附件包。

本轮只做最小收口：

- `CTFTaskDispatcher.run(...)` 新增 `challenge_context`
- CLI CTF 入口显式传递 `challenge_context`
- Web Console CTF 路径显式传递 `challenge_context`
- 旧 hint bridge 保留兼容，不移除

## 最小合同

```json
{
  "challengePath": "string | null",
  "artifactPaths": ["string", "..."]
}
```

语义：

- `challengePath`
  - 优先表示本地题目根目录
  - 若存在，dispatcher 优先把它当成 challenge root 候选
- `artifactPaths`
  - 表示与题目相关的本地附件路径
  - 可包含 `docker-compose.yml`、源码文件、zip 包等

## 解析优先级

dispatcher 解析 challenge root 时按以下顺序工作：

1. `challenge_context.challengePath`
2. `challenge_context.artifactPaths`
3. hint 中的 `[local_ctf_assets]` 结构化块
4. hint 自由文本里的路径猜测

这保证：

- 新入口走显式 truth source
- 旧入口和旧测试仍可通过 hint 兼容运行

## Auto-verify 关联

`local_challenge_auto_verify` 的判定也同步改为基于：

- `challenge_context` 可解析出本地 challenge root
- 或 hint fallback 可解析出本地 challenge root

这样 directory-only / zip-only 的 local challenge runtime verified 逻辑保持不变。

## 本轮不做

- 不改 MCP ingress 调度链
- 不移除 `[local_ctf_assets]` hint bridge
- 不扩展更多 artifact 类型（仍只收 zip 自动解包）
- 不改 UI 展示合同

## 验收

本轮最小验收关注：

1. dispatcher 可直接从 `challenge_context` 解析目录 / zip challenge root
2. CLI CTF 路径把结构化本地资产显式透传给 dispatcher
3. Web Console CTF 路径把结构化本地资产显式透传给 dispatcher
4. 3-case local asset eval pack 继续保持：
   - directory-only success
   - zip-only success
   - no-local-asset honesty
