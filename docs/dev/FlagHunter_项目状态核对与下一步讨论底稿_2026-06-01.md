# FlagHunter 项目状态核对与下一步讨论底稿（2026-06-01）

> 适用仓库：`D:\webstudy\FlagHunter`
> 
> 文档目的：在暂停继续开发的前提下，先把“当前文档是否可信、代码实际到了哪一步、下一步最值得讨论什么”收敛成一份可复用底稿。

---

## 1. 本轮核对范围

本轮只做三件事：

1. 核对当前项目主文档与开发文档入口
2. 抽样检查关键代码主干与最近改造主线是否一致
3. 记录当前最重要的文档缺口、代码事实和下一步讨论建议

本轮**不继续推进新功能开发**。

---

## 2. 已核对的主要文档

### 2.1 仓库主文档

已核对：

- `D:\webstudy\FlagHunter\README.md`
- `D:\webstudy\FlagHunter\AGENTS.md`

结论：

- `README.md` 作为对外/协作入口，整体方向是对的：
  - 明确了 `FlagHunter` 是外部品牌
  - 明确了内部兼容骨架仍是 `pentestagent/`
  - 明确了 CTF / Pentest / MCP / runtime 的总体定位
- 但它当前更像“项目首页”，**不是当前开发主线的唯一 source of truth**。
- `AGENTS.md` 对仓库结构、运行方式、核心模块的描述仍有较高参考价值，尤其适合恢复代码语义。

### 2.2 Web Console 文档主线

已核对：

- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_文档索引与状态矩阵_V1.md`

结论：

- 这组文档仍然是 **Web Console 局部真相** 的主要入口。
- 文档内容和当前 `web_server.py` / Web 前端合同的主方向**基本一致**：
  - dashboard live filters
  - settings truthful contract
  - knowledge reindex / add doc / open file
  - traces filters
  - task detail attachments
- 但其“最近同步日期”仍停在 `2026-05-29`，**没有显式吸收 05-30 / 05-31 / 06-01 这轮与 harness、mode、local challenge、artifact truth 相关的新增事实**。

### 2.3 当前方向文档

已核对：

- `D:\webstudy\FlagHunter\docs\dev\FlagHunter_Harness优化方案_借鉴Cairn_V1.md`
- `D:\webstudy\FlagHunter\docs\dev\Cairn_源码深度分析_围绕Blackboard与Dispatcher_V1.md`
- `D:\webstudy\FlagHunter\docs\dev\FlagHunter_下一阶段路线_目标驱动_BlackboardLite_V1.md`
- `D:\webstudy\FlagHunter\docs\dev\local_challenge_sample_matrix.md`
- `D:\webstudy\FlagHunter\docs\superpowers\plans\2026-05-29-harness-optimization-plan.md`

结论：

- 这些文档已经较清楚地表达了“项目下一阶段真正想往哪里走”。
- 当前共识方向不是继续扩 GUI / MCP 接入，而是：
  - **目标驱动**
  - **事实优先**
  - **本地 CLI / 脚本 / Kali 优先**
  - **轻量 Blackboard-lite / Harness 收紧**
  - **一边实战，一边优化**

---

## 3. 本轮代码核对结论

### 3.1 已经落地的事实

#### A. Mode Router 已经真正接入入口层

已核对：

- `D:\webstudy\FlagHunter\pentestagent\interface\mode_router.py`
- `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
- `D:\webstudy\FlagHunter\pentestagent\mcp\server\mcp_tools.py`

当前事实：

- `mode / modeSubtype / goalStyle` 已经不是纯文档概念，**而是实际入口合同的一部分**。
- Web 入口与 MCP 入口都已经接入模式合同解析。
- replay / retry / continue 也已经按源任务继承 mode 相关信息。

#### B. Harness 外壳已经有“骨架”，但还不是完整黑板系统

已核对：

- `D:\webstudy\FlagHunter\pentestagent\harness\session_ledger.py`
- `D:\webstudy\FlagHunter\pentestagent\harness\artifact_registry.py`
- `D:\webstudy\FlagHunter\pentestagent\harness\checkpoint_store.py`
- `D:\webstudy\FlagHunter\pentestagent\harness\audit_events.py`
- `D:\webstudy\FlagHunter\pentestagent\knowledge\session_context.py`

当前事实：

- 项目已经有：
  - append-only ledger
  - artifact registry
  - checkpoint store
  - audit event builders
  - session context view
- 这说明项目已经从“只有方向文档”进展到“已有 Harness 基础模块”。
- 但它**还不能被称为完整 Blackboard 模式**，因为：
  - 事实 / 猜测 / 待验证结论 / 决策记录 尚未形成统一的项目级共享板
  - Pentest 路径还没有像 CTF 路径一样接入同等级别的统一状态主线
  - 主控调度仍未彻底从大 dispatcher / 大入口文件里抽离

