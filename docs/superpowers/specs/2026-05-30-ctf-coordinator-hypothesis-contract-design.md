# CTFCoordinator hypothesis generation / chain order contract extraction 最小设计

日期：2026-05-30

## 目标

在 `strategy memory audit contract` 已完成的基础上，把进入 chain loop 之前的 hypothesis generation / chain order 合同继续从 dispatcher 往 coordinator 吸。

这轮只抽两件事：

1. `hypothesis_engine.generate(state)`
2. `choose_chain_order(state)`

## 这轮不做什么

仍然先不抽：

- chain loop 执行
- recovery 内部链路重排
- outcome audit
- finalize 的一般路径

## 最小合同

### 合同 1

coordinator 必须在 inner run 之前完成 hypothesis contract。

### 合同 2

若 `state` 与 `hypothesis_engine` 可用：

- coordinator 负责生成 `state.hypotheses`
- coordinator 负责生成初始 `chain_order`

### 合同 3

inner run 收到：

- `_hypotheses_ready=True`
- `_chain_order=<初始链路顺序>`

并直接消费：

- `state.hypotheses`
- `_chain_order`

## 最小实现策略

继续沿用内部 seam：

- `dispatcher.run(..., _hypotheses_ready=True, _chain_order=chain_order, ...)`

coordinator 负责：

- `dispatcher.hypothesis_engine.generate(state)`
- `dispatcher.hypothesis_engine.choose_chain_order(state)`
- 初始 `chain_order` 去重

dispatcher 的 `_run_bootstrapped(...)` 负责：

- 若 `_hypotheses_ready=False`，走原 fallback 路径
- 若 `_hypotheses_ready=True`，直接进入 chain loop

## 验收

新增单测验证：

1. coordinator 在 inner run 前完成 hypothesis contract
2. inner run 收到 `_hypotheses_ready=True` 与 `_chain_order`
3. `state.hypotheses` 已就位

并补窄回归：

- `tests/unit/agents/test_ctf_coordinator.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/integration/test_backup_node_app_candidate_eval.py`
- `tests/integration/test_ctf_dispatcher_backup_acceptance.py`
