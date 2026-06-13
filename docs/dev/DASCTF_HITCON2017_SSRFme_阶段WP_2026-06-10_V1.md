# DASCTF / [HITCON 2017]SSRFme 阶段 WP / FlagHunter 通用能力缺口记录

日期：2026-06-10

## 目标

验证 FlagHunter 在 live SSRF 题上的通用端到端能力，不写题目专用脚本，只修复可复用的能力缺口。

## 题面关键信号

- 首页直接高亮泄露 PHP 源码。
- 泄露代码表明：
  - 支持 `X-Forwarded-For` 覆写 `REMOTE_ADDR`
  - `$_GET["url"]` 进入 `shell_exec("GET " . escapeshellarg(...))`
  - `$_GET["filename"]` 决定写入路径
  - 输出目录位于 `sandbox/` + `md5("orange" . REMOTE_ADDR)`
- 这不是“猜 SSRF”，而是已经拿到可执行的 `source_fetch_write_ssrf` 原语。

## Live 过程留痕

### run6

- 实例：`http://a22df207d1aff3332833bbbf.http-ctf2.dasctf.com:80`
- run id：`ctf-e5baedfb6a40`
- 结果：
  - runtime 证据仍然表明 SSRF/source-leak 主链有效。
  - 但 CLI `run --mode ctf` 未给 `CTFTaskDispatcher` 注入 `llm`。
  - 因此流程停在 `llm_not_configured`，不是题目失败，而是 CLI 能力链断裂。

### run7

- run id：`ctf-ff9af3c68585`
- 结果：
  - 补上 CLI LLM 注入后，LLM follow-up 首次真实执行。
  - 新阻塞来自 `ToolGuard blocked: external domain is outside target/collector allowlist`。
  - 进一步核对发现是 `http://host` 与 `http://host:80` 被误判成不同主机。

### run8

- run id：`ctf-f256bd62c637`
- 结果：
  - 默认端口同域归一化后，`ToolGuard` 阻塞消失。
  - `llm_exploration_steps=8`，说明系统已真实进入 post-source-leak 跟进阶段。
  - 但仍未命中 flag，暴露出新的通用短板：
    - LLM 多次重复获取首页高亮源码，没有优先消费已确认的 `source_fetch_write_ssrf` 原语。
    - shell follow-up 生成 Linux 风格 here-doc 和 `/tmp`，在 Windows `LocalRuntime` 下失败。

### run11

- 日期：`2026-06-13`
- 实例：`http://2d1c320ed1d8a28774d53709.http-ctf2.dasctf.com:80`
- 实例 id：`2d1c320e-7bbf-4b5b-a977-f1a682794112`
- run id：`ctf-a8a21324f7ed`
- 结果：
  - runtime 主链仍然稳定，继续回收 `/etc/passwd`、`/proc/self/cmdline`、`/proc/self/environ`、`/var/www/html/index.php`、`/flag`、`/flag.txt` 和 loopback 页面。
  - Windows heredoc 兼容修复未回退，空 shell 命令问题也未再显性出现。
  - 但 post-source-leak 后仍会退化成弱 GET 与 provider-heavy 循环，其中出现未带 `filename` 的 `?url=file:///etc/passwd` follow-up。

### run12

- run id：`ctf-3eab53ecf0e4`
- 结果：
  - live ledger 首次明确出现 `llm_action` 的 `source_fetch_write=true`：
    - 触发：`GET ?url=file:///flag&filename=p/flaghunter_probe.txt`
    - 回收：`retrieve_source_fetch_write_output`
  - 这说明“长 observation 后遗忘 confirmed primitive”的缺口已经被实质性收紧。
  - 但仍看到 2 次无参数根路径 GET，说明 remaining gap 已从“primitive retention”上移到“planner 仍会提出弱动作”。

### run13

- run id：`ctf-82062fa9c801`
- 结果：
  - 再次确认 `llm_action -> source_fetch_write=true -> retrieve_source_fetch_write_output` 主链可复现，这次桥接到了 `file:///etc/passwd`。
  - 说明 retained bridge 已进入 live 主路径，而不是偶发行为。
  - 仍有 3 次 `GET http://host:80` 的无参数根路径请求进入 `llm_action`，表明剩余问题不是 SSRF primitive 本身，而是 post-source-leak planner 质量 / reasoning 可见性。

## 已确认有效的 runtime 能力

- 已确认 `source_fetch_write_ssrf` 真正可打通。
- 已成功回收：
  - `file:///etc/passwd`
  - `file:///proc/self/cmdline`
  - `file:///proc/self/environ`
  - `file:///var/www/html/index.php`
  - `http://127.0.0.1/`
  - `http://127.0.0.1/index.php`
- 已能把 runtime 回收源码注册为 `local_challenge_source_hint`，供后续调度继续消费。

## 本轮通用修复

### 1. CLI CTF 模式补齐 LLM 注入

- 文件：`pentestagent/interface/cli.py`
- 修复点：
  - `run --mode ctf` 统一注入 `LLM(model=model, rag_engine=rag)` 到 `CTFTaskDispatcher`
- 价值：
  - 保证 CLI live E2E 与 TUI/内部 dispatcher 一致，不再因入口差异导致假失败。

### 2. PreActionReasoning 同域默认端口归一化

- 文件：`pentestagent/agents/pa_agent/reasoning.py`
- 修复点：
  - `http://host` 视作 `http://host:80`
  - `https://host` 视作 `https://host:443`
- 价值：
  - 避免同域 follow-up 被误拦截成“外域请求”。

### 3. LLM action 执行层做通用归一化

