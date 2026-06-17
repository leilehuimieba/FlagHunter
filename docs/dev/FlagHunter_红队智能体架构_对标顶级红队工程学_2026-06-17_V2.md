# FlagHunter 红队智能体架构 V2 —— 对标顶级红队工程学

- 日期：2026-06-17
- 定位：架构方向文档（不是实现说明，不是越狱/绕过手册）
- 适用：授权红队 / CTF / 安全评估场景，`D:\webstudy\FlagHunter`
- 取代：[[FlagHunter_红队黑板智能体架构学习笔记_2026-06-17_V1]]（V1 的「Red-Team Blackboard Swarm」愿景保留，本版为其补上真实红队工程学根基）

---

## 0. 边界声明

本文讨论授权场景下的**红队智能体系统工程**。研究素材来自公开的行业标准与学术资料（MITRE、Lockheed Martin、SpecterOps、DARPA、OWASP、PTES 等）。学习对象是**系统工程方法与思维模型**，不沉淀可直接用于绕过真实系统的 payload 或复现步骤。

---

## 1. V1 的不足与 V2 的修法

V1 几乎全部从一篇「AI 红队实验室」文章反推，概念正确但**悬空**——它描述了一个理想的多 agent 黑板系统，却没有锚定真实红队工程师每天赖以思考的成熟框架。结果是：术语自洽但无外部坐标系，难以判断"我们离顶级还差什么"。

V2 的修法：**把真实世界顶级红队的三件东西灌进来**，并逐条映射到 FlagHunter 已落地的骨架与缺口。

> 顶级红队的 through-line（三份独立研究反复指向同一结论）：
> **① 图式规划（attacker thinks in graphs）  ② ATT&CK 映射的可复用知识  ③ 强迫式全量日志 → 可复现叙事。**
> 顶级 ≠ 拥有更多 exploit，而是内化了这三件事。

V2 还吸收了自主 AI 攻防 agent（DARPA CGC/AIxCC、PentestGPT、HPTSA、Cybench）的**实证教训**——其中最硬的一条:**瓶颈不是想法生成,而是验证、grounding、可复现**。

---

## 2. 五大专业框架 → FlagHunter 落点

红队框架沿三个正交轴互补:**流程**(PTES/WSTG)、**行为/序列**(Kill Chain/UKC/ATT&CK)、**知识表示**(Diamond)。每轴各取其一,不要二选一。

| 框架 | 它是什么 | 顶级操作员怎么用 | **FlagHunter 落点** |
|---|---|---|---|
| **MITRE ATT&CK**(14 战术矩阵:Recon→…→Impact;技术有稳定 ID 如 `T1190`) | 对手**行为**的知识库(战术=why,技术=how),不是攻击流程,是攻防共用语言 | 当**覆盖图 + 计划清单**:挑战术、选技术、按真实威胁组仿真;发现映射到技术 ID,报告可机读、缺口可见 | **每个动作/发现打 `technique_id`**:黑板上动作=已知过程的词汇表;控制器按战术覆盖度评分;天然支持报告。CTF 裁剪到 web/host 相关技术 |
| **Lockheed Cyber Kill Chain**(7 阶段) | 入侵=链,断任一环即可挫败;军事 doctrine | 高层叙事弧;防御者把控制点映到各阶段 | **仅作人类可读进度摘要**——它太线性、偏外围/恶意载荷,post-compromise 全塞进一个框,不适合会 pivot 的 agent |
| **Unified Kill Chain**(Pols,18 阶段=In 8/Through 6/Out 4) | Kill Chain × ATT&CK 的混合,显式建模"in→through→out"**循环**(可重入 recon/escalate) | 跨"外部突破+内部传播"的**有状态战役地图** | **顶层状态机**:用 In→Through→Out 三超态做状态机,ATT&CK 技术做态内转移;**建模成循环图不是直线**(pivot 后在新位点重入 Discovery)。契合 CTF 链:foothold→内部枚举→提权→loot |
| **Diamond Model**(Adversary/Capability/Infrastructure/Victim 四顶点 + pivot) | 入侵的**关系 schema**:知一顶点可 pivot 出其余 | 随证据填充,跨顶点 pivot 扩展认知 | **黑板实体 schema**:Victim(目标主机/服务/攻击面)、Capability(持有的 exploit/技术)、Infrastructure(回连/listener)、Adversary(agent 自身/仿真画像)。**pivot 语义=发现新 capability/infra 触发跨顶点扩展查询**。比 ad-hoc notes 干净,对齐 ShadowGraph |
| **PTES**(7 阶段:pre-engagement→…→reporting) | 交战**流程标准**(治理+技术);ATT&CK 描述行为,PTES 描述工作流与交付物 | **生命周期/阶段门**:威胁建模前不 exploit、不越 scope、必出结构化报告 | **守卫 + 计划先验**:pre-engagement scope=**一等公民硬门**(越界直接拒);阶段顺序=planner 先验(确认 foothold 才 post-ex)。**正好对应双模:渗透保守模式严守 PTES 门,CTF 激进模式压缩门去抢最短 flag 链** |
| **OWASP WSTG**(web 测试方法:INFO/CONF/ATHN/ATHZ/SESS/INPV/BUSL/CLNT…) | web 攻击面的**可重复清单方法** | 按类别走清单,逐项映射 WSTG ID + OWASP Top 10 | **web 域覆盖清单**:driver 把 WebChain worker 跑遍 WSTG 类别。**直击本项目"能力写好却够不着"缺口**(如 SQLi 能力 web 链从不触发)——清单强制每个面都被尝试 |

