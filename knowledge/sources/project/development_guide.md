# PentestAgent-CPA 项目开发指南

## 项目核心设计模式

### 1. Agent 状态机

所有 Agent 继承 `BaseAgent`，共享 `_run_loop()`：

```text
IDLE → THINKING → EXECUTING → (THINKING | COMPLETE | ERROR)
```

- `AgentStateManager` 硬编码合法转移图，非法转移被拒绝
- `force_transition()` 仅用于异常恢复
- 状态历史记录到 `history`，可计算状态持续时间

**开发规则**：新增 Agent 必须继承 `BaseAgent`，重写 `get_system_prompt()`，不要重写 `_run_loop()`。

### 2. 工具 Self-Register 机制

```python
from pentestagent.tools.registry import register_tool, ToolSchema

@register_tool(name="my_tool", description="...", schema=ToolSchema(...), category="scanner")
async def my_tool(arguments: dict, runtime: Runtime) -> str:
    ...
```

- 装饰器在模块导入时自动注册到全局 `_tools` 字典
- `loader.py` 遍历 `pentestagent/tools/` 子目录，通过 `importlib` 触发注册
- 运行时动态注册使用 `register_tool_instance()`（如 MCP 子 Agent 工具）

### 3. CTF 解题引擎架构

CTF 模式不是 LLM 自由发挥，而是**确定性调度器**：

```text
CTFTaskDispatcher.run()
  ├── 浏览器侦察（HTML/表单/端点/Cookie）
  ├── HypothesisEngine.generate()     # 规则生成假设
  ├── StrategyRegistry.execute()      # 策略执行
  ├── CTFVerifier.verify_flag()       # 四级证据验证
  ├── RecoveryController.after_chain() # 规则决策下一步
  └── StrategyMemory.save()           # 持久化本次经验
```

**关键子系统**：
- **HypothesisEngine**：基于页面特征生成假设，Observation Floor 防止无证据假设排在前面
- **StrategyRegistry**：15+ 策略定义，包含 precondition、success_signal、failure_signal
- **CapabilityRegistry**：每个能力原语有多级实现（high/medium/low），自动降级
- **CTFVerifier**：candidate → runtime → verified → rejected 四级证据
- **StrategyMemory**：跨题持久化，自动静音低成功率条目

### 4. LLM 调用链路

```text
Agent.generate()
  ├── ConversationMemory.get_messages_with_summary()
  │     └── 超过 60% token 预算时，分块摘要旧消息，保留最近 10 条
  ├── LLM._call_with_provider_failover()
  │     ├── M1 ProviderManager.select_provider()  # 按 task_hint 路由
  │     └── 错误分类：PERMANENT / TRANSIENT / LOGIC
  └── token_tracker.record_usage_sync()           # 持久化到 loot/token_usage.json
```

### 5. MCP 双向集成

**Client 侧**：
- `MCPManager` 读取 `mcp_servers.json`
- 支持 stdio / SSE / FIFO / WebSocket 四种传输
- 单 Server >128 工具时，启用 `mcp_{server}_rag_optimizer` 元工具

**Server 侧**：
- `MCPRouter` 处理 JSON-RPC：`initialize` / `tools/list` / `tools/call`
- 每个任务创建**全新** Agent + Runtime，避免状态污染
- `spawn_mcp_agent` 通过 FIFO/PTY 启动子 Agent，注入其工具到父 Agent

### 6. Runtime 抽象

三种运行时实现统一 `Runtime` ABC：

| 方法 | LocalRuntime | DockerRuntime | SSHRuntime |
|------|-------------|---------------|------------|
| `execute_command` | `asyncio.subprocess_shell` | `container.exec_run` | `ssh` 子进程 |
| `browser_action` | Playwright + 系统浏览器回退 | `curl` + 正则 | `curl` + 正则 |
| `proxy_action` | `httpx.AsyncClient` | `mitmdump` | 内嵌 Python 脚本 |

**开发规则**：新增 Runtime 必须实现全部 ABC 方法。浏览器操作需处理 `localhost` 别名回退。

### 7. ShadowGraph 知识图

从 `notes.json` 增量构建 NetworkX `DiGraph`：

- **节点类型**：`cred:*`、`service:{host}:{port}`、`endpoint:{host}:{path}`、`tech:{host}:{name}`、`vuln:{key}`
- **边类型**：`CONTAINS`、`AUTH_ACCESS`、`HAS_SERVICE`、`HAS_ENDPOINT`、`USES_TECH`、`AFFECTED_BY`
- **洞察生成**：未使用凭证、高价值目标（度数统计）、多跳攻击路径（`nx.shortest_path`）

### 8. 配置与模块开关

环境变量控制模块加载：

```bash
CPA_M1_API_HUB=true
CPA_M2_CTF_KIT=true
CPA_M2_PWN_TOOLS=true
CPA_M2_CRYPTO_TOOLS=true
CPA_M2_REVERSE_TOOLS=true
CPA_M2_FLAG_SUBMITTER=true
CPA_M5_SWARM_LINK=true
```

`initializer.py` 的 `build_agent_components()` 按顺序初始化：
1. RAG Engine（若 `no_rag=False`）
2. Runtime（Local / Docker / SSH）
3. CPA Modules M1-M6（条件初始化）
4. LLM
5. Agent
6. MCP Manager（若 `no_mcp=False`）

## 开发约束

### 低侵入原则
- 对原版 M0 的修改必须用 `=== CPA MX HOOK BEGIN/END ===` 标记
- 侵入行数控制在 25 行以内
- 新增模块放在 `cpa_modules/` 下，独立目录、独立开关、独立测试

### 延迟加载
- pwntools、r2pipe、capstone 等重型依赖使用 lazy import
- Windows 本机不导入 POSIX-only 模块

### 测试要求
- 新增模块需提供独立测试用例
- 优先写 unit test（`tests/unit/`），再写 integration test
- CTF 功能需通过 `tests/integration/test_ctf_dispatcher_*_acceptance.py` 验收

## 常用调试命令

```bash
# 查看已注册工具
pentestagent tools list

# 查看 API Provider 状态
> /api

# 查看 CTF Playbook
> /ctf list

# 运行单个测试
pytest tests/unit/test_xxx.py -v
pytest tests/integration/test_ctf_dispatcher_acceptance.py -v

# 带覆盖率
pytest --cov=pentestagent --cov-report=html

# 格式化代码
black pentestagent
ruff check pentestagent
```
