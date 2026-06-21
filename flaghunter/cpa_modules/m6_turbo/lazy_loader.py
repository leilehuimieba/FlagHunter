#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lazy_loader.py — FlagHunter M6 Turbo 延迟加载统一封装与 import 代理

本模块提供 ``LazyLoader`` 工具类，用于对重量级第三方库（pwn、playwright 等）
实施按需（lazy）加载，避免启动时一次性全部 import 带来的内存与耗时开销。

核心能力：
1. **异步安全加载** — 基于 ``asyncio.Lock`` 防止并发重复 import；
2. **预加载** — 支持策略化批量预热；
3. **卸载** — 从 ``sys.modules`` 与内部缓存双清，辅助内存回落；
4. **透明代理** — ``wrap_import()`` 返回代理模块对象，首次属性访问时自动触发真实 import，业务代码无感；
5. **Import Hook** — 通过 ``sys.meta_path`` 插入自定义 finder，使 ``import xxx`` 语句本身也能被拦截为延迟加载。

技术约束：
- Python 3.10+
- 仅使用标准库（importlib, sys, types, gc, time, asyncio）
- 零外部依赖

作者: FlagHunter M6 模块
"""

from __future__ import annotations

import asyncio
import gc
import importlib
import importlib.abc
import importlib.machinery
import sys
import time
import types
import warnings
from typing import Any, Callable, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# 模块元数据与内部类型
# ---------------------------------------------------------------------------

#: 受控的延迟加载模块注册表，包含用途、重量级别、消费者等元数据。
LAZY_REGISTRY: Dict[str, Dict[str, str]] = {
    "pwn": {
        "purpose": "pwn_tools",
        "weight": "heavy",
        "used_by": "m2_ctf_kit.pwn_tools",
    },
    "r2pipe": {
        "purpose": "reverse_tools",
        "weight": "heavy",
        "used_by": "m2_ctf_kit.reverse_tools",
    },
    "pycryptodome": {
        "purpose": "crypto_tools",
        "weight": "medium",
        "used_by": "m2_ctf_kit.crypto_tools",
    },
    "jinja2": {
        "purpose": "templates",
        "weight": "medium",
        "used_by": "m3_reporter.template_engine",
    },
    "playwright": {
        "purpose": "pdf_export",
        "weight": "heavy",
        "used_by": "m3_reporter.pdf_exporter",
    },
}

#: 模块重量级别排序权重（数字越小越轻）。
_WEIGHT_ORDER = {"light": 1, "medium": 2, "heavy": 3}


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _now_ms() -> float:
    """返回当前时间戳（毫秒）。"""
    return time.perf_counter() * 1000.0


class _LazyImportFinder(importlib.abc.MetaPathFinder):
    """自定义 import finder，用于拦截注册表中的模块并将其重定向到延迟加载代理。

    当 Python 执行 ``import xxx`` 时，``sys.meta_path`` 上的 finder 依次被询问。
    本 finder 对 ``LAZY_REGISTRY`` 中的顶层模块名返回一个 ``ModuleSpec``，
    其 loader 指向 ``_LazyImportLoader``，从而将真实 import 推迟到模块首次被访问时。
    """

    def __init__(self, loader: _LazyImportLoader) -> None:
        self._loader = loader

    # 重写 find_module 以保持兼容（Python 3.4+ 推荐 find_spec）
    def find_module(
        self, fullname: str, path: Optional[str] = None
    ) -> Optional[_LazyImportLoader]:
        return self.find_spec(fullname, path)  # type: ignore[return-value]

    def find_spec(
        self,
        fullname: str,
        path: Optional[List[str]] = None,
        target: Optional[types.ModuleType] = None,
    ) -> Optional[importlib.machinery.ModuleSpec]:
        """若 ``fullname`` 的根命名空间命中注册表，则构造延迟加载用的 ModuleSpec。

        Args:
            fullname: 被请求的模块全限定名（如 ``pwn.lib.timeout``）。
            path: 通常为 ``None`` 或父包的 ``__path__``。
            target: 已存在的模块对象（重载场景）。

        Returns:
            命中时返回 ``ModuleSpec``（loader 指向 ``_LazyImportLoader``），
            否则返回 ``None`` 让后续 finder 继续尝试。
        """
        # 仅拦截注册表中的顶层包名
        top_level = fullname.split(".")[0]
        if top_level not in LAZY_REGISTRY:
            return None

        # 构造一个指向自定义 loader 的 ModuleSpec
        spec = importlib.machinery.ModuleSpec(
            name=fullname,
            loader=self._loader,  # type: ignore[arg-type]
            origin=f"<lazy_loader:{fullname}>",
            is_package=True,
        )
        # 将实际请求的模块名存入 spec 的自定义属性，供 loader 使用
        spec._lazy_target = top_level  # type: ignore[attr-defined]
        return spec


class _LazyImportLoader(importlib.abc.Loader):
    """与 ``_LazyImportFinder`` 配套的自定义 loader。

    ``create_module`` 返回代理模块对象；
    ``exec_module`` 在首次访问时通过 ``LazyLoader.get`` 完成真实加载。
    """

    def __init__(self) -> None:
        # 用于标记哪些模块已经完成 exec_module
        self._executed: Set[str] = set()

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> Optional[types.ModuleType]:
        """创建代理模块对象，而非直接执行真实 import。"""
        target = getattr(spec, "_lazy_target", spec.name)
        # 返回代理模块
        proxy = LazyLoader.wrap_import(target, alias=spec.name)
        return proxy  # type: ignore[return-value]

    def exec_module(self, module: types.ModuleType) -> None:
        """代理模块不需要在创建时执行实际代码；真实 import 被推迟到属性访问。"""
        module_name = getattr(module, "__name__", "")
        self._executed.add(module_name)
        # 真实执行推迟到 _ModuleProxy.__getattr__


class _ModuleProxy(types.ModuleType):
    """模块代理对象，用于透明拦截对未加载模块的属性访问。

    当业务代码首次访问代理模块的任意属性（如 ``pwn.asm(...)``）时，
    ``__getattr__`` 会被触发，此时调用 ``LazyLoader.get`` 完成真实 import，
    然后将属性委托给真实模块。

    Attributes:
        _proxy_name: 被代理的模块注册名（如 ``pwn``）。
        _proxy_alias: 外部可见的模块全限定名（如 ``pwn.lib.timeout``）。
        _proxy_loaded: 内部标记，避免重复触发真实加载。
    """

    def __init__(self, proxy_name: str, alias: Optional[str] = None) -> None:
        super().__init__(alias or proxy_name)
        self._proxy_name: str = proxy_name
        self._proxy_alias: str = alias or proxy_name
        self._proxy_loaded: bool = False
        self._proxy_real_module: Optional[types.ModuleType] = None
        # 用 object.__setattr__ 避免递归
        object.__setattr__(self, "__path__", [])  # 让 importlib 认为这是一个包
        object.__setattr__(self, "__package__", self._proxy_alias)
        object.__setattr__(self, "__loader__", None)
        object.__setattr__(self, "__spec__", None)

    def __getattr__(self, name: str) -> Any:
        """拦截任意属性访问，触发真实模块加载并委托属性。

        Args:
            name: 被访问的属性名。

        Returns:
            真实模块上对应属性的值。

        Raises:
            AttributeError: 真实模块加载失败或不包含该属性时抛出。
        """
        # 防止对代理内部属性访问触发递归
        if name in (
            "_proxy_name",
            "_proxy_alias",
            "_proxy_loaded",
            "_proxy_real_module",
            "__name__",
            "__doc__",
            "__path__",
            "__package__",
            "__loader__",
            "__spec__",
            "__class__",
            "__dict__",
        ):
            try:
                return object.__getattribute__(self, name)
            except AttributeError:
                raise AttributeError(
                    f"module {self._proxy_alias!r} has no attribute {name!r}"
                ) from None

        if not object.__getattribute__(self, "_proxy_loaded"):
            # 触发真实加载（同步方式）
            try:
                real_mod = importlib.import_module(self._proxy_name)
                LazyLoader._loaded[self._proxy_name] = real_mod
            except Exception as exc:
                raise ImportError(
                    f"延迟加载模块 {self._proxy_name!r} 失败 (属性 '{name}'): {exc}"
                ) from exc
            object.__setattr__(self, "_proxy_real_module", real_mod)
            object.__setattr__(self, "_proxy_loaded", True)

        real_module = object.__getattribute__(self, "_proxy_real_module")
        if real_module is not None:
            try:
                return getattr(real_module, name)
            except AttributeError as exc:
                raise AttributeError(
                    f"module {self._proxy_alias!r} (proxy for {self._proxy_name!r}) "
                    f"has no attribute {name!r}"
                ) from exc

        raise ImportError(
            f"模块 {self._proxy_name!r} 代理加载失败，无法访问属性 {name!r}"
        )

    def __repr__(self) -> str:
        loaded = object.__getattribute__(self, "_proxy_loaded")
        alias = object.__getattribute__(self, "_proxy_alias")
        name = object.__getattribute__(self, "_proxy_name")
        status = "loaded" if loaded else "lazy"
        return f"<_ModuleProxy({alias} -> {name}, {status})>"

    def __dir__(self) -> List[str]:
        """返回代理模块的属性列表。若已加载，合并真实模块的属性。"""
        base = list(object.__getattribute__(self, "__dict__").keys())
        if object.__getattribute__(self, "_proxy_loaded"):
            real_module = object.__getattribute__(self, "_proxy_real_module")
            if real_module is not None:
                base.extend(dir(real_module))
        return sorted(set(base))


# ---------------------------------------------------------------------------
# LazyLoader 主类
# ---------------------------------------------------------------------------

class LazyLoader:
    """延迟加载统一封装入口，全类方法设计，无需实例化。

    典型用法：
        >>> pwn = LazyLoader.wrap_import("pwn")
        >>> pwn.asm("xor eax, eax")   # 首次使用时才真正 import pwn

        >>> # 异步场景
        >>> pwn_mod = await LazyLoader.get("pwn")

        >>> # 启动时预加载轻量模块
        >>> stats = await LazyLoader.preload()

        >>> # 卸载不再使用的模块释放内存
        >>> LazyLoader.unload("playwright")
    """

    #: 延迟加载模块注册表（可读别名，兼容外部访问）。
    LAZY_MODULES: Dict[str, Dict[str, str]] = LAZY_REGISTRY

    #: 已加载模块的缓存：{module_name: module_object}
    _loaded: Dict[str, Any] = {}

    #: 模块级加载锁：{module_name: asyncio.Lock}
    _loading: Dict[str, asyncio.Lock] = {}

    #: 各模块加载耗时记录（毫秒）：{module_name: load_time_ms}
    _load_times: Dict[str, float] = {}

    #: 是否已安装 import hook（防止重复插入）。
    _hook_installed: bool = False

    #: 内部 finder 实例引用。
    _finder_instance: Optional[_LazyImportFinder] = None

    # ------------------------------------------------------------------
    # 核心加载/卸载
    # ------------------------------------------------------------------

    @classmethod
    async def get(cls, module_name: str) -> Any:
        """异步获取指定模块，带并发安全锁。

        若模块尚未加载，则调用 ``importlib.import_module`` 进行真实 import，
        并将结果缓存到 ``_loaded``；若已加载则直接返回缓存。

        Args:
            module_name: 模块注册名（如 ``pwn``、``playwright``）。

        Returns:
            加载后的模块对象。

        Raises:
            ImportError: 模块不在注册表中或 import 失败时抛出。
            ModuleNotFoundError: 模块未安装时抛出。
        """
        # 已缓存直接返回
        if module_name in cls._loaded:
            return cls._loaded[module_name]

        # 确认在注册表中（支持子模块映射）
        top_level = module_name.split(".")[0]
        if top_level not in cls.LAZY_MODULES:
            # 不在注册表中的模块也允许加载（降级为普通 import），但发出警告
            warnings.warn(
                f"模块 {module_name!r} 不在延迟加载注册表中，将以普通方式导入。",
                RuntimeWarning,
                stacklevel=2,
            )

        # 懒初始化 Lock
        if module_name not in cls._loading:
            cls._loading[module_name] = asyncio.Lock()

        lock = cls._loading[module_name]
        async with lock:
            # 双重检查（可能其他协程已加载完成）
            if module_name in cls._loaded:
                return cls._loaded[module_name]

            t0 = _now_ms()
            try:
                real_mod = importlib.import_module(module_name)
            except Exception as exc:
                raise ImportError(
                    f"延迟加载模块 {module_name!r} 失败: {exc}"
                ) from exc

            elapsed = _now_ms() - t0
            cls._loaded[module_name] = real_mod
            cls._load_times[module_name] = elapsed
            return real_mod

    @classmethod
    async def preload(cls, module_names: Optional[List[str]] = None) -> Dict[str, float]:
        """批量预加载模块。

        当 ``module_names`` 为 ``None`` 时，默认加载所有 ``weight='light'`` 的模块。

        Args:
            module_names: 要预加载的模块名列表。为 ``None`` 时自动选择轻量模块。

        Returns:
            加载耗时字典：{module_name: load_time_ms}。若模块已加载则耗时为 0.0。
        """
        if module_names is None:
            module_names = [
                name
                for name, meta in cls.LAZY_MODULES.items()
                if meta.get("weight") == "light"
            ]

        results: Dict[str, float] = {}
        for name in module_names:
            if name in cls._loaded:
                results[name] = 0.0
                continue
            try:
                await cls.get(name)
                results[name] = cls._load_times.get(name, 0.0)
            except ImportError as exc:
                # 预加载失败不应中断整体流程，记录警告并继续
                warnings.warn(f"预加载 {name!r} 失败: {exc}", RuntimeWarning, stacklevel=2)
                results[name] = -1.0  # 负值表示失败
        return results

    @classmethod
    def unload(cls, module_name: str) -> bool:
        """卸载指定模块，从 ``sys.modules`` 与内部缓存中双重移除。

        卸载后可由 GC 回收模块占用的内存（前提是其他地方无引用）。

        Args:
            module_name: 要卸载的模块注册名。

        Returns:
            ``True`` 表示成功卸载；``False`` 表示模块未加载或不存在。
        """
        removed = False

        # 1) 从内部缓存移除
        if module_name in cls._loaded:
            del cls._loaded[module_name]
            removed = True

        # 2) 从 sys.modules 移除（包括子模块）
        to_remove = [
            key
            for key in sys.modules
            if key == module_name or key.startswith(module_name + ".")
        ]
        for key in to_remove:
            del sys.modules[key]
            removed = True

        # 3) 清理加载时间记录（保留 key 以便统计知道曾经加载过）
        if module_name in cls._load_times and not removed:
            # 模块未在缓存中但有时间记录——可能是外部导入的
            removed = bool(to_remove)

        if removed:
            # 触发 GC，帮助回收模块内存
            gc.collect()

        return removed

    @classmethod
    def is_loaded(cls, module_name: str) -> bool:
        """判断模块是否已被加载。

        Args:
            module_name: 模块注册名。

        Returns:
            若模块在内部缓存中则返回 ``True``，否则 ``False``。
        """
        return module_name in cls._loaded

    # ------------------------------------------------------------------
    # 统计与报告
    # ------------------------------------------------------------------

    @classmethod
    def get_load_stats(cls) -> Dict[str, Any]:
        """获取模块加载统计信息。

        Returns:
            字典包含：
            - ``registry``: 注册表模块总数与明细
            - ``loaded``: 已加载模块数及列表
            - ``pending``: 尚未加载的模块列表
            - ``load_times``: 各模块加载耗时（毫秒）
            - ``total_load_time_ms``: 累计加载耗时
        """
        loaded_keys = sorted(cls._loaded.keys())
        pending_keys = [
            name for name in cls.LAZY_MODULES if name not in cls._loaded
        ]
        total_time = sum(cls._load_times.values())

        return {
            "registry": {
                "total": len(cls.LAZY_MODULES),
                "modules": {
                    name: {
                        "weight": meta.get("weight"),
                        "purpose": meta.get("purpose"),
                        "used_by": meta.get("used_by"),
                    }
                    for name, meta in cls.LAZY_MODULES.items()
                },
            },
            "loaded": {
                "count": len(loaded_keys),
                "modules": loaded_keys,
            },
            "pending": {
                "count": len(pending_keys),
                "modules": pending_keys,
            },
            "load_times": dict(cls._load_times),
            "total_load_time_ms": round(total_time, 3),
        }

    # ------------------------------------------------------------------
    # 代理模块
    # ------------------------------------------------------------------

    @classmethod
    def wrap_import(
        cls, module_name: str, alias: Optional[str] = None
    ) -> types.ModuleType:
        """创建并返回一个代理模块对象，首次属性访问时触发真实 import。

        这是**核心方法**，业务代码通过它获得对重量级模块的透明引用：

        .. code-block:: python

            pwn = LazyLoader.wrap_import("pwn")
            # 此时 pwn 并未真正加载
            pwn.asm("...")  # <- 第一次属性访问时才 import pwn

        代理内部使用 ``_ModuleProxy``（``types.ModuleType`` 子类），
        重写 ``__getattr__`` 以拦截属性访问。

        Args:
            module_name: 被代理的模块注册名。
            alias: 代理模块对外暴露的 ``__name__``，为 ``None`` 时与 ``module_name`` 相同。

        Returns:
            代理模块对象，行为上兼容 ``types.ModuleType``。
        """
        alias = alias or module_name
        proxy = _ModuleProxy(proxy_name=module_name, alias=alias)
        # 将代理对象注入 sys.modules，使后续 import 语句复用同一代理
        if alias not in sys.modules:
            sys.modules[alias] = proxy  # type: ignore[assignment]
        return proxy  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Import Hook
    # ------------------------------------------------------------------

    @classmethod
    def install_import_hook(cls) -> None:
        """在 ``sys.meta_path`` 中插入自定义 import finder，拦截注册表模块。

        安装后，当代码执行 ``import pwn`` 或 ``from pwn import asm`` 时，
        Python 的 import 机制会优先命中我们的 finder，
        返回指向 ``_LazyImportLoader`` 的 ``ModuleSpec``，
        从而将真实 import 推迟到模块属性首次被访问时。

        注意：
        - 本方法幂等——重复调用不会重复插入；
        - finder 被插入到 ``sys.meta_path`` 的最前端，优先级最高。
        """
        if cls._hook_installed:
            return

        loader = _LazyImportLoader()
        finder = _LazyImportFinder(loader)
        cls._finder_instance = finder

        # 插入到 meta_path 最前端，确保优先拦截
        sys.meta_path.insert(0, finder)  # type: ignore[arg-type]
        cls._hook_installed = True

    @classmethod
    def uninstall_import_hook(cls) -> None:
        """移除通过 ``install_import_hook`` 插入的 finder。

        用于测试或需要恢复标准 import 行为的场景。
        """
        if not cls._hook_installed or cls._finder_instance is None:
            return
        if cls._finder_instance in sys.meta_path:
            sys.meta_path.remove(cls._finder_instance)  # type: ignore[arg-type]
        cls._finder_instance = None
        cls._hook_installed = False

    @classmethod
    def is_hook_installed(cls) -> bool:
        """判断 import hook 是否已安装。"""
        return cls._hook_installed

    # ------------------------------------------------------------------
    # 批量工具
    # ------------------------------------------------------------------

    @classmethod
    def unload_all(cls) -> Dict[str, bool]:
        """卸载所有已加载的延迟模块。

        Returns:
            卸载结果字典：{module_name: success_bool}
        """
        results: Dict[str, bool] = {}
        # 复制 keys 避免遍历时修改字典
        for name in list(cls._loaded.keys()):
            results[name] = cls.unload(name)
        return results

    @classmethod
    def reload(cls, module_name: str) -> Any:
        """同步重载指定模块。

        先 ``unload`` 再重新 ``importlib.import_module``。

        Args:
            module_name: 模块注册名。

        Returns:
            重载后的模块对象。

        Raises:
            ImportError: 重载失败时抛出。
        """
        cls.unload(module_name)
        try:
            mod = importlib.import_module(module_name)
        except Exception as exc:
            raise ImportError(f"重载模块 {module_name!r} 失败: {exc}") from exc
        cls._loaded[module_name] = mod
        cls._load_times[module_name] = 0.0  # 重载不统计时间
        return mod

    @classmethod
    def get_module_info(cls, module_name: str) -> Optional[Dict[str, str]]:
        """获取注册表中模块的元数据。

        Args:
            module_name: 模块注册名。

        Returns:
            元数据字典，若模块不在注册表中则返回 ``None``。
        """
        return dict(cls.LAZY_MODULES.get(module_name, {})) or None
