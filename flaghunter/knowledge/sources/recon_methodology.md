# 信息收集方法论

## 原理
信息收集的目标不是“把所有工具都跑一遍”，而是快速建立目标攻击面的真实模型，并据此挑出最短可利用链。无论面对的是 CTF Web、内网靶场、混合资产还是单机服务，侦察阶段都应回答几类关键问题：目标究竟有哪些入口点、暴露了哪些服务、哪些资源需要认证、哪些子系统彼此信任、哪些历史遗留或调试面仍然在线、哪些客户端资产泄露了后端结构。高质量的信息收集必须遵守一个原则：先被动、后主动；先低噪声确认事实，再针对性扩展枚举。因为 CTF 里很多高价值线索根本不在端口扫描结果里，而在 HTML、JS、source map、API schema、错误信息、默认文件、重定向头、证书 SAN、对象存储地址、登录流与前端路由中。

一套有效的方法论通常围绕“收敛”而不是“发散”。先归一化目标范围：域名、IP、端口、URL、虚拟主机、是否需要 Host 头、是否存在登录前后差异；再进行服务识别与版本推断；随后针对 Web、API、静态资源、管理面板、文件上传、消息接口、第三方组件做面向利用的枚举；最后把发现整理成可执行的下一步，比如“从 `main.js` 暴露的 `/api/debug` 入手”“优先打本地信任的 `/admin`”“利用 source map 恢复前端接口定义”。CTF 环境里，正确的方法不是把目录扫描、端口扫描、子域名枚举分裂成孤立任务，而是让每条线索都反哺后续路径选择。

## 工具与命令示例
```bash
# 1) 端口与服务识别，优先建立暴露面
nmap -sV -Pn target.example

# 2) 快速高并发端口扫描，适合靶场先摸清大面
rustscan -a target.example --ulimit 5000

# 3) Web 指纹识别，观察中间件、框架、CDN、CMS
whatweb http://target.example

# 4) 目录与文件枚举，注意状态码和长度过滤
ffuf -u http://target.example/FUZZ -w wordlists.txt -mc all -fs 0

# 5) 子域名收集，适用于有统一根域的靶场
subfinder -d example.com -silent

# 6) 抓首页与关键头部，确认重定向、服务器类型、Cookie
curl -i http://target.example/

# 7) 搜索前端源码里的接口与敏感路径
rg -n "/api|graphql|swagger|token|debug|localhost|admin" flaghunter

# 8) 抓取 HTML/JS 后提取 URL，适合快速恢复隐藏路由
python -c "import re,requests; t=requests.get('http://target.example').text; print('\n'.join(sorted(set(re.findall(r'/[A-Za-z0-9_./?-]+', t)))))"
```

## 常见 CTF 题型
### 题型一：主页很干净，JS 泄露真实接口
思路：页面只给一个登录框或静态介绍，但 `main.js`、source map、Webpack chunk、API client 里暴露了 `/api/debug`、`/internal`、`/graphql`、上传接口和管理员功能。优先读 JS，而不是先重扫十遍目录。

```python
import re, requests
js = requests.get('http://target/static/main.js').text
for m in sorted(set(re.findall(r'/[A-Za-z0-9_./?-]+', js))):
    print(m)
```

### 题型二：额外管理端口/虚拟主机藏入口
思路：80 端口内容平平无奇，但 5000/8080/7001 暴露调试面板、管理接口、Jenkins、Actuator、Tomcat Manager；或同一 IP 通过不同 Host 头提供另一套站点。先确认端口，再做 Host 枚举与证书 SAN 分析。

```python
import requests
hosts = ['admin.target', 'dev.target', 'staging.target']
for h in hosts:
    r = requests.get('http://1.2.3.4/', headers={'Host': h}, timeout=3)
    print(h, r.status_code, len(r.text))
```

### 题型三：默认文件/备份包/元数据泄露
思路：`robots.txt`、`.git/HEAD`、`backup.zip`、`swagger.json`、`openapi.yaml`、`composer.lock`、`package-lock.json`、`Dockerfile`、`/.env` 往往直接暴露框架、路由、依赖版本和敏感配置。此类题中，目录扫描要结合文件语义分析，不是只看状态码。

```bash
curl http://target.example/robots.txt
curl http://target.example/.git/HEAD
curl http://target.example/swagger.json
```

### 题型四：登录边界差异产生攻击面
思路：未登录只能看到很少页面，但注册普通用户后会多出上传、个人资料、导出、Markdown 渲染、Webhook 等高价值功能；管理员与访客渲染模板也可能不同。信息收集必须覆盖“身份变化前后”的页面差异。

```python
import requests
s = requests.Session()
s.post('http://target/register', data={'u':'a','p':'a'})
print(s.get('http://target/profile').text[:500])
```

## 绕过与进阶技巧
- **先首页再爆破**：首页 HTML、JS、Cookie、重定向和报错信息经常比大规模目录扫描更快给出入口。
- **身份切换是侦察的一部分**：游客、普通用户、管理员 bot、内网来源、不同 Host 头都可能看到不同攻击面。
- **静态资源最值钱**：JS、source map、WASM、OpenAPI、GraphQL schema、移动端 APK/IPA 往往直接给出真实 API 结构。
- **扫描结果要做语义过滤**：不是每个 200 都有价值，关注登录页、上传点、导出点、预览点、调试接口、健康检查、管理面板。
- **证书与头部信息**：TLS 证书 SAN、`Server`、`X-Powered-By`、反向代理特征、CORS、缓存头都能反推出架构与隐藏域名。
- **Host 头与虚拟主机**：同一 IP 多站点极常见，证书名、JS 内联域名、邮件模板链接、错误页都能提供候选 Host。
- **目录扫描别脱离上下文**：从首页与 JS 中提取的路径词比通用字典更有效，能显著降低噪声。
- **记录异常行为**：404 模板差异、500 栈信息、302 跳转、空白页面、长延迟都可能是后续漏洞入口的证据。
- **一条链跑通再扩展**：信息收集不是比赛谁发现资产多，而是谁最快找到可利用路径并闭环验证。

## 快速检查清单
- [ ] 目标范围是否已归一化：域名、IP、URL、端口、Host 头、登录上下文
- [ ] 首页 HTML、响应头、Cookie、重定向和错误信息是否已完整检查
- [ ] 是否完成端口识别并关注非常见管理端口
- [ ] 是否阅读了关键 JS/source map，提取 API、隐藏路由和环境变量
- [ ] 是否检查了 `robots.txt`、`.git`、备份包、Swagger、GraphQL、调试接口等默认暴露面
- [ ] 是否对登录前后、不同身份、不同 Host 头做了差异化探测
- [ ] 目录扫描是否结合了上下文词表和长度/状态码过滤，而不是盲扫
- [ ] 是否记录了每条线索的来源、证据、URL、参数和后续动作
- [ ] 是否已经识别最短攻击链，而不是只累计零散资产
- [ ] 是否把发现整理为可交接、可复现的下一步验证路径
