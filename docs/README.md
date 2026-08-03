# 项目文档总入口

> 状态：Active / Canonical Index
>
> 最近更新：2026-07-31
>
> 目标：只保留少量权威入口；历史设计、审计、阶段记录和单题 WP 作为证据资料，不与当前路线竞争。

---

## 1. 最短阅读路径

第一次接手项目只需按顺序阅读：

1. `README.md`：项目定位、能力和快速开始。
2. `AGENTS.md`：仓库结构、架构规则和开发约束。
3. `docs/optimization-guide.md`：当前问题、优化优先级、功能域、代码质量、运维、安全、数据、成本和实施路线。

综合优化、现状判断和后续优先级以第 3 份为准，不再从旧 Gap Report、Roadmap 或阶段审计中拼接“最新结论”。

---

## 2. 当前权威文档

| 领域 | 权威入口 | 作用 |
|---|---|---|
| 产品与使用 | `README.md` | 项目定位、稳定能力、安装和运行入口 |
| 开发约束 | `AGENTS.md` | 架构边界、命名、proof authority、协作纪律 |
| 综合优化 | `docs/optimization-guide.md` | 唯一综合优化与治理指南和最新阶段路线 |
| Clean Architecture | `docs/dev/FlagHunter_Clean_Architecture_Development_Guidelines_v0.1_2026-07-04.md` | Domain、Application、Ports、Adapters、Presentation 和 Composition Root 规则 |
| 中立命名 | `docs/dev/FlagHunter_Domain_Neutral_Naming_Policy_v0.1_2026-07-04.md` | 新公共 contract/port/domain 命名规则 |
| 真实能力评估 | `docs/dev/真实解题率基线_方法论与harness_2026-07-25_V1.md` | 分层 corpus、judge、runner、cold/warm 和成本护栏 |
| 版本变化 | `CHANGELOG.md` | 对协作者可感知的版本变化 |
| 发布 | `docs/release-policy.md`、`docs/release-checklist.md`、`docs/release-playbook.md` | 当前发布规则、检查和操作；后续计划收敛为单一发布手册 |

仓库级协作说明只维护 `AGENTS.md`，不再按具体 coding agent、模型或 provider 创建重复的项目说明文件。具体品牌名称仅在真实 provider 兼容、客户端接入或历史证据中出现，不承担项目身份和治理入口职责。

---

## 3. 其他文档如何理解

### 3.1 架构决策与迁移记录

以下类型记录“当时为什么这样设计”和“迁移如何进行”，用于追溯，不自动代表当前状态：

- `FlagHunter_架构决策记录_*`
- `FlagHunter_目标架构_*`
- `FlagHunter_Clean_Architecture_Migration_Playbook_*`
- `FlagHunter_Module_Boundary_Review_*`
- `FlagHunter_Claim_VerificationRecord_*`

发生重大架构决策时仍应新增 ADR；综合结论和执行优先级同步回写 `docs/optimization-guide.md`。

### 3.2 旧规格、Gap Report 和 Roadmap

以下文档是历史阶段快照，不再作为当前路线真相源：

- `FlagHunter_CTF_Solver_Spec_*`
- `FlagHunter_CTF_Solver_Gap_Report_*`
- `FlagHunter_CTF_Solver_Implementation_Roadmap_*`
- `FlagHunter_P1_Claim_Verification_Backlog_*`
- 旧结构债、阶段优化方案和上线问题清单。

需要了解历史缺口或迁移原因时再查阅；当前优先级统一看项目优化与治理指南。

### 3.3 Baseline、审计和验收记录

`基准_*`、live 台账、可达性审计、失败 characterization 和 eval 记录属于事实证据层。它们可以更新具体测量结果，但不单独维护综合路线。

### 3.4 学习笔记和单题 WP

- `DASCTF_*`：题目过程、能力证据和知识沉淀。
- `Cairn_*`、学习笔记、文章复盘：设计背景和参考资料。

这些资料进入知识检索时应标记为历史/参考，不覆盖当前代码和运行证据。

---

## 4. 冲突处理顺序

文档或代码结论冲突时，按以下顺序判断：

1. 当前 live runtime 行为。
2. 当前 trace、receipt、traffic 和 actively served assets。
3. 当前进程配置与持久化状态。
4. 当前仓库代码。
5. 当前权威文档。
6. 历史设计、审计、Roadmap、注释和学习笔记。

代码用于解释运行真相，历史文档不得覆盖已变化的实现。

---

## 5. 文档维护规则

1. 同一主题只能有一份 Active/Canonical 文档。
2. 综合优化只更新 `docs/optimization-guide.md`，不再创建带日期、项目名或工具名的新优化方案。
3. 历史文档保留原事实，只增加 Historical/Superseded 状态和替代指向。
4. README 只描述稳定、可验证的用户能力，不承载详细开发 backlog。
5. AGENTS 只维护开发必须遵守的不变量，不写阶段进度日记。
6. Baseline 文档只记录测量方法、环境和结果，不单独发明架构路线。
7. 版本、路径、配置和链接变化后同步更新本入口。
8. 每个 minor release 至少复查一次权威文档的状态和链接。

---

## 6. 当前唯一综合优化与治理入口

`docs/optimization-guide.md`

该文档已经合并：

- 当前静态审计和高风险事实。
- 架构与 proof authority 不变量。
- 各功能域职责、问题、优化方法、质量检测和预期效果。
- 代码质量检测与分层门禁。
- 部署、监控、告警、备份、恢复、发布和事件响应。
- 控制面安全、供应链、schema、持久化、性能和成本。
- 容易遗漏的跨平台、多用户、配置、时间、ID、回压和文档债问题。
- 分阶段 backlog、实施流程和完成定义。
