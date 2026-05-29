# CTFCoordinator façade 第一刀最小设计

日期：2026-05-29

## 目标

在不改动既有 CTF 利用行为的前提下，把 `CTFTaskDispatcher` 的入口职责先收成一个明确的 coordinator seam。

这一刀只解决：

1. `run()` 不再直接作为唯一 orchestration 入口
2. coordinator 成为后续拆分主循环的稳定插点
3. 保持现有 acceptance / local eval 行为不变

## 这轮不做什么

- 不抽全部 exploit helper
- 不重写 recovery / verifier
- 不拆双进程
- 不改变对外调用 contract

## 最小合同

### 合同 1：dispatcher façade

`CTFTaskDispatcher.run()` 的职责变成：

- 接收现有 public 参数
- 先把执行委托给 `CTFCoordinator.execute(...)`

### 合同 2：coordinator re-entry path

`CTFCoordinator.execute(...)` 必须：

- 回调 dispatcher 的非再委托路径
- 避免 coordinator → dispatcher.run() → coordinator 无限递归

### 合同 3：行为不变

既有：

- dispatcher unit tests
- backup honesty acceptance
- local asset / local challenge runner

都不应回退。

## 最小实现策略

第一刀不做大搬家，采用：

- 新增 `pentestagent/agents/pa_agent/coordinator.py`
- `dispatcher.run(..., _delegate_to_coordinator=True)` 作为 façade
- `CTFCoordinator.execute(...)` 调用
  `dispatcher.run(..., _delegate_to_coordinator=False)`

这样可以：

- 立刻获得 coordinator 边界
- 不需要一次性迁移 400+ 行 orchestration 主体
- 为下一轮真正抽主循环保留稳定入口

## 验收

新增单测：

- `tests/unit/agents/test_ctf_coordinator.py`

至少验证：

1. dispatcher.run 会委托给 coordinator
2. coordinator.execute 会调用 dispatcher 的非再委托路径

并补一轮窄回归：

- `tests/unit/agents/test_ctf_coordinator.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/integration/test_backup_node_app_candidate_eval.py`
- `tests/integration/test_ctf_dispatcher_backup_acceptance.py`

## 预期收益

这轮不是“拆完 dispatcher”，而是把后续拆分所需的**入口控制面**先立起来。

后续如果继续推进，可以在 coordinator 内逐步吸收：

- 初始化 / bootstrap
- recon phase
- chain loop orchestration
- finalize / stop contract
