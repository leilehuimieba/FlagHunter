# Advanced Reverse Engineering Techniques for CTF

> VM analysis, deobfuscation, dynamic analysis with Frida, and automated reversing with angr/Ghidra scripts.

---

## 1. VM (Virtual Machine) Analysis

Many CTF challenges implement custom virtual machines. The binary contains a bytecode interpreter and a hidden bytecode program.

### 1.1 VM Structure Recognition

Look for these patterns in disassembly/decompilation:

```c
// Classic VM loop
def opcode_handlers = [...];  // Array of function pointers
while (running) {
    byte opcode = bytecode[pc++];
    int op1 = bytecode[pc++];
    int op2 = bytecode[pc++];
    opcode_handlers[opcode](op1, op2);
}
```

**Key indicators**:
- Large `switch` statement or function pointer table
- `pc` (program counter) variable that increments
- `sp` (stack pointer) manipulating a memory array
- `regs[]` array for virtual registers
- `memory[]` array for VM RAM

### 1.2 VM Reversing Workflow

1. **Identify VM components**: PC, SP, registers, memory, opcode table
2. **Dump bytecode**: Find where bytecode is loaded/stored
3. **Analyze opcode handlers**: Map each opcode number to its behavior
4. **Write disassembler**: Python script to print human-readable bytecode
5. **Trace execution**: Add logging to understand control flow
6. **Find vulnerability**: Usually a bounds check missing in memory operations
7. **Exploit**: Craft malicious bytecode or find the flag in bytecode constants

### 1.3 Common VM Opcodes

| Opcode | Typical Behavior | Vulnerability |
|--------|-----------------|---------------|
| `PUSH imm` | `stack[sp++] = imm` | — |
| `POP reg` | `regs[reg] = stack[--sp]` | — |
| `ADD` | `stack[sp-2] += stack[sp-1]` | — |
| `LOAD reg, addr` | `regs[reg] = memory[addr]` | **OOB read** |
| `STORE addr, reg` | `memory[addr] = regs[reg]` | **OOB write** |
| `JMP addr` | `pc = addr` | — |
| `JZ addr` | `if (stack[--sp] == 0) pc = addr` | — |
| `CALL addr` | `stack[sp++] = pc; pc = addr` | — |
| `RET` | `pc = stack[--sp]` | — |
| `GETC` | `stack[sp++] = getchar()` | — |
| `PUTC` | `putchar(stack[--sp])` | — |

### 1.4 Automated VM Solving with angr

If the VM interprets bytecode, you can often symbolize the bytecode or VM state:

```python
import angr, claripy

proj = angr.Project("./vm_binary")

# Symbolize the bytecode input
bytecode = claripy.BVS("bytecode", 8 * 100)

# Hook the VM interpreter to inject symbolic bytecode
# Or symbolize the comparison at the end
```

---

## 2. Deobfuscation Techniques

### 2.1 Control Flow Flattening (控制流平坦化)

**识别特征**:
- Large `switch` with a dispatcher variable
- All basic blocks connect to a central dispatcher
- Original control flow is encoded in a state machine

**Ghidra 反平坦化**:
```python
# Ghidra script
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

def deflatten_function(func):
    decomp = DecompInterface()
    decomp.openProgram(currentProgram)
    results = decomp.decompileFunction(func, 30, ConsoleTaskMonitor())
    # Analyze the decompiled code, identify state variable
    # Map states to basic blocks, reconstruct original CFG
```

**自动化工具**:
- `d810` (Ghidra plugin): https://github.com/p首yorg/d810
- `SREmc` (binary ninja): Control flow deobfuscation
- `angr` symbolic execution: Execute symbolically to find real paths

### 2.2 String Encryption

**识别**: Encrypted strings decrypted at runtime.

**Ghidra 脚本批量解密**:
```python
# Identify decrypt function by cross-references
# Hook decrypt function in angr/frida
# Dump all decrypted strings

import angr

proj = angr.Project("./binary")

# Hook the decrypt function
@proj.hook(decrypt_func_addr)
def decrypt_hook(state):
    # Read encrypted string pointer from argument
    ptr = state.regs.rdi
    length = state.regs.rsi
    enc = state.memory.load(ptr, length)
    print(f"Encrypted: {enc}")
    # Let original function execute
```

