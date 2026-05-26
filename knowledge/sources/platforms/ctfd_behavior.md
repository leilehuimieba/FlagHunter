# CTFd 平台行为与题目特征

## 平台识别

- 域名特征：常含 `ctf`、`challenge`、`pwn`、`web`
- 页面特征：顶部导航栏有 Challenges、Scoreboard、Notifications
- API 端点：`/api/v1/challenges`、`/api/v1/scoreboard`
- Cookie：`session`（Flask session）

## 常见题目模式

### Web 题型
- 单页面单漏洞（SQLi、XSS、RCE、SSTI、反序列化）
- 源码泄露（.git、备份文件、注释中的提示）
- Admin Bot 类：需要构造 XSS 让 bot 访问并触发操作
- 多层漏洞链：如 LFI → Log Poisoning → RCE

### Crypto 题型
- 加密脚本 + 密文，要求解密
- Oracle 类：提供加密/解密服务，要求利用 Oracle 恢复明文
- 共享模数、小公钥指数、已知明文攻击

### Pwn 题型
- 远程服务（nc target port）
- 提供二进制文件下载
- 通常需要：泄露 libc → 计算 one_gadget / system 地址 → getshell

### Reverse 题型
- 提供二进制文件
- 输入验证型：输入正确 flag 输出 success
- VM 型：自定义字节码虚拟机

### Misc 题型
- 隐写（图片、音频、PDF）
- 流量分析（pcap 文件）
- 取证（磁盘镜像、内存 dump）

## Flag 提交 API

```bash
# CTFd 标准提交端点
POST /api/v1/challenges/attempt
Content-Type: application/json

{"challenge_id": 1, "submission": "flag{xxx}"}

# 响应
{"success": true, "data": {"status": "correct", "message": "Correct"}}
{"success": true, "data": {"status": "incorrect", "message": "Incorrect"}}
```

## 计分板特征

- 动态积分制：解出人数越多，分值越低
- 血（First Blood）：第一个解出某题的用户
- 隐藏题：需要解出前置题目才能解锁

## 自动化策略

1. **批量提交**：对 candidate_flags 批量调用提交 API
2. **状态监控**：轮询 `/api/v1/challenges` 获取已解锁题目
3. **分数跟踪**：通过 `/api/v1/scoreboard` 监控竞争状态
