# Local Asset Eval Pack — Minimal Design

## 背景

当前系统已经具备两个真实可用输入形态：

1. directory-only
2. zip-only

但如果没有一组稳定、可复跑的小型 eval，用后续 agent 链路改动时很容易出现：

- 功能回退
- 假阳性成功
- honesty 边界漂移

## 目标

建立一个最小但有效的本地资产 eval pack，覆盖：

1. directory-only success baseline
2. zip-only success baseline
3. no-local-asset honesty baseline

## 非目标

本轮不做：

- 大规模 benchmark
- 多题型全面覆盖
- 真实 LLM 在线评测矩阵
- 跨平台 submit 场景评测

## 场景设计

### Case 1: directory-only success
- 输入：`challengePath=<easy_login目录>`
- 期望：`success=True` 且拿到 verified flag

### Case 2: zip-only success
- 输入：`artifactPaths=[easy_login.zip]`
- 期望：`success=True` 且拿到 verified flag

### Case 3: no-local-asset honesty
- 输入：只给 target / goal，不给本地资产
- 期望：
  - `success=False`
  - `flag is None`
  - `verified_flags == []`
  - stop reason 不应伪装成 flag success

## 判断规则

- 前两项用于检测“真实 solve 主链是否回退”
- 第三项用于检测“系统是否出现假阳性 / 不诚实成功”

## 回归价值

这组 eval 可以在后续下列改动后复跑：

- challenge_context 显式化
- verifier policy 调整
- dispatcher exploit 链调整
- CLI / Web / MCP ingress 改动

## 下一步

这轮完成后，可以继续补：

1. 只给题目链接的 honesty / direction case
2. 目录输入 + 少提示 case
3. 另一道真实题的对照样本
