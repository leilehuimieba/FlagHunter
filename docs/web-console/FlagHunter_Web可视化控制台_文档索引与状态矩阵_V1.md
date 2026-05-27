# FlagHunter Web 可视化控制台 文档索引与状态矩阵 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 文档角色：**文档导航 / source-of-truth 判定矩阵**
- 用途：明确 `docs/web-console/` 下每份文档当前属于“有效事实”“历史快照”“规划参考”还是“证据文件”

---

## 1. 使用规则

默认按下面优先级阅读：

1. **当前有效主文档**
2. **当前状态矩阵 / 规划映射**
3. **阶段状态卡 / 阶段总验收**
4. **验证证据 JSON**
5. **规划 / 草案 / 任务拆分文档**

### 关键规则

- 不要把“首轮复核文档”当作“当前最终状态”
- 不要把“规划文档中的推荐技术栈”当作“当前实际代码实现”
- 若文档之间冲突，以 **当前有效主文档 + 当前代码 + 最新提交状态** 为准

---

## 2. 状态矩阵

| 文档 | 角色 | 当前是否有效 | 是否历史快照 | 是否需维护 | 备注 |
|---|---|---|---|---|---|
| `FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md` | current | **是** | 否 | 是 | 当前可用性主文档 / 使用边界 source of truth |
| `FlagHunter_Web可视化控制台_StageV_总验收归档与交接_V1.md` | current | **是** | 否 | 是 | 当前阶段总验收主文档 |
| `FlagHunter_Web可视化控制台_StageI~III_总验收归档与交接_V2.md` | historical-baseline | 是 | **是** | 低频 | Stage I~III 基线交接文档，供历史恢复参考 |
| `FlagHunter_Web可视化控制台_文档索引与状态矩阵_V1.md` | current | **是** | 否 | 是 | 当前文档导航入口 |
| `FlagHunter_Web可视化控制台_规划文档收口映射_V1.md` | current | **是** | 否 | 是 | 规划文档与当前实现的桥接文档 |
| `FlagHunter_Web可视化控制台_StageI~III_总验收归档与交接_V1.md` | historical | 否 | **是** | 否 | 清理与提交前的快照，已被 V2 替代 |
| `FlagHunter_Web可视化控制台_StageIII_第二轮状态卡_V1.md` | stage-final | 是 | 部分 | 低频 | Stage III 真流验收结果，仍有证据价值 |
| `FlagHunter_Web可视化控制台_StageIII_首轮复核验收与交接_V1.md` | historical | 否 | **是** | 否 | 仅描述“首轮复核当时”的事实 |
| `FlagHunter_Web可视化控制台_StageIII_首轮状态卡_V1.md` | historical | 否 | **是** | 否 | 首轮状态快照 |
| `FlagHunter_Web可视化控制台_StageII_总验收归档_V1.md` | historical-baseline | 是 | **是** | 低频 | Stage II 基线文档，后续仅做参考 |
| `FlagHunter_Web可视化控制台_StageII_首轮状态卡_V1.md` | historical | 否 | **是** | 否 | 首轮联调快照 |
| `FlagHunter_Web可视化控制台_StageII_第二轮状态卡_V1.md` | historical | 否 | **是** | 否 | 第二轮真实化收口快照 |
| `FlagHunter_Web可视化控制台_StageI_收口状态卡_V1.md` | historical-baseline | 是 | **是** | 低频 | Stage I 基线文档 |
| `FlagHunter_Web可视化控制台_StageI_首轮浏览器联调证据_V1.json` | evidence | 是 | 是 | 否 | Stage I 证据文件 |
| `FlagHunter_Web可视化控制台_StageI_尾巴复验证据_V1.json` | evidence | 是 | 是 | 否 | Stage I 尾巴复验证据 |
| `FlagHunter_Web可视化控制台_StageII_首轮修补复验证据_V1.json` | evidence | 是 | 是 | 否 | Stage II 证据文件 |
| `FlagHunter_Web可视化控制台_StageII_第二轮验证证据_V1.json` | evidence | 是 | 是 | 否 | Stage II 证据文件 |
| `FlagHunter_Web可视化控制台_StageIII_首轮验证证据_V1.json` | evidence | 是 | 是 | 否 | Stage III 首轮证据 |
| `FlagHunter_Web可视化控制台_StageIII_第二轮验证证据_V1.json` | evidence | 是 | 是 | 否 | Stage III 第二轮真流证据 |
| `FlagHunter_Web可视化控制台_StageIV_总验收归档与交接_V1.md` | historical-baseline | 是 | **是** | 低频 | Stage IV 基线文档，后续仅做参考 |
| `FlagHunter_Web可视化控制台_StageV_首轮页面级回归验证证据_V1.json` | evidence | 是 | 是 | 否 | Stage V Task A 页面级回归证据 |
| `FlagHunter_Web可视化控制台_StageV_动作链验收验证证据_V1.json` | evidence | 是 | 是 | 否 | Stage V Task B 动作链证据 |
| `FlagHunter_Web可视化控制台_当前可用性Smoke验证证据_V1.json` | evidence | 是 | 是 | 否 | post-Stage-V 当前可用性 smoke 证据 |
| `FlagHunter_Web可视化控制台建设计划书_V1.md` | planning | 否 | 否 | 否 | 初始规划，描述建设愿景，不代表当前实现 |
| `FlagHunter_Web可视化控制台_信息架构与API事件草案_V1.md` | planning/reference | 否 | 否 | 低频 | 参考合同文档，部分已实现，部分已偏离 |
| `FlagHunter_Web可视化控制台_前端原型拆解与组件树规范_V1.md` | planning/reference | 否 | 否 | 低频 | 原型设计参考，不是当前代码结构真相 |
| `FlagHunter_Web可视化控制台_前端开发任务拆分清单_V1.md` | planning | 否 | 否 | 低频 | 前端推荐执行方案，需要配合“规划映射”阅读 |
| `FlagHunter_Web可视化控制台_后端适配任务清单_V1.md` | planning | 否 | 否 | 低频 | 后端推荐执行方案，需要配合“规划映射”阅读 |
| `FlagHunter_Web可视化控制台_前后端联调与验收清单_V1.md` | planning/checklist | 否 | 否 | 低频 | 联调 checklist，部分已完成，部分自然失效 |

