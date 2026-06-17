# FlagHunter 文档总入口

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 最后更新：`2026-06-18`
>
> 目标：把当前最值得先读、先维护、先对齐的文档收口到一个低成本入口。
> 历史快照、阶段验收证据与已实现特性的设计草案已于 2026-06-18 清理，本入口只保留仍然有效的文档。

---

## 1. 先读什么

如果你是第一次接手 FlagHunter，建议按下面顺序读：

1. `README.md` —— 项目定位、能力域、快速开始
2. `docs/README.md` —— 本文件，文档导航
3. `AGENTS.md` —— 仓库结构、架构模式、开发协作约束
4. `docs/dev/FlagHunter_架构决策记录_自顶向下骨架与两关节契约_2026-06-17_V1.md` —— 当前骨架与不变量(ADR)
5. `docs/dev/FlagHunter_红队智能体架构_对标顶级红队工程学_2026-06-17_V2.md` —— 架构方向锚

---

## 2. 文档分层

### 2.1 架构主线（当前最重要）

这三份是当前架构演进的核心，构成"领域知识 + 工程实现 + 已落地骨架"的闭环：

- `docs/dev/FlagHunter_架构决策记录_自顶向下骨架与两关节契约_2026-06-17_V1.md`
  —— 目标骨架、两关节契约、不变量 I1–I4、P0–P5 路线与进度（ADR，source of truth）
- `docs/dev/FlagHunter_红队智能体架构_对标顶级红队工程学_2026-06-17_V2.md`
  —— 对标 ATT&CK / UKC / Diamond / PTES / WSTG 与顶级红队思维，框架优化的方向锚
- `docs/dev/FlagHunter_agent引擎工程层优化_知识库补遗_2026-06-17_V1.md`
  —— 记忆 / 控制面 / 评估 / 工具四类工程层优化清单与 Do-First 短名单

愿景背景：

- `docs/dev/FlagHunter_红队黑板智能体架构学习笔记_2026-06-17_V1.md` —— 黑板群智体的初始愿景笔记（被 V2 取代，保留作背景）

### 2.2 背景分析与学习笔记

解释"为什么这样做"，不直接作为执行指令：

- `docs/dev/Cairn_源码深度分析_围绕Blackboard与Dispatcher_V1.md`
- `docs/dev/FlagHunter_Harness优化方案_借鉴Cairn_V1.md`
- `docs/dev/御网杯_AI复盘文章学习笔记_离线复盘导向_V1.md`

### 2.3 运营 / 验证事实层

最接近当前代码真相的运行与验证记录：

- `docs/dev/FlagHunter_live_CTF能力与端到端测试台账_2026-06-09_V1.md` —— live CTF 能力与端到端测试台账
- `docs/dev/CTF_web链可达性静态审计_2026-06-17_V1.md` —— web 链"能力够不够得着"的静态审计
- `docs/dev/FlagHunter_预存验收链失败_根因characterization_2026-06-16_V1.md` —— 预存验收链失败根因
- `docs/dev/FlagHunter_架构优化方案_黑板控制单元与façade收尾_2026-06-16_V1.md` —— 黑板控制单元与 façade 收尾方案
- `docs/dev/CHANGELOG_schema.md` —— changelog 结构约定

### 2.4 CTF 做题 WP（知识沉淀）

`docs/dev/DASCTF_*` —— 8 篇真实赛题做题/阶段 WP（piapiapia、urlstorage RPO、Unicorn shop、WarmUp、SSRFme、强网杯 Upload/随便注、easy_tornado SSTI），作为能力验证与知识沉淀保留。

### 2.5 发布与协作流程

- `docs/release-policy.md` / `docs/release-checklist.md` / `docs/release-playbook.md`
- `docs/label-strategy.md`
- `docs/agent-intelligence-roadmap.md`

---

## 3. 当前架构主线

主线已从"叶子打补丁"转向**自顶向下优化**：先保证骨架与层间契约优秀，再逐层下沉。

- **关节 A（入口→编排）**：4 个入口（TUI / CLI / web / MCP）统一经 `AgentSession` 门面装配，事件统一经中立 `EventBus`。
- **关节 B（编排→策略）**：`_execute_chain` registry 驱动分发；chains 子包化（mixin 拆分），逐步收敛 `ChainContext` 上帝对象透传。
- **不变量**：I1 依赖单向向下 / I2 唯一装配入口 / I3 事件单源 / I4 chain 不读上帝对象。

进度与下一步以 ADR（§2.1 第一份）的进展日志为准。

---

## 4. 运行环境说明

本仓库默认使用虚拟环境解释器：

```powershell
.\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe -m pytest
```

不要默认用系统 Python 判断是否回归，否则容易把环境问题误判成代码问题。

---

## 5. 文档维护规则

改了下面任意一类内容，请同步更新对应文档：

- 入口装配 / 事件契约（关节 A）→ ADR
- 策略分发 / chains 结构（关节 B）→ ADR
- 架构方向 / 红队工程学映射 → V2 与工程层补遗
- CTF 能力与端到端验证 → live 台账 / 可达性审计

维护原则只有一句话：

> **以最新代码真相为准，文档只记录已确认的事实、已决定的优先级和已对齐的执行边界。**
