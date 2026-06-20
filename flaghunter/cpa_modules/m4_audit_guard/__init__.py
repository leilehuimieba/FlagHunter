"""CPA M4 Audit Guard — 审计守卫模块入口。

提供审计日志、RoE规则引擎、作用域管控、审批门控、数据脱敏。
环境变量控制开关，支持异步初始化与懒加载单例。

环境变量: CPA_M4_AUDIT_GUARD(总开关,默认true), CPA_M4_LOG_DIR(默认./logs/audit),
CPA_M4_LOG_RETENTION_DAYS(默认90), CPA_M4_ROE_FILE(默认空), CPA_M4_STRICT_MODE(默认false),
CPA_M4_DANGEROUS_TOOLS(默认空), CPA_M4_AUTO_BLOCK_GOV(默认true),
CPA_M4_MASK_SENSITIVE(默认true), CPA_M4_APPROVAL_TIMEOUT(默认300)
"""
from __future__ import annotations
import asyncio, logging, os
from typing import TYPE_CHECKING
from .audit_logger import AuditLogger
from .roe_engine import RoEEngine
from .scope_enforcer import ScopeEnforcer, ScopeBlockedException
from .approval_gate import ApprovalGate
from .data_protection import DataProtector
if TYPE_CHECKING: pass
__version__ = "1.0.0"
__all__ = [
    "init_m4", "is_m4_enabled", "get_audit_logger", "get_roe_engine",
    "get_scope_enforcer", "get_approval_gate", "get_data_protector",
    "AuditLogger", "RoEEngine", "ScopeEnforcer", "ScopeBlockedException",
    "ApprovalGate", "DataProtector",
]

# 模块级单例
_audit_logger: AuditLogger | None = None
_roe_engine: RoEEngine | None = None
_scope_enforcer: ScopeEnforcer | None = None
_approval_gate: ApprovalGate | None = None
_data_protector: DataProtector | None = None
_initialized: bool = False
_init_lock: asyncio.Lock = asyncio.Lock()
_logger = logging.getLogger("cpa.m4_audit_guard")

def _env_bool(key: str, default: str = "false") -> bool:
    """从环境变量读取布尔值。"""
    return os.getenv(key, default).lower() in ("1", "true", "yes", "on")

def _env_int(key: str, default: str) -> int:
    """从环境变量读取整数值。"""
    try: return int(os.getenv(key, default))
    except ValueError:
        _logger.warning("%s 不是有效整数，使用默认值 %s", key, default)
        return int(default)

def _env_str(key: str, default: str = "") -> str:
    """从环境变量读取字符串值。"""
    return os.getenv(key, default)

async def init_m4() -> None:
    """异步初始化M4 Audit Guard模块。检查开关→防重复→读配置→创建组件→标记完成。
    全部异常捕获，失败仅记录日志不阻塞。"""
    global _audit_logger, _roe_engine, _scope_enforcer, _approval_gate, _data_protector, _initialized
    if not is_m4_enabled():
        _logger.info("CPA_M4_AUDIT_GUARD已关闭，跳过M4初始化"); return
    async with _init_lock:
        if _initialized:
            _logger.debug("M4已初始化，跳过重复调用"); return
        try:
            log_dir = _env_str("CPA_M4_LOG_DIR", "./logs/audit")
            retention_days = _env_int("CPA_M4_LOG_RETENTION_DAYS", "90")
            roe_file = _env_str("CPA_M4_ROE_FILE", "")
            strict_mode = _env_bool("CPA_M4_STRICT_MODE", "false")
            dangerous_tools_str = _env_str("CPA_M4_DANGEROUS_TOOLS", "")
            auto_block_gov = _env_bool("CPA_M4_AUTO_BLOCK_GOV", "true")
            mask_sensitive = _env_bool("CPA_M4_MASK_SENSITIVE", "true")
            approval_timeout = _env_int("CPA_M4_APPROVAL_TIMEOUT", "300")
            _audit_logger = AuditLogger(log_dir=log_dir, retention_days=retention_days)
            _roe_engine = RoEEngine()
            if roe_file and os.path.isfile(roe_file):
                _roe_engine.load_roe(roe_file); _logger.info("已自动加载RoE文件: %s", roe_file)
            _scope_enforcer = ScopeEnforcer(
                roe_engine=_roe_engine, audit_logger=_audit_logger,
                auto_block_gov=auto_block_gov, strict_mode=strict_mode)
            _approval_gate = ApprovalGate(audit_logger=_audit_logger, approval_timeout=approval_timeout)
            if dangerous_tools_str:
                extra = [t.strip() for t in dangerous_tools_str.split(",") if t.strip()]
                for t in extra:
                    _approval_gate.add_dangerous_tool(t)
                _logger.info("已加载%d个额外危险工具", len(extra))
            # 总开关 mask_sensitive 同向治理可配置敏感类目(IP/邮箱);flag 单独硬编码
            # 为不脱敏(CTF 场景保留)。IP 与 email 一致跟随总开关:开则脱敏,关则保留。
            _data_protector = DataProtector(
                mask_ips=mask_sensitive, mask_emails=mask_sensitive, mask_flags=False)
            _initialized = True
            _audit_logger.log_command(
                command="m4_init",
                output_preview=f"M4初始化成功 log_dir={log_dir} roe={roe_file or 'none'}",
            )
            _logger.info("M4 Audit Guard v%s初始化完成", __version__)
        except Exception as exc:
            _logger.error("M4初始化失败: %s", exc, exc_info=True)

def get_audit_logger() -> AuditLogger:
    """获取审计日志记录器单例。未初始化抛RuntimeError。"""
    if not _initialized or _audit_logger is None: raise RuntimeError("M4未初始化，请先调用init_m4()")
    return _audit_logger

def get_roe_engine() -> RoEEngine:
    """获取RoE规则引擎单例。未初始化抛RuntimeError。"""
    if not _initialized or _roe_engine is None: raise RuntimeError("M4未初始化，请先调用init_m4()")
    return _roe_engine

def get_scope_enforcer() -> ScopeEnforcer:
    """获取作用域强制管控器单例。未初始化抛RuntimeError。"""
    if not _initialized or _scope_enforcer is None: raise RuntimeError("M4未初始化，请先调用init_m4()")
    return _scope_enforcer

def get_approval_gate() -> ApprovalGate:
    """获取危险操作审批门控单例。未初始化抛RuntimeError。"""
    if not _initialized or _approval_gate is None: raise RuntimeError("M4未初始化，请先调用init_m4()")
    return _approval_gate

def get_data_protector() -> DataProtector:
    """获取数据脱敏保护器单例。未初始化抛RuntimeError。"""
    if not _initialized or _data_protector is None: raise RuntimeError("M4未初始化，请先调用init_m4()")
    return _data_protector

def is_m4_enabled() -> bool:
    """判断M4是否被环境变量启用。默认true。"""
    return os.getenv("CPA_M4_AUDIT_GUARD", "true").lower() == "true"
