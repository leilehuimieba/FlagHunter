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
  - `run6`：
    - 新实例：`http://a22df207d1aff3332833bbbf.http-ctf2.dasctf.com:80`
    - run id：`ctf-e5baedfb6a40`
    - 内部证据显示 SSRF/source-leak 主链依然成立，但 CLI `run --mode ctf` 未把 `llm` 注入 `CTFTaskDispatcher`，导致 flow 停在 `llm_not_configured`。
  - `run7`：
    - run id：`ctf-ff9af3c68585`
    - 注入 CLI LLM 后，LLM follow-up 首次真实跑起来。
    - 新阻塞：`ToolGuard blocked: external domain is outside target/collector allowlist`。
    - 归因：`PreActionReasoning` 把 `http://host` 与 `http://host:80` 误判为不同主机，导致同域 follow-up 被挡。
  - `run8`：
    - run id：`ctf-f256bd62c637`
    - 默认端口同域归一化修复后，`ToolGuard blocked...` 消失。
    - `llm_exploration_steps=8`，说明 dispatcher 已经真实继续执行 post-source-leak 的 LLM follow-up，而不再停在 SSRF/runtime 基线能力。
    - 新主缺口不再是“能不能 SSRF”，而是“拿到源码后怎么稳定推进下一步”：
      - LLM 多次重复请求首页高亮源码，未优先消费已确认的 `source_fetch_write_ssrf` 原语与 runtime 证据。
      - LLM shell follow-up 存在 Windows `LocalRuntime` 不兼容命令：
        - `python3 - <<'PY'` 触发 `<< was unexpected at this time.`
        - `python3` 在某一步返回 `9009`。
  - `run11`：
    - 日期：`2026-06-13`
    - 实例 id：`2d1c320e-7bbf-4b5b-a977-f1a682794112`
    - URL：`http://2d1c320ed1d8a28774d53709.http-ctf2.dasctf.com:80`
    - 过期：`2026-06-13 22:57:06 +08:00`
    - run id：`ctf-a8a21324f7ed`
    - 结果：live runtime 仍可稳定触发 `source_fetch_write_ssrf`，继续回收 `/etc/passwd`、`/proc/self/*`、`/var/www/html/index.php`、`/flag`、`/flag.txt`、loopback 目标。
    - 新确认：Windows heredoc 归一化回归未复发，空 shell 命令问题也未再显性出现。
    - 新主缺口：post-source-leak 后 LLM 仍会退化成弱 GET 和 provider-heavy 循环；其中出现 `GET /` 与 `GET ?url=file:///etc/passwd` 但未桥接 `filename` 的低质量 follow-up。
  - `run12`：
    - run id：`ctf-3eab53ecf0e4`
    - 时长：`7m17s`
    - 结果：首次在 long-run live ledger 中确认 `llm_action` 已保留 `source_fetch_write=true` 桥接语义，并成功执行：
      - `GET ?url=file:///flag&filename=p/flaghunter_probe.txt`
      - 随后 `retrieve_source_fetch_write_output`
    - 结论：此前“长 observation 后遗忘 confirmed primitive”这一类缺口已经明显收紧。
    - 仍存问题：run12 中仍出现两次无参数根路径 `GET http://host:80`，说明 planner/guard 对弱动作的抑制还不稳定。
  - `run13`：
    - run id：`ctf-82062fa9c801`
    - 时长：`7m59s`
    - 结果：再次确认 long-run 下 `llm_action -> source_fetch_write=true -> retrieve_source_fetch_write_output` 仍成立，这次桥接到 `file:///etc/passwd`。
    - 结论：`source_fetch_write` retained bridge 已进入 live 主链，不再只是单元测试能力。
    - 仍存问题：run13 里无参数根路径 `GET http://host:80` 依然出现 3 次，说明剩余瓶颈已经进一步收敛为 post-source-leak planner 质量 / reasoning 可见性，而不是 SSRF primitive 本身。
  - 注意：终端摘要中的 `Loops: 0 / Tools: 0` 与内部 ledger/checkpoint 证据不一致；真实 session ledger 显示已执行大量 `browser_action` / `proxy_action` / `execute_command`。
