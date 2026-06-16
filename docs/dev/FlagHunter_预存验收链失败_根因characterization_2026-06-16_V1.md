# 预存验收链失败：根因 characterization（V1）

> 日期：2026-06-16
> 范围：`tests/integration/` 中长期 RED 的 4 条 CTF 验收链 + 说明它们**不是** Workstream A/B 重构引入的回归。
> 目的：把"agent 真正会判断仅 50–60%"这句自评落到**具体哪条链、卡在哪一步、是测试问题还是能力问题**，避免每次从零调查。

---

## 0. 前提：这 4 条是预存失败，非本轮重构回归

本轮 façade（slice 0/1）+ 黑板（B1/B2）每步都用全量 `tests/unit + tests/integration` 对齐过 **clean-HEAD 16 失败基线**，逐步零新增。其中：

- **真实失败（隔离也挂）**：`llm7_blocks_external_domain_request`（allowlist）+ 下述 4 条验收链。
- **跨套件污染（仅合并跑挂、隔离全过）**：adversarial_grounding ×3、easy_login ×4、full_chain ×2、http_request_smoke ×2 —— 是某个 unit 测试向后续 integration 泄漏全局状态，**与被测能力无关**。

  > **已修复（commit `7b2b52d`）**：根因是**工具注册是 import 副作用、被 `sys.modules` 缓存**（`loader.load_tool_module` 见到模块已导入就提前 return）。一旦某测试调 `clear_tools()` 清空全局注册表，`load_all_tools()` 无法重填（模块已导入、不会重新注册）。`test_http_request`/`test_dirscan`/`test_nuclei` 等在 **teardown** 调 `clear_tools()`，把空注册表留给后续所有测试 → 那 11 条断言 `get_tool("nmap") is not None` 的集成测试就挂。修复：`tests/conftest.py` 加 session 级 baseline 快照 + autouse teardown fixture，用 `setdefault` 把被清掉的 baseline 工具补回（不 clobber、不影响测内断言）。全量套件从 **16 失败 → 5 失败**（只剩本文 4 条 + llm7），套件终于可信。

本文只 characterize 那 4 条真实验收链。

---

## 1. 逐条根因

### 1.1 `easy_tornado :: solves_easy_tornado_chain` —— 测试过度指定
- **期望**：`observed_kinds` 含 `render_ssti_response`。
- **实际**：flag **已解出**（`flag{easy_tornado_acceptance_ok}`），但路径是 `cookie_secret_leaked → hash_reconstruction_response → file_read_response`，未记录 `render_ssti_response` 观测。SSTI 请求 (`/error?msg={{handler.settings["cookie_secret"]}}`) 确实发了（requests 断言能过），只是对应观测被记成 `cookie_secret_leaked`。
- **性质**：观测命名/路径分叉。dispatcher 行为可能是对的（换了等价有效路径），测试把中间观测名写死了。
- **修复**：放宽对 `render_ssti_response` 的断言 **或** 让 SSTI 渲染时补记该观测。前者需确认不是真的漏记。

### 1.2 `easy_tornado :: skips_identify_when_ssti_probe_has_no_hit` —— 测试前提失效
- **期望**：`success is False`（SSTI 探针没命中 → 不应解出）。
- **实际**：`success=True`，经 `hash_reconstruction(md5) flag: /fllllllllllllag` 解出。
- **性质**：测试假设"无 SSTI 命中即无解"，但 dispatcher 有 hash 重建路径能绕过 SSTI 直接拿 cookie_secret/flag。**可能是真 solve（测试前提过时），也可能是该场景下的误报**——取决于 `easy_tornado_realistic_server` 是否本就该在该路径泄漏 flag。
- **风险**：直接放宽测试会**掩盖潜在误报**，必须先核 fixture 意图。

