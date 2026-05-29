# Local Challenge Active Sample Runner 最小设计

日期：2026-05-29  
仓库：`D:\webstudy\FlagHunter`

---

## 目标

在已有：

- local challenge catalog
- local asset eval pack

之后，把 **active 样本的执行逻辑** 收成一个最小 runner helper，而不是继续散落在单个 test 文件里。

本轮只做：

1. 为 active 样本定义统一 runner 入口
2. 先支持 `easy_login`
3. 统一支持：
   - `directory`
   - `zip`
   - `none`
4. 返回原始 `dispatcher.run(...)` 结果，不额外包复杂协议

---

## 为什么现在做

catalog 已经能表达：

- 样本是什么
- 路径在哪
- 最小提示是什么

但还不能表达：

- active 样本到底怎么跑

如果没有 runner helper，后面每增加一个 active 样本，都会把 runtime stub、dispatcher 调用、variant 分支再复制一遍。

---

## 最小模块落点

新增：

- `D:\webstudy\FlagHunter\tests\integration\local_challenge_runner.py`

当前它属于测试资产，不进入生产代码。

---

## 最小接口

```python
async def run_active_local_challenge_sample(
    sample,
    *,
    variant: str,
    monkeypatch,
    tmp_dir: Path | None = None,
)
```

### 约束

- 当前只实现 `easy_login`
- 其他 sample 如果调用，明确抛 `NotImplementedError`

---

## `easy_login` runner 合同

### `variant="directory"`

- 使用 catalog 里的目录 challengePath
- 应返回 verified flag success

### `variant="zip"`

- 使用 catalog 构造 zip-only challenge_context
- 应返回 verified flag success

### `variant="none"`

- 不给 local assets
- 应保持 honesty，不得 false verified

---

## 验证口径

本轮通过标准：

1. `test_local_challenge_runner.py` 三个变体通过
2. 现有 `test_local_asset_eval_pack.py` 仍然全绿
3. 串行运行这两份 integration 测试无回退

