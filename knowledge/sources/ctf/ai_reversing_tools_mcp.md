# AI-Powered Reversing Tools & MCP Servers

> Tools that allow AI agents to programmatically interact with reverse engineering suites.

---

## 1. Ghidra MCP Servers

Ghidra is the **most accessible** option (free, open-source, NSA-developed).

### 1.1 GhidraMCP by LaurieWired (原始项目)
- **架构**: Python MCP Bridge + Java Ghidra Plugin
- **功能**: `decompile_function`, `rename_function`, `rename_variable`, `list_defined_strings`, `get_xrefs_to`
- **安装**: 下载 ZIP → Ghidra File → Install Extensions → 重启
- **适用**: 初学者，快速上手
- **仓库**: https://github.com/LaurieWired/GhidraMCP

### 1.2 GhydraMCP by starsong-consulting (高级版)
- **改进**: 多实例支持，HATEOAS REST API
- **适用**: 需要同时分析多个二进制文件的复杂场景
- **仓库**: https://github.com/starsong-consulting/GhydraMCP

### 1.3 GhidrAssistMCP by jtang613 (用户友好版)
- **特点**: 原生 Java 插件（无需 Python Bridge），自带 GUI 配置面板
- **适用**: 不想折腾 Python 环境的用户
- **仓库**: https://github.com/jtang613/GhidrAssistMCP

### 1.4 pyghidra-mcp by clearbluejar (GUI + Headless)
- **特点**: 支持 `--gui` 模式（驱动 live Ghidra CodeBrowser）和 `--headless` 模式
- **命令**: `uvx pyghidra-mcp --gui --transport http --port 8337 --project-path /path/to/project.gpr`
- **适用**: 需要 AI 实时驱动 Ghidra GUI 的场景
- **仓库**: https://github.com/clearbluejar/pyghidra-mcp

### 1.5 Ghidra Bridge (非 MCP，但可包装)
- **特点**: Python 到 Ghidra 的直接 bridge，无需 MCP 层
- **用法**: `import ghidra_bridge; b = ghidra_bridge.GhidraBridge(namespace=globals())`
- **适用**: 想自己写 MCP wrapper 的高级用户
- **仓库**: https://github.com/justfoxing/ghidra_bridge

---

## 2. IDA Pro MCP Servers

IDA Pro 是商业软件，功能最强但需授权。

### 2.1 ida-pro-mcp by mrexodia (最流行)
- **架构**: IDA Plugin (Python) + MCP Server
- **传输**: SSE / stdio / HTTP
- **工具数**: ~76 个（含 debugger 扩展 ~96 个）
- **Headless 模式**: `idalib-mcp` — 基于 IDA 9.0+ 的 `idalib`
- **安装**: `uv run ida-pro-mcp --install`
- **命令**: `uv run ida-pro-mcp --transport http://127.0.0.1:8744/sse`
- **Headless**: `uv run idalib-mcp --host 127.0.0.1 --port 8745 path/to/exe`
- **仓库**: https://github.com/mrexodia/ida-pro-mcp

### 2.2 ida-mcp by jtsylve (多数据库支持)
- **特点**: 支持同时打开多个数据库（per-database worker subprocess）
- **工具**: `decompile_function`, `analyze_funcs`, `basic_blocks`, `callgraph`, `find_regex`, `find_bytes`, `find_insns`, `rename`, `patch`, `stack_frame`
- **传输**: stdio（默认）
- **Prompt 模板**: 8 个内置提示（`survey_binary`, `analyze_function`, `find_crypto_constants`, `auto_rename_strings`）
- **要求**: IDA Pro 9+，Python 3.12+
- **仓库**: https://github.com/jtsylve/ida-mcp

### 2.3 ida-mcp-rs (Rust 实现)
- **特点**: 直接链接 IDA 原生库，支持 macOS/iOS `dyld_shared_cache`
- **工具数**: ~11 个，聚焦核心分析
- **适用**: Apple 平台逆向
- **仓库**: https://github.com/... (搜索 ida-mcp-rs)

### 2.4 对比总结

| 方案 | 需要 GUI | Headless | 多数据库 | 工具数 | 最佳场景 |
|------|----------|----------|----------|--------|---------|
| ida-pro-mcp | 可选 | ✅ idalib | 单进程切换 | ~96 | 通用，功能最全 |
| ida-mcp | 否 | ✅ | ✅ 并发 worker | ~40 | 多文件并行分析 |
| ida-mcp-rs | 否 | ✅ | ? | ~11 | macOS/iOS 分析 |

---

## 3. Radare2 MCP & Python API

Radare2 是开源免费的全能逆向框架，**最适合 Kali 部署**。

### 3.1 radare2-mcp (官方 MCP Server)
- **仓库**: https://github.com/radareorg/radare2-mcp
- **传输**: stdio / SSE
- **适用**: 直接接入 Agent 的 MCP client

### 3.2 r2pipe (Python API)
- **安装**: `pip install r2pipe`
- **用法**:
```python
import r2pipe
r = r2pipe.open("/path/to/binary")
r.cmd("aaa")                    # 分析
print(r.cmd("afl~main"))        # 列出 main 函数
print(r.cmd("pdf @ main"))      # 反汇编 main
print(r.cmd("pdg @ main"))      # 反编译 main (需要 r2ghidra-dec)
print(r.cmdj("izj")[0]["string"])  # 提取字符串 (JSON)
```
- **适用**: 在 Agent 的 `terminal` 或 `pwn` 工具中直接调用

