# FlagHunter live CTF 能力与端到端测试台账

日期：2026-06-09

## 测试原则

1. 先测能力，不先写题目专用脚本。
2. 能力测试必须说明当前项目已有的通用策略、触发条件和预期证据。
3. 端到端测试必须使用 live 靶场 URL，优先让 `pentestagent run --mode ctf` 独立完成。
4. 失败时先归因到通用能力缺口，再做最小通用修复；不得把题名、固定 flag、固定靶机 URL 写进 solver。
5. 每次修复后至少保留单元/集成回归和 live 回归证据。
6. 浏览器平台操作使用 OpenCLI Browser Bridge 复用登录态；不截图，不导出大 HTML/大响应体。

## 统一记录模板

- 题目：
- 目标能力：
- 能力测试：
- live 靶机：
- E2E 命令：
- E2E 结果：
- 平台确认：
- 暴露缺口：
- 通用修复：
- 回归验证：
- WP/证据：

## 已记录样本

### [34C3CTF 2017]urlstorage

- 目标能力：contact/admin bot、captcha/PoW、URL 存储、RPO/CSS exfil、无外网约束下的收敛。
- 能力测试：验证项目可发现 `/contact`，可解析 captcha/PoW 字段，可提交 contact 表单。
- live 靶机：`http://fc1a16aa6f365c18a121bd57.http-ctf2.dasctf.com:80`
- E2E 结果：未解；修复后能诚实停止，不再制造假进展。
- 平台确认：未完成。
- 暴露缺口：缺少 RPO/CSS exfil 候选链识别；无外网时缺少 `external_exfil_blocked` 类停止/同源替代判断。
- 通用修复：过滤假 backup/source HTML；contact 已提交后不再重复 POST。
- 回归验证：`tests/unit/agents/test_ctf_dispatcher.py` 全量 `144 passed`；live 回归不再出现 `www.zip/backup.zip` 假 candidate。
- WP/证据：`docs/dev/DASCTF_34C3CTF2017_urlstorage_contact_RPO_阶段WP_2026-06-09_V1.md`

### [ASIS 2019]Unicorn shop

- 目标能力：购买表单识别、`id/price` 字段语义、Unicode 数字/单字符绕过。
- 能力测试：已有 `unicode_numeric_form_bypass` 单元/集成样本；live 前先确认该策略不是题名硬编码。
- live 靶机：`http://7e10c632576bf0ca519a08f5.http-ctf2.dasctf.com:80`
- E2E 命令：

```powershell
.\.venv\Scripts\pentestagent run -t "http://7e10c632576bf0ca519a08f5.http-ctf2.dasctf.com:80" --mode ctf --max-loops 5 "拿到flag。目标是 ASIS 2019 Unicorn shop，优先少量HTTP侦察、商品/购买表单、价格/数量字段和 Unicode 数字/单字符绕过；不要大规模扫描。"
```

- E2E 结果：成功，项目自动提交 `price=万` 到 `/charge` 并获得 `DASCTF{0b9a836f-e4cc-46aa-a2ee-173b91efef35}`。
- 平台确认：回答正确，WEB 进度变为 `2/1608`。
- 暴露缺口：本题未暴露新缺口。
- 通用修复：无。
- 回归验证：live E2E 成功；平台提交成功。
- WP/证据：`docs/dev/DASCTF_ASIS2019_Unicorn_shop_Unicode数字绕过_做题WP_2026-06-09_V1.md`

### [强网杯 2019]Upload

- 目标能力：文件上传题的通用表单发现、multipart 上传、扩展名/MIME/内容绕过、上传后可访问路径发现。
- 能力测试：先跑 `pytest tests -k upload`，从最初 `7 passed` 逐步扩展到 `10 passed`；新增 post-auth upload、PHP upload cookie POP、source-only recoverable 等通用样本。
- live 靶机：
  - 初始平台按钮多次不刷新 URL；后用 OpenCLI Browser Bridge 登录态 API 取到 `http://24421ffa554d8f5706749f7b.http-ctf2.dasctf.com:80`。
  - 旧靶机过期后重新启动，最终 E2E 靶机为 `http://ee9c111fba2e7a34d85b055d.http-ctf2.dasctf.com:80`。
