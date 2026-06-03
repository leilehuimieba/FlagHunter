# FlagHunter 交接文档：当前主线与第一批任务（2026-06-01）V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 文档角色：**随时可交接的当前执行底稿**
>
> 维护原则：这份文档要随着项目推进持续更新，保证任意时点都能把当前状态交给下一位接手者。

---

## 1. 这份交接文档回答什么

只回答四件事：

1. 现在项目真实到哪一步了
2. 当前主线是什么
3. 第一批最小任务是什么
4. 接手的人下一步该先看什么、先做什么

---

## 2. 当前一句话状态

> **FlagHunter 已经完成 Web Console 真值化收口、Mode Router 入口合同接入、Harness 基础壳层建立，并把 control decision → first action → run-start event 链接到了 trace / checkpoint / session ledger。**

这意味着当前阶段不应该继续把重点放在：

- 继续加 TUI
- 继续加页面动作
- 继续扩复杂 MCP
- 不带样本的大重构

而应该放在：

- 主控判断能力
- Blackboard-lite 事实分层
- 调度链路收短
- 本地样本驱动验证

---

## 3. 当前主线

### 3.1 唯一主线

> **主控 / Blackboard-lite / 调度收紧**

### 3.2 主线顺序

1. 先会判断
2. 再会跑
3. 最后才扩张

### 3.3 核心判断

主控必须先能回答：

- 现在该不该跑
- 跑什么
- 为什么跑这个
- 跑完之后怎么判断结果

### 3.4 下一阶段执行顺序

下一阶段按下面顺序推进：

1. **主控 / Blackboard-lite / 调度收紧**
2. **最小 Eval Harness**
3. **知识与上下文编排**

对应文档：

- `D:\webstudy\FlagHunter\docs\dev\FlagHunter_下一阶段执行方案_主控_BlackboardLite_Eval三线合并_V1.md`

---

## 4. 第一批最小任务

这批任务是当前阶段最值得先做的 5 个任务。

### 任务 1：主控判断合同收口

目标：

- 先明确系统如何判断“该不该跑、跑什么、为什么跑”

最小切口：

- 输入：目标、入口、边界、事实、样本类型、资源状态
- 输出：是否执行、先做什么、是否探索、是否切换、是否调用工具、推荐动作
- 停止条件：已验证、无进展、风险超界、样本耗尽、需要人确认

完成标准：

- 任一任务开始时，主控先给出明确判断
- 判断可解释、可回放、可检查

---

### 任务 2：Blackboard-lite 事实层分层

目标：

- 把项目认知层分成最少但最有用的几类信息

最小切口：

1. 事实
2. 猜测
3. 待验证结论
4. 决策记录
5. 执行产物

完成标准：

- 系统不会把猜测当事实
- worker 回写能落到正确层
- 未来可以从这层做上下文摘要和回放

---

### 任务 3：调度链路收短

目标：

- 把“谁来做、先做什么、怎么切换、怎么停”收成更短的链路

最小切口：

- 先选最值钱路径
- 只在必要时扩散
- 工具调用必须服从判断
- TUI 不再作为重点投入对象

完成标准：

- 任务开始时先有路径选择
- 每次工具调用都能解释为什么现在该跑

---

### 任务 4：本地样本驱动验证闭环

目标：

- 用本地 challenge / artifact / runtime 样本持续逼出真实缺口

最小切口：

- challengePath
- artifactPaths
- zip / source / docker-compose / runtime-only

完成标准：

- 能跑完整一轮“判断 → 执行 → 回写 → 再判断”
- 不是只看页面能不能点，而是看系统是否真的能靠事实推进

---

### 任务 5：项目级文档同步收口

目标：

- 文档跟项目事实保持同步，降低接手成本

最小切口：

- `docs/README.md`
- `README.md`
- `docs/dev/FlagHunter_项目级source-of-truth状态卡_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目状态核对与下一步讨论底稿_2026-06-01.md`
- `docs/dev/FlagHunter_下一阶段主线_主控_BlackboardLite_调度收紧_V1.md`
- `docs/dev/local_challenge_sample_matrix.md`

完成标准：

- 新接手的人先读文档就能知道当前阶段
- 文档不会和代码真相脱节太多

---

## 5. 当前已确认的事实层

### 5.1 Web Console 已真值化收口

主路径：

