# FlagHunter 下一阶段执行方案：主控 / Blackboard-lite / Eval 三线合并 V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 文档角色：**下一阶段实际执行方案 / 讨论结论落地稿 / 后续任务排序依据**
>
> 最近同步：`2026-06-03`

---

## 1. 当前执行总判断

当前项目已经完成：

1. **入口判定显式化**
   - `mode`
   - `controlDecision`
   - `driver / facts / reason`

2. **首动作真实消费**
   - `verify_or_submit_flag`
   - `verify_runtime_signal`
   - `resume_from_checkpoint`
   - `collect_initial_facts`
   - `bootstrap_local_assets`

3. **运行时证据第一段成型**
   - `dispatcher_started`
   - checkpoint start metadata
   - Web Trace `outcomeEvents`

4. **样本主线已形成牵引**
   - `challengePath`
   - `artifactPaths`
   - `zip / source / docker-compose / runtime-only`

这说明当前主要矛盾已经不是“有没有功能”，而是：

> **agent 会不会判断、能不能按判断去执行、执行后能不能把事实重新写回系统。**

---

## 2. 三条主线与先后顺序

### 主线 A：主控 / Blackboard-lite / 调度收紧

这是第一优先级。

目标不是直接做重型 blackboard，而是先把最短判断链做实：

- 当前事实是什么
- 当前候选动作是什么
- 为什么先走这条
- 动作是否真的开始 / 完成 / 改变事实

### 主线 B：样本驱动 Eval / Harness

这是第二优先级，但必须紧跟。

目标：

- 继续让真实样本牵引优化
- 防止结构收口脱离真实收益

### 主线 C：知识与上下文分层

这是第三优先级。

目标：

- 区分长期知识、当前事实、临时记忆、待验证结论
- 减轻上下文膨胀
- 让不同 run 的沉淀可复用

---

## 3. 当前最小任务清单

### P0：控制链执行证据闭环

这一步是当前最值得立刻推进的任务。

#### 最小切口

1. `control_action_started`
2. `control_action_completed`
3. 首批 5 个 first action 已接入 started/completed 事件

#### 第一批覆盖动作

- `verify_or_submit_flag`
- `verify_runtime_signal`
- `resume_from_checkpoint`
- `collect_initial_facts`
- `bootstrap_local_assets`

#### 目标

- 证明 first action 确实开始执行
- 证明动作结果是 `ok / skipped / failed`
- 让 trace / ledger / checkpoint 看到一致事实

### P1：Blackboard-lite 候选动作池

#### 当前已落地第一刀

- `blackboardSnapshot.candidates`
- `blackboardSnapshot.activeDecision`

#### 下一步最小切口

- 让 candidates 从“投影视图”继续收紧到“可被调度消费的最小队列”
- 补 action results 与候选优先级变更依据

#### 目标

- 从单条 `nextAction` 升级为“主路径 + 备选路径”
- 让主控解释为什么当前优先这条

### P2：最小 Eval Harness

#### 最小切口

- easy_login 之外再补 1~2 个低成本样本
- 延续 `challengePath + artifactPaths`
- 优先能离线复跑、能快速定位缺口的样本

#### 目标

- 看系统是否真的先建立事实、再选择路径、再执行、再回写
- 能区分主控问题 / 工具问题 / 知识问题 / 上下文问题

---

## 4. 当前明确不做什么

下一阶段先不做：

- TUI 继续投入
- 大规模前端美化
- 没有样本牵引的大重构
- 无约束扩工具
- 过早扩复杂多智能体
- 为了架构而架构地大拆 `ctf_dispatcher.py`

---

## 5. 当前推荐开发节奏

建议继续保持这套节奏：

1. 主控盘点最高价值缺口
2. 先做最小设计
3. TDD：RED → GREEN
4. 窄回归
5. `git diff --stat`
6. commit / push
7. 同步交接文档与状态卡

---

## 6. 环境约定

本仓库后续测试与验证，优先使用：

```powershell
.\.venv\Scripts\python.exe
```

推荐测试口径：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

---

## 7. 一句话收口

> **下一阶段不要再平均扩功能，而要围绕“主控判断能力”推进三条主线：先补 control action 事件闭环，再做 blackboard-lite 候选动作池，然后用最小 Eval Harness 验证真实收益。**

