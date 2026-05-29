# Local Asset Eval Pack — 2026-05-29

## 文件

- `tests/integration/test_local_asset_eval_pack.py`

## 场景

### 1. directory-only success
- 本地 `easy_login` 目录输入
- 期望 verified flag

### 2. zip-only success
- 本地 `easy_login.zip` 输入
- 期望 verified flag

### 3. no-local-asset honesty
- 无 challengePath / 无 artifactPaths
- 期望诚实失败，不产生 verified flag

## 运行命令

```powershell
./.venv/Scripts/python.exe -m pytest tests/integration/test_local_asset_eval_pack.py -q
```

## 最近验证结果

- `3 passed`

## 组合回归命令

```powershell
./.venv/Scripts/python.exe -m pytest \
  tests/integration/test_local_asset_eval_pack.py \
  tests/unit/interface/test_cli_local_asset_contract.py \
  tests/unit/agents/test_ctf_verifier.py \
  tests/unit/agents/test_ctf_dispatcher.py \
  -k "local_asset or local_challenge or local_runtime or zip_artifact or cli_local_asset_contract or test_eval_" -q
```

## 最近组合结果

- `12 passed`

## 结论

当前仓库已拥有最小但真实有效的 local-asset regression pack，可用于后续：

- ingress 收口
- dispatcher 调整
- verifier policy 调整
- challenge_context 显式化

后的快速回归。