### 1.3 `php_object_injection :: escalates_past_source_flag_to_runtime_flag` —— 真能力缺口（candidate→verified 升级）
- **期望**：source 里发现诱饵 `Syc{dog_dog_dog_dog}` 后，经 **PHP unserialize 运行时利用**升级到 `RUNTIME_FLAG`，`success=True`，reason 含 "php unserialize runtime exploit"。
- **实际**：`success=False`，reason=`检测到 source-only candidate flag: Syc{dog_dog_dog_dog}；未获得运行时验证，已停止误报`。
- **关键判断**：`recovery.py:finalize()` 的 `stop_candidate_only`（candidate 有、runtime 无 → 停）是**正确的防御行为**（拒绝把 source-only 当成功，避免误报）。**真缺口在上游**：`web` 链从 `/www.zip` 源码识别到 unserialize sink 后，**没有执行 PHP 对象注入运行时利用**把诱饵升级成 runtime flag。
- **性质**：深度 exploit 链能力缺失，不是停机逻辑 bug。修复=实现/修通 PHP unserialize 运行时利用路径，对 1551 个通过用例有连带风险。
- **与 Workstream B 的关联**：黑板已能把 candidate/refuted 暴露给模型（B2），但"识别 sink → 构造 gadget → 运行时验证"这一段是 exploit 实现，黑板协议只负责让它可见，不负责替它实现。

### 1.4 `profile_poisoning :: solves_profile_photo_poisoning_chain` —— 真能力缺口（未解出）
- **期望**：`success=True`。
- **实际**：`success=False`，`chain_used=['sqli','sqli','web']`，穷尽停止、未找到 flag。
- **性质**：完整攻击链（profile photo 污染）未跑通。深度 exploit 能力缺口。

---

## 2. 结论与建议

| 链 | 性质 | 状态 |
|---|---|---|
| llm7 allowlist | 真 bug（ToolGuard 块被 replan 吞掉，reason 没冒出来） | ✅ 已修 `95b652f`（allowlist 块改为 terminal） |
| easy_tornado solves/skips | 行为哲学分歧（激进直接利用 vs 保守先确认）——非 bug 非纯过时 | ✅ 已修 `0957d94`：引入 `exploitation_mode` 两模式（aggressive=CTF 默认走最短链 / conservative=pentest 先确认再打），两条测试跑 conservative |
| php escalation | **其实不是能力缺口，是一行正则 bug**：备份源码分析用 `re.sub(r"<[^>]+>"," ")` 剥 HTML，把整段 `<?php ?>`（含 unserialize/__destruct 标记）也吃掉了 → 探测器永远检测不到 → 停在 source-only。payload 构造器（`O:4:"Name":3:` __wakeup 绕过）和利用链一直是对的，只是没触发。 | ✅ 已修 `04f3800` |
| profile poisoning | **同一根因**：profile_photo_poisoning 探测也走 `normalized_joined`，同样被 `<?php ?>` 吃源码问题挡住。 | ✅ 已修 `04f3800`（同一行修复） |

> **进展（commit 时间线）**：5 真失败 → **0**。`llm7`（allowlist terminal）+ easy_tornado 两条（两模式）+ php/profile（`<?php ?>` 正则修复，一行修双 bug）全部清掉。全量套件 **1575 passed / 0 failed**，本会话首次全绿。
>
> **教训**：php/profile 一开始被我判为"深度 exploit 能力缺口"，实际是**探测层一行正则顺序 bug**静默禁用了两条已实现的利用链——`scan_text` 在剥 HTML 前的原文上跑（所以诱饵 flag 找得到），但 exploit 探测在剥过 HTML 的 `normalized_joined` 上跑（`<?php ?>` 被当成 HTML 标签删掉）。能力其实都在，被一行正则埋了。
>
> **`exploitation_mode` 设计**：呼应蚁群"发散探索→走最短链"——CTF 默认激进（最短链直达 flag），渗透模式保守（不断收集信息、确认漏洞类型再打）。两条 easy_tornado 测试因此各自归位到对应模式，而非被强行放宽。

**总判断**：这 4 条没有低风险的"快修"。两条 easy_tornado 是测试与行为分叉（改测试有掩盖误报风险），两条是真 exploit 能力缺口（深度实现 + 对现有 1551 通过用例的连带风险）。

**建议优先级**：
1. 若要做能力提升，**php escalation 最值得**——目标清晰（source 诱饵 → PHP unserialize → runtime flag），是文档点名的 candidate→verified 指标，且 `finalize()` 防御逻辑已就位、只缺上游利用实现。应作为独立专项（带自己的 fixture 复现 + 不碰共享停机逻辑）。
2. easy_tornado 两条建议**先核 fixture 意图**再决定是放宽断言还是补观测，不要为了变绿而盲目放宽。
3. ~~跨套件污染那 11 条是**测试隔离问题**，与能力无关，值得单独排查~~ **已完成（`7b2b52d`）**：工具注册表污染已修，全量套件 16→5 失败、可信。
