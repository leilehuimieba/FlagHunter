"""M2 CTF Kit — /ctf 命令系列处理模块

提供从状态面板到 playbook 执行、flag 提交、pwn、crypto、reverse 等
全链路 CTF 交互命令。所有命令函数均返回 str，供 TUI 层直接渲染。
"""

from __future__ import annotations
import os
from typing import Optional

from .playbook_engine import PlaybookEngine, PlaybookResult
from .pwn_tools import pwn_remote, pwn_leak_info, pwn_close, PwnResult
from .crypto_tools import crypto_auto_solve, CryptoResult
from .reverse_tools import rev_analyze, rev_strings, rev_close, ReverseResult
from .flag_submitter import submit_flag, SubmitResult

# 全局状态（由 init_m2() 注入引擎）
_PLAYBOOK_ENGINE: Optional[PlaybookEngine] = None
_CURRENT_PLAYBOOK: Optional[str] = None
_CURRENT_PHASE: int = 0
_PHASE_NAMES: list[str] = ["侦察", "分析", "利用", "提取 Flag"]

def _set_engine(engine: PlaybookEngine) -> None:
    """供 __init__.py 注入已初始化的 PlaybookEngine。"""
    global _PLAYBOOK_ENGINE
    _PLAYBOOK_ENGINE = engine


def _header(title: str) -> str:
    """生成带边框的 TUI 标题。"""
    return f"╔{'═' * 58}╗\n║{title:^58}║\n╠{'═' * 58}╣"


def _footer() -> str:
    """生成底边框。"""
    return f"╚{'═' * 58}╝"


def _row(label: str, value: str) -> str:
    """生成键值对行，自动截断填充。"""
    left = f"  {label}: "
    right = str(value)
    remain = 58 - len(left) - len(right)
    if remain < 0:
        right = right[:55 - len(left)] + "..."
        remain = 58 - len(left) - len(right)
    return f"║{left}{right}{' ' * remain}║"


def _err(msg: str) -> str:
    """生成错误提示框。"""
    return f"╔{'═' * 58}╗\n║  [错误] {msg:49s}║\n╚{'═' * 58}╝"


async def cmd_ctf() -> str:
    """显示 CTF Kit 状态面板。"""
    lines = [_header("M2 CTF Kit 状态面板")]
    lines.append(_row("当前 Playbook", _CURRENT_PLAYBOOK or "未选择"))
    phase = f"{_PHASE_NAMES[_CURRENT_PHASE]} ({_CURRENT_PHASE + 1}/{len(_PHASE_NAMES)})" if _CURRENT_PLAYBOOK else "等待开始"
    lines.append(_row("当前阶段", phase))
    lines.append("║" + " " * 58 + "║")
    lines.append("║  子模块状态:                                          ║")
    for mod in ("pwn", "crypto", "reverse", "flag"):
        key = f"CPA_M2_{mod.upper()}_TOOLS" if mod != "flag" else "CPA_M2_FLAG_SUBMITTER"
        ok = os.getenv(key, "true").lower() == "true"
        lines.append(_row(f"  [{'✓' if ok else '✗'}] {mod:8s}", "就绪" if ok else "已禁用"))
    lines.append(_footer())
    hints = [
        "", "用法提示:", "  /ctf list          — 列出 Playbook",
        "  /ctf run <pb> <tg> — 执行 Playbook", "  /ctf phase         — 查看阶段",
        "  /ctf next          — 下一阶段", "  /ctf flag <flag>   — 提交 Flag",
        "  /ctf pwn <h> <p>   — 快速 Pwn", "  /ctf decode <text> — 快速解码",
        "  /ctf rev <binary>  — 快速逆向", "  /ctf status        — 模块诊断",
    ]
    return "\n".join(lines + hints)


async def cmd_ctf_list() -> str:
    """列出所有 Playbook，按题型分类。"""
    if _PLAYBOOK_ENGINE is None:
        return _err("PlaybookEngine 尚未初始化")
    lines = [_header("Playbook 列表")]
    try:
        all_names = _PLAYBOOK_ENGINE.list_playbooks()
        # Group by category
        cats: dict = {}
        for pb_name in all_names:
            pb = _PLAYBOOK_ENGINE._playbooks.get(pb_name)
            cat = pb.category if pb else "misc"
            cats.setdefault(cat, []).append(pb_name)
    except Exception as exc:
        return _err(f"获取列表失败: {exc}")
    if not cats:
        lines.append("║  暂无 Playbook，请将 .yaml/.json 放入                 ║")
        lines.append("║  ~/.config/flaghunter/m2_playbooks/                  ║")
    else:
        for cat, pbs in sorted(cats.items()):
            lines.append("║" + " " * 58 + "║")
            lines.append(f"║  ▶ {cat.upper():53s}║")
            for pb in pbs:
                lines.append(f"║      • {pb:<51s}║")
    lines.append(_footer())
    return "\n".join(lines)


