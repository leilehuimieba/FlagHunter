# FlagHunter 文档总入口

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 最后更新：`2026-06-03`
>
> 目标：把当前项目最值得先读、先维护、先对齐的文档收口到一个低成本入口，避免把历史快照、规划草案、局部证据混在一起。

---

## 1. 先读什么

如果你是第一次接手当前项目，建议按下面顺序读：

1. `D:\webstudy\FlagHunter\README.md`
2. `D:\webstudy\FlagHunter\docs\README.md`
3. `D:\webstudy\FlagHunter\AGENTS.md`
4. `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
5. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_项目级source-of-truth状态卡_2026-06-01_V1.md`
6. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_交接文档_当前主线与第一批任务_2026-06-01_V1.md`
7. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_项目状态核对与下一步讨论纪要_2026-06-03_V1.md`
8. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_下一阶段执行方案_主控_BlackboardLite_Eval三线合并_V1.md`
9. `D:\webstudy\FlagHunter\docs\dev\local_challenge_sample_matrix.md`

---

## 2. 当前项目的文档分层

### 2.1 当前事实层

这几份最接近当前代码真相：

- `docs/web-console/FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
- `docs/web-console/FlagHunter_Web可视化控制台_文档索引与状态矩阵_V1.md`
- `docs/dev/FlagHunter_项目级source-of-truth状态卡_2026-06-01_V1.md`
- `docs/dev/FlagHunter_交接文档_当前主线与第一批任务_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目状态核对与下一步讨论纪要_2026-06-03_V1.md`
- `docs/dev/FlagHunter_下一阶段执行方案_主控_BlackboardLite_Eval三线合并_V1.md`
- `docs/dev/local_challenge_sample_matrix.md`
- `docs/dev/FlagHunter_reports目录状态与分层建议_2026-06-01_V1.md`
- `docs/dev/FlagHunter_仓库根目录剩余目录状态整理_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目文件分类索引_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目文件清理优先级清单_2026-06-01_V1.md`

### 2.2 背景分析层

这些用于解释为什么要这样收口，但不直接当作当前执行指令：

- `docs/dev/FlagHunter_Harness优化方案_借鉴Cairn_V1.md`
- `docs/dev/Cairn_源码深度分析_围绕Blackboard与Dispatcher_V1.md`
- `docs/dev/FlagHunter_下一阶段路线_目标驱动_BlackboardLite_V1.md`
- `docs/dev/御网杯_AI复盘文章学习笔记_离线复盘导向_V1.md`

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

当前更准确的成熟度判断是：

> **已经进入 blackboard-lite 收紧阶段，但还不是完整黑板模式。**

这条主线当前的优先顺序是：

1. **先会判断**
   - 先确认目标、入口、边界、事实、可用样本
   - 再决定要不要跑、先跑什么、为什么跑
2. **再会跑**
   - `tool / runtime / CLI / Kali / 本地脚本` 都属于执行面
   - 执行必须服从判断
3. **最后才扩张**
   - 不再平均扩功能
   - 不先上复杂多智能体
   - 不先做 TUI 投入

---

## 4. 当前阶段最值得关注的 3 件事

### 4.1 第一优先级：控制链执行证据闭环

当前已经稳定到：

- ingress `controlDecision`
- coordinator `first action`
- `dispatcher_started`
- checkpoint metadata
- Web Trace `outcomeEvents`

下一步最自然的缺口是：

- `control_action_started`
- `control_action_completed`

也就是把“决定了什么”推进到“真的开始做了什么、做完了什么、结果如何”。

### 4.2 第二优先级：最小 Eval Harness

继续让真实样本牵引后端收口，而不是脱离样本做结构优化。

当前建议持续使用：

- `challengePath`
- `artifactPaths`
- `zip / source / docker-compose / log / runtime-only`

### 4.3 第三优先级：知识与上下文分层

继续区分：

- 长期知识
- 当前 run 事实
- 当前 run 的候选动作 / 决策记录
- 临时失败原因 / 待验证结论

---

## 5. 运行环境说明

### 5.1 Python 解释器

本仓库当前默认使用虚拟环境：

```powershell
.\.venv\Scripts\python.exe
```

后续所有测试、脚本和验证命令，优先按这个解释器执行。

### 5.2 推荐测试口径

```powershell
.\.venv\Scripts\python.exe -m pytest
```

不要默认用系统 Python 判断是否回归，否则很容易把环境问题误判成代码问题。

---

## 6. 当前明确要做 / 不做

### 要做

- 主控判断能力收紧
- control action 事件闭环
- Blackboard-lite 候选动作池最小设计
- 本地 challenge / artifact / runtime 样本驱动优化
- 继续维护低成本、可随时交接的状态文档

### 先不做

- TUI 继续投入
- 大规模前端美化
- 没有样本牵引的大重构
- 复杂 MCP 扩张
- 为了架构而架构的 dispatcher 大拆

---

## 7. 文档维护规则

以后如果改了下面任意一类内容，请同步更新对应文档：

- 入口模式 / 控制合同
- Web Console 主路径事实
- Harness / ledger / artifact / checkpoint / trace
- 本地 challenge 样本矩阵
- 下一阶段主线优先级
- 可交接状态卡

维护原则只有一句话：

> **以最新代码真相为准，文档只记录已经确认的事实、已决定的优先级和已经对齐的执行边界。**

