# DASCTF/BUUCTF [护网杯 2018]easy_tornado — FlagHunter live 自动解题 WP

**日期**:2026-06-29 · **平台**:ctf2.dasctf.com BUUCTF 公开练习场 · **类型**:WEB/简单
**结果**:✅ FlagHunter 全自动解出并平台判对(回答正确 +1,WEB 进度 5→6/1608)

第二条 live 自动解题(首条见 WarmUp WP)。同时**实证上一轮修的两个 gap**(快路径
回填 ctf_sessions + 报告 CTF Solve Chain)在本题真解上都生效。

## 1. 环境
- 实例(授权,本账号):`http://b7e814868f017b7ddc663504.http-ctf2.dasctf.com/`(1h 窗口)
- 平台每实例唯一 flag:`CTF2{1617c627-64f9-4c6c-b6d6-fc6484f690a5}`
- 命令:`flaghunter run "<tornado SSTI 提示>" -t <url> --mode ctf --ctf-type web --profile ctf --report`

## 2. 题目与解链
Tornado 模板注入经典题。FlagHunter dispatcher web 快路径 **11s** 解出(Loops 0/50):
- 指纹/递归探测拿到端点 `/file`、`/flag.txt`、`/hints.txt`、`/welcome.txt`(报告 trace 可见)。
- `/flag.txt` 提示 flag 在 `/fllllllllllllag`;`/hints.txt`:`filehash = md5(cookie_secret + md5(filename))`。
- 经 `/error?msg={{handler.settings}}` 的 SSTI 泄露 `cookie_secret`。
- 算 `filehash = md5(cookie_secret + md5("/fllllllllllllag"))`,请求
  `/file?filename=/fllllllllllllag&filehash=<...>` 读出 flag。

## 3. 工程意义:gap 修复 live 复验
- **第②层自动回填**(上轮修):本题成功后生成
  `knowledge/ctf_sessions/20260629_211315_web_b7e814868...dasctf.com.md`(含 flag)。✅
- **报告链路 trace**(上轮修):`loot/reports/..._211315.md` 含 `## CTF Solve Chain` +
  指纹端点列表。✅
两条均不再是 WarmUp 那次的"0 命令空报告 / 知识库无草稿"。

## 4. 产出归位(数据治理 policy)
① 原始 loot/reports + 注册表(gitignore);② 自动回填 ctf_sessions(本次已触发);
③ 本题解(committed);④ 框架教训:两 gap 已修并复验,治理结论回填 `数据治理与知识回填_policy_2026-06-29_V1.md`。
