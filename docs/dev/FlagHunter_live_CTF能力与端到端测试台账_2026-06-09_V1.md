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
- 能力测试：
  - 早期基线：`pytest tests -k ssrf` 只能覆盖 `detect_type` 与 `gf` 模式，dispatcher 的 SSRF 链仍偏固定 payload。
  - 本轮补充 focused 回归：

```powershell
pytest tests/unit/agents/test_ctf_dispatcher.py -k "source_fetch_write_ssrf or inline_source_on_current_page or runtime_source_hint or replays_prefix_strategies or followup_fetch_targets" -q
```

  - 结果：`5 passed`；新增覆盖 inline highlighted source 归一化、`source_fetch_write_ssrf` 观察结果、runtime source hint 注册、backup/source 后的 web 前缀回放、以及 follow-up file target 自动扩展。
- live 靶机：
  - 通过 OpenCLI Browser Bridge 复用 DASCTF 登录态后，确认 challenge start/read API 为：
    - `POST /api/v1/practice/<practice_id>/challenges/<challenge_id>/target/`
    - `GET /api/v1/practice/<practice_id>/challenges/<challenge_id>/target/?is_private=false`
  - live challenge id：`0884c676-f23e-40a2-92b6-2bd7f6e8a50e`
  - 成功启动后拿到 URL：`http://7f27af4c32949d4708f8686f.http-ctf2.dasctf.com:80`
  - 实例时间：
    - 创建：`2026-06-09 22:07:26 +08:00`
    - 过期：`2026-06-09 23:07:26 +08:00`
- E2E 命令：

```powershell
.\.venv\Scripts\pentestagent run -t "http://7f27af4c32949d4708f8686f.http-ctf2.dasctf.com:80" --mode ctf --max-loops 6 "拿到flag。先测试通用SSRF能力：优先少量HTTP侦察、从页面源码和表单中发现 SSRF 输入面、再按响应证据迭代 localhost/file/gopher/dict 等目标；不要大规模扫描。"
```

- E2E 结果：
  - `run1/run2/run3`：只停在 `backup_source_leak`，尚未真正跑出 SSRF runtime 探针。
  - `run4`：已确认 runtime 真实触发 `source_fetch_write_ssrf`，从 live 靶机回收：
    - `file:///etc/passwd`
    - `file:///proc/self/cmdline`
    - `file:///proc/self/environ`
    - `file:///var/www/html/index.php`
    - `http://127.0.0.1/`
    - `http://127.0.0.1/index.php`
  - `run5`：在 run4 基础上，新增把 runtime 回收源码注册为 `local_challenge_source_hint`，observation 数从 `13` 提升到 `18`，但仍未自动收敛到 flag。
  - 注意：终端摘要中的 `Loops: 0 / Tools: 0` 与内部 ledger/checkpoint 证据不一致；真实 session ledger 显示已执行大量 `browser_action` / `proxy_action` / `execute_command`。
- 平台确认：未完成。
- 暴露缺口：
  - inline highlighted PHP source 虽然能识别为 source leak，但此前 analyzer 对高亮 HTML 归一化不足，无法稳定提取 SSRF 原语。
  - Windows `LocalRuntime` 下，backup analyzer 早期使用超长 `python -c` 命令行，触发 `The command line is too long.`。
  - SSRF runtime 已能回收源码/配置，但此前不会把回收结果注册为后续可消费的 `source hint`，导致主流程停在“证明可读文件”，不能基于新证据继续展开。
  - SSRF follow-up 目标此前主要依赖固定文件列表，缺少基于回收内容自动扩展后续 file/loopback 目标的能力。
  - 输出层缺口：终端 `Loops/Tools` 汇总口径与 session ledger 不一致，容易误导验收。
- 通用修复：
  - `pentestagent/agents/pa_agent/ctf_dispatcher.py`
  - backup/source analyzer 对 highlighted HTML 做 `<br>`、tag stripping、HTML entity unescape、空白归一化，稳定识别 `source_fetch_write_ssrf`。
  - Windows LocalRuntime 下改为临时 `.py` 文件执行 backup analyzer，绕过命令行长度限制。
  - `source_fetch_write_ssrf` runtime 成功回收源码时，统一注册为 `local_challenge_source_hint`，来源标记为 `runtime_source_leak`。
  - web 链在 `backup_source_leak` 新发现 source hint 后，允许回放一轮前置策略，让新源码证据真正进入后续调度。
  - SSRF follow-up 目标支持从已回收内容中自动抽取 `file:///...` 和 `http://127.0.0.1/...` 候选，继续少量扩展。
- 回归验证：
  - `pytest tests/unit/agents/test_ctf_dispatcher.py -k "source_fetch_write_ssrf or inline_source_on_current_page or runtime_source_hint or replays_prefix_strategies or followup_fetch_targets" -q`
  - `5 passed`
  - live 证据：
    - `loot/ssrfme_e2e_2026-06-09_run4.log`
    - `loot/ssrfme_e2e_2026-06-09_run5.log`
    - `loot/checkpoints/ctf-d2d0b952ec43.jsonl`
    - `loot/checkpoints/ctf-98367b67287c.jsonl`
    - `loot/session_ledgers/ctf-d2d0b952ec43.jsonl`
    - `loot/session_ledgers/ctf-98367b67287c.jsonl`
- WP/证据：本台账记录。
