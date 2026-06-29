# 上线验收 — 三类 profile 端到端 + live 真跑 handoff

对应《FlagHunter_运行方式愿景与上线问题清单_2026-06-28_V1.md》线 210-211 的上线门:
**三类 profile（CTF / 攻防演练 / 代码审计）各跑通真实样例,回归全绿 + import-linter /
reachability / taxonomy 三道治理全 KEPT。**

---

## 1. in-session 确定性回归门（已入仓·可重复）

这是上线门的**自动化部分**——无需 live LLM / 网络靶机,CI 可跑,改动悄悄打断
已解链即 FAIL。

```bash
source .venv/Scripts/activate

# CTF profile(aggressive/url)：4 条金标准 fixture 逐一确定性复现
python -m pytest tests/eval/test_replay_harness.py -q

# 攻防演练(conservative/blackbox)+ 代码审计(source) profile 端到端验收
python -m pytest tests/eval/test_profile_acceptance.py -q

# 三道治理门
lint-imports                                                   # import-linter:4 contracts
python -m pytest tests/unit/agents/test_chain_reachability_invariant.py \
                 tests/unit/agents/test_strategy_reachability.py -q   # reachability
python -m pytest tests/unit/knowledge/test_attack_taxonomy.py -q      # taxonomy/coverage 30/30
```

**覆盖映射**：
| profile | entry / 激进度 | 真样例 | 端到端断言 |
|---------|----------------|--------|------------|
| ctf | url / aggressive | 4 replay fixtures | 逐条复现录得的 flag |
| pentest（攻防演练）| blackbox / conservative | 同 4 fixtures 在 conservative 下重驱 | conservative 覆盖不打断非直放链 |
| code_audit | source / conservative | `tests/fixtures/samples/source_audit_app/`（真实漏洞 Python 源码）| profile→source 进场→scan→可疑点(CWE-502/78/89)→P12 攻击面面板 |

**诚实边界**：in-session 门是 **确定性回归**（replay 重驱真 dispatcher + 纯 Python
真扫源码），不是 live 真跑。replay 用 scripted 响应(无 live LLM/靶机);code_audit
的 source_audit 本就纯 Python 故是真扫。live 真跑见 §2。

---

## 2. live 真跑 handoff（需用户 infra：API key + 靶机；在 `! ` 里整段粘贴）

> 前置：`.env` 里 `ANTHROPIC_API_KEY` + `FLAGHUNTER_MODEL` 已配；靶机/源码就位。
> ⚠️ live 真跑会发起真实 LLM 调用并可能跑真爆破工具(gobuster/ffuf 分钟级)——
> 仅对**有授权**的目标跑。

```bash
# —— CTF profile：给 URL，激进走最短链 ——
flaghunter run -t http://<your-ctf-host>:<port> --profile ctf --ctf-type web

# —— 攻防演练 profile：黑盒目标，保守先确认 ——
flaghunter run -t http://<authorized-target> --profile pentest

# —— 代码审计 profile：给源码目录，白盒优先 ——
flaghunter run --profile code_audit --challenge-path <path-to-source-tree>
```

跑完后看 `loot/notes.json`（findings）、`loot/provenance.jsonl`（工具调用溯源）、
`flaghunter chains`（涌现链 + P7 评分）确认链路;web/TUI 黑板快照里看 P12 攻击面面板。

---

## 3. 验收判定

- §1 全绿 + §2 三类各至少一次 live 跑产出预期(CTF/演练出 flag 或有效推进、
  code_audit 扫出真可疑点) ⇒ **上线门通过**。
- §1 是合并前必过的硬门;§2 是发布前的人工 live 抽验。
