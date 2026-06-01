# FlagHunter 仓库根目录剩余目录状态整理（2026-06-01）V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 文档目的：在完成一轮 P0 清理后，对仓库根目录当前剩余目录做一次状态整理，区分哪些是核心保留、哪些是运行时目录、哪些是样本/产物、哪些仍待确认。

---

## 1. 当前根目录剩余目录概览

当前根目录仍保留的主要目录有：

- `.claude/`
- `.git/`
- `.github/`
- `.venv/`
- `.vscode/`
- `assets/`
- `conversations/`
- `cpa_modules/`
- `docs/`
- `embeddings/`
- `knowledge/`
- `logs/`
- `loot/`
- `mcp_examples/`
- `pentestagent/`
- `reports/`
- `scripts/`
- `tests/`
- `tools/`
- `web/`
- `workspaces/`

---

## 2. A 类：核心保留目录

这些目录应该默认视为当前仓库主干的一部分，不建议清理。

### 2.1 核心代码

- `pentestagent/`
- `cpa_modules/`
- `scripts/`
- `tools/`
- `web/`

### 2.2 文档与协作

- `docs/`
- `.github/`

### 2.3 测试

- `tests/`

### 2.4 必要环境目录

- `.git/`
- `.venv/`

---

## 3. B 类：保留，但应视为运行时 / 状态目录

这些目录不是核心代码，但对当前运行、验证、记忆或恢复有价值。

### 3.1 `loot/`

当前是项目最重要的运行状态目录之一。

里面已经包含：

- `artifact_registry/`
- `checkpoints/`
- `session_ledgers/`
- `metrics/`
- `sessions/`
- `strategy_memory.json`
- `tasks.json`
- `web_tasks.json`

判断：

- **保留**
- 但应明确这是运行时与状态层，不是“源码层”

### 3.2 `knowledge/`

当前属于知识层主目录，保留。

### 3.3 `embeddings/`

属于知识检索 / 向量索引运行产物，保留，但归类为运行时产物更合适。

### 3.4 `workspaces/`

当前包含多组按目标拆分的工作区目录，例如：

- `127.0.0.1_3000`
- `127.0.0.1_8080`
- `test.example.com`
- `tool-smoke-site`

判断：

- 保留
- 但后续应明确哪些是长期保留的工作区，哪些是过期实验目录

### 3.5 `conversations/`

当前包含：

- `index.json`
- `session.json`
- 单独 conversation JSON

判断：

- 保留
- 归类为对话与会话状态目录

---

## 4. C 类：保留，但属于样本 / 报告 / 产物目录

### 4.1 `reports/`

当前已完成实际分层，包含：

- `reports/benchmarks/`
- `reports/smoke/`
- `reports/validation/`
- `reports/writeups/`
- `reports/exports/`

判断：

- 保留
- 当前不再是混放根层，而是已经完成第一轮结构收口

### 4.2 `logs/`

当前包含：

- `app/`
- `audit/`
- `blackboard.db`
- 多份 `web_console_808*.log`

判断：

- 当前仍有运行时与审计价值
- 但也混入了过期端口日志

建议：

- 保留
- 当前已处理：**过期 `web_console_8081 ~ 8086` 端口日志已清理**
- 继续保留 `app/`、`audit/` 与 `blackboard.db`

### 4.3 `assets/`

默认保留，但应视为静态资源或 UI/项目附属资源目录，而不是核心逻辑目录。

### 4.4 `mcp_examples/`

保留，属于示例配置 / 示例接入资料目录。

---

## 5. D 类：待处理 / 已处理目录

这类目录是本轮清理里单独处理的对象。

### 5.1 `null/`

当前只看到：

- `null/skylot/`

判断：

- 当前已确认它不是项目主干目录
- 实际内容是 **JADX 的磁盘缓存目录**
- 其中可见：
  - `null/skylot/jadx/cache/projects/...`
  - 对应 `my` / `myde` / `CrackMe_2_2` 等反编译项目缓存

补充证据：

- `PowerShell 7.6.2/skylot/jadx/config/caches.json` 明确把缓存路径写到了：
  - `D:\webstudy\FlagHunter\null\skylot\jadx\cache\projects\...`

建议：

- 已处理：**已从仓库根目录移除**
- 结论保留在本文档中，便于后续交接时解释其历史用途

### 5.2 `PowerShell 7.6.2/`

当前只看到：

- `PowerShell 7.6.2/skylot/`

判断：

- 当前已确认它不是项目主干目录
- 实际内容是 **JADX 的本地配置目录**
- 其中可见：
  - `PowerShell 7.6.2/skylot/jadx/config/gui.json`
  - `PowerShell 7.6.2/skylot/jadx/config/caches.json`

补充判断：

- `gui.json` 显示的是本地 GUI 设置
- `caches.json` 记录的是缓存路径，且缓存路径指向 `null/skylot/jadx/cache/...`
- 因此这两个目录是同一组工具残留：
  - `PowerShell 7.6.2/` = JADX 配置
  - `null/` = JADX 缓存

建议：

- 已处理：**已从仓库根目录移除**
- 结论保留在本文档中，便于后续交接时解释其历史用途

### 5.3 `tmp/`

虽然 P0 清理后这里一度残留：

- `tmp/edge13432.dmp`

判断：

- 这是高体积、高疑似临时残留项
- 当时删不掉，原因是当前用户仅有 `Read, Synchronize` 权限
- 后续已补充当前用户文件权限并完成删除

建议：

- 已处理：**`tmp/edge13432.dmp` 已删除，`tmp/` 目录已从仓库根目录移除**

---

## 6. E 类：本地工具 / 编辑器 / 协作环境目录

这类目录默认不应影响项目真相判断，但会影响本地开发体验。

### 6.1 `.claude/`

本地协作或工具环境目录，保留。

### 6.2 `.vscode/`

编辑器目录，保留。

### 6.3 `.venv/`

当前虚拟环境目录，保留，且是当前项目默认 Python 解释器来源。

---

## 7. 当前建议的根目录整理判断

### 7.1 现在就应保持在根目录视野中的目录

- `pentestagent/`
- `cpa_modules/`
- `docs/`
- `tests/`
- `scripts/`
- `tools/`
- `knowledge/`
- `loot/`
- `workspaces/`

### 7.2 可以保留，但应在认知上降级为“运行时 / 产物”

- `logs/`
- `reports/`
- `embeddings/`
- `conversations/`
- `assets/`
- `mcp_examples/`

### 7.3 需要继续确认或后续迁移

- `null/`
- `PowerShell 7.6.2/`
- `tmp/`

---

## 8. 建议的下一步

如果继续做仓库收口，建议按这个顺序：

1. 先单独处理 `tmp/edge13432.dmp`
2. `tmp/edge13432.dmp` 已处理完成，无需再单独处理
3. `null/` 与 `PowerShell 7.6.2/` 已确认并已处理，无需再单独确认
4. `logs/` 里的过期 `web_console_8081 ~ 8086` 端口日志已清理
5. `reports/` 的 benchmark / smoke / validation / writeups / exports 分层已完成，后续只需保持新产物继续按层写入

---

## 9. 一句话总结

> **当前根目录已经基本从“散乱状态”收回到“核心代码 + 文档事实 + 运行时目录 + 已分层产物目录”的状态，接下来重点不是盲删，而是保持新增产物继续写入正确层级。**
