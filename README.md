# FlagHunter

[![Status](https://img.shields.io/badge/status-active-2ea44f)](https://github.com/leilehuimieba/FlagHunter/releases/tag/v0.1.0)
[![Version](https://img.shields.io/badge/version-v0.1.0-0969da)](https://github.com/leilehuimieba/FlagHunter/releases/tag/v0.1.0)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](#license)
[![Modes](https://img.shields.io/badge/runtime-local%20%7C%20docker%20%7C%20ssh-8250df)](#典型工作模式)
[![MCP](https://img.shields.io/badge/integration-MCP-1f6feb)](#典型工作模式)

> 面向 **CTF** 与 **合规渗透测试** 的 AI 代理框架  
> 基于 PentestAgent 演进，强化 **多 API 调度、CTF 专项能力、多 Agent 协作与可观测性**

---

## 快速导航

- [项目定位](#项目定位)
- [当前能力概览](#当前能力概览)
- [快速开始](#快速开始)
- [典型工作模式](#典型工作模式)
- [架构一览](#架构一览)
- [主要文档](#主要文档)
- [路线图](#路线图)
- [Changelog](./CHANGELOG.md)

> 当前 GitHub 仓库默认保持 **Private**，用于受控协作与内部演进；不会作为公开演示仓库使用。

---

## 项目定位

FlagHunter 是一个以 **攻防实战效率** 为目标的 AI 驱动安全测试项目。它保留了 PentestAgent 原有的轻量主循环、工具系统、TUI/CLI/MCP 接口，同时围绕真实使用场景补上了几条关键能力：

- **M1 多 API 调度与故障切换**：多 provider 路由、故障转移、消耗追踪
- **M2 CTF 专项增强**：Web / Crypto / Reverse / Pwn / Misc 多题型工作流
- **M3 报告输出**：面向交付的 HTML / Markdown 报告链路
- **M4 审计与边界控制**：作用域校验、执行审计、风险收口
- **M5 多 Agent 协作**：Worker 池、ShadowGraph、Swarm 路由
- **M6 性能优化**：缓存、并发、上下文与执行效率优化

> 适合两类场景：**CTF 靶场解题**，以及**有明确授权范围的安全测试自动化**。

---

## 当前能力概览

| 模块 | 方向 | 当前状态 |
|------|------|----------|
| **M0** | 原版核心能力（Agent Loop / Tool Calling / TUI / CLI / MCP） | ✅ 可用 |
| **M1** | 多 API 接入调度、故障切换、成本追踪 | ✅ 可用 |
| **M2** | CTF 增强工具包与专项工作流 | ✅ 可用 |
| **M3** | 报告生成与交付整理 | 🟡 持续完善 |
| **M4** | 审计守卫、作用域边界、执行留痕 | 🟡 持续完善 |
| **M5** | 多 Agent 协作、并行执行、信息素路由 | 🟡 持续完善 |
| **M6** | 性能优化、缓存、上下文压缩 | ⬜ 规划中 |

---

## 核心特点

### 1. 不是“纯聊天代理”，而是可执行的安全工作流

FlagHunter 的核心不是让模型自由发挥，而是把：

- 计划生成
- 工具调用
- 结果验证
- 策略切换
- 记忆沉淀

串成一个可复用、可观察、可回放的执行闭环。

### 2. CTF 模式强调“确定性调度 + LLM 辅助”

在 CTF 场景下，FlagHunter 不是单纯把题目扔给模型，而是通过：

- `HypothesisEngine`
- `StrategyRegistry`
- `CapabilityRegistry`
- `CTFVerifier`
- `StrategyMemory`

把题型分析、策略选择、能力降级与 flag 验证拆开处理，尽量减少“幻觉式乱试”。

### 3. 兼顾本地开发、隔离执行和远程接入

运行时支持：

- **LocalRuntime**：本地调试与开发
- **DockerRuntime**：隔离执行与沙箱化工具运行
- **SSHRuntime**：外接 Kali / 远程环境

同时可作为 **MCP Server** 暴露给外部客户端调用。

---

## 快速开始

### 环境要求

- Python **3.10+**
- Windows / Linux / macOS（按本地运行方式配置）
- 如需浏览器自动化：Playwright 或系统 Chromium / Edge
- 如需隔离执行：Docker
- 如需远程工具链：Kali VM / SSH 环境

### 克隆项目

```bash
git clone https://github.com/leilehuimieba/FlagHunter.git
cd FlagHunter
```

### 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux / macOS
pip install -r requirements.txt
```

### 配置环境变量

```bash
copy .env.example .env       # Windows
# cp .env.example .env       # Linux / macOS
```

按需填写：

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `PENTESTAGENT_MODEL`
- 以及 CPA / CTF / MCP 相关开关

### 启动

```bash
pentestagent
```

常用入口：

```text
/api           查看 API Hub 状态
/tools         查看工具列表
/ctf list      查看 CTF Playbook
/ctf run ...   启动 CTF 工作流
/mcp list      查看 MCP 配置
```

### 当前推荐起步路径

如果你是第一次接手这个仓库，建议按下面顺序理解：

1. 先读本页 `README`
2. 再看 `D:\webstudy\FlagHunter\AGENTS.md`
3. 然后看 `D:\webstudy\FlagHunter\docs\D1_M1M2_用户使用手册.md`
4. 如果要继续开发，再看 `D:\webstudy\FlagHunter\docs\superpowers\plans\`

---

## 典型工作模式

### TUI 交互

```bash
pentestagent
pentestagent -t 192.168.1.10
pentestagent tui --docker
```

### CLI / Playbook

```bash
pentestagent run -t example.com --playbook thp3_web
```

### MCP Server

```bash
pentestagent mcp_server --type stdio
pentestagent mcp_server --type sse --host 0.0.0.0 --port 8080
```

---

## 架构一览

```text
FlagHunter
├─ pentestagent/        # 主体代码（沿用上游项目结构）
├─ cpa_modules/         # M1~M6 模块增强层
├─ tools/               # 工具系统与执行守卫
├─ docs/                # 用户文档、部署文档、设计与计划
├─ knowledge/           # RAG / ShadowGraph / 记忆资产
├─ tests/               # 测试集
└─ scripts/             # 启动、构建、辅助脚本
```

### 保持不改的部分

为了减少无意义迁移成本，项目当前**没有**重命名以下内部技术路径：

- Python 包目录 `pentestagent/`
- 运行入口命令 `pentestagent`
- 与上游兼容的部分配置字段

这意味着：**外部品牌是 FlagHunter，内部代码骨架仍与 PentestAgent 体系兼容**。

---

## 主要文档

| 文档 | 说明 |
|------|------|
| `D:\webstudy\FlagHunter\AGENTS.md` | 当前仓库的开发与协作约束 |
| `D:\webstudy\FlagHunter\docs\D1_M1M2_用户使用手册.md` | 用户视角使用说明 |
| `D:\webstudy\FlagHunter\docs\D2_部署指南_Windows_KaliVM.md` | Windows + Kali VM 部署指南 |
| `D:\webstudy\FlagHunter\docs\D3_CTF实战攻略.md` | CTF 实战路径说明 |
| `D:\webstudy\FlagHunter\docs\superpowers\plans\` | 当前实现计划与执行文档 |
| `D:\webstudy\FlagHunter\CHANGELOG.md` | 版本与仓库演进记录 |

---

## Release / License / Repository Hygiene

- **Release**：使用 GitHub Releases 记录阶段性可用版本
- **Current Release**：`v0.1.0`
- **License**：当前采用 `MIT`（兼容上游）
- **.gitignore**：仓库已包含顶层 `.gitignore`，用于屏蔽本地环境、日志、缓存和敏感文件
- **Website**：当前未设置公开站点链接，避免把私有仓库误当公开展示页

建议协作时遵循：

1. 先提交可复现的最小改动
2. 大功能按 spec / plan / implementation 拆分推进
3. 不将 `.env`、本地 token、运行缓存、loot 等敏感内容提交到 Git

---

## 安全与授权说明

FlagHunter 面向：

- CTF / 靶场环境
- 获得明确授权的安全测试环境

请不要将其中的自动化能力直接用于未授权目标。

---

## 路线图

- [x] 建立新仓库 `FlagHunter`
- [x] 迁移主线代码与基础文档
- [x] 接入新仓库描述、topics、release 管理
- [ ] 继续收敛 README / 文档对外叙事
- [ ] 逐步统一更多对外命名与交付材料
- [ ] 为关键功能补更清晰的验证矩阵与版本说明

---

## License

MIT License
