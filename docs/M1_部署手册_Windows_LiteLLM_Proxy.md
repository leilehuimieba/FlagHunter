# M1: Windows 本机 LiteLLM Proxy 部署手册

> **版本**: v1.0  
> **适用系统**: Windows 10/11  
> **目标**: 部署 LiteLLM Proxy 作为多渠道 API 调度中心，为 PentestAgent 提供高可用的 LLM 路由服务  
> **部署端口**: 4000

---

## 1. 前置条件

### 1.1 系统要求

| 项目 | 最低要求 | 推荐配置 |
|------|---------|---------|
| 操作系统 | Windows 10 1903+ | Windows 11 23H2+ |
| 内存 | 4 GB | 8 GB |
| 磁盘空间 | 2 GB 可用空间 | 5 GB 可用空间 |
| 网络 | 可访问中转站 API | 稳定的外网连接 |
| PowerShell | 5.1 | 7.x (pwsh) |

### 1.2 需提前安装的软件

**Python 3.10+**

```powershell
# 检查 Python 版本（需 3.10 或更高）
python --version
# 预期输出: Python 3.10.x 或更高

# 如未安装，从 https://www.python.org/downloads/ 下载安装
# 安装时务必勾选 "Add Python to PATH"
```

**Git（可选，用于版本管理配置）**

```powershell
git --version
# 如未安装，从 https://git-scm.com/download/win 下载
```

**PowerShell 7（推荐，性能更好）**

```powershell
# 检查是否已安装
pwsh --version

# 如未安装，使用 winget 一键安装
winget install --id Microsoft.PowerShell --source winget
```

### 1.3 网络要求

- 本机端口 `4000` 未被占用
- 可访问各中转站 API 端点（需提前确认网络连通性）
- 防火墙允许本地回环地址访问 `127.0.0.1:4000`

---

## 2. 安装步骤

### 步骤 1: 创建项目目录

```powershell
# 创建 LiteLLM Proxy 专属目录
New-Item -ItemType Directory -Force -Path "C:\Tools\LiteLLM-Proxy" | Out-Null
Set-Location "C:\Tools\LiteLLM-Proxy"

# 创建配置和日志子目录
New-Item -ItemType Directory -Force -Path "config" | Out-Null
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
```

### 步骤 2: 创建 Python 虚拟环境

```powershell
# 创建 venv（避免污染全局 Python 环境）
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 验证已进入虚拟环境（提示符前应有 (venv) 标识）
# 升级 pip 到最新版
python -m pip install --upgrade pip
```

> **提示**: 若执行策略阻止脚本运行，以管理员身份执行：
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 步骤 3: 安装 LiteLLM Proxy

```powershell
# 确保在虚拟环境中（提示符前有 (venv)）
# 安装 LiteLLM Proxy 及全部依赖
pip install "litellm[proxy]>=1.40.0"

# 安装过程约 3-5 分钟，取决于网络速度
# 安装完成后验证
litellm --version
```

### 步骤 4: 验证安装

```powershell
# 快速启动测试（无配置，仅验证安装）
litellm --port 4000 --detection

# 按 Ctrl+C 停止测试服务
# 如能正常启动并显示 "LiteLLM Proxy started on port 4000"，则安装成功
```

---

## 3. 配置文件编写

### 3.1 创建主配置文件

在 `C:\Tools\LiteLLM-Proxy\config\cpa_llm_router.yaml` 创建以下配置：