- 平台确认：未完成。
- 暴露缺口：
  - inline highlighted PHP source 虽然能识别为 source leak，但此前 analyzer 对高亮 HTML 归一化不足，无法稳定提取 SSRF 原语。
  - Windows `LocalRuntime` 下，backup analyzer 早期使用超长 `python -c` 命令行，触发 `The command line is too long.`。
  - SSRF runtime 已能回收源码/配置，但此前不会把回收结果注册为后续可消费的 `source hint`，导致主流程停在“证明可读文件”，不能基于新证据继续展开。
  - SSRF follow-up 目标此前主要依赖固定文件列表，缺少基于回收内容自动扩展后续 file/loopback 目标的能力。
  - CLI `run --mode ctf` 此前未注入 `llm`，导致 live E2E 与 TUI / 内部 dispatcher 能力不一致。
  - `PreActionReasoning` 的外域判断此前没有归一化默认端口，`http://host` 与 `http://host:80` 会被误判成不同目标。
  - post-source-leak 阶段存在两个新的通用短板：
    - LLM 动作虽然能生成 richer payload，但执行层会把一部分 payload 意图塌缩成普通首页 GET，没把 discovered primitive 真正翻译成 runtime 请求。
    - LLM shell follow-up 缺少 Windows/PowerShell 兼容约束，容易生成 here-doc 和 `/tmp` 之类的 Linux 命令。
  - 输出层缺口：终端 `Loops/Tools` 汇总口径与 session ledger 不一致，容易误导验收。
  - 2026-06-13 新定位后的剩余缺口：
    - `source_fetch_write_ssrf` observation 与 `local_challenge_source_hint` 的 retained context 已部分补齐，但 planner 仍会周期性提出无参数根路径 GET。
    - 该弱动作在 run12/run13 中仍能进入 `llm_action` 执行，说明剩余问题更偏向“LLM proposal 为什么绕过/未命中已有弱动作判定”，而不是 primitive 已丢失。
- 通用修复：
  - `pentestagent/agents/pa_agent/ctf_dispatcher.py`
  - backup/source analyzer 对 highlighted HTML 做 `<br>`、tag stripping、HTML entity unescape、空白归一化，稳定识别 `source_fetch_write_ssrf`。
  - Windows LocalRuntime 下改为临时 `.py` 文件执行 backup analyzer，绕过命令行长度限制。
  - `source_fetch_write_ssrf` runtime 成功回收源码时，统一注册为 `local_challenge_source_hint`，来源标记为 `runtime_source_leak`。
  - web 链在 `backup_source_leak` 新发现 source hint 后，允许回放一轮前置策略，让新源码证据真正进入后续调度。
  - SSRF follow-up 目标支持从已回收内容中自动抽取 `file:///...` 和 `http://127.0.0.1/...` 候选，继续少量扩展。
  - `pentestagent/interface/cli.py`
  - CLI CTF 模式统一注入 `LLM(model=model, rag_engine=rag)`，避免 `run --mode ctf` 在 live E2E 中停在 `llm_not_configured`。
  - `pentestagent/agents/pa_agent/reasoning.py`
  - 同域外发判断对默认端口做归一化，`http://host == http://host:80`，`https://host == https://host:443`。
  - `pentestagent/agents/pa_agent/ctf_dispatcher.py`
  - LLM prompt 追加 runtime 环境摘要和已确认的 `source_fetch_write_ssrf` exploit 上下文，明确要求优先消费已知 primitive，不再重复抓取同一首页源码。
  - LLM http action 执行层新增 payload 归一化：
    - 支持 `"GET http://..."` 这种字符串 payload。
    - 支持从 `candidate_file_urls` / `candidate_urls` 中恢复真实请求意图。
    - 若已观察到 `source_fetch_write_ssrf`，可把 LLM follow-up 直接桥接到 runtime trigger + output retrieve，而不是退化成首页 GET。
  - LLM shell action 在 Windows `LocalRuntime` 下新增通用兼容归一化：
    - 将 `python3 - <<'PY'` here-doc 转为临时 `.py` 文件执行。
    - 将 `/tmp/...` 重写到本机临时目录。
    - 将 `python3` 替换为当前解释器路径，减少 `9009` 类失败。
  - `pentestagent/agents/pa_agent/ctf_state.py`
  - 新增 `recent_observations(kind=..., limit=...)`，按 observation kind 回看最近匹配项，而不是只盯“最后 N 条事件”。
  - `pentestagent/agents/pa_agent/ctf_dispatcher.py`
  - `source_fetch_write_ssrf` 与 `local_challenge_source_hint` 相关上下文改为按 kind 回看，避免 long-run 被大量 probe observation 挤掉。
  - `pentestagent/agents/pa_agent/reasoning.py`
  - 无参数/相对根路径 GET 的弱动作判定更早收紧：
    - `GET /`
    - `payload: {method: GET}`
    - 但保留 `candidate_file_urls` / `candidate_urls` 这类真实 SSRF follow-up 意图，不误伤已确认 primitive 的桥接动作。
