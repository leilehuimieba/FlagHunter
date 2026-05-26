# Schema Changelog

> 凡涉及 CTFState / StrategyMemoryEntry / CapabilityRegistry 等 VersionedEntity 的 schema 变更，
> 必须在此文件追加一行记录，再提交代码。
>
> 格式规则：
> - major 变更（字段删除/类型变更）：必须同时提供 migration 函数
> - minor 变更（新增可选字段）：向后兼容，无需 migration
> - patch 变更（默认值调整）：直接记录

| 日期 | 实体 | 旧版本 | 新版本 | 变更类型 | 说明 | migration 函数 |
|---|---|---|---|---|---|---|
| 2026-05-23 | CTFState | — | 1.0 | 初始版本 | 文档建立 | — |
| 2026-05-23 | CTFState | 1.0 | 1.1 | minor | 新增 exploration_agenda 字段与 ExplorationItem 条目契约 | — |
| 2026-05-24 | CTFState | 1.1 | 1.2 | minor | 新增 llm_exploration_steps / llm_exploration_log / weak_decision_log 与 LLMStepLog 契约 | — |
| 2026-05-23 | StrategyMemoryEntry | — | 1.0 | 初始版本 | 文档建立 | — |
| 2026-05-23 | CapabilityRegistry | — | 1.0 | 初始版本 | 文档建立 | — |
