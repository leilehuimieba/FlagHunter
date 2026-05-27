# FlagHunter Web 可视化控制台 Stage V 执行计划 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 文档角色：**Stage V 当前执行文档**
- 适用范围：`web/console/`、`pentestagent/interface/web_server.py`、`docs/web-console/`
- 当前基线提交：`4de5e52` · `docs(web): archive stage iv acceptance handoff`

---

## 1. 本轮目标

在 Stage IV 已正式封存的前提下，执行一轮 **Stage V：收口回归 + 动作链验收**，把当前 Web Console 从“阶段性功能完成”推进到“可稳定交付、可继续开发的基线状态”。

本轮固定顺序：

1. **页面级回归**
2. **动作链验收**
3. **只修 P0 / P1 问题**
4. **合同 / 文档同步**
5. **Stage V 总验收归档**

---

## 2. 本轮非目标

以下内容不在本轮范围内：

1. 不回头重构 Stage I ~ Stage IV 已验收页面
2. 不进行 Web Console 技术栈迁移
3. 不引入新的状态管理框架或通用 abstraction layer
4. 不做大规模 event / schema 重写
5. 不因局部优化冲动扩展为新功能开发轮次

---

## 3. 执行模式

- 执行模式：**single-owner**
- 原因：
  1. 当前任务是一条连续主线：回归 → 修补 → 复验 → 归档
  2. 页面与后端接口、SSE 事件、高频 UI 状态强耦合
  3. 并行拆分会增加同步成本，不利于快速定位回归

---

## 4. 任务拆分

### 4.1 Task A：页面级回归

按顺序回归以下页面：

1. Dashboard
2. Tasks（list / detail）
3. Traces（list / detail）
4. Knowledge（list / detail）
5. Logs
6. Settings

每页至少检查：

- 真数据加载是否正常
- 空态是否正常
- 切页是否报错
- console 是否出现 error / warn
- 是否仍依赖 mock 专属字段

#### 本任务产物

- `FlagHunter_Web可视化控制台_StageV_首轮页面级回归验证证据_V1.json`

---

### 4.2 Task B：动作链验收

优先验证现有已落地动作合同：

1. **创建任务**
2. **running task live 观察**
3. **hint 注入**
4. **stop**
5. **成功 run 回放**

说明：

- `retry` 不作为本轮第一优先级硬门槛
- 若当前实现已存在 retry 能力，则顺手纳入验收；若没有，则只记录为缺口，不扩 scope 现补

#### 本任务通过标准

至少形成一条完整真实链路：

- create → run → observe → hint / stop → trace replay

#### 本任务产物

- `FlagHunter_Web可视化控制台_StageV_动作链验收验证证据_V1.json`

---

### 4.3 Task C：P0 / P1 修补

只允许修补以下问题：

- 页面报错 / 崩溃
- 接口字段不一致
- 状态不同步
- 空态 / 异常态崩溃
- live 事件消费断链

不允许顺手做：

- UI 大改
- 通用重构
- 新功能铺设
- 大范围样式改造

---

### 4.4 Task D：合同 / 文档同步

同步以下文档：

1. `FlagHunter_Web可视化控制台_前后端联调与验收清单_V1.md`
2. `FlagHunter_Web可视化控制台_规划文档收口映射_V1.md`
3. Stage V 过程文档与归档文档

目标：

- 文档结论与代码真相一致
- 不再出现“文档说未完成，代码已完成”的失配

---

### 4.5 Task E：Stage V 总验收归档

完成条件：

1. 页面级回归通过
2. 动作链验收通过
3. P0 问题归零
4. 文档与代码同步
5. 工作区清洁

#### 本任务产物

- `FlagHunter_Web可视化控制台_StageV_总验收归档与交接_V1.md`

---

## 5. 最小验收条

本轮最小 acceptance bar：

1. 六大主页面都能接真数据打开
2. 至少一个任务能从前端真实创建
3. 至少一个 running task 能被前端实时观察
4. 至少一个 hint 注入链路跑通
5. 至少一个成功 run 能在 Trace 页面完整回放
6. 无阻断级 P0 问题，console 无持续性 error / warn

满足以上 6 条即可判定：

> **Stage V 第一轮收口完成。**

---

## 6. 验证方式

### 6.1 接口级

- `GET /api/dashboard/summary`
- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{taskId}`
- `POST /api/tasks/{taskId}/hint`
- `POST /api/tasks/{taskId}/stop`
- `GET /api/traces`
- `GET /api/traces/{runId}`
- `GET /api/knowledge`
- `GET /api/knowledge/{docId}`
- `GET /api/logs`
- `GET /api/settings`
- `PUT /api/settings`（仅对白名单字段做可逆验证）

### 6.2 浏览器级

- 打开 6 大主页面
- 记录页面级空态 / 异常态 / console 情况
- 对动作链进行真实前端操作
- 对成功 run 做 trace replay spot-check

---

## 7. 提交与回滚

### 7.1 当前 safe rollback point

- `4de5e52` · `docs(web): archive stage iv acceptance handoff`

### 7.2 建议检查点

1. Stage V 执行计划文档落盘后
2. 页面级回归证据完成后
3. 动作链修补通过后
4. Stage V 总验收归档完成后

### 7.3 回滚纪律

- 若 Stage V 中途引入回归，优先回退到最近稳定 checkpoint
- 若回归来源不清，直接回退到 `4de5e52`，不要叠加脏修补

---

## 8. 临时文件策略

允许的临时文件：

- `tmp_web_console_stdout.log`
- `tmp_web_console_stderr.log`

规则：

1. 仅用于当前浏览器 / 接口回归
2. 每轮验证后清理
3. 不作为长期归档产物保留

---

## 9. 当前最小下一步

执行顺序已确定。当前直接开始：

1. 建立 `Stage V` 执行文档（本文件）
2. 进入 **Task A：页面级回归**
3. 先产出首轮页面级回归证据，再决定是否进入动作链验收