```yaml
# ============================================================
# CPA LiteLLM Router 配置 - 多渠道 API 调度中心
# ============================================================
# 功能: 管理多个中转站 API Key，自动故障转移
# 适用: PentestAgent 项目的 LLM 路由需求
# ============================================================

model_list:
  # ----------------------------------------------------------
  # Provider 1: 中转站A - Claude 系列
  # ----------------------------------------------------------
  - model_name: claude-primary
    litellm_params:
      model: anthropic/claude-sonnet-4-20250514
      api_key: os.environ/ZHONGZHUAN_A_CLAUDE_KEY
      api_base: os.environ/ZHONGZHUAN_A_BASE_URL
      timeout: 120
    model_info:
      id: zhongzhuan-a-claude
      description: "中转站A - Claude Sonnet 主力"

  # ----------------------------------------------------------
  # Provider 2: 中转站B - Claude 备用
  # ----------------------------------------------------------
  - model_name: claude-backup
    litellm_params:
      model: anthropic/claude-sonnet-4-20250514
      api_key: os.environ/ZHONGZHUAN_B_CLAUDE_KEY
      api_base: os.environ/ZHONGZHUAN_B_BASE_URL
      timeout: 120
    model_info:
      id: zhongzhuan-b-claude
      description: "中转站B - Claude Sonnet 备用"

  # ----------------------------------------------------------
  # Provider 3: 中转站A - GPT-4o
  # ----------------------------------------------------------
  - model_name: gpt4o-primary
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/ZHONGZHUAN_A_GPT_KEY
      api_base: os.environ/ZHONGZHUAN_A_BASE_URL
      timeout: 120
    model_info:
      id: zhongzhuan-a-gpt4o
      description: "中转站A - GPT-4o 主力"

  # ----------------------------------------------------------
  # Provider 4: DeepSeek 官方
  # ----------------------------------------------------------
  - model_name: deepseek-chat
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_API_KEY
      timeout: 180
    model_info:
      id: deepseek-official
      description: "DeepSeek 官方 API"

  # ----------------------------------------------------------
  # Provider 5: 官方 Claude（保底）
  # ----------------------------------------------------------
  - model_name: claude-official
    litellm_params:
      model: anthropic/claude-sonnet-4-20250514
      api_key: os.environ/ANTHROPIC_API_KEY
      timeout: 120
    model_info:
      id: anthropic-official
      description: "Anthropic 官方 Claude Sonnet 保底"

  # ----------------------------------------------------------
  # 模型别名: PentestAgent 使用的统一入口
  # ----------------------------------------------------------
  - model_name: pentest-claude
    litellm_params:
      model: anthropic/claude-sonnet-4-20250514
      api_key: os.environ/ZHONGZHUAN_A_CLAUDE_KEY
      api_base: os.environ/ZHONGZHUAN_A_BASE_URL
      timeout: 120

  - model_name: pentest-gpt4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/ZHONGZHUAN_A_GPT_KEY
      api_base: os.environ/ZHONGZHUAN_A_BASE_URL
      timeout: 120

  - model_name: pentest-deepseek
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_API_KEY
      timeout: 180

# ============================================================
# LiteLLM 核心设置
# ============================================================
litellm_settings:
  # 丢弃不支持的参数（避免报错）
  drop_params: true

  # 请求超时（秒）
  request_timeout: 120

  # 全局重试次数
  num_retries: 3

  # 重试间隔（秒）
  retry_after: 5

  # 日志回调
  success_callback: []
  failure_callback: []

  # 关闭消息内容日志（安全考虑）
  turn_off_message_logging: true

  # 用户 API Key 信息脱敏
  redact_user_api_key_info: true

  # JSON 格式日志（便于解析）
  json_logs: true

# ============================================================
# 路由设置 - 故障转移与负载均衡
# ============================================================
router_settings:
  # 路由策略: least-busy（最少活跃请求优先）
  routing_strategy: least-busy

  # 部署失败冷却时间（秒），失败后 60 秒内不再路由到该节点
  cooldown_time: 60

  # 允许失败次数阈值，超过后触发冷却
  allowed_fails: 2

  # 路由重试次数
  num_retries: 2

  # 启用预调用检查（验证模型可用性）
  enable_pre_call_checks: true

  # ----------------------------------------------------------
  # 降级链配置（核心功能：故障自动转移）
  # ----------------------------------------------------------
  fallbacks:
    # Claude 主链路: 中转站A → 中转站B → 官方 Claude
    - claude-primary: [claude-backup, claude-official]
    # GPT-4o 链路: 中转站A → DeepSeek
    - gpt4o-primary: [deepseek-chat]
    # PentestAgent 别名路由
    - pentest-claude: [claude-backup, claude-official]
    - pentest-gpt4o: [gpt4o-primary, deepseek-chat]

  # 上下文窗口超限降级: 小模型 → 大模型
  context_window_fallbacks:
    - deepseek-chat: [claude-official]

# ============================================================
# 代理全局设置
# ============================================================
general_settings:
  # 主控密钥（用于访问 Proxy API，必须设置）
  master_key: os.environ/LITELLM_MASTER_KEY

  # 日志级别: DEBUG / INFO / WARNING / ERROR
  log_level: INFO

  # 全局最大并行请求数
  global_max_parallel_requests: 50

  # 端口
  port: 4000

  # 主机
  host: 0.0.0.0
```