- 回归验证：
  - `pytest tests/unit/agents/test_ctf_dispatcher.py -k "source_fetch_write_ssrf or inline_source_on_current_page or runtime_source_hint or replays_prefix_strategies or followup_fetch_targets" -q`
  - `5 passed`
  - `pytest tests/unit/interface/test_cli_local_asset_contract.py -k "run_cli_routes_ctf_mode_into_dispatcher_with_local_asset_hint or run_cli_preserves_auto_ctf_subtype_for_dispatcher or run_cli_syncs_derived_target_into_challenge_context_when_target_missing" -q`
  - `3 passed`
  - `pytest tests/unit/agents/test_ctf_reasoning.py -k "default_port_is_implicit or blocks_external_domain_request or allows_stop_action_without_capability_gate" -q`
  - `2 passed`
  - 本轮新增 focused 回归：
    - `llm string payload -> http_request`
    - `llm source_fetch_write candidate urls -> runtime trigger/retrieve`
    - `windows heredoc shell normalization`
    - `source_fetch_write bridge survives probe history`
    - `redundant root fetch blocked for relative/implicit root payload`
    - `redundant root fetch blocked after source exploit candidate`
  - live 证据：
    - `loot/ssrfme_e2e_2026-06-09_run4.log`
    - `loot/ssrfme_e2e_2026-06-09_run5.log`
    - `loot/ssrfme_e2e_2026-06-10_run6.log`
    - `loot/ssrfme_e2e_2026-06-10_run7.log`
    - `loot/ssrfme_e2e_2026-06-10_run8.log`
    - `loot/ssrfme_e2e_2026-06-13_run11.log`
    - `loot/ssrfme_e2e_2026-06-13_run12.log`
    - `loot/ssrfme_e2e_2026-06-13_run13.log`
    - `loot/checkpoints/ctf-d2d0b952ec43.jsonl`
    - `loot/checkpoints/ctf-98367b67287c.jsonl`
    - `loot/checkpoints/ctf-e5baedfb6a40.jsonl`
    - `loot/checkpoints/ctf-ff9af3c68585.jsonl`
    - `loot/checkpoints/ctf-f256bd62c637.jsonl`
    - `loot/session_ledgers/ctf-d2d0b952ec43.jsonl`
    - `loot/session_ledgers/ctf-98367b67287c.jsonl`
    - `loot/session_ledgers/ctf-e5baedfb6a40.jsonl`
    - `loot/session_ledgers/ctf-ff9af3c68585.jsonl`
    - `loot/session_ledgers/ctf-f256bd62c637.jsonl`
    - `loot/session_ledgers/ctf-a8a21324f7ed.jsonl`
    - `loot/session_ledgers/ctf-3eab53ecf0e4.jsonl`
    - `loot/session_ledgers/ctf-82062fa9c801.jsonl`
- WP/证据：本台账记录；本轮建议配套查看 `docs/dev/DASCTF_HITCON2017_SSRFme_阶段WP_2026-06-10_V1.md`。

### [护网杯 2018]easy_laravel（2026-06-16 live）

- 目标能力：web 框架指纹识别、Laravel 应用的源码/路由发现与反序列化利用。
- live 靶机：`http://c6c0f5452a46239c548766bb.http-ctf2.dasctf.com:80`（DASCTF ctf2 新平台 BUUCTF 迁移练习场，OpenCLI Browser Bridge 复用登录态启动）。
- E2E 命令：`pentestagent run -t <url> --mode ctf --max-loops 6 "拿到flag。先做少量HTTP侦察，识别框架与源码泄露(.git、composer、路由入口如 /index.php)，基于源码证据逐步推进利用；不要大规模扫描、不要暴力破解。"`
- E2E 结果：未解。recon 后仅探了 backup.zip/tar.gz/bak，exploration_agenda 为空 → recovery(explore_agenda) → 停。
- 暴露缺口（通用）：**recon 抓到了 `laravel_session`/`XSRF-TOKEN` cookie，但项目无任何 web 框架指纹**（`detected_type` 始终 None），把 Laravel 应用当作空白 web 目标，过早放弃。首页明明有 `/login`、`/register`。
- 通用修复（`e78c345`）：`_phase_recon` HTTP 回退路径补抓 response headers + Set-Cookie（无浏览器也能拿框架信号）；新增 `_fingerprint_framework`，按 cookie/header/body 签名识别 Laravel/ThinkPHP/Django/WordPress/Rails/Express/Spring/Flask，记 `framework_detected` observation（流入黑板 facts + planner prompt）。
- 回归验证：新增单测 `test_recon_fingerprints_framework_from_signals`；全量 `1585 passed / 0 failed`；live 靶机真实 `laravel_session` cookie 上验证识别为 laravel。
- 仍存深层缺口（后续专项）：① 浏览器被平台 WAF(ModSecurity) 挡/无法启动时，recon 的链接/表单抽取仍可能为空 → agenda 空；② Laravel 加密 cookie 反序列化 RCE 利用链（需 APP_KEY 泄露 + gadget）尚未实现。

