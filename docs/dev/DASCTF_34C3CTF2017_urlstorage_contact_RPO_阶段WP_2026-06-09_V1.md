# DASCTF [34C3CTF 2017]urlstorage 阶段 WP / FlagHunter 缺口记录

日期：2026-06-09

目标：用 live 靶场验证 FlagHunter 对 URL 存储、contact/admin bot、captcha/PoW 与无外网约束的处理效果。

## 靶场信息

- 靶场 URL：`http://fc1a16aa6f365c18a121bd57.http-ctf2.dasctf.com:80`
- 平台提示：靶机目前暂时无法访问外网。
- 当前结果：未拿到 DASCTF flag，已记录为项目能力缺口。

## 已验证事实

1. 未登录访问 `/contact`、`/urlstorage` 会跳转到登录页。
2. 随机账号登录后可进入 `/urlstorage`，页面包含可编辑 `url` 字段和 `flag?token=<own-token>` 链接。
3. 访问自己的 `flag?token=<own-token>` 只返回假 flag：`34C3_4e5ebd7658283d8d74226d650409963c435344a7`，状态为 `non-admin`。
4. `/contact` 页面存在 CSRF、captcha、可选 PoW；`/static/pow.py`、`/static/vpow.py` 可访问。
5. captcha 可通过小范围枚举绕过；一次实测中 `captcha_1=3` 后 contact POST 成功跳回 `/urlstorage`。
6. 将自己的 `/flag?token=<own-token>` 提交给 contact/admin 后，自己的 flag 页面状态没有变化。
7. `static../views.py` 等源码泄露路径在当前复刻环境中返回 302，不是可用捷径。

## 项目暴露的问题

修复前 FlagHunter 在本题上有两个明显误判：

1. contact 已提交后每轮仍重复 POST，造成假进展和额外流量。
2. `www.zip`、`backup.zip`、`source.zip`、`/.git/HEAD` 等路径返回登录/URLStorage HTML 时，被错误记录为 `ctf_backup_candidate`。

## 已完成修复

1. `contact_report_chain` 增加已提交 observation 门控：同一轮 state 已有 `contact_report_submitted` 后不再重复提交。
2. `backup_source_leak` 增加候选真实性过滤：归档路径必须像真实归档，`.git/HEAD` 必须像 git ref，源码路径必须像源码或已知泄露页面；普通登录 HTML 会被跳过。
3. 新增回归测试覆盖 contact 不重放与 HTML 假 backup 过滤。

## 当前能力缺口

公开解法方向是 RPO/CSS exfil/admin bot：利用 `/flag?token=` 的注入面和 `/urlstorage` 的可控 URL 内容，让 admin 浏览器加载攻击者控制的 CSS，再外带 admin token/flag。

当前 DASCTF 题面提示靶机无法访问外网，因此 FlagHunter 还需要新增一类判断：

1. 识别 `urlstorage + flag?token + contact/admin + relative stylesheet` 组成的 RPO/CSS exfil 候选链。
2. 当题面或运行事实显示无外网时，不应盲目构造外部 callback，而应记录 `external_exfil_blocked`。
3. 在 blocked 后只尝试同源可观测替代链；若没有同源回收面，应明确停在“需要外部回连或源码新线索”，而不是回退到泛 backup 探测。

## 验证

- 定向回归：`5 passed`
- Dispatcher 全量：`144 passed`
- live 回归：不再记录 `www.zip/backup.zip/...` 假 backup candidate；contact 不再重复提交；最终诚实停止为未命中 flag。