**综合落点**:状态机用 UKC 超态(循环)、动作/覆盖评分用 ATT&CK 技术 ID、黑板 schema+pivot 用 Diamond、生命周期+安全门用 PTES、web 覆盖用 WSTG。控制器在**覆盖度**上规划(ATT&CK)、在**状态**上推进(UKC)、在**知识**上推理(Diamond)、在**流程/合规**内行动(PTES)。

---

## 3. 顶级红队的思维模型 (mindset)

### 3.1 "防御者想清单,攻击者想图"(John Lambert, Microsoft)
核心心法:**环境是图,目标是节点,"下一步做什么"=一次最短路径查询,不是走清单**。BloodHound 把这点工程化("Six Degrees of Domain Admin"):AD 对象=节点,权限/关系=边,计算从已控节点到高价值目标(如 Domain Admin)的最短路径——能找出手工枚举永远发现不了的、穿过嵌套组/ACL 链/信任关系的攻击路径。防御者用同一张图找并切断高影响边(**咽喉点 / choke point**)。

→ **FlagHunter**:把 ShadowGraph 升级为真正的**攻击路径图引擎**——把 **flag/目标设为图节点**,把"已知事实→利用点→权限/秘密→flag"建成边,"下一步"=对该图的 pathfinding(BloodHound 用 Dijkstra 最短路),而非按 `_WEB_STRATEGY_ORDER` 走固定清单。报告时识别 **chokepoint**(切断能斩断最多路径的那条边)= 最高价值修复点。

### 3.1b 攻击树:给边打分,查"最便宜的攻击"(Schneier)
攻击树是图思维的形式化祖先:**根=攻击者目标,叶=具体步骤**,子节点按 OR(多条替代路)/AND(必须都成)组合,**叶子标注 cost/成功概率/难度/耗时/是否需特殊条件**,数值**传播到根**,于是可查询"最便宜的攻击""无需特殊条件的最便宜攻击"。这是"最弱链/最短路径"推理的形式化。

→ **FlagHunter**:给攻击路径图每条候选边**标 cost/likelihood/难度/noise**,传播到目标节点,控制器优先**最便宜、最少设防**的路径(Dijkstra 式)。**这正是"能力写好却够不着"缺口的原理级解法**——权重合理的图会把"被冷落的强能力"(如未接进 web 链的 SQLi)直接浮现为最便宜的边。

### 3.2 OODA 循环(Observe-Orient-Decide-Act, John Boyd)
红队靠**比防御者更快地转 OODA 环**取得节奏优势。这正是 agent 控制器该实现的 tempo:每轮 observe(工具回显)→orient(更新黑板/假设)→decide(选最高价值动作)→act(最小实验),且每轮都缩小不确定性。

→ **FlagHunter**:控制器 = OODA 环;`AgentSession`/`EventBus` 已提供 observe(事件)与 act(工具)的统一通道,orient/decide 落在黑板 + 假设引擎 + 覆盖评分。

