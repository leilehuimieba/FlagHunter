# CTFCoordinator post-recon decision contract extraction 最小设计

日期：2026-05-30

## 目标

在 `recon contract` 已完成的基础上，把 recon 之后、进入 strategy memory / hypothesis / chain loop 之前的第一段决策合同继续从 dispatcher 往 coordinator 吸。

这轮只抽四件事：

1. `platform alignment`
2. `already solved` fast exit
3. `direct flag on rendered page` fast path
4. `detected_type` 的初始落点

## 这轮不做什么

仍然先不抽：

- strategy memory fingerprint / query
- hypothesis generate / rank
- chain order
- chain execution loop
- finalize 的一般路径

## 最小合同

### 合同 1

coordinator 必须在 inner run 之前完成 post-recon decision contract。

### 合同 2

若平台对齐结果表明题目已解：

- coordinator 负责追加 `platform_challenge_alignment`
- 必要时回填 `submit_challenge_id`
- 直接 honest early-stop
- 不进入 inner run

### 合同 3

若渲染页面直接提取到 flag 且 `_observe_flag(...)` 决策为 `verified`：

- coordinator 直接以 `recon` 链路结束
- 不进入 inner run

### 合同 4

若未触发 early-stop，则 coordinator 必须先确定初始 `detected_type`，并把结果传给 inner run。

inner run 收到：

- `_post_recon_ready=True`
- `_page_features=<recon 输出>`
- `_detected_type=<初始类型>`

## 最小实现策略

继续沿用内部 seam：

- `dispatcher.run(..., _post_recon_ready=True, _page_features=page_features, _detected_type=detected_type, ...)`

coordinator 负责：

- `alignment = _align_platform_challenge(target, page_features)`
- 记录 `platform_challenge_alignment`
- `already solved` fast exit
- `_extract_flag(page_features["content"])`
- `_observe_flag(...)` 的 direct-flag fast path
- `detect_type(...)` 或显式 `requested_type` 的初始类型确定

dispatcher 的 `_run_bootstrapped(...)` 负责：

- 若 `_post_recon_ready=False`，走原 fallback 路径
- 若 `_post_recon_ready=True`，直接消费 `_detected_type`

## 验收

新增单测验证：

1. coordinator 在 inner run 前完成 post-recon contract，并把 `_post_recon_ready` / `_detected_type` 传入 inner run
2. `already solved` fast exit 由 coordinator 触发，不进入 inner run
3. 页面直接命中旗帜且验证通过时，由 coordinator 直接结束，不进入 inner run

并补窄回归：

- `tests/unit/agents/test_ctf_coordinator.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/integration/test_backup_node_app_candidate_eval.py`
- `tests/integration/test_ctf_dispatcher_backup_acceptance.py`
