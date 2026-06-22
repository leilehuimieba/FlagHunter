# 并行任务卡 Backlog(可丢进新对话独立跑)

本文件维护一批**自包含、文件不重叠、可并行**的任务卡。每张卡可直接复制粘贴进一个新
对话独立执行。设计目标:让多个对话同时推进而**不互相踩文件**。

> 配套主线文档:`docs/dev/FlagHunter_架构决策记录_自顶向下骨架与两关节契约_2026-06-17_V1.md`(ADR)。
> 任务卡只是 ADR 路线图的"可外包切片",完成后回写 ADR §8 变更记录。

---

## 并行安全铁律(每张卡都默认继承,勿违反)

1. **文件不重叠**:同时在跑的卡,触及文件集合必须互斥。本文件每张卡都显式列出
   「碰哪些文件 / 不碰哪些」。开新卡前先扫一眼在跑的卡,确认无交集。
2. **环境里有自动提交进程**:本仓存在一个以 `FlagHunter` git 身份**自动 commit** 的
   进程(会把未提交改动抢先提交)。后果:你的 `git add && commit` 可能只剩残余几行。
   应对——**改完尽快自己提交**,提交后用 `git show --stat HEAD~N..HEAD` 核对你的改动
   确实落在某条提交里、内容完整即可,**不要试图改写历史**去合并。
3. **不碰 `challenges/`**:它是 gitignored 的题目目录,**永远不要 `git add`**。
4. **venv 解释器**:`.venv/Scripts/python.exe`(Windows)。
5. **门禁命令**:`.venv/Scripts/python.exe -m pytest tests/unit/agents/ -q -p no:cacheprovider`
   (全 agents 套件,约 6 分钟)。改动越界到别的子系统时,跑对应目录的测试。
6. **双提交节奏**:`refactor(...)`/`feat(...)` 一个 + `docs(...)` 一个;直接提交 `main`,
   **不要 push**(本地有意领先 origin/main)。
7. **commit message 用文件方式**:`git commit -F <tempfile>`(临时文件放 `D:/tmp`)。
   **不要**在 Bash 工具里用 PowerShell here-string `@'...'@`(Bash 工具是 Git Bash/POSIX sh,
   会把 `@` 混进提交标题)。消息结尾固定:
   `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。
8. **抽取/改名后、跑套件前先做 monkeypatch 路径预扫**:`grep "<旧模块>.<被移符号>"`,
   把 setattr-rebind 的 patch 路径改到新使用点(消除失败往返)。

---

## 任务卡模板

```
标题:<一句话>
文档锚点:<ADR 章节 / 相关文件>
风险级别:低 / 中 / 高(高=真改调用路径,需 live eval 回放兜底)
详细目标:
  - <可验证的具体改动>
边界:
  - 只碰:<文件白名单>
  - 不碰:<显式排除>
完成判据(DoD):
  - <客观、可 grep / 可跑出来的判据>
验证:
  - <命令>
收尾:
  - 双提交(refactor/feat + docs);回写 ADR §8。
```

---

## 卡 A — P3b 第④刀(收尾刀:删死字段 + 摘 dispatcher) ✅(0308774)

```
继续 FlagHunter 的 P3b 重构第④刀(收尾)。这是纯机械、可推理证零行为变更的低风险刀。

文档锚点:docs/dev/...自顶向下骨架与两关节契约_2026-06-17_V1.md 的「P3b 主体刀完成」条目
(主体刀已把 strategy_registry.py 全部 22 处 ctx.dispatcher 透传迁到 ctx.services,
services 过渡期 = self)。本刀做两件事:

详细目标:
  1. 删 ChainContext 的 4 个零引用死字段:runtime / capability_registry /
     strategy_memory / exploitation_mode。先全仓 grep 确认这 4 个字段的读取点为 0
     (已知 strategy_registry.py + chains/ 内为 0,需再扫 tests/ 与全仓),
     再从 ChainContext 定义和 _strategy_context 工厂里删掉这 4 个字段及其赋值。
  2. 摘掉 dispatcher 字段:先全仓 grep `ctx.dispatcher` / `context.dispatcher` 的"读取"
     点必须为 0(strategy_registry.py 内只剩注释字面,需确认 chains/ 与其它处也为 0);
     确认后从 ChainContext 删 dispatcher 字段,从 _strategy_context 删 dispatcher=self,
     并把所有测试里 StrategyContext(dispatcher=...) 的构造改为去掉 dispatcher= 或换成
     services=（约 11 处直接构造,见 tests/unit/agents/test_ctf_strategy_registry.py）。
     若某处确实仍读 ctx.dispatcher,先把它迁到 ctx.services 再摘字段。
  3. 保持 services = self(本刀不收窄成 Protocol —— 收窄是另一张高风险卡,需 live 回放)。

