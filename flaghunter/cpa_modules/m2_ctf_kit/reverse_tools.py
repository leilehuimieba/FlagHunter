"""
FlagHunter M2 CTF Kit - 逆向工程工具封装模块

基于 radare2 / r2pipe 的二进制分析、反汇编、反编译、字符串提取、补丁等能力。
所有接口均为异步，返回 ReverseResult 结果对象，不抛异常。使用延迟加载模式。
"""
from __future__ import annotations
import asyncio
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_R2PIPE_AVAILABLE: bool = False
_r2pipe_module: Any = None
_r2: Any = None
_KEY_FUNCS = {"main", "win", "flag", "get_shell", "system", "execve", "gets", "strcpy",
              "sprintf", "scanf", "printf", "puts", "read", "write", "open", "malloc",
              "free", "memcpy", "memmove", "strncpy", "fgets"}


def _get_r2pipe() -> Any:
    """延迟导入 r2pipe；失败返回 None。"""
    global _R2PIPE_AVAILABLE, _r2pipe_module
    if "_r2pipe_module" not in globals() or _r2pipe_module is None:
        try:
            import r2pipe  # type: ignore[import-untyped]
            _r2pipe_module = r2pipe
            _R2PIPE_AVAILABLE = True
        except ImportError:
            _r2pipe_module = None
            _R2PIPE_AVAILABLE = False
    return _r2pipe_module


def _ensure_r2pipe() -> bool:
    """检查 r2pipe 是否可用。"""
    return _get_r2pipe() is not None


def _get_r2() -> Any:
    """获取当前 r2pipe 会话。"""
    global _r2
    return _r2


def _set_r2(r2: Any) -> None:
    """设置当前 r2pipe 会话。"""
    global _r2
    _r2 = r2


@dataclass
class ReverseResult:
    """逆向操作结果容器，success=False 时 error 说明原因，不抛异常。"""
    success: bool
    output: str = ""
    error: str = ""
    strings: List[str] = field(default_factory=list)
    functions: List[dict] = field(default_factory=list)
    disassembly: str = ""
    decompiled: str = ""
    protections: dict = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)


def _check_r2() -> ReverseResult:
    """检查 r2pipe 及会话是否就绪。"""
    if not _ensure_r2pipe():
        return ReverseResult(success=False, error="r2pipe 未安装: pip install r2pipe")
    if _get_r2() is None:
        return ReverseResult(success=False, error="radare2 会话未建立，请先调用 rev_analyze()")
    return ReverseResult(success=True)


def _get_protections(binary_path: str) -> dict:
    """解析二进制保护机制（NX/PIE/Canary/RELRO/Fortify）。"""
    protections: Dict[str, Any] = {"NX": False, "PIE": False, "Canary": False, "RELRO": "No", "Fortify": False}
    r2 = _get_r2()
    if r2 is None:
        return protections
    try:
        for line in r2.cmd("iI").splitlines():
            ll = line.lower()
            if "nx" in ll:
                protections["NX"] = "true" in ll or "enabled" in ll
            elif "pie" in ll or "pic" in ll:
                protections["PIE"] = "true" in ll or "enabled" in ll
            elif "canary" in ll:
                protections["Canary"] = "true" in ll or "enabled" in ll
            elif "relro" in ll:
                protections["RELRO"] = "Full" if "full" in ll else "Partial" if "partial" in ll else "No"
            elif "fortify" in ll:
                protections["Fortify"] = "true" in ll or "enabled" in ll
    except Exception:
        pass
    return protections