#### easy_laravel 深挖追加（2026-06-16，commit `85288c3`）

复验时发现"body 抖动"背后其实藏着一个**更大的通用根因 bug**：

- **根因**：`_should_ignore_exploration_candidate` 比较主机时**不归一化默认端口**。靶机 URL 是 `http://host:80`（DASCTF 实例都带 `:80`），而页面里的链接写成 `http://host/login`（不带端口）→ 被判为**跨主机** → **所有同站链接被忽略** → exploration_agenda 空 → agent 在**任何带显式端口的目标**上都直接放弃。这才是 easy_laravel（以及大量 live 题）recon 后"无事可做"的真因，不是框架识别也不是抖动。
- **修复**：归一化 `:80`(http)/`:443`(https)，`http://host` 与 `http://host:80` 视为同站；真正的跨主机和非默认端口仍正确拒绝。
- **附带修复**：`_proxy_get_with_retry`——recon 对 5xx/空/极小 body 重试（CTF 实例常在启动中返回 "Target unavailable"），不再把错误页当 recon 内容。
- **Live 验证**：对真实活实例，recon 现在产出 `raw_links=[/login,/register]` + agenda 被填充（原来空）+ `framework_detected=laravel`。
- 回归：全量 `1588 passed / 0 failed`（+2 retry、+1 端口归一化单测）。

#### easy_laravel 复跑追加（2026-06-16，框架常规路由播种）

端口归一化修完后再跑一次完整 agent（`max-loops 8`，靶机 `http://384a6158d060c2a4f0dc96dd...:80`，log `loot/easy_laravel_full_205104.log`，ledger `ctf-5a8416c89179.jsonl`）：

- **结果**：仍未解。8 轮全耗在盲猜 `.env`/`.git/config`/`backup.zip`/`backup.bak`，**从未访问 `/login`、`/register`**；`recovery(explore_agenda)` 的理由写着"消耗 ExplorationAgenda 中的显式页面线索"，实际却跳去 backup.zip → agenda 当时是空的。
- **定位**：直接对活靶机调真实 `_phase_recon`，**happy path 完全正常**（`html_len=2252`、`raw_links=[/login,/register]`、`framework_detected=laravel`、`agenda=[/,/login,/register]`）。说明那一跑命中真实的 **"body 抖动"**——代理那一刻 body 空/坏，recon 抓到 0 链接 → 退化成盲猜 backup，且无回头补侦察的路径。
- **关键观察**：**headers/cookie 稳，body 抖**。`laravel_session`/`XSRF-TOKEN` 即使 body 空也照样到，而 `_fingerprint_framework` 正是靠 cookie/header 触发。
- **通用修复**：新增 `_FRAMEWORK_CONVENTIONAL_ROUTES` + `_seed_framework_conventional_routes`——只要框架被指纹识别，就把该框架的常规入口路由（laravel: `/login /register /home /api`；wordpress: `/wp-login.php …`；spring: `/actuator …` 等）播种进 exploration_agenda（`discovery_source=framework_convention`, `hint_strength=2`，默认端口归一化以与抓取链接去重）。这样 recon 不再单靠"首页能否抓到链接"——body 抖动/SPA/重定向到登录页时，agent 仍落在应用真实入口而非盲猜备份文件。
- **Live 验证**：活靶机 recon 现在 agenda = `link_href:/login,/register` + `framework_convention:/home,/api`，`/login` 正确去重为 1 条；空 body 场景（只剩 laravel cookie）单测验证仍能播种 `/login,/register`。
- 回归：新增单测 `test_recon_seeds_framework_conventional_routes_when_body_empty`；全量 `tests/unit tests/integration` 运行中（提交前以零新增失败为准）。
- 仍存深层缺口（后续专项）：Laravel 加密 cookie 反序列化 RCE 利用链（APP_KEY 泄露 + gadget）尚未实现——这是 easy_laravel 拿 flag 的最后一公里。

