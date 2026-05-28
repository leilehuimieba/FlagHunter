# FlagHunter 交接提示词

> 生成时间：2026-05-24 | 版本：v0.4.1+
> 用途：让新对话直接延续当前任务上下文，无需重新探索

---

## 一、项目定位

**FlagHunter** 是一个 AI 驱动的 CTF/渗透测试智能体框架。当前处于 **CTF 专项能力提升阶段**（内部代号 Phase 6.5~7），核心目标是：让 Agent 在 CTF 实战中能用更少的循环、更少的 token 拿到 flag。

- **架构**：单 Agent (PA) + Crew 多 Agent 模式
- **LLM 层**：LiteLLM 代理，支持多 provider 切换
- **工具层**：30 个已注册工具（含 3 个新增 CTF 工具）
- **知识层**：13 个 CTF 技术文档，本地 RAG（sentence-transformers）

---

## 二、已完成的核心工作（必须了解）

### 1. 知识库扩展（9 个新文件，~3000 行）
路径：`knowledge/sources/ctf/`

| 文件 | 核心内容 |
|------|---------|
| `cmd_injection_blacklist_bypass.md` | `$IFS$1` 空格绕过、关键字过滤、编码绕过、内联执行 |
| `sql_injection_blacklist_bypass.md` | `/**/` 替代空格、`/*!50000UNION*/`、逗号绕过、tamper 脚本 |
| `ssrf_bypass.md` | IP 八进制/十六进制/IPv6、DNS 重绑定、Gopher、云元数据 |
| `php_tricks_and_gotchas.md` | 弱类型、伪协议、POP 链、变量覆盖 |
| `file_upload_bypass.md` | MIME、双扩展名、空字节、magic bytes、竞争条件 |
| `crypto_advanced_attacks.md` | ECC Smart/MOV、LLL 格攻击、LFSR、块密码攻击 |
| `pwn_stack_and_rop.md` | 栈溢出、ret2libc、ROP、Canary、SROP、格式化字符串 |
| `reverse_advanced.md` | VM 分析、去混淆、angr 脚本、Frida、Ghidra 脚本 |
| `ai_reversing_tools_mcp.md` | Ghidra/IDA/radare2 MCP 调研、工具对比 |

> ⚠️ **RAG 当前故障**：Windows host 缺少 `sentence_transformers` 包，`knowledge_search` 工具会报错。如需要 RAG，先执行 `pip install sentence-transformers`。

### 2. CTF Quick Path 优化（实战验证有效）
路径：`pentestagent/agents/pa_agent/ctf_planner.py`

**GXYCTF2019 "Ping Ping Ping" 实测效果**：
- **优化前**：50 循环 / 6分51秒 / 1,097k tokens → 失败（max loops）
- **优化后**：14 循环 / 1分55秒 / 178k tokens → ✅ `flag{0395823a-116a-476b-a131-25d85f7b3930}`

**核心改动**：在 `CTF_QUICK_PATHS["cmd"]` 中新增了：
1. Step 3: `cat$IFS$1index.php` 读取源码（最高优先级，不盲猜 payload）
2. Step 4: `$IFS$1` 空格绕过说明（注意 `$IFS` 后必须加 `$1/$9` 分隔）
3. Step 5: base64 编码绕过 + 变量拼接绕过 `flag` 关键字过滤

**启示**：其他 challenge type（sqli、lfi、crypto、pwn）可能也需要类似的实战调优。

### 3. 新增 3 个 CTF 专用工具

| 工具 | 路径 | 功能 | 运行环境 |
|------|------|------|---------|
| `radare2` | `pentestagent/tools/radare2/__init__.py` | r2pipe 封装：反汇编、字符串、函数、节区 | Kali VM |
| `angr_solve` | `pentestagent/tools/angr_solve/__init__.py` | 符号执行：find/avoid 地址、输入长度、前缀约束 | Kali VM |
| `crypto_solve` | `pentestagent/tools/crypto_solve/__init__.py` | 密码学攻击：RSA (small e/Wiener/common modulus/Hastad)、编码解码、Caesar/XOR 暴力 | Kali VM |

