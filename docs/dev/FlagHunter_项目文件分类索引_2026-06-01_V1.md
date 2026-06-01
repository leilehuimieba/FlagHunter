# FlagHunter 项目文件分类索引（2026-06-01）V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 文档目的：把当前仓库文件按“核心代码 / 文档 / 测试 / 样本与产物 / 运行时输出 / 临时与可清理项”做一次可维护分类，方便接手、清理、收口和后续文档同步。

---

## 1. 分类原则

这份索引只按“项目推进价值”来分，不按文件名好不好看来分。

### 分类规则

1. **核心代码**
   - 项目真正运行的代码
2. **文档**
   - 当前事实、阶段判断、计划、交接、说明
3. **测试**
   - 单元 / 集成 / 验收 / 回归 / eval
4. **样本与产物**
   - CTF 样本、二进制、压缩包、截图、下载物、报告
5. **运行时输出**
   - 日志、缓存、任务中间产物、运行过程残留
6. **临时与可清理项**
   - 不应长期作为项目事实存在的文件或目录

---

## 2. 仓库顶层分类

### 2.1 核心仓库主结构

#### 核心代码与运行骨架

- `pentestagent/`
- `cpa_modules/`
- `tools/`
- `runtime/`（若在代码引用中对应运行时实现）
- `web/`
- `scripts/`
- `workspaces/`

#### 文档

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `CHANGELOG.md`
- `docs/`

#### 测试

- `tests/`

#### 配置与构建

- `pyproject.toml`
- `requirements.txt`
- `requirements-local-tools.txt`
- `docker-compose.yml`
- `Dockerfile`
- `Dockerfile.kali`
- `.dockerignore`
- `.gitignore`
- `pyrightconfig.json`

#### 环境与启动

- `.env`
- `.env.example`
- `run.bat`
- `docker-entrypoint.sh`

#### 样本 / 产物 / 外部材料

- `my.bin`
- `myde.bin`
- `libcrackme2.so`
- `pow.py`
- `vpow.py`
- `tax_cookie.txt`
- `tmp_tasks_1280.png`
- `tmp_tasks_1366.png`
- `tmp_tasks_1440.png`

#### 运行时输出 / 缓存 / 临时目录

- `logs/`
- `loot/`
- `tmp/`
- `tmp_pwn/`
- `embeddings/`
- `conversations/`
- `.pytest_cache/`
- `__pycache__/`
- `.coverage`

#### 额外工具与本地环境目录

- `.venv/`
- `.claude/`
- `.vscode/`
- `.git/`
- `PowerShell 7.6.2/`
- `null/`

---

## 3. 代码目录分类

### 3.1 `pentestagent/`

这是项目最核心的运行代码目录，建议按职责再分：

#### 入口与全局

- `pentestagent/__main__.py`
- `pentestagent/__init__.py`
- `pentestagent/hooks.py`
- `pentestagent/logging_config.py`
- `pentestagent/observability.py`
- `pentestagent/task_registry.py`

#### Agent 主体

- `pentestagent/agents/`
  - `pa_agent/`：单 agent / CTF 主链
  - `crew/`：多 agent / worker 池
  - `state.py`：共享状态机

#### 配置

- `pentestagent/config/`

#### 接口层

- `pentestagent/interface/`
  - `cli.py`
  - `tui.py`
  - `web_server.py`
  - `mode_router.py`
  - `conversation_store.py`
  - `initializer.py`
  - `notifier.py`
  - `utils.py`

#### Harness / 运行时壳层

- `pentestagent/harness/`
  - `session_ledger.py`
  - `artifact_registry.py`
  - `checkpoint_store.py`
  - `audit_events.py`

#### 知识层

- `pentestagent/knowledge/`
  - `session_context.py`
  - `context_assembler.py`
  - `graph.py`
  - `indexer.py`
  - `rag.py`
  - `retrospective.py`

#### LLM

- `pentestagent/llm/`

#### MCP

- `pentestagent/mcp/`

#### Playbooks

- `pentestagent/playbooks/`

#### Runtime

- `pentestagent/runtime/`

#### Tools

- `pentestagent/tools/`

#### Workspace

- `pentestagent/workspaces/`

---

## 4. 文档目录分类

### 4.1 `docs/`

这部分是当前项目推进最重要的“事实与说明层”。

#### 当前事实层

