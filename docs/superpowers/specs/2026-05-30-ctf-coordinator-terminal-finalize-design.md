# CTFCoordinator wrong-flag / terminal success / final recovery contract extraction 最小设计

日期：2026-05-30

## 目标

在 `progress evaluation / after-chain recovery contract` 已完成的基础上，把 loop 剩余三个主要退出口，从 dispatcher 继续往 coordinator helper 吸。

这轮只抽三件事：

1. wrong-flag early-stop contract
2. terminal success contract
3. final recovery decision contract

## 这轮不做什么

仍然先不抽：

- `_finalize_solve_result(...)` 内部实现
- strategy memory session entry / outcome audit 的 finalize 细节
- stop report 生成细节

## 最小合同

### 合同 1：wrong-flag early-stop

coordinator helper 负责：

- 检查 `not outcome.flag and _pending_wrong_flag_feedback`
- 回填 `result.notes / result.reason / state.stop_reason`
- 写 retrospective
- 调 `_finalize_solve_result(...)`

### 合同 2：terminal success

coordinator helper 负责：

- 回填 `result.success / result.flag / result.reason`
- `state.mark_progress(...)`
- terminal feedback / interpretation / evaluation
- 调 `_finalize_solve_result(...)`

### 合同 3：final recovery decision

coordinator helper 负责：

- `recovery_controller.finalize(...)`
- `_record_recovery_decision(...)`
- `_emit(...)`
- 回填 `result.notes / result.reason / state.stop_reason`
- 写 retrospective
- 调 `_finalize_solve_result(...)`

## 最小实现策略

新增三个 helper：

- `CTFCoordinator._apply_wrong_flag_early_stop_contract(...)`
- `CTFCoordinator._apply_terminal_success_contract(...)`
- `CTFCoordinator._apply_final_recovery_contract(...)`

dispatcher 主循环继续保留，但改为调用 helper。

## 验收

新增单测验证：

1. wrong-flag helper 返回 finalized result，并写回 `state.stop_reason`
2. terminal success helper 返回 finalized result，并写 terminal feedback / interpretation
3. final recovery helper 返回 finalized result，并写 recovery decision

并补窄回归：

- `tests/unit/agents/test_ctf_coordinator.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/integration/test_backup_node_app_candidate_eval.py`
- `tests/integration/test_ctf_dispatcher_backup_acceptance.py`
