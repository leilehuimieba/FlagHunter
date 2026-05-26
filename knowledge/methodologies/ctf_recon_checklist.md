# CTF 信息收集与侦察清单

## Phase 1: 初始接触（5 分钟）

### 1.1 题目信息记录
- [ ] 记录题目名称、类别、分值
- [ ] 记录目标 URL / IP / 端口
- [ ] 记录提供的附件（二进制、源码、流量包等）
- [ ] 记录题目描述中的提示（往往包含关键线索）

### 1.2 快速端口扫描
```bash
nmap -sV -sC -p- --open target.com
nmap -sV -sC target.com      # 常见端口快速扫描
```

关注端口：
- 80/443 → Web
- 22 → SSH（可能后续提权需要）
- 3306 → MySQL
- 6379 → Redis
- 8080/8443 → 备用 Web 服务
- 1337/9000-9100 → 常见 CTF 服务端口

---

## Phase 2: Web 侦察（10 分钟）

### 2.1 页面基础分析
- [ ] 查看页面源代码（Ctrl+U）
- [ ] 检查注释（`<!-- -->`）中是否隐藏提示
- [ ] 检查 JS 文件（搜索 `flag`、`key`、`secret`、`api`、`token`）
- [ ] 检查 Cookie（是否有 session、token、hint）
- [ ] 检查 HTTP 响应头（Server、X-Powered-By、Set-Cookie）

### 2.2 技术栈识别
```bash
whatweb http://target.com
wappalyzer 浏览器插件
```

识别：
- 后端语言（PHP、Python/Flask/Django、Node.js、Java）
- 前端框架（Vue、React、Angular）
- Web 服务器（Nginx、Apache、Tomcat）
- 数据库类型（MySQL、PostgreSQL、MongoDB、SQLite）

### 2.3 敏感文件探测
```bash
ffuf -u http://target/FUZZ -w wordlists/ctf_specific.txt -mc all -fs 0
dirsearch -u http://target.com -e php,txt,zip,bak,git,env,json
```

优先级扫描：
- `.git/`（源码泄露）
- `.env`（配置泄露）
- `flag*`（直接暴露）
- `backup*` / `*.zip`（备份文件）
- `admin*` / `login*`（认证入口）
- `phpinfo.php`（PHP 信息）
- `robots.txt`（隐藏路径提示）

### 2.4 目录结构理解
- [ ] 绘制站点地图（哪些页面存在、功能是什么）
- [ ] 识别所有输入点（URL 参数、表单、文件上传、HTTP Header）
- [ ] 识别所有输出点（页面内容、错误信息、响应头）

---

## Phase 3: 漏洞面分析（10 分钟）

### 3.1 输入点分类
| 输入类型 | 测试方向 |
|---------|---------|
| URL 参数 `?id=` | SQLi、XSS、LFI、SSRF |
| 表单输入 | SQLi、XSS、Commandi、逻辑漏洞 |
| 文件上传 | 文件上传漏洞、MIME 绕过 |
| Cookie / Header | 会话固定、JWT 攻击 |
| JSON API | NoSQLi、反序列化 |

### 3.2 功能点映射
- [ ] 用户系统：注册、登录、密码重置、资料修改
- [ ] 内容系统：搜索、评论、发布、编辑
- [ ] 文件系统：上传、下载、查看、删除
- [ ] 外部交互：URL 访问、Webhook、邮件发送
- [ ] 管理功能：后台管理、数据导出、配置修改

### 3.3 题目特征匹配
根据页面特征快速匹配题型：

| 页面特征 | 可能的漏洞 |
|---------|-----------|
| `?page=about.php` | LFI |
| `?id=1` 且显示数据库内容 | SQLi |
| 搜索框反射输入 | XSS / SQLi |
| `?url=` 或图片加载 | SSRF |
| 文件上传功能 | 文件上传漏洞 |
| `?data=` 且数据被反序列化 | 反序列化 |
| 用户名显示在页面上 | XSS / SSTI |
| `/visit` + `/admin` + login form | XSS bot / 会话劫持 |

---

## Phase 4: 深度探测（视情况）

### 4.1 自动化扫描
```bash
nuclei -u http://target.com -t nuclei-templates/
nikto -h http://target.com
```

### 4.2 API 端点分析
```bash
curl http://target.com/api/v1/challenges
# 检查 REST API 的认证、授权、参数注入
```

### 4.3 JavaScript 分析
```bash
# 提取所有 JS 文件中的 endpoint
katana -u http://target.com -jc
# 或手动分析 JS 中的 fetch/XHR 调用
```

搜索 JS 中的敏感信息：
- API Key / Token
- 隐藏的管理端点
- 前端路由和组件
- 调试信息和 TODO 注释

### 4.4 子域名 / 路径枚举
```bash
subfinder -d target.com
ffuf -u http://target.com/FUZZ -w wordlists/common.txt
```

---

## Phase 5: 信息整理与假设生成

### 5.1 整理发现
- [ ] 开放端口和服务列表
- [ ] 技术栈和版本信息
- [ ] 所有输入点和对应功能
- [ ] 发现的敏感文件和路径
- [ ] 错误信息和异常行为

### 5.2 生成攻击假设
基于收集到的信息，按优先级排列假设：

1. 最直接的路径（如直接暴露的 flag 文件）
2. 明显的漏洞面（如 `?id=` 参数存在 SQLi）
3. 题目描述暗示的漏洞类型
4. 技术栈已知的默认漏洞（如旧版本框架）

### 5.3 制定测试计划
对每个假设：
- 定义成功的可观测信号
- 定义失败的信号
- 准备备选路径
- 记录所有测试结果（成功/失败/异常）
