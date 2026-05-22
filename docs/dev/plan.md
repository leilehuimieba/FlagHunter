# M1 API Hub 模块开发执行计划

## 任务概述
按照《M1多Agent并行调度手册》的Phased调度策略，完成 `cpa_modules/m1_api_hub/` 目录下6个Python文件的开发，实现对PentestAgent的API接入调度模块二开。

## 技术约束
- Python 3.10+，asyncio异步编程
- 使用标准库dataclass（不用Pydantic）
- Windows环境
- 对原版侵入<25行

## 文件清单（7个文件）
1. `models.py` — 9个数据模型类
2. `config_schema.py` — 环境变量配置解析（4个函数）
3. `provider_manager.py` — ProviderManager调度核心
4. `failover_monitor.py` — 健康检查+故障监控+自动恢复
5. `cost_tracker.py` — Token追踪+预算管理
6. `__init__.py` — 模块入口
7. `status_display.py` — TUI状态面板

## 执行阶段

### Stage 1: Phase 1 并行开发（3个Agent，无依赖）
- **Agent-1**: models.py — ProviderState/ProviderConfig/ProviderStatus/RequestLog/HealthCheckResult/FallbackChain/CostSummary/M1Config/ProviderEvent
- **Agent-2**: config_schema.py — _parse_env_dict/load_provider_from_env/load_all_providers_from_env/load_m1_config_from_env
- **Agent-3**: provider_manager.py — ProviderManager类（register/unregister/get/select/update/mark等方法）
- **产出**: 3个Python文件代码

### Stage 2: Phase 1 审查
- 审查类名一致性、方法签名匹配、状态转换逻辑正确性
- 通过后进入Phase 2

### Stage 3: Phase 2 并行开发（2个Agent，依赖Phase 1输出）
- **Agent-4**: failover_monitor.py — FailoverMonitor类（健康检查/故障转移/自动恢复三大循环）
- **Agent-5**: cost_tracker.py + __init__.py — CostTracker类 + 模块入口初始化
- **产出**: 3个Python文件代码

### Stage 4: Phase 2 审查
- 审查状态转换一致性、接口配合、初始化正确性
- 通过后进入Phase 3

### Stage 5: Phase 3 串行开发（1个Agent，依赖全部前置）
- **Agent-6**: status_display.py + M0侵入层代码 — TUI面板 + 4个Hook点
- **产出**: 1个Python文件 + 4个侵入点代码

### Stage 6: 最终集成审阅
- 文件完整性检查
- 接口一致性检查
- 状态机正确性检查
- 侵入点检查
- 开关检查
- 输出最终6个文件到输出目录

## 技能加载
- Stage 1-5: vibecoding-general-swarm（通用编码技能）
- Stage 6: 最终输出（纯文件写入，无需特殊技能）
