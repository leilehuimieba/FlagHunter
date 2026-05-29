# Local Challenge Runtime Auto-Verify — Minimal Design

## 背景

在 Web / MCP / CLI 都已经能把本地题目目录与材料路径桥接到 CTF dispatcher 之后，新的主缺口变成了验证层：

- dispatcher 已能在本地 challenge 上拿到强 runtime flag
- 但若没有 submit channel / operator confirmation，结果仍可能停在 `runtime but not verified`

这会让“本地离线题目目录 -> agent 自主分析 -> 直接拿 flag”链路停在最后一步。

## 目标

当且仅当满足下面条件时，让 verifier 自动把 runtime flag 收成 verified：

1. 当前任务存在本地 challenge 上下文
2. 证据属于强 runtime evidence
3. 当前没有平台提交通道

## 非目标

本轮不做：

- 覆盖弱 runtime 证据
- 覆盖在线平台 submit 路径
- 新增 challenge_context dataclass
- 修改 dispatcher 公共 `run()` 签名

## 最小设计

### state 标记

`CTFState` 新增：

- `local_challenge_auto_verify: bool = False`

### dispatcher 赋值

`CTFTaskDispatcher.run()` 在启动阶段：

- 若 hint 中可解析出真实本地 challenge root
- 则设置 `state.local_challenge_auto_verify = True`

### verifier 规则

在 runtime flag 分支中，若满足：

- `state.local_challenge_auto_verify == True`
- `runtime_strength == strong`
- `not self._has_submit_channel(state)`

则直接：

- `decision = verified`
- `verification_path = local_challenge_runtime`

### 安全边界

这一步不会自动放过：

- 弱证据首页 echo
- 已有平台提交通道的题目
- source-only candidate

## 验证口径

1. verifier 能对本地 challenge 的强 runtime flag 自动 verified
2. verifier 不会对本地 challenge 的弱 runtime flag 自动 verified
3. dispatcher 在带 `challengePath` 的 hint 下能把 runtime pending 收口成 success
4. 真实 CLI `easy_login` headless 运行能输出 verified flag

## 下一步

这轮完成后，更值得继续的是：

1. 将 Web / CLI / TUI 对本地 challenge 的 verification policy 统一文案化
2. 把 `challenge_context` 从 hint bridge 升级为显式结构
3. 用压缩包 / 目录输入补一轮更贴近真实使用方式的 eval
