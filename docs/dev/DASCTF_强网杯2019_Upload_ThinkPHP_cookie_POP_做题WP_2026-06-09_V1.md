# DASCTF / BUUCTF `[强网杯 2019]Upload` 做题 WP

日期：2026-06-09

## 结论

- 题目：`[强网杯 2019]Upload`
- live 靶机：`http://ee9c111fba2e7a34d85b055d.http-ctf2.dasctf.com:80`
- flag：`DASCTF{16cd03e2-c913-48bf-a62e-6da5518573e3}`
- 平台确认：`submit` API 返回 `is_correct=true`，`points=1`

## 项目能力测试记录

先测通用 upload 能力，不先写题目专用脚本。

初始回归：

```powershell
.\.venv\Scripts\python -m pytest tests -k upload -q
```

修复前状态：

- `detect_type` 与 multipart 基础能力存在。
- `ctf_dispatcher` 已有 upload chain，但只能处理首页直接暴露 file input 的普通上传。
- live E2E 首次失败：页面只有 login/register，dispatcher 误入 `sqli` auth probe，没有注册登录后重新侦察上传面。

第一轮通用修复：

- post-auth recon 支持先注册低权限账号，再登录。
- 注册邮箱模板改为更通用的 `ctf_probe_xxxxxx@example.com`，避免被目标判为 `Email illegal`。
- 登录字段若是 email，则提交邮箱而不是用户名。
- 登录后重新解析页面表单，post-auth 页面出现 file input 时自然判型为 `upload`。
- 新增 full dispatcher 用例：未登录页只有 login/register，登录后出现 upload form，最终由 upload chain 拿 flag。

第二轮 live E2E 结果：

- 已正确进入 `detected_type=upload`。
- 但普通上传链不能执行 PHP，因为目标会把上传文件保存为 `md5(original_name).png`。
- 随后 backup source leak 下载 `www.tar.gz`，但源码里的模板字符串 `literal{$count}` 被当作 source-only candidate flag，恢复控制停止，没有继续 runtime exploit。

第二轮通用修复：

- source-only / placeholder wrong flag 标记为 recoverable，不触发 early stop。
- flag 提取器优先匹配常见 CTF 前缀，避免 `GIF89aDASCTF{...}` 被整体吞入 flag，也减少 `literal{$count}` 类模板假 flag。

第三轮通用修复：

- 修正相对 form action 解析：`/index.php/home` 页面里的 `action="upload"` 应按 URL 标准解析为 `/index.php/upload`，不能错误拼成 `/index.php/home/upload`。
- backup analyzer 增加源码证据模式识别：
  - `cookie('user')`
  - `unserialize(base64_decode(...))`
  - `__destruct`
  - `__call`
  - `copy($this->filename_tmp, $this->filename)`
- 新增 `php_upload_cookie_pop` runtime exploit：
  - 注册并登录低权限账号。
  - 上传 `GIF89a + PHP` polyglot。
  - 从 home 页面解析真实 `../upload/<md5(ip)>/<md5(name)>.png`。
  - 构造 cookie unserialize POP，把已上传 png 复制为同目录 PHP 文件。
  - 访问生成的 PHP 路径读取 `/flag`。

回归验证：

```powershell
.\.venv\Scripts\python -m pytest tests -k upload -q
```

结果：`10 passed`

```powershell
.\.venv\Scripts\python -m pytest tests/unit/agents/test_ctf_dispatcher.py -q
```

结果：`148 passed`

## 手工验证关键事实

源码泄露：

- `/www.tar.gz` 实际 magic 为 `PK`，是 zip 内容。
- 关键文件：
  - `application/web/controller/Index.php`
  - `application/web/controller/Profile.php`
  - `application/web/controller/Register.php`
  - `route/route.php`

关键源码事实：

- 登录状态来自 `cookie('user')`。
- `Index::login_check()` 执行 `unserialize(base64_decode($profile))`。
- `Profile::upload_img()` 使用 `copy($this->filename_tmp, $this->filename)`。
- `Register::__destruct()` 在未注册成功状态下调用 `$this->checker->index()`。
- `Profile::__call()` / `__get()` 可把 `index` 调到 `upload_img`。
- 正常上传通过 `getimagesize()`，保存为 `.png`，路径为 `../upload/<md5(REMOTE_ADDR)>/<md5(original_name)>.png`。

手工验证 POP 链时曾拿到一条当前实例 flag：

- `DASCTF{924a51fc-477f-4047-b0fd-f434262ac5d1}`

该 flag 属于已过期旧靶机，仅用于验证 exploit 链，不作为最终提交。

## 最终 E2E

靶机重新启动：

- challenge id：`186208e2-1c4a-4588-b64e-144ce20caf63`
- 新 live URL：`http://ee9c111fba2e7a34d85b055d.http-ctf2.dasctf.com:80`
- 到期时间：`2026-06-09T22:17:50+08:00`

E2E 命令：

```powershell
.\.venv\Scripts\pentestagent run -t "http://ee9c111fba2e7a34d85b055d.http-ctf2.dasctf.com:80" --mode ctf --max-loops 5 "拿到flag。先测试通用文件上传能力：发现登录/注册入口，注册低权限账号，登录后重新侦察上传表单，multipart 上传；若源码泄露显示 cookie unserialize + __destruct/__call + copy(upload tmp, filename)，用源代码证据驱动的 PHP upload cookie POP runtime 验证；不要大规模扫描。"
```

E2E 结果：

- `detected_type=upload`
- 发现并分析 `www.tar.gz`
- 命中 `php_upload_cookie_pop`
- runtime shell 返回并 verified：`DASCTF{16cd03e2-c913-48bf-a62e-6da5518573e3}`

平台提交：

```http
POST /api/v1/practice/b9bbb32f-f186-458f-b90b-12440c0f6aea/challenges/186208e2-1c4a-4588-b64e-144ce20caf63/submit/
{"flag":"DASCTF{16cd03e2-c913-48bf-a62e-6da5518573e3}"}
```

返回：

```json
{"data":{"attempt":1,"is_correct":true,"points":1},"success":true}
```

## 暴露出的通用不足与已修复项

- 不足：只看 pre-auth 页面会把 upload 题误判为 SQLi 登录绕过。
- 修复：post-auth recon 支持注册/登录后重新侦察。
- 不足：相对 action 解析错误，把 `/index.php/home + upload` 拼成 `/index.php/home/upload`。
- 修复：按标准 `urljoin(page_url, action)` 解析。
- 不足：source-only 假 flag 会使恢复控制提前停止。
- 修复：source-only wrong flag recoverable，记录后继续。
- 不足：polyglot 响应中的 GIF magic 会污染 flag 提取。
- 修复：优先严格匹配常见 CTF flag 前缀。
- 不足：缺少源码证据驱动的 PHP upload cookie POP 通用 primitive。
- 修复：新增 `php_upload_cookie_pop` 识别与 runtime exploit。
