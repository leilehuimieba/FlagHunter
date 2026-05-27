# FlagHunter Web 可视化控制台 Stage IV 执行计划 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 文档角色：**Stage IV 当前执行文档**
- 适用范围：`web/console/` 与 `pentestagent/interface/web_server.py`

---

## 1. 本轮目标

在不重构 Web Console 架构的前提下，收掉 Stage I ~ III 后仍保留的“半真半 mock”能力，优先顺序固定为：

1. **Settings 可写化**
2. **Trace Graph 真图化**
3. **Task Detail 会话真实度增强**
4. **Knowledge usage 可视分析增强**

本轮先执行 **Milestone 1：Settings 可写化**。

---

## 2. 本轮非目标

以下内容不在本轮范围内：

1. 不改 Web Console 技术栈
2. 不把 Trace / Task / Knowledge 一起并行开工
3. 不为 Settings 引入复杂表单框架
4. 不承诺“所有 Settings 字段都立刻影响运行中 agent”
5. 不回头修改 Stage I ~ III 已归档文档的结论

---

## 3. Milestone 1 最小方案

### 3.1 目标

把 Settings 从“前端可编辑但实际只读”改为：

- **支持字段可真实写回 `.env`**
- **不支持字段保持只读并明确提示**
- **保存结果对用户可解释**

### 3.2 约束

1. 只做 `.env` / 当前配置可落盘字段
2. 不支持字段不得伪装成“已保存”
3. 保存后以 **GET → PUT → GET 一致** 为通过标准
4. 对可能需重启才能完全生效的字段，要在 UI 中明确标识

### 3.3 本轮代码边界

- 后端主改动：
  - `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
- 前端主改动：
  - `D:\webstudy\FlagHunter\web\console\src\pages\settings.jsx`
  - `D:\webstudy\FlagHunter\web\console\src\api.js`
  - `D:\webstudy\FlagHunter\web\console\src\components.jsx`
  - `D:\webstudy\FlagHunter\web\console\src\styles.css`
  - `D:\webstudy\FlagHunter\web\console\src\i18n.js`

---

## 4. Milestone 1 验收标准

满足以下最小标准即视为通过：

1. live 模式下 Settings 支持字段可以保存
2. 保存成功后刷新页面，值仍保持
3. 未支持字段不能编辑，或明确提示“不持久化”
4. 保存失败时有错误反馈
5. 页面不再显示 “Stage I：只读”

---

## 5. 验证方式

### 5.1 接口级

1. `GET /api/settings`
2. 修改支持字段后 `PUT /api/settings`
3. 再次 `GET /api/settings`
4. spot-check `.env` 对应键值变化

### 5.2 浏览器级

1. 打开 Settings 页面
2. 修改至少 3 个支持字段
3. 点击保存
4. 刷新后确认值保持
5. 确认只读字段仍不可编辑，且文案正确

---

## 6. 提交与回滚

- 当前 safe rollback point：
  - `188db71 docs(web): sync web console archive matrix and mapping`

建议在 Milestone 1 保留两个检查点：

1. Settings 前后端保存链路打通后提交一次
2. 浏览器级 live 验收通过后再提交一次

