# PentestAgent-CPA

> **C**ustomized **P**entest **A**gent — 基于PentestAgent的模块化增强版  
> 专为CTF竞赛和合规渗透测试设计，轻量、安全、可扩展  

---

## 项目概述

PentestAgent-CPA 是对开源项目 [PentestAgent](https://github.com/GH05TCREW/PentestAgent) 的模块化二开增强，补齐原版在**API调度**和**CTF题型覆盖**方面的短板，同时保持原版"轻量快速"的核心优势。

### 核心能力

| 模块 | 功能 | 状态 |
|------|------|:----:|
| **M1 API接入调度** | 多中转站自动切换、故障转移、Token追踪 | ✅ |
| **M2 CTF增强工具包** | Web/Pwn/Crypto/Reverse/Misc全题型覆盖 | ✅ |
| **M3 报告生成** | HTML/Markdown专业报告（计划中） | ⬜ |
| **M4 审计合规** | 操作审计、RoE授权管理（计划中） | ⬜ |
| **M5 多Agent协作** | Swarm架构协作（计划中） | ⬜ |
| **M6 性能优化** | 缓存、并发、延迟加载（计划中） | ⬜ |

---

## 快速开始

### 环境要求

- **Windows 10/11** 本机（运行PentestAgent主程序）
- **Kali Linux VM**（运行渗透测试工具链）
- **Python 3.10+**
- **VMware Workstation Player**（免费）

### 5分钟启动

```bash
# 1. 克隆项目
git clone https://github.com/yourname/PentestAgent-CPA.git
cd PentestAgent-CPA

# 2. 安装依赖
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 3. 配置API Key（编辑 .env）
cp .env.example .env
# 填入你的中转站API Key

# 4. 启动
pentestagent

# 5. 验证
> /api        # 查看API状态
> /ctf list   # 查看CTF Playbook
```

详细部署指南：[部署指南](docs/D2_部署指南_Windows_KaliVM.md)

---

## M1 模块：API接入调度

**解决什么问题**：原版PentestAgent只支持单一API Provider，API断了只能手动切换。

**M1提供的能力**：

```
多Provider管理 — 同时配置任意数量的中转站/官方API
自动故障转移 — 主渠道断了自动切备用，无需人工干预
自动恢复检测 — API恢复后自动重新投入使用
Token消耗追踪 — 精确到每次请求的消耗统计
预算告警 — 超过阈值时自动提醒
TUI状态面板 — /api 命令实时查看所有Provider健康状态
```

### M1 TUI展示

```
> /api
╔══════════════════ API Hub 状态面板 ══════════════════╗
║ 中转站A-Claude    🟢健康   1.2s    45    12K   $2.30 ║
║ 中转站B-Claude    🟢健康   0.8s    32     8K   $1.80 ║
║ 中转站A-GPT4      🟡降级   5.1s    12     3K   $0.90 ║
║ 官方-GPT4         🔴故障   ---      0      0   $0.00 ║ ← 已自动切换
╚════════════════════════════════════════════════════╝
```

### M1 命令速查

| 命令 | 功能 |
|------|------|
| `/api` | 状态面板 |
| `/api providers` | 列出所有Provider |
| `/api switch <id>` | 手动切换 |
| `/api cost` | 消耗统计 |
| `/api test <id>` | 测试连接 |

---

## M2 模块：CTF增强工具包

**解决什么问题**：原版PentestAgent几乎不支持Crypto/Pwn/Reverse题型。

**M2提供的能力**：

```
CTF Playbook引擎 — YAML定义解题流程，半自动模式（等LLM确认）
Pwn工具封装 — pwntools远程连接/泄露/ROP/Payload构造
密码学工具集 — 23个函数覆盖古典/编码/RSA/AES/自动解题
逆向工具封装 — radare2静态分析/反汇编/反编译/字符串提取
Flag提交器 — 支持CTFd/HTB/THM/RootMe多平台自动提交
```

### M2 TUI展示

```
> /ctf
╔══════════════════ CTF Kit 状态 ═════════════════════╗
║ Playbook引擎: 🟢 就绪 (5个模板已加载)               ║
║ Pwn工具:      🟢 就绪 (pwntools已安装)              ║
║ Crypto工具:   🟢 就绪 (23个函数可用)                ║
║ Reverse工具:  🟢 就绪 (r2pipe已安装)                ║
║ Flag提交器:   🟢 就绪 (CTFd/HTB/THM支持)           ║
╚════════════════════════════════════════════════════╝

> /ctf list
📋 可用Playbook (5个):
   [web]     web.yaml      — Web渗透测试 (5阶段, ~30分钟)
   [pwn]     pwn.yaml      — 二进制利用 (5阶段, ~45分钟)
   [crypto]  crypto.yaml   — 密码学破解 (5阶段, ~20分钟)
   [reverse] reverse.yaml  — 逆向工程 (5阶段, ~40分钟)
   [misc]    misc.yaml     — 杂项挑战 (4阶段, ~15分钟)

> /ctf run pwn "challenge.ctf 1337"
🚀 启动Playbook: pwn.yaml
📍 Phase 1/5: 连接靶机
🔧 执行: pwn_remote("challenge.ctf", 1337)
✅ 成功！Banner: "Welcome to Pwn Challenge!"
💡 LLM建议: "这是一个标准的堆溢出题目，需要先泄露libc基址"
⏳ 输入 /ctf next 进入下一阶段
```

### M2 命令速查

| 命令 | 功能 | 示例 |
|------|------|------|
| `/ctf list` | 列出Playbook | `/ctf list pwn` |
| `/ctf run <模板> <目标>` | 执行Playbook | `/ctf run web "http://t"` |
| `/ctf phase` | 查看当前阶段 | `/ctf phase` |
| `/ctf next` | 进入下一阶段 | `/ctf next` |
| `/ctf flag <flag>` | 提交Flag | `/ctf flag "flag{xxx}"` |
| `/ctf pwn <h> <p>` | 快速Pwn | `/ctf pwn 127.0.0.1 1337` |
| `/ctf decode <密文>` | 自动解密 | `/ctf decode "SGVsbG8..."` |
| `/ctf rev <二进制>` | 快速逆向 | `/ctf rev ./challenge` |

---

## 架构设计

```
PentestAgent-CPA 模块化架构
│
├─ M0: 原版PentestAgent核心（侵入<25行）
│
├─ cpa_modules/
│   ├─ m1_api_hub/          ← M1 API接入调度
│   │   ├── models.py       # 9个数据模型
│   │   ├── config_schema.py   # 环境变量解析
│   │   ├── provider_manager.py   # Provider调度核心
│   │   ├── failover_monitor.py   # 故障监控+自动恢复
│   │   ├── cost_tracker.py   # Token追踪
│   │   └── status_display.py   # TUI状态面板
│   │
│   └─ m2_ctf_kit/          ← M2 CTF增强工具包
│       ├── playbook_engine.py   # Playbook引擎
│       ├── pwn_tools.py    # Pwn工具封装
│       ├── crypto_tools.py   # 密码学工具
│       ├── reverse_tools.py   # 逆向工具
│       ├── flag_submitter.py   # Flag提交器
│       └── playbooks/      # 5个题型模板
│
└─ 每个模块独立开关（.env中 CPA_MX_YYYY=true/false）
```

### 设计原则

| 原则 | 实现 |
|------|------|
| **模块化** | 每个模块独立目录、独立开关、独立测试 |
| **低侵入** | 对原版M0侵入<25行代码，全部用HOOK标记 |
| **延迟加载** | pwntools/r2pipe等用lazy import，Windows本机不报错 |
| **Kali VM执行** | 安全工具在VM中运行，Windows本机零工具依赖 |
| **可选加载** | 不需要的功能关闭即可，不影响其他功能 |

---

## 文档

| 文档 | 说明 |
|------|------|
| [D1: 用户使用手册](docs/D1_M1M2_用户使用手册.md) | M1/M2模块的完整使用指南 |
| [D2: 部署指南](docs/D2_部署指南_Windows_KaliVM.md) | Windows+Kali VM从零搭建 |
| [D3: CTF实战攻略](docs/D3_CTF实战攻略.md) | 5类题型的实战操作步骤 |
| [M1 调度手册](M1_多Agent并行调度手册_完整版.md) | M1模块开发文档 |
| [M2 调度手册](M2_多Agent并行调度手册_完整版.md) | M2模块开发文档 |

---

## 与原版PentestAgent对比

| 维度 | 原版PentestAgent | PentestAgent-CPA |
|------|:---------------:|:----------------:|
| API Provider | 只支持1个 | **支持任意数量，自动故障转移** |
| CTF Web题型 | ✅ 支持 | ✅ 支持 + Playbook模板 |
| CTF Pwn题型 | ❌ 不支持 | **✅ 支持（pwntools封装）** |
| CTF Crypto题型 | ❌ 不支持 | **✅ 支持（23个密码学函数）** |
| CTF Reverse题型 | ❌ 不支持 | **✅ 支持（radare2封装）** |
| CTF Misc题型 | ❌ 不支持 | **✅ 支持（文件分析+隐写）** |
| Flag自动提交 | ❌ 不支持 | **✅ 支持（5个平台）** |
| Token追踪 | ❌ 不支持 | **✅ 支持（精确到请求）** |
| 内存占用 | ~150MB | ~275MB（M1+M2全部加载） |
| 启动时间 | 2-5秒 | 3-6秒（含模块初始化） |

---

## 风险提示

1. **Kali VM隔离**：所有渗透测试工具在Kali VM中执行，Windows本机零暴露
2. **Playbook半自动**：M2的CTF Playbook是半自动模式（每Phase等LLM确认），不会自动执行危险操作
3. **API Key安全**：API Key存储在.env文件，**不要提交到Git仓库**（已配置.gitignore）
4. **授权范围**：M2的Pwn/Reverse工具仅用于CTF授权靶场，**不要用于未授权目标**

---

## Roadmap

```
2026-Q2 (已完成)
├── M1: API接入调度 ✅
└── M2: CTF增强工具包 ✅

2026-Q3 (计划中)
├── M3: 报告生成系统
│   └── HTML/Markdown报告，Jinja2模板
├── M4: 审计合规守卫
│   └── 操作审计日志、RoE授权管理
└── M5: 多Agent协作链
    └── Swarm架构、共享黑板

2026-Q4 (计划中)
└── M6: 性能优化加速
    └── 结果缓存、并发扫描、内存优化
```

---

## 贡献

本项目基于PentestAgent进行模块化扩展。如果你想贡献：

1. Fork本项目
2. 保持模块化设计，新增模块放在 `cpa_modules/` 下
3. 对原版M0的侵入用 `=== CPA MX HOOK BEGIN/END ===` 标记
4. 每个模块提供独立开关和测试用例

---

## License

MIT License（继承自原版PentestAgent）

---

> **一句话**：PentestAgent-CPA = 原版PentestAgent的轻量身躯 + 多API自动调度 + CTF全题型覆盖，是CTF比赛和轻量渗透测试的最佳选择。
