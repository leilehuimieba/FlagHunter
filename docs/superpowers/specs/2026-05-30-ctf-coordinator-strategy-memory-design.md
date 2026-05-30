# CTFCoordinator strategy memory audit contract extraction 最小设计

日期：2026-05-30

## 目标

在 `post-recon decision contract` 已完成的基础上，把进入 hypothesis / chain loop 之前的 strategy memory audit 合同继续从 dispatcher 往 coordinator 吸。

这轮只抽五件事：

1. `build_fingerprint`
2. `query`
3. `record_query_usage`
4. `compute_hypothesis_adjustments`
5. `strategy_memory_audit` meta reasoning

## 这轮不做什么

仍然先不抽：

- hypothesis generate
- chain order choose
- strategy_memory outcome audit
- chain execution loop
- finalize 的一般路径

## 最小合同

### 合同 1

coordinator 必须在 inner run 之前完成 strategy memory audit contract。

### 合同 2

若当前 dispatcher 具备 `strategy_memory` 且 `state` 已建立：

- coordinator 负责生成 `_current_fingerprint`
- coordinator 负责查询 memory matches
- coordinator 负责回填 `_memory_match_ids`
- 若有命中，负责 `record_query_usage(...)`
- coordinator 负责写入 `state.hypothesis_memory_adjustments`
- 若有命中，负责追加 `strategy_memory_audit`

### 合同 3

inner run 收到：

- `_strategy_memory_ready=True`

并直接消费已准备好的：

- `dispatcher._current_fingerprint`
- `dispatcher._memory_match_ids`
- `state.hypothesis_memory_adjustments`

## 最小实现策略

继续沿用内部 seam：

- `dispatcher.run(..., _strategy_memory_ready=True, ...)`

coordinator 负责：

- 调 `strategy_memory.build_fingerprint(...)`
- 调 `strategy_memory.query(...)`
- 命中后调 `strategy_memory.record_query_usage(...)`
- 调 `strategy_memory.compute_hypothesis_adjustments(...)`
- 必要时写 `strategy_memory_audit`

dispatcher 的 `_run_bootstrapped(...)` 负责：

- 若 `_strategy_memory_ready=False`，走原 fallback 路径
- 若 `_strategy_memory_ready=True`，直接进入 hypothesis / chain loop 前的下一段逻辑

## 验收

新增单测验证：

1. coordinator 在 inner run 前完成 strategy memory audit contract
2. inner run 收到 `_strategy_memory_ready=True`
3. dispatcher 上的 fingerprint / memory ids / hypothesis adjustments 已就位
4. 命中时已写 `strategy_memory_audit`

并补窄回归：

- `tests/unit/agents/test_ctf_coordinator.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/integration/test_backup_node_app_candidate_eval.py`
- `tests/integration/test_ctf_dispatcher_backup_acceptance.py`