---

## 3. 当前 source of truth 组合

如果只允许看 3 份文档，优先看：

1. `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
2. `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageV_总验收归档与交接_V1.md`
3. `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_文档索引与状态矩阵_V1.md`

如果需要证据，再补看：

4. `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性Smoke验证证据_V1.json`

---

## 4. 读文档的推荐顺序

### 场景 A：我要恢复当前项目状态

按顺序读：

1. `当前可用性收口与使用边界_V1`
2. `StageV_总验收归档与交接_V1`
3. `文档索引与状态矩阵_V1`

### 场景 B：我要看阶段证据

按顺序读：

1. `当前可用性Smoke验证证据_V1.json`
2. `StageV_动作链验收验证证据_V1.json`
3. `StageV_首轮页面级回归验证证据_V1.json`
4. `StageIV_总验收归档与交接_V1.md`

### 场景 C：我要看最初是怎么规划的

按顺序读：

1. `建设计划书_V1`
2. `信息架构与API事件草案_V1`
3. `前端开发任务拆分清单_V1`
4. `后端适配任务清单_V1`
5. 同时必须对照 `规划文档收口映射_V1`

---

## 5. 一句话说明

> **以后任何“当前事实判断”都不要单独依赖 planning 文档或历史阶段快照，应先看“当前可用性收口与使用边界 V1”与 Stage V 总验收文档，再用本矩阵判断哪些文档还有效。**
