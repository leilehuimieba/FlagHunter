# M3 Reporter 模块开发执行计划

## 任务概述
按《M3多Agent并行调度手册》完成 `cpa_modules/m3_reporter/` 目录下报告生成系统的开发。

## 技术约束
- Python 3.10+，Jinja2模板引擎（轻量，可接受）
- Playwright延迟加载（PentestAgent已有依赖）
- 双格式输出（HTML + Markdown），PDF通过Playwright
- 增量生成：边扫描边追加
- M0侵入<15行
- Windows兼容：pathlib

## 文件清单

### Python模块（8个文件）
1. `report_models.py` — 7个数据模型（Agent-13）
2. `template_engine.py` — TemplateEngine类（Agent-13）
3. `report_generator.py` — ReportGenerator类（Agent-14）
4. `html_exporter.py` — HTML导出（Agent-15）
5. `markdown_exporter.py` — Markdown导出（Agent-15）
6. `pdf_exporter.py` — PDF导出（Agent-15）
7. `screenshot_catcher.py` — Playwright截图（Agent-16）
8. `incremental_tracker.py` — 增量追踪（Agent-16）
9. `__init__.py` — 模块入口（Agent-18）

### 模板文件（3+4=7个文件）
- `templates/default.html`（Agent-17）
- `templates/default.md`（Agent-17）
- `templates/pentest_full.html`（Agent-17）
- `templates/components/cover.html`（Agent-17）
- `templates/components/risk_matrix.html`（Agent-17）
- `templates/components/finding_detail.html`（Agent-17）
- `templates/components/attack_path.html`（Agent-17）

### 静态资源
- `static/style.css`（Agent-17）

## 执行阶段

### Stage 1: Phase 1 并行开发（3个Agent）
- **Agent-13**: report_models.py + template_engine.py
- **Agent-14**: report_generator.py
- **Agent-15**: html_exporter.py + markdown_exporter.py + pdf_exporter.py

### Stage 2: Phase 1 审查
- to_dict()输出结构 vs TemplateEngine.render() data参数
- export_html()是否正确调用html_exporter
- 三个导出器函数签名一致性

### Stage 3: Phase 2 并行开发（2个Agent）
- **Agent-16**: screenshot_catcher.py + incremental_tracker.py
- **Agent-17**: 7个模板文件 + style.css

### Stage 4: Phase 2 审查
- ScreenshotCatcher返回值与Finding.screenshots匹配
- IncrementalTracker.flush()正确调用add_finding()
- 模板Jinja2变量名与to_dict()键名一致

### Stage 5: Phase 3 串行开发（1个Agent）
- **Agent-18**: __init__.py + 4个M0 HOOK

### Stage 6: 最终集成审阅
- 文件完整性、模板变量一致性、导出链路、增量链路、M0侵入量
