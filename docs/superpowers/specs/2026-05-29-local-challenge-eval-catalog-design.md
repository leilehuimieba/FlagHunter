# Local Challenge Eval Catalog 最小设计

日期：2026-05-29  
仓库：`D:\webstudy\FlagHunter`

---

## 目标

把已经能跑通的本地题评测，从“散落在单个 integration test 里的硬编码路径”收成一个最小样本 catalog。

本轮只做：

1. 定义本地 challenge sample 元数据
2. 至少纳入 1 个 active 样本
3. 至少纳入 1 个 candidate 样本
4. 让现有 `local_asset_eval_pack` 开始消费 catalog，而不是继续硬编码

---

## 为什么值得做

现在仓库虽然已经有：

- `easy_login` local asset eval

但还缺一层统一表达：

- 哪些题是正式样本
- 题目路径在哪里
- 最小提示是什么
- 预期结果等级是什么
- directory / zip 两种 challenge_context 如何构造

如果没有这一层，后面很难稳定扩到第 2、第 3 个本地题样本。

---

## 最小模块落点

新增：

- `D:\webstudy\FlagHunter\tests\integration\local_challenge_catalog.py`

只放测试资产，不放生产代码。

原因：

- 当前目标是评测组织，不是产品功能
- 先在 tests 里稳定形状更轻

---

## 最小数据形状

```python
LocalChallengeSample(
    key="easy_login",
    status="active",
    mode="ctf",
    mode_subtype="web",
    challenge_path=Path(...),
    target="http://127.0.0.1:3000",
    minimal_prompt="...",
    expected_outcome="verified_flag",
)
```

---

## 本轮样本

### 1. `easy_login`

状态：
- `active`

原因：
- 已有本地目录
- 已有 local asset eval
- 已有完整 exploit / acceptance / retry / e2e 测试基础

目标：
- 作为第一个正式本地题样本

### 2. `backup_node_app`

状态：
- `candidate`

原因：
- 本地确有 `backup.zip`
- 但当前还没有正式的“local-only solve baseline”
- 更适合作为 honesty / source-only 候选样本

目标：
- 先进入 catalog，后续再决定是否做成 active eval

---

## 最小接口

### 1. `list_local_challenge_samples()`

返回所有样本。

### 2. `get_local_challenge_sample(key)`

按 key 取样本。

### 3. `build_challenge_context(sample, variant=...)`

当前支持：

- `directory`
- `zip`

用于统一生成：

```json
{
  "challengePath": "...",
  "artifactPaths": []
}
```

或：

```json
{
  "challengePath": null,
  "artifactPaths": ["...zip"]
}
```

---

## 最小提示约束

catalog 中的 `minimal_prompt` 需要遵守：

1. 不直接泄露 exploit 链
2. 不直接给出 flag
3. 不把“预期结果”写成解法提示

例如：

- 对 `easy_login` 不应直接写 `/login -> /visit -> /admin`
- 对 `backup_node_app` 不应直接写 `www.zip`

---

## 验证口径

本轮通过标准：

1. catalog 合同测试通过
2. `easy_login` active 样本路径存在
3. `backup_node_app` candidate 样本路径存在
4. `local_asset_eval_pack` 改为消费 catalog 后仍然全绿

