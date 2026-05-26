# PentestAgent-CPA

> **C**ustomized **P**entest **A**gent — 基于 PentestAgent 的模块化增强版  
> 专为 CTF 竞赛和合规渗透测试设计，轻量、安全、可扩展

---

## 项目概述

PentestAgent-CPA 是对开源项目 [PentestAgent](https://github.com/GH05TCREW/PentestAgent) 的模块化二开增强，补齐原版在 **API 调度**和 **CTF 题型覆盖**方面的短板，同时保持原版"轻量快速"的核心优势。

### 模块状态

| 模块 | 功能 | 状态 |
|------|------|:----:|
| **M0 原版核心** | Agent 循环、工具调用、TUI/CLI/MCP 接口 | ✅ |
| **M1 API 接入调度** | 多中转站自动切换、故障转移、Token 追踪 | ✅ |
| **M2 CTF 增强工具包** | Web/Pwn/Crypto/Reverse/Misc 全题型覆盖 | ✅ |
| **M3 报告生成** | HTML/Markdown 专业报告（finish 工具自动触发） | 🟡 |
| **M4 审计合规** | 作用域检查、操作审计（ToolExecutor 已集成） | 🟡 |
| **M5 多 Agent 协作** | Crew Worker 池、Swarm 信息素路由（已部分落地） | 🟡 |
| **M6 性能优化** | 结果缓存、并发扫描、内存优化（计划中） | ⬜ |

> 🟡 = 核心框架已落地，部分功能待完善

---

## 快速开始

### 环境要求

- **Windows 10/11** 本机（运行 PentestAgent 主程序）
- **Kali Linux VM**（运行渗透测试工具链）
- **Python 3.10+**
- **VMware Workstation Player**（免费）

### 5 分钟启动

```bash
# 1. 克隆项目
git clone https://github.com/yourname/PentestAgent-CPA.git
cd PentestAgent-CPA

# 2. 安装依赖
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的中转站 API Key

# 4. 启动
pentestagent

# 5. 验证
> /api        # 查看 API 状态
> /ctf list   # 查看 CTF Playbook
```

---

## 核心架构（代码层面）

### Agent 主循环

所有 Agent 共享 `BaseAgent._run_loop()`，一个状态机驱动的迭代器：

```text
agent_loop()
  ├── 第1轮强制生成计划
  ├── LLM.generate()        # Function-calling 模式
  ├── _execute_tools()      # 并发执行
  ├── _expand_plan()        # 发现驱动扩展（nmap/subfinder 发现新服务时）
  ├── _replan()             # 战术重规划（步骤失败时）
  └── plan.is_complete() → 总结 → COMPLETE
```

### CTF 解题引擎

CTF 模式不是 LLM 自由发挥，而是**确定性调度器 + LLM 辅助策略选择**：

- **HypothesisEngine**：基于规则的假设生成与排序（Observation Floor 防幻觉）
- **StrategyRegistry**：15+ 策略定义（XSS bot、SQLi、反序列化、SSTI 等），含前置条件与成功/失败信号
- **CapabilityRegistry**：能力降级（sqlmap → 手动 Payload）
- **CTFVerifier**：四级 Flag 证据（candidate → runtime → verified → rejected）
- **StrategyMemory**：跨题持久化记忆，自动静音低成功率策略

### 工具系统（25 个工具）

| 类别 | 工具 | 说明 |
|------|------|------|
| **网络扫描** | `nmap` / `fscan` / `subfinder` / `httpx_probe` | 端口、服务、子域、存活探测 |
| **Web 渗透** | `dirscan` / `nuclei` / `afrog` / `katana` / `dalfox` / `gau` | 目录爆破、漏洞扫描、爬虫、XSS、URL 历史 |
| **数据提取** | `sqlmap` / `binary` / `pwn` / `msf` / `gf` | SQL 注入、二进制分析、Pwn、Metasploit、模式匹配 |
| **信息收集** | `browser` / `web_search` / `login_flow` / `opencli_browser` / `knowledge_search` | 浏览器、搜索、登录流、知识库检索 |
| **多 Agent** | `mcp_agent` / `shadowgraph` | 子 Agent 嵌套、知识图战略洞察 |
| **通用** | `terminal` / `http_request` / `notes` / `finish` / `waf` | 终端、HTTP、笔记、完成、WAF 检测 |

- **Self-Register**：`@register_tool` 装饰器 + `loader.py` 动态导入
- **执行守卫**：M4 作用域检查 → Cookie 自动注入 → Stealth 模式 → Flag 扫描 → 缺失工具检测
- **终端启发式修复**：自动补全 LLM 漏写的二进制名（如 `-sS -p 80` → `nmap -sS -p 80`）

### 运行时隔离

| 模式 | 命令执行 | 浏览器 | 代理 | 场景 |
|------|----------|--------|------|------|
| **Local** | `subprocess` | Playwright + 系统浏览器回退 | `httpx` | 本地开发 |
| **Docker** | `container.exec_run` | `curl` + 正则 | `mitmdump` | 隔离沙箱 |
| **SSH** | `ssh` 子进程 | `curl` + 正则 | 内嵌 Python | Kali VM |

### MCP 双向集成

- **Client**：连接外部 MCP Server（stdio / SSE / FIFO / WebSocket）；>128 工具时启用 RAG Optimizer
- **Server**：暴露 22+ 工具；每个任务创建全新 Agent + Runtime 避免污染；支持 `spawn_mcp_agent` 嵌套子 Agent

---

## 模块说明

### M1：API 接入调度

多 Provider 管理，主渠道断了自动切备用，无需人工干预。

```
> /api
╔══════════════════ API Hub 状态面板 ══════════════════╗
║ 中转站A-Claude    🟢健康   1.2s    45    12K   $2.30 ║
║ 中转站B-Claude    🟢健康   0.8s    32     8K   $1.80 ║
║ 中转站A-GPT4      🟡降级   5.1s    12     3K   $0.90 ║
║ 官方-GPT4         🔴故障   ---      0      0   $0.00 ║ ← 已自动切换
╚════════════════════════════════════════════════════╝
```

| 命令 | 功能 |
|------|------|
| `/api` | 状态面板 |
| `/api providers` | 列出所有 Provider |
| `/api switch <id>` | 手动切换 |
| `/api cost` | 消耗统计 |
| `/api test <id>` | 测试连接 |

**实现细节**：`ProviderManager` 按 `task_hint` 做模型路由（planning → heavy，tool_parse → light）；`FailoverMonitor` 双循环健康探测（30s 故障检测 + 60s 恢复检测）；错误分级处理（永久故障标记 DOWN，限流本地 jitter 退避）。

### M2：CTF 增强工具包

覆盖 Web/Pwn/Crypto/Reverse/Misc 五大题型，含 Playbook 引擎和 Flag 自动提交。

| 命令 | 功能 |
|------|------|
| `/ctf list` | 列出 Playbook |
| `/ctf run <模板> <目标>` | 执行 Playbook |
| `/ctf next` | 进入下一阶段 |
| `/ctf flag <flag>` | 提交 Flag |
| `/ctf decode <密文>` | 自动解密 |
| `/ctf rev <二进制>` | 快速逆向 |

**实现细节**：`PlaybookEngine` 半自动执行（每 Phase 暂停等确认）；`CTFTaskDispatcher` 确定性调度；`FlagSubmitter` 支持 CTFd/HTB/TryHackMe/RootMe；`StrategyMemory` 跨题学习。

---

## 架构

```
PentestAgent-CPA
│
├─ M0: 原版 PentestAgent 核心（侵入 < 25 行）
│   ├── agents/base_agent.py      # 主循环 + 状态机
│   ├── agents/pa_agent/          # 单 Agent（含 CTF Dispatcher）
│   ├── agents/crew/              # 多 Agent（Orchestrator + WorkerPool）
│   ├── tools/                    # Self-Register 工具系统
│   ├── llm/                      # LLM + Memory + M1 Failover
│   ├── mcp/                      # MCP Client & Server
│   ├── runtime/                  # Local / Docker / SSH
│   ├── knowledge/                # ShadowGraph + RAG
│   └── interface/                # TUI + CLI + Notifier
│
└─ cpa_modules/
    ├─ m1_api_hub/       # M1：Provider 管理 + 故障转移 + 成本追踪
    ├─ m2_ctf_kit/       # M2：Playbook 引擎 + Pwn/Crypto/Reverse + Flag 提交
    ├─ m3_reporter/      # M3：报告生成（finish 工具调用）
    ├─ m4_audit_guard/   # M4：作用域检查 + 审计日志
    ├─ m5_swarm_link/    # M5：信息素路由 + Crew 桥接
    └─ m6_turbo/         # M6：性能优化（计划中）
```

每个模块独立开关，在 `.env` 中用 `CPA_MX_YYYY=true/false` 控制。

---

## 文档

| 文档 | 说明 |
|------|------|
| [用户使用手册](docs/D1_M1M2_用户使用手册.md) | M1/M2 完整使用指南 |
| [部署指南](docs/D2_部署指南_Windows_KaliVM.md) | Windows + Kali VM 从零搭建 |
| [CTF 实战攻略](docs/D3_CTF实战攻略.md) | 5 类题型的实战操作步骤 |
| [AGENTS.md](AGENTS.md) | **Agent 开发指南（含代码架构详解）** |
| [开发文档](docs/dev/) | 模块调度手册与开发计划 |
| [分析报告存档](docs/archive/) | 选型调研与竞品分析 |

---

## 风险提示

1. **Kali VM 隔离**：所有渗透测试工具在 Kali VM 中执行，Windows 本机零暴露
2. **半自动 Playbook**：每个 Phase 等 LLM 确认，不会自动执行危险操作
3. **API Key 安全**：Key 存在 `.env` 文件中，**不要提交到 Git**（已配置 .gitignore）
4. **授权范围**：Pwn/Reverse 工具仅用于 CTF 授权靶场，**不要用于未授权目标**

---

## License

MIT License（继承自原版 PentestAgent）