> 三个工具都通过 `SSHRuntime` 在 Kali VM 的 `~/ctf-tools` venv 中执行。

### 4. Kali VM 环境
- **SSH**: `127.0.0.1:2222`, user1, Ed25519 key auth
- **Sudo 密码**: `123456`
- **Venv**: `~/ctf-tools/` (Python 3.13)
- **已安装核心包**：angr 9.2.217、r2pipe 1.9.8、pwntools 4.15.0、z3-solver 4.13.0、pycryptodome 3.23.0、gmpy2、owiener、claripy、unicorn、qiling、frida-tools、ropgadget、ropper、keystone-engine、lief
- **系统工具**：radare2 5.9.8 ✅
- **已安装**：gdb、strace、ltrace、RsaCtfTool
- **安装中**：SageMath (`pip install sagemath-standard`)、Ghidra (zip 下载中)
- **SSHRuntime 结构 bug**：`_extract_forms_from_html` 误置导致类提前结束，已修复
- **部署脚本**：`scripts/kali_setup.sh`

---

## 三、当前待办清单（按优先级排序）

### 🔴 P0：实战验证新工具 ✅
- [x] `crypto_solve`：RSA small-e + base64 通过集成测试（Kali VM）
- [x] `angr_solve`：简单 crackme 通过集成测试（Kali VM）
- [x] `radare2`：`afl` / `iz` 通过集成测试（Kali VM）
- [x] 验证结果已写入 `reports/ctf_tool_validation.md`

### 🟡 P1：继续优化 Quick Path
- [x] 分析 sqli 类型 challenge 的失败案例，给 `CTF_QUICK_PATHS["sqli"]` 增加 blacklist bypass 指导
- [x] 分析 lfi 类型 challenge 的失败案例，优化 `CTF_QUICK_PATHS["lfi"]`
- [x] 分析 crypto 类型 challenge，优化 `CTF_QUICK_PATHS["crypto"]`（结合 `crypto_solve` 工具）
- [x] 分析 pwn 类型 challenge，优化 `CTF_QUICK_PATHS["pwn"]`（结合 `angr_solve` 工具）

### 🟢 P2：环境与基础设施（进行中）
- [x] 修复 Windows host RAG：`sentence-transformers` 已安装，索引重建完成（20 files / 139 docs）
- [x] 修复 `SSHRuntime` 结构 bug：`_extract_forms_from_html` 从类内部移至模块顶部，类方法恢复正常
- [x] 单元测试（291/291 pass，含新增 10 个 CTF 工具测试）
  - `tests/unit/tools/test_crypto_solve.py`（4 tests）
  - `tests/unit/tools/test_angr_solve.py`（3 tests）
  - `tests/unit/tools/test_radare2.py`（3 tests）
- [x] 集成测试（4/4 pass）
  - `tests/integration/test_new_ctf_tools.py`：crypto_solve RSA/base64、radare2 analyze、angr_solve crackme
- [x] Kali VM 补装工具
  - `gdb strace ltrace` ✅
  - `RsaCtfTool` ✅
- [x] Kali VM 大体积工具
  - `Ghidra` ✅：通过 `apt-get install ghidra` 安装成功，headless 分析器路径 `/usr/share/ghidra/support/analyzeHeadless`
  - `sagemath-standard` 🔄：编译依赖（pkg-config, build-essential, libgmp-dev 等）已安装，pip 安装重新启动中

### 🔵 P3：架构与扩展
- [ ] MCP 集成调研：radare2-mcp（官方）、GhidraMCP（LaurieWired）、ida-pro-mcp（mrexodia）
- [ ] 建立 CTF benchmark 套件：5~10 道经典题，量化优化前后的 loops/time/tokens/flag rate
- [ ] 考虑将 CTF quick path 从 hard-code 改为可配置（YAML/JSON），便于 A/B 测试