- E2E 命令：

```powershell
.\.venv\Scripts\pentestagent run -t "http://ee9c111fba2e7a34d85b055d.http-ctf2.dasctf.com:80" --mode ctf --max-loops 5 "拿到flag。先测试通用文件上传能力：发现登录/注册入口，注册低权限账号，登录后重新侦察上传表单，multipart 上传；若源码泄露显示 cookie unserialize + __destruct/__call + copy(upload tmp, filename)，用源代码证据驱动的 PHP upload cookie POP runtime 验证；不要大规模扫描。"
```

- E2E 结果：成功，项目自动完成 post-auth recon、源码泄露分析、PHP upload cookie POP runtime exploit，获得 `DASCTF{16cd03e2-c913-48bf-a62e-6da5518573e3}`。
- 平台确认：`POST /api/v1/practice/.../submit/` 返回 `is_correct=true`，`points=1`。
- 暴露缺口：
  - pre-auth 只有 login/register 时误判 SQLi，未进入注册登录后的 upload 面。
  - 注册邮箱默认模板过短，容易触发 `Email illegal`。
  - 相对 form action 解析错误，曾把 `/index.php/home + upload` 拼成 `/index.php/home/upload`。
  - source-only 假 flag / 模板占位符会提前停止。
  - polyglot 响应可能把 `GIF89a` 吞进 flag。
  - 缺少源码证据驱动的 `cookie unserialize + upload copy` POP primitive。
- 通用修复：
  - `upload` dispatcher 闭环：发现 file input、multipart 上传、跟随上传路径。
  - post-auth recon：自动注册低权限账号、登录后重新侦察，发现 file input 后重新判为 upload。
  - 相对 form action 按标准 `urljoin(page_url, action)` 解析。
  - source-only wrong flag 标记 recoverable，记录后继续链路。
  - flag 提取器优先严格匹配常见 CTF flag 前缀。
  - backup analyzer 新增 `php_upload_cookie_pop` 识别；runtime exploit 自动上传 GIF/PHP polyglot、构造 cookie POP、复制为 PHP shell 并回收 flag。
- 回归验证：
  - focused：`php_upload_cookie_pop / generic_upload / post_auth_upload / recoverable_source_only`，`4 passed`。
  - `pytest tests -k upload -q`：`10 passed`。
  - `pytest tests/unit/agents/test_ctf_dispatcher.py -q`：`148 passed`。
- WP/证据：`docs/dev/DASCTF_强网杯2019_Upload_ThinkPHP_cookie_POP_做题WP_2026-06-09_V1.md`

### [HITCON 2017]SSRFme

- 目标能力：SSRF 判型、参数名泛化、内网/本地文件读取、协议 payload、二次触发与结果回收。
- 能力测试：`pytest tests -k ssrf` 通过 `2 passed`，覆盖 `detect_type` 与 `gf` 模式；dispatcher 当前 SSRF 链仅固定尝试 `?url=http://127.0.0.1/`、`?url=file:///etc/passwd`、`?url=dict://127.0.0.1:6379/`。
- live 靶机：未分配。OpenCLI 点击“启动靶机”后页面仍保持“启动靶机”，无 `http-ctf2` 地址，未进入运行中。
- E2E 命令：未运行，因为没有 live target URL。
- E2E 结果：未开始，不计为项目解题失败。
- 平台确认：未完成。
- 暴露缺口：SSRF 通用链能力较薄；平台本次同样未能启动环境，需要后续重新尝试 live URL。
- 通用修复：待补。方向应是从表单/链接/参数自动发现 SSRF 参数，按响应证据迭代协议和目标，而不是固定 `?url=`。
- 回归验证：待补。
- WP/证据：本台账记录。
