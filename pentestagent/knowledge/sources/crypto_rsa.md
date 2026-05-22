# RSA

## 原理
RSA 的攻击面几乎从来不在“暴力分解一个标准 2048 位模数”，而在参数设计、密钥生成、使用方式或题面附带信息的错误。一个典型 CTF RSA 题至少要先收集 `n`、`e`、`c`，再判断是否存在多组样本、共享模数、共享素数、已知明文格式、部分私钥泄露、签名 oracle、解密 oracle 或故障样本。因为 RSA 的核心关系是 `n = p*q` 与 `ed ≡ 1 (mod φ(n))`，任何让 `p/q/d/φ(n)` 变得可恢复的条件，都会比“正面分解”容易得多。比如 `e` 过小、`d` 过小、`p` 与 `q` 过近、多个模数共享素数、同一明文用同一个小 `e` 广播到多个目标、私钥 CRT 参数 `dp/dq/qinv` 泄露、已知部分明文或格式、模数存在可预测生成缺陷，都是 CTF 高频设计点。

分析 RSA 题的第一步不是写脚本，而是做分类。先检查 `gcd(n_i, n_j)` 是否大于 1；再看 `e` 是否是常见的 `65537`、是否异常小如 3；再看是否存在同模不同指数、同明文不同模数、多个密文间的相关性；若能接触服务端，确认是加密、解密、签名还是验签场景，因为同样的数学关系在 oracle 下会产生完全不同的利用链。很多题其实不需要“完全拿私钥”，而只需要复原一个消息、伪造一次签名、还原一个中间参数即可。判断结构正确以后再落脚到 `RsaCtfTool`、Sage、`gmpy2`、连分数、CRT、Coppersmith，效率会高很多。

## 工具与命令示例
```bash
# 1) 用 RsaCtfTool 自动跑常见攻击
RsaCtfTool --publickey pub.pem --private --attack all

# 2) 检查多个模数是否共享素数
python -c "import math; ns=[int(x.strip()) for x in open('n.txt')];
from itertools import combinations
for a,b in combinations(ns,2):
 g=math.gcd(a,b)
 if g!=1: print('shared factor=',g)"

# 3) 用 gmpy2 直接开 e 次根，适合 low-e 无模回绕
python -c "import gmpy2; c=int(open('c.txt').read()); print(gmpy2.iroot(c,3))"

# 4) Wiener attack，适合 d 很小的私钥
RsaCtfTool --publickey pub.pem --attack wiener

# 5) 用 openssl 查看公钥参数
openssl rsa -pubin -in pub.pem -text -noout

# 6) Sage/Python 中求模逆
python -c "e=65537; phi=1234567891; print(pow(e,-1,phi))"

# 7) common modulus 题常用扩展欧几里得
python -c "import gmpy2; e1,e2=17,65537; print(gmpy2.gcdext(e1,e2))"

# 8) 用 factordb 查询小模数或异常模数线索
python -c "import requests; n=open('n.txt').read().strip(); print(requests.get(f'https://factordb.com/api?query={n}').text)"
```

## 常见 CTF 题型
### 题型一：小指数 `e=3` 与明文过短
思路：若 `m^e < n`，密文实际上就是普通整数幂，没有发生模回绕，直接开三次根即可。很多题会加一点填充或前缀，需结合已知格式调整。

```python
import gmpy2
c = 74088
m, exact = gmpy2.iroot(c, 3)
print(m, exact)
if exact:
    print(bytes.fromhex(hex(int(m))[2:]))
```

### 题型二：Common Modulus，同模不同指数
思路：同一个 `n` 被不同公钥指数 `e1/e2` 用来加密同一明文时，只要 `gcd(e1,e2)=1`，可用扩展欧几里得求出系数 `a,b`，进而恢复 `m`。这是 CTF 非常经典的数学直出题。

```python
import gmpy2
n = 0xD5B1
e1, e2 = 17, 65537
c1, c2 = 0x1234, 0x5678
g, a, b = gmpy2.gcdext(e1, e2)
assert g == 1
m = (pow(c1, a, n) * pow(c2, b, n)) % n if a >= 0 and b >= 0 else None
print(m)
```

### 题型三：广播攻击 Hastad
思路：同一消息用相同的小指数 `e` 加密到多个互素模数，只要样本数量达到 `e` 个，就能用中国剩余定理合并出 `m^e`，再开根恢复明文。

```python
from sympy.ntheory.modular import crt
import gmpy2
mods = [n1, n2, n3]
cts = [c1, c2, c3]
M, _ = crt(mods, cts)
m, exact = gmpy2.iroot(int(M), 3)
print(m, exact)
```

### 题型四：Wiener/近质数/共享素数
思路：若 `d` 太小，可用连分数恢复；若 `p`、`q` 很接近，费马分解非常快；若多模数共享一个素因子，`gcd` 一步出私钥。此类题关键在快速分类，而不是先入为主只跑一种攻击。

```python
import math
n = 0
a = math.isqrt(n)
while a*a < n:
    a += 1
b2 = a*a - n
b = math.isqrt(b2)
if b*b == b2:
    print(a-b, a+b)
```

## 绕过与进阶技巧
- **先做结构检查**：同模、同明文、共享素数、低指数、近质数这几类检查成本极低，应先于复杂格攻击。
- **不要盲跑 all**：自动化工具有用，但在样本量多时，先做人类分类能更快锁定方向。
- **已知明文格式**：`flag{`、ASN.1 头、固定协议字段常能把“模糊可行”变成可验证攻击，尤其对 Coppersmith/相关消息题很重要。
- **签名与加密场景区分**：一些题给的是“签名服务”或“验签逻辑”，这时要考虑低公钥指数、CRT 故障、Bleichenbacher/Manger 类 oracle，而不是只盯 `c`。
- **多组样本优先做 gcd**：共享素数题非常高频，`gcd` 基本零成本，别漏。
- **部分密钥泄露**：已知 `dp/dq`、私钥高位、`p` 高位/低位、随机源弱化，都可能走 Coppersmith 或枚举恢复。
- **大整数转换**：CTF 经常把消息编码为十六进制、十进制字符串或 `bytes_to_long()`，解出后别忘了正确转字节并处理前导零。
- **Oracle 题稳住边界**：若服务可重复调用，先确认错误类型、填充规则、速率限制，再决定是否做自适应查询，不要一次性把攻击面想复杂。
- **数值验证**：恢复出 `p/q/d/m` 后务必回代验证，例如检查 `pow(m,e,n)==c` 或 `p*q==n`，防止误中伪解。

## 快速检查清单
- [ ] 是否已收集完整的 `n`、`e`、`c` 以及所有相关样本
- [ ] 多个模数之间是否已做 `gcd`，排查共享素数
- [ ] `e` 是否异常小，是否可直接开根或做广播攻击
- [ ] 是否存在同模不同指数、同明文多模数、相关消息结构
- [ ] `p` 与 `q` 是否接近，是否值得尝试费马分解
- [ ] 是否泄露了 `dp/dq/d`、`p/q` 的高低位、签名故障样本
- [ ] 当前题是加密、解密、签名还是验签场景
- [ ] 明文是否有已知格式，如 `flag{`、协议头、ASN.1 前缀
- [ ] 自动化工具给出的结果是否已经回代验证
- [ ] 是否存在比“拿私钥”更短的得分路径，例如直接恢复消息或伪造一次签名
