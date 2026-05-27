# FlagHunter Web 可视化控制台 Stage IV · Settings 可写化状态卡 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 归属阶段：Stage IV / Milestone 1
- 结论：**已完成最小可写化闭环**

---

## 1. 本轮完成项

1. Settings 页面已从“Stage I 只读”切到“部分 live 写回”
2. 后端 `GET /api/settings` 已返回：
   - `meta.editablePaths`
   - `meta.restartRequiredPaths`
   - `meta.saveMode`
3. 后端 `PUT /api/settings` 已返回：
   - `saved`
   - `ignored`
   - `restartRequired`
   - `settings`
4. 前端已只开放本轮白名单字段，未支持字段保留为只读
5. `discard` 已回到最近一次后端状态，而不是回到 mock

---

## 2. 本轮验证结论

### 2.1 接口级

- `GET /api/settings` 返回 `meta` 与当前值
- `PUT /api/settings` 写回后，再次 `GET` 能读回
- no-op `PUT` 返回：
  - `saved = []`
  - `ignored = []`
  - `restartRequired = []`

### 2.2 浏览器级

- live 模式打开 `#/settings` 无报错
- 页面顶部文案已变为“部分 live 写回”
- 只读字段展示为 disabled / read-only
- 可写字段修改后，保存按钮可用
- 保存后刷新页面，值可读回

---

## 3. 本轮验证过的真实字段

本轮至少验证过以下字段的写回与恢复：

1. `runtime.workdir`
2. `budget.alertAt`
3. `ctf.autoRetry`

验证过程中：

- 先写入临时值确认保存与刷新生效
- 随后恢复为原值
- 当前 `.env` 已恢复到验证前状态

---

## 4. 当前残余边界

1. 当前仍是**部分可写**，不是全量可写
2. `model.temperature / model.maxTokens / runtime.mode / mcp.* / audit.* / knowledge.threshold` 等仍保持只读
3. 部分可写字段虽已落盘，但仍属于“可能需重启才完全生效”的配置

---

## 5. 下一步建议

Milestone 1 已可视为完成。  
建议直接进入 Stage IV / Milestone 2：

- **Trace Graph 真图化**