**Frida 动态 dump**:
```javascript
Interceptor.attach(Module.findExportByName(null, "decrypt_string"), {
    onEnter: function(args) {
        console.log("Decrypt called with:", Memory.readUtf8String(args[0]));
    },
    onLeave: function(retval) {
        console.log("Decrypted:", Memory.readUtf8String(retval));
    }
});
```

### 2.3 Import Hashing / API Hashing

Malware/obfuscated binaries resolve APIs by hash instead of name.

**识别**: No import table, but calls to `GetProcAddress` or manual PE parsing.

**绕过**: Let the program run to the point where hashes are resolved, then dump the resolved addresses.

```python
# Using frida
import frida

code = """
Interceptor.attach(Module.findExportByName("kernel32.dll", "GetProcAddress"), {
    onEnter: function(args) {
        this.name = Memory.readUtf8String(args[1]);
    },
    onLeave: function(retval) {
        console.log(this.name + " @ " + retval);
    }
});
"""

process = frida.attach("target.exe")
script = process.create_script(code)
script.load()
```

### 2.4 Anti-Debug Detection

**常见反调试技术**:
- `IsDebuggerPresent()`
- `CheckRemoteDebuggerPresent()`
- `NtGlobalFlag` (PEB+0x68)
- `Heap.Flags` and `Heap.ForceFlags`
- `INT3` / `ICE` breakpoint detection
- Timing checks (`rdtsc`, `QueryPerformanceCounter`)
- Parent process check (tracer/debugger usually has specific PPID)

**绕过方法**:
```bash
# Patch binary to nop out checks
# Use x64dbg / GDB with anti-anti-debug plugins
# Frida hook anti-debug functions
```

Frida 通用反调试绕过:
```javascript
// Hook IsDebuggerPresent
Interceptor.replace(Module.findExportByName("kernel32.dll", "IsDebuggerPresent"), 
    new NativeCallback(function() { return 0; }, "int", []));
```

---

## 3. angr 实战高级技巧

### 3.1 Avoiding Path Explosion

```python
import angr

proj = angr.Project("./binary")
state = proj.factory.entry_state()
simgr = proj.factory.simulation_manager(state)

# Use exploration techniques to limit paths
simgr.use_technique(angr.exploration_techniques.DFS())  # Depth-first
simgr.use_technique(angr.exploration_techniques.LoopSeer(bound=2))  # Loop bound

# Find target, avoid anti-debug checks
simgr.explore(
    find=0x401234,
    avoid=[0x401000, 0x401100]  # Anti-debug / failure paths
)
```

### 3.2 Hooking Functions

```python
import angr

proj = angr.Project("./binary")

# Skip complex library functions
@proj.hook(0x401000)
def skip_strlen(state):
    state.regs.rax = state.regs.rdi  # Return string length = argument
    state.regs.rip = state.stack_read(state.regs.rsp, 8)
    state.regs.rsp += 8

# Or use call state with custom SimProcedure
class MyGets(angr.SimProcedure):
    def run(self, buf, size):
        data = self.state.solver.BVS("input", 8 * 64)
        self.state.memory.store(buf, data)
        return size

proj.hook_symbol("gets", MyGets())
```

### 3.3 Symbolic File System

```python
import angr
from angr.sim_type import SimTypeFd, SimTypeChar

proj = angr.Project("./binary")
state = proj.factory.entry_state(stdin=angr.SimFileStream(name='stdin', content=angr.claripy.BVS('stdin', 8*100)))
```

### 3.4 Constraint Solving Tricks

```python
import angr, claripy

# Add constraints on symbolic input
flag = claripy.BVS("flag", 8 * 32)

# Flag starts with "flag{"
for i, c in enumerate(b"flag{"):
    state.solver.add(flag.get_byte(i) == c)

# Printable ASCII only
for i in range(32):
    b = flag.get_byte(i)
    state.solver.add(b >= 0x20)
    state.solver.add(b <= 0x7e)

# Run and get solution
simgr = proj.factory.simulation_manager(state)
simgr.explore(find=0x401234)
if simgr.found:
    solution = simgr.found[0].solver.eval(flag, cast_to=bytes)
```

---

## 4. Ghidra 脚本自动化

### 4.1 Headless Analysis Script

```bash
# Run Ghidra headless analysis
/opt/ghidra/support/analyzeHeadless \
    /tmp/ghidra_project \
    MyProject \
    -import ./binary \
    -postScript /path/to/script.py \
    -scriptPath /path/to/scripts \
    -deleteProject
```

### 4.2 Auto-Rename Functions by String References

