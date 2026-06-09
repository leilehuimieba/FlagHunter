# generic_param_sqli 最小 Eval Pack

> 适用仓库：`D:\webstudy\FlagHunter`  
> 来源题型：DASCTF `[强网杯 2019]随便注`  
> 对应 WP：`docs/dev/DASCTF_强网杯2019_随便注_SQLi_做题WP_2026-06-09_V1.md`

## 1. 目标

这份 eval pack 只覆盖一个策略能力：

```text
GET 参数 SQLi -> SQL error -> stacked query -> show tables -> show columns -> handler read
```

它不把 DASCTF live URL 接进默认 benchmark。原因是外部靶场生命周期、登录态、容器实例和网络状态都不稳定，直接接入会让 CI / benchmark 误报。这里先把真实题沉淀成稳定的本地策略级回归。

---

## 2. 当前必须守住的行为

### Behavior A：capability registry 会在 CTF run 前预热

目的：

- 避免 `sql_injection_test` 能力表为空时，SQLi 链提前降级或走错路。

对应测试：

```text
tests/unit/agents/test_ctf_dispatcher.py::test_ctf_dispatcher_auto_primes_capabilities_for_generic_get_sqli
```

### Behavior B：普通 GET 参数表单会传给 sqlmap

目的：

- 不再只把 auth form 当作 SQLi 输入面。
- `?inject=test` 这类 GET 参数能进入 sqlmap 预探测。

对应测试：

```text
tests/unit/agents/test_ctf_dispatcher.py::test_ctf_dispatcher_auto_primes_capabilities_for_generic_get_sqli
```

### Behavior C：sqlmap 没直接出 flag 时，能落到 stacked-query 手工链

目的：

- 覆盖 `sqlmap是没有灵魂的` 这类题面。
- 当 `select` 被过滤时，继续尝试 `show tables` / `show columns` / `handler read first`。

对应测试：

```text
tests/unit/agents/test_ctf_dispatcher.py::test_ctf_dispatcher_falls_back_to_stacked_query_generic_get_sqli
```

### Behavior D：没有 sqlmap 时，manual HTTP fallback 仍然能解

目的：

- 只要 `http_request` 可用，就不因为缺少 sqlmap 放弃轻量 GET 参数 SQLi 链。

对应测试：

```text
tests/unit/agents/test_ctf_dispatcher.py::test_ctf_dispatcher_uses_stacked_query_fallback_without_sqlmap
```

### Behavior E：策略层认识 `generic_param_sqli`

目的：

- `generic_param_sqli` 不是私有 fallback，而是可被 hypothesis / registry / recovery / memory 识别的一等策略。

对应测试：

```text
tests/unit/agents/test_ctf_dispatcher.py::test_hypothesis_engine_generates_generic_param_sqli_for_get_form_surface
tests/unit/agents/test_ctf_dispatcher.py::test_ctf_dispatcher_uses_strategy_registry_for_generic_param_sqli
```

### Behavior F：关键解析工具有小单测保护

目的：

- PHP `var_dump` 字符串解析不能被改坏。
- 数字表名 / 反引号 identifier 不能被错误拼接。

对应测试：

```text
tests/unit/agents/test_ctf_dispatcher.py::test_ctf_dispatcher_extracts_php_var_dump_strings_for_stacked_sqli
tests/unit/agents/test_ctf_dispatcher.py::test_quote_sql_identifier_escapes_backticks_for_stacked_sqli
```

---

## 3. 最小 rerun 命令

```powershell
.\.venv\Scripts\pytest tests\unit\agents\test_ctf_dispatcher.py -k "auto_primes_capabilities_for_generic_get_sqli or falls_back_to_stacked_query_generic_get_sqli or uses_stacked_query_fallback_without_sqlmap or hypothesis_engine_generates_generic_param_sqli_for_get_form_surface or uses_strategy_registry_for_generic_param_sqli or extracts_php_var_dump_strings_for_stacked_sqli or quote_sql_identifier_escapes_backticks_for_stacked_sqli"
```

CLI auto subtype 合同：

```powershell
.\.venv\Scripts\pytest tests\unit\interface\test_cli_local_asset_contract.py -k "run_cli_preserves_auto_ctf_subtype_for_dispatcher"
```

---

## 4. Pass / Fail 口径

Pass：

- 上述策略级测试全部通过。
- `generic_param_sqli` 能成为 `winning_hypothesis_kinds`。
- flag 仍通过 verifier 进入 runtime / verified 证据流。

Fail：

- GET 参数表单只被当成普通 web recon。
- `unknown` 子类型阻断 auto detection。
- 只有 sqlmap 路径，没有 manual stacked-query fallback。
- 解析出表名 / 列名后没有继续读取 flag。

---

## 5. Live smoke 口径

live smoke 只在手工授权和靶场实例可用时运行：

```powershell
.\.venv\Scripts\pentestagent run -t "http://f1a805b770f343da5dbead3c.http-ctf2.dasctf.com:80" --mode ctf --max-loops 6 "拿到flag，优先少量HTTP侦察和表单测试，不要大规模扫描。"
```

期望摘要：

```text
detected_type=sqli
ctf_sqli_stacked_tables
ctf_sqli_columns_1919810931114514
Flag verified: DASCTF{07423849-4854-4b8e-99a3-90d6b83ede12}
```

