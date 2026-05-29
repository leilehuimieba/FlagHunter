# Harness Audit Events 最小设计（Phase A-5）

日期：2026-05-29  
仓库：`D:\webstudy\FlagHunter`

---

## 目标

在已有：

- `session_ledger`
- `artifact_registry`
- `checkpoint_store`
- `SessionContextView`

之后，把**关键 harness 动作也写回统一事件流**，避免 session context 只能看到结果、看不到动作。

本轮最小目标只补两类事件：

1. `artifact_registered`
2. `checkpoint_written`

---

## 为什么现在做

如果 artifact 和 checkpoint 只存在于独立 store 中，而不进入统一事件流，那么：

- 时间线不完整
- detail timeline 难解释“什么时候产出了 artifact / checkpoint”
- 后续 handoff / audit / resume 只能多源拼接

所以这一刀的价值是：

> 让关键存储动作也成为可观察事件。

---

## 最小接入点

### 1. `CTFTaskDispatcher._register_artifact_record(...)`

当 artifact registry 注册成功后，同步写：

```json
{
  "event_type": "artifact_registered",
  "payload": {
    "artifact_id": "...",
    "kind": "artifact",
    "title": "ctf_flag",
    "location": "...",
    "path": null,
    "producer": "notes"
  }
}
```

### 2. `CTFTaskDispatcher._write_checkpoint(...)`

当 checkpoint store 写入成功后，同步写：

```json
{
  "event_type": "checkpoint_written",
  "payload": {
    "checkpoint_id": "...",
    "label": "task_finished",
    "metadata": {}
  }
}
```

---

## 事件边界

本轮仍然不做：

- tool called / tool finished 统一事件化
- recovery / verifier 之外更多执行明细
- Web timeline 全量切换到 harness event source

只收口最关键的 harness 存储动作。

---

## 验证口径

本轮通过标准：

1. artifact note → artifact registry 的路径会新增 `artifact_registered`
2. dispatcher run 的 checkpoint 路径会新增 `checkpoint_written`
3. `SessionContextView` 与 `web_server task detail` 相关测试不退化