### 3.3 assume-breach / 目标优先 / 弱链组合
顶级红队与单纯 pentest 的区别:不是"找尽量多漏洞",而是**达成目标 / 仿真特定威胁组 / 检验检测与响应**。思维是**目标优先**(盯着目标节点,顺着信任关系走)、**弱链组合**(把多个低危串成高影响)、**最弱环**。

→ **FlagHunter**:控制器评分要带 `path_shortening_bonus`(向目标节点靠近的动作优先),并显式支持"低危事实组合成链"(Diamond pivot + 路径图)。

### 3.4 假设驱动 + 紫队反馈
操作员同时维护多个带证据/置信度/最小实验/失败排除意义的假设;紫队把攻防反馈互相喂养。

→ **FlagHunter**:`HypothesisEngine` 已是雏形;补"失败→排除什么"的负向信号入黑板(见 §5 failure-as-knowledge)。

### 3.5 pentest ≠ red team(目标导向 + assume-breach)
pentest = 广度,尽量枚举并利用更多漏洞,findings 给系统 owner,透明执行;**red team = 目标导向的隐蔽交战**,测/量/改进人-流程-技术,defender 不知情,findings 给 Blue/SOC,核心是**威胁仿真**(用某威胁组的 TTP 来度量与训练检测响应)。Zenko 把红队定义为**"有组织的刻意自我批判 + 像敌人一样思考"**。assume-breach(Microsoft Zero Trust 三原则之一)= 假设攻击者已在内部,控制重心从"防"转向"限制爆炸半径 + 快速检测响应"。

### 3.6 OPSEC 当成"代价维度",紫队反馈做自我改进
- **OPSEC = 边权里的 noise/可检测性维度**,不是单独模式:每条边除 cost 外还带"会产生什么遥测/多大概率被抓"。于是行为可配置——**CTF 吵闹快、检测验证型交战安静慎**。好操作员"行动前先预测该动作产生的遥测"。
- **紫队反馈环**(Orchilles PTEF):"offense informs defense informs defense informs offense"。→ 把每次结果(哪条 TTP/边奏效、哪条被检测/失败)**回灌图权重与 planner**,让 agent 的启发式跨 run 自我改进(对应已有 pheromone/strategy_memory 基建)。

---

## 4. 顶级红队"拥有什么" (arsenal) → 我们的对应与缺口

| 顶级红队拥有 | 作用 | **FlagHunter 对应 / 缺口** |
|---|---|---|
| **C2 框架**(Cobalt Strike/Mythic/Sliver/Havoc/Metasploit) + 基础设施(redirector/OPSEC) | post-access 控制面:beacon 心跳、tasking、post-ex 模块;capability 只有挺过检测才有用 | CTF 无需真 C2,但要**post-foothold 的受管 tasking 抽象**:已建立访问→枚举→pivot 的状态与证据跨步持久,而非一次性散落 shell |
| **BloodHound/SharpHound** 攻击图引擎(Neo4j;最短路径到 DA;ADCS 边) | 图思维工程化:pathfinding 取代清单 | **ShadowGraph 升级为攻击路径图**(§3.1)。这是最高价值升级 |
| **ATT&CK 映射的 TTP 库** | 行动空间=已知过程词汇表;覆盖可审计;报告可机读 | playbooks/ + RAG 已有底座;**缺**:技术 ID 标注 + 检索式 TTP 库 |
| **CALDERA**(基于 ATT&CK 的自动对手仿真:server+agent 跑"abilities",每个 ability 绑技术)、**Atomic Red Team** | 把方法论编码成可组合的 ability,agent 选链而非临场造原语 | **`StrategyRegistry` 正是 ability 注册表雏形**——给每条 strategy 标 ATT&CK/WSTG ID 即升级为对手仿真剧本库 |
| **漏斗式 recon 流水线**(reconFTW:被动→liveness→服务识别→签名扫→人工验证) | 单一职责工具串联,结果可重复 | tools/ 已有 nmap/nuclei/httpx/katana 等;**缺**:编排成漏斗式可重复 pipeline(而非脆弱一次性链) |
| **全量 operator ledger**(逐动作时间戳:命令/目标/参数/原始输出/推断) | 顶级团队的标志性产物:可复现叙事的原料;deconfliction;报告 | `SessionLedger` 是底座;**缺口**:notes 只存**精选发现**,需补**全量动作日志**(不只成功) |
| **交战纪律**(scope/RoE/deconfliction/stop 条件/证据追踪/报告标准) | 把"做了点事"变成"用这些证据证明了这条路径,这样复现与修复" | scope gate + 双模已有雏形;补证据等级与 replay |

