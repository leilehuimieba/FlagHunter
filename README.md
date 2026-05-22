# PentestAgent-CPA

> **C**ustomized **P**entest **A**gent — 基于 PentestAgent 的模块化增强版  
> 专为 CTF 竞赛和合规渗透测试设计，轻量、安全、可扩展

---

## 项目概述

PentestAgent-CPA 是对开源项目 [PentestAgent](https://github.com/GH05TCREW/PentestAgent) 的模块化二开增强，补齐原版在 **API 调度**和 **CTF 题型覆盖**方面的短板，同时保持原版"轻量快速"的核心优势。

### 模块状态

| 模块 | 功能 | 状态 |
|------|------|:----:|
| **M1 API接入调度** | 多中转站自动切换、故障转移、Token 追踪 | ✅ |
| **M2 CTF增强工具包** | Web/Pwn/Crypto/Reverse/Misc 全题型覆盖 | ✅ |
| **M3 报告生成** | HTML/Markdown 专业报告，Jinja2 模板 | ⬜ |
| **M4 审计合规** | 操作审计日志、RoE 授权管理 | ⬜ |
| **M5 多Agent协作** | Swarm 架构、共享黑板 | ⬜ |
| **M6 性能优化** | 结果缓存、并发扫描、内存优化 | ⬜ |

---

## 快速开始

### 环境要求

- **Windows 10/11** 本机（运行 PentestAgent 主程序）
- **Kali Linux VM**（运行渗透测试工具链）
- **Python 3.10+**

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

## 模块说明

### M1：API 接入调度

多 Provider 管理，主渠道断了自动切备用，无需人工干预。

```
> /api
╔══════════════════ API Hub 状态面板 ══════════════════╗
║ 中转站A-Claude    🟢健康   1.2s    45    12K   $2.30 ║
║ 中转站B-Claude    🟢健康   0.8s    32     8K   $1.80 ║
║ 中转站A-GPT4      🟡降级   5.1s    12     3K   $0.90 ║
║ 官方-GPT4         🔴故障   ---      0      0   $0.00 ║
╚════════════════════════════════════════════════════╝
```

| 命令 | 功能 |
|------|------|
| `/api` | 状态面板 |
| `/api providers` | 列出所有 Provider |
| `/api switch <id>` | 手动切换 |
| `/api cost` | 消耗统计 |
| `/api test <id>` | 测试连接 |

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

---

## 架构

```
PentestAgent-CPA
│
├─ M0: 原版 PentestAgent 核心（侵入 < 25 行）
│
└─ cpa_modules/
    ├─ m1_api_hub/       # M1：API 接入调度
    ├─ m2_ctf_kit/       # M2：CTF 增强工具包
    ├─ m3_reporter/      # M3：报告生成（开发中）
    ├─ m4_audit_guard/   # M4：审计合规（开发中）
    ├─ m5_swarm_link/    # M5：多 Agent 协作（开发中）
    └─ m6_turbo/         # M6：性能优化（开发中）
```

每个模块独立开关，在 `.env` 中用 `CPA_MX_ENABLED=true/false` 控制。

---

## 文档

| 文档 | 说明 |
|------|------|
| [用户使用手册](docs/D1_M1M2_用户使用手册.md) | M1/M2 完整使用指南 |
| [部署指南](docs/D2_部署指南_Windows_KaliVM.md) | Windows + Kali VM 从零搭建 |
| [CTF 实战攻略](docs/D3_CTF实战攻略.md) | 5 类题型的实战操作步骤 |
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
