# CTF 密码学常见题型与识别

## 快速识别流程

拿到密文后，按以下顺序判断：

1. **是否是人类可读编码？** → Base64 / URL编码 / Hex / Rot13
2. **是否是古典密码？** → Caesar / Vigenere / Substitution / Bacon
3. **是否是现代对称加密？** → AES / DES / 3DES
4. **是否是非对称加密？** → RSA
5. **是否是哈希？** → MD5 / SHA1 / SHA256 / bcrypt

---

## 1. 编码识别

### Base64
- 特征：字母表 `A-Z a-z 0-9 + / =`，长度是 4 的倍数
- 快速检测：正则 `^[A-Za-z0-9+/]{4,}={0,2}$`
- 变种：Base32（只有大写字母+数字）、Base58（比特币地址）、URL-safe Base64（`-_` 替代 `+/`）

### Hex（十六进制）
- 特征：只有 `0-9 a-f`，偶数长度
- Python: `bytes.fromhex(s)`

### URL 编码
- 特征：含大量 `%XX` 序列
- Python: `urllib.parse.unquote(s)`

### Rot13
- 特征：纯字母文本，看起来像乱码但保持字母频率分布
- Python: `codecs.encode(s, 'rot_13')`

---

## 2. 古典密码

### Caesar（移位密码）
- 特征：字母被统一偏移固定位数
- 快速破解：尝试 1-25 的所有偏移，或用词频分析
- Python: `''.join(chr((ord(c)-65+k)%26+65) for c in s if c.isalpha())`

### Vigenere（维吉尼亚密码）
- 特征：多表替换，密文长度与明文相同，需要密钥
- 破解步骤：
  1. Kasiski 检验确定密钥长度
  2. 按密钥长度分组，每组做词频分析
  3. 组合得到密钥

### 仿射密码 (Affine Cipher)
- 加密公式：`E(x) = (ax + b) mod 26`
- 条件：`a` 必须与 26 互质（gcd(a,26)=1）
- 爆破：a 取值 {1,3,5,7,9,11,15,17,19,21,23,25}，b 取值 0-25

###培根密码 (Bacon's Cipher)
- 特征：只有 A 和 B 两种字符（或隐藏在其他文本中，如大小写、粗体）
- 5 位一组对应字母表

---

## 3. RSA 常见攻击

### 基本参数
- `n = p * q`（模数）
- `e`（公钥指数，通常为 65537）
- `d`（私钥指数）
- `c`（密文）

### 攻击类型速查表

| 攻击类型 | 条件 | 工具/方法 |
|---------|------|----------|
| **小公钥指数** | e=3，且 m^3 < n | 直接开立方根 |
| **共模攻击** | 同一 n，不同 e | 扩展欧几里得算法 |
| **低加密指数广播攻击** | 同一 m，多个 (n,e) 对 | 中国剩余定理 (CRT) |
| **p 或 q 过小** | n 可因数分解 | factordb.com / yafu / sage |
| **dp/dq 泄露** | 已知 dp = d mod (p-1) | 已知 dp 攻击脚本 |
| **私钥 d 过小** | d < n^0.25 | Wiener 攻击 |
| **部分密钥泄露** | 已知 p 的部分位 | Coppersmith 方法 |
| **Oracle 攻击** | 存在解密/签名 Oracle | Bleichenbacher / PKCS#1 v1.5 padding oracle |

### Wiener 攻击条件
- `d < n^0.25 / 3` 且 `q < p < 2q`
- 工具：`owiener` 库或 SageMath 脚本

### Coppersmith 攻击适用场景
- 已知明文的高位或低位（Partial Key Exposure）
-  stereotyped messages（消息前缀已知）
- 工具：SageMath `coppersmith_howgrave()`

---

## 4. AES 常见模式

### ECB 模式弱点
- 相同明文块 → 相同密文块
- 攻击：可以重排密文块、替换块
- 识别：如果图像加密后仍能看到轮廓，通常是 ECB

### CBC 模式 Padding Oracle
- 条件：服务器对错误 padding 返回不同错误信息
- 攻击：逐字节恢复明文
- 工具：`padbuster`、自定义 Python 脚本

### Bit Flipping Attack (CBC)
- 修改前一个密文块的某字节，可导致下一个明文块对应字节被翻转
- 利用：篡改 cookie、用户权限字段

---

## 5. 哈希识别与破解

### 长度特征
| 算法 | 长度 | 特征 |
|------|------|------|
| MD5 | 32 | 纯十六进制 |
| SHA1 | 40 | 纯十六进制 |
| SHA256 | 64 | 纯十六进制 |
| bcrypt | 60 | 以 `$2a$`/`$2b$`/`$2y$` 开头 |
| MySQL5 | 40 | 大写十六进制 |

### 快速破解
- 在线库：hashes.org、crackstation.net
- 本地工具：`hashcat -m 0 -a 0 hash.txt wordlist.txt`
- CTF 常见弱口令：admin、password、123456、flag、ctf、root

---

## 6. CTF Crypto 工具链

### Python 常用库
```python
from Crypto.Util.number import long_to_bytes, bytes_to_long, inverse
from Crypto.Cipher import AES
import gmpy2  # 大数运算、模逆元、开方
import owiener  # Wiener 攻击
```

### SageMath 常用功能
```python
# 因数分解
factor(n)

# 离散对数
discrete_log(mod( ciphertext, p ), mod( generator, p ))

# Coppersmith
R.<x> = Zmod(n)[]
f = x + known_part
f.small_roots(X=2^unknown_bits, beta=0.5)
```

### 在线工具
- factordb.com：大数因数分解数据库
- dcode.fr：古典密码自动识别与破解
- cryptohack.org：密码学学习平台
