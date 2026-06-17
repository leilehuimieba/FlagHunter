# FlagHunter Label Strategy

> 适用于 `D:\webstudy\FlagHunter` 当前私有仓库。目标是让 Issue / PR 在**私有协作场景**下也能快速分流、检索与回顾。

---

## 1. 设计目标

当前标签体系只追求三件事：

1. **快速分流**：一眼看出这是 bug、功能、文档还是发版事项
2. **快速定位**：一眼看出它主要落在哪个模块域
3. **快速决策**：一眼看出是否需要优先处理、是否需要发布说明

不追求一次性建出非常复杂的标签矩阵，避免标签过多反而失效。

---

## 2. 标签分层

建议分成三层使用：

### 2.1 类型层（What is it）

用于表达事项本质：

- `bug`
- `enhancement`
- `documentation`
- `release`
- `security`

### 2.2 领域层（Where does it belong）

用于表达主要影响面：

- `ui`
- `backend`
- `agent-runtime`
- `ctf`
- `dependencies`

### 2.3 状态 / 决策层（What should we do with it）

用于表达处理动作或风险提示：

- `needs-triage`
- `breaking-change`

---

## 3. 当前推荐标签集

| 标签 | 用途 | 何时使用 |
|------|------|----------|
| `bug` | 缺陷 / 回归 | 行为不符合预期、已有能力失效 |
| `enhancement` | 能力增强 | 新功能、增强改造、工作流完善 |
| `documentation` | 文档相关 | README、指南、模板、说明更新 |
| `release` | 发布相关 | 发版准备、tag、release note、版本同步 |
| `security` | 安全边界 | 敏感内容、授权边界、风险控制、凭据处理 |
| `ui` | 界面层 | TUI / Web / 展示层 / 交互改动 |
| `backend` | 后端逻辑 | 服务逻辑、数据流、配置、生效链路 |
| `agent-runtime` | Agent 运行时 | loop、memory、tool execution、state 管理 |
| `ctf` | CTF 专项 | Web/Crypto/Reverse/Pwn/Misc/solver 工作流 |
| `dependencies` | 依赖更新 | Python 包、镜像、工具链版本更新 |
| `needs-triage` | 待分流 | 刚进入仓库、还没明确归类或优先级 |
| `breaking-change` | 兼容性提醒 | 行为、配置、接口、协作方式发生不兼容变化 |

---

## 4. 推荐使用规则

### Issue

每个 Issue 建议至少包含：

- **1 个类型层标签**
- **0~2 个领域层标签**
- 如未分析清楚，再补 **`needs-triage`**

示例：

- “前端对话区太窄，需要重构布局”  
  → `enhancement` + `ui`
- “MCP server 某工具调用结果丢失”  
  → `bug` + `backend` + `agent-runtime`
- “准备 v0.1.1 release 并同步 changelog”  
  → `release` + `documentation`

### Pull Request

每个 PR 建议至少包含：

- **1 个类型层标签**
- **1 个领域层标签（如适用）**
- 若需要在 release note 中重点说明，再补：
  - `release`
  - `breaking-change`

---

## 5. 不建议的做法

以下做法当前不建议采用：

- 一次性创建几十个低频标签
- 用标签代替 issue 标题或正文
- 把优先级、模块、状态、负责人全部压到标签里
- 同一个 PR 打上 6~10 个标签，导致失去识别价值

---

## 6. 最小执行约束

为保持体系长期可用，建议至少遵守：

- 新建 issue 时先判断是否需要 `needs-triage`
- 文档 / README / release 工作，优先补 `documentation` 或 `release`
- 只要涉及兼容性风险，就显式打上 `breaking-change`
- 涉及敏感内容、凭据、授权边界、误公开风险时，显式打上 `security`

---

## 7. 与当前仓库策略的关系

本文件默认建立在以下前提之上：

- 仓库继续保持 **Private**
- 当前对外品牌为 **FlagHunter**
- Python 包与命令统一为 `flaghunter`（历史 `PENTESTAGENT_*` 环境变量仍作兼容别名）

如果未来协作者数量明显增加，再考虑引入：

- 优先级标签（如 `priority:high`）
- 工作流标签（如 `blocked`、`ready`）
- 模块更细粒度标签（如 `mcp`、`runtime`、`knowledge`）