#### C. Web Console 已从 mock 驱动转向 truth-driven 主路径

已核对：

- `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
- Web Console 相关单测合同

当前事实：

- 当前 Web Console 已不只是原型壳。
- Tasks / Traces / Knowledge / Settings / Dashboard 的主读路径和一批关键动作，已经接真实数据或真实空态。
- 它已经具备“作为事实观察面”的价值，而不是仅作为演示层。

#### D. Local Challenge / artifactPaths 主线已经成型

已核对：

- `D:\webstudy\FlagHunter\docs\dev\local_challenge_sample_matrix.md`
- `D:\webstudy\FlagHunter\tests\integration\local_challenge_catalog.py`
- `D:\webstudy\FlagHunter\tests\integration\test_local_asset_eval_pack.py`
- `D:\webstudy\FlagHunter\pentestagent\interface\cli.py`
- `D:\webstudy\FlagHunter\pentestagent\mcp\server\mcp_tools.py`
- `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\coordinator.py`

当前事实：

- `challengePath + artifactPaths` 已经是明确的输入合同。
- 这条链路已经不是“以后再做”，而是已经成为当前仓库最有价值的一条实战/评估主线之一。
- 这也与“让 agent 尽量利用本地附件、源码、压缩包、docker-compose、日志做真分析”的方向一致。

---

## 4. 当前仍然存在的关键问题

### 4.1 整个项目缺一个“总文档入口”

当前事实：

- `D:\webstudy\FlagHunter\docs\README.md` **已补齐**。
- 这意味着：
  - Web Console 有自己的文档索引
  - 开发思路散落在 `docs/dev/`
  - 计划散落在 `docs/superpowers/plans/`
  - 现在已经有一份“当前项目应该先读哪几份文档”的总入口

影响：

- 新接手时恢复成本高
- 容易把历史阶段文档误读为当前事实
- 容易把 README、dev 文档、web-console 文档各自当成 source of truth

### 4.2 还没有“整个项目级”的 current source of truth 文档

当前事实：

- Web Console 有局部真相文档
- Harness 方向有分析文档
- Blackboard-lite 有方向文档
- Local challenge 有样本矩阵

但还没有一份真正覆盖下面 5 件事的总状态文档：

1. 当前 Pentest / CTF 两种 mode 的真实边界
2. 当前 Harness 已落地到什么程度
3. 当前 Web Console 是观察面还是控制面，边界在哪
4. 当前本地 eval / challenge 样本到什么程度
5. 当前最值得继续打磨的是哪条主线

### 4.3 `ctf_dispatcher.py` 仍然过大

当前事实：

- `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_dispatcher.py` 仍然是超大文件
- 虽然已经引入了 `coordinator.py`，也已经引入了 harness 相关能力
- 但 dispatcher 仍然承载过多策略、helper、流程粘合与细节逻辑

判断：

- 这依然是当前代码最明显的结构性债务之一
- 但它未必是“下一步最优先立刻下刀”的对象
- 如果没有更强的 eval / 真样本回归作为牵引，单独继续拆 dispatcher 容易进入“结构优化先行、收益后验”的风险

### 4.4 目前还不能说项目已经进入“真正黑板模式”

当前事实：

- 方向文档里已经明确提出 Blackboard-lite
- TUI 文案里甚至有 blackboard 字样
- 但项目真正落地的是：
  - ledger
  - artifact registry
  - checkpoint
  - session context
  - mode routing

判断：

- **现在更准确的表述是：项目进入了“黑板前置阶段 / harness 收紧阶段”，而不是黑板模式已完成。**
- 这点如果不说清楚，后续很容易误判成熟度。

### 4.5 当前验证命令依赖 `.venv`，这件事需要写回文档

本轮测试中观察到：

- 直接运行系统 `python + pytest` 会因缺少 `aiohttp` 导致接口相关测试收集失败
- 使用项目自己的：
  - `D:\webstudy\FlagHunter\.venv\Scripts\python.exe -m pytest ...`
  则通过

这说明：

- 不是代码本身有立即性回归
- 而是当前本机默认 Python 环境与项目依赖环境不一致

这件事应该明确写回开发文档或 docs 入口，否则后续很容易重复踩坑。

---

## 5. 本轮验证证据

### 5.1 已通过的关键测试

使用项目 `.venv` 运行后，以下测试通过：

#### A. 模式入口 / MCP / Web 入口主线

命令：

```powershell
D:\webstudy\FlagHunter\.venv\Scripts\python.exe -m pytest \
  tests/unit/interface/test_mode_router.py \
  tests/unit/mcp/test_mcp_ingress_mode_contract.py \
  tests/unit/interface/test_web_server.py -q
