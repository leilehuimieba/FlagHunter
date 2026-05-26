# HackTheBox 平台行为

## 机器类型

| 类型 | 说明 | 难度 |
|------|------|------|
| **Starting Point** | 入门级，带详细教程 | 简单 |
| **Machines** | 独立虚拟机 | 简单/中等/困难/疯狂 |
| **Challenges** | 分类挑战（Web/Pwn/Crypto/Reverse/Misc/Forensics/Mobile/OSINT） | 各难度 |
| **Pro Labs** | 企业级 AD 网络 | 专业 |
| **Battlegrounds** | 实时对战 | 竞技 |

## 机器生命周期

1. **Spawn**：启动实例（约 2-5 分钟）
2. **Enumeration**：端口扫描、服务识别
3. **Initial Access**：利用漏洞获取 user shell
4. **Privilege Escalation**：从 user 提升到 root
5. **Capture Flags**：`user.txt`（/home/user）和 `root.txt`（/root）

## 常见端口服务

```
22   - SSH（通常有密钥认证或密码爆破）
80   - HTTP（Web 应用，主要攻击面）
443  - HTTPS
445  - SMB（Windows，枚举共享、空会话）
3306 - MySQL
3389 - RDP（Windows 远程桌面）
8080 - 备用 Web（Tomcat/Jenkins/Proxy）
```

## 攻击路径模式

### Linux 机器典型路径
```
Web 服务漏洞 → 反向 Shell → 用户 Shell → SUID/sudo 提权 → Root
```

### Windows 机器典型路径
```
SMB 枚举 → 共享访问/密码喷洒 → 用户 Shell →
WinPEAS 枚举 → 服务滥用/内核漏洞/Token 模拟 → SYSTEM
```

## Active Directory (AD) 专项

### 常见攻击链
1. **LLMNR/NBT-NS 投毒**：Responder 捕获 NTLM hash
2. **SMB Relay**：将捕获的 hash relay 到其他机器
3. **Kerberoasting**：请求 SPN 的服务票据，离线破解
4. **AS-REP Roasting**：不需要预认证的账户，离线破解
5. **BloodHound**：AD 关系图谱分析，寻找最短攻击路径
6. **DCSync**：模拟域控制器同步密码 hash
7. **Golden Ticket**：伪造 KRBTGT 的 TGT

### 关键工具
```bash
# 信息收集
enum4linux -a target.com
ldapsearch -x -H ldap://target.com -b "dc=target,dc=com"

# BloodHound
collection: SharpHound.exe -c All
analysis: BloodHound.py + Neo4j

# Kerberoasting
GetUserSPNs.py domain/user:password -dc-ip 10.10.10.10 -request

# 密码喷洒
crackmapexec smb 10.10.10.0/24 -u users.txt -p passwords.txt
```

## HTB 与 CTF 的差异

| 维度 | CTF | HTB |
|------|-----|-----|
| 目标 | 获取 flag{...} | 获取 user.txt + root.txt |
| 环境 | 容器/简化环境 | 完整操作系统 |
| 稳定性 | 可能不稳定 | 较稳定 |
| 工具限制 | 通常无 | 通常无 |
| 写报告 | 不需要 | 需要详细 writeup |
| 防火墙 | 通常无 | 可能有 outbound 限制 |