### 3.2 配置字段说明

| 配置段 | 字段 | 说明 |
|--------|------|------|
| `model_list` | `model_name` | 模型别名，客户端请求时使用 |
| `model_list` | `litellm_params.model` | 实际模型标识，`provider/model-name` 格式 |
| `model_list` | `litellm_params.api_key` | API Key，使用 `os.environ/变量名` 从环境变量读取 |
| `model_list` | `litellm_params.api_base` | 中转站基础 URL，覆盖默认端点 |
| `model_list` | `litellm_params.timeout` | 单次请求超时时间（秒） |
| `router_settings` | `routing_strategy` | 负载均衡策略 |
| `router_settings` | `cooldown_time` | 节点故障冷却时间（秒） |
| `router_settings` | `allowed_fails` | 触发冷却的连续失败次数 |
| `router_settings` | `fallbacks` | **核心：降级链配置** |
| `general_settings` | `master_key` | Proxy 访问认证密钥 |

### 3.3 降级链逻辑说明

```
PentestAgent 请求 claude-primary
        ↓
  中转站A Claude 可用？
        ↓ 否
  中转站B Claude 可用？
        ↓ 否
  官方 Claude 可用？
        ↓ 否
  返回错误
```

---

## 4. 启动脚本

### 4.1 创建环境变量配置脚本

创建 `C:\Tools\LiteLLM-Proxy\set-env.ps1`：

```powershell
# ============================================================
# LiteLLM Proxy 环境变量配置
# ============================================================
# 警告: 此文件包含敏感信息，请勿提交到 Git！
# 建议设置文件权限: 仅当前用户可读
# ============================================================

# ---- 中转站 A ------------------------------------------------
$env:ZHONGZHUAN_A_BASE_URL = "https://api.zhongzhuan-a.example.com/v1"
$env:ZHONGZHUAN_A_CLAUDE_KEY = "sk-zhongzhuan-a-claude-key-here"
$env:ZHONGZHUAN_A_GPT_KEY = "sk-zhongzhuan-a-gpt-key-here"

# ---- 中转站 B ------------------------------------------------
$env:ZHONGZHUAN_B_BASE_URL = "https://api.zhongzhuan-b.example.com/v1"
$env:ZHONGZHUAN_B_CLAUDE_KEY = "sk-zhongzhuan-b-claude-key-here"

# ---- DeepSeek 官方 -------------------------------------------
$env:DEEPSEEK_API_KEY = "sk-deepseek-key-here"

# ---- Anthropic 官方（保底）------------------------------------
$env:ANTHROPIC_API_KEY = "sk-ant-api03-official-key-here"

# ---- LiteLLM 主控密钥 ----------------------------------------
# 用于 PentestAgent 访问 Proxy 的认证密钥
$env:LITELLM_MASTER_KEY = "cpa-litellm-master-key-2024"

Write-Host "[OK] 环境变量已加载" -ForegroundColor Green
```

### 4.2 创建启动脚本

创建 `C:\Tools\LiteLLM-Proxy\start-proxy.ps1`：

```powershell
#!/usr/bin/env pwsh
# ============================================================
# LiteLLM Proxy 启动脚本
# ============================================================

$ErrorActionPreference = "Stop"
$ProxyDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProxyDir

# 加载环境变量
. "$ProxyDir\set-env.ps1"

# 激活虚拟环境
. "$ProxyDir\venv\Scripts\Activate.ps1"

# 配置日志
$LogFile = "$ProxyDir\logs\litellm-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

Write-Host "[INFO] 启动 LiteLLM Proxy..." -ForegroundColor Cyan
Write-Host "[INFO] 配置: config\cpa_llm_router.yaml" -ForegroundColor Cyan
Write-Host "[INFO] 端口: 4000" -ForegroundColor Cyan
Write-Host "[INFO] 日志: $LogFile" -ForegroundColor Cyan

# 启动服务（日志同时输出到文件和控制台）
litellm `
  --config "$ProxyDir\config\cpa_llm_router.yaml" `
  --port 4000 `
  --host 0.0.0.0 `
  2>&1 | Tee-Object -FilePath $LogFile
```