#### easy_laravel 新靶机复跑（2026-06-16，SSH runtime 暴露两个新缺口）

新实例 `http://b547e85b1cceb7848573fd09...:80`（同 Laravel），完整 agent `max-loops 8`，本次 runtime 自动解析成 **SSH（Kali VM user1@127.0.0.1:2222）**，log `loot/easy_laravel_new_215649.log`，ledger `ctf-053987fbdb39.jsonl`。

- **结果**：仍未解，`stop_generic`。recon 后又只探 `.git/HEAD`、`.env`、`backup.zip/tar.gz`，**全程没碰 `/login`、`/register`**。
- **缺口 1（agent 不消费 agenda）**：本次 recon **是工作的**——`agenda` 里实打实有 `/login`、`/register`（link_href 抓到了）。但 planner prompt 只把链接埋在 `Known links` 里，**从不显式呈现 ExplorationAgenda 这个结构化高价值队列** → 模型按 CTF 先验去盲猜 `.git/.env/backup` 并停。
  - **修复**：`_call_llm_for_action` 新增「Unexplored high-value entry points (ExplorationAgenda)」块，把 `get_unexplored_priority_items` 的未探索高优先条目（带 discovery_source/hint）显式列给模型，提示优先消费 `/login /register /admin /api`、auth-gated 应用先注册再登录走最短链。**补协议不补控制**——只呈现队列，不强制选择。
- **缺口 2（SSH 下 HTTP get 不支持）**：`recon_errors: ['proxy_get: Unknown proxy action: get']`。`SSHRuntime.proxy_action` 只是 mitmproxy 控制器，没有 HTTP `get` → recon 的 HTTP 回退拿不到 response headers/Set-Cookie → `framework_detected=[]`（Local 下能识别 laravel，SSH 下识别不了，常规路由播种也跟着失效）。
  - **修复**：`SSHRuntime` 新增 `_proxy_http_fetch`，用 Kali VM 上的 curl 实现 `get/request/post`，返回 `{status_code, headers, body, final_url}`，对齐 LocalRuntime 的 httpx 契约（含多跳 Set-Cookie 合并）。
- **Live 验证（SSH runtime 真实靶机）**：`proxy get status=200`、set-cookie 含 `laravel_session`、`framework_detected=['laravel']`、`recon_errors=[]`、agenda = link_href `/login,/register` + framework_convention `/home,/api`。两缺口均闭环。
- 回归：新增单测 `test_planner_prompt_surfaces_unexplored_exploration_agenda`、`TestSSHRuntimeProxyHttpFetch`（2 条）；全量 `tests/unit tests/integration`（剔除 2 个需 Kali VM 的 radare2/angr 环境用例）运行中，提交前以零新增失败为准。

#### easy_laravel 第三台复跑（2026-06-17，闭合认证流缺口）

第三个实例 `http://0d10c31dee607afda9f261a0...:80`，完整 agent `max-loops 10`（SSH runtime），log `loot/easy_laravel_n3_233439.log`，ledger `ctf-a90b18fb150a.jsonl`。

- **结果**：仍未解，但**两处修复显著生效** —— agent 这次**真的去 GET 了 `/login`、`/register`**（前两台从不碰），`framework=laravel`，agenda 里 `/login /register /home /api` 全部 `explored=True`，还发现了 `/password/reset`。
- **新缺口（认证流死在无表单首页）**：agent 只是把 `/login`、`/register` 当页面 GET 来读，**没有真正注册→登录→带 session 重新侦察**。根因：`_attempt_post_auth_recon` 只看**首页**的 `features["forms"]`，而 Laravel 落地页是 welcome 页 `forms=0`，登录/注册表单在 `/login`、`/register` 子页上 → `find_auth_form` 返回空 → 整个认证流不触发。
  - **通用修复**：新增 `_candidate_auth_page_urls`（从 raw_links/agenda 里挑 login/register/signin/signup 路径 + 常规 `/register`、`/login` 兜底，默认端口去重）+ `_harvest_auth_forms_from_routes`（GET 这些子页、解析其表单、动作 URL 解析为绝对）。首页无表单时改用采集到的表单跑既有 register→login→re-recon 流。顺手把 `has_session_cookie` 从 Django 专用 `sessionid=` 扩成多框架（laravel_session/_session_id/connect.sid/jsessionid）。
  - **Live 验证**：真实靶机采集到两张表单 —— 登录 `/login`(_token,email,password,remember)、注册 `/register`(_token,name,email,password,password_confirmation)，`find_auth_form`/`_find_registration_form` 均正确命中。
