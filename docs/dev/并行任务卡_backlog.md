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

## 卡 M — benchmark_runner 合并跑死锁取证 ✅(已复核·main 上非现存缺陷·关单·解除 eval 互斥锁)

> **状态:阶段 0 取证完成,关单。** 卡 L1 完工报告里浮出"`benchmark_runner` 合并跑死锁"的怀疑,经只读复现 + 结构性排除,**当前 main 上死锁复现不出**——五种"合并跑"解释全部跑绿,卡面假设的两个共享资源根因被结构性排除。**降级为"已复核·非现存缺陷",解除它对 eval 卡的互斥锁。**
>
> **实测全绿(无触发)**:默认 5 条合并 `python -m tests.eval.benchmark_runner` ✅ 30.6s;全 8 条合并(含 3 个 local_*)✅ 125s;`pytest tests/eval/test_benchmark_runner.py`(faulthandler_timeout=120)✅ 17 passed/108s;全量 suite(faulthandler_timeout=240)✅ 1937 passed/8 skipped/19m38s。
>
> **五项根因结构性排除**:① 端口撞车——临时分配(实测 49680 等),不可能撞;② 线程 join 死等——fixture teardown 全部 `server.shutdown(); thread.join(timeout=5); server.server_close()`,join 带 5s 上限 + daemon 线程,最坏多等 5s 无法无限阻塞;③ asyncio loop 复用——CLI 合并跑共用单一 `asyncio.run()`(`benchmark_runner.py:1015`),`run_benchmark` 内串行 `await spec.runner()`(L944-948),不嵌套 loop;④ 全局单例——每 challenge 用 `_isolated_notes`/`_benchmark_runtime_env`/`TemporaryDirectory` 隔离 + finally 还原(L102-149),唯一实例级 async 原语 `ctf_state.py:179 self._write_lock=asyncio.Lock()` 是 per-state 新建、不跨 loop;⑤ 子进程通信死等——未见无界 communicate。
>
> **方案 B(可选加固草稿·未派·低优先)**:不碰并发模型,只在 `run_benchmark` 的每条 `await spec.runner(callback)`(L947)外包一层 `asyncio.wait_for(..., timeout=N)`,把"未来若再现的挂起"转成可诊断的 `TimeoutError`(带 `challenge_id`)而非无限等。纯增量护栏、不改既有路径、live 回放兜底即可。**待有人手时做,非紧急**(当前无死锁证据,属预防性可观测加固)。文件锁 `benchmark_runner.py`,与 eval 卡互斥。

---

## 维护说明(给我自己/未来对话)

- 每完成一张卡,在卡标题后标 `✅(commit 短哈希)`,并回写 ADR §8。
- 每盘清一轮路线图,把新发现的"自包含+文件不重叠"切片加成新卡。
- 卡之间若出现文件交集,**串行**而非并行,并在卡里注明依赖顺序。
- 高风险卡(真改调用路径)必须在卡里写明"需 live eval 回放兜底",且不与同文件卡并行。
