# Local Zip Artifact Challenge Root Resolution — Minimal Design

## 背景

当前本地 challenge 目录输入已经可闭环：

- `challengePath` 可直接命中 challenge root
- strong runtime flag 可在本地 challenge 场景下自动 verified

但如果用户只提供：

- 本地 `.zip` 压缩包路径

dispatcher 还不能把它解析成 challenge root。

## 目标

当 `artifactPaths` 中存在本地 zip 包时：

1. 识别 zip
2. 解压到临时目录
3. 在解压树中查找 `docker-compose.yml`
4. 其所在目录作为 challenge root

## 非目标

本轮不做：

- `.tar.gz` / `.7z` / `.rar` 全格式支持
- 长期缓存解压结果
- 显式 challenge_context dataclass
- 通用本地文件取证框架

## 最小设计

### helper 行为

在 `_extract_local_challenge_root_from_hint(hint)` 中：

- 若候选路径是 `docker-compose.yml` 文件，仍直接返回其父目录
- 若候选路径是本地 `.zip` 文件，则调用本地 archive helper：
  - 解压到 `tempfile.mkdtemp(...)`
  - 递归搜索 `docker-compose.yml`
  - 首个命中的 compose 所在目录即 challenge root

### 安全边界

最小过滤：

- 忽略绝对路径成员
- 忽略包含 `..` 的 archive member

## 验证口径

1. zip-only artifact path 可解析出 challenge root
2. challenge root 下存在解压后的 `docker-compose.yml`
3. CLI zip-only headless smoke 能在真实 `easy_login` 上拿到 verified flag

## 下一步

这轮完成后，更值得继续的是：

1. 扩到 `.tar.gz` / `.7z`
2. 统一本地 challenge 目录、压缩包、远端下载件到显式 `challenge_context`
3. 做“只给压缩包 / 只给题目链接”的小型 regression eval pack