async def rev_analyze(binary_path: str) -> ReverseResult:
    """对二进制文件进行完整静态分析。打开 r2 会话执行 aaa，收集保护机制、
    文件信息、导入/导出函数、字符串列表及函数列表，并生成安全建议。"""
    if not _ensure_r2pipe():
        return ReverseResult(success=False, error="r2pipe 未安装: pip install r2pipe")
    if not os.path.isfile(binary_path):
        return ReverseResult(success=False, error=f"文件不存在: {binary_path}")
    r2 = _get_r2()
    if r2 is not None:
        try:
            r2.quit()
        except Exception:
            pass
    try:
        r2 = _get_r2pipe().open(binary_path)
        _set_r2(r2)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: r2.cmd("aaa"))
        info_out = await loop.run_in_executor(None, lambda: r2.cmd("iI"))
        protections = _get_protections(binary_path)
        strings_out = await loop.run_in_executor(None, lambda: r2.cmd("izz"))
        strings_list = [line.strip() for line in strings_out.splitlines() if line.strip()]
        funcs_out = await loop.run_in_executor(None, lambda: r2.cmd("afl"))
        functions = []
        for line in funcs_out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3:
                functions.append({"address": parts[0], "size": int(parts[1]) if parts[1].isdigit() else 0,
                                  "name": parts[-1], "key": any(kf in parts[-1] for kf in _KEY_FUNCS)})
        imports_out = await loop.run_in_executor(None, lambda: r2.cmd("ii"))
        exports_out = await loop.run_in_executor(None, lambda: r2.cmd("iE"))
        output = f"[*] 文件信息:\n{info_out}\n\n[*] 导入函数:\n{imports_out}\n\n[*] 导出函数:\n{exports_out}\n\n[*] 发现 {len(functions)} 个函数, {len(strings_list)} 条字符串"
        suggestions = []
        if not protections.get("NX"):
            suggestions.append("NX 未启用，栈上代码可执行，考虑 shellcode 注入")
        if not protections.get("Canary"):
            suggestions.append("Stack Canary 未启用，可能存在缓冲区溢出")
        if protections.get("RELRO") == "No":
            suggestions.append("RELRO 未启用，可考虑 GOT 覆写攻击")
        if not protections.get("PIE"):
            suggestions.append("PIE 未启用，地址固定，可利用硬编码地址")
        return ReverseResult(success=True, output=output, strings=strings_list,
                             functions=functions, protections=protections, suggestions=suggestions)
    except Exception as exc:
        return ReverseResult(success=False, error=f"分析失败: {exc}")


async def rev_strings(binary_path: str, min_length: int = 4) -> ReverseResult:
    """提取二进制文件中的所有可打印字符串。"""
    check = _check_r2()
    if not check.success:
        result = await rev_analyze(binary_path)
        if not result.success:
            return result
    try:
        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, lambda: _get_r2().cmd(f"izz~{min_length}"))
        slist = [line.strip() for line in out.splitlines() if line.strip() and len(line.strip()) >= min_length]
        return ReverseResult(success=True, output=f"提取到 {len(slist)} 条长度 >= {min_length} 的字符串", strings=slist)
    except Exception as exc:
        return ReverseResult(success=False, error=f"字符串提取失败: {exc}")


async def rev_functions(binary_path: str) -> ReverseResult:
    """列出所有函数及其地址、大小，并标记关键函数。"""
    check = _check_r2()
    if not check.success:
        result = await rev_analyze(binary_path)
        if not result.success:
            return result
    try:
        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, lambda: _get_r2().cmd("afl"))
        functions = []
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3:
                functions.append({"address": parts[0], "size": int(parts[1]) if parts[1].isdigit() else 0,
                                  "name": parts[-1], "key": any(kf in parts[-1] for kf in _KEY_FUNCS)})
        kf = [f["name"] for f in functions if f.get("key")]
        return ReverseResult(success=True, output=f"共 {len(functions)} 个函数", functions=functions,
                             suggestions=[f"发现关键函数: {', '.join(kf)}"] if kf else [])
    except Exception as exc:
        return ReverseResult(success=False, error=f"函数列表获取失败: {exc}")


async def rev_disassemble(binary_path: str, function: Optional[str] = None,
                          address: Optional[str] = None, count: int = 50) -> ReverseResult:
    """反汇编指定函数或地址处的指令。function 和 address 二选一。"""
    check = _check_r2()
    if not check.success:
        result = await rev_analyze(binary_path)
        if not result.success:
            return result
    if not function and not address:
        return ReverseResult(success=False, error="必须提供 function 或 address 之一")
    try:
        loop = asyncio.get_event_loop()
        cmd = f"pdf @ {function}" if function else f"pd {count} @ {address}"
        dis = await loop.run_in_executor(None, lambda: _get_r2().cmd(cmd))
        return ReverseResult(success=True, output=f"反汇编完成 ({len(dis.splitlines())} 行)", disassembly=dis)
    except Exception as exc:
        return ReverseResult(success=False, error=f"反汇编失败: {exc}")