```

结果：

- `78 passed`

#### B. Harness / Session / Artifact / Checkpoint 主线

命令：

```powershell
pytest tests/unit/knowledge/test_session_context.py \
  tests/unit/harness/test_audit_events.py \
  tests/unit/agents/test_ctf_dispatcher_checkpoint_store.py \
  tests/unit/agents/test_ctf_dispatcher_artifact_registry.py -q
```

结果：

- `26 passed`

#### C. Web Console 合同主线

命令：

```powershell
pytest tests/unit/web_console/test_task_local_asset_contract.py \
  tests/unit/web_console/test_traces_page_contract.py \
  tests/unit/web_console/test_dashboard_filters_contract.py \
  tests/unit/web_console/test_traces_filters_contract.py -q
```

结果：

- `21 passed`

### 5.2 本轮发现的环境性问题

直接使用系统 Python：

```powershell
python -m pytest ...
```

会因为当前系统解释器缺失 `aiohttp` 而报错。

因此当前更可信的项目测试口径应写成：

```powershell
D:\webstudy\FlagHunter\.venv\Scripts\python.exe -m pytest ...
```

---

## 6. 我对当前项目阶段的判断

如果用一句话概括当前状态，我的判断是：

> **FlagHunter 已经从“Web Console 真值化收口”阶段，推进到“Mode Router + Harness 壳层初步成立 + Local Challenge 实战样本开始接管方向”的阶段。**

更细一点说：

### 已经不是最早阶段

因为现在已经具备：

- 入口 mode contract
- harness 基础模块
- session / artifact / checkpoint 投影视图
- Web Console 真实观察面
- 本地 challenge / artifact ingress

### 但也还没到“后端智能体主线真正稳定”的阶段

因为现在仍然缺：

- 项目级统一真相文档
- 黑板级共享状态模型
- 更强的主控调度闭环
- Pentest Mode 与 CTF Mode 的进一步分层
- 更系统的 eval / regression harness

---

## 7. 我建议接下来不要立刻继续堆功能，而是先讨论的 4 个问题

### 问题 1：当前下一阶段的唯一主线到底选哪条

我建议候选只保留 3 条，不要再发散：

1. **主控 / Blackboard-lite / 调度收紧**
2. **Local Challenge eval pack / 实战样本驱动优化**
3. **Pentest Mode 主链补齐**

我的倾向顺序是：

1. `Local Challenge eval pack / 实战样本驱动优化`
2. `主控 / Blackboard-lite / 调度收紧`
3. `Pentest Mode 主链补齐`

原因：

- 没有稳定样本和回归任务，继续收拾主控结构很容易脱离真实问题
- 先用样本逼出 agent 主线缺口，再决定黑板与主控要收紧到什么程度，更稳

### 问题 2：我们是先做“会跑”，还是先做“会判断”

我当前判断：

- Web Console 层已经够用，不必再优先扩页面
- 接下来最值得投入的是：
  - agent 如何判断下一步做什么
  - 如何区分事实 / 猜测 / 待验证结论
  - 如何用本地 artifact 和 runtime 结果做高价值推进

也就是：

> **后续优先级应该从“再接更多页面动作”切回“后端 agent 逻辑与调度判断”。**

### 问题 2.1：虚拟环境解释器必须写回文档

本仓库当前测试与验证应优先使用：

```powershell
.\.venv\Scripts\python.exe
```

原因很简单：

- 系统 Python 与项目依赖不一定一致
- 用系统 Python 跑测试可能误判为代码回归
- 用 `.venv` 跑测试更接近项目真实执行环境

因此后续文档和执行记录都应显式标注这一点。

### 问题 3：TUI 是否继续作为重点

当前我的建议是：

- **TUI 不再作为下一阶段重点建设对象**
- 保留兼容即可
- 主要观察与人工控制面以：
  - CLI
  - Web Console
  为主

这和你前面提出的判断是一致的：

- Web 更适合人看
- CLI / 本地脚本更适合 agent 执行
- TUI 的继续重投入优先级不高

### 问题 4：文档现在最该补哪一份

当前最应该继续维护的是两份文档：

1. **`docs/README.md`：整个项目文档入口**
2. **项目级 current status / source-of-truth 总状态卡**

如果只保留一份优先维护对象，我建议优先维护：

- `D:\webstudy\FlagHunter\docs\README.md`

因为它能直接降低接手、恢复、判断当前事实的成本。

---

## 8. 建议的下一步讨论顺序

建议我们接下来按这个顺序讨论，而不是同时开很多线：

1. 先确认：
   - 下一阶段主线到底选 `样本驱动优化`、`主控调度收紧` 还是 `Pentest Mode`。
2. 再确认：
   - 是否先补 `docs/README.md + 项目级状态卡`。
3. 最后再进入：
   - 具体实现路线和最小任务拆解。

---

## 9. 本轮一句话收口

> **现在最值得做的不是继续堆新页面或新按钮，而是先把“项目总入口文档 + 当前真实阶段判断 + 样本驱动的后端主控优化方向”这三件事钉死。**