### 3.3 r2sleigh ( radare2 + Ghidra Sleigh)
- **特点**: 将 Ghidra 的 Sleigh 反编译器集成到 radare2
- **新增**: SSA form, 符号执行, 污点分析, 自动函数命名
- **适用**: 需要高级静态分析但不想开 Ghidra GUI
- **仓库**: https://github.com/radareorg/r2sleigh

### 3.4 r2angr (radare2 + angr)
- **特点**: 在 radare2 中直接调用 angr 符号执行
- **命令**: `(r4ge)` 宏
- **适用**: CTF reverse 自动化求解
- **仓库**: https://github.com/radareorg/radare2/wiki/angr

---

## 4. 符号执行框架 (Symbolic Execution)

### 4.1 angr ⭐ (最成熟)
- **安装**: `pip install angr`
- **功能**: CFG 恢复、符号执行、自动漏洞发现、约束求解
- **典型 CTF 用法**:
```python
import angr, claripy

proj = angr.Project("./binary", main_opts={'base_addr': 0x0})
flag = claripy.BVS("flag", 8 * 32)  # 32 字节符号变量

state = proj.factory.full_init_state(args=["./binary"], stdin=flag)
simgr = proj.factory.simulation_manager(state)

# 找到成功分支
simgr.explore(find=lambda s: b"Correct" in s.posix.dumps(1))

if simgr.found:
    solution = simgr.found[0].solver.eval(flag, cast_to=bytes)
    print(solution)
```
- **适用**: Reverse CTF 自动化、路径探索、约束求解

### 4.2 Triton
- **安装**: `pip install triton`
- **功能**: 动态符号执行、污点分析、AST 优化
- **适用**: 需要运行时 trace 的分析

### 4.3 claripy (angr 的约束求解器)
- **用途**: 单独使用符号变量和约束求解

---

## 5. 二进制操作库

| 工具 | 功能 | 安装 |
|------|------|------|
| `pwntools` | CTF pwn 框架：远程交互、ELF 解析、ROP、shellcode | `pip install pwntools` |
| `lief` | ELF/PE/Mach-O 解析、修改、patch | `pip install lief` |
| `capstone` | 多架构反汇编引擎 | `pip install capstone` |
| `keystone` | 多架构汇编引擎 | `pip install keystone-engine` |
| `unicorn` | CPU 模拟器（基于 QEMU） | `pip install unicorn` |
| `qiling` | 高级模拟环境（支持系统调用、文件系统） | `pip install qiling` |
| `frida-tools` | 动态插桩、API hook、运行时 trace | `pip install frida-tools` |
| `ROPgadget` | ROP gadget 查找 | `pip install ropgadget` |
| `ropper` | ROP gadget 查找（支持更多架构） | `pip install ropper` |
| `binwalk` | 固件提取、文件签名扫描 | `apt install binwalk` |
| `z3-solver` | 微软的 SMT 求解器 | `pip install z3-solver` |

---

## 6. 密码学工具

| 工具 | 功能 | 安装 |
|------|------|------|
| `SageMath` | 数学计算、RSA/ECC/Lattice、因数分解 | `apt install sagemath` |
| `RsaCtfTool` | RSA 常见攻击自动化 | `git clone + pip install` |
| `pycryptodome` | 现代加密库（AES/RSA/ECC） | `pip install pycryptodome` |
| `gmpy2` | 大数运算、模逆元 | `pip install gmpy2` |
| `owiener` | Wiener 攻击 | `pip install owiener` |
| `z3-solver` | 约束求解（用于 LFSR、密码分析） | `pip install z3-solver` |
| `john` / `hashcat` | 密码哈希破解 | `apt install john hashcat` |

---

## 7. 推荐 Kali VM 部署方案

在 Kali 上安装以下工具，Agent 通过 SSHRuntime 远程调用：

```bash
# 基础逆向工具
apt update && apt install -y \
    radare2 r2pipe \
    gdb gdbserver \
    binwalk \
    strace ltrace \
    john hashcat

# Python 分析框架
pip3 install -U \
    angr claripy \
    pwntools \
    lief \
    capstone keystone-engine unicorn \
    qiling \
    frida-tools \
    ropgadget ropper \
    r2pipe \
    z3-solver \
    pycryptodome gmpy2 owiener

# SageMath (密码学必备)
apt install -y sagemath

# RsaCtfTool
pip3 install -U git+https://github.com/RsaCtfTool/RsaCtfTool.git

# Ghidra (headless 分析)
# 下载并解压到 /opt/ghidra
# 可通过 ghidra-headless 命令行运行

# IDA Pro (如果已有授权)
# 安装 idalib 支持 headless MCP
```

---

## 8. Agent 集成建议

### 方案 A：SSHRuntime + terminal 调用 (最简单)
Agent 通过 SSH 连接到 Kali，直接用 `terminal` 工具执行 radare2/angr/pwntools 命令。

### 方案 B：封装专用 Agent 工具
为常用操作封装专用工具：
- `radare2` 工具：接受二进制路径和 r2 命令，返回 JSON
- `angr_solve` 工具：接受二进制路径、find/avoid 地址，自动符号执行
- `pwntools_run` 工具：已有，运行 exploit 脚本
- `crypto_solve` 工具：接受加密参数，调用 SageMath/RsaCtfTool

### 方案 C：MCP Server 接入 (最优雅)
在 Kali 上运行 Ghidra MCP / radare2-mcp / ida-mcp，Agent 通过 MCP client 连接。
- 需要 Agent 框架支持外部 MCP server
- 可参考 `flaghunter/mcp/` 目录的适配器实现
