# CTF Agent Walkthrough：PHP Object Injection Acceptance

> **目标**：给新操作者一条可复验、可截图、可对照日志的首题尝试路径。  
> **对应链路**：`backup_source_leak` → `php_unserialize_magic_method` → runtime / verified flag  
> **证据文件**：
>
> - 验证日志：`D:\webstudy\FlagHunter\docs\dev\assets\phase6\phase6_first_attempt_validation.log`
> - 截图：`D:\webstudy\FlagHunter\docs\dev\assets\phase6\phase6_tui_*.svg`
> - 集成测试：`D:\webstudy\FlagHunter\tests\integration\test_ctf_dispatcher_php_object_injection_acceptance.py`

---

## 1. 这个 walkthrough 解决什么问题

Phase 6 的目标不是“再补一个命令”，而是让用户真的能：

1. 启动 `/ctf`
2. 看懂推理和 StopReport
3. 遇到 source-only 假 flag 不被误导
4. 在需要时用 `/ctf override` 或 `/ctf wrong` 把闭环跑完

这份 walkthrough 选用本仓库已经有 acceptance coverage 的 PHP 题型替身：

- 首页出现备份线索
- `/www.zip` 可下载源码
- 源码里有 **假 flag**
- 真 flag 只能通过运行时 PHP 反序列化链打出来

这条链和 Phase 0.5 里记录的 `[极客大挑战 2019]PHP` 主路径是同类问题，因此既可复现，又能检验“错误 flag 后继续深挖”的关键能力。

---

## 2. 预期结果

完成本 walkthrough 后，你应看到：

- `candidate_flags` 里出现源码 flag
- agent 不把源码 flag 直接当成终点
- 后续通过运行时利用拿到 `flag{php_object_injection_runtime_ok}`
- `StopReport` 能明确区分 candidate / runtime / verified
- 整个“首题尝试 + 人工收口”在 30 分钟内完成

当前验证日志中的真实结果见：

- `D:\webstudy\FlagHunter\docs\dev\assets\phase6\phase6_first_attempt_validation.log`

其中记录到：

- `elapsed_to_runtime_pending_seconds=20.79`
- `elapsed_to_verified_seconds=21.32`

---

## 3. 复验方式

### 路线 A：看现成交付物

直接检查：

1. 截图
   - `phase6_tui_startup.svg`
   - `phase6_tui_running.svg`
   - `phase6_tui_stopreport.svg`
2. 日志
   - `phase6_first_attempt_validation.log`

适合做文档验收、产品演示和 Phase 6 audit。

### 路线 B：跑 acceptance 测试

```powershell
cd D:\webstudy\FlagHunter
pytest -q tests/integration/test_ctf_dispatcher_php_object_injection_acceptance.py
```

这个测试验证：

- 实际命中了 `/www.zip`
- 实际构造了 `/?select=...` payload
- state 里同时保留了源码 candidate 与运行时 verified flag

### 路线 C：按操作者视角理解 TUI 流程

真实操作者最关心的不是 pytest，而是下面这个节奏：

```text
/ctf http://127.0.0.1:<port> type=auto goal="拿到flag"
... 观察 reasoning / stop_report ...
/ctf override flag{php_object_injection_runtime_ok}
```

本仓库已经把这条流程的验证结果落到 `phase6_first_attempt_validation.log`。

---

## 4. 题目链路拆解

### Step 1：启动 `/ctf`

命令形态：

```text
/ctf http://127.0.0.1:<port> type=auto goal="拿到flag"
```

此时你应该看到：

- TUI 进入 CTF dispatcher mode
- 头部状态进入 `thinking/agent`
- chat 区开始出现 reasoning / recon 输出

### Step 2：识别备份线索

首页会给出“有备份网站习惯”之类的线索。

正确预期：

- agent 优先生成 `backup_source_leak`
- 尝试访问 `/www.zip`
- 不会因为“看起来像 PHP 题”就先乱打 payload

### Step 3：从源码里拿到 candidate flag

`www.zip` 解压后，源码里会出现：

- 反序列化入口
- 魔术方法链
- 一个 **假的源码 flag**

正确行为：

- 这个 flag 进入 `candidate_flags`
- **不会** 直接进入 `verified_flags`

这是本项目“验证独立化”是否生效的关键点。

### Step 4：升级到运行时利用

agent 继续沿 `php_unserialize_magic_method` 深挖，构造 `Name` 对象 payload。

正确预期：

- 不是只停在源码阅读
- 会真正访问 `/?select=...`
- 页面运行时回显 `flag{php_object_injection_runtime_ok}`

### Step 5：必要时人工收口

如果当前环境没有自动提交端点，或平台适配未接好，操作者可以执行：

```text
/ctf override flag{php_object_injection_runtime_ok}
```

然后应看到：

- `verified_flags` 包含该 flag
- `StopReport.reason = flag_verified`

---

## 5. 这条 walkthrough 实际证明了什么

它证明的不是“这个系统会做一道固定题”，而是下面这些行为不变量：

1. **源码 flag 不会直接变 verified**
2. **同一路线可以从 source-only 继续升级到 runtime**
3. **StopReport 会把 candidate/runtime/verified/rejected 分层展示**
4. **操作者可以用 `/ctf override` 在最后一跳完成闭环**

这正是“错误 flag 后深挖提示流”要保证的最低用户体验。

---

## 6. 如果平台返回错误 flag，下一步怎么做

这条 walkthrough 的配套恢复路径是：

```text
/ctf wrong <wrong_flag>
/ctf reasoning postmortem
/ctf memory audit 0.60 sort=correlation
/ctf memory rollback <id>
```

解释：

- `/ctf wrong` 负责把这次错误当成强反证
- `postmortem` 告诉你“为什么它会错”
- `memory audit` 检查是不是旧记忆把系统带偏
- `rollback` 用于撤销被自动 mute 但这次又可能有价值的条目

---

## 7. 首题尝试是否满足 30 分钟

当前 Phase 6 交付物给出的实际验证结果：

- 到 runtime / 成功拿到 flag：约 `20.79s`
- 到人工 override 收口为 verified：约 `21.32s`

证据：

- `D:\webstudy\FlagHunter\docs\dev\assets\phase6\phase6_first_attempt_validation.log`

因此，**“按手册完成首题尝试”这一标准在当前 acceptance walkthrough 上已具备真实证据，而不是只有口头承诺。**

---

## 8. 建议如何把这份 walkthrough 用在后续验收

每次 `/ctf` 主交互面有改动时，至少回看这三样：

1. `tests/integration/test_ctf_dispatcher_php_object_injection_acceptance.py`
2. `docs/dev/assets/phase6/phase6_first_attempt_validation.log`
3. `docs/dev/CTF_Agent_用户操作手册_V1.md`

如果三者之间出现不一致，优先以**当前代码和当前真实日志**为准，再回填文档。