### 4.3 后台运行方案

#### 方案 A: PowerShell 后台任务（快速测试）

```powershell
# 进入项目目录
cd C:\Tools\LiteLLM-Proxy

# 加载环境变量
. .\set-env.ps1

# 激活虚拟环境
. .\venv\Scripts\Activate.ps1

# 后台启动（使用 Start-Process 无窗口模式）
$LogFile = "C:\Tools\LiteLLM-Proxy\logs\litellm-bg-$(Get-Date -Format 'yyyyMMdd').log"
Start-Process -FilePath "litellm" `
  -ArgumentList "--config", "C:\Tools\LiteLLM-Proxy\config\cpa_llm_router.yaml", "--port", "4000" `
  -WindowStyle Hidden `
  -RedirectStandardOutput $LogFile `
  -RedirectStandardError "$LogFile.error"

Write-Host "[OK] LiteLLM Proxy 已在后台启动 (PID: $(Get-Process -Name python | Select-Object -First 1 -ExpandProperty Id))"
```

#### 方案 B: 任务计划程序（推荐，开机自启）

```powershell
# 以管理员权限运行 PowerShell，执行以下命令

$TaskName = "LiteLLM-Proxy"
$ProxyDir = "C:\Tools\LiteLLM-Proxy"
$Action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ProxyDir\start-proxy.ps1`""

$Trigger = New-ScheduledTaskTrigger -AtStartup

# 使用 SYSTEM 账户运行，或指定你的用户
$Principal = New-ScheduledTaskPrincipal `
  -UserId "$env:USERNAME" `
  -LogonType ServiceAccount `
  -RunLevel Highest

$Settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Principal $Principal `
  -Settings $Settings `
  -Force

Write-Host "[OK] 任务计划已创建: $TaskName (开机自启)"

# 立即启动测试
Start-ScheduledTask -TaskName $TaskName
```

#### 方案 C: 使用 WinSW 注册为 Windows 服务（生产环境）

```powershell
# 1. 下载 WinSW
$WinSwUrl = "https://github.com/winsw/winsw/releases/download/v3.0.0-alpha.11/WinSW-x64.exe"
Invoke-WebRequest -Uri $WinSwUrl -OutFile "C:\Tools\LiteLLM-Proxy\litellm-service.exe"

# 2. 创建服务配置文件
@"
<service>
  <id>litellm-proxy</id>
  <name>LiteLLM Proxy Service</name>
  <description>多渠道 LLM API 调度中心</description>
  <executable>C:\Tools\LiteLLM-Proxy\venv\Scripts\litellm.exe</executable>
  <arguments>--config C:\Tools\LiteLLM-Proxy\config\cpa_llm_router.yaml --port 4000</arguments>
  <workingdirectory>C:\Tools\LiteLLM-Proxy</workingdirectory>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold>
    <keepFiles>8</keepFiles>
  </log>
  <env name="LITELLM_MASTER_KEY" value="cpa-litellm-master-key-2024"/>
  <!-- 其他环境变量按实际填写 -->
  <onfailure action="restart" delay="10 sec"/>
  <onfailure action="restart" delay="20 sec"/>
</service>
"@ | Set-Content -Path "C:\Tools\LiteLLM-Proxy\litellm-service.xml" -Encoding UTF8

# 3. 安装并启动服务（需管理员权限）
cd C:\Tools\LiteLLM-Proxy
.\litellm-service.exe install
.\litellm-service.exe start

# 查看服务状态
.\litellm-service.exe status
```

### 4.4 停止服务命令

