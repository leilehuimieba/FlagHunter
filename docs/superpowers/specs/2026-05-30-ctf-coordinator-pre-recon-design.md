# CTFCoordinator pre-recon contract extraction 最小设计

日期：2026-05-30

## 目标

在 `bootstrap` 与 `run-start` 已完成抽取后，继续把 `_phase_recon()` 之前的准备合同从 dispatcher 往 coordinator 吸。

这轮只抽四项：

1. `_load_rejected_flags()`
2. `_snapshot_platform_context(target)`
3. `capability_registry.full_check()`
4. `state.capabilities = capability_registry.to_dict()`

## 这轮不做什么

仍然先不抽：

- `_emit("[CTF dispatcher] target=...")`
- `_phase_recon()`
- alignment
- chain loop
- finalize

## 最小合同

### 合同 1
coordinator 必须在 inner run 之前完成 pre-recon contract。

### 合同 2
inner run 收到的 dispatcher state 必须已经带有：

- rejected flags 已加载
- platform snapshot 已完成
- capability check 已完成
- state.capabilities 已就位

### 合同 3
dispatcher continuation 在 `_pre_recon_ready=True` 时，不再重复做这四件事。

## 最小实现策略

继续沿用内部 seam：

- `dispatcher.run(..., _pre_recon_ready=True, ...)`

coordinator 负责：

- 调 `_load_rejected_flags()`
- await `_snapshot_platform_context(target)`
- await `capability_registry.full_check()`
- 回填 `state.capabilities`

dispatcher 的 `_run_bootstrapped(...)` 负责：

- 若 `_pre_recon_ready=False`，走原 fallback 路径
- 若 `_pre_recon_ready=True`，直接进入 recon

## 验收

新增单测验证：

1. coordinator 在 inner run 前完成 pre-recon contract
2. inner run 收到 `_pre_recon_ready=True`
3. capability/state payload truthful

并补窄回归：

- `tests/unit/agents/test_ctf_coordinator.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/integration/test_backup_node_app_candidate_eval.py`
- `tests/integration/test_ctf_dispatcher_backup_acceptance.py`
