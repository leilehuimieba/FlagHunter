# FlagHunter 项目级 Source-of-Truth 状态卡（2026-06-01）V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 角色：项目级当前事实总览 / 接手恢复卡 / 下一阶段决策底稿
>
> 这份文档只回答一件事：**“现在这个项目到底真实到哪一步了？”**

---

## 1. 当前一句话结论

> **FlagHunter 已经完成了 Web Console 真值化收口、Mode Router 入口合同接入、Harness 基础壳层建立，并把 control decision / first action 的运行时证据开始落到了 trace、checkpoint、session ledger。**

这意味着：

- 项目不再是“只有方向文档”
- 也不再是“只靠页面看数据的可视化壳”
- 当前真正需要推进的是 **判断能力**、**事实分层** 和 **调度收紧**

---

## 2. 当前主线

当前唯一主线：

> **主控 / Blackboard-lite / 调度收紧**

这条主线的优先顺序是：

1. 先会判断
2. 再会跑
3. 最后才扩张

### 2.1 当前判断标准

主控要先回答：

- 现在该不该跑
- 跑什么
- 为什么跑这个
- 跑完之后怎么判断结果

### 2.2 当前执行原则

执行面必须服从判断：

- 工具调用是判断后的动作，不是起点
- CLI / 本地脚本 / Kali / runtime 是执行面
- TUI 不再作为重点投入对象

---

## 3. 当前已确认的事实层

### 3.1 Web Console 已进入真值化收口状态

当前 Web Console 的主路径已经不是 mock 驱动，而是以真实数据 / 真实空态 / 真实动作合同为基础。

已确认的主路径包括：

- Dashboard
- Logs
- Settings
- Tasks / Task Detail
- Traces / Trace Detail
- Knowledge

当前已接通的关键动作包括：

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

### 3.2 Mode Router 已成为真实入口合同

当前 `mode / modeSubtype / goalStyle` 已经不是文档概念，而是实际入口合同的一部分。

它已经接入：

- Web 入口
- MCP 入口
- replay / retry / continue 派生链路

### 3.3 Harness 基础壳层已经存在

当前仓库已经有这些真实模块：

- `session_ledger`
- `artifact_registry`
- `checkpoint_store`
- `audit_events`
- `session_context`

这说明：

- 状态外置已经开始落地
- artifact 不再完全只是裸路径思维
- checkpoint / resume 的基础壳已经具备

### 3.4 Local Challenge / artifactPaths 真实样本链路已经成型

当前项目已经不只是“能跑任务”，而是开始有一条明确的本地样本主线：

- `challengePath`
- `artifactPaths`
- `runtime-only`
- `zip / source / docker-compose / 日志`

这条线是下一阶段最重要的实战牵引之一。

### 3.5 control decision 运行时证据链已开始稳定

当前已经可以确认：

1. `controlDecision` 不是只存在于入口 payload
2. coordinator 首动作不是只存在于代码意图
3. `dispatcher_started` / checkpoint / Web Trace 已经开始能承接这条链

这意味着当前项目正在从“可解释”走向“可证明”。

---

## 4. 当前已经稳定的 source of truth 组合

下面这些文件可以认为是当前阶段最接近真相的文档组合：

1. `D:\webstudy\FlagHunter\docs\README.md`
2. `D:\webstudy\FlagHunter\README.md`
3. `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
4. `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_文档索引与状态矩阵_V1.md`
5. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_项目状态核对与下一步讨论底稿_2026-06-01.md`
6. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_下一阶段主线_主控_BlackboardLite_调度收紧_V1.md`
7. `D:\webstudy\FlagHunter\docs\dev\local_challenge_sample_matrix.md`
8. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_Harness优化方案_借鉴Cairn_V1.md`
9. `D:\webstudy\FlagHunter\docs\dev\Cairn_源码深度分析_围绕Blackboard与Dispatcher_V1.md`

---

## 5. 当前仍然存在的关键短板

### 5.1 还没有真正完成 Blackboard-lite

虽然方向已经明确，但现在还不是成熟黑板：

- 事实 / 猜测 / 待验证结论 / 决策记录 还没有完全成为统一共享板
- 主控调度还需要继续收紧
- worker / 主控 / 观察面之间的状态切片还可以更清楚

### 5.2 `ctf_dispatcher.py` 仍然偏大

当前 CTF 调度器还承担了太多粘合逻辑。

这说明：

- 结构债务还在
- 但它应该被放在“样本驱动牵引”的前提下继续处理
- 不能脱离样本与验证独自大拆

### 5.3 项目级入口文档虽然已补，但还需要持续维护

`docs/README.md` 已经补上了总入口，但它本身也要随着项目事实变化而更新。

这意味着：

- 文档不是一次写完就结束
- 文档必须跟着代码真相迭代

---

## 6. 当前明确不做的事情

下一阶段先不做：

- TUI 重点投入
- 没有样本牵引的大重构
- 继续优先加页面按钮
- 继续把重点放在更多 MCP 接入
- 先扩功能再补判断

---

## 7. 当前最值得做的事情

如果只看当前阶段，最值得做的是：

1. **主控判断能力收紧**
2. **control action 事件闭环**
3. **Blackboard-lite 候选动作池**
4. **最小 Eval Harness**
5. **继续用本地 challenge / artifact 样本逼出真实缺口**
6. **保持文档与代码真相同步**

---

## 8. 当前环境约定

本仓库后续测试与验证，优先使用：

```powershell
.\.venv\Scripts\python.exe
```

推荐测试口径：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

不要默认使用系统 Python 去判断项目是否回归，因为那很容易把环境问题误判成代码问题。

---

## 9. 接手与恢复时的建议阅读顺序

如果现在要重新恢复上下文，建议按这个顺序：

1. `docs/README.md`
2. `README.md`
3. `docs/web-console/FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
4. `docs/dev/FlagHunter_项目状态核对与下一步讨论底稿_2026-06-01.md`
5. `docs/dev/FlagHunter_下一阶段主线_主控_BlackboardLite_调度收紧_V1.md`
6. `docs/dev/local_challenge_sample_matrix.md`

---

## 10. 一句话收口

> **当前项目已经不是“再补页面”的阶段，而是进入了“先判断、再证明判断真的被执行、再扩张”的主控收紧阶段。**
