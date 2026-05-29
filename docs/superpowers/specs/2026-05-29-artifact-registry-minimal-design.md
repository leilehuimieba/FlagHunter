# Artifact Registry 最小设计（Harness Phase A-2）

日期：2026-05-29  
仓库：`D:\webstudy\FlagHunter`

---

## 目标

在已有 `session_ledger` 之后，补一个**最小可用的 artifact handle 主线**，先解决：

1. CTF 主链路里产生的 artifact 不再只有裸路径 / notes 文本
2. 同一个 `run_id` 下的 artifact 可以被统一列出
3. 后续 Web / MCP / resume / handoff 有稳定 registry 可消费

本轮只做 **append-only artifact registry**，不做：

- checkpoint / resume
- Web attachments 全量接管
- MCP / Web 展示层改造
- artifact 去重 / 生命周期治理

---

## 最小数据合同

每条 artifact record 先统一成下面形状：

```json
{
  "artifact_id": "artifact-xxxxxxxxxxxx",
  "ts": "2026-05-29T00:00:00+00:00",
  "run_id": "ctf-run-1",
  "kind": "artifact | credential",
  "title": "ctf_backup_candidate",
  "path": "D:\\path\\to\\file",
  "location": "http://ctf.local/www.zip",
  "producer": "notes | dispatcher | upload",
  "metadata": {}
}
```

其中：

- `artifact_id`：统一 handle
- `run_id`：跨日志 / task / handoff 的主键
- `kind`：先只区分 `artifact` 与 `credential`
- `title`：当前沿用现有 note key / artifact name
- `path` / `location`：允许二选一或并存
- `producer`：标识产出链路
- `metadata`：保留原始语义

---

## 最小模块落点

新增：

- `D:\webstudy\FlagHunter\pentestagent\harness\artifact_registry.py`

职责：

1. `register_artifact(...)`
2. `list_artifacts(run_id)`
3. `get_artifact(artifact_id)`

实现原则：

- 轻量
- append-only
- JSONL
- 不引入数据库

---

## 存储策略

先按 `run_id` 分文件：

- `loot/artifact_registry/<run_id>.jsonl`

这样可以直接复用 `session_ledger` 的存储习惯，保持：

- 调试简单
- 人工可读
- 后续 easy handoff

---

## 最小接入点

### 1. `CTFTaskDispatcher.run(...)`

run 启动时初始化 registry，并绑定当前 `run_id`。

### 2. `CTFTaskDispatcher._store_note(...)`

当：

- `category == "artifact"`
- `category == "credential"`

时，除了保留现有：

- `notes`
- `state.add_artifact(...)`

还要再向 registry 注册一份 handle record。

---

## 为什么这一刀值最高

这一步不会大改现有主干，却能立刻让系统从：

- `state.artifacts`
- `notes`
- 裸路径 / 裸 URL

向统一 artifact registry 收口。

它是后续这些能力的共同前置：

1. Web / MCP artifact truth view
2. task detail 附件真值化
3. handoff / resume 的 artifact 引用
4. checkpoint 与 session context 按 handle 装配

---

## 验证口径

本轮通过标准：

1. registry 单测能证明：
   - 能注册 record
   - 能按 `run_id` 列出
   - 能按 `artifact_id` 读取

2. dispatcher 单测能证明：
   - `artifact` note 仍写入 `state.artifacts`
   - 同时 registry 新增一条 record
   - record 至少包含：
     - `run_id`
     - `kind`
     - `title`
     - `producer`
     - `location/path`
     - `metadata`

3. 既有 `session_ledger` / 本地题集成回归不回退