```powershell
# 方案 A: 停止后台进程
Get-Process -Name "python" | Where-Object { $_.CommandLine -like "*litellm*" } | Stop-Process -Force

# 方案 B: 停止计划任务
Stop-ScheduledTask -TaskName "LiteLLM-Proxy"

# 方案 C: 停止 Windows 服务
cd C:\Tools\LiteLLM-Proxy
.\litellm-service.exe stop
```

---

## 5. 验证测试

### 测试 1: Proxy 是否启动成功

```powershell
# 检查健康状态
curl.exe -s http://localhost:4000/health | python -m json.tool

# 预期输出:
# {
#     "healthy_endpoints": [...],
#     "unhealthy_endpoints": [],
#     "status": "healthy"
# }

# 检查模型列表
curl.exe -s http://localhost:4000/v1/models `
  -H "Authorization: Bearer cpa-litellm-master-key-2024" | python -m json.tool

# 预期输出包含配置的模型列表
```

### 测试 2: 各 Provider 是否可达

```powershell
# 测试中转站 A Claude
$Body = @{
    model = "claude-primary"
    messages = @(@{role="user"; content="Say hello in 5 words"})
    max_tokens = 50
} | ConvertTo-Json -Depth 5

curl.exe -s http://localhost:4000/v1/chat/completions `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer cpa-litellm-master-key-2024" `
  -d $Body | python -m json.tool

# 预期输出包含 assistant 的回复消息
```

```powershell
# 测试 DeepSeek
$Body = @{
    model = "deepseek-chat"
    messages = @(@{role="user"; content="你好"})
    max_tokens = 50
} | ConvertTo-Json -Depth 5

curl.exe -s http://localhost:4000/v1/chat/completions `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer cpa-litellm-master-key-2024" `
  -d $Body | python -m json.tool
```

### 测试 3: 故障转移是否生效

```powershell
# 模拟故障：将中转站A的 URL 设为无效地址
# 编辑 set-env.ps1，临时修改 $env:ZHONGZHUAN_A_BASE_URL 为错误地址
# 重启 Proxy 后测试 pentest-claude（应自动降级到中转站B或官方）

$Body = @{
    model = "pentest-claude"
    messages = @(@{role="user"; content="Hello"})
    max_tokens = 50
} | ConvertTo-Json -Depth 5

# 发送请求，观察日志中的 fallback 行为
curl.exe -s http://localhost:4000/v1/chat/completions `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer cpa-litellm-master-key-2024" `
  -d $Body 2>&1

# 查看日志确认 fallback 路径
Get-Content C:\Tools\LiteLLM-Proxy\logs\litellm-*.log -Tail 20
# 预期看到: "Falling back to model claude-backup" 或类似日志
```

### 测试 4: Token 追踪

```powershell
# LiteLLM Proxy 自动在响应头中返回 Token 使用量
$response = curl.exe -s -D - http://localhost:4000/v1/chat/completions `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer cpa-litellm-master-key-2024" `
  -d (@{model="pentest-claude"; messages=@(@{role="user"; content="Hello"}); max_tokens=50} | ConvertTo-Json)

# 查看响应头中的 x-litellm-* 字段
$response | Select-String "x-litellm"

# 预期看到: x-litellm-response-cost, x-litellm-model-used 等
```

---

## 6. 与 PentestAgent 集成

### 6.1 配置 PentestAgent 指向本地 Proxy

在 PentestAgent 项目根目录创建/修改 `.env` 文件：

```env
# ============================================================
# PentestAgent 配置 - 指向本地 LiteLLM Proxy
# ============================================================

# ---- LLM 配置（通过 LiteLLM Proxy）----------------------------
# 使用 OpenAI 兼容格式连接本地 Proxy
OPENAI_API_KEY=cpa-litellm-master-key-2024
OPENAI_API_BASE=http://localhost:4000

# 模型选择（对应 LiteLLM 配置的 model_name 别名）
# 主用 Claude Sonnet
PENTESTAGENT_MODEL=pentest-claude

# ---- 备选模型配置（如需切换）----------------------------------
# PENTESTAGENT_MODEL=pentest-gpt4o
# PENTESTAGENT_MODEL=pentest-deepseek