```python
# Ghidra Python script
from ghidra.program.model.symbol import SourceType

string_mgr = currentProgram.getListing().getDataIterator(
    currentProgram.getMemory().getLoadedAndInitializedAddress(), True
)

for s in string_mgr:
    if s.getDataType().getName() == "string":
        str_val = s.getValue()
        refs = getReferencesTo(s.getAddress())
        for ref in refs:
            func = getFunctionContaining(ref.getFromAddress())
            if func and func.getName().startswith("FUN_"):
                new_name = "func_using_" + str_val[:20]
                func.setName(new_name, SourceType.USER_DEFINED)
```

### 4.3 Extract All Decompiled Functions

```python
from ghidra.app.decompiler import DecompInterface

decomp = DecompInterface()
decomp.openProgram(currentProgram)

for func in currentProgram.getFunctionManager().getFunctions(True):
    results = decomp.decompileFunction(func, 30, None)
    if results.decompileCompleted():
        print(f"// {func.getName()}")
        print(results.getDecompiledFunction().getC())
```

---

## 5. Frida 动态分析

### 5.1 Hook Specific Function

```javascript
// frida_script.js
Interceptor.attach(Module.findExportByName(null, "strcmp"), {
    onEnter: function(args) {
        console.log("strcmp:", Memory.readUtf8String(args[0]), "vs", Memory.readUtf8String(args[1]));
    }
});
```

### 5.2 Memory Scan and Patch

```javascript
// Search for pattern in memory
Memory.scan(ptr("0x400000"), 0x100000, "48 8b ?? ??", {
    onMatch: function(addr, size) {
        console.log("Pattern at:", addr);
        // Patch: nop out instruction
        Memory.patchCode(addr, 2, function(code) {
            code.writeByteArray([0x90, 0x90]);
        });
    }
});
```

### 5.3 Trace All Function Calls

```javascript
// Trace all calls in a module
var module = Process.findModuleByName("target.so");
module.enumerateExports().forEach(function(exp) {
    if (exp.type === "function") {
        Interceptor.attach(exp.address, {
            onEnter: function(args) {
                console.log("Called:", exp.name);
            }
        });
    }
});
```

### 5.4 Python Frida Script

```python
import frida
import sys

code = """
Interceptor.attach(Module.findExportByName(null, "check_flag"), {
    onEnter: function(args) {
        console.log("Flag check input:", Memory.readUtf8String(args[0]));
    },
    onLeave: function(retval) {
        console.log("Result:", retval);
    }
});
"""

def on_message(message, data):
    print(message)

process = frida.spawn(["./binary"])
session = frida.attach(process)
script = session.create_script(code)
script.on("message", on_message)
script.load()
frida.resume(process)
sys.stdin.read()
```

---

## 6. 固件 / 嵌入式分析

### 6.1 Binwalk 提取

```bash
binwalk -e firmware.bin              # 自动提取
binwalk -M firmware.bin              # 递归提取
binwalk -Y firmware.bin              # 识别文件签名
```

### 6.2 QEMU 模拟运行

```bash
# ARM binary on x86
qemu-arm -L /usr/arm-linux-gnueabihf ./arm_binary

# ARM with strace
qemu-arm -strace ./arm_binary
```

### 6.3 Cross-Architecture angr

```python
import angr

proj = angr.Project("./arm_binary", arch="ARMEL")
state = proj.factory.entry_state()
```

---

## 7. 常见 CTF Reverse Patterns

| Pattern | Recognition | Tool/Technique |
|---------|-------------|----------------|
| Custom VM | Large switch + bytecode array | Dump bytecode, write disassembler |
| Control flow flattening | Central dispatcher + state variable | angr symbolic exec, d810 plugin |
| String encryption | Encrypted blobs decrypted at runtime | Frida hook decrypt function |
| Self-modifying code | `mprotect` + runtime patch | Dynamic analysis, dump after unpacking |
| UPX/VMProtect packer | High entropy, small import table | UPX -d, or dump from memory |
| Anti-debug | `IsDebuggerPresent`, timing checks | Frida patch, x64dbg ScyllaHide |
| Z3 constraint solver | Complex boolean conditions | angr or direct z3 solving |
| Flag hidden in constants | Hardcoded byte arrays | strings, xref analysis |
| RC4/AES hidden in binary | T-boxes, S-boxes | Find crypto constants (r2 or manual) |
| Fork-based challenge | `fork()` in main | Brute force byte-by-byte |
