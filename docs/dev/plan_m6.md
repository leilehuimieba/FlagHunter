# M6 Turbo 模块开发执行计划（最终模块）

## 任务概述
按《M6多Agent并行调度手册》完成 `cpa_modules/m6_turbo/` 目录下6个Python文件的开发。M6是透明性能增强层，对M2-M5完全透明。

## 技术约束
- Python 3.10+，标准库为主
- 默认开启（CPA_M6_TURBO=true）
- 安全降级：缓存失效自动回退原始执行
- 资源可控：内存/并发/缓存上限可配置
- 侵入最小：只在工具执行层加wrapper

## 文件清单（6个文件）
1. `result_cache.py` — 扫描结果缓存TTL+LRU（Agent-30）
2. `parallel_scanner.py` — 并发扫描器Semaphore（Agent-31）
3. `lazy_loader.py` — 延迟加载统一封装（Agent-32）
4. `memory_optimizer.py` — 内存优化监控（Agent-32）
5. `__init__.py` — 模块入口+全局wrapper注册（Agent-33）
6. `turbo_commands.py` — /turbo命令（Agent-33）

## 执行阶段

### Stage 1: Phase 1 并行开发（3个Agent）
- **Agent-30**: result_cache.py — ResultCache类（get/set/invalidate/LRU/内存控制）
- **Agent-31**: parallel_scanner.py — ParallelScanner类（execute/execute_batch/Semaphore/依赖图）
- **Agent-32**: lazy_loader.py + memory_optimizer.py — LazyLoader+MemoryOptimizer

### Stage 2: Phase 1 审查
- LRU淘汰、双重Semaphore、wrap_import代理

### Stage 3: Phase 2 串行开发（1个Agent）
- **Agent-33**: __init__.py + turbo_commands.py + 4个M0 HOOK

### Stage 4: 最终集成审阅
- 文件完整性、缓存正确性、并发安全、透明wrapper、默认开启
- **全部6个模块开发完成！**