# ---- 其他原有配置保持不变 --------------------------------------
# TAVILY_API_KEY=tvly-...
```

### 6.2 集成验证

```powershell
# 1. 确保 LiteLLM Proxy 已启动
curl.exe -s http://localhost:4000/health | Select-String "healthy"

# 2. 进入 PentestAgent 项目目录
cd C:\path\to\pentestagent

# 3. 激活 PentestAgent 虚拟环境
.\venv\Scripts\Activate.ps1

# 4. 运行 PentestAgent TUI（测试连接）
pentestagent -t 127.0.0.1

# 如 TUI 正常启动且无 API 连接错误，则集成成功
```

### 6.3 多模型切换指南

| 场景 | `.env` 配置 | 说明 |
|------|-------------|------|
| 主力 Claude | `PENTESTAGENT_MODEL=pentest-claude` | 走中转站A，故障自动转移 |
| 主力 GPT-4o | `PENTESTAGENT_MODEL=pentest-gpt4o` | 走中转站A，降级到 DeepSeek |
| 主力 DeepSeek | `PENTESTAGENT_MODEL=pentest-deepseek` | 直连 DeepSeek 官方 |
| 强制官方 Claude | `PENTESTAGENT_MODEL=claude-official` | 绕过所有中转站 |

---

## 7. 故障排查

### 7.1 常见问题速查

| 序号 | 问题现象 | 可能原因 | 解决方案 |
|------|---------|---------|---------|
| 1 | `ModuleNotFoundError: No module named 'litellm'` | 未激活虚拟环境 | 执行 `.\venv\Scripts\Activate.ps1` |
| 2 | `Port 4000 already in use` | 端口被占用 | `netstat -ano \| findstr 4000` 找到占用进程并结束 |
| 3 | `AuthenticationError: 401` | Master Key 不匹配 | 检查请求头的 `Authorization` 与 `LITELLM_MASTER_KEY` |
| 4 | `Connection timeout` | 中转站网络不通 | 用 `curl` 直接测试中转站 URL |
| 5 | `API key not found` | 环境变量未加载 | 确认执行了 `.\set-env.ps1` |
| 6 | 降级不生效 | fallback 配置错误 | 检查 `cpa_llm_router.yaml` 中 `fallbacks` 的缩进和格式 |
| 7 | 模型返回 `not found` | model_name 拼写错误 | 用 `curl /v1/models` 确认可用模型列表 |
| 8 | `No healthy deployments` | 所有节点都冷却了 | 等待 `cooldown_time`（默认60秒）后重试 |
| 9 | 后台任务消失 | PowerShell 会话结束 | 改用任务计划程序或 WinSW 方案 |
| 10 | 服务启动后立即退出 | 环境变量缺失 | 检查 WinSW XML 中的 `<env>` 配置 |
| 11 | SSL/TLS 证书错误 | 中转站证书问题 | 在 litellm_params 添加 `verify: false`（仅测试） |
| 12 | 响应慢/卡死 | 某节点超时未返回 | 降低 `timeout` 值，加快触发 fallback |

### 7.2 日志查看

```powershell
# 查看最新日志（实时）
Get-Content C:\Tools\LiteLLM-Proxy\logs\litellm-*.log -Wait -Tail 20

# 搜索错误信息
Select-String -Path "C:\Tools\LiteLLM-Proxy\logs\*.log" -Pattern "ERROR|FALLBACK|timeout"

# 查看 JSON 格式化的日志
Get-Content C:\Tools\LiteLLM-Proxy\logs\*.log -Tail 10 | ForEach-Object {
    $_ | python -m json.tool 2>$null
}
```

### 7.3 调试模式启动

```powershell
# 调试模式（详细日志输出到控制台）
cd C:\Tools\LiteLLM-Proxy
. .\set-env.ps1
. .\venv\Scripts\Activate.ps1
litellm --config .\config\cpa_llm_router.yaml --port 4000 --debug

# 或设置环境变量启用 LiteLLM 详细日志
$env:LITELLM_LOG = "DEBUG"
litellm --config .\config\cpa_llm_router.yaml --port 4000
```

### 7.4 网络连通性检查

```powershell
# 检查本地 Proxy 是否监听
Test-NetConnection -ComputerName localhost -Port 4000

