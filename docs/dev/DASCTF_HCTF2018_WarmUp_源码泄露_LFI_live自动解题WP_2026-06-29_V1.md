# DASCTF/BUUCTF [HCTF 2018]WarmUp — FlagHunter live 自动解题 WP

**日期**：2026-06-29 · **平台**：ctf2.dasctf.com 公开练习场 BUUCTF · **类型**：WEB/简单
**结果**：✅ FlagHunter 全自动解出并平台判对（回答正确 +1 分，WEB 进度 4→5/1608）

这是 FlagHunter 第一条**端到端 live 自动解题闭环**的记录：opencli 复用 Edge 登录态进
靶场起靶机 → 多 provider 池(gpt-5.4 主力)驱动 → flaghunter run 自动解出 → opencli
提交 flag → 平台判对。对应数据治理 policy 的第③层(人写题解)。

---

## 1. 环境

- 靶机实例(授权,本账号):`http://4afb3426fe76cdba8e1ae4d0.http-ctf2.dasctf.com/`
  (动态实例,1 小时窗口;平台发**每实例唯一** `CTF2{...}` flag,非静态 `flag{}`)
- LLM:`flaghunter run` 走 M1 hub provider 池,主力 `openai/gpt-5.4`@blackaicoding。
- 命令:
  ```
  flaghunter run "Solve this CTF web challenge ... source.php ... LFI" \
    -t http://4afb3426fe76cdba8e1ae4d0.http-ctf2.dasctf.com/ \
    --mode ctf --ctf-type web --profile ctf --report
  ```

## 2. FlagHunter 的解题链（CTF dispatcher web 快路径）

耗时 **12s**,`Loops 0/50, Tools 0` —— 没进完整 agent 循环,由 CTF dispatcher 的
确定性 web 链直接打通:

1. `ctf_runtime_fingerprint` —— 指纹 detected_type=web。
2. `ctf_backup_candidate` —— 命中备份/源码泄露候选:`/source.php`
   (首页 HTML 注释 `<!--source.php-->` 是 WarmUp 的经典提示)。
3. `ctf_backup_analysis` —— 分析 source.php:`checkFile()` 白名单校验有缺陷
   (对 `?file=` 做 `mb_strpos` 截断前缀匹配,可用 `source.php?/../` 绕过)。
4. `ctf_flag_runtime` —— 经 LFI 读取 flag 文件
   (WarmUp 标准路径 `?file=source.php?/../../../../../../ffffllllaaaagggg`),
   runtime 拿到并 verify。

**Flag**：`CTF2{31dde64f-ae8b-4262-a5d5-20f646551bbe}`(本实例;他人复现得到自己的)。

## 3. 两个工程发现（已回填记忆,后续可治理）

1. **快路径不触发知识自动回填**:dispatcher 快路径解出时(0 loop)未调用
   `ctf_experience.save_ctf_experience` → `knowledge/ctf_sessions/` 无本题草稿。
   即数据治理"第②层自动回填"只在 agent 循环路径上挂着,快路径漏了。
2. **快路径报告偏薄**:`loot/reports/*.md` 的 "Commands Executed: 0" —— dispatcher
   在 agent 命令记录之前就解出,报告只有 flag 没有链路 trace(本 WP 补足链路)。

两者都是"能力够强反而绕过了观测/回填挂点"的同构问题,记入
[[project_data_governance]] / [[project_operating_model_vision]] 后续 backlog。

## 4. 产出归位（按数据治理 policy）

- ① 原始:`loot/reports/http_4afb...md`、artifact_registry/checkpoints/session_ledgers(gitignore)
- ② 自动回填:本次**未触发**(见发现 1)
- ③ 本题解:本文(committed)
- ④ 框架教训:回填 Claude memory(provider 池 live 验证 + 两发现)