---

## 四、关键文件速查

| 文件 | 作用 |
|------|------|
| `pentestagent/agents/pa_agent/ctf_planner.py` | CTF quick paths 定义 |
| `pentestagent/agents/pa_agent/prompts.py` | System prompt 构建 |
| `pentestagent/tools/radare2/__init__.py` | radare2 工具实现 |
| `pentestagent/tools/angr_solve/__init__.py` | angr_solve 工具实现 |
| `pentestagent/tools/crypto_solve/__init__.py` | crypto_solve 工具实现 |
| `pentestagent/config/settings.py` | 全局配置（singleton） |
| `pentestagent/tools/loader.py` | 工具注册与发现 |
| `knowledge/sources/ctf/` | CTF 知识文档（13 个文件） |
| `scripts/kali_setup.sh` | Kali 环境部署脚本 |
| `AGENTS.md` | 项目规范与架构说明 |
| `.env` | API Key 与模型配置 |

---

## 五、重要配置参数

```bash
# .env 关键项
ANTHROPIC_API_KEY=sk-ant-...
PENTESTAGENT_MODEL=Codex-sonnet-4-20250514
# 可选
TAVILY_API_KEY=...
OPENAI_API_KEY=sk-...

# 当前活跃 provider
# su8-main (gpt-5.4) / mimo-main (mimo-v2.5-pro) / deepseek-main (deepseek-v4-pro)

# Agent 限制
MAX_LOOPS=50
recon_bundle=enabled
finish=batch mode supported
```

---

## 六、继续工作的正确姿势

1. **先读当前文件状态**：用 `git diff HEAD` 确认未提交的改动
2. **先跑测试确认基线**：`pytest tests/ -x`
3. **如果要验证新工具**：
   - 找一个对应类型的 CTF 题目（如 [CTFHub](https://www.ctfhub.com/) 或本地靶机）
   - 在 TUI 中执行 `/agent <题目描述>` 或 `/assist <任务>`
   - 观察工具调用链和 token 消耗
4. **如果要优化 quick path**：
   - 复现失败案例 → 分析 agent 日志 → 找出卡点 → 在 `ctf_planner.py` 中补充步骤
   - 修改后必须用同一道题重新验证，确认 loops/tokens 下降且 flag 拿到
5. **任何修改后更新本交接文档**，保持上下文同步

---

## 七、已知陷阱

| 陷阱 | 说明 |
|------|------|
| `$IFS` 不加分隔符 | `$IFS` 后直接跟字母会被解析为变量名（如 `$IFSY2F0...`），必须用 `$IFS$1` |
| Kali 网络受限 | GitHub/apt 访问可能被重置，需配置代理或换源 |
| Windows 缺少 sentence_transformers | RAG 会 fallback 或报错，需手动安装 |
| angr 内存占用大 | `angr_solve` 执行时建议设置合理的 timeout，避免 OOM |
| **angr PIE 地址映射** | **radare2 `pdf` 显示文件偏移，angr 使用虚拟地址。64位 PIE 默认基址 `0x400000`，`find_addrs` 必须传虚拟地址（如 `0x401234`）否则 explore 永远找不到路径** |
| **angr 约束未生效** | **原代码中 printable constraints 只被创建未添加到 state.solver，已修复** |
| **angr LoopSeer 崩溃** | **LoopSeer + auto_load_libs=True 时 CFGFast 可能崩溃，已改为 try/except 静默跳过** |
| 工具注册后未生效 | 检查 `__init__.py` 中是否有 `@register_tool` 装饰器，以及工具目录名是否正确 |

---

> **最后更新**：2026-05-24 | 下一对话可直接从「三、当前待办清单」中选择任务继续

