# CLI easy_login Local Assets Smoke — 2026-05-29

## 目标

验证当前 headless CLI 已能：

- 接收 `--mode ctf`
- 接收 `--challenge-path`
- 接收 `--artifact-path`
- 通过本地题目目录驱动 dispatcher 闭环
- 在本地 challenge 场景下把强 runtime flag 收成 verified

## 环境

- 仓库：`D:\webstudy\FlagHunter`
- 题目目录：`D:\webstudy\CTF\2026\CTF比赛题\easy_login`
- 目标地址：`http://127.0.0.1:3000`
- 时间：`2026-05-29`

## 执行命令

```powershell
./.venv/Scripts/python.exe -m pentestagent.interface.main run \
  --target http://127.0.0.1:3000 \
  --model gpt-5 \
  --mode ctf \
  --ctf-type web \
  --challenge-path "D:\webstudy\CTF\2026\CTF比赛题\easy_login" \
  --artifact-path "D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml" \
  "solve easy_login from local challenge assets"
```

## 关键观测

- runtime 自动解析本地 challenge 上下文
- dispatcher 保存：
  - `ctf_admin_password`
  - `ctf_sid`
  - `ctf_flag`
- 最终输出：
  - `flag{dummy_flag_for_testing}`
  - `Flag verified: flag{dummy_flag_for_testing}`

## 结论

当前 CLI headless CTF 路径已经可以在真实 `easy_login` 上完成：

- 本地题目目录桥接
- 本地 compose 日志 pivot
- admin 登录利用
- runtime flag 验证闭环

也就是说，“只给 agent 本地题目目录和最小任务描述”这条主线已经具备真实可复现的最小成功样本。
