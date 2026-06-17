# FlagHunter 部署指南（Windows + Kali VM）

> 目标：在Windows本机上搭建完整的FlagHunter运行环境  
> 包含：Windows环境准备 + Kali VM配置 + PentestAgent安装 + M1/M2模块配置  

---

## 目录

1. [架构概览](#一架构概览)
2. [Windows本机环境准备](#二windows本机环境准备)
3. [Kali Linux虚拟机部署](#三kali-linux虚拟机部署)
4. [FlagHunter安装](#四pentestagent-cpa安装)
5. [M1模块配置](#五m1模块配置)
6. [M2模块配置](#六m2模块配置)
7. [验证测试](#七验证测试)
8. [故障排查](#八故障排查)

---

## 一、架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Windows 10/11 物理机                        │
│                                                              │
│  ┌──────────────────────────┐  ┌──────────────────────────┐ │
│  │ FlagHunter (Python) │  │ LiteLLM Proxy (可选)      │ │
│  │ · M1 API接入调度          │  │ · 端口 localhost:4000     │ │
│  │ · M2 CTF工具包            │  │ · 多渠道API调度           │ │
│  │ · TUI交互界面             │  │                          │ │
│  └──────────┬───────────────┘  └──────────────────────────┘ │
│             │                                                │
│             │ SSH (端口2222)                                 │
│             ▼                                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │        Kali Linux 虚拟机 (VMware/VB)                  │  │
│  │  · pwntools  · radare2  · metasploit  · burpsuite   │  │
│  │  · nmap  · sqlmap  · john  · hydra  · nuclei        │  │
│  │  · Docker (容器化工具沙箱)                            │  │
│  │  · SSH服务 (端口22，映射到本机2222)                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**设计原则**：
- Windows本机只跑 **PentestAgent + LiteLLM Proxy**（纯Python，无需安全工具）
- Kali VM跑 **所有渗透测试工具**（pwntools/metasploit等预装）
- 两者通过 **SSH** 通信

---

## 二、Windows本机环境准备

### 2.1 安装Python 3.10+

1. 下载：https://www.python.org/downloads/ （选Python 3.11）
2. 安装时勾选 **"Add Python to PATH"**
3. 验证：

```powershell
python --version   # Python 3.11.x
pip --version      # pip 24.x
```

### 2.2 安装Git

1. 下载：https://git-scm.com/download/win
2. 使用默认配置安装
3. 验证：

```powershell
git --version   # git version 2.43.x
```

### 2.3 安装Windows Terminal（推荐）

Microsoft Store搜索 "Windows Terminal" 安装，TUI显示效果更好。

### 2.4 配置SSH客户端（连接Kali VM用）

Windows 10/11自带OpenSSH，验证：

```powershell
ssh -V   # OpenSSH_for_Windows_9.x
```

生成SSH密钥对（用于免密登录Kali VM）：

```powershell
# 创建.ssh目录
mkdir -Force $env:USERPROFILE\.ssh

# 生成密钥（一路回车）
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\kali_vm

# 记下公钥路径
$env:USERPROFILE\.ssh\kali_vm.pub
```

### 2.5 创建项目目录

```powershell
# 创建工作目录
mkdir C:\Tools\FlagHunter
cd C:\Tools\FlagHunter

# 克隆PentestAgent原版
# （后续你将自己的二开代码覆盖进去）
```

---

## 三、Kali Linux虚拟机部署

### 3.1 下载Kali VM镜像

**推荐方式：下载VMware预装镜像（最省事）**

1. 访问：https://www.kali.org/get-kali/#kali-virtual-machines
2. 下载 **Kali Linux VMware 64-bit**（约3GB）
3. 解压得到 `.vmx` 文件

### 3.2 导入VMware

1. 安装VMware Workstation Player（免费）：https://support.broadcom.com/security-advisory/security-advisory-detail.html?documentUuid=8d8f42f8-c79e-4bc3-86b3-78b53750eb68
2. Player中点击 **"Open a Virtual Machine"**
3. 选择解压后的 `.vmx` 文件
4. 导入后先**不要启动**

### 3.3 配置Kali VM网络

编辑虚拟机设置：

| 设置项 | 推荐值 | 说明 |
|--------|--------|------|
| 内存 | 4096 MB (4GB) | 最低2GB，推荐4-8GB |
| CPU | 2核 | 推荐2-4核 |
| 网络适配器 | NAT模式 | VM可访问外网+与本机通信 |
| 显示 | 自动检测 | 默认即可 |

**NAT网络配置**（确保本机与VM互通）：

```
VMware菜单 → Edit → Virtual Network Editor
→ 选择VMnet8 (NAT模式)
→ NAT Settings → 添加端口转发:
    Host port: 2222  →  VM port: 22  (SSH转发)
→ 确认子网: 192.168.56.0/24  (Kali默认IP在此网段)
```

### 3.4 启动Kali并初始配置

1. 启动VM，登录：`kali` / `kali`
2. 打开Terminal，执行：

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装pwntools
pip3 install pwntools

# 确认pwntools安装成功
python3 -c "import pwn; print(pwn.__version__)"

# 安装r2pipe
pip3 install r2pipe

# 确认radare2已安装（Kali预装）
r2 -v

# 安装pycryptodome（Crypto工具用）
pip3 install pycryptodome

# 安装Docker（容器化工具沙箱）
sudo apt install docker.io -y
sudo systemctl enable docker
sudo usermod -aG docker kali

# 确认Docker
sudo docker --version

# 配置SSH服务（通常已启动）
sudo systemctl enable ssh
sudo systemctl start ssh

# 查看IP地址
ip addr show eth0
# 记下IP，如 192.168.56.101
```

### 3.5 配置SSH免密登录

在Kali VM中：

```bash
# 创建.ssh目录
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# 编辑authorized_keys，粘贴Windows本机的公钥内容
cat >> ~/.ssh/authorized_keys
# 然后粘贴 C:\Users\你的用户名\.ssh\kali_vm.pub 的内容
# 按Ctrl+D结束

chmod 600 ~/.ssh/authorized_keys
```

**或者更简单的方式**：

在Windows本机的PowerShell中：

```powershell
# 将公钥复制到Kali（会提示输入密码kali）
$pubKey = Get-Content $env:USERPROFILE\.ssh\kali_vm.pub
ssh kali@192.168.56.101 "mkdir -p ~/.ssh && echo '$pubKey' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

### 3.6 测试SSH连接

在Windows PowerShell中：

```powershell
ssh -i $env:USERPROFILE\.ssh\kali_vm -p 2222 kali@localhost

# 如果成功登录到Kali（看到kali@kali:~$），说明SSH配置完成
# 输入 exit 退出
```

### 3.7 对Kali VM打快照

VMware菜单 → VM → Snapshot → Take Snapshot

```
名称: 初始 clean 状态
描述: 刚配置完的环境快照，可随时恢复
```

**每次打CTF前都建议打一个新快照，玩坏了秒回。**

---

## 四、FlagHunter安装

### 4.1 安装PentestAgent原版

```powershell
cd C:\Tools\FlagHunter

# 克隆原版（二开代码后续覆盖）
git clone https://github.com/GH05TCREW/PentestAgent.git .

# 创建Python虚拟环境
python -m venv .venv

# 激活虚拟环境
.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

### 4.2 放置二开代码（M1 + M2）

将M1和M2的代码文件放到对应位置：

```
FlagHunter/
├── pentestagent/              # 原版代码
│   ├── __main__.py            # ← 添加M1/M2初始化hook
│   ├── config/
│   │   └── settings.py        # ← 添加M1/M2开关字段
│   ├── llm/
│   │   └── llm.py             # ← 添加M1 Provider选择hook
│   └── interface/
│       └── commands.py        # ← 注册/api和/ctf命令
├── cpa_modules/               # ← 新建：二开模块目录
│   ├── m1_api_hub/            # ← M1模块文件
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── config_schema.py
│   │   ├── provider_manager.py
│   │   ├── failover_monitor.py
│   │   ├── cost_tracker.py
│   │   └── status_display.py
│   └── m2_ctf_kit/            # ← M2模块文件
│       ├── __init__.py
│       ├── playbook_engine.py
│       ├── pwn_tools.py
│       ├── crypto_tools.py
│       ├── reverse_tools.py
│       ├── flag_submitter.py
│       ├── ctf_commands.py
│       └── playbooks/         # ← Playbook模板
│           ├── web.yaml
│           ├── pwn.yaml
│           ├── crypto.yaml
│           ├── reverse.yaml
│           └── misc.yaml
├── .env                       # ← 配置文件
└── ...
```

### 4.3 应用M0侵入层（4+3=7个Hook点）

按以下位置修改原版文件：

**Hook 1 — `pentestagent/llm/llm.py`**

在 `LLM.acompletion()` 方法开头，litellm.acompletion()调用之前：

```python
# === CPA M1 HOOK BEGIN ===
import os
if os.getenv("CPA_M1_API_HUB", "true").lower() == "true":
    try:
        from pentestagent.cpa_modules.m1_api_hub import get_provider_manager
        pm = get_provider_manager()
        if pm:
            provider = await pm.select_provider(model_hint=self.model)
            kwargs['api_base'] = provider.api_base
            kwargs['api_key'] = provider.api_key
            kwargs['model'] = provider.model
    except Exception:
        pass
# === CPA M1 HOOK END ===
```

**Hook 2 — `pentestagent/__main__.py`**

在 `main()` 函数开头，程序初始化之后：

```python
# === CPA M1 HOOK BEGIN ===
import os
if os.getenv("CPA_M1_API_HUB", "true").lower() == "true":
    try:
        from pentestagent.cpa_modules.m1_api_hub import init_m1
        import asyncio
        asyncio.run(init_m1())
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"M1模块初始化失败: {e}")
# === CPA M1 HOOK END ===

# === CPA M2 HOOK BEGIN ===
if os.getenv("CPA_M2_CTF_KIT", "true").lower() == "true":
    try:
        from pentestagent.cpa_modules.m2_ctf_kit import init_m2
        import asyncio
        asyncio.run(init_m2())
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"M2模块初始化失败: {e}")
# === CPA M2 HOOK END ===
```

**Hook 3 — `pentestagent/config/settings.py`**

在 `Settings` 类的字段定义中添加：

```python
# === CPA M1 HOOK BEGIN ===
cpa_m1_api_hub: bool = field(default_factory=lambda: os.getenv("CPA_M1_API_HUB", "true").lower() == "true")
# === CPA M1 HOOK END ===

# === CPA M2 HOOK BEGIN ===
cpa_m2_ctf_kit: bool = field(default_factory=lambda: os.getenv("CPA_M2_CTF_KIT", "true").lower() == "true")
cpa_m2_pwn_tools: bool = field(default_factory=lambda: os.getenv("CPA_M2_PWN_TOOLS", "true").lower() == "true")
cpa_m2_crypto_tools: bool = field(default_factory=lambda: os.getenv("CPA_M2_CRYPTO_TOOLS", "true").lower() == "true")
cpa_m2_reverse_tools: bool = field(default_factory=lambda: os.getenv("CPA_M2_REVERSE_TOOLS", "true").lower() == "true")
cpa_m2_flag_submitter: bool = field(default_factory=lambda: os.getenv("CPA_M2_FLAG_SUBMITTER", "true").lower() == "true")
# === CPA M2 HOOK END ===
```

**Hook 4 — `pentestagent/interface/commands.py`**（或类似的命令注册处）

在命令注册逻辑中添加：

```python
# === CPA M1 HOOK BEGIN ===
if os.getenv("CPA_M1_API_HUB", "true").lower() == "true":
    try:
        from pentestagent.cpa_modules.m1_api_hub.status_display import StatusDisplay
        from pentestagent.cpa_modules.m1_api_hub import get_provider_manager, get_cost_tracker
        # 注册 /api 命令 → StatusDisplay.render_full_panel()
        # 注册 /api providers → list_providers()
        # 注册 /api status → show_status()
        # 注册 /api switch → switch_provider()
        # 注册 /api test → test_provider()
        # 注册 /api logs → show_logs()
        # 注册 /api cost → show_cost()
    except Exception:
        pass
# === CPA M1 HOOK END ===

# === CPA M2 HOOK BEGIN ===
if os.getenv("CPA_M2_CTF_KIT", "true").lower() == "true":
    try:
        from pentestagent.cpa_modules.m2_ctf_kit.ctf_commands import (
            cmd_ctf, cmd_ctf_list, cmd_ctf_run, cmd_ctf_phase,
            cmd_ctf_next, cmd_ctf_flag, cmd_ctf_pwn, cmd_ctf_decode, cmd_ctf_rev, cmd_ctf_status
        )
        # 注册 /ctf 命令 → cmd_ctf()
        # 注册 /ctf list → cmd_ctf_list()
        # 注册 /ctf run → cmd_ctf_run()
        # 注册 /ctf phase → cmd_ctf_phase()
        # 注册 /ctf next → cmd_ctf_next()
        # 注册 /ctf flag → cmd_ctf_flag()
        # 注册 /ctf pwn → cmd_ctf_pwn()
        # 注册 /ctf decode → cmd_ctf_decode()
        # 注册 /ctf rev → cmd_ctf_rev()
        # 注册 /ctf status → cmd_ctf_status()
    except Exception:
        pass
# === CPA M2 HOOK END ===
```

---

## 五、M1模块配置

### 5.1 创建.env文件

在项目根目录创建 `.env`：

```bash
# ============================================
# FlagHunter 配置文件
# ============================================

# ── 原版PentestAgent配置 ──
PENTESTAGENT_MODEL=claude-sonnet-4-20250514
# OPENAI_API_KEY=        # 已由M1管理，不需要

# ── M1: 模块开关 ──
CPA_M1_API_HUB=true

# ── M1: Provider 0 — 中转站A - Claude（主渠道） ──
CPA_PROVIDER_0_ID=zz_a_claude
CPA_PROVIDER_0_NAME=中转站A-Claude
CPA_PROVIDER_0_MODEL=openai/claude-sonnet-4
CPA_PROVIDER_0_API_BASE=https://api.zz-a.com/v1
CPA_PROVIDER_0_API_KEY=sk-xxxxxxxxxxxxxxxx
CPA_PROVIDER_0_TIMEOUT=60
CPA_PROVIDER_0_MAX_RETRIES=3
CPA_PROVIDER_0_RPM_LIMIT=60
CPA_PROVIDER_0_TPM_LIMIT=100000
CPA_PROVIDER_0_PRIORITY=1
CPA_PROVIDER_0_ENABLED=true
CPA_PROVIDER_0_IS_BACKUP=false
CPA_PROVIDER_0_TAGS=claude,中转站A
CPA_PROVIDER_0_COST_1K_INPUT=0.003
CPA_PROVIDER_0_COST_1K_OUTPUT=0.015

# ── M1: Provider 1 — 中转站B - Claude（备用） ──
CPA_PROVIDER_1_ID=zz_b_claude
CPA_PROVIDER_1_NAME=中转站B-Claude
CPA_PROVIDER_1_MODEL=openai/claude-sonnet-4
CPA_PROVIDER_1_API_BASE=https://api.zz-b.com/v1
CPA_PROVIDER_1_API_KEY=sk-yyyyyyyyyyyyyyyy
CPA_PROVIDER_1_PRIORITY=2
CPA_PROVIDER_1_ENABLED=true
CPA_PROVIDER_1_IS_BACKUP=true
CPA_PROVIDER_1_TAGS=claude,中转站B,备用
CPA_PROVIDER_1_COST_1K_INPUT=0.003
CPA_PROVIDER_1_COST_1K_OUTPUT=0.015

# ── M1: Provider 2 — 中转站A - GPT4（不同模型） ──
CPA_PROVIDER_2_ID=zz_a_gpt4
CPA_PROVIDER_2_NAME=中转站A-GPT4
CPA_PROVIDER_2_MODEL=openai/gpt-4
CPA_PROVIDER_2_API_BASE=https://api.zz-a.com/v1
CPA_PROVIDER_2_API_KEY=sk-xxxxxxxxxxxxxxxx
CPA_PROVIDER_2_PRIORITY=3
CPA_PROVIDER_2_ENABLED=true
CPA_PROVIDER_2_TAGS=gpt4,中转站A
CPA_PROVIDER_2_COST_1K_INPUT=0.03
CPA_PROVIDER_2_COST_1K_OUTPUT=0.06

# ── M1: Provider 3 — DeepSeek（应急渠道） ──
CPA_PROVIDER_3_ID=deepseek_official
CPA_PROVIDER_3_NAME=DeepSeek官方
CPA_PROVIDER_3_MODEL=deepseek/deepseek-chat
CPA_PROVIDER_3_API_BASE=https://api.deepseek.com/v1
CPA_PROVIDER_3_API_KEY=sk-zzzzzzzzzzzzzzzz
CPA_PROVIDER_3_PRIORITY=4
CPA_PROVIDER_3_ENABLED=true
CPA_PROVIDER_3_TAGS=deepseek,官方,便宜
CPA_PROVIDER_3_COST_1K_INPUT=0.00014
CPA_PROVIDER_3_COST_1K_OUTPUT=0.00028

# ── M1: 健康检查配置 ──
CPA_M1_HEALTH_CHECK_INTERVAL=30       # 健康检查间隔（秒）
CPA_M1_HEALTH_CHECK_TIMEOUT=10        # 健康检查超时（秒）
CPA_M1_FAIL_THRESHOLD=3               # 连续失败次数阈值
CPA_M1_RECOVERY_CHECK_INTERVAL=60     # 恢复检测间隔（秒）
CPA_M1_RECOVERY_CONFIRM_REQUESTS=2    # 恢复确认成功次数

# ── M1: 预算管理 ──
CPA_M1_DAILY_BUDGET_USD=50            # 每日预算（美元）
CPA_M1_BUDGET_ALERT_THRESHOLD=0.8     # 预算告警阈值（0-1）
```

### 5.2 多Provider配置规则

| 规则 | 说明 |
|------|------|
| ID唯一 | 每个Provider的`ID`必须全局唯一 |
| 优先级 | `PRIORITY`数字越小优先级越高（1最高） |
| 备份标记 | `IS_BACKUP=true`表示备用渠道，不主动调度 |
| 自动扫描 | M1自动扫描`CPA_PROVIDER_0_`到`CPA_PROVIDER_N_`，断号停止 |
| 价格配置 | `COST_1K_INPUT/OUTPUT`用于成本估算，可选 |

---

## 六、M2模块配置

### 6.1 在.env中添加M2配置

```bash
# ── M2: 模块开关 ──
CPA_M2_CTF_KIT=true              # M2总开关
CPA_M2_PWN_TOOLS=true            # Pwn工具子开关
CPA_M2_CRYPTO_TOOLS=true         # Crypto工具子开关
CPA_M2_REVERSE_TOOLS=true        # Reverse工具子开关
CPA_M2_FLAG_SUBMITTER=true       # Flag提交子开关

# ── M2: Kali VM连接配置 ──
CPA_M2_KALI_VM_HOST=192.168.56.101   # Kali VM IP地址
CPA_M2_KALI_VM_PORT=22               # Kali VM SSH端口（VM内）
# 注意：Windows本机通过端口2222连接（VMware NAT转发）
CPA_M2_KALI_VM_USER=kali             # Kali VM用户名
CPA_M2_KALI_VM_KEY=~/.ssh/kali_vm    # SSH私钥路径

# ── M2: CTF平台配置（可选） ──
CPA_CTF_PLATFORM_TYPE=ctfd           # 平台类型: ctfd/htb/tryhackme/rootme/manual
CPA_CTF_PLATFORM_URL=https://ctf.example.com
CPA_CTF_API_KEY=ctfd_api_key_xxx     # CTFd API Key
CPA_CTF_AUTO_SUBMIT=true             # 是否自动提交Flag
```

### 6.2 SSH端口转发说明

| 连接方 | 地址 | 端口 | 说明 |
|--------|------|------|------|
| Windows本机 → Kali VM | localhost | 2222 | VMware NAT转发 |
| Kali VM内部 | localhost | 22 | SSH服务原生端口 |

所以Windows本机连接Kali VM用 `ssh -p 2222 kali@localhost`，但M2模块配置中`CPA_M2_KALI_VM_PORT=22`（模块内部通过Docker/SSH exec在VM内执行，走22端口）。

如果你的M2模块设计为从Windows直接SSH到Kali，则`CPA_M2_KALI_VM_PORT=2222`。

---

## 七、验证测试

### 7.1 测试M1模块

```powershell
# 1. 启动PentestAgent
pentestagent

# 2. 在TUI中输入：
> /api
# 应看到彩色状态面板，所有Provider 🟢 健康

> /api providers
# 应看到你配置的4个Provider

> /api cost
# 应显示消耗统计（刚开始都是0）

> /api test zz_a_claude
# 手动测试某个Provider，应显示响应时间
```

### 7.2 测试M2模块

```powershell
# 在TUI中输入：
> /ctf
# 应看到CTF Kit状态面板，所有工具 🟢 就绪

> /ctf list
# 应看到5个Playbook模板

> /ctf status
# 应看到各子模块可用性

> /ctf decode "SGVsbG8gV29ybGQh"
# 应触发自动解码，显示Base64解码结果 "Hello World!"
```

### 7.3 测试故障转移（可选）

```powershell
# 方法：临时改错一个Provider的API Key，看它是否自动切换

# 1. 修改.env，把主Provider的API_KEY改成错的
# 2. 重启PentestAgent
# 3. 发送一个请求
# 4. 观察 /api 面板：主Provider应变🔴，自动切换到备用Provider
```

### 7.4 测试Kali VM连接

```powershell
# Windows PowerShell中：
ssh -i $env:USERPROFILE\.ssh\kali_vm -p 2222 kali@localhost "python3 -c 'import pwn; print(\"pwntools OK\")'"
# 应输出: pwntools OK
```

---

## 八、故障排查

### 8.1 PentestAgent启动失败

| 症状 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: cpa_modules` | 模块路径不在PYTHONPATH | 确认`cpa_modules/`目录在项目根目录 |
| `ImportError: cannot import name 'init_m1'` | M1文件缺失或语法错误 | 检查`cpa_modules/m1_api_hub/__init__.py`是否存在 |
| TUI不显示`/api`命令 | Hook未生效 | 检查`__main__.py`中M1初始化代码 |

### 8.2 M1 Provider连接失败

```powershell
# 诊断步骤：

# 1. 检查网络连通性
curl https://api.zz-a.com/v1/models
# 应返回模型列表，如连不通则是网络问题

# 2. 检查API Key有效性
curl -H "Authorization: Bearer sk-xxx" https://api.zz-a.com/v1/chat/completions \
  -d '{"model":"claude-sonnet-4","messages":[{"role":"user","content":"hi"}]}'
# 如返回401则是Key无效，403是余额不足

# 3. 查看PentestAgent日志
# 日志位置通常在用户目录的.pentestagent/logs/
```

### 8.3 M2工具不可用

```powershell
# 1. 检查Kali VM是否运行
ping 192.168.56.101

# 2. 检查SSH连接
ssh -i ~/.ssh/kali_vm -p 2222 kali@localhost "echo OK"

# 3. 检查Kali VM中的工具
ssh -i ~/.ssh/kali_vm -p 2222 kali@localhost "python3 -c 'import pwn; print(pwn.__version__)'"
ssh -i ~/.ssh/kali_vm -p 2222 kali@localhost "r2 -v"

# 4. 检查环境变量
cat .env | findstr "CPA_M2"
```

### 8.4 恢复Kali VM快照

如果Kali VM环境被搞坏了：

```
VMware → VM → Snapshot → Restore Snapshot → 选择"初始 clean 状态"
```

30秒恢复到干净环境。

---

**部署完成！** 接下来阅读 [D1: M1M2用户使用手册](D1_M1M2_用户使用手册.md) 学习如何使用。

