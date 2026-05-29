# CLI easy_login Zip-Only Smoke — 2026-05-29

## 目标

验证当前 headless CLI 已能：

- 只接收本地 zip artifact path
- 自动解压并定位 challenge root
- 走本地 compose 日志 pivot
- 最终 verified runtime flag

## 环境

- 仓库：`D:\webstudy\FlagHunter`
- 题目目录：`D:\webstudy\CTF\2026\CTF比赛题\easy_login`
- 临时 zip：`C:\Users\33371\AppData\Local\Temp\easy_login_flaghunter_smoke.zip`
- 目标地址：`http://127.0.0.1:3000`
- 时间：`2026-05-29`

## 构造 zip

```powershell
$src='D:\webstudy\CTF\2026\CTF比赛题\easy_login'
$zip=Join-Path $env:TEMP 'easy_login_flaghunter_smoke.zip'
Compress-Archive -LiteralPath $src -DestinationPath $zip -Force
```

## 执行命令

```powershell
./.venv/Scripts/python.exe -m pentestagent.interface.main run \
  --target http://127.0.0.1:3000 \
  --model gpt-5 \
  --mode ctf \
  --ctf-type web \
  --artifact-path "C:\Users\33371\AppData\Local\Temp\easy_login_flaghunter_smoke.zip" \
  "solve easy_login from local zip artifact only"
```

## 关键观测

- dispatcher 成功恢复本地 challenge 上下文
- 保存：
  - `ctf_admin_password`
  - `ctf_sid`
  - `ctf_flag`
- 最终输出：
  - `flag{dummy_flag_for_testing}`
  - `Flag verified: flag{dummy_flag_for_testing}`

## 结论

当前系统已经具备第二种真实最小输入形态：

- 不给 challenge directory
- 只给本地 zip artifact path

在真实 `easy_login` 上仍能完成：

- 解压
- challenge root 解析
- 本地 compose 日志 pivot
- runtime flag verified
