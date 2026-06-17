"""M2 CTF Kit — PentestAgent CTF 攻击模块

提供 Playbook 驱动的 CTF 全链路工具链（Pwn / Crypto / Reverse / Flag 提交），
通过 ``/ctf`` 命令系列与 TUI 交互。
"""

from __future__ import annotations

import os
import logging
from typing import Optional, Dict

logger = logging.getLogger("pentestagent.m2_ctf_kit")

__all__ = [
    "init_m2", "get_playbook_engine", "is_m2_enabled", "is_ctf_tool_available",
    "CPA_M2_CTF_KIT", "CPA_M2_PWN_TOOLS", "CPA_M2_CRYPTO_TOOLS",
    "CPA_M2_REVERSE_TOOLS", "CPA_M2_FLAG_SUBMITTER",
    "CPA_M2_KALI_VM_HOST", "CPA_M2_KALI_VM_PORT", "CPA_M2_KALI_VM_USER", "CPA_M2_KALI_VM_KEY",
]

# ---------------------------------------------------------------------------
# 环境变量开关
# ---------------------------------------------------------------------------
CPA_M2_CTF_KIT: bool = os.getenv("CPA_M2_CTF_KIT", "true").lower() == "true"
CPA_M2_PWN_TOOLS: bool = os.getenv("CPA_M2_PWN_TOOLS", "true").lower() == "true"
CPA_M2_CRYPTO_TOOLS: bool = os.getenv("CPA_M2_CRYPTO_TOOLS", "true").lower() == "true"
CPA_M2_REVERSE_TOOLS: bool = os.getenv("CPA_M2_REVERSE_TOOLS", "true").lower() == "true"
CPA_M2_FLAG_SUBMITTER: bool = os.getenv("CPA_M2_FLAG_SUBMITTER", "true").lower() == "true"

# Kali VM 配置
CPA_M2_KALI_VM_HOST: str = os.getenv("CPA_M2_KALI_VM_HOST", "")
CPA_M2_KALI_VM_PORT: int = int(os.getenv("CPA_M2_KALI_VM_PORT", "22"))
CPA_M2_KALI_VM_USER: str = os.getenv("CPA_M2_KALI_VM_USER", "kali")
CPA_M2_KALI_VM_KEY: str = os.getenv("CPA_M2_KALI_VM_KEY", "~/.ssh/id_rsa")

# 内部状态
_PLAYBOOK_ENGINE: Optional["PlaybookEngine"] = None
_TOOL_AVAILABILITY: Dict[str, bool] = {}
_INITIALIZED: bool = False


async def init_m2() -> None:
    """初始化 M2 CTF Kit 模块。

    执行流程：
        1. 检查总开关 ``CPA_M2_CTF_KIT``，为 false 则跳过。
        2. 检测子模块运行时依赖（pwntools / r2pipe / capstone / requests）。
        3. 初始化 ``PlaybookEngine`` 并加载所有 Playbook。
        4. 向 ``ctf_commands`` 注入引擎引用。
    """
    global _INITIALIZED, _PLAYBOOK_ENGINE, _TOOL_AVAILABILITY

    if not CPA_M2_CTF_KIT:
        logger.info("M2 CTF Kit 总开关为 false，跳过初始化")
        return

    logger.info("M2 CTF Kit 初始化中...")

    # 依赖检测
    _TOOL_AVAILABILITY["pwn"] = _chk("pwnlib") and CPA_M2_PWN_TOOLS
    _TOOL_AVAILABILITY["crypto"] = _chk("Crypto") and CPA_M2_CRYPTO_TOOLS
    _TOOL_AVAILABILITY["reverse"] = (_chk("r2pipe") or _chk("capstone")) and CPA_M2_REVERSE_TOOLS
    _TOOL_AVAILABILITY["flag"] = _chk("requests") and CPA_M2_FLAG_SUBMITTER
    logger.debug(f"子模块可用性: {_TOOL_AVAILABILITY}")

    # 初始化 PlaybookEngine
    try:
        from .playbook_engine import PlaybookEngine
        _PLAYBOOK_ENGINE = PlaybookEngine()
        _PLAYBOOK_ENGINE.load_all_playbooks()
        logger.info(f"PlaybookEngine 就绪，已加载 {len(_PLAYBOOK_ENGINE.list_playbooks())} 个 Playbook")
    except ImportError:
        logger.warning("playbook_engine 未找到，Playbook 功能不可用")
    except Exception as exc:
        logger.error(f"PlaybookEngine 初始化失败: {exc}")

    # 向命令模块注入引擎
    try:
        from .ctf_commands import _set_engine
        if _PLAYBOOK_ENGINE is not None:
            _set_engine(_PLAYBOOK_ENGINE)
    except ImportError:
        logger.warning("ctf_commands 未找到，命令注册可能不完整")

    _INITIALIZED = True
    logger.info("M2 CTF Kit 初始化完成")


def get_playbook_engine() -> Optional["PlaybookEngine"]:
    """获取已初始化的 PlaybookEngine 实例，未初始化返回 ``None``。"""
    return _PLAYBOOK_ENGINE


def is_m2_enabled() -> bool:
    """M2 总开关为 true 且初始化成功时返回 ``True``。"""
    return CPA_M2_CTF_KIT and _INITIALIZED


def is_ctf_tool_available(tool_name: str) -> bool:
    """查询指定 CTF 子工具可用性。

    Args:
        tool_name: ``pwn`` / ``crypto`` / ``reverse`` / ``flag``。
    """
    return _TOOL_AVAILABILITY.get(tool_name, False)


def _chk(module_name: str) -> bool:
    """尝试导入模块，成功返回 True。"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False
