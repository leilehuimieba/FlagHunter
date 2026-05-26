# CTF 逆向工程速查

## 1. 拿到二进制后的第一步

```bash
# 基础信息
file ./challenge
strings -n 8 ./challenge | grep -iE "flag|ctf|password|key|input"

# 保护机制
checksec --file=./challenge

# 快速反汇编（无反编译器时）
r2 -q -c "aaa; s main; pdf" ./challenge
objdump -d -M intel ./challenge | grep -A 20 "<main>:"
```

## 2. 静态分析流程

### 使用 Ghidra
1. **导入文件** → 自动分析
2. **查找字符串** → Window → Defined Strings（找 "flag"、"correct"、"wrong"）
3. **交叉引用** → 右键字符串 → References → Find references to（定位使用位置）
4. **关键函数**：`main`、`check`、`validate`、`encrypt`、`decrypt`、`strcmp`、`memcmp`

### 使用 IDA Pro
- Shift+F12：字符串表
- X：交叉引用
- F5：反编译为伪代码

### 使用 radare2
```bash
r2 ./challenge
[0x00000000]> aaa          # 完整分析
[0x00000000]> afl          # 列出所有函数
[0x00000000]> iz~flag      # 找含 flag 的字符串
[0x00000000]> s sym.main   # 跳转到 main
[0x00000000]> pdf          # 打印函数反汇编
[0x00000000]> VV           # 可视化控制流图
```

## 3. 常见算法识别

### Base64
- 特征：标准 Base64 字母表字符串，或自定义变体（通常为 64 个字符的排列）
- 查找：搜索 64 字节长的常量数组

### XOR 加密
- 特征：循环中对每个字节做 `xor` 操作，密钥通常是单个字节或短字符串
- 破解：尝试所有 256 个单字节密钥，找可读文本

### RC4
- 特征：S-box 初始化（256 次 swap），然后伪随机生成密钥流
- 查找：长度为 256 的数组初始化

### AES
- 特征：S-box（256 字节常量表）、轮常量（Rcon）、4x4 状态矩阵操作
- 查找：搜索已知 AES S-box 常量

### MD5 / SHA1 / SHA256
- 特征：特定的初始化向量（IV）常量
- MD5 IV: `0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476`
- SHA1 IV: `0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0`

### 自定义虚拟机 (VM)
- 特征：一个大 switch-case 或跳转表，处理自定义字节码
- 分析：提取字节码，编写解释器或反汇编器

## 4. 动态调试

### GDB + Pwndbg
```bash
gdb ./challenge
# 常用命令
b *main           # main 断点
b *0x401234       # 地址断点
r                 # 运行
ni                # 单步（不进入函数）
si                # 单步（进入函数）
vmmap             # 内存映射
x/20gx $rsp       # 查看栈
x/s $rdi          # 查看字符串参数
```

### 输入追踪
如果程序从文件读取：
```bash
ltrace ./challenge 2>&1 | grep -iE "fopen|fread|scanf|strcmp"
strace ./challenge 2>&1 | grep -iE "open|read|write"
```

## 5. 常见 CTF 逆向模式

### 模式 1：输入验证函数
```c
int check(char *input) {
    // 对 input 进行一系列变换
    // 与硬编码的密文比较
    return strcmp(transformed, secret) == 0;
}
```
**解法**：提取 secret 和变换逻辑，逆向变换得到原始输入。

### 模式 2：迷宫 / 路径搜索
- 特征：二维数组表示迷宫，`WASD` 或方向键控制移动
- 解法：提取迷宫数据，用 BFS/DFS 找从起点到终点的路径

### 模式 3：花指令 / 混淆
- 特征：代码中插入 `jmp $+2`、无效指令、自我修改代码
- 解法：手动 patch 花指令，或用动态 trace 获取真实执行流

### 模式 4：反调试 / 反虚拟机
- 特征：检测 `ptrace`、`IsDebuggerPresent`、`vmware`、`virtualbox`
- 绕过：Patch 检测函数返回值为 0，或在虚拟机外运行

## 6. Python 反编译

### .pyc 文件
```bash
uncompyle6 file.pyc > file.py
# 或
pycdc file.pyc > file.py
```

### PyInstaller 打包的 exe
```bash
python pyinstxtractor.py challenge.exe
# 然后对提取出的 .pyc 反编译
```

## 7. 脚本辅助分析

### 快速提取所有字符串（含 Unicode）
```python
import re
with open('challenge', 'rb') as f:
    data = f.read()
    strings = re.findall(b'[\x20-\x7e]{4,}', data)
    for s in strings:
        print(s.decode('ascii', errors='ignore'))
```

### 自动化 XOR 爆破
```python
from itertools import product

def xor(data, key):
    return bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])

# 单字节爆破
cipher = bytes.fromhex('...')
for k in range(256):
    plain = xor(cipher, [k])
    if b'flag{' in plain:
        print(f"Key {k}: {plain}")
```
