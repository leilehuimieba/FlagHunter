# CTFCoordinator bootstrap extraction 最小设计

日期：2026-05-30

## 目标

在已存在的 `CTFCoordinator façade seam` 基础上，再向前推进一小步：

- 不再让 coordinator 只是“转发器”
- 让 coordinator 开始接管 `run()` 的 bootstrap / setup 前半段

## 这轮只抽什么

只抽这些 **运行前置初始化职责**：

1. public ingress normalization
2. `_notes_log` 重置
3. `challenge_context` 归一化并挂到 dispatcher
4. session ledger 初始化
5. artifact registry 初始化
6. `CTFState(target, goal)` 初始化
7. checkpoint store 初始化
8. `_current_fingerprint / _memory_match_ids / _pending_wrong_flag_feedback / _exhausted_visit_url_targets` 重置
9. `reasoning_layer.degradation_events` 清空
10. `submit_profile` 应用
11. failover monitor 启动

## 这轮不抽什么

以下仍留在 dispatcher 的 bootstrapped continuation 里：

- local challenge auto verify 判定
- dispatcher_started ledger event
- dispatcher_started checkpoint event
- platform snapshot
- capability full check
- phase recon
- alignment / chain loop / finalize

## 最小合同

### 合同 1
`CTFCoordinator.execute(...)` 在调用 inner run 之前，必须先完成 bootstrap。

### 合同 2
bootstrap 完成后，coordinator 仍通过 dispatcher 的非再委托路径进入后续逻辑。

### 合同 3
dispatcher 后续逻辑看到的是**已初始化状态**，而不是自己再做第一轮 setup。

## 最小实现策略

采用最小隐式内部参数：

- `dispatcher.run(..., _delegate_to_coordinator=False, _bootstrap_ready=True, _requested_type=...)`

这样可以：

- 保持 coordinator → dispatcher 的 seam 不变
- 又允许 dispatcher 在 `_bootstrap_ready=True` 时跳过已迁出的 setup 逻辑

## 验收

单测重点验证：

1. coordinator 在 inner run 之前完成 bootstrap
2. inner run 收到 `_bootstrap_ready=True`
3. target / goal / hint / requested_type 已归一化
4. dispatcher 的 run-time state / registry / checkpoint 初始化已就位

并补窄回归：

- `tests/unit/agents/test_ctf_coordinator.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/integration/test_backup_node_app_candidate_eval.py`
- `tests/integration/test_ctf_dispatcher_backup_acceptance.py`
