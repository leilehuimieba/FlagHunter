# CTFCoordinator progress evaluation / after-chain recovery contract extraction 最小设计

日期：2026-05-30

## 目标

在 `chain iteration prep / missing-tools recovery contract` 已完成的基础上，把 loop 后半段的进展评估与链后恢复决策，从 dispatcher 继续往 coordinator helper 吸。

这轮只抽两件事：

1. progress evaluation contract
2. after-chain recovery contract

## 这轮不做什么

仍然先不抽：

- wrong-flag feedback
- terminal success 分支
- finalize 收尾

## 最小合同

### 合同 1：progress evaluation

coordinator helper 负责：

- 计算 `progress_delta`
- 计算 `effective_progress`
- progress / no-progress 下调用：
  - `state.mark_progress` / `state.mark_no_progress`
  - `record_experiment_feedback(...)`
  - `record_interpretation(...)`
  - `evaluate_experiment_result(...)`

### 合同 2：after-chain recovery

coordinator helper 负责：

- `recovery_controller.after_chain(...)`
- `_record_recovery_decision(...)`
- `_emit(...)`
- 处理：
  - `explore_agenda`
  - `switch_chain`
  - `should_stop`

## 最小实现策略

新增两个 helper：

- `CTFCoordinator._apply_progress_evaluation_contract(...)`
- `CTFCoordinator._apply_after_chain_recovery_contract(...)`

dispatcher loop 继续保留，但改为调用 helper。

## 验收

新增单测验证：

1. progress helper 在有效进展时正确写 feedback / interpretation，并返回 `effective_progress=True`
2. after-chain helper 在 `switch_chain` 时返回新的 chain_order，在 `should_stop` 时返回 finalized result

并补窄回归：

- `tests/unit/agents/test_ctf_coordinator.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/integration/test_backup_node_app_candidate_eval.py`
- `tests/integration/test_ctf_dispatcher_backup_acceptance.py`