async def cmd_ctf_run(playbook_name: str, target: str) -> str:
    """执行指定 Playbook。

    Args:
        playbook_name: Playbook 名称（不含扩展名）。
        target: 目标地址（host:port 或 URL）。
    """
    global _CURRENT_PLAYBOOK, _CURRENT_PHASE
    if _PLAYBOOK_ENGINE is None:
        return _err("PlaybookEngine 尚未初始化")
    lines = [_header(f"执行: {playbook_name}"), _row("目标", target),
             "║" + " " * 58 + "║", "║  [流程] 侦察 → 分析 → 利用 → 提取 Flag                 ║",
             "║" + " " * 58 + "║"]
    try:
        result: PlaybookResult = await _PLAYBOOK_ENGINE.execute(playbook_name, target)
        _CURRENT_PLAYBOOK, _CURRENT_PHASE = playbook_name, 0
        lines.append(_row("状态", "✓ 成功" if result.success else "✗ 失败"))
        if result.flag:
            lines.append(_row("Flag", result.flag))
        if result.summary:
            for ln in result.summary.splitlines()[:6]:
                lines.append(f"║  {ln[:54] + '...' if len(ln) > 57 else ln:<56s}║")
    except FileNotFoundError:
        return _err(f"未找到 Playbook '{playbook_name}'")
    except Exception as exc:
        return _err(f"执行异常: {exc}")
    lines.append(_footer())
    return "\n".join(lines)


async def cmd_ctf_phase() -> str:
    """显示当前阶段和进度。"""
    lines = [_header("当前阶段"), _row("Playbook", _CURRENT_PLAYBOOK or "未选择"),
             "║" + " " * 58 + "║"]
    total = len(_PHASE_NAMES)
    filled = int(40 * (_CURRENT_PHASE + 1) / total) if _CURRENT_PLAYBOOK else 0
    bar = "█" * filled + "░" * (40 - filled)
    lines.append(f"║  {bar}  ║")
    label = _PHASE_NAMES[_CURRENT_PHASE] if _CURRENT_PLAYBOOK else "等待开始"
    lines.append(f"║  {label:>56s}  ║")
    for idx, name in enumerate(_PHASE_NAMES):
        icon = "●" if idx <= _CURRENT_PHASE and _CURRENT_PLAYBOOK else "○"
        lines.append(f"║    {icon} {idx + 1}. {name:<51s}║")
    lines.append(_footer())
    return "\n".join(lines)


async def cmd_ctf_next() -> str:
    """确认当前阶段完成，进入下一阶段。"""
    global _CURRENT_PHASE
    if _CURRENT_PLAYBOOK is None:
        return "[提示] 尚未执行 Playbook，请先用 /ctf run 开始。"
    if _CURRENT_PHASE >= len(_PHASE_NAMES) - 1:
        _CURRENT_PHASE = len(_PHASE_NAMES) - 1
        return f"╔{'═' * 58}╗\n║  所有阶段已完成！请使用 /ctf flag <flag> 提交成果。    ║\n╚{'═' * 58}╝"
    prev, _CURRENT_PHASE = _PHASE_NAMES[_CURRENT_PHASE], _CURRENT_PHASE + 1
    lines = [_header("阶段推进"), _row("已完成", prev), _row("新阶段", _PHASE_NAMES[_CURRENT_PHASE]),
             f"║  进度: {_CURRENT_PHASE + 1} / {len(_PHASE_NAMES):<45s}║", _footer()]
    return "\n".join(lines)


async def cmd_ctf_flag(flag: str, challenge_id: str | None = None) -> str:
    """提交 Flag。

    Args:
        flag: 要提交的 flag 字符串。
        challenge_id: 可选的挑战 ID。
    """
    lines = [_header("Flag 提交")]
    lines.append(_row("Flag", flag[:40] + "..." if len(flag) > 43 else flag))
    if challenge_id:
        lines.append(_row("Challenge", challenge_id))
    try:
        result: SubmitResult = await submit_flag(flag, challenge_id=challenge_id)
        if result.accepted:
            lines.append(_row("结果", "✓ Accepted — Flag 正确！"))
            if result.points:
                lines.append(_row("得分", f"+{result.points}"))
        else:
            lines.append(_row("结果", f"✗ Rejected — {result.reason or 'Flag 错误'}"))
        if result.message:
            for ln in result.message.splitlines()[:4]:
                lines.append(f"║  {ln[:54] + '...' if len(ln) > 57 else ln:<56s}║")
    except Exception as exc:
        lines.append(_row("结果", f"✗ 失败: {exc}"))
    lines.append(_footer())
    return "\n".join(lines)