- `docs/README.md`
- `docs/dev/FlagHunter_reports目录状态与分层建议_2026-06-01_V1.md`
- `docs/web-console/FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
- `docs/web-console/FlagHunter_Web可视化控制台_文档索引与状态矩阵_V1.md`
- `docs/dev/FlagHunter_交接文档_当前主线与第一批任务_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目级source-of-truth状态卡_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目状态核对与下一步讨论底稿_2026-06-01.md`
- `docs/dev/FlagHunter_下一阶段主线_主控_BlackboardLite_调度收紧_V1.md`
- `docs/dev/local_challenge_sample_matrix.md`

#### 背景分析层

- `docs/dev/FlagHunter_Harness优化方案_借鉴Cairn_V1.md`
- `docs/dev/Cairn_源码深度分析_围绕Blackboard与Dispatcher_V1.md`
- `docs/dev/FlagHunter_下一阶段路线_目标驱动_BlackboardLite_V1.md`

#### 计划 / 执行层

- `docs/superpowers/plans/2026-05-29-harness-optimization-plan.md`
- `docs/release-policy.md`
- `docs/release-checklist.md`
- `docs/release-playbook.md`
- `docs/label-strategy.md`

#### 历史 / 归档

- `docs/archive/`

---

## 5. 测试目录分类

### 5.1 `tests/`

#### 单元测试

- `tests/unit/`

#### 集成测试

- `tests/integration/`

#### 安全 / 专项测试

- `tests/security/`

#### 评估 / 样本测试

- `tests/eval/`

#### 顶层基础测试

- `tests/conftest.py`
- `tests/test_mcp_scaffold.py`

### 5.2 当前测试重点

当前测试体系已经覆盖的重点包括：

- Web Console 合同
- Mode Router 合同
- MCP ingress 合同
- Harness event / ledger / checkpoint / artifact
- Local challenge eval pack
- CTF dispatcher 回归与 acceptance

---

## 6. 样本与产物分类

### 6.1 CTF / 二进制 / 样本材料

这些文件更像“样本与分析产物”，不是核心代码：

- `libcrackme2.so`
- `my.bin`
- `myde.bin`
- `pow.py`
- `vpow.py`

### 6.2 本地题目 / 口令 / 附件类材料

- `tax_cookie.txt`
- `tmp_tasks_1280.png`
- `tmp_tasks_1366.png`
- `tmp_tasks_1440.png`

### 6.3 CTF 工具资料

- `tools/` 下的各种 scanner、browser、notes、finish、knowledge_search 子目录
- `mcp_examples/`

### 6.4 `reports/` 当前分层结构

当前 `reports/` 已完成第一轮实际分层：

- `reports/benchmarks/`
- `reports/smoke/`
- `reports/validation/`
- `reports/writeups/`
- `reports/exports/`

---

## 7. 临时 / 可清理项分类

这类内容不一定要立刻删，但应该被视为“暂存”而不是“长期事实”。

### 7.1 明显临时输出

- `.tmp-web-console.err.log`
- `.tmp-web-console.out.log`
- `tmp_web_console_stdout.log`
- `tmp_web_console_stderr.log`
- `tmp/`
- `tmp_pwn/`

### 7.2 浏览器 / 截图 / 运行残留

- `tmp_tasks_1280.png`
- `tmp_tasks_1366.png`
- `tmp_tasks_1440.png`
- `logs/`
- `.coverage`
- `.pytest_cache/`
- `__pycache__/`

### 7.3 环境目录

- `.venv/`
- `PowerShell 7.6.2/`
- `.claude/`
- `.vscode/`
- `.git/`

### 7.4 需要特别确认是否该长期保留的目录

- `null/`

这类目录如果不是明确用途，建议后续单独确认是否为：

- 临时占位
- 误创建目录
- 某个工具运行副产物

---

## 8. 建议的文件分类使用方式

### 8.1 新文件进仓前先问三件事

1. 它是代码、文档、测试、样本还是产物？
2. 它是长期事实，还是临时残留？
3. 它会不会影响接手者判断当前状态？

### 8.2 文档同步规则

如果新增或改动下面任意一类文件，应该同步更新这份分类索引：

- 新入口文档
- 新状态卡
- 新交接文档
- 新样本矩阵
- 新测试类别
- 新产物目录
- 根目录剩余目录状态判断

---

## 8.1 当前根目录剩余目录状态文档

如需继续判断根目录中的剩余目录该保留、降级还是继续确认，请优先阅读：

- `D:\webstudy\FlagHunter\docs\dev\FlagHunter_仓库根目录剩余目录状态整理_2026-06-01_V1.md`

如需继续判断 `reports/` 目录内的内容如何分层，请优先阅读：

- `D:\webstudy\FlagHunter\docs\dev\FlagHunter_reports目录状态与分层建议_2026-06-01_V1.md`

---

## 9. 当前建议的仓库整理顺序

如果后续要做仓库整理，我建议按这个顺序：

1. 先保留核心代码与入口文档
2. 再稳定当前事实层文档
3. 再整理测试与样本目录
4. 再区分临时输出和长期产物
5. 最后再考虑清理无用残留

---

## 10. 一句话总结

> **FlagHunter 当前最重要的不是“文件多不多”，而是要把文件分成：核心事实、验证样本、临时残留、以及能随时交接的说明层。**
