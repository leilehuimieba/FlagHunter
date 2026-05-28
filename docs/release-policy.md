# FlagHunter Release Policy

> 适用于 `D:\webstudy\FlagHunter` 当前仓库。默认前提：仓库保持 **Private**，发布面向受控协作与内部版本演进。

---

## 1. 目标

本规则用于统一以下内容：

- 版本号命名
- `CHANGELOG.md` 写法
- GitHub Release 标题与正文结构
- 发布前检查动作

目标是：

1. 让版本信息可回溯
2. 让 README / CHANGELOG / Release 三者保持一致
3. 避免私有仓库在发布时误暴露不该公开的内容

---

## 2. 版本号规则

当前阶段采用 **语义化版本的简化实践**：

### 2.1 主版本（Major）

格式：`vX.0.0`

适用场景：

- 出现明显的兼容性变化
- 运行方式、配置方式、模块边界发生重大调整
- 项目从一个阶段进入下一个稳定阶段

示例：

- `v1.0.0`
- `v2.0.0`

### 2.2 次版本（Minor）

格式：`v0.X.0` 或 `v1.X.0`

适用场景：

- 新增清晰可见的能力模块
- 新增新的工作流、工具域或集成功能
- README / 文档 / 交付链发生明显增强，足以构成一个阶段性版本

示例：

- `v0.1.0`
- `v0.2.0`

### 2.3 补丁版本（Patch）

格式：`v0.1.X`、`v1.2.X`

适用场景：

- 文档修正
- 小范围 bugfix
- 非破坏性展示层优化
- 小范围脚本 / 配置修复

示例：

- `v0.1.1`
- `v0.1.2`

---

## 3. 当前阶段建议

在 `FlagHunter` 当前阶段，建议遵循：

- `v0.x.y`：快速演进期
- 不承诺完全稳定 API / 结构
- 但要求每次 release 都写清楚“加了什么、改了什么、是否影响协作方式”

简单判断规则：

- **新能力 / 新模块 / 新阶段** → `minor`
- **文档 / 修复 / 小调整** → `patch`
- **兼容性或结构大改** → `major`

---

## 4. CHANGELOG 规则

`CHANGELOG.md` 建议使用以下分类：

- `Added`
- `Changed`
- `Fixed`
- `Docs`
- `Internal`

### 推荐格式

```md
## v0.1.1 - 2026-05-29

### Added
- 新增 ……

### Changed
- 调整 ……

### Fixed
- 修复 ……

### Docs
- 更新 README / 手册 / 部署文档 ……

### Internal
- 内部结构或协作流程调整 ……
```

### 书写原则

- 面向“协作者”写，而不是面向 commit 历史写
- 写“可感知变化”，不要机械重复 git diff
- 若无某类内容，可省略该小节

---

## 5. GitHub Release 模板

每次创建 GitHub Release 时，建议使用以下结构：

```md
## Summary
一句话总结本次版本的目标。

## Included
- 本次包含的核心内容 1
- 本次包含的核心内容 2
- 本次包含的核心内容 3

## Changed
- 有哪些行为、文档或展示层发生变化

## Fixed
- 修复了哪些问题

## Docs
- 更新了哪些说明文档

## Upgrade Notes
- 对现有协作者是否有额外动作要求
- 是否需要重新配置、重新拉取、重新初始化

## Verification
- 本次版本如何验证通过

## Notes
- 额外说明（例如：仓库继续保持 Private、内部骨架未重命名等）
```

---

## 6. Release 标题规则

建议统一为：

- `FlagHunter v0.1.0`
- `FlagHunter v0.1.1`
- `FlagHunter v0.2.0`

不要混用：

- `release-1`
- `first stable`
- `update docs`
- 没有项目前缀的标题

这样能保证 GitHub Releases 列表更整齐。

---

## 7. 发布前检查清单

每次发版前至少检查：

- [ ] 仓库仍为 **Private**
- [ ] README 是否与当前项目状态一致
- [ ] `CHANGELOG.md` 是否已更新
- [ ] release tag 与标题是否一致
- [ ] 是否误包含 `.env`、token、loot、日志、缓存等敏感内容
- [ ] 是否需要同步 `docs/`、`plans/`、`AGENTS.md`
- [ ] 是否需要补验证说明

---

## 8. 发布节奏建议

当前推荐节奏：

- **patch**：展示层、文档、小修复完成后可发
- **minor**：完成一个明确阶段后发
- **major**：只有在结构边界或兼容性发生重大变化时再发

简化建议：

- 不要为每一个 commit 发 release
- 让每个 release 都对应一个“协作者能感知到的阶段成果”

---

## 9. 与当前仓库策略的关系

本规则默认假设：

- 当前仓库继续保持 **Private**
- 不设置公开 Website
- 对外品牌为 **FlagHunter**
- 内部代码骨架继续兼容 `pentestagent/`

如果未来仓库策略改变，应先更新本文件，再调整发布方式。

---

## 10. 配套文档

建议结合以下文档一起使用：

- `D:\webstudy\FlagHunter\docs\release-checklist.md`
- `D:\webstudy\FlagHunter\docs\release-playbook.md`