async def rev_decompile(binary_path: str, function: Optional[str] = None) -> ReverseResult:
    """使用 radare2 内置反编译器生成伪代码。"""
    check = _check_r2()
    if not check.success:
        result = await rev_analyze(binary_path)
        if not result.success:
            return result
    try:
        loop = asyncio.get_event_loop()
        cmd = f"pdc @ {function}" if function else "pdc"
        dec = await loop.run_in_executor(None, lambda: _get_r2().cmd(cmd))
        return ReverseResult(success=True, output=f"反编译完成 ({len(dec.splitlines())} 行)", decompiled=dec)
    except Exception as exc:
        return ReverseResult(success=False, error=f"反编译失败: {exc}")


async def rev_find_crypto_constants(binary_path: str) -> ReverseResult:
    """搜索二进制中常见密码学常量，提示可能存在加密逻辑。
    检测 AES S-box、MD5 初始值、SHA 常量、Base64 表等。"""
    check = _check_r2()
    if not check.success:
        result = await rev_analyze(binary_path)
        if not result.success:
            return result
    patterns = {"AES_Sbox": "637c777bf26b6fc53001672bfed7ab76", "MD5_IV_0": "01234567",
                "MD5_IV_1": "89abcdef", "SHA1_H0": "67452301", "SHA256_K0": "428a2f98", "BASE64_TABLE": "414243444546"}
    try:
        loop = asyncio.get_event_loop()
        found = []
        for name, hp in patterns.items():
            try:
                res = await loop.run_in_executor(None, lambda p=hp: _get_r2().cmd(f"/x {p}"))
                if res and "0x" in res:
                    found.append(name)
            except Exception:
                continue
        sug = [f"发现可能的密码学常量: {', '.join(found)}", "建议进一步分析相关函数寻找加解密逻辑"] if found else ["未检测到常见密码学常量"]
        return ReverseResult(success=True, output=f"密码学常量检测完成，发现 {len(found)} 个匹配", suggestions=sug)
    except Exception as exc:
        return ReverseResult(success=False, error=f"加密常量搜索失败: {exc}")


async def rev_trace_calls(binary_path: str, target_function: str) -> ReverseResult:
    """追踪对指定函数的调用路径（交叉引用）。"""
    check = _check_r2()
    if not check.success:
        result = await rev_analyze(binary_path)
        if not result.success:
            return result
    try:
        loop = asyncio.get_event_loop()
        xrefs = await loop.run_in_executor(None, lambda: _get_r2().cmd(f"axt @ {target_function}"))
        chain = [line.strip() for line in xrefs.splitlines() if line.strip()]
        sug = [f"发现 {len(chain)} 处对 {target_function} 的调用"] if chain else [f"未发现对 {target_function} 的调用"]
        return ReverseResult(success=True, output="\n".join(chain) if chain else "无调用路径", suggestions=sug)
    except Exception as exc:
        return ReverseResult(success=False, error=f"调用追踪失败: {exc}")


async def rev_patch(binary_path: str, patches: List[dict]) -> ReverseResult:
    """对二进制文件打补丁并生成 .patched 文件。patches 每项为 {"addr": "0x1234", "bytes": "9090"}。"""
    check = _check_r2()
    if not check.success:
        result = await rev_analyze(binary_path)
        if not result.success:
            return result
    if not patches:
        return ReverseResult(success=False, error="补丁列表为空")
    try:
        loop = asyncio.get_event_loop()
        for p in patches:
            addr, bdata = p.get("addr", ""), p.get("bytes", "")
            if addr and bdata:
                await loop.run_in_executor(None, lambda a=addr, b=bdata: _get_r2().cmd(f"wx {b} @ {a}"))
        patched_path = f"{binary_path}.patched"
        await loop.run_in_executor(None, lambda: _get_r2().cmd(f"wtf {patched_path}"))
        if not os.path.exists(patched_path):
            shutil.copy2(binary_path, patched_path)
            with open(patched_path, "r+b") as f:
                for p in patches:
                    addr, bdata = p.get("addr", ""), p.get("bytes", "")
                    if addr and bdata:
                        f.seek(int(addr, 16) if isinstance(addr, str) else addr)
                        f.write(bytes.fromhex(bdata))
        return ReverseResult(success=True, output=f"补丁完成: {patched_path}",
                             suggestions=[f"chmod +x {patched_path} 赋予执行权限"])
    except Exception as exc:
        return ReverseResult(success=False, error=f"补丁失败: {exc}")


async def rev_close() -> ReverseResult:
    """关闭当前 radare2 会话并释放资源。"""
    r2 = _get_r2()
    if r2 is not None:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, r2.quit)
        except Exception:
            pass
        finally:
            _set_r2(None)
    return ReverseResult(success=True, output="radare2 会话已关闭")
