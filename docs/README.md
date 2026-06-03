# FlagHunter 文档总入口

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 目标：把当前项目最值得先读、先维护、先对齐的文档收口到一个低成本入口，避免再把历史快照、规划草案、局部证据混在一起。

---

## 1. 先读什么

如果你是第一次接手当前项目，建议按下面顺序读：

1. `D:\webstudy\FlagHunter\README.md`
2. `D:\webstudy\FlagHunter\docs\README.md`
3. `D:\webstudy\FlagHunter\AGENTS.md`
4. `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
5. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_下一阶段主线_主控_BlackboardLite_调度收紧_V1.md`
6. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_下一阶段执行方案_主控_BlackboardLite_Eval三线合并_V1.md`
7. `D:\webstudy\FlagHunter\docs\dev\local_challenge_sample_matrix.md`

---

## 2. 当前项目的文档分层

### 2.1 当前事实层

这几份是当前最接近“事实”的文档：

- `docs/web-console/FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
- `docs/web-console/FlagHunter_Web可视化控制台_文档索引与状态矩阵_V1.md`
- `docs/dev/FlagHunter_reports目录状态与分层建议_2026-06-01_V1.md`
- `docs/dev/FlagHunter_仓库根目录剩余目录状态整理_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目文件清理优先级清单_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目文件分类索引_2026-06-01_V1.md`
- `docs/dev/FlagHunter_交接文档_当前主线与第一批任务_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目级source-of-truth状态卡_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目状态核对与下一步讨论底稿_2026-06-01.md`
- `docs/dev/FlagHunter_下一阶段主线_主控_BlackboardLite_调度收紧_V1.md`
- `docs/dev/FlagHunter_下一阶段执行方案_主控_BlackboardLite_Eval三线合并_V1.md`
- `docs/dev/local_challenge_sample_matrix.md`

### 2.2 背景分析层

这些文档用于解释为什么要这样做，但不直接当作当前执行指令：

- `docs/dev/FlagHunter_Harness优化方案_借鉴Cairn_V1.md`
- `docs/dev/Cairn_源码深度分析_围绕Blackboard与Dispatcher_V1.md`
- `docs/dev/FlagHunter_下一阶段路线_目标驱动_BlackboardLite_V1.md`

### 2.3 规划与执行层

这些文档用于任务拆解、阶段执行和验收：

- `docs/superpowers/plans/2026-05-29-harness-optimization-plan.md`
- `docs/release-policy.md`
- `docs/release-checklist.md`
- `docs/release-playbook.md`

---

## 3. 当前项目的主线判断

当前主线已明确收缩为：

> **主控 / Blackboard-lite / 调度收紧**

当前进一步落实后的下一阶段执行判断是：

> **先做主控 / Blackboard-lite / 调度收紧，再用最小 Eval Harness 验证，最后再扩知识与上下文编排。**

这条主线的优先顺序是：

1. **先会判断**
   - 先确认当前目标、入口、边界、可用事实
   - 再决定是否调用工具、调用什么工具、如何调用
   - 判断先于执行，执行服从判断

2. **再会跑**
   - `tool`、`runtime`、`cli`、`kali` 这些能力是“判断之后的执行面”
   - 没有判断，就没有高价值跑法

3. **最后才谈更复杂的调度和扩张**
   - 先把最短链路走通
   - 再讨论是否增加更多 agent / 更多入口 / 更多自动化

---

## 4. 运行环境说明

### 4.1 Python 解释器

本仓库当前默认使用虚拟环境：

```powershell
.\.venv\Scripts\python.exe
```

后续所有测试、脚本和验证命令，优先按这个解释器执行。

### 4.2 推荐测试口径

```powershell
.\.venv\Scripts\python.exe -m pytest
```

如果你用的是系统 Python，而不是 `.venv`，请先确认依赖是否完整，否则可能出现“代码没坏、环境先坏”的假象。

---

## 5. 当前阶段要做什么，不做什么

### 要做

- 主控判断能力收紧
- Blackboard-lite 事实 / 猜测 / 待验证结论 / 决策记录分层
- 调度逻辑收敛到最短路径
- 本地 challenge / artifact / runtime 样本驱动优化
- 继续维护低成本、可复用的状态文档

### 先不做

- TUI 继续加投入
- 大量新增页面动作
- 复杂 MCP 扩张
- 没有样本牵引的大重构

---

## 6. 降低接手成本的最小文档集合

如果你只想快速恢复当前项目状态，优先看这 5 份：

1. `docs/README.md`
2. `README.md`
3. `docs/web-console/FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
4. `docs/dev/FlagHunter_项目文件清理优先级清单_2026-06-01_V1.md`
5. `docs/dev/FlagHunter_项目文件分类索引_2026-06-01_V1.md`
6. `docs/dev/FlagHunter_交接文档_当前主线与第一批任务_2026-06-01_V1.md`
7. `docs/dev/FlagHunter_项目级source-of-truth状态卡_2026-06-01_V1.md`
8. `docs/dev/FlagHunter_下一阶段主线_主控_BlackboardLite_调度收紧_V1.md`
9. `docs/dev/FlagHunter_下一阶段执行方案_主控_BlackboardLite_Eval三线合并_V1.md`
10. `docs/dev/local_challenge_sample_matrix.md`

这套组合的目标是：

- 少读历史
- 少读猜测
- 先读当前事实
- 再读下一阶段怎么做

---

## 7. 文档维护规则

以后如果你改了下面任意一类内容，请同步更新对应文档：

- 入口模式合同
- Web Console 主路径真相
- Harness / ledger / artifact / checkpoint
- 本地 challenge 样本矩阵
- 下一阶段主线优先级

维护原则只有一句话：

> **以最新代码真相为准，文档只记录已经确认的事实、已决定的优先级和已经对齐的执行边界。**
