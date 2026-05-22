"""
PentestAgent M6 Turbo — 扫描结果缓存模块 (result_cache.py)

带 TTL 过期与 LRU 淘汰的线程安全内存缓存。
支持批量读写、后台定时清理、内存上限保护，以及破坏性操作的缓存屏蔽。

技术约束: Python 3.10+; 标准库 (threading, time, hashlib, json, collections);
零外部依赖; threading.RLock 线程安全; 中文 docstring。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# TTL 策略 — 按工具类型区分存活时间（秒）
# ---------------------------------------------------------------------------
_TTL_MAP: dict[str, int] = {"nmap": 300, "sqlmap": 3600, "crypto": 86400}

_NON_CACHEABLE_TOOL_KEYWORDS = (
    "rm", "del", "delete", "remove", "drop", "exploit",
    "exec", "shell", "reverse", "payload",
)
_NON_CACHEABLE_PARAM_KEYS = ("_force", "_nocache", "_no_cache", "_refresh")


# ===========================================================================
# 数据模型
# ===========================================================================

@dataclass
class CacheEntry:
    """单个缓存条目。"""
    key: str
    tool_name: str
    target: str
    params: dict
    result: dict
    created_at: float
    ttl: int = 3600
    hit_count: int = 0
    size_bytes: int = 0

    @property
    def is_expired(self) -> bool:
        """条目是否已超出 TTL。"""
        return time.time() - self.created_at > self.ttl

    @property
    def age_seconds(self) -> float:
        """条目已存活秒数。"""
        return time.time() - self.created_at


@dataclass
class CacheStats:
    """缓存全局统计快照。"""
    total_entries: int = 0
    expired_entries: int = 0
    total_hits: int = 0
    total_misses: int = 0
    total_evictions: int = 0
    current_size_bytes: int = 0
    hit_rate: float = 0.0
    avg_entry_age: float = 0.0


# ===========================================================================
# ResultCache — 核心缓存类
# ===========================================================================

class ResultCache:
    """线程安全的扫描结果内存缓存，支持 TTL 过期与 LRU 淘汰。

    参数:
        max_size:      缓存最大条目数（默认 1000）。
        default_ttl:   默认 TTL 秒数（默认 3600）。
        max_memory_mb: 内存上限 MB（默认 100）。
    """

    def __init__(
        self, max_size: int = 1000, default_ttl: int = 3600, max_memory_mb: int = 100
    ) -> None:
        self._max_size: int = max_size
        self._default_ttl: int = default_ttl
        self._max_memory_bytes: int = max_memory_mb * 1024 * 1024

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock: threading.RLock = threading.RLock()
        self._stats: CacheStats = CacheStats()

        self._cleanup_interval: int = 60
        self._cleanup_task: Optional[threading.Timer] = None
        self._stop_event: bool = False

        self._start_cleanup_loop()

    # ---- 公共 API ----

    def get(
        self, tool_name: str, target: str, params: Optional[dict] = None
    ) -> Optional[dict]:
        """查询缓存。命中→move_to_end→hit_count++→返回result。过期→删除→返回None。"""
        key = self._generate_key(tool_name, target, params)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats.total_misses += 1
                return None
            if entry.is_expired:
                del self._cache[key]
                self._stats.total_entries = len(self._cache)
                self._stats.total_misses += 1
                return None
            self._cache.move_to_end(key)
            entry.hit_count += 1
            self._stats.total_hits += 1
            return entry.result

    def set(
        self,
        tool_name: str,
        target: str,
        result: dict,
        params: Optional[dict] = None,
        ttl: Optional[int] = None,
    ) -> str:
        """写入缓存。生成key→检查内存→LRU淘汰→写入OrderedDict→返回key。"""
        if not self.is_cacheable(tool_name, target, params):
            return self._generate_key(tool_name, target, params)
        key = self._generate_key(tool_name, target, params)
        entry = CacheEntry(
            key=key,
            tool_name=tool_name,
            target=target,
            params=params or {},
            result=result,
            created_at=time.time(),
            ttl=ttl if ttl is not None else self._resolve_ttl(tool_name),
            size_bytes=self._estimate_size(result),
        )
        with self._lock:
            if key in self._cache:
                self._cache.pop(key)
            self._enforce_limits()
            self._cache[key] = entry
            self._cache.move_to_end(key)
            self._stats.total_entries = len(self._cache)
        return key

    def invalidate(
        self, tool_name: Optional[str] = None, target: Optional[str] = None
    ) -> int:
        """按条件失效缓存。tool_name与target均为None时清空全部。返回失效数量。"""
        removed = 0
        with self._lock:
            if tool_name is None and target is None:
                removed = len(self._cache)
                self._cache.clear()
                self._stats.total_entries = 0
                self._stats.current_size_bytes = 0
                return removed
            keys_to_remove = [
                k for k, e in self._cache.items()
                if (tool_name is None or e.tool_name == tool_name)
                and (target is None or e.target == target)
            ]
            for k in keys_to_remove:
                del self._cache[k]
                removed += 1
            self._stats.total_entries = len(self._cache)
        return removed

    def invalidate_expired(self) -> int:
        """清理所有已过期的缓存条目。返回清理数量。"""
        with self._lock:
            expired_keys = [k for k, e in self._cache.items() if e.is_expired]
            for k in expired_keys:
                del self._cache[k]
            self._stats.total_entries = len(self._cache)
            return len(expired_keys)

    def get_batch(self, queries: List[tuple]) -> List[Optional[dict]]:
        """批量查询缓存。queries 为 (tool_name, target, params?) 元组列表。"""
        return [
            self.get(q[0], q[1], q[2]) if len(q) >= 3 else self.get(q[0], q[1])
            for q in queries
        ]

    def set_batch(self, entries: List[tuple]) -> List[str]:
        """批量写入缓存。entries 为 (tool_name, target, result, params?, ttl?) 元组列表。"""
        keys: List[str] = []
        for e in entries:
            if len(e) >= 5:
                keys.append(self.set(e[0], e[1], e[2], e[3], e[4]))
            elif len(e) == 4:
                keys.append(self.set(e[0], e[1], e[2], e[3]))
            else:
                keys.append(self.set(e[0], e[1], e[2]))
        return keys

    def get_stats(self) -> CacheStats:
        """获取实时统计快照。hit_rate = hits / (hits + misses)。"""
        with self._lock:
            total = self._stats.total_hits + self._stats.total_misses
            hit_rate = self._stats.total_hits / total if total > 0 else 0.0
            entries_list = list(self._cache.values())
            ages = [e.age_seconds for e in entries_list]
            avg_age = sum(ages) / len(ages) if ages else 0.0
            expired_count = sum(1 for e in entries_list if e.is_expired)
            current_size = sum(e.size_bytes for e in entries_list)
            return CacheStats(
                total_entries=len(self._cache),
                expired_entries=expired_count,
                total_hits=self._stats.total_hits,
                total_misses=self._stats.total_misses,
                total_evictions=self._stats.total_evictions,
                current_size_bytes=current_size,
                hit_rate=round(hit_rate, 4),
                avg_entry_age=round(avg_age, 2),
            )

    def get_entries(
        self,
        tool_name: Optional[str] = None,
        target: Optional[str] = None,
        include_expired: bool = False,
    ) -> List[CacheEntry]:
        """获取符合条件的缓存条目列表。"""
        with self._lock:
            return [
                e for e in self._cache.values()
                if (tool_name is None or e.tool_name == tool_name)
                and (target is None or e.target == target)
                and (include_expired or not e.is_expired)
            ]

    def stop(self) -> None:
        """停止后台清理循环。"""
        self._stop_event = True
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    def is_cacheable(
        self, tool_name: str, target: str, params: Optional[dict] = None
    ) -> bool:
        """判断是否可缓存。不缓存 rm/del/exploit 等破坏性操作及含 _force/_nocache 的参数。"""
        t_lower = tool_name.lower()
        if any(kw in t_lower for kw in _NON_CACHEABLE_TOOL_KEYWORDS):
            return False
        if params and any(pk in params for pk in _NON_CACHEABLE_PARAM_KEYS):
            return False
        return True

    # ---- 内部方法 ----

    def _start_cleanup_loop(self) -> None:
        """启动后台 threading.Timer 定时清理任务（60 秒周期）。"""
        def _loop() -> None:
            if self._stop_event:
                return
            self._cleanup()
            self._cleanup_task = threading.Timer(self._cleanup_interval, _loop)
            self._cleanup_task.daemon = True
            self._cleanup_task.start()

        self._cleanup_task = threading.Timer(self._cleanup_interval, _loop)
        self._cleanup_task.daemon = True
        self._cleanup_task.start()

    def _cleanup(self) -> int:
        """清理过期条目，超限则执行 LRU 淘汰。返回淘汰总数。"""
        removed = self.invalidate_expired()
        with self._lock:
            if len(self._cache) > self._max_size:
                removed += self._evict_lru(len(self._cache) - self._max_size)
            if not self._check_memory():
                removed += self._evict_aggressive()
        if removed > 0:
            self._stats.total_evictions += removed
        return removed

    def _check_memory(self) -> bool:
        """检查当前缓存总大小是否在内存限制内。True=未超限。"""
        total = sum(e.size_bytes for e in self._cache.values())
        self._stats.current_size_bytes = total
        return total <= self._max_memory_bytes

    def _evict_lru(self, n: int = 1) -> int:
        """淘汰 OrderedDict 头部（最久未使用）的 n 个条目。返回实际淘汰数。"""
        removed = 0
        for _ in range(n):
            if not self._cache:
                break
            self._cache.popitem(last=False)
            removed += 1
        self._stats.total_entries = len(self._cache)
        return removed

    def _evict_aggressive(self) -> int:
        """激进淘汰：先清过期，再清一半 LRU 条目。返回淘汰总数。"""
        removed = self.invalidate_expired()
        with self._lock:
            half = len(self._cache) // 2
            if half > 0:
                removed += self._evict_lru(half)
        return removed

    def _enforce_limits(self) -> None:
        """写入前强制确保容量与内存均不超限。"""
        if len(self._cache) >= self._max_size:
            self._evict_lru(len(self._cache) - self._max_size + 1)
        if not self._check_memory():
            self._evict_aggressive()

    @staticmethod
    def _estimate_size(result: dict) -> int:
        """估算结果字典 JSON 序列化后的字节长度。"""
        return len(json.dumps(result, ensure_ascii=False, default=str))

    @staticmethod
    def _generate_key(
        tool_name: str, target: str, params: Optional[dict] = None
    ) -> str:
        """生成缓存 key: sha256(f'{tool_name}:{target}:{sorted_params_json}')。"""
        sorted_params = ""
        if params:
            try:
                sorted_params = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                sorted_params = str(params)
        return hashlib.sha256(f"{tool_name}:{target}:{sorted_params}".encode("utf-8")).hexdigest()

    def _resolve_ttl(self, tool_name: str) -> int:
        """根据工具名称解析 TTL。匹配 _TTL_MAP 前缀，未匹配则使用 default_ttl。"""
        t_lower = tool_name.lower()
        for prefix, ttl_val in _TTL_MAP.items():
            if prefix in t_lower:
                return ttl_val
        return self._default_ttl
