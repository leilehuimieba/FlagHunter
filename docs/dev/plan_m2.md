# M2 CTF Kit 模块开发执行计划

## 任务概述
按《M2多Agent并行调度手册》完成 `cpa_modules/m2_ctf_kit/` 目录下9个文件的开发。

## 技术约束
- Python 3.10+，async异步编程
- Kali VM执行（SSH/Docker exec），不在Windows本机
- 延迟加载pwntools/r2pipe/pycryptodome
- 每个子模块独立开关
- Playbook驱动半自动模式（等LLM确认）

## 文件清单（9个文件）
1. `playbook_engine.py` — Playbook解析执行引擎（Agent-7）
2. `playbooks/web.yaml` — Web类CTF模板（Agent-7）
3. `playbooks/pwn.yaml` — Pwn类CTF模板（Agent-7）
4. `playbooks/crypto.yaml` — Crypto类CTF模板（Agent-7）
5. `playbooks/reverse.yaml` — Reverse类CTF模板（Agent-7）
6. `playbooks/misc.yaml` — Misc类CTF模板（Agent-7）
7. `pwn_tools.py` — Pwn二进制利用工具封装（Agent-8）
8. `crypto_tools.py` — 密码学工具集（Agent-9）
9. `reverse_tools.py` — 逆向工程工具封装（Agent-10）
10. `flag_submitter.py` — CTF平台Flag自动提交（Agent-11）
11. `ctf_commands.py` — /ctf命令注册（Agent-12）
12. `__init__.py` — 模块入口（Agent-12）

## 执行阶段

### Stage 1: Phase 1 并行开发（3个Agent，无依赖）
- **Agent-7**: playbook_engine.py + 5个Playbook模板
- **Agent-8**: pwn_tools.py — 10个Pwn工具函数
- **Agent-9**: crypto_tools.py — 古典/编码/现代/辅助/自动5大类

### Stage 2: Phase 1 审查
- 审查Playbook引擎、Pwn工具、Crypto工具的实现质量

### Stage 3: Phase 2 并行开发（2个Agent，依赖Phase 1）
- **Agent-10**: reverse_tools.py — r2pipe封装
- **Agent-11**: flag_submitter.py — 5个CTF平台

### Stage 4: Phase 2 审查
- 审查逆向工具、Flag提交器

### Stage 5: Phase 3 串行开发（1个Agent，依赖全部）
- **Agent-12**: ctf_commands.py + __init__.py + 3个M0 HOOK

### Stage 6: 最终集成审阅
- 文件完整性、工具覆盖、延迟加载、结果对象一致性、M0侵入量
