# CTFCoordinator recon contract extraction 最小设计

日期：2026-05-30

## 目标

在 `pre-recon contract` 已完成的基础上，把真正进入主循环前的 recon 合同继续从 dispatcher 往 coordinator 吸。

这轮只抽三件事：

1. `page_features = await _phase_recon(target)`
2. `_ingest_local_challenge_artifacts(target)`
3. 空侦察 + `recon_missing_tools` 的最小 honest early-stop

## 这轮不做什么

仍然先不抽：

- direct-flag fast path
- alignment
- type detect
- chain loop
- finalize 的一般路径

## 最小合同

### 合同 1
coordinator 必须在 inner run 之前完成 recon contract。

### 合同 2
inner run 收到：

- `_recon_ready=True`
- `_page_features=<phase_recon 输出>`

### 合同 3
若 `page_features` 没有 html/content/forms/endpoints，且存在 `recon_missing_tools`，
coordinator 必须直接 honest early-stop，不再进入 inner run。

## 最小实现策略

继续沿用内部 seam：

- `dispatcher.run(..., _recon_ready=True, _page_features=page_features, ...)`

coordinator 负责：

- await `_phase_recon(target)`
- `_ingest_local_challenge_artifacts(target)`
- 检查空侦察 + missing_tools
- 必要时调用：
  - `_store_missing_tools(...)`
  - `_finalize_solve_result(...)`

dispatcher 的 `_run_bootstrapped(...)` 负责：

- 若 `_recon_ready=False`，走原 fallback 路径
- 若 `_recon_ready=True`，直接消费 `_page_features`

## 验收

新增单测验证：

1. coordinator 在 inner run 前完成 recon contract
2. inner run 收到 `_recon_ready=True` 与 `_page_features`
3. 空侦察 missing-tools 时不会进入 inner run，而是直接 honest early-stop

并补窄回归：

- `tests/unit/agents/test_ctf_coordinator.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/integration/test_backup_node_app_candidate_eval.py`
- `tests/integration/test_ctf_dispatcher_backup_acceptance.py`