- Dashboard
- Logs
- Settings
- Tasks / Task Detail
- Traces / Trace Detail
- Knowledge

已接通动作：

- create task
- hint
- stop
- retry
- continue
- runtime test
- knowledge reindex
- knowledge add doc
- knowledge open file
- MCP add server
- dashboard browse
- task detail attachment upload

### 5.2 Mode Router 已接入真实入口合同

当前 `mode / modeSubtype / goalStyle` 已经进入真实入口链路：

- Web
- MCP
- replay / retry / continue

### 5.3 Harness 基础壳层已建立

已有模块：

- `session_ledger`
- `artifact_registry`
- `checkpoint_store`
- `audit_events`
- `session_context`

### 5.4 本地样本主线已成型

当前最关键的样本输入合同：

- `challengePath`
- `artifactPaths`
- `runtime-only`
- `zip / source / docker-compose / 日志`

### 5.5 control decision 主链已进入“可回放”状态

当前已经稳定的真实链路包括：

1. **入口优先级**
   - `verified_flag > runtime_flag > resume_context > resume_bootstrap_hint > initial_fact_collection_requested > local_assets`

2. **coordinator 首动作合同**
   - `verify_or_submit_flag`
   - `verify_runtime_signal`
   - `resume_from_checkpoint`
   - `collect_initial_facts`
   - `bootstrap_local_assets`

3. **运行时证据回放**
   - `dispatcher_started` 事件
   - 起始 checkpoint metadata
   - Web Trace `outcomeEvents`

这说明当前主线已经从“判断是什么”推进到了“如何证明判断真的被执行”。

---

## 6. 当前明确不做

当前先不做：

- TUI 重点投入
- 继续优先加页面按钮
- 复杂 MCP 扩张
- 没有样本牵引的大重构
- 先扩功能再补判断

---

## 6.1 当前已确认的目录清理结论补充

为了避免下一位接手者重复确认，这里补一条当前已经确认的清理事实：

- `D:\webstudy\FlagHunter\null\` = **JADX 缓存目录**
- `D:\webstudy\FlagHunter\PowerShell 7.6.2\` = **JADX 配置目录**

两者不是项目主干事实，不应继续按核心目录理解。

当前状态：

- **两者均已从仓库根目录移除**
- 历史用途结论已保留在文档中，供后续交接参考

- `D:\webstudy\FlagHunter\tmp\edge13432.dmp` 也已处理完成：
  - 问题原因：当前用户只有读权限
  - 处理结果：补齐权限后已删除，`tmp/` 目录已不再作为根目录残留项存在

- `D:\webstudy\FlagHunter\logs\` 中过期的 `web_console_8081 ~ 8086` 端口日志也已清理：
  - 保留对象：`app/`、`audit/`、`blackboard.db`
  - 已清理对象：旧端口 `stdout/stderr` 日志

- `D:\webstudy\FlagHunter\reports\` 当前已完成状态整理：
  - 已确认它不是脏目录，而是高价值报告与产物目录
  - 当前已完成实际分层：`benchmarks / smoke / validation / writeups / exports`
  - 相关说明见：`docs/dev/FlagHunter_reports目录状态与分层建议_2026-06-01_V1.md`

---

## 7. 当前维护规则

### 7.1 文档更新顺序

以后更新按这个顺序来：

1. 先确认代码事实
2. 再更新交接文档
3. 再更新状态卡
4. 再更新入口文档
5. 最后再推进实现

### 7.2 解释器约定

本仓库后续测试与验证，优先使用：

```powershell
.\.venv\Scripts\python.exe
```

推荐测试口径：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

---

## 8. 接手顺序

如果要交接给下一位接手者，建议按这个顺序读：

1. `docs/README.md`
2. `README.md`
3. `docs/dev/FlagHunter_项目级source-of-truth状态卡_2026-06-01_V1.md`
4. `docs/dev/FlagHunter_项目状态核对与下一步讨论底稿_2026-06-01.md`
5. `docs/dev/FlagHunter_下一阶段主线_主控_BlackboardLite_调度收紧_V1.md`
6. `docs/dev/local_challenge_sample_matrix.md`

---

## 9. 一句话交接摘要

> **当前项目已从“Web 真值化收口”进入“主控判断收紧 + Blackboard-lite 落地 + 调度收短”的下一阶段；下一批任务优先做主控动作事件闭环、候选动作池和最小 Eval Harness。**