- **认证流为何仍 None（题目专属，非 bug）**：实测 register/login POST 均返回 **500**（Laravel debug 异常页，YUI 样式），既有 `400<=status<600 → None` 守卫正确拦下，不把 500 误判成登录成功。easy_laravel 的真实解法本就不是"正常注册登录"，而是 **debug 错误页泄露 → 加密 cookie 反序列化 RCE 链**（APP_KEY + gadget），属深层专项。
- 回归：新增单测 `test_harvest_auth_forms_from_conventional_routes_when_homepage_formless`；34 条 auth/login 相关用例全过；全量运行中，提交前以零新增失败为准。
- **能力进展小结（三台连跑）**：recon→框架指纹→agenda 播种→planner 消费 agenda→探登录入口→采集认证表单→尝试注册登录，这条**通用渗透前置链路在 Local/SSH 两种 runtime 下已全部打通**。剩下的就是 easy_laravel 专属的反序列化利用链。

---

## 2026-06-17 [强网杯 2019]随便注（SQLi）— 换题型实测，发现并修复 web 链漏配 SQLi 策略

- **背景**：按上轮"easy_laravel 通用前置已榨干，建议换不同类型 Web 题"的结论，登录 DASCTF/BUUCTF 公开练习场，启动 **[强网杯 2019]随便注** 实例 `http://823598383173574d7f97c383.http-ctf2.dasctf.com:80`（经典堆叠注入：首页 `GET ?inject=` 表单，`select` 关键字被过滤，需 `show tables`/`handler` 绕过）。
- **首跑（修复前）**：`--ctf-type web --max-loops 12`。轨迹 = recon(navigate/get_content/get_forms/get_cookies/GET) → post_auth_recon 试 `/register`,`/login`（本题对任意路径回 200，假阳性）→ llm_action 猜 `/backup.zip`×2 → 6m27s **未命中 flag**，**全程从未对 inject 表单发任何注入 payload**。
- **根因定位**：dispatcher 已内置专为随便注写好的完整解题链 `_attempt_generic_param_sqli`（`1'` 报错探测 → `1';show tables;#` → 优先 `words`/数字表 → `show columns` 找 flag 列 → `handler <t> open;read first;#` 绕过 select 读 flag → 验证）。但该策略**只在分类器选 `sqli` 链时才跑**；`chain_name=="web"` 走的是 `_WEB_STRATEGY_ORDER`（file_read/SSTI/path_traversal/backup/unserialize），**整张表里没有任何 SQLi 策略** → 通用 web 分类下注入点被白白放过。
- **通用修复（commit `dd58a1c`）**：把 `generic_param_sqli` 追加到 `_WEB_STRATEGY_ORDER` **末尾**。安全性：① precondition 仅在"有非隐藏命名输入的 GET 表单"时触发；② `_run_strategy_sequence` 只在 `outcome.flag` 时提前返回（progress 不短路），放末尾 ⇒ 靠前置策略出 flag 的题在到达它前就 return，**零行为变化**；③ 非 SQLi 应用从它拿不到 flag，链照常继续。只加 `generic_param_sqli`，`auth_form_sqli`（登录框 SQLi，回归风险高）暂不动。
- **Live 验证（修复后）**：同靶机重跑 **0m59s 解出** —— `ctf_sqli_stacked_tables` → `ctf_sqli_columns_1919810931114514` → **Flag verified `CTF2{be61d3f1-33fd-4dc2-ba84-326da6920311}`**，平台提交显示**"已解出"**。对比：6m27s 未解 → 59s 解出。
- **回归**：全量 unit **1507 passed**；19 个 sqli/web-chain 单测 + 13 个 web 验收集成测试（acceptance/jinja2/tornado/include/llm_fallback/backup/misc/php_object/profile_poisoning）全过，零新增失败。
- **方法论复盘**：这是"能力已写好但够不着"型缺口——补的不是算法而是**调度可达性**（把已有强能力接进通用分类路径）。同类可疑点：web 链同样没接 `auth_form_sqli`、LFI/cmdi/ssrf 等也都各自锁在专属 `chain_name`，通用 web 分类未必能触发；下一步可逐一核查"分类器漏判 → 专属链够不着"的同构缺口。
