# Local Challenge Log Pivot — Minimal Design

## 背景

真实 `easy_login` 题目位于本地 challenge 目录，包含：

- `docker-compose.yml`
- 应用源码
- 可启动容器

此前 CTF dispatcher 已经能基于运行时证据识别 `/visit + /admin` 形态，并在黑盒 `visit-url` exploit 失败后 truthful stop。但真实题进一步表明：

- 纯黑盒 bot-XSS 会被跨域边界阻断
- 题目本身又暴露了更强的本地证据面
- 例如 `src/server.ts` 会把 admin password 打到容器日志中

因此，下一个高价值能力不是继续扩展黑盒 payload，而是让 agent 在“本地题包 / compose / 源码可得”的上下文里，能够主动 pivot 到本地资产与日志。

## 目标

本次只实现一个最小闭环：

1. 从 `hint` 中识别本地 challenge 路径
2. 在该路径下发现 `docker-compose.yml`
3. 读取 compose logs
4. 从日志中提取可直接复用的 credential
5. 复用现有 HTTP 路径执行：
   - `/login`
   - `/admin`
6. 获得 verified flag

## 非目标

本次不做：

- 通用源码审计框架
- 压缩包自动解压总线
- 容器内任意命令编排
- 多题型通用本地资产探针
- 针对所有日志格式的 credential parser

## 最小合同

### 输入

- `target`: 当前题目 URL，例如 `http://127.0.0.1:3000`
- `hint`: 包含本地题目目录的文本，例如绝对路径
- 当前页面已通过 recon 拿到 auth form 与 `/admin` 线索

### 输出

若日志中存在明确凭据，例如：

- `Admin password set to: <secret>`

则 dispatcher 应：

1. 识别 `admin / <secret>`
2. POST 登录
3. 使用返回的 sid / cookie 请求 `/admin`
4. 命中 flag 时返回成功的 `_ChainOutcome`

若未命中路径、compose 文件或凭据，则：

- 返回 `progress=False`
- 不伪造 success
- 继续走原有链路

## 放置位置

先放在：

- `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_dispatcher.py`

以一个薄 helper / 薄策略存在，不引入新的大层级。

## 触发条件

本轮最小触发条件：

1. `hint` 中包含可解析的本地 challenge 目录
2. 该目录下存在 `docker-compose.yml`
3. 当前题目存在 auth form
4. 当前题目存在 `/admin` 之类明确的 post-auth 高价值端点

## 最小实现草图

```text
_execute_xss_chain(...)
  -> 尝试 local challenge log pivot
      -> 从 hint 提取 challenge path
      -> 检查 docker-compose.yml
      -> docker compose logs --no-color
      -> 提取 admin password
      -> POST /login
      -> GET /admin
      -> verify flag
  -> 若未闭环，再继续现有 stored-xss / visit-url 路径
```

## 风险与约束

### 风险 1：hint 路径解析过宽
控制方式：

- 本轮只接受明确的本地目录路径
- 且必须存在 `docker-compose.yml`

### 风险 2：logs 命令噪声大
控制方式：

- 本轮只匹配一条窄格式：
  - `Admin password set to: ...`

### 风险 3：把本地证据面误用到远程题
控制方式：

- 没有本地目录 + compose 文件就不触发

## 测试口径

### RED 1
当：

- `hint` 提供本地 challenge path
- 该路径存在 `docker-compose.yml`
- `execute_command()` 返回带有 `Admin password set to: <secret>` 的日志
- `/login` 与 `/admin` 路径可用

则 dispatcher 应：

- 提取凭据
- 登录 admin
- 拉取 `/admin`
- 返回 verified flag

### 复验

对真实目录：

- `D:\webstudy\CTF\2026\CTF比赛题\easy_login`

在 hint 带本地路径的情况下复验，确认 agent 能从 truthful stop 升级到真实拿 flag，或至少真实命中日志凭据阶段。

## 推荐下一步

直接进入 TDD：

1. 写 failing test
2. 最小 GREEN
3. 窄回归
4. 真实 easy_login 复验
