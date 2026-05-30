# CTFCoordinator run-start contract extraction 最小设计

日期：2026-05-30

## 目标

在 `bootstrap extraction` 已完成的基础上，再抽 dispatcher continuation 头部的“任务开始瞬间合同”。

这轮只收这三项：

1. `local_challenge_auto_verify` 判定
2. `dispatcher_started` session ledger 事件
3. `dispatcher_started` checkpoint 写入

## 这轮不做什么

仍然先不抽：

- `_emit("[CTF dispatcher] target=...")`
- `_load_rejected_flags()`
- `_snapshot_platform_context()`
- `capability_registry.full_check()`
- `_phase_recon()`
- alignment / chain loop / finalize

## 最小合同

### 合同 1
`CTFCoordinator.execute(...)` 在 inner run 之前，必须完成 run-start contract。

### 合同 2
inner run 收到的 dispatcher state 必须已经带有正确的：

- `local_challenge_auto_verify`
- run-start ledger event
- run-start checkpoint

### 合同 3
dispatcher continuation 在 `_run_started=True` 时，不再重复做这三件事。

## 最小实现策略

继续沿用内部 seam：

- `dispatcher.run(..., _run_started=True, ...)`

coordinator 负责：

- 调 `_extract_local_challenge_root(...)`
- 更新 `state.local_challenge_auto_verify`
- 写 `dispatcher_started` ledger event
- 写 `dispatcher_started` checkpoint

dispatcher 的 `_run_bootstrapped(...)` 负责：

- 若 `_run_started=False`，走原 fallback 路径
- 若 `_run_started=True`，直接继续后半段

## 验收

新增单测验证：

1. coordinator 在 inner run 前完成 run-start contract
2. inner run 收到 `_run_started=True`
3. local challenge auto verify 判定正确
4. recorded event / checkpoint payload truthful

并补窄回归：

- `tests/unit/agents/test_ctf_coordinator.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/integration/test_backup_node_app_candidate_eval.py`
- `tests/integration/test_ctf_dispatcher_backup_acceptance.py`