- 文件：`pentestagent/agents/pa_agent/ctf_dispatcher.py`
- 修复点：
  - 支持字符串型 http payload，例如 `"GET http://target/admin"`。
  - 支持从 `candidate_file_urls` / `candidate_urls` 中恢复真实请求意图。
  - 若已观察到 `source_fetch_write_ssrf`，则 LLM 的 http follow-up 可直接桥接到：
    - runtime trigger
    - sandbox output retrieve
- 价值：
  - 避免 LLM “说的是利用 primitive，执行的却只是首页 GET”。

### 4. Windows shell follow-up 兼容归一化

- 文件：`pentestagent/agents/pa_agent/ctf_dispatcher.py`
- 修复点：
  - 将 `python3 - <<'PY'` 转为临时 `.py` 文件执行
  - 将 `/tmp/...` 重写到本机临时目录
  - 将 `python3` 替换为当前解释器路径
- 价值：
  - 让 LLM shell follow-up 在 Windows `LocalRuntime` 下至少具备基本可执行性。

### 5. LLM prompt 强化已有 runtime 事实

- 文件：`pentestagent/agents/pa_agent/ctf_dispatcher.py`
- 修复点：
  - 注入 runtime 环境摘要
  - 注入已确认的 `source_fetch_write_ssrf` exploit 上下文
  - 注入最近已确认执行过的 fetch target
  - 明确要求不要重复抓取同一个首页源码
- 价值：
  - 让 LLM 更容易基于已有证据做“下一步利用”，而不是重新回到“读源码”。

### 6. observation kind 级 retained context

- 文件：`pentestagent/agents/pa_agent/ctf_state.py`
- 修复点：
  - 新增 `recent_observations(kind=..., limit=...)`
- 价值：
  - 不再依赖“最后 N 条 observation”这种容易被长 run 冲掉的视窗，而是按 kind 取最近匹配项。

### 7. source_fetch/source_hint 相关上下文按 kind 回看

- 文件：`pentestagent/agents/pa_agent/ctf_dispatcher.py`
- 修复点：
  - `source_fetch_write_ssrf` exploit observation
  - `local_challenge_source_hint`
  - source hint 去重与路径提取
  - 全部改为按 observation kind 回看
- 价值：
  - run12/run13 已验证：LLM follow-up 在长 probe 历史后仍能保留 `source_fetch_write=true` bridge。

### 8. 弱根路径 GET guard 收紧

- 文件：`pentestagent/agents/pa_agent/reasoning.py`
- 修复点：
  - 对 `GET /`
  - `payload: {method: GET}`
  - 以及相对根路径形式，统一视作可能退化成同域首页 GET
  - 但保留 `candidate_file_urls` / `candidate_urls` 这类真实 SSRF follow-up，不误伤桥接请求
- 价值：
  - 把“重复首页 GET”尽量拦在 reasoning 层，而不是等到 live 里再浪费一步。

## 当前仍未解决的缺口

- 终端摘要中的 `Loops: 0 / Tools: 0` 仍与 session ledger 不一致，展示层口径还没修。
- run12/run13 已证明执行桥接稳定性在提升，但 planner 仍会偶发提出根路径弱动作，说明后续应重点排查：
  - 这类 proposal 为什么在 live 中仍能进入 `llm_action`
  - `PreActionReasoning` 与实际 LLM proposal 之间是否存在状态可见性/形态不一致
  - 是否需要把“confirmed exploit primitive 之后的低增益 GET”进一步提升为确定性 stop/replan 条件

## 回归与证据

- focused 回归：
  - `tests/unit/interface/test_cli_local_asset_contract.py`
  - `tests/unit/agents/test_ctf_reasoning.py`
  - `tests/unit/agents/test_ctf_dispatcher.py`
- live 证据：
  - `loot/ssrfme_e2e_2026-06-10_run6.log`
  - `loot/ssrfme_e2e_2026-06-10_run7.log`
  - `loot/ssrfme_e2e_2026-06-10_run8.log`
  - `loot/ssrfme_e2e_2026-06-13_run11.log`
  - `loot/ssrfme_e2e_2026-06-13_run12.log`
  - `loot/ssrfme_e2e_2026-06-13_run13.log`
  - `loot/checkpoints/ctf-e5baedfb6a40.jsonl`
  - `loot/checkpoints/ctf-ff9af3c68585.jsonl`
  - `loot/checkpoints/ctf-f256bd62c637.jsonl`
  - `loot/checkpoints/ctf-a8a21324f7ed.jsonl`
  - `loot/checkpoints/ctf-3eab53ecf0e4.jsonl`
  - `loot/checkpoints/ctf-82062fa9c801.jsonl`
  - `loot/session_ledgers/ctf-e5baedfb6a40.jsonl`
  - `loot/session_ledgers/ctf-ff9af3c68585.jsonl`
  - `loot/session_ledgers/ctf-f256bd62c637.jsonl`
  - `loot/session_ledgers/ctf-a8a21324f7ed.jsonl`
  - `loot/session_ledgers/ctf-3eab53ecf0e4.jsonl`
  - `loot/session_ledgers/ctf-82062fa9c801.jsonl`

## 结论

这轮最重要的结论不是“SSRF 还不行”，而是：

- SSRF/source-leak 原语已经被系统稳定发现并执行。
- retained bridge 也已经进入 live 主链，说明“confirmed primitive 会不会被长 run 忘掉”这个问题已被部分收紧。
- 当前主阻塞已经进一步上移到：
  - post-source-leak 的 planner 收敛质量
  - 弱动作 proposal 为什么仍能穿过 live reasoning
  - 展示层 `Loops/Tools` 汇总口径失真

因此后续路线应该继续按照“先通用修复，再 live E2E 回归”的节奏推进，而不是写这道题的专用脚本。
