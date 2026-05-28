# FlagHunter Release Checklist

> 本清单用于 **发版前最后人工检查**。  
> 与 `D:\webstudy\FlagHunter\docs\release-policy.md` 配套使用。

---

## 1. Repository Status

- [ ] 仓库仍为 **Private**
- [ ] 未设置不必要的公开 Website
- [ ] 默认分支正确（通常为 `main`）
- [ ] 当前工作区干净，没有未预期改动

---

## 2. Docs Consistency

- [ ] `README.md` 已与当前版本状态同步
- [ ] `CHANGELOG.md` 已更新到目标版本
- [ ] `docs/release-policy.md` 仍适用于当前发版方式
- [ ] 如有必要，已同步 `AGENTS.md` / `plans/` / 其它用户文档

---

## 3. Security / Sensitive Content Check

- [ ] 未提交 `.env` / token / key / cookie / 凭据
- [ ] 未提交 `loot/`、日志、缓存或本地敏感产物
- [ ] 未误包含不该出现在 release notes 中的敏感上下文
- [ ] 未误加入公开暴露链接或不必要外链

---

## 4. Validation

- [ ] 本次版本关键变更已完成验证
- [ ] 验证命令 / 页面 / 结果摘要已记录
- [ ] 已知问题已在 release notes 或 changelog 中说明

---

## 5. Release Content

- [ ] tag 命名正确（如 `v0.1.1`）
- [ ] release 标题与 tag 一致（如 `FlagHunter v0.1.1`）
- [ ] release notes 已按模板填写
- [ ] changelog 分类清晰（Added / Changed / Fixed / Docs / Internal）

---

## 6. Post-Release Quick Check

- [ ] GitHub Releases 页面展示正常
- [ ] README 首页展示正常
- [ ] About / Topics / License / Latest Release 显示正常
- [ ] 当前仓库仍保持 **Private**

---

## 7. Notes

如本次发版有特殊情况，请记录：

- 
