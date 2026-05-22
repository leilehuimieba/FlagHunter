# Hash

## 原理
Hash 类 CTF 题的重点不在“某算法是否过时”这句抽象结论，而在系统如何使用散列值：它是做完整性校验、请求签名、密码存储、缓存键、文件去重，还是仅仅拿来比较两个输入是否“看起来一样”。安全性判断首先要看构造方式，而不是先看算法名字。比如 `HMAC(secret, msg)` 与 `sha256(secret || msg)` 的性质完全不同；`md5(file)` 用于去重和用作“授权签名”的风险也完全不同；而 PHP 中 `==` 比较 hash 字符串又会引入与密码学本身无关的弱类型问题。对 CTF 来说，最常考的三类能力是长度扩展、碰撞/前缀碰撞、弱比较或可预测签名方案。

大多数常见散列如 MD5、SHA1、SHA256 属于 Merkle–Damgård 结构，因此当应用错误地使用 `hash(secret || message)` 充当 MAC 时，攻击者可利用长度扩展在不知道 `secret` 的前提下追加数据并得到新摘要。碰撞题则考验你如何构造两份不同输入拥有相同摘要，同时尽量保持文件语义可用；弱比较题往往结合语言特性，比如 PHP 的 magic hash、仅比较前几位、大小写不敏感、去掉前导零、直接把十六进制串转数字。排查此类题时，要先问：可控的是前缀还是后缀？是否有盐？是否是 HMAC？比较是否完整？有没有现成格式和约束需要维持？

## 工具与命令示例
```bash
# 1) 长度扩展，已知旧摘要、旧消息和 secret 长度时追加参数
hashpump -s 5d41402abc4b2a76b9719d911017c592 -d "a=1" -a "&admin=1" -k 16

# 2) 计算常见 hash，先验证服务端到底用的哪种算法
python -c "import hashlib;print(hashlib.md5(b'test').hexdigest());print(hashlib.sha1(b'test').hexdigest())"

# 3) 生成 MD5 碰撞文件
fastcoll -o a.bin b.bin

# 4) 爆破短前缀碰撞，适合只比较前 N 位摘要的题
python -c "import hashlib,itertools,string
for s in map(''.join,itertools.product(string.ascii_lowercase, repeat=6)):
 h=hashlib.md5(s.encode()).hexdigest()
 if h.startswith('0000'): print(s,h); break"

# 5) 用 hashcat/JtR 破解弱密码存储
hashcat -m 0 hashes.txt rockyou.txt

# 6) 用 openssl/sha256sum 校验文件摘要
sha256sum sample.bin

# 7) 快速验证 HMAC 与简单拼接 hash 的差异
python -c "import hmac,hashlib;print(hmac.new(b'secret',b'msg',hashlib.sha256).hexdigest())"

# 8) 批量搜索源码中的危险签名写法
rg -n "md5\(|sha1\(|sha256\(|hmac|==\s*hash|substr\(.+hash" .
```

## 常见 CTF 题型
### 题型一：长度扩展伪造管理员参数
思路：服务端把签名写成 `md5(secret || query)` 或 `sha1(secret || msg)`，你已知原摘要和原消息，只差 secret 长度。枚举合理长度，生成追加 `&admin=1` 后的新消息与摘要即可。

```python
import hashpumpy
orig_sig = '5d41402abc4b2a76b9719d911017c592'
orig = 'a=1'
for k in range(8, 33):
    new_sig, new_msg = hashpumpy.hashpump(orig_sig, orig, '&admin=1', k)
    print(k, new_sig, new_msg)
```

### 题型二：MD5 碰撞文件上传
思路：平台只校验 MD5，要求两份内容不同但哈希相同的文件。先用 `fastcoll` 或 `hashclash` 生成碰撞块，再把碰撞块嵌入两份语义不同的容器文件中，例如 PDF、图片或自定义协议文件。

```python
import hashlib
for name in ['a.bin', 'b.bin']:
    data = open(name,'rb').read()
    print(name, hashlib.md5(data).hexdigest(), len(data))
```

### 题型三：PHP magic hash/弱比较
思路：服务端做 `if (md5($a) == md5($b))` 或将摘要与某值做弱类型比较，若摘要形如 `0e12345...`，PHP 会把它当科学计数法数值 0。题目关键是语言语义，不是密码学本身。

```php
<?php
var_dump(md5('QNKCDZO'));
var_dump(md5('240610708'));
var_dump(md5('QNKCDZO') == md5('240610708'));
```

### 题型四：只比前几位摘要的前缀碰撞
思路：有些题只要求命中 SHA256/MD5 的前 4~8 个十六进制字符，这时暴力成本很低。重点是控制搜索空间和验证约束，而不是误用大工具。

```python
import hashlib, itertools, string
for s in map(''.join, itertools.product(string.ascii_letters, repeat=5)):
    h = hashlib.sha256(s.encode()).hexdigest()
    if h.startswith('dead'):
        print(s, h)
        break
```

## 绕过与进阶技巧
- **先判定是否为 HMAC**：若服务端用标准 HMAC，长度扩展通常无效；不要把所有拼接哈希都误判成可扩展。
- **secret 长度枚举**：长度扩展常差最后一步 secret 长度，CTF 中 key 长度一般不大，枚举 8~64 字节往往足够。
- **碰撞不等于可利用**：生成相同摘要后，还要保证两份文件都能被目标程序接受，因此容器格式与语义保持常常比碰撞本身更难。
- **前缀碰撞与全碰撞区分**：只比摘要前几位时，暴力更直接；别为简单题引入过重工具链。
- **magic hash 语言差异**：`0e...` 弱比较是 PHP 经典坑，在 Python/Go/Java 中并不会自动成立，要基于运行时证据判断。
- **截断比较**：只比较前 4/8/16 位或转成整数比较，都会显著降低碰撞难度，是 CTF 高频设计点。
- **签名拼接顺序**：`hash(secret||msg)` 与 `hash(msg||secret)` 的性质不同；有些题虽然不受长度扩展影响，但可通过可预测 secret、时间戳或拼接歧义伪造。
- **密码存储题**：若题目给的是数据库 dump，优先判断是否无盐 MD5/SHA1、是否有用户名规律、是否可字典攻击，不要先想复杂。
- **文件校验绕过**：系统若只校验上传时摘要，后续内容还能变，或只比“客户端提交的 hash 值”，那问题就可能已经不是密码学而是业务逻辑。

## 快速检查清单
- [ ] 服务端使用的是 HMAC 还是简单拼接 hash
- [ ] 可控位置在消息前缀、后缀还是中间，是否影响长度扩展/碰撞可行性
- [ ] 比较逻辑是否完整，是否只比较前几位、忽略大小写或弱类型比较
- [ ] 是否存在 PHP `0e...`、整数转换、字符串截断等语言层陷阱
- [ ] 是否已验证摘要算法与编码方式（hex/base64/raw bytes）
- [ ] 长度扩展场景下，secret 长度是否已枚举验证
- [ ] 碰撞题中，两份文件是否都满足业务语义和格式约束
- [ ] 密码存储题是否先排查无盐弱 hash 与字典规律
- [ ] 源码中是否存在手写签名、拼接顺序错误或客户端可控 hash
- [ ] 是否存在比密码学攻击更短的利用路径，例如业务逻辑绕过或比较实现缺陷
