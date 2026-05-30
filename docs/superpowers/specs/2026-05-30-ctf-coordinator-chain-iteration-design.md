# CTFCoordinator chain iteration prep / missing-tools recovery contract extraction 最小设计

日期：2026-05-30

## 目标

在 `hypothesis contract` 已完成的基础上，把 chain loop 内每轮迭代开头的准备逻辑，以及 `missing-tools` 的恢复决策逻辑，从 dispatcher 继续往 coordinator helper 吸。

这轮只抽两件事：

1. per-chain iteration prep contract
2. missing-tools recovery contract

## 这轮不做什么

仍然先不抽：

- loop 的成功/失败后半段
- wrong-flag feedback
- after_chain recovery
- finalize 的一般路径

## 最小合同

### 合同 1：iteration prep

coordinator helper 必须负责装配：

- `active_hypothesis`
- `strategy`
- `capability_primitive`
- `capability_choice`
- `experiment`
- `alternatives`

### 合同 2：missing-tools recovery

coordinator helper 必须负责：

- `_store_missing_tools(...)`
- `recovery_controller.on_missing_tools(...)`
- `_record_recovery_decision(...)`
- `switch_chain / stop_missing_tools` 分支决策

## 最小实现策略

新增两个 helper：

- `CTFCoordinator._prepare_chain_iteration_contract(...)`
- `CTFCoordinator._apply_missing_tools_recovery_contract(...)`

dispatcher loop 继续保留，但改为调用 helper。

## 验收

新增单测验证：

1. iteration prep helper 能正确装配 hypothesis / strategy / capability / experiment / alternatives
2. missing-tools helper 在 `switch_chain` 时返回新的 chain_order 与 chain_index

并补窄回归：

- `tests/unit/agents/test_ctf_coordinator.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/integration/test_backup_node_app_candidate_eval.py`
- `tests/integration/test_ctf_dispatcher_backup_acceptance.py`
