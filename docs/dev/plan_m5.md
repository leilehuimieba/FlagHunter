# M5 Swarm Link 模块开发执行计划

## 任务概述
按《M5多Agent并行调度手册》完成 `cpa_modules/m5_swarm_link/` 目录下6个Python文件的开发。

## 技术约束
- Python 3.10+，SQLite共享黑板（零外部依赖）
- 默认关闭（CPA_M5_SWARM_LINK=false）
- 不重构Crew模式，只增强通信层
- M0侵入<15行

## 文件清单（6个文件）
1. `shared_blackboard.py` — SQLite共享黑板（Agent-25）
2. `pheromone_router.py` — 信息素路由器（Agent-26）
3. `agent_messenger.py` — Agent通信协议（Agent-27）
4. `consensus_mechanism.py` — 共识投票机制（Agent-28）
5. `__init__.py` — 模块入口（Agent-29）
6. `swarm_commands.py` — /swarm命令（Agent-29）

## 执行阶段

### Stage 1: Phase 1 并行开发（3个Agent，无依赖）
- **Agent-25**: shared_blackboard.py — SQLite黑板+消息存储/查询/订阅
- **Agent-26**: pheromone_router.py — 信息素动态优先级
- **Agent-27**: agent_messenger.py — Agent间通信协议

### Stage 2: Phase 1 审查
- metadata JSON序列化、current_strength动态计算、receive()超时

### Stage 3: Phase 2 串行开发（1个Agent，依赖Phase 1）
- **Agent-28**: consensus_mechanism.py — Borda计数+投票

### Stage 4: Phase 2 审查
- Borda计数正确性、timeout机制、阈值判断

### Stage 5: Phase 3 串行开发（1个Agent，依赖全部）
- **Agent-29**: __init__.py + swarm_commands.py + 4个M0 HOOK

### Stage 6: 最终集成审阅
- 文件完整性、信息素衰减公式、消息链路、共识流程、默认关闭
