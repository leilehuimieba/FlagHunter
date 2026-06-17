# Changelog

> Format and release discipline follow [docs/release-policy.md](./docs/release-policy.md).

本文件记录 `FlagHunter` 仓库在新项目阶段的关键版本与展示层收口动作。

---

## Unreleased

### Changed

- 将内部 Python 包与命令入口从历史名 `pentestagent` 正式重命名为 `flaghunter`
  （包目录、所有 import、`console_scripts` 命令、构建/CI/Docker/脚本同步）。
- 环境变量统一为 `FLAGHUNTER_*` 前缀；历史 `PENTESTAGENT_*` 名称在启动时自动别名为
  对应的 `FLAGHUNTER_*`，现有 `.env` 无需修改即可继续工作。
- 全量品牌清扫：代码、文档、提示词、TUI 横幅中的 `PentestAgent` 统一为 `FlagHunter`。

---

## v0.2.0 - 2026-06-09

围绕 live Web CTF 实战的通用能力增强与验证留痕版本。

### Added

- 新增 live CTF 能力与端到端测试台账，统一记录能力测试、E2E 结果、平台确认、暴露缺口、通用修复与回归验证。
- 新增多道 DASCTF 靶场做题 WP，沉淀 solved / partial solved 的实战过程与证据。
- 新增 `generic_param_sqli` 最小 eval pack，用于把真实题型经验下沉为稳定的本地策略级回归。

### Changed

- 补强通用 Web CTF 挑战恢复链路，强化调度收敛、候选链筛选与诚实停止行为。
- 将 `generic_param_sqli` 提升为更清晰的一等策略路径，使其能被 dispatcher / hypothesis / recovery 协同识别与推进。
- 改进上传题通用推进流程，使仅暴露登录/注册入口的目标更容易进入 post-auth upload 侦察与源码驱动利用阶段。

### Fixed

- 减少误把伪 backup/source 页面当作有效突破口的假阳性。
- 改进 `sqlmap` 未直接出 flag 时的 stacked-query 与轻量 HTTP fallback 行为。
- 修复 live 上传题验证中暴露的若干相对表单 action、注册输入与运行时恢复边界问题。

### Docs

- 补充 live challenge 运行台账与实战 WP，形成从能力测试到端到端验证的可回读证据链。
- 明确记录“先测能力，再测端到端；失败先归因为通用能力缺口”的测试与修复原则。

### Internal

- 本次版本对应的能力增强提交为 `e1eae86`，文档与留痕提交为 `fda4e39`。
- 当前仓库继续保持 **Private**；本地对话交接备忘未纳入仓库历史。

---

## v0.1.0 - 2026-05-28

首个 `FlagHunter` 仓库基线版本。

### Included

- 建立新的 GitHub 仓库 `leilehuimieba/FlagHunter`
- 将主线代码迁移到新仓库并切换默认远程
- 将仓库可见性保持为 **Private**
- 重写顶层 `README.md` 为 `FlagHunter` 项目首页
- 统一主要用户文档中的旧品牌 `PentestAgent-CPA`
- 补充仓库 `topics`
- 创建首个 GitHub Release：`FlagHunter v0.1.0`

### Notes

- 外部品牌统一为 **FlagHunter**
- 内部代码骨架仍兼容 `pentestagent/` 结构与现有运行入口
- 当前不设置公开 Website，避免与私有仓库策略冲突