---

## 5. 自主 AI 攻防 agent 的实证教训(必须设计进去)

来自 DARPA CGC/AIxCC、PentestGPT、"LLM 自主利用 one-day"、HPTSA、Cybench/NYU CTF 的交叉结论:

1. **验证优先(proof-or-it-didn't-happen)** —— **头号教训**。AIxCC 中 **~38–46% 通过全部自动校验的补丁含语义缺陷**(只压症状),仅人工复核才抓出;LLM agent 普遍产出"看似对实则错"的幻觉发现。
   → **Validation Agent 做硬门**:无再执行的证据不得以"confirmed"入黑板——CTF 要 flag 串,渗透要可复现副作用。对应我们 `CTFVerifier`,需上升为强制 gate + 证据等级。
2. **黑板要 cross-feed,连失败一起** —— AIxCC 最强系统显式**在组件间共享 fuzzer 种子、崩溃/sanitizer 报告、失败反馈**。这是最贴合 FlagHunter 的架构杠杆。
   → 确保**失败被记录并回流**(不只成功);pheromone/ShadowGraph 是对的底座。
3. **planner + 专精执行体** —— HPTSA、D-CIPHER 证明角色专精(分析/web/shell/编程 + 验证)胜过单体,且隔离 context 防 recon 发现被裁掉。
   → 保留 crew 分解;web/xss/sqli 等 specialist 各管自己领域假设。
4. **持久攻击路径记忆** —— **文档记载的头号失败:忘记 recon、A 服务找到漏洞却链不到 B**。
   → 这正是我们台账里"能力写好却够不着"(SQLi 没接进 web 链)的根因。需**显式攻击路径/状态对象 + 每步检索**,而非只存原始 notes。
5. **失败反思(Reflexion)** —— dead-end 后写结构化 post-mortem 入记忆喂回 planner,打断 loop-and-retry。
6. **工程鲁棒性 > 更聪明的 prompt** —— AIxCC 赢家靠 uptime/robustness 拉开差距;一半漏洞 baseline 本可解却因 build/调度崩溃漏掉。
7. **run-to-run 方差大** —— 同 agent 同目标 400 次跑结果差异巨大。单次"解出"不算能力证明。
   → 评测报 **pass@k / 方差**,别拿单次 happy path 当结论(呼应我们 live 测试的可复现纪律)。
8. **自主度校准(HaCRS:在难/高风险步增强自主,而非全自主)**:
   - **可激进**:recon、枚举、**有客观 oracle 的 CTF flag 捕获**、已知类漏洞(给了 CVE/指纹时 one-day 成功率 87% vs 无 grounding 7%)。
   - **需 gate**:新颖 exploit 链、任何无复现的"成功"、真目标上的破坏性动作、最终 finding/补丁签收。
   → 正好对应双模:CTF 激进走最短**已验证**链;渗透先确认再动。

---

## 6. 映射到 FlagHunter 当前骨架(已落地 + 缺口)

本会话已完成的架构骨架(P0–P4)正好是承接以上的底座:

| 现有组件 | 现状 | 升级方向(本文驱动) |
|---|---|---|
| `AgentSession` + 中立 `EventBus`(P1) | 统一装配 + 单一事件源 | observe/act 通道 = OODA 环的 I/O 层;事件可作 cross-feed 总线 |
| `blackboard_lite` / `knowledge/blackboard` | 入口投影 + planner 读视图 | 升级为 **Diamond schema 实体图 + ATT&CK 标签**;失败入黑板 |
| `ShadowGraph` | notes 派生的知识图雏形 | 升级为 **BloodHound 式攻击路径图**(flag=节点,pathfinding) |
| `StrategyRegistry` + `chains/`(P3a/P4) | dict 分发 + mixin 拆分,precondition 门控 | 每条 strategy 标 **ATT&CK/WSTG ID** → CALDERA 式 ability 库;WSTG 清单强制覆盖 |
| `CTFVerifier` | flag 验证雏形 | 升级为 **Validation Agent 硬门 + 证据等级**(candidate/observed/runtime/verified/rejected) |
| `SessionLedger` / `CheckpointStore` / `ArtifactRegistry` | 探索历史 + 恢复点 + artifact | 补**全量动作 ledger** → 可复现叙事 + replay |
| `HypothesisEngine` | 假设生成雏形 | 补假设的证据/置信/最小实验/**失败排除意义**(负向信号) |
| `CTFCoordinator` / `_execute_chain`(P3a dict 分发) | 主控 + chain 路由 | 升级为**覆盖度/路径缩短驱动的 OODA 控制器**(评分见 V1 §6.3) |
| 双攻击模式(CTF 激进 / 渗透保守) | 已有 exploitation_mode | 对接 PTES 阶段门 + 自主度校准(§5.8) |

---

## 7. 修订后的优化路线(在已落地骨架上继续)

承接 P0–P4 的"自顶向下"成果,框架基础优化的下一批(按价值/风险排序):

1. **黑板对象模型最小化 + Diamond schema + ATT&CK 标签**(V1 §13.1 的对象,叠加技术 ID 与四顶点)。验收:每个控制决策可追溯到 facts/hypotheses;每个工具调用可追溯到 experiment 且带 technique_id。
2. **Validation gate 上升为一等公民**(§5.1)。验收:candidate 不直接变 verified;flag/exploit 必过 Validation;失败写成 dead-end。
3. **攻击路径图引擎 + 边打分**(§3.1/§3.1b,ShadowGraph 升级)。边带 cost/likelihood/难度/noise 权重,Dijkstra 式最短路。验收:输出当前最短候选路径 + 缺哪条证据 + minimal replay chain + chokepoint。
4. **覆盖度驱动控制器**(ATT&CK 战术覆盖 + WSTG web 清单 + path_shortening_bonus)。验收:控制器不再只按固定 chain 顺序;能解释为何选此动作;**WSTG 清单确保每个 web 面都被尝试(关掉"够不着"缺口的根因)**。
5. **failure-as-knowledge + Reflexion**(§5.2/§5.5):失败→负向信号/dead-end/post-mortem 入黑板回流。
6. **全量 operator ledger + pass@k 评测**(§4/§5.7):动作全量日志;能力以多次跑的 pass@k/方差度量,接 Cybench/NYU CTF 式 benchmark。
7. **recon 漏斗 pipeline 化**(§4):被动→liveness→服务识别→签名扫→人工/agent 验证,可重复编排。

---

## 8. 硬性工程约束(纳入开发纪律)

> - 新增能力/策略必须标 **ATT&CK(+WSTG)技术 ID**,写入黑板对象。
> - 每次 tool call 绑 experiment、experiment 绑 hypothesis、hypothesis 绑 evidence;**全量进 ledger**(成功与失败都记)。
> - **无再执行证据不得标 verified**;flag/exploit 必过 Validation gate。
> - **失败必须变知识**(dead-end / refuting evidence / boundary fact),回流黑板。
> - 攻击路径图持续维护:result 写 produces/enables/refutes 边;PathFinder 出最短路径。
> - scope/RoE 为硬门,高风险动作 gate;CTF 激进走最短**已验证**链,渗透先确认再动。
> - 入口不绕过 `AgentSession`/`EventBus`(已立);chain 继续按 mixin 模块化拆分(P4)。
> - 能力以 **pass@k / 方差**度量,拒绝单次 happy path 当结论。

---

## 9. 一句话浓缩

> 顶级红队的本质 = **图式规划(攻击路径而非清单)+ ATT&CK 映射的可复用知识 + 强迫式全量日志→可复现叙事**;
> 顶级自主 agent 的本质 = **验证优先 + cross-feed 黑板 + 持久攻击路径记忆 + 失败反思 + 工程鲁棒**。
> FlagHunter 的边际优势,不在更聪明的 prompt 或更多 exploit,而在**把这两组心法做成骨架级的硬约束**——这正是本版要把项目"打到顶级、打好基础"的方向。

---

## 10. 参考来源

**框架**
- MITRE ATT&CK Enterprise Tactics — https://attack.mitre.org/tactics/enterprise/
- Lockheed Martin Cyber Kill Chain — https://www.lockheedmartin.com/en-us/capabilities/cyber/cyber-kill-chain.html
- Unified Kill Chain (Pols) — https://www.unifiedkillchain.com/ · 白皮书 https://www.unifiedkillchain.com/assets/The-Unified-Kill-Chain.pdf
- Diamond Model of Intrusion Analysis — https://www.activeresponse.org/the-diamond-model/
- PTES — http://www.pentest-standard.org/index.php/Main_Page
- OWASP WSTG — https://owasp.org/www-project-web-security-testing-guide/

**武器库 / 战术**
- BloodHound (SpecterOps) — https://github.com/specterops/bloodhound · Cypher https://bloodhound.specterops.io/analyze-data/explore/cypher-search
- ADCS Attack Paths in BloodHound — https://posts.specterops.io/adcs-attack-paths-in-bloodhound-part-1-799f3d3b03cf
- Bishop Fox — 2025 Red Team Tools & C2 — https://bishopfox.com/blog/2025-red-team-tools-c2-frameworks-active-directory-network-exploitation
- MITRE CALDERA — https://github.com/apache/caldera · Atomic Red Team — Red Canary
- reconFTW 方法论 — https://starlog.is/articles/cybersecurity/six2dez-reconftw/
- 交战 RoE — https://blog.securelayer7.net/red-team-rules-of-engagement/

**思维模型(mindset)**
- John Lambert "Defenders think in lists, attackers think in graphs" — https://learn.microsoft.com/en-us/archive/blogs/johnla/defenders-think-in-lists-attackers-think-in-graphs-as-long-as-this-is-true-attackers-win
- Schneier 攻击树 — https://www.schneier.com/academic/archives/1999/12/attack_trees.html
- BloodHound 起源 / 派生管理员 / Attack Path Management(chokepoint) — https://wald0.com/?p=68 · https://specterops.io/blog/2021/05/25/the-attack-path-management-manifesto/
- OODA(Boyd)与红队 — https://library.mosse-institute.com/articles/2022/02/what-is-the-ooda-loop-and-why-is-it-relevant-to-red-teaming/ · SANS WP 35990
- assume-breach / Zero Trust — https://learn.microsoft.com/en-us/security/zero-trust/zero-trust-overview · NIST SP 800-207
- Zenko《Red Team》 — https://education.cfr.org/teach/book-guide/red-team-how-succeed-thinking-enemy
- pentest→red→purple(SANS)/ PTEF(Orchilles) — https://www.sans.org/blog/shifting-from-penetration-testing-to-red-team-and-purple-team
- 假设驱动狩猎(SANS, Lee & Bianco)— https://www.sans.org/white-papers/37172
- OPSEC/tradecraft 思维(SpecterOps)— https://specterops.io/blog/2023/09/19/reactive-progress-and-tradecraft-innovation/

> 取证留痕:以上若干"行业惯用对立"(emulation vs simulation、"chain low into critical"、"weakest link")属厂商/转述措辞,非 MITRE/OWASP/Zenko 原文逐字定义;采纳其工程含义而非当作权威引文。

**自主 AI 攻防 agent**
- DARPA CGC — https://www.darpa.mil/research/programs/cyber-grand-challenge · CRS 综述 arXiv:1702.06162 · HaCRS arXiv:1708.02749
- DARPA AIxCC 结果 — https://www.darpa.mil/news/2025/aixcc-results · SoK arXiv:2602.07666
- PentestGPT (USENIX Sec 2024) — https://www.usenix.org/system/files/usenixsecurity24-deng.pdf
- LLM 自主利用 one-day (Kang et al.) — arXiv:2404.08144 · HPTSA arXiv:2406.01637 · D-CIPHER arXiv:2502.10931
- Cybench — https://cybench.github.io/ · NYU CTF Bench — https://nyu-llm-ctf.github.io/
- Google Big Sleep — https://blog.google/innovation-and-ai/technology/safety-security/cybersecurity-updates-summer-2025/

相关:[[project-topdown-architecture]] [[project-web-chain-reachability-sqli]] [[project-ctf-mode]] [[project-exploitation-modes-antcolony]]
