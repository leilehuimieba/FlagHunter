# FlagHunter Web 可视化控制台 Settings 字段持久化合同 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 文档角色：**Settings API / UI 持久化白名单合同**

---

## 1. 设计原则

1. 只有后端明确支持落盘的字段，前端才能开放编辑
2. 不支持字段保留展示价值，但必须明确标为只读
3. 返回成功时，至少要能通过后续 `GET /api/settings` 读回
4. 可能需要重启进程才能完全生效的字段，需要在结果中标记

---

## 2. 本轮允许编辑并持久化的字段

| 路径 | `.env` 键 | 备注 |
|---|---|---|
| `model.provider` | `FH_PROVIDER` | 供应商选择 |
| `model.apiBase` | `LITELLM_API_BASE` | LiteLLM / proxy base |
| `model.name` | `PENTESTAGENT_MODEL` | 主模型名 |
| `model.apiKey` | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | 仅在非掩码输入时写入 |
| `runtime.dockerEnabled` | `PENTESTAGENT_DOCKER` | local / docker 开关 |
| `runtime.workdir` | `PENTESTAGENT_WORKDIR` | 工作目录 |
| `budget.dailyTokenLimit` | `FH_DAILY_TOKEN_LIMIT` | 预算限制 |
| `budget.dailyCostLimit` | `FH_DAILY_COST_LIMIT` | 预算限制 |
| `budget.perTaskTokenLimit` | `FH_PER_TASK_TOKEN_LIMIT` | 预算限制 |
| `budget.alertAt` | `FH_BUDGET_ALERT_AT` | 告警阈值 |
| `knowledge.embeddingModel` | `PENTESTAGENT_EMBEDDINGS` | 嵌入模型 |
| `ctf.enabled` | `CPA_CTF_MODE` | CTF 模式开关 |
| `ctf.maxIterations` | `PENTESTAGENT_AGENT_MAX_ITERATIONS` | 迭代上限 |
| `ctf.autoRetry` | `CTF_AUTO_RETRY` | 自动重试 |
| `ctf.hintPolicy` | `CTF_HINT_POLICY` | hint 策略 |
| `ctf.hypothesisDepth` | `CTF_HYPOTHESIS_DEPTH` | 假设树深度 |
| `ctf.strategyMemory` | `CTF_STRATEGY_MEMORY` | 策略记忆开关 |
| `ctf.flagFormat` | `CTF_FLAG_FORMAT` | flag 正则 |
| `ctf.verifierUrl` | `CTF_VERIFIER_URL` | verifier endpoint |

---

## 3. 本轮只读字段

以下字段保留展示，但本轮不开放写入：

| 路径 | 原因 |
|---|---|
| `model.temperature` | 当前后端未建立稳定 env 合同 |
| `model.maxTokens` | 当前后端未建立稳定 env 合同 |
| `model.streaming` | 当前为固定行为，不做配置化 |
| `runtime.mode` | 当前真实落盘来源仍是 `dockerEnabled` 推导 |
| `runtime.autoSsh` | 未纳入本轮可验证持久化范围 |
| `runtime.sshConfigured` | 反映运行环境现状，不应由 UI 改写 |
| `runtime.sandboxNetwork` | 未纳入本轮可验证持久化范围 |
| `mcp.*` | 本轮不改 mcp server 配置合同 |
| `knowledge.enabled` | 当前真实语义仍由 embeddings 配置推导 |
| `knowledge.chunkSize` | 当前未做运行时可验证落盘 |
| `knowledge.overlap` | 当前未做运行时可验证落盘 |
| `knowledge.threshold` | 当前未做运行时可验证落盘 |
| `audit.*` | 当前仅展示，不做真实配置改写 |

---

## 4. 返回结果约定

`PUT /api/settings` 本轮应返回至少以下结构：

```json
{
  "ok": true,
  "saved": ["model.provider", "model.apiBase"],
  "ignored": ["model.temperature"],
  "restartRequired": ["model.provider", "model.apiBase", "model.name", "model.apiKey"]
}
```

其中：

- `saved`：本次明确写入的字段路径
- `ignored`：请求带来但本轮不支持写入的字段路径
- `restartRequired`：已写入，但可能要重启进程才完全生效的字段

---

## 5. 前端行为约定

1. 只读字段显示 lock / read-only 提示
2. 保存成功后，以后端返回的 `saved / ignored / restartRequired` 生成反馈
3. `discard` 回到最近一次成功 `GET /api/settings` 的值，而不是回到 mock
4. 如果 live API 不可达，不允许伪造“保存成功”

