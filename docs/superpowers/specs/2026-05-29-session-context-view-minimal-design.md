# Session Context View 最小设计（Harness Phase A-4）

日期：2026-05-29  
仓库：`D:\webstudy\FlagHunter`

---

## 目标

在已有：

- `session_ledger`
- `artifact_registry`
- `checkpoint_store`

之后，补一个**可查询的运行态聚合视图**，把“已经记录下来的 harness 真相”变成一个稳定消费面。

本轮目标只做：

1. 基于 `run_id` 聚合最近事件
2. 聚合该 run 的 artifact handles
3. 聚合 latest checkpoint 的关键状态摘要
4. 接到 Web task detail payload，形成第一处真实消费

本轮不做：

- prompt 注入
- MCP inspection 接线
- resume 自动恢复
- 前端展示改造

---

## 最小模块落点

新增：

- `D:\webstudy\FlagHunter\pentestagent\knowledge\session_context.py`

核心对象：

- `SessionContextView`

最小输入：

- `ledger_root`
- `artifact_root`
- `checkpoint_root`
- `run_id`

最小输出：

```json
{
  "runId": "run-123",
  "recentEvents": [],
  "artifacts": [],
  "latestCheckpoint": null
}
```

---

## 输出形状

### `recentEvents`

```json
[
  {
    "type": "task_finished",
    "t": "2026-05-29T00:00:00+00:00",
    "payload": {}
  }
]
```

### `artifacts`

```json
[
  {
    "artifactId": "artifact-xxxx",
    "kind": "artifact",
    "title": "ctf_backup_candidate",
    "path": null,
    "location": "http://ctf.local/www.zip",
    "producer": "notes",
    "metadata": {},
    "t": "2026-05-29T00:00:00+00:00"
  }
]
```

### `latestCheckpoint`

```json
{
  "checkpointId": "checkpoint-xxxx",
  "label": "task_finished",
  "t": "2026-05-29T00:00:00+00:00",
  "metadata": {"success": true},
  "stopReason": "flag_verified",
  "verifiedFlags": ["flag{ok}"],
  "runtimeFlags": [],
  "artifactCount": 1,
  "observationCount": 3
}
```

---

## 为什么先接 Web task detail

这一步最值钱的地方不在“多写一个工具类”，而在于它成为了**第一处真实消费点**。

把它先接到：

- `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`

的 `task detail payload`，收益最大：

1. 已有 `run_id`，不用重开 ingress
2. 不需要先改前端布局
3. 立刻让 detail truth-source 多一条真实来源
4. 后续 MCP / prompt / resume 可以直接复用同一视图

---

## Web detail 最小接线

`_task_detail_payload(...)` 新增：

- `sessionContext`
- `detailSource.sessionContext`

其中：

- 有 harness 数据时：`detailSource.sessionContext = "harness"`
- 否则：`detailSource.sessionContext = "unobserved"`

---

## 验证口径

本轮通过标准：

1. `SessionContextView` 单测能证明：
   - recent events 可读
   - artifacts 可读
   - latest checkpoint 可读
   - 无数据时返回稳定空形状

2. Web detail 单测能证明：
   - 当 `run_id` 对应 harness 数据存在时
   - `task detail payload` 暴露 `sessionContext`
   - `detailSource.sessionContext == "harness"`

3. 既有 harness 单测与 web detail 默认形状不退化