# 检查中转站连通性
Test-NetConnection -ComputerName api.zhongzhuan-a.example.com -Port 443

# 直接测试中转站 API（绕过 Proxy）
curl.exe -v https://api.zhongzhuan-a.example.com/v1/models `
  -H "Authorization: Bearer sk-zhongzhuan-a-key"
```

---

## 8. 安全建议

### 8.1 API Key 存储

```powershell
# 正确做法: 使用环境变量（已在 set-env.ps1 中实现）
# 错误做法: 将 Key 写入 YAML 配置文件

# 额外安全措施: 设置文件权限（仅当前用户可读写）
$Path = "C:\Tools\LiteLLM-Proxy\set-env.ps1"
$Acl = Get-Acl $Path

# 移除继承权限
$Acl.SetAccessRuleProtection($true, $false)

# 仅保留当前用户权限
$Rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $env:USERNAME, "Read,Write", "Allow"
)
$Acl.SetAccessRule($Rule)
Set-Acl $Path $Acl
```

### 8.2 Master Key 配置

- `LITELLM_MASTER_KEY` 长度至少 32 个字符
- 定期更换（建议每 90 天）
- 不同环境使用不同的 Master Key

### 8.3 日志脱敏

配置已启用以下安全选项：

```yaml
litellm_settings:
  turn_off_message_logging: true      # 不记录消息内容
  redact_user_api_key_info: true       # 脱敏 API Key
```

---

## 9. 维护指南

### 9.1 添加新 Provider

编辑 `config\cpa_llm_router.yaml`，在 `model_list` 末尾添加：

```yaml
  - model_name: new-provider-model
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/NEW_PROVIDER_KEY
      api_base: os.environ/NEW_PROVIDER_BASE_URL
      timeout: 120
```

在 `set-env.ps1` 中添加对应环境变量，然后重启 Proxy。

### 9.2 修改降级链

编辑 `cpa_llm_router.yaml` 中的 `router_settings.fallbacks`：

```yaml
  fallbacks:
    # 格式: 原模型: [降级目标1, 降级目标2, ...]
    - claude-primary: [claude-backup, claude-official, deepseek-chat]
```

### 9.3 更新 LiteLLM 版本

```powershell
cd C:\Tools\LiteLLM-Proxy
. .\venv\Scripts\Activate.ps1

# 检查当前版本
litellm --version

# 更新到最新版
pip install --upgrade "litellm[proxy]"

# 如更新后异常，回退到稳定版
pip install "litellm[proxy]==1.40.0"
```

### 9.4 备份与恢复

```powershell
# ---- 备份（建议每月执行）-----------------------------
$BackupDir = "C:\Tools\LiteLLM-Proxy\backups"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
Compress-Archive `
  -Path "C:\Tools\LiteLLM-Proxy\config","C:\Tools\LiteLLM-Proxy\set-env.ps1","C:\Tools\LiteLLM-Proxy\logs" `
  -DestinationPath "$BackupDir\litellm-backup-$Timestamp.zip"

Write-Host "[OK] 备份完成: $BackupDir\litellm-backup-$Timestamp.zip"

# ---- 恢复 -------------------------------------------
# 解压备份到原目录即可
Expand-Archive -Path "$BackupDir\litellm-backup-xxx.zip" -DestinationPath "C:\Tools\LiteLLM-Proxy" -Force
```

---

## 附录: 快速命令索引

```powershell
# 一键启动（交互式）
cd C:\Tools\LiteLLM-Proxy; . .\set-env.ps1; . .\venv\Scripts\Activate.ps1; .\start-proxy.ps1

# 一键启动（后台）
Start-ScheduledTask -TaskName "LiteLLM-Proxy"

# 查看状态
curl.exe -s http://localhost:4000/health

# 查看日志
Get-Content .\logs\*.log -Wait -Tail 20

# 停止服务
Stop-ScheduledTask -TaskName "LiteLLM-Proxy"
# 或: Get-Process python | Where-Object { $_.CommandLine -like "*litellm*" } | Stop-Process
```

---

> **文档结束**  
> 如有问题，查看日志目录 `C:\Tools\LiteLLM-Proxy\logs\` 获取详细错误信息。
