# FlagHunter Release Playbook

> 适用于 `D:\webstudy\FlagHunter` 当前仓库。  
> 这是 **“实际怎么发版”** 的操作手册；与 `docs/release-policy.md`、`docs/release-checklist.md` 配套使用。

---

## 1. 使用时机

当你已经确认要发布一个新版本时，按本手册执行。

适用场景：

- 文档、展示层、协作流程完成一轮明确收口
- 一个阶段性能力已经可交付、可验证、可记录
- 需要创建新的 tag 与 GitHub Release

---

## 2. 发布前判断

先判断这次是：

- **patch**：文档、小修复、小范围展示层调整
- **minor**：新增阶段性能力、明显增强工作流
- **major**：有不兼容变化或明显结构边界调整

如不确定，优先回看：

- `D:\webstudy\FlagHunter\CHANGELOG.md`
- `D:\webstudy\FlagHunter\docs\release-policy.md`

---

## 3. 标准发布流程

### Step 1：确认仓库状态

先确认：

- 当前仓库仍为 **Private**
- 当前分支为预期发布分支（通常是 `main`）
- 工作区干净
- 没有未预期的本地实验性改动

推荐命令：

```bash
git status --short --branch
gh repo view leilehuimieba/FlagHunter --json name,visibility,isPrivate,url,homepageUrl
```

---

### Step 2：整理变更内容

整理本次版本真正要对协作者表达的变化，而不是机械照抄 commit。

优先检查：

- `README.md`
- `CHANGELOG.md`
- `docs/`
- `.github/`

问题自检：

- 这次版本最重要的“对外可感知变化”是什么？
- 有没有兼容性提醒？
- 有没有需要协作者额外手动处理的地方？

---

### Step 3：更新 `CHANGELOG.md`

新增目标版本段落，建议使用：

```md
## v0.1.1 - 2026-05-28

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Docs
- ...

### Internal
- ...
```

注意：

- 没有内容的分类可以省略
- 文档类更新不要写得像 commit message，要写成“协作者能感知到的变化”

---

### Step 4：同步 README / 文档入口

如果这次版本改变了：

- 项目定位
- 首页展示
- 快速开始
- 文档入口
- release 规则

就需要同步更新 `README.md`，确保：

- 首页看到的内容和当前仓库真实状态一致
- 新增文档在 README 里能被找到

---

### Step 5：执行验证

在创建 tag 之前，至少要记录：

- 本次关键改动验证是否通过
- 用什么命令 / 页面 / 结果验证
- 是否存在已知未解决问题

最小验证示例：

```bash
git status --short --branch
pytest
gh repo view leilehuimieba/FlagHunter --json visibility,isPrivate
```

如果这次只是展示层 / release / 模板调整，至少也要确认：

- 文档文件存在
- README 链接没有漏
- GitHub 元数据仍符合私有仓库预期

---

### Step 6：提交并推送

在确认无误后：

```bash
git add .
git commit -m "docs: prepare v0.1.1 release"
git push origin main
```

commit message 可以按实际内容调整，但要避免：

- `update`
- `fix stuff`
- `misc`

这类无法回溯含义的提交信息。

---

### Step 7：创建 tag 与 GitHub Release

推荐方式：

```bash
git tag v0.1.1
git push origin v0.1.1
gh release create v0.1.1 --title "FlagHunter v0.1.1" --notes-file <release-notes-file>
```

如果直接用命令行临时写 notes，也要保持结构和 `release-policy.md` 一致。

推荐 release notes 结构：

- `Summary`
- `Included`
- `Changed`
- `Fixed`
- `Docs`
- `Upgrade Notes`
- `Verification`
- `Notes`

---

### Step 8：发布后快速核验

发布完成后立即检查：

- GitHub Releases 页面是否展示正常
- README 首页是否正常
- About / Topics / License / Latest Release 是否正常
- 仓库是否仍保持 **Private**

推荐命令：

```bash
gh release view v0.1.1 --repo leilehuimieba/FlagHunter
gh repo view leilehuimieba/FlagHunter --json visibility,isPrivate,homepageUrl
```

---

## 4. 常见错误

### 错误 1：先发 release，再补 changelog

不建议。  
正确顺序应是先整理变更、写 changelog，再发 release。

### 错误 2：release 标题与 tag 不一致

例如：

- tag：`v0.1.1`
- title：`Release Candidate`

这种会让 releases 列表失去一致性。建议统一为：

- `FlagHunter v0.1.1`

### 错误 3：把私有仓库当公开仓库写说明

当前仓库是 **Private / Internal Collaboration**，发布说明不要误写成：

- “欢迎所有外部用户直接使用”
- “公开产品官网见 …”

除非仓库策略已经变化并被明确确认。

### 错误 4：把内部兼容骨架改名当成普通 patch

如果涉及：

- `pentestagent/` 包骨架
- `pentestagent` 命令
- 兼容性配置字段

这类变更通常不应作为普通 patch 处理，应重新评估版本级别与迁移说明。

---

## 5. 一次典型发版的最小产物

一次合格的发版，至少应留下：

- 一个干净的发布前提交
- 一个更新过的 `CHANGELOG.md`
- 一个明确的 Git tag
- 一个可回读的 GitHub Release
- 一份可复核的验证摘要

---

## 6. 建议配套阅读顺序

1. `D:\webstudy\FlagHunter\docs\release-policy.md`
2. `D:\webstudy\FlagHunter\docs\release-checklist.md`
3. `D:\webstudy\FlagHunter\docs\release-playbook.md`

其中：

- `release-policy` 解决“规则是什么”
- `release-checklist` 解决“临门一脚检查什么”
- `release-playbook` 解决“实际一步步怎么发”
