# FlagHunter 项目文件清理优先级清单（2026-06-01）V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 文档目的：把当前仓库里哪些东西应该优先清理、哪些应该保留、哪些要先确认用途，分成一份可执行清单，避免把样本、交接资料和临时残留混在一起。

---

## 1. 清理判断原则

清理不是按“文件大不大”来决定，而是按下面四个问题来决定：

1. 它是不是项目长期事实的一部分
2. 它是不是当前阶段会反复引用的样本或产物
3. 它是不是仅用于临时验证 / 调试 / 运行残留
4. 它会不会影响新接手的人判断当前状态

---

## 2. 清理优先级分层

### P0：可立即清理或移出事实层的临时残留

这类东西不应长期混在仓库顶层事实视图里。

#### 典型项

- `.tmp-web-console.err.log`
- `.tmp-web-console.out.log`
- `tmp_web_console_stderr.log`
- `tmp_web_console_stdout.log`
- `.pytest_cache/`
- `__pycache__/`
- `.coverage`
- `tmp/`
- `tmp_pwn/`

#### 处理建议

- 如果不再需要调试内容，可直接移除或继续忽略
- 如果近期还会用，至少移出“事实层”视角

当前已处理的一批典型项包括：

- `.tmp-web-console.err.log`
- `.tmp-web-console.out.log`
- `tmp_web_console_stderr.log`
- `tmp_web_console_stdout.log`
- `web_console_8081 ~ 8086` 的过期端口日志

---

### P1：明显是运行时产物，但需要确认是否仍有分析价值

这类文件往往很大，或者是一次性跑出来的中间结果。

#### `loot/` 下重点项

- `loot/edge_history.db`
- `loot/edge13432.dmp`
- `loot/benchmark_*.json`
- `loot/fetch_competition_info.out`
- `loot/edge_wide_search.txt`
- `loot/*_truthy_artifacts.json`
- `loot/*_producers.json`
- `loot/notes_real_*.json`
- `loot/strategy_memory.json`
- `loot/tasks.json`
- `loot/web_tasks.json`

#### 判断方式

先问这几个问题：

- 这份数据是不是还会被当前样本或当前主线继续引用？
- 它是不是已经被更高层的文档 / 状态卡吸收了？
- 它是不是只是一轮调试残留？

#### 处理建议

- 真正有复用价值的：保留，但归类到“样本 / 产物”或“运行时输出”
- 仅用于一次性验证的：考虑移出主视图或清理

---

### P2：可保留但不应该当作长期事实的样本材料

这些通常是本地 challenge、脚本、二进制、截图、验证产物。

#### 典型项

- `tests/fixtures/samples/reverse/my.bin`
- `tests/fixtures/samples/reverse/myde.bin`
- `libcrackme2.so`
- `pow.py`
- `vpow.py`
- `tests/fixtures/samples/web/tax_cookie.txt`
- `tmp_tasks_1280.png`
- `tmp_tasks_1366.png`
- `tmp_tasks_1440.png`

#### 处理建议

- 不建议直接删除
- 但要明确它们是样本、不是主干代码
- 当前已将其中一部分归位到 `tests/fixtures/samples/`

---

### P3：需要先确认用途再决定保留与否

这类目录/文件名比较容易误判，必须先确认其用途。

#### 典型项

- `null/`
- `PowerShell 7.6.2/`
- `.claude/`
- `conversations/`
- `embeddings/`
- `logs/`
- `reports/`（当前已完成实际分层，后续主要是维持结构）
- `workspaces/`
- `mcp_examples/`
- `assets/`

#### 处理建议

- 先确认是不是工具、插件、缓存、对话、知识库或工作区的一部分
- 确认后再决定：保留、迁移、还是清理

---

## 3. 当前最值得优先处理的具体对象

### 3.1 `null/`

当前已经看到：

- `D:\webstudy\FlagHunter\null\skylot`

当前已确认：

- 它是 **JADX 的磁盘缓存目录**
- 缓存中保存了 `my`、`myde`、`CrackMe_2_2` 等反编译项目缓存

建议：

- 不当作项目事实层保留
- 当前已处理：**已从仓库根目录移除**

### 3.2 `PowerShell 7.6.2/`

当前已确认：

- 它是 **JADX 的本地配置目录**
- 包含 `gui.json` 与 `caches.json`
- 其中 `caches.json` 明确引用了 `null/skylot/jadx/cache/...`

建议：

- 不当作项目主干事实保留
- 当前已处理：**已从仓库根目录移除**

### 3.3 `loot/edge13432.dmp`

这个文件体积非常大，属于明显高成本产物。

建议先确认：

- 是否仍是当前分析链路必需
- 是否已被更小、更抽象的结果替代

当前状态：

- 已处理：**原位于 `tmp/edge13432.dmp` 的大 dump 已删除**

结论：

- 不再作为当前仓库根目录残留项存在

### 3.4 `loot/edge_history.db`

这是浏览器历史或类似运行记录，通常不应该默认当作长期事实。

建议确认：

- 是否用于当前样本验证
- 是否只是一次性抓取残留

### 3.5 `loot/strategy_memory.json`

这个文件是有语义价值的，不应随便删。

建议：

- 保留
- 但纳入“项目记忆 / 样本复盘”视角

### 3.6 `loot/benchmark_*.json`

这些一般是阶段性验证结果。

建议：

- 若对应当前主线回归，保留
- 若只是过期 benchmark，可归档

---

## 4. 当前建议保留的高价值项

这些文件/目录虽然不一定是“代码”，但对当前项目很重要：

- `README.md`
- `docs/README.md`
- `docs/dev/FlagHunter_交接文档_当前主线与第一批任务_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目级source-of-truth状态卡_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目文件分类索引_2026-06-01_V1.md`
- `docs/dev/FlagHunter_项目状态核对与下一步讨论底稿_2026-06-01.md`
- `docs/dev/FlagHunter_下一阶段主线_主控_BlackboardLite_调度收紧_V1.md`
- `docs/dev/local_challenge_sample_matrix.md`
- `pentestagent/`
- `tests/`
- `loot/session_ledgers/`
- `loot/artifact_registry/`
- `loot/checkpoints/`
- `loot/strategy_memory.json`

---

## 5. 当前建议的清理顺序

如果你后面真要动手清理，我建议顺序是：

1. 先清理明显的临时日志和缓存
2. 再确认 `null/`、`PowerShell 7.6.2/` 这种歧义目录
3. 再盘点 `loot/` 下的大文件和过期 benchmark
4. 最后再考虑样本材料是否要迁移到专门目录

---

## 6. 不建议现在清理的对象

这些东西当前不建议直接删：

- `pentestagent/`
- `cpa_modules/`
- `tests/`
- `docs/`
- `loot/strategy_memory.json`
- `loot/session_ledgers/`
- `loot/checkpoints/`
- 当前在用的 Web Console / Harness 文档

原因很简单：

- 它们是当前主线事实的一部分
- 删了会影响回放、验证或交接

---

## 7. 建议的落地方式

如果你要真正执行清理，我建议先按这三步走：

1. 先标记，不先删
2. 先备份，不直接动主线样本
3. 先确认，不让清理影响交接

---

## 8. 一句话总结

> **当前仓库的清理优先级不是“先删大文件”，而是先把临时残留、样本材料、项目事实和运行时产物分开，再决定哪些值得保留。**
