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

## 卡 A — P3b 第④刀(收尾刀:删死字段 + 摘 dispatcher)

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

## 卡 B — roadmap-P5:cpa_modules m1–m6 命名/文档 + capability registry 收尾

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

## 维护说明(给我自己/未来对话)

- 每完成一张卡,在卡标题后标 `✅(commit 短哈希)`,并回写 ADR §8。
- 每盘清一轮路线图,把新发现的"自包含+文件不重叠"切片加成新卡。
- 卡之间若出现文件交集,**串行**而非并行,并在卡里注明依赖顺序。
- 高风险卡(真改调用路径)必须在卡里写明"需 live eval 回放兜底",且不与同文件卡并行。