async def cmd_ctf_pwn(host: str, port: int) -> str:
    """快速启动 Pwn 工具链：连接靶机 + 泄露信息。

    Args:
        host: 靶机地址。
        port: 靶机端口。
    """
    lines = [_header(f"Pwn — {host}:{port}")]
    try:
        conn = await pwn_remote(host, port)
        lines.append(_row("连接", "✓ 已建立"))
        leaks = await pwn_leak_info(conn)
        if leaks.canary: lines.append(_row("Stack Canary", leaks.canary))
        if leaks.base_addr: lines.append(_row("Base Addr", hex(leaks.base_addr)))
        if leaks.libc_base: lines.append(_row("libc Base", hex(leaks.libc_base)))
        if leaks.stack_addr: lines.append(_row("Stack", hex(leaks.stack_addr)))
        await pwn_close(conn)
        lines.append(_row("连接", "已关闭"))
    except ConnectionRefusedError:
        lines.append(_row("连接", "✗ 被拒绝"))
    except TimeoutError:
        lines.append(_row("连接", "✗ 超时"))
    except Exception as exc:
        lines.append(_row("错误", str(exc)[:48]))
    lines.append(_footer())
    return "\n".join(lines)


async def cmd_ctf_decode(ciphertext: str) -> str:
    """快速调用 crypto_auto_solve 尝试自动化解密。

    Args:
        ciphertext: 密文字符串。
    """
    lines = [_header("Crypto 自动解密"),
             _row("输入", ciphertext[:40] + "..." if len(ciphertext) > 43 else ciphertext),
             "║" + " " * 58 + "║"]
    try:
        result: CryptoResult = await crypto_auto_solve(ciphertext)
        if result.solved:
            lines.append(_row("状态", "✓ 解密成功"))
            lines.append(_row("方法", result.method or "unknown"))
            plain = result.plaintext[:40] + "..." if len(result.plaintext) > 43 else result.plaintext
            lines.append(_row("明文", plain))
        else:
            lines.append(_row("状态", "✗ 未能自动解密"))
        if result.details:
            for d in result.details[:4]:
                lines.append(f"║  {d[:54] + '...' if len(d) > 57 else d:<56s}║")
    except Exception as exc:
        lines.append(_row("错误", str(exc)[:48]))
    lines.append(_footer())
    return "\n".join(lines)


async def cmd_ctf_rev(binary_path: str) -> str:
    """快速启动逆向分析：strings + 基础分析。

    Args:
        binary_path: 二进制文件路径。
    """
    lines = [_header(f"Reverse — {os.path.basename(binary_path)}")]
    if not os.path.exists(binary_path):
        return _err(f"文件不存在: {binary_path}")
    try:
        result: ReverseResult = await rev_analyze(binary_path)
        lines.append(_row("架构", result.arch or "unknown"))
        lines.append(_row("位数", f"{result.bits or '?'}-bit"))
        if result.entry_point:
            lines.append(_row("Entry", hex(result.entry_point)))
        if result.protection:
            prot = ", ".join(f"{k}={v}" for k, v in result.protection.items())
            lines.append(_row("保护", prot[:50] + "..." if len(prot) > 53 else prot))
        strs = await rev_strings(binary_path, limit=20)
        if strs.strings:
            lines.append("║" + " " * 58 + "║")
            lines.append("║  关键字符串:                                          ║")
            for s in strs.strings[:8]:
                lines.append(f"║    {repr(s)[:54] + '...' if len(repr(s)) > 57 else repr(s):<54s}║")
        await rev_close(binary_path)
    except Exception as exc:
        lines.append(_row("错误", str(exc)[:48]))
    lines.append(_footer())
    return "\n".join(lines)


async def cmd_ctf_status() -> str:
    """显示各子模块可用性状态。"""
    lines = [_header("M2 CTF Kit 模块诊断")]
    lines.append("║  环境变量开关:                                        ║")
    for label, key in [
        ("CTF Kit 总开关", "CPA_M2_CTF_KIT"), ("Pwn 工具链", "CPA_M2_PWN_TOOLS"),
        ("Crypto 工具链", "CPA_M2_CRYPTO_TOOLS"), ("Reverse 工具链", "CPA_M2_REVERSE_TOOLS"),
        ("Flag 提交器", "CPA_M2_FLAG_SUBMITTER"),
    ]:
        val = os.getenv(key, "true").lower()
        lines.append(_row(f"  [{'✓' if val == 'true' else '✗'}] {label}", val))
    lines.append("║" + " " * 58 + "║")
    lines.append("║  运行时依赖检测:                                      ║")
    for mod_name, pkg in [("pwntools", "pwnlib"), ("r2pipe", "r2pipe"),
                          ("capstone", "capstone"), ("requests", "requests")]:
        try:
            m = __import__(pkg)
            lines.append(_row(f"  {mod_name}", f"✓ {getattr(m, '__version__', '已安装')}"))
        except ImportError:
            lines.append(_row(f"  {mod_name}", "✗ 未安装"))
    lines.append("║" + " " * 58 + "║")
    lines.append("║  Kali VM 配置:                                        ║")
    for k, v in [("Host", "CPA_M2_KALI_VM_HOST"), ("Port", "CPA_M2_KALI_VM_PORT"), ("User", "CPA_M2_KALI_VM_USER")]:
        lines.append(_row(f"  {k}", os.getenv(v, "未配置" if k == "Host" else "22" if k == "Port" else "kali")))
    lines.append(_footer())
    return "\n".join(lines)