边界:
  - 只碰:flaghunter/agents/pa_agent/strategy_registry.py、
          flaghunter/agents/pa_agent/ctf_dispatcher.py(仅 _strategy_context 工厂段)、
          tests/unit/agents/test_ctf_strategy_registry.py、
          docs/dev/...2026-06-17_V1.md(ADR 回写)。
  - 不碰:flaghunter/agents/pa_agent/chains/**、其它 mixin 文件、cpa_modules/**、eval/**。

完成判据(DoD):
  - grep `ctx\.(runtime|capability_registry|strategy_memory|exploitation_mode|dispatcher)`
    在 flaghunter/ 与 tests/ 内仅余注释(理想为 0)。
  - ChainContext 字段集 = {dispatcher 已删} + services/target/page_features/hint/extras/
    state/ingress_handoff/challenge_context。
  - 全 agents 套件零回归。

验证:.venv/Scripts/python.exe -m pytest tests/unit/agents/ -q -p no:cacheprovider
收尾:双提交(refactor(P3b) + docs(P3b));ADR §8 追加「P3b 第④刀完成」;P3b 即收口。
```

---

## 卡 B — roadmap-P5:cpa_modules m1–m6 命名/文档 + capability registry 收尾 ✅(67ba49e)

```
执行 FlagHunter ADR 路线图里的 P5(注意:这是 §5 表格定义的"cpa_modules 命名/文档 +
capability registry 收尾",与 §8 里那条"P5 god-object 23 刀拆分"是不同的东西,后者已收敛)。

文档锚点:ADR §5 路线图表 P5 行;cpa_modules 现状见 flaghunter/cpa_modules/
(m1_api_hub / m2_ctf_kit / m3_reporter / m4_audit_guard / m5_swarm_link / m6_turbo)。

详细目标:
  1. 先派 Explore agent 测绘 m1–m6 各自的真实职责、对外暴露的能力、被谁调用,产出一份
     "模块职责对照表"。
  2. 给每个 m* 模块补/校准模块级 docstring 与命名(若有名实不符),不改行为。
  3. capability registry 收尾:核对 capability 注册表与 m1–m6 暴露能力是否一致、有无
     悬空/重复注册,补齐文档。
  4. 把对照表写进 docs/dev/(新文件,或 ADR 附录)。

边界:
  - 只碰:flaghunter/cpa_modules/**(仅 docstring/命名/注释级,除非发现明确 bug)、
          docs/dev/**、相应 tests/(若加守卫测试)。
  - 不碰:agents/pa_agent/**(strategy_registry/ctf_dispatcher/chains/mixins)、eval/**。
  - 这是低风险文档/命名为主的卡;任何真行为改动须单列并加测试。

完成判据(DoD):
  - 一份 m1–m6 职责对照表落到 docs/dev/。
  - capability registry 与 m* 暴露能力一致性结论(有差异则列出+修正)。
  - 全套件零回归。

验证:.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider(或至少 cpa_modules 相关测试)
收尾:双提交(docs + 可选 refactor);ADR §5/§8 标注 P5 收尾。
```

---

## 卡 C — eval/回放 harness 扩充(题目覆盖) ✅(808482c)

```
扩充 FlagHunter 的 eval/回放 harness 覆盖面。

文档锚点:flaghunter/eval/(record.py / replay.py / fixtures/);
记忆 project_eval_harness_and_parallel(含 recon-diagnose fixture 坑:
fake 必须返回正经的 diagnose 探针,否则回放失真)。

详细目标:
  1. 先读 record.py / replay.py 摸清录制&回放协议与 fixture 格式。
  2. 盘点已有 fixtures 覆盖了哪些题型/链路,找出缺口(例如某条已打通的 chain 没有回放夹具)。
  3. 为 1–2 条缺口链路新增 record fixture + replay 测试,确保可重放、断言稳定。
  4. 注意 fixture 坑:fake/桩必须返回与真实探测同构的结构,不能返回空壳。

边界:
  - 只碰:flaghunter/eval/**、tests/(eval 相关)。
  - 不碰:agents/pa_agent/** 生产代码、cpa_modules/**、strategy_registry/ctf_dispatcher。
    (若发现必须改生产代码才能回放,停下来记录,不在本卡里改。)

完成判据(DoD):
  - 新增 ≥1 条链路的 record fixture + 可重放 replay 测试,跑绿。
  - 回放对真实行为忠实(fixture 非空壳)。

验证:.venv/Scripts/python.exe -m pytest <eval 相关测试路径> -q -p no:cacheprovider
收尾:双提交(feat + docs)。
```

---

## 卡 D — M4 audit_guard:DataProtector mask_ips 语义核查(卡 B 浮出的待复核项) ✅(826bd70)

```
核查 FlagHunter cpa_modules/m4_audit_guard 一处疑似语义反转 bug(卡 B 审计时浮出,
按"不夹带"纪律未在卡 B 内改动,已列入 m1–m6 职责对照表 §4 待复核)。仓库
D:\webstudy\FlagHunter(Windows),Python 用 .venv\Scripts\python.exe。

文档锚点:
  - docs/dev/cpa_modules_m1-m6_职责对照表_2026-06-20_V1.md §4(M4 待复核条目)。
  - 代码:flaghunter/cpa_modules/m4_audit_guard/__init__.py 的 init_m4——
    `DataProtector(mask_ips=not mask_sensitive, ...)`,mask_ips 与 mask_sensitive
    取反,读起来与开关语义相悖。

详细目标:
  1. 先只读测绘:DataProtector 定义处 mask_ips / mask_sensitive 各自的真实语义、
     默认值;init_m4 的调用方/配置如何传 mask_sensitive;有无下游依赖这个取反行为。
  2. 判定:
     - 若确为 bug(取反导致 mask 行为与配置相悖)→ 修正为正确语义 + 加回归测试
       锁定(断言 mask_sensitive=True 时 IP 被遮蔽)。
     - 若为有意设计("报告保留 IP"等)→ 不改行为,改写 docstring/注释澄清语义,
       消除误导。
  3. 更新对照表 §4:把"待复核"结论改为"已复核(bug 已修 / 确认有意 + 已澄清)"。

边界:
  - 只碰:flaghunter/cpa_modules/m4_audit_guard/**、相应 tests/、上述对照表 .md。
  - 不碰:其它 m* 模块、flaghunter/agents/pa_agent/**、flaghunter/eval/**、
          flaghunter/session/initializer.py 行为、challenges/。
  - 与卡 B 文件锁无活动交集(卡 B 已收口);若改对照表,确认无人正写该文件。

完成判据(DoD,客观可 grep/可跑):
  - mask_ips 语义有明确书面结论(bug 已修 + 回归测试 / 或确认有意 + 注释澄清)。
  - 若判 bug:新增回归测试覆盖 mask_sensitive↔mask_ips 一致性,跑绿。
  - 对照表 §4 的"待复核"标记已更新为"已复核"。
  - 全套件零回归。

验证命令:
  - 先 glob 确认 m4 是否有就近 tests 目录;有则:
    .venv\Scripts\python.exe -m pytest flaghunter/cpa_modules/m4_audit_guard/tests -q -p no:cacheprovider
  - 门禁:.venv\Scripts\python.exe -m pytest tests/unit/agents/ -q -p no:cacheprovider
  - DoD 零回归:.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
    (本环境缺 certifi/aiohttp 致整片 integration/runtime-proxy 预存失败,需以
     clean HEAD 复现确认与本卡无关,而非误判为回归。)

风险级别:
  - 低/中。单模块,默认不触调用路径。若修正改变 DataProtector 默认遮蔽行为,
    须确认无下游依赖原(疑似错误的)行为,并跑全量;不触 initializer 接线,
    无需 live eval。

通用纪律:
  - 双提交:① fix/refactor(m4 修复或注释澄清 + 测试)② docs(对照表 §4 更新)。
  - 直接提交 main 不 push;git commit -F <tempfile>(临时文件写 D:\tmp);
    每个 commit 结尾署名 Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>;
    不碰 challenges/。
```

---

## 卡 E — benchmark backup_node_app:zip 验收链转绿(高风险·独占 pa_agent) ✅(ed8cdb4)

> 收口结论(2026-06-20):根因不在"本地路径未升级",而在 `artifact_forensics.py` 顶层**漏 import json**
> (P5 抽包时丢失)。`_analyze_attachment_artifact` 的 `json.loads(...)` 抛 `NameError`,被裸 `except Exception`
> 吞掉后于 L824 提前 return,导致 **HTTP 与本地两条路径**的 `ctf_artifact_forensics` note 与
> `artifact_forensics_summary` 观测从不落地——即"能力已实现却被静默禁用"族。最小修复=补 `import json`,
> 让既有落地代码真正执行(语义与 HTTP 路径完全一致,backup.zip 无 flag→不引入假 verified)。
> 验证:benchmark case 转绿(matched=True/candidate_only_honesty);sibling 集成 15/15 绿;
> 隔离重跑 14 例验收链:基线 13/14(misc_artifact_forensics 因同一 NameError 预存失败)→ 修复后 **14/14**
> (顺带修好该预存失败,零新增回归;全量套件里那 13 例的偶发失败为长跑端口/资源竞争抖动,基线隔离同样通过)。


> ⚠️ 高风险卡:真改 dispatcher 验收判定路径,**须 live eval 回放兜底,禁与任何 pa_agent/ 卡并行**。
> 文件锁:flaghunter/agents/pa_agent/{artifact_forensics.py(主位),coordinator.py,strategy_registry.py}。
> 派发期间须独占 pa_agent/——确认并发后台写手未在编辑该目录。

```
【高风险任务卡｜benchmark backup_node_app:zip 验收链转绿（candidate_only_honesty 升级）】

只读取证、随后实现。先只读复现+定位，再动生产代码，最后跑门禁。

[1] 文档锚点
- 根因文档：docs/dev/FlagHunter_预存验收链失败_根因characterization_2026-06-16_V1.md
  （该文档把 backup/profile 类失败归为"探测层在剥过 HTML 的文本上跑、能力其实已实现却被静默禁用"——
   本卡同属"已实现的取证链未在某条输入路径上触发"族，按其方法论先核触发条件再改）
- 预存失败用例：tests/eval/test_benchmark_runner.py::test_run_benchmark_supports_local_backup_node_app_zip_case
- 分类器：tests/eval/benchmark_runner.py::_derive_eval_observed_outcome（candidate_only_honesty vs honest_no_flag 判定）

[2] 详细目标（分阶段）
  阶段A 复现+定位（只读）：跑该用例确认 observed_outcome='honest_no_flag'、expected='candidate_only_honesty'、matched=False。
    定位缺失逻辑：zip 变体的 challenge_context 把 backup.zip 放进 artifactPaths，
    flaghunter/agents/pa_agent/artifact_forensics.py::_ingest_local_challenge_artifacts 会发出 local_challenge_artifact 观测并解压，
    但 artifact_forensics_summary 观测仅由 _run_artifact_forensics_strategy 在通过 HTTP artifact_url 下载并 execute_command 成功时发出（约 L844-858）；
    本地 artifactPaths（无 HTTP URL）这条路径下该观测从不触发。
    分类器 _has_source_only_artifact_forensics_signal 要求 {local_challenge_artifact, artifact_forensics_summary} 两个观测都在，
    缺其一 → 落到 honest_no_flag。即"升级未实现"=本地归档取证未升级为对 artifact_forensics_summary（或 candidate_flag）的产出。
  阶段B 实现：在 artifact_forensics.py 内补齐"本地 artifactPaths/解压根目录"路径上的取证产出，
    使其落地 artifact_forensics_summary 观测或 candidate_flag（与现有 HTTP 路径语义一致、不引入假 verified）。
  阶段C 验证：该 benchmark case 转绿，且 sibling integration（test_backup_node_app_candidate_eval.py）与 easy_login_none 的 honest_no_flag 不回归。

[3] 边界
  白名单生产文件（仅可改其一/其二，优先最小）：
    - flaghunter/agents/pa_agent/artifact_forensics.py（缺失逻辑主位）
    必要时（且仅当确证）才可触及：
    - flaghunter/agents/pa_agent/coordinator.py（仅本地资产 ingest 调用点 L803/L992 一线）
    - flaghunter/agents/pa_agent/strategy_registry.py（仅 artifact_forensics 注册项 L648 一线）
  不碰清单：tests/eval/benchmark_runner.py 的分类器（_derive_eval_observed_outcome 等，改它=作弊掩盖）、
    recovery.py 的 stop_candidate_only 防误报逻辑、ctf_dispatcher.py 的停机/验收主路径除非确证、
    challenges/、任何测试断言文件（不得放宽测试来"变绿"）。

[4] DoD（客观可跑）
  - tests/eval/test_benchmark_runner.py::test_run_benchmark_supports_local_backup_node_app_zip_case 转绿
    （eval_verdict.matched=True, observed_outcome=candidate_only_honesty）。
  - 全量 pytest 零新增回归（对齐当前基线：本地 challenges/ 未跟踪、工作树干净）。

[5] 验证命令
  .venv\Scripts\python.exe -m pytest tests/eval/test_benchmark_runner.py -q -p no:cacheprovider
  .venv\Scripts\python.exe -m pytest tests/integration/test_backup_node_app_candidate_eval.py tests/integration/test_local_challenge_runner.py -q -p no:cacheprovider   （sibling 集成）
  .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider   （全量）

[6] 风险级别 = 高
  真改 dispatcher 验收判定路径（artifact 取证 → 观测/candidate → eval 分类），必须 live eval 回放兜底
  （改完务必跑 [5] 三条命令全绿，尤其确认 easy_login_none 仍判 honest_no_flag、无新增假 verified）。
  禁与任何 pa_agent/ 卡并行——artifact_forensics.py / coordinator.py / strategy_registry.py 文件锁，
  派发期间不得有其他写手编辑 pa_agent/。

[7] 通用纪律
  双提交：fix 与 docs 分两个 commit。main 不 push。
  提交用 git commit -F D:\tmp\<msgfile>（消息文件写在 D:\tmp）。
  每条 commit 末尾署名：Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  不碰 challenges/。
```

---

## 卡 F — M6 apply_turbo 死代码删除 ✅(837f0d2)

> 已完成并主控审核通过。结论:apply_turbo 经核为零调用点死代码(全仓仅定义+导出+文档,生产侧 0 调用),走删除路线 A;保留 _wrap_tool registry。新建 tests/unit/cpa_modules/m6_turbo/test_m6_turbo_deadcode.py 锁"已删 + 无残留引用"(7 passed)。M6 加速面收敛为 /turbo 命令。文件锁:flaghunter/cpa_modules/m6_turbo/**。零越界。

---

## 卡 G — initializer 门控统一走 is_mN_enabled ✅(b52cb0c)

> 已完成并主控审核通过。结论:M1/M3/M4/M6 统一经 is_mX_enabled() 门控;M2/M5 因 is_mN_enabled 含 _initialized 前置(若用于 init 前门控会自锁致 init 永不执行),**刻意保留直读 env**。新增守卫测试 tests/unit/session/test_cpa_hook_gating.py(27 项,套件 41 passed)。文件锁:flaghunter/session/initializer.py + tests/unit/session/。零越界。

---

## 卡 H — easy_tornado 观测命名复核(render_ssti vs cookie_secret) ✅(399f262)

> 已完成并主控审核通过。结论:阶段 B 选① —— 根因文档 §1.1"未记录 render_ssti_response"是 0957d94 之前的过时快照;生产三条 SSTI 路径(ssti_executor.py)都在 cookie_secret_leaked 前先发 render_ssti_response,测试 L404-405 已同时断言两者(3 passed)。仅在根因文档 §1.1/§1.2 补复核结论块,未触生产、未改断言含义。文件锁:根因文档 .md。低风险。

---

## 卡 I — 补建 ADR §8 变更记录章节 ✅(b51f056)

> 已完成并主控审核通过。在 ADR §7 后补建 `## 8. 变更记录`(总索引表 21 行,纯增 34 行 / 0 删),§5.2 进展日志保留为详述、二者并存。文件锁:ADR .md 独占。零越界、纯增量。

---

## 卡 J — M6 register_turbo_commands 接线复核 ✅(复核·零改动)

> 已完成并主控审核通过。阶段 0 取证 gate 确认**统一 command_registry 体系仍不存在**(全仓无 register(name,func) 消费者:HookRunner 是限四类 event 的事件总线、ToolRegistry 三参、StrategyRegistry/CapabilityRegistry 签名不符;/turbo 走 tui.py:5073-5104 硬编码 elif 链)。走 (b) 维持预留:register_turbo_commands 保留为预留接口,不接线/不删除/**零代码改动**、零回归。文件锁:无(仅取证)。
> **升格提议(候选新卡)**:若要落实统一 slash-command 注册体系——M0/initializer 持有 registry + 为 M2/M5 等补 register_*_commands + tui.py 分发改查表——会牵动全 M1–M6 elif 链,属独立**高风险跨模块**卡,另立处理。

---

## 卡 L1 — ChainContext.services 收窄为 StrategyServices Protocol(高风险·真·改路径·独占 pa_agent) ✅(b73b6bf)

> 已完成并主控审核通过(live 回放兜底)。这是 P3b 主体刀/第④刀明确预告的「另一张高风险卡」:把 `ChainContext.services` 的静态类型从 `Any` 收窄为显式 `StrategyServices` Protocol(`strategy_registry.py` 顶部新增,`@runtime_checkable`),刻画 execute lambda 经 `ctx.services.<method>` 无条件调用的 **20 个必调成员**(全 `async -> _ChainOutcome`)。
> **核心裁决(采 option b)**:3 个 hasattr 守卫成员 `_run_jwt_manipulation_strategy` / `_run_graphql_introspection_strategy` / `_run_nosql_injection_strategy` **留在 Protocol 外**——带 LLM fallback、语义上可缺失,纳入「必有」契约会与运行期 optional 语义矛盾,故保留 duck-typing 并在 probe 处加注。
> **风险定性**:本属主体刀注明的「`services` 收成 Protocol」真·改路径,受 live 回放门槛约束;但 `_strategy_context` 仍 `services=self`(同一对象/MRO),仅静态收窄、零行为变化。**门禁**:`tests/unit/agents/` 489 passed/0 failed、`tests/eval/test_replay_harness.py`(live 回放)5 passed/0 failed,零差兜底。
> **边界**:仅动 `strategy_registry.py` + `tests/unit/agents/test_ctf_dispatcher.py`(`ctf_dispatcher.py` 本次未触,`services=self` 早于第④刀就位),coordinator/recon/chains/eval 零越界。至此 **P3b(关节 B)从「结构破除」升级到「显式类型契约」彻底收口**。详述见 ADR §5.2「P3b L1」+ §8 索引。

---

## 卡 L2a — coordinator 的 dispatcher: Any 收窄为 CoordinatorDispatcherServices Protocol(P3b 关节 B 延伸·破冰刀·真·改路径·独占 coordinator.py) ✅(4960eaf)

> 已完成并主控审核通过(live 回放兜底)。把 L1 手法用到 coordinator 层:`coordinator.py` 顶部新增 `@runtime_checkable CoordinatorDispatcherServices` Protocol,刻画 `CTFCoordinator` 把 dispatcher 当方法参数逐个传入时**无条件访问**(bare `dispatcher.X`)的依赖面——共 **39 成员 = 22 必调方法 + 17 必有属性/引擎句柄**(audit 6 / dispatcher 本体 7 / flag 3 / recon 3 / notes 2 / progress 1;属性含 `state: CTFState|None`、5 个引擎句柄标 `Any`、10 个 run-scratch 字段)。
> **主控裁决(唯一高判断点)**:① 单个大 Protocol(横跨多簇,分组无益);② `strategy_memory` 虽仅 getattr+`is None` 访问,按依赖面完整性**纳入**标 `Any|None`。**7 守卫成员留 Protocol 外**(option b):`_ingress_handoff` + `_restore_context` / `_ingest_local_challenge_artifacts` / `_ingest_registered_local_source_hints` / `_align_platform_challenge` / `_extract_flag` / `_record_ingress_handoff_observations`(getattr+`callable()`,语义可缺失)。**裁决保留 4 处 `Any`**:2 模块级 helper 参数(只摸 OUT 成员 `_ingress_handoff`)+ `RunContext.__init__`/property(不改 RunContext;`_run_solve_loop` 经 `ctx.dispatcher` Any 逃生口、不入 Protocol)。
> **风险定性**:真·改路径(改类型契约),但注入对象不变(生产无参 `CTFCoordinator()` + 逐参数传真实 `CTFTaskDispatcher`,测试传 fake)、Protocol 运行期不强制,纯静态收窄、零行为变化;23 处形参 `dispatcher: Any` → `CoordinatorDispatcherServices`,调用体 163 处访问点一行未改。**门禁**:`tests/unit/agents/` 489 passed/0 failed、`tests/eval/test_replay_harness.py`(live 回放)5 passed/0 failed,零差兜底。
> **边界**:仅动 `coordinator.py`(50 个 coordinator 测试的 fake dispatcher 靠 duck-typing 满足实际调用子集,零改动),ctf_dispatcher/executor mixin/chains/eval/RunContext 实质逻辑零越界。至此**关节 B 的 coordinator↔dispatcher 隐式依赖面亦显式化成契约**,与 L1 的 strategy 层对称收口。详述见 ADR §5.2「P3b L2a」+ §8 索引。

---

## 卡 L2b — 闭合 RunContext 的 dispatcher: Any 缺口,收窄到 CoordinatorDispatcherServices(P3b 关节 B 延伸·收口刀·真·改路径·独占 coordinator.py) ✅(6f43a87)

> 已完成并主控审核通过(live 回放兜底)。L2a 把 23 处合约形参收窄为 `CoordinatorDispatcherServices`,但 `execute()` 喂进的是 `RunContext(dispatcher)` 透明代理(`__init__`/`dispatcher` property 仍 `Any`)——契约恰在包装器这一环留 `Any` 缺口(L2a「不碰 RunContext」点名延后的 L2b+)。本卡收窄之。**Phase 0**:`RunContext` 仅用于 `coordinator.py`,`ctx` 流入全部 23 形参;`ctx.dispatcher.X` 逃生口访问仅 1 处 = `_run_solve_loop`(L1790)。
> **主控裁决(3 点)**:① **纳入 `_run_solve_loop`**(async、真实签名、返回标 `Any`)——这是把 `RunContext.dispatcher` property 从 `Any` 收窄的前置耦合,Protocol 39→40;② **RunContext 不显式继承 Protocol**,靠返回 `Any` 的 `__getattr__` 结构化合规(最小改动,`__getattr__`/`__setattr__` 运行期一行未改);③ **2 个模块级 helper 形参保留 `Any`**(只经 getattr 摸 OUT 成员 `_ingress_handoff`,收窄零收益且语义不诚实)。
> **风险定性**:真·改路径(改类型契约),但 `from __future__ import annotations` 在顶、注解运行期不求值,纯静态收窄、零行为;注入对象不变。**门禁**:`tests/unit/agents/` 489 passed/0 failed、`tests/eval/test_replay_harness.py`(live 回放)5 passed/0 failed,零差兜底。
> **边界**:仅动 `coordinator.py`,测试零改动,ctf_dispatcher/executor/chains/eval 零越界。至此 **coordinator 自身调用路径的 `Any` 缺口全闭合**(仅余 2 处裁决保留的模块级 helper `Any`),L2a+L2b 合并完成「关节 B coordinator 层 dispatcher 依赖面显式化」。详述见 ADR §5.2「P3b L2b」+ §8 索引。

---

## 卡 L2c — 补 CoordinatorDispatcherServices 生产侧 conformance 断言(对称 L1·CI 强制·test-only·独占 test_ctf_dispatcher.py) ✅(b200123)

> 已完成并主控审核通过(live 回放兜底)。L1/L2a/L2b 把契约建在**消费侧**(形参/包装器视图),但无证据保证**生产侧**真实 `CTFTaskDispatcher` 供齐契约成员(某 mixin 方法改名/删除只在运行期炸)。L1 早已留对称范式:`test_ctf_dispatcher.py:73` 的 `assert isinstance(dispatcher, StrategyServices)`。本卡为 L2a/L2b 的 `CoordinatorDispatcherServices`(40 成员)补同款生产侧断言。
> **Phase 0**:① `mypy` 未安装、CI lint 只跑 `ruff`+`black`(`continue-on-error`)→ **pytest 是 CI 唯一强制门,静态断言零强制力**;② `CTFTaskDispatcher.__init__`(L299–328)初始化全部 17 数据成员,23 方法 + `_run_solve_loop` 由 mixin 提供 → 新实例即满足 `isinstance`;③ 用 `isinstance`(非 `issubclass`)→ data-member 检查跨 3.10–3.12 一致、不触 `TypeError`。**无高判断点**——设计由 L1 对称性唯一确定,不设裁决门。
> **落地**:加 `CoordinatorDispatcherServices` import + 专用 test `test_dispatcher_conforms_to_coordinator_dispatcher_services_protocol`。**边界**:仅动 `tests/unit/agents/test_ctf_dispatcher.py`,**零生产改动**。**门禁**:`tests/unit/agents/` 490 passed/0 failed(489+1)、`tests/eval/test_replay_harness.py` 5 passed/0 failed。至此 **L2 线消费侧+生产侧双向闭合**,与 L1 strategy 层完全对称。详述见 ADR §5.2「P3b L2c」+ §8 索引。

---

## 卡 L3a — RunContext 字段分流机制(L3「真断透传」线破冰刀·空白名单·零承载·独占 coordinator.py) ✅(3bd372e)

> 已完成并主控审核通过(独立坐实门禁 + live 回放兜底)。L2 把 coordinator↔dispatcher 契约**显式化**(Protocol),但运行期 coordinator 仍把整个 dispatcher 当参数透传。L3 线目标=让 coordinator 经 RunContext 承载 run-state/executor、dispatcher 缩成 façade。**测绘关键发现**:`RunContext`(coordinator.py)已全程接通 execute() 主干(`ctx=RunContext(dispatcher)`,18 个 `_apply_*` 收 ctx),但仍纯透明代理、承载量 0;其 `__setattr__` 全代理是后续一切真承载的**硬闸门**。
> **L3a(破冰·采主控裁决的候选 A)**:给 RunContext 加"自有字段白名单 + object.__* 分流"骨架,白名单 `_OWN_FIELDS=frozenset()` **留空**。`__setattr__`:白名单内走 `object.__setattr__`、否则代理 dispatcher;`__getattr__`:对内部名 `_dispatcher`/`_OWN_FIELDS` 显式短路抛 AttributeError(杜绝 _dispatcher 未就绪时代理递归)、白名单未设值不代理(防影子读穿)、其余代理。**白名单为空→行为与纯透明代理完全一致(零承载、可推理证零行为)**。把"机制"与"承载"解耦成两刀(本刀只建闸门,承载 state 是 L3b)。
> **关键发现(纠正 DoD 假设)**:Py3.12 `runtime_checkable` Protocol 的 `isinstance` 走 `getattr_static`(忽略 `__getattr__`),故透明代理 ctx **本身不满足** `CoordinatorDispatcherServices`——这 L3a 前后一致、非本刀回归(透明代理固有);真实满足契约的是 `ctx.dispatcher` 真身(传给 Protocol 形参的对象)。测试据此改为坐实"L3a 不改变 isinstance 行为 + dispatcher 真身满足契约",而非断言假前提。
> **边界**:仅动 coordinator.py 的 RunContext 类(+28 行)+ 新建 `tests/unit/agents/test_ctf_run_context.py`(10 测试,+121 行)。不碰 dispatcher/executor/chains/eval/coordinator 其它方法。**门禁**:`tests/unit/agents/` 500 passed/0 failed(含新 10)、`test_replay_harness.py` 5 passed/0 failed。**为 L3b(RunContext 真承载 state·共享引用)开闸**。
> ⚠ 过程注记:执行 agent 跑长 pytest 时一度"假死"(提前 rest 给非结论),主控误以为卡死、派了收尾 agent;原 agent 实际跑完并提交 3bd372e,主控查清后叫停收尾 agent 防重复。改动无丢失/无重复。

---

## 卡 L3b — ProgressTracker 对象化(L3「真断透传」线·执行体对象化第一刀·切法 A·不动 MRO) ✅(35d7649)

> **裁决换序**:原 L3 路线 L3b=承载 state、L3c=executor 对象化。测绘暴露 **state 是最难安全承载的字段**——唯一运行期 rebind 在 `ctf_dispatcher.py:1680`(`_restore_context` resume 路径,`CTFState.from_snapshot()` 返新身份),eager 引用承载(切法 B)会在 resume 后与 dispatcher 新 state **分叉失同步**,且 dispatcher 不持 ctx 引用、回写要走反向通道。故 **state 延后**,先在最闭合·零扇出的 **ProgressTracker** 上验证对象化范式。
> **切法 A(裁定落点)**:`progress_tracker.py` 抽出独立 `ProgressTracker` 类(方法显式收 `state` 参,**绝不 eager 持 state 引用**——规避 rebind 坑);`ProgressTrackerMixin` 两方法(`_snapshot_flag_counts`/`_derive_progress_delta`)退化为 thin 委派壳(`__module__` 锚定测试仍成立);`CTFTaskDispatcher.__init__` 持 `self._progress = ProgressTracker()`。**两个调用站不动**(`ctf_dispatcher.py:448` / `coordinator.py:1467` 经委派壳行为等价),**不动 MRO**(`:260` 保留)。
> **不选 B/C 的理由**:B 摘 MRO + 注入 ctx 承载,但 `dispatcher.py:448` 无 ctx 句柄 → 要么退化成 A,要么透传 ctx 进 solve-loop 造新扇出,违"最闭合"初衷;承载/路径切 ctx 留独立后续卡。
> **不变量**:5-key dict 等价;terminal/strong/rejected/weak/none 分级逐条等价,尤其 `:66 chain_outcome.progress` 短路返回 `"none"`(非 `"rejected"`)这条 bug-fix。
> **门禁**:`tests/unit/agents` 全量零回归 + 新单测(独立 new `ProgressTracker` 脱离 dispatcher 跑 None 守卫/计数递增/短路三类)。纯计数·零 I/O,**不跑 live replay**。边界:仅 `progress_tracker.py` + `ctf_dispatcher.py` + 测试文件;不碰 docs/challenges。
> **✅ 完工(35d7649·独立坐实通过)**:`ProgressTracker` 新类无 `__init__`(零 eager 持 state,规避 rebind 坑),`snapshot_flag_counts(self, state)`/`derive_progress_delta(self, state, before_state, chain_outcome=None)` 显式收 state、无继承、无 dispatcher-only 依赖;mixin 两方法退化为 `return self._progress.<m>(self.state, …)` 委派壳(`__module__` 锚定测试仍过);`ctf_dispatcher.py:73` import、`:301` `self._progress = ProgressTracker()`;**MRO `:260` 未删、调用站 449/1467 未改、coordinator.py 不在 diff**。`:76-78` `chain_outcome.progress` 短路 → `"none"` 逐字保留。门禁:`tests/unit/agents` **425 passed/5 skipped**(零回归)、新测文件 **6 passed**(锚定×1 + None 守卫/计数/分级/短路 true→none/false→rejected 共 5)。3 文件 +140/−24。**后续**:摘 MRO + ctx `_progress` 承载 + 把 1467 路径切 ctx → 独立后续卡;硬骨头 `state` 承载仍延后(rebind 坑)。

---

## 卡 L3c — flag_observer 对象化(L3「真断透传」线·执行体对象化第二刀·切法 A·独占 pa_agent) ✅(563d525)

> **比选裁决(测绘 3 候选)**:AuditInfra/note_store/flag_observer 里选 **flag_observer**——唯一**零反向依赖底座**(`_observe_flag` 35 处全是消费者调它、无兄弟 mixin 调回,对象化不破单向依赖),本体无直接 I/O(落盘经 `_store_note` 委派仍留壳)。**AuditInfra 排除**(166 处反向调用底座 + 三类磁盘 store 运行期 rebind,对象化掀翻单向依赖);**note_store 排 L3d**(60 处反向调用 + 直写 `loot/notes.json`,需先解决落盘 replay 隔离)。推荐序 flag_observer→note_store→AuditInfra。
> **切法 A**:`flag_observer.py` 抽独立 `FlagObserver` 类(无 `__init__`、零 eager 持 state/context);`observe_flag` 把 state/两个 context **per-call 传值**(每轮+resume rebind 不能 eager 持),`verifier` + 4 个兄弟方法(`_store_note`/`_record_session_event`/`_hydrate_flag_proof`/`_record_wrong_flag_feedback`)**per-call 注入 bound method**(壳里现取跟随 MRO);mixin `_observe_flag` 保留原签名退化委派壳(35 调用站零改);dispatcher `__init__` 持 `self._flag_observer = FlagObserver()`。不动 MRO/调用站/coordinator。
> **不变量**:candidate/runtime/verified/rejected + None-guard 各分支逐字;rejected 仅当 `verification.flag` 真值才 `record_wrong_flag_feedback`;`store_note` 4 类 key(`ctf_flag_candidate`/`_runtime`/`ctf_flag`/`_rejected`)+ artifact 参数逐字;`build_verification_decision_event` payload 逐字。
> **门禁(风险略升·独占 pa_agent)**:`tests/unit/agents` 全量零回归 + 新 detached 单测(假 state/verifier + Mock 协作者,4 分支/None 守卫/rejected 条件/per-call 不 eager)+ **`tests/eval/test_replay_harness.py` 5 passed live 回放兜底**(热路径+落盘链路,委派壳零行为须回放坐实)。边界:`flag_observer.py` + `ctf_dispatcher.py` + `test_ctf_flag_observer.py`。
> **✅ 完工(563d525)**:`FlagObserver` 独立类(无 `__init__`、零 eager 持 state/context),`observe_flag` 把 state/两个 active context **per-call 传值**、verifier + 4 兄弟方法(`_store_note`/`_record_session_event`/`_hydrate_flag_proof`/`_record_wrong_flag_feedback`)**per-call 注入 bound method**;mixin `_observe_flag` 保留原签名退化委派壳(35 调用站零改),仍在 flag_observer 模块。`ctf_dispatcher.__init__` 持 `self._flag_observer = FlagObserver()`;MRO/调用站/coordinator 零改。3 文件 +224/−18。门禁:`tests/unit/agents` **515 passed**(零回归,`test_ctf_flag_observer.py` 11 passed)+ `test_replay_harness.py` **5 passed**(live 回放零差)。⚠ 过程注记:执行 agent 代码改完后撞 Anthropic 服务端 529 过载(连带安全分类器 `claude-opus-4-8` 不可用→主控写/执行操作全被挡),改动滞留工作树未提交;主控核实 `--stat` 形态符合切法 A 后,经用户 `!` 自助跑门禁+提交落地(见 [[feedback-handoff-scripts-when-blocked]]),零丢失。

---

## 卡 L3d — note_store 对象化(L3「真断透传」线·执行体对象化第三刀·切法 A·独占 pa_agent) ✅(2de4d1f)

> **测绘裁决(切法 A 4/5 干净)**:`NoteStoreMixin` 6 方法对象化为独立 `NoteStore` 类。三个"额外变量"两个非风险——① **落盘非风险**:写盘不在 note_store(只调 `notes_tool` 单例),replay 已有现成 `set_notes_file` tmp 隔离(`eval/replay.py`);② **40 反向调用非风险**:全 `self._store*`/`dispatcher._store*`,委派壳保原名原签名→零改,coordinator Protocol 桩也不动。
> **唯一真坑 = `_notes_log` 归属**:dispatcher 持有的可变 `list[str]`(`ctf_dispatcher.py:299`),`:574 result.notes = list(self._notes_log)` 直接读它。**必须留 dispatcher、委派壳 per-call 传 list 引用**(靠引用语义原地 `.append`),**绝不搬进 NoteStore 实例持有**(否则断 result.notes 取数=非零行为)。
> **切法 A**:`NoteStore` stateless 类,`store_note(state, *, runtime, register_artifact_record, emit, notes_log, key, value, category, **metadata)` 等——state per-call 传值、兄弟方法(`_record_session_event`/`_register_artifact_record`/`_select_hypothesis_for_chain`/`_emit`)per-call 注入 bound method、`_notes_log` 传引用;两个 `_derive_*` 纯函数随搬;mixin 6 方法保原签名退委派壳;dispatcher `__init__` 持 `self._note_store=NoteStore()`。不动 MRO/调用站/coordinator/Protocol 桩。
> **不变量**:notes.json 内容/格式逐字(notes_tool 负责);`_notes_log` 追加 `f"[{category}] {key}: {value}"` 逐字 + `result.notes` 取同一 list;artifact 注册/session 事件/`state.add_artifact` 参数逐字;`derive_*` 映射逐 key。
> **门禁(独占 pa_agent)**:`tests/unit/agents` 全量零回归 + 新 detached 单测(脱离 dispatcher + `set_notes_file(tmp)` + 独立 list 充 notes_log 证传引用)+ `test_replay_harness.py` 5 passed(落盘隔离零差兜底)。边界:`note_store.py` + `ctf_dispatcher.py` + `test_ctf_note_store.py`。⚠ 若执行 agent 撞 529/分类器不可用,改动留工作树未提交,主控核 `--stat` 后经用户 `!` 落地(见 [[feedback-handoff-scripts-when-blocked]])。

---

## 卡 L3e — AuditInfra 的 RT(runtime action)簇对象化(L3「真断透传」线·执行体对象化第四刀·切法 A·独占 pa_agent) ✅(cc75c06)

> **测绘裁决(取拆分方案 B)**:AuditInfra(`AuditInfraMixin` 13 方法)实为 **5 个半独立簇**(session ledger / artifact registry / checkpoint / source hint / **runtime action**)。整体打切法 A 虽 4/5 可行,但有两代价:① `_ledger_run_id` 双向流 + setup 接力(coordinator 回读 dispatcher 字段);② **挖出既有缺陷**(见下)。故**只取最闭合的 RT 簇先吃一口**。
> **RT 簇为何最干净**:3 个 `_runtime_*_action`(browser/proxy/execute_command)只依赖 `self.runtime`(稳定)+ `self._record_session_event`(兄弟注入),**不碰任何 store 字段/run_id/bool/state**;反向调用面最大(122 处)但形态全 `self.` 统一→委派壳零改;**RT 不持三个 store → 完全绕开 replay 隔离洞**,这刀不动 replay.py/coordinator,纯净低风险。
> **切法 A**:抽 stateless `RuntimeAuditedActions` 类(3 方法逐字搬,`self.runtime`→`runtime` 注入、`self._record_session_event`→`record_session_event` 注入 bound method);mixin 3 方法保原名原签名退委派壳(122 调用站零改);dispatcher `__init__` 持 `self._runtime_actions`。不动 MRO/调用站/coordinator/其余 10 方法/store 字段/replay.py。
> **门禁(独占 pa_agent)**:`tests/unit/agents` 全量零回归 + 新 detached 单测(脱离 dispatcher,假 runtime + Mock record_session_event,called/finished 成对发射、无自持状态)+ `test_replay_harness.py` 5 passed。边界:`audit_infra.py` + `ctf_dispatcher.py` + `test_ctf_audit_infra.py`。⚠ 撞 529 则改动留工作树,主控核后经用户 `!` 落地。
> **✅ 完工(cc75c06)**:`RuntimeAuditedActions` stateless 类(无 `__init__`、`vars()=={}` 证零自持),3 个 `_runtime_*_action`(browser/proxy/execute_command)逐字搬入,`self.runtime`→注入、`self._record_session_event`→注入 bound method;mixin 3 方法保原名原签名退委派壳(122 反向调用站零改);dispatcher `__init__` 持 `self._runtime_actions`。**只动 RT 3 方法,其余 10 个 AuditInfra 方法/三 store 字段/setup/replay.py 零改;MRO 未动**。事件 payload/I/O/返回值逐字,簇内 `_record_session_event` 经注入仍命中同一 sink。3 文件原子提交。门禁:`tests/unit/agents` **523 passed**(零回归)+ `test_replay_harness.py` **5 passed**——**主控独立坐实**(亲跑 `test_ctf_audit_infra` 5 passed + replay 5 passed)。**后续**:store 三簇(S/RA/CP)+ SH 簇 + replay 隔离洞 = 卡 L3f(中风险,牵动 coordinator/run() 签名)。

---

## 卡 L3f-1 — 补 replay 三处落盘隔离洞(infra/bug-fix·生产零行为) ✅(615890c)

> **既有缺陷(L3e 测绘挖出,对象化之前就存在)**:`eval/replay.py` 仅 `set_notes_file` 隔离 notes;三个 store 在 `audit_infra.py` `_setup_*` 硬编码 `Path("loot")/...` 默认根、setup 时即 mkdir;`run()`/`coordinator.execute()`/`_bootstrap_dispatcher` 透传链**已有 `ledger_root`/`checkpoint_root` 但缺 `registry_root`**(coordinator `:709` 硬编码 None),`run_replay` 也没传任何 root → **replay 把 session_ledger/artifact_registry/checkpoint 写进真实 `loot/`**。
> **测绘裁决(拆卡·甲先)**:最小改法 = `run()`/`execute()`/`_bootstrap_dispatcher` 各加 `registry_root`(kwonly·默认 `None`)+ `:709` 改透传 + `run_replay` 在 `TemporaryDirectory` 块给三个 root 指向 tmp 子目录。**不需 finally 复原**(store root 是 per-call 入参非全局 module state,run 完即弃,tmp 退出即清)。生产路径不传 → 默认 None 字节不变。Protocol 的 `_setup_*` 签名已含 registry_root,无需改 Protocol。
> **门禁**:`test_replay_harness.py` 5 passed + 新断言(replay 前后真实 `loot/{session_ledgers,artifact_registry,checkpoints}` 无新增文件)+ `tests/unit/agents` 全量零回归(改了 run()/coordinator 签名须全量确认生产零回归)。边界:`ctf_dispatcher.py`(run 签名)+ `coordinator.py`(execute+_bootstrap)+ `eval/replay.py` + 测试。**触碰 coordinator 签名但纯增量 None-默认 = 低风险**。⚠ 撞 529 则改动留工作树,主控核后经用户 `!` 落地。
> **✅ 完工(615890c)**:`run()`/`execute()`/`_bootstrap_dispatcher` 各加 `registry_root`(kwonly·默认 None)+ `:709` 改透传;`run_replay` 在 `TemporaryDirectory` 块给三个 root 指向 tmp 子目录(复用已 import 的 `Path`,未动 finally);三个 `_setup_*` body 未动。生产路径不传→`xxx_root or 默认`原逻辑,字节不变。新测 `test_replay_does_not_touch_real_loot_stores`(replay 前后真实 loot 三目录快照断言无新增)。**连带改动**:`test_ctf_coordinator.py` 的 `_FakeCoordinator.execute` 替身镜像新签名(否则新 kwarg 触发 TypeError fallback 误抛=改前那条 `test_dispatcher_run_delegates_to_coordinator_execute` 失败根因)。门禁:`test_replay_harness.py` **6 passed**(5 fixture reproduced + 新隔离守护)+ `tests/unit/agents` **523 passed**——**主控亲跑 replay 6 passed 独立坐实**。5 文件 +63/−4。**为 L3f-2(乙)的产物对拍开闸**。

---

## 卡 L3f-2 — AuditInfra store 簇对象化(切法 A·一次抽全 4 簇·独占 pa_agent·中风险) ✅(8ecd999)

> **依赖**:L3f-1(甲 `615890c`)已合入,用"replay 写 tmp,fixture 仍 reproduced"做产物对拍等效证据。与 L3f-1 都碰 `ctf_dispatcher.py`,**串行**(甲已合,现派乙)。
> **测绘裁决**:RT 簇(L3e)已抽走,剩约 10 方法(session ledger / artifact registry / checkpoint / source hint / `_record_recovery_decision`)**一次抽全到单个 stateless `AuditStore`**(分簇会制造 `_record_session_event` sink 跨 class 注入、不划算)。切法 A 4 簇全适用:三个 store 对象 + 三个 run_id + `_registered_local_source_hints_loaded` flag **留 dispatcher**(coordinator 直读 `_ledger_run_id`/Protocol 声明它 + flag;`_restore_context:1644/1661/1663` 直读 `_checkpoint_store`);`_setup_*` 委派壳**返回 `(run_id, store)` 写回 `self._xxx`**(保 setup 接力 + coordinator 回读语义);写事件簇 per-call 传 store 引用+run_id+state+`record_session_event` bound method;`_ingest` 的 loaded-flag 守卫留壳里。`_restore_context` 零改(store 留 dispatcher 传引用的关键收益)。
> **门禁(独占 pa_agent)**:`tests/unit/agents` 全量零回归(含 `test_ctf_audit_infra`/`test_ctf_dispatcher_artifact_registry`/`test_ctf_dispatcher_checkpoint_store`/`test_ctf_coordinator`)+ **replay 产物对拍**(依赖甲:抽前抽后 tmp 内 session_ledger/artifact_registry/checkpoint 逐字节相同)。理论上**不需改 coordinator**(委派壳保名保签,coordinator 只调 `_setup_*` 名 + 读 `_ledger_run_id`)。边界:`audit_infra.py` + `ctf_dispatcher.py`(+ 必要时测试)。**需主控先确认甲已合再派**。
> **✅ 完工(8ecd999)**:剩余 10 方法一次抽全到 stateless `AuditStore`(`vars()=={}` 零自持);`build_session_ledger`/`build_artifact_registry`/`build_checkpoint_store` 返回 `(run_id, store)`,`_setup_*` 壳回写 `self._x_run_id, self._x`(artifact/checkpoint 经 `fallback_run_id=self._ledger_run_id` 保两步 fallback 接力);写事件簇 per-call 传 store/run_id/state + `record_session_event` 注入;`_ingest` 的 `state is None`→`loaded` 守卫顺序逐字保留在壳、收尾置 `loaded=True`;三 store/三 run_id/flag 全留 dispatcher `__init__`;**`_restore_context` 零改、coordinator 零改、MRO/调用站零改**;落盘默认 `Path("loot")/...` 三处不变。3 文件原子提交。**门禁**:`tests/unit/agents` **534 passed**(零回归)+ DoD 四件套 81 passed + 整文件 replay 6 passed——**主控独立坐实**(亲跑 DoD 四件套 81 passed + 整文件 replay 6 passed + 隔离测试单跑绿)。⚠ agent 报告里 replay 出现的 1 failed(`test_replay_does_not_touch_real_loot_stores`)经查证**与本刀无关**:整文件在主控环境 6 passed、隔离测试单跑绿、534 全量零回归——是 L3f-1 隔离补洞未闭合留下的**间歇旁路泄漏**(见卡 L3g),非 L3f-2 引入。**AuditInfra 至此整体对象化完毕**(RT 簇 L3e + store 簇 L3f-2)。
> **✅ 完工(2de4d1f)**:`NoteStore` stateless 独立类(6 方法逐字搬入,`_derive_*`→`derive_*`),state/runtime/4 兄弟方法/reasoning_layer 全 per-call 传值;**`_notes_log` 留 dispatcher、委派壳 per-call 传 list 引用、NoteStore 仅 `.append` 从不自持**(新测专门断言 NoteStore 实例无 `_notes_log` 属性 + 传入独立 list 被原地追加),故 `:574 result.notes=list(self._notes_log)` 仍读同一 list 字节级等价。`NoteStoreMixin` 6 方法保原名原签名退委派壳(`__module__` 锚定 note_store);`ctf_dispatcher.__init__` 持 `self._note_store=NoteStore()`;MRO/调用站/coordinator Protocol 桩零改。3 文件 +372/−34。门禁:`tests/unit/agents` **519 passed**(零回归)+ `test_replay_harness.py` **5 passed**(落盘零差)——**主控亲跑门禁独立印证**(519 passed + replay 5 passed,与 agent 报告一致)。⚠ 过程:执行 agent 给非结论 rest("等 monitor")疑似假死,主控先核 git 真相(同 [[feedback-handoff-scripts-when-blocked]] 教训)——实为 agent 在等自起的长 pytest,随后真完成并提交 2de4d1f,无重复派单。**后续**:AuditInfra(底座·166 反向调用·三磁盘 store rebind,留最后/单独立项)→ recon/llm/jwt(难)。

---

## 卡 L3g ✅(6204315)— replay 隔离测试间歇红修复(根因坐实=测试套件漏传 root)

> **完工(2026-06-22,fix `6204315`)**:audit_infra 加 `set_default_loot_root`/`get_default_loot_root` 进程级默认 loot 基址钩子(默认仍 `Path("loot")` 生产字节零改),三个 `build_*` 的 `*_root` fallback 改读该默认值;`tests/unit/agents/conftest.py` 加 autouse fixture 每测试把默认基址指向 `tmp_path`、teardown 还原。门禁:`tests/unit/agents` **534 passed**(零回归)、replay 整文件 **6 passed**(含隔离测试)、隔离测试连跑 **5 次 delta 恒 0**(修前间歇 +26)。**审计教训**:执行 agent 改完代码后陷入轮询空转、未提交未验证就歇手(回报仅"waiting for notification"),主控亲核 git 发现产出在工作树未提交 → 独立坐实门禁 + 显式 pathspec 收尾提交。

---

## 卡 L3h ✅(7c92ff4)— JWT executor 对象化(切法 A·L3 执行体对象化第七刀·破冰·低风险)

> **完工(2026-06-22,refactor `7c92ff4`)**:`JWTExecutorMixin` 6 方法抽成 stateless `JWTExecutor`(`vars()=={}`),退委派壳;`self.state` per-call 传值(未入实例)、`_recent_local_source_hint_secret_candidates` 作回调注入;`ctf_dispatcher.__init__` 持 `self._jwt_executor`。MRO/coordinator/jwt_contact_chain 零改。门禁:`tests/unit/agents` **538 passed**(基线 534 + 4 新 detached 单测,零回归)+ jwt 定向 9 passed(executor detached 5 + chain 2 + contact_chain 2)——主控独立坐实(亲跑 9 + 全量 538 + `git show --stat` 3 文件无越界)。执行 agent 本卡回报规范(纪律 prompt 生效,未再轮询空转)。

---

## 卡 L3i ✅(d7f97ac)— LLM executor 对象化(切法 A·L3 执行体对象化第八刀·中风险大刀)

> **完工(2026-06-22,refactor `d7f97ac`)**:`LLMExecutorMixin` 15 方法抽成 stateless `LLMExecutor`(`vars()=={}`),退 15 个委派壳保签名+保 hasattr;`self.llm`/`self.state`/runtime/collector_port/capability_registry 全经 per-call 短命 `LLMExecContext`(每调现造,绝不入实例)传、6 个兄弟方法作回调注入;2 个 `@staticmethod` 随迁。`strategy_registry` 的 `hasattr(dispatcher,'_run_llm_driven_exploration')` 运行时仍 True;MRO/coordinator/strategy_registry/ssti_executor 零改。门禁:`tests/unit/agents` **542 passed**(基线 538 + 4 新 detached,零回归)+ **replay 整文件 6 passed**(5 fixture 重放 LLM-driven exploration 全 reproduced=入口行为零变核心兜底)+ detached 5——主控独立坐实(亲跑 replay 6 + 全量 542 + `git show --stat` 3 文件无越界)。执行 agent 回报规范。

---

## 卡 L3j ⏳(派发中)— Recon executor 对象化(切法 A·L3 执行体对象化第九刀·最后一刀·中风险·三者最难)

> **文档锚点**:ADR §5.2 L3i(per-call ctx 容器范本 `d7f97ac`)。**主控测绘坐实**:`recon_executor.py:34 ReconExecutorMixin` 818 行 11 方法,适配度 3/5(兄弟耦合最宽 + 触 Protocol)。**切法 A + per-call `ReconExecContext`**:抽 stateless `ReconExecutor`(`vars()=={}`),11 方法逐字搬;`self.state`/`runtime`/`reasoning_layer` per-call 经 ctx 传(state 绝不入实例)、**~12 个兄弟方法**(`_runtime_browser_action`/`_runtime_proxy_action`/`_store_note`/`_scan_and_store`/`_fingerprint_framework`/`_should_ignore_exploration_candidate`/`_classify_exploration_hint_strength`/`_extract_embedded_links`/`_form_action_url`/`_emit`/`_is_legacy_browser_runtime_probe`/`_proxy_get_with_retry` 等)经 ctx 回调注入。**⚠ Protocol 强约束**:`_phase_recon`/`_explore_agenda_items` 是 `CoordinatorDispatcherServices` 声明方法(coordinator.py:116/118)→ 委派壳必须留确保 Protocol 契约不破。**文件锁**:`recon_executor.py` + `ctf_dispatcher.py`(import+__init__)+ recon 测试(含 detached)。不碰 coordinator/tui。**门禁(中风险)**:`tests/unit/agents` 全量零回归(基线 542)+ **replay 整文件 6 passed**(recon 触 `_store_note` 落盘验隔离 + recon→auth 链行为不变)+ Protocol 满足坐实 + recon→auth 集成用例绿。**收掉即 L3 执行体对象化系列(L3a–L3j)全部收官**,只剩"承载收尾"独立主线。

> **文档锚点**:ADR §5.2 L3h(切法 A 范本 `7c92ff4`)。**主控测绘坐实**:`llm_executor.py:32 LLMExecutorMixin` 769 行 15 方法(本系列最大一刀),适配度 4/5。**切法 A**:抽 stateless `LLMExecutor`(`vars()=={}`),15 方法逐字搬;`self.llm`+`self.state`+runtime/collector_port/capability_registry **per-call 传**(绝不入实例,replay/fork 换 state/llm 持旧引用=非零行为)、6 个兄弟方法(`_scan_and_store`/`_extract_flag`/`_observe_flag`/`_recent_observed_source_fetch_write_exploit`/`_runtime_proxy_action`/`_runtime_execute_command`)注入;有外部调用者的方法退委派壳保签名。**关键**:`strategy_registry.py:513/542/575` 有 `hasattr(dispatcher, '_run...')` 守卫——委派壳必须留确保 hasattr 仍 True、调用站零改。**真坑**:llm 句柄/state 绝不入实例。**coordinator/Protocol 零依赖,strategy_registry/ssti_executor 调用站零改**。**文件锁**:`llm_executor.py` + `ctf_dispatcher.py`(import+__init__)+ llm 测试(含 detached 单测)。不碰 coordinator/strategy_registry/ssti_executor。**门禁(中风险)**:`tests/unit/agents` 全量零回归(基线 538)+ **replay 整文件 6 passed**(5 fixture 重放 LLM-driven exploration 路径=核心兜底)+ detached 单测 `vars()=={}` + llm 入口/hasattr 守卫用例绿。**后续**:L3j(Recon·中·兄弟耦合最宽+触 Protocol,留最后);碰 `ctf_dispatcher.py` 须与 L3i 串行。

> **文档锚点**:ADR §5.2 L3d/L3e/L3f-2 切法 A 模式。**主控测绘坐实**(2026-06-22):`jwt_executor.py:19 JWTExecutorMixin` 183 行 6 方法(纯计算/编码,零落盘/零 LLM/零 runtime IO),适配度 **5/5**,三块硬骨头(recon/llm/jwt)里最闭合 → 选作破冰。**切法 A**:抽 stateless `JWTExecutor`(`vars()=={}`),6 方法逐字搬,`self.state` **per-call 传**(绝不搬进实例,同 L3d `_notes_log` 坑)、`_recent_local_source_hint_secret_candidates` 注入;Mixin 退委派壳保原名原签名;dispatcher `__init__` 持 `self._jwt_executor`。**真坑**:state/句柄绝不入实例。**coordinator/Protocol 零依赖、jwt_contact_chain(唯一外部调用面)零改**。**文件锁**:`jwt_executor.py` + `ctf_dispatcher.py`(__init__ 加一行)+ jwt 测试文件(含新 detached 单测)。不碰 coordinator/jwt_contact_chain。**门禁**:`tests/unit/agents` 全量零回归(基线 534)+ detached 单测证 `vars()=={}` + jwt chain 用例绿;纯函数无需 replay/eval。**后续**:LLM(L3i·中·体量大需 eval 兜底)→ Recon(L3j·中·兄弟耦合最宽+触 Protocol,留最后)。

> **🔍 主控测绘坐实(2026-06-22,翻转原假设)**:泄漏**不在 replay/生产**——`run_replay` 经内存 monkeypatch 验证 0 命中真实 loot(三 root 全程透传、`_restore_context` 只读不构造)。**真凶在测试侧**:`tests/unit/agents/test_ctf_dispatcher.py` ~26 个 `dispatcher.run(...)` 不传 `ledger_root` → `build_session_ledger` fallback 到 `Path("loot")/session_ledgers` → 每跑一个往真实 loot 写一个 `ctf-<uuid>.jsonl`;隔离测试只在与这些 dispatcher 测试同进程跑时把新文件算进 before/after delta → 间歇红。**采用方案**:audit_infra 加进程级默认 loot 基址钩子(`set_default_loot_root`,默认仍 `Path("loot")` 生产零改)+ 测试 autouse fixture 指向 tmp 根治。门禁:agents 全量零回归 + 隔离测试连跑 5 次 delta 恒 0 + replay 整文件 6 passed。文件锁:`audit_infra.py` + `tests/(unit/agents/)conftest.py`,不碰 replay/coordinator/dispatcher。

> **现象**:L3f-1 加的 `test_replay_does_not_touch_real_loot_stores` **间歇 fail**——replay 偶发往真实 `loot/session_ledgers` 漏写新 `ctf-<uuid>.jsonl`(uuid 每次不同);整文件多数 run 绿(主控 615890c/8ecd999 两次 6 passed),少数 run 红(L3f-2 执行 agent 环境命中)。**间歇 = 旁路 + 异步时序**。
> **根因方向**:L3f-1 只把 root 线穿过 `run()`/`_bootstrap_dispatcher`/`_setup_*`,但 replay 链路里**某条 store 构造没拿到 tmp root、退回默认 `Path("loot")`**。候选:`_restore_context` resume 路径、异步事件 flush、二次 dispatcher 构造、或某 fixture 走不经 `_setup_session_ledger` 的旁路。
> **L3g 应做**:① 派只读测绘定位"replay 期间不经 `_setup_*` 而构造 store 的旁路点"(grep `SessionLedger(`/`Path("loot")`/`get_loot_file` 在 replay 可达链路);② 补该旁路 root 透传,或给三个 store 加 replay 可设的基址钩子(类比 notes 的 `set_notes_file`,更稳);③ 隔离测试转稳定绿。**低-中风险,infra/test 收尾,需主控测绘+裁决再派。** 非阻塞(主路径 fixture 全 reproduced,泄漏只污染真实 loot 不影响判定),但 flaky 测试应尽快收。

---

## 卡 M — benchmark_runner 合并跑死锁取证 ✅(已复核·main 上非现存缺陷·关单·解除 eval 互斥锁)

> **状态:阶段 0 取证完成,关单。** 卡 L1 完工报告里浮出"`benchmark_runner` 合并跑死锁"的怀疑,经只读复现 + 结构性排除,**当前 main 上死锁复现不出**——五种"合并跑"解释全部跑绿,卡面假设的两个共享资源根因被结构性排除。**降级为"已复核·非现存缺陷",解除它对 eval 卡的互斥锁。**
>
> **实测全绿(无触发)**:默认 5 条合并 `python -m tests.eval.benchmark_runner` ✅ 30.6s;全 8 条合并(含 3 个 local_*)✅ 125s;`pytest tests/eval/test_benchmark_runner.py`(faulthandler_timeout=120)✅ 17 passed/108s;全量 suite(faulthandler_timeout=240)✅ 1937 passed/8 skipped/19m38s。
>
> **五项根因结构性排除**:① 端口撞车——临时分配(实测 49680 等),不可能撞;② 线程 join 死等——fixture teardown 全部 `server.shutdown(); thread.join(timeout=5); server.server_close()`,join 带 5s 上限 + daemon 线程,最坏多等 5s 无法无限阻塞;③ asyncio loop 复用——CLI 合并跑共用单一 `asyncio.run()`(`benchmark_runner.py:1015`),`run_benchmark` 内串行 `await spec.runner()`(L944-948),不嵌套 loop;④ 全局单例——每 challenge 用 `_isolated_notes`/`_benchmark_runtime_env`/`TemporaryDirectory` 隔离 + finally 还原(L102-149),唯一实例级 async 原语 `ctf_state.py:179 self._write_lock=asyncio.Lock()` 是 per-state 新建、不跨 loop;⑤ 子进程通信死等——未见无界 communicate。
>
> **方案 B(可选加固草稿·未派·低优先)**:不碰并发模型,只在 `run_benchmark` 的每条 `await spec.runner(callback)`(L947)外包一层 `asyncio.wait_for(..., timeout=N)`,把"未来若再现的挂起"转成可诊断的 `TimeoutError`(带 `challenge_id`)而非无限等。纯增量护栏、不改既有路径、live 回放兜底即可。**待有人手时做,非紧急**(当前无死锁证据,属预防性可观测加固)。文件锁 `benchmark_runner.py`,与 eval 卡互斥。

---

## 卡 N1–N4 — pa_agent 外死代码/bug 清理批次(S 扫描衍生·低风险·文件锁互斥·4 对话并行) ✅

> S 只读扫描(范围 tools/llm/knowledge/runtime/mcp/cpa_modules/config/interface/playbooks/workspaces,排除 pa_agent/eval/tui 命令分发)挖出的自包含切片,4 张文件锁两两不重叠、与 L2(coordinator)/eval 零交集,4 对话并行完成,主控逐张审核通过(边界 + 就近测试坐实)。**均零越界、未碰 backlog/ADR(文档由主控串行收口)**。
> - **卡 N1**(`6afd433`)`refactor(llm)`:删 llm/utils.py 5 个零调用函数 + 移除 count_tokens/truncate_to_tokens(连 llm/__init__.py import/__all__)+ 消除 count_tokens 恒等分支(if gpt-4/gpt-3.5 两分支同赋 cl100k_base、model 实际被忽略);parse_llm_json 保留。边界仅 llm/utils.py+llm/__init__.py(-160)。tests/unit/llm 绿。
> - **卡 N2**(`6e2126d`)`refactor(m6)`:删 m6_turbo 顶层便捷包装 lazy_get/lazy_wrap/install_lazy_hook(lazy_loader.py)+ get_memory_mb/quick_cleanup(memory_optimizer.py),保留 LazyLoader/MemoryOptimizer 类本体。边界仅这两文件(-61)。test_m6_turbo_deadcode 7 passed。
> - **卡 N3**(`27b9092`)`fix(playbooks)`:base_playbook.py 的 phases 默认值从裸 field(default_factory=list)(BasePlaybook 非 @dataclass → 实为 Field 对象、未覆写子类 get_task() 会崩)改为普通类属性 []+删 field import;新增 tests/unit/test_base_playbook.py 守卫(未覆写 phases 子类 get_task 不崩)。4 passed。
> - **卡 N4**(`8e77449`)`refactor(knowledge)`:删 retrospective.py 死代码 _safe_list(零调用);_extract_flag_values/_extract_hypothesis_kinds 保留。边界仅 retrospective.py(-9)。test_retrospective 5 passed。
> 汇总:96+4 passed、import 冒烟 EXIT=0、零回归。
> - **卡 C5**(`4884979`)`refactor(tools)`:token_tracker.set_data_file 判定=**测试专用 API**(test_token_tracker.py isolated_tracker autouse fixture 用它注入 tmp_path 数据文件),**保留+docstring 标注**(非删除,"测试专用、生产无调用、勿删"),零行为变化。16 passed。
> - **卡 C6**(`b88bb81`)`test(m5)`:consensus_mechanism.get_vote_status 判定=**预留对外契约接口**(兄弟方法 propose_binary/vote/propose_priority_ranking 被 swarm_commands.py 消费、语义对称),**保留+补 4 契约测试**(未知 vote_id 空状态 / 开放投票回显 total_votes·options·deadline·is_open / 关闭 is_open=False / 走公共 vote() 端到端坐实票数),零生产改动。16 passed(12+4)。
> C5/C6 均为判断题保守落点:**确证有用即保留+留证(标注/测试),不为清理而删**。background agent 自托管并行执行(主控开 run_in_background agent + 逐张审核 + 串行回写),非手动开对话。

---

## 卡 S1–S5 — 第二轮 S 扫描批次(3 真 bug + 1 死代码 + 1 docstring·background agent 自托管并行) ✅

> 第二轮 S 只读扫描挖出 5 个互斥切片,主控开 4 个 `run_in_background` agent 并行执行(S1+S2 同文件合并)、逐张审核(边界 + 就近测试 + 真 bug 修复正确性)。**全部代码已落历史、无丢失无重复**。
> - **卡 S1+S2**(`6de4d1d`)`fix(m5)`:pheromone_router.py 两 bug——S1 heapq 入堆元组加 `(-score, idx, prio)` enumerate 单调 tie-breaker(同 final_score 时不再比较不可比较的 TaskPriority→消除 TypeError 崩溃、稳定 FIFO);S2 新增 `is_active_above(threshold)`,`get_active_trails` 改吃 router 的 `self._threshold`(与 evaporate/get_stats 口径一致,修"写死 0.1 无视构造 threshold"配置失效);7 新测试坐实同分不崩 + 自定义阈值生效。11 passed。
> - **卡 S3**(`0e5ea9f`)`refactor(interface)`:删 utils.py 4 个零调用展示函数(format_tool_call/format_scan_progress/colorize_severity/format_command_output)+ 级联删仅被其调用的 truncate_output + 失效的 typing.Any import;保留 format_finding/print_status/print_banner。-120 行。267 passed。
> - **卡 S4**(`0c7f0cb`)`docs(m1)`:cost_tracker.get_recent_logs docstring 名实不符——grep 零调用方、无人依赖顺序,改 docstring "从新到旧"→"从旧到新(末尾最新)"符合实现 `list(_logs)[-n:]`(零行为变更最保守)+ 2 顺序契约测试。25 passed。
> - **卡 S5**(内容落 `9704e20`,见下注)`fix(knowledge)`:indexer.py `_index_data_file` :161 的 `file_path.suffix == ".json"`(大小写敏感原始 suffix)改 `.lower() == ".json"`,使经 index_file 已 lower 派发的大写 `.JSON` 正确走 json.loads 而非 YAML 分支;2 回归测试(毒化 yaml import 断言大写 .JSON 绝不进 YAML、与小写一致)。59 passed。
> **⚠ 并发竞争遗留(按"不改写历史"铁律保留原样)**:4 agent 并发提交时 staged-set 竞争,致 `9704e20` **内容是 S5 的 indexer 修复、但 commit message 错挂为 S4 的「docs(m1): cost_tracker...」标题**;S4 随后用 reset+pathspec 重做出干净的 `0c7f0cb`。两份改动均完整正确、无丢失无重复,**仅 9704e20 的 subject 名实不符**。活跃并发期 rebase 改写共享历史风险过高(可能与常驻写手碰撞),故不强行 reword——**真实映射以本表为准:S5=`9704e20`(内容)、S4=`0c7f0cb`**。

---

## 维护说明(给我自己/未来对话)

- 每完成一张卡,在卡标题后标 `✅(commit 短哈希)`,并回写 ADR §8。
- 每盘清一轮路线图,把新发现的"自包含+文件不重叠"切片加成新卡。
- 卡之间若出现文件交集,**串行**而非并行,并在卡里注明依赖顺序。
- 高风险卡(真改调用路径)必须在卡里写明"需 live eval 回放兜底",且不与同文件卡并行。
