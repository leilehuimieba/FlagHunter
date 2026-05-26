# FlagHunter 本地工具集合

本目录保存 `D:\webstudy\FlagHunter` 项目优先使用的本地安全工具副本。

## 解析优先级

项目运行时会优先从以下目录查找工具：

1. `D:\webstudy\FlagHunter\tools`
2. `D:\webstudy\tools`
3. 其他兼容 Windows 的本地工具目录

对应实现位于：

- `D:\webstudy\FlagHunter\pentestagent\tools\_tool_env.py`

## 当前纳入的工具

| 工具 | 项目内路径 | 启动方式 | 说明 |
|---|---|---|---|
| nmap | `D:\webstudy\FlagHunter\tools\nmap\nmap.exe` | 直接执行 | 端口/服务扫描 |
| sqlmap | `D:\webstudy\FlagHunter\tools\sqlmap\sqlmap.cmd` | `.cmd` 包装 | 优先走项目 `.venv` 的 Python |
| gobuster | `D:\webstudy\FlagHunter\tools\gobuster\gobuster.exe` | 直接执行 | 目录、DNS、vhost、fuzz |
| ffuf | `D:\webstudy\FlagHunter\tools\ffuf\ffuf.exe` | 直接执行 | Web fuzz / 目录扫描 |
| nuclei | `D:\webstudy\FlagHunter\tools\nuclei\nuclei.exe` | 直接执行 | 模板化漏洞扫描 |
| dirsearch | `D:\webstudy\FlagHunter\tools\dirsearch\dirsearch.cmd` | `.cmd` 包装 | 优先走项目 `.venv` 的 Python |

## 远程工具 (Kali VM via SSHRuntime)

以下工具**不在 Windows 宿主机**上运行，而是通过 `SSHRuntime` 在 Kali VM 上远程执行：

| 工具 | 类别 | 说明 | Kali 依赖 |
|------|------|------|----------|
| `radare2` | CTF | radare2 二进制分析（反汇编、字符串、函数列表） | `r2pipe`, `radare2` |
| `angr_solve` | CTF | angr 符号执行自动解题 | `angr`, `claripy` |
| `crypto_solve` | CTF | 密码学攻击自动化（RSA、编码、古典密码） | `pycryptodome`, `gmpy2`, `owiener` |
| `pwn` | CTF | pwntools exploit 脚本执行 | `pwntools` |
| `binary` | CTF | 二进制静态分析（checksec、strings、objdump） | `binutils` |

Kali 部署脚本：`scripts/kali_setup.sh`

## 当前验证状态

以下工具已完成真实最小调用验证：

- `nmap`
- `sqlmap`
- `gobuster`
- `ffuf`
- `nuclei`
- `dirsearch`

其中 `dirsearch` 额外依赖已补齐到项目虚拟环境：

- `setuptools==80.9.0`（恢复 `pkg_resources`）
- `psycopg[binary]`
- `mysql-connector-python`
- `requests_ntlm`
- `requests-toolbelt`
- 以及 `requirements.txt` 中其余直接依赖

## 字典

常用字典路径：

- `D:\webstudy\FlagHunter\tools\wordlists\common.txt`
- `D:\webstudy\FlagHunter\tools\wordlists\minimal-web.txt`

其中：

- `common.txt`：从宿主机 Dirsearch 字典复制的常用目录字典
- `minimal-web.txt`：本项目自带的最小自测字典，适合快速连通性验证

## 建议调用方式

优先通过项目运行时的 `find_tool()` 获取路径，不要手写宿主机路径。

示例：

```python
from pentestagent.tools._tool_env import patch_tool_path, find_tool

patch_tool_path()
print(find_tool("nmap"))
print(find_tool("sqlmap"))
print(find_tool("gobuster"))
print(find_tool("ffuf"))
print(find_tool("nuclei"))
print(find_tool("dirsearch"))
```

## 本地工具依赖安装

如果要在新的 Python 虚拟环境中直接使用项目内 `tools/` 集合，建议额外安装：

```bash
pip install -r requirements-local-tools.txt
```

或者使用可选依赖：

```bash
pip install -e ".[localtools]"
```

## 运行本地工具 Smoke Test

默认情况下，真实工具链 smoke test 不会随普通 `pytest` 自动执行。

显式运行方式：

```bash
set RUN_LOCAL_TOOL_SMOKE=1
pytest tests/integration/test_local_tool_smoke.py -q
```

PowerShell:

```powershell
$env:RUN_LOCAL_TOOL_SMOKE='1'
pytest .\tests\integration\test_local_tool_smoke.py -q
```

## Windows 启动包装

以下工具已补本地包装脚本，避免系统 Python / PATH 干扰：

- `D:\webstudy\FlagHunter\tools\sqlmap\sqlmap.cmd`
- `D:\webstudy\FlagHunter\tools\dirsearch\dirsearch.cmd`

## 维护说明

如果后续新增工具，建议同步更新：

1. `D:\webstudy\FlagHunter\tools\README.md`
2. `D:\webstudy\FlagHunter\pentestagent\tools\_tool_env.py`
3. 必要时新增 `.cmd` 包装，确保优先走项目 `.venv`
