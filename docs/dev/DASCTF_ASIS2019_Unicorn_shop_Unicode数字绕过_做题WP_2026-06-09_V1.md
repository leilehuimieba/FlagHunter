# DASCTF [ASIS 2019]Unicorn shop Unicode 数字绕过 WP

日期：2026-06-09

## 结果

- 靶机：`http://7e10c632576bf0ca519a08f5.http-ctf2.dasctf.com:80`
- Flag：`DASCTF{0b9a836f-e4cc-46aa-a2ee-173b91efef35}`
- 平台反馈：回答正确，题目状态已完成。

## 做题过程

1. 使用 OpenCLI Browser Bridge 复用已登录浏览器，在 BUUCTF WEB 分类中开启 `[ASIS 2019]Unicorn shop` 靶机。
2. 使用 FlagHunter 端到端运行：

```powershell
.\.venv\Scripts\pentestagent run -t "http://7e10c632576bf0ca519a08f5.http-ctf2.dasctf.com:80" --mode ctf --max-loops 5 "拿到flag。目标是 ASIS 2019 Unicorn shop，优先少量HTTP侦察、商品/购买表单、价格/数量字段和 Unicode 数字/单字符绕过；不要大规模扫描。"
```

3. 项目识别到购买表单和 `id/price` 语义，触发 `unicode_numeric_form_bypass`。
4. 使用 `price=万` 向 `/charge` 提交后拿到 runtime flag，并被 verifier 认定为 verified。
5. 将 flag 提交到平台，平台返回“回答正确！(+1 分)”。

## 关键点

题目核心是服务端对价格字段存在单字符/数字处理差异。普通低价会失败，而 Unicode 数字字符 `万` 在服务端数值语义中可绕过价格校验，从而购买目标商品并返回 flag。

## 对 FlagHunter 的验证价值

这题是 `unicode_numeric_form_bypass` 的正向端到端样本：

- 能从页面表单识别 `id` / `price` 字段。
- 能优先尝试 Unicode 数字绕过，而不是退回泛扫描。
- 能把 runtime flag 通过 verifier 收敛为 verified flag。
- 平台提交确认通过。

