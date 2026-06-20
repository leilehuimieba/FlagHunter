"""FlagHunter 能力层（CAPABILITY）—— CPA 模块 m1..m6 包根。

本包承载 FlagHunter 自顶向下骨架里的 **能力层** 横向扩展模块（ADR §2 目标骨架）。
每个 ``mN_*`` 子包是一块可独立开关的能力，统一遵循以下契约：

- ``init_mN()``      —— 异步初始化入口；由 ``flaghunter/session/initializer.py``
  的 CPA 钩子按环境变量开关逐个调用，失败被吞掉（记 warning 不阻塞主流程）。
- ``is_mN_enabled()`` —— 开关查询；m1 在 initializer 处真正调用它做门控，
  m2–m6 的 initializer 门控直接读各自环境变量（语义见各模块 docstring）。
- ``__all__``        —— 对外暴露的能力符号（getter / 数据类 / 开关）。

模块清单（详见 ``docs/dev/cpa_modules_m1-m6_职责对照表_*.md``）：

==== =================== =========================================================
模块  包名                职责
==== =================== =========================================================
M1   m1_api_hub          多 Provider LLM API 枢纽（路由 / 成本 / 故障切换）
M2   m2_ctf_kit          CTF 工具链（Pwn / Crypto / Reverse / Flag 提交 / Playbook）
M3   m3_reporter         渗透测试报告生成（HTML / Markdown / PDF + 增量追踪 + 截图）
M4   m4_audit_guard      合规审计守卫（审计日志 / RoE / 作用域 / 审批门 / 数据脱敏）
M5   m5_swarm_link       多 Agent 群体协作（共享黑板 / 信息素路由 / 消息 / 共识）
M6   m6_turbo            性能加速（结果缓存 / 并发扫描 / 内存优化）
==== =================== =========================================================

依赖方向（不变量 I1）：能力层只允许向下 import foundation（runtime/llm/knowledge/config），
不得 import orchestration/entry 层。
"""
