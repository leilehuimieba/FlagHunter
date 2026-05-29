# Web Console Local Asset UI Contract — Minimal Design

## 背景

后端与 MCP ingress 已经支持结构化本地资产：

- `challengePath`
- `artifactPaths`

如果 Web Console 仍然只支持普通字段与附件上传，用户无法在前端明确：

- 给 agent 哪个题目目录
- 给 agent 哪些本地解题材料路径

这会让任务真值进入后端但无法从 UI 创建与核对。

## 目标

补齐 Web Console 最小闭环：

1. `NewTaskModal` 可以录入 `challengePath`
2. `NewTaskModal` 可以录入 `artifactPaths`
3. 提交时真值化为：
   - `challengePath: string | null`
   - `artifactPaths: string[]`
4. `Task Detail` 可以直接展示这两个字段

## 非目标

本轮不做：

- 浏览器原生目录选择器
- 路径存在性校验
- artifact metadata 扩展对象
- 将本地资产从 hint bridge 升级为新的执行签名

## 最小设计

### New Task Modal

新增两个字段：

- `challengePath`：单行输入
- `artifactPathsText`：多行输入，每行一个本地路径

提交时：

- `challengePath.trim() || null`
- `artifactPathsText` 按换行切分、`trim()`、过滤空行后得到 `artifactPaths`

### Task Detail

右侧 side panel 新增 `LocalAssetCard`：

- 有 `challengePath` 时展示 challenge path
- 有 `artifactPaths` 时逐行展示 artifact paths
- 两者都为空时不渲染该卡片

## 设计取舍

选择文本输入而不是文件系统 API：

- 浏览器环境最稳定
- 与当前后端 truth contract 完全一致
- 不把“附件上传”和“本地路径语义”混为一谈

## 验证口径

1. `NewTaskModal` 源码存在本地资产字段
2. create payload 明确标准化 `challengePath / artifactPaths`
3. `Task Detail` 存在 `LocalAssetCard`
4. 详情页展示 challenge path 与 artifact paths 文案与结构

## 下一步

这轮完成后，更值得继续的相邻主线是：

1. Tasks list 对本地资产提供轻量指示
2. CLI ingress 对 `challengePath / artifactPaths` 对齐
3. 将 Web / MCP / CLI 的本地资产桥接进一步升级成显式 `challenge_context`
