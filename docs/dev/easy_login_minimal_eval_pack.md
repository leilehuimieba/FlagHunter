# easy_login 最小 Eval Pack

> 适用仓库：`D:\webstudy\FlagHunter`  
> 适用样本：`D:\webstudy\CTF\2026\CTF比赛题\easy_login`

## 1. 目标

这份 eval pack 只回答一个问题：

> **FlagHunter 当前是否已经具备“对 easy_login 做到可复跑、可区分能力层级、可防止假阳性”的最小验证集？**

它不是大而全 benchmark，也不是所有 CTF Web 题的统一标准。

---

## 2. 当前最重要的行为

按风险和回归价值排序，当前最值得盯的行为只有 4 个：

1. **本地资产辅助成功**
   - 当给出 challenge 目录或 zip 时，dispatcher 能利用本地资产闭环拿 flag。

2. **纯 runtime 成功**
   - 当不给本地资产，只给运行中的 URL 时，dispatcher 也应该能在 Docker localhost 场景下通过 `/visit -> sid -> /admin` 闭环。

3. **失败时保持 honest**
   - 没有足够 runtime 证据时，不应该 false verified，不应该把 source-only 猜测伪装成 runtime success。

4. **恢复路径稳定**
   - 关键链条中的单次 receive miss / collector 失败后，agent 不应永久卡死，至少要有一次最小恢复。

---

## 3. 最小场景集

### Scenario A — directory variant success

- **目的**
  - 验证 local asset ingress + challengePath 路径
- **输入**
  - `challenge_context = {"challengePath": "<easy_login dir>", "artifactPaths": []}`
- **期望**
  - `result.success == True`
  - `result.flag` 为真实 flag
- **对应测试**
  - `tests/integration/test_local_asset_eval_pack.py::test_eval_local_asset_directory_only_success`
  - `tests/integration/test_local_challenge_runner.py::test_local_challenge_runner_solves_easy_login_directory_variant`

### Scenario B — zip variant success

- **目的**
  - 验证 zip-only 本地资产入口
- **输入**
  - `challenge_context = {"challengePath": None, "artifactPaths": ["<zip>"]}`
- **期望**
  - `result.success == True`
  - `result.flag` 为真实 flag
- **对应测试**
  - `tests/integration/test_local_asset_eval_pack.py::test_eval_local_asset_zip_only_success`
  - `tests/integration/test_local_challenge_runner.py::test_local_challenge_runner_solves_easy_login_zip_variant`

### Scenario C — no asset honesty baseline

- **目的**
  - 验证没有本地资产时不会假装 verified
- **输入**
  - 无 `challenge_context`
- **期望**
  - `result.success == False`
  - `result.flag is None`
  - `result.reason` 非空
- **对应测试**
  - `tests/integration/test_local_asset_eval_pack.py::test_eval_no_local_asset_is_honest_not_false_verified`
  - `tests/integration/test_local_challenge_runner.py::test_local_challenge_runner_keeps_no_asset_easy_login_honest`

### Scenario D — runtime-only Docker localhost success

- **目的**
  - 验证 URL-only 模式在 Docker localhost 下的 `/visit` fallback 闭环
- **输入**
  - 仅目标 URL，无本地资产
- **期望**
  - `result.success == True`
  - `result.reason == "docker localhost visit fallback"`
- **对应测试**
  - `tests/integration/test_easy_login_runtime_only_docker_fallback.py::test_runtime_only_loopback_target_falls_back_to_container_local_probe`
  - `tests/integration/test_local_challenge_runner.py::test_local_challenge_runner_solves_easy_login_runtime_only_variant`

### Scenario E — recovery path

- **目的**
  - 验证 collector 首次 miss 后的最小恢复
- **输入**
  - easy_login 全链假 runtime
- **期望**
  - 首次 miss 后重新触发 `/visit`
  - 最终仍能拿到 flag
- **对应测试**
  - `tests/integration/test_easy_login_retry_stability.py::test_easy_login_collector_first_receive_failure_recovers`

---

## 4. 评分口径

### Pass

满足以下条件：

- Scenario A/B 至少一条成功
- Scenario C 保持 honest
- Scenario D 成功
- Scenario E 成功

### Concerns

出现以下情况之一：

- 只能 directory 成功，zip 失败
- 只能 local asset 成功，runtime-only 失败
- 能拿到 flag，但 reason / evidence path 与实际链路不一致

### Fail

出现以下情况之一：

- no-asset 场景 false verified
- runtime-only 失效回归
- collector fail 后无恢复
- 真实 easy_login URL-only smoke 不能闭环

---

## 5. Inspectable artifacts

建议重点看：

1. `SolveResult.success / flag / reason`
2. `chain_used`
3. `dispatcher.state.local_challenge_auto_verify`
4. `dispatcher.state.runtime_flags / verified_flags`
5. notes 中是否落了 `sid`
6. retry 场景是否真的发生了二次 `/visit`

---

## 6. 建议 rerun 命令

### 代码级最小回归

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/integration/test_easy_login_runtime_only_docker_fallback.py `
  tests/integration/test_local_asset_eval_pack.py `
  tests/integration/test_local_challenge_runner.py `
  tests/integration/test_easy_login_retry_stability.py -q
```

### 真实 URL-only smoke

确保 `easy_login` Docker 环境已启动后，运行：

```powershell
.\.venv\Scripts\python.exe D:\webstudy\FlagHunter\tmp\eval_easy_login_runtime_only_smoke.py
```

期望关键输出：

- `"success": true`
- `"reason": "docker localhost visit fallback"`

---

## 7. 当前结论

截至本轮收口，`easy_login` 已经不再只是“源码方向判断”样本，而是具备了下面 3 个独立验收面：

1. **local asset assisted success**
2. **runtime-only Docker localhost success**
3. **honesty + retry recovery**

这就是当前 FlagHunter 最小但真实有效的 easy_login eval pack。
