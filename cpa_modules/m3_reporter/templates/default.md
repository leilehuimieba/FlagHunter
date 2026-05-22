# {{ meta.title }}

> **版本**: {{ meta.version }} | **作者**: {{ meta.author }} | **日期**: {{ meta.start_date }} ~ {{ meta.end_date }}
>
> **分类**: {{ meta.classification }} | **公司**: {{ meta.company_name }} | **报告ID**: {{ report_id }}

---

## 执行摘要

{{ executive_summary or "未提供执行摘要。" }}

---

## 测试范围

| 项目 | 内容 |
|------|------|
| **测试目标** | {{ meta.scope or "未指定" }} |
| **测试方法** | {{ meta.methodology or "未指定" }} |
| **测试周期** | {{ meta.start_date }} ~ {{ meta.end_date }} |
| **报告版本** | {{ meta.version }} |
| **保密级别** | {{ meta.classification }} |

---

## 风险摘要

| 严重度 | 数量 | 颜色标识 |
|--------|------|----------|
| 🔴 严重 (Critical) | {{ risk_summary.critical }} | `#dc3545` |
| 🟠 高危 (High) | {{ risk_summary.high }} | `#fd7e14` |
| 🟡 中危 (Medium) | {{ risk_summary.medium }} | `#ffc107` |
| 🔵 低危 (Low) | {{ risk_summary.low }} | `#17a2b8` |
| ⚪ 信息 (Info) | {{ risk_summary.info }} | `#6c757d` |
| **总计** | **{{ risk_summary.total_findings }}** | - |

{% if risk_summary.risk_score %}
**综合风险评分**: {{ "%.1f" | format(risk_summary.risk_score) }} / 10.0
{% endif %}

---

## 详细发现

{% if findings %}
共发现 **{{ findings | length }}** 个安全问题，详情如下：

{% for finding in findings %}
### {{ finding.severity_label }} {{ finding.id }}: {{ finding.title }}

| 属性 | 内容 |
|------|------|
| **ID** | `{{ finding.id }}` |
| **严重度** | {{ finding.severity_label }} |
{% if finding.cvss_score %}
| **CVSS评分** | {{ finding.cvss_score }} |
{% endif %}
{% if finding.cwe_id %}
| **CWE编号** | {{ finding.cwe_id }} |
{% endif %}
{% if finding.affected_target %}
| **影响目标** | `{{ finding.affected_target }}` |
{% endif %}
{% if finding.discovered_at %}
| **发现时间** | {{ finding.discovered_at }} |
{% endif %}

#### 描述

{{ finding.description or "无描述。" }}

{% if finding.impact %}
#### 安全影响

{{ finding.impact }}
{% endif %}

{% if finding.remediation %}
#### 修复建议

{{ finding.remediation }}
{% endif %}

{% if finding.reproduction_steps %}
#### 复现步骤

{% for step in finding.reproduction_steps %}
{{ loop.index }}. {{ step }}
{% endfor %}
{% endif %}

{% if finding.proof_of_concept %}
#### 概念验证 (PoC)

```
{{ finding.proof_of_concept }}
```
{% endif %}

{% if finding.references %}
#### 参考链接

{% for ref in finding.references %}
- [{{ ref }}]({{ ref }})
{% endfor %}
{% endif %}

---
{% endfor %}
{% else %}
未发现安全问题。
{% endif %}

## 攻击路径

{% if attack_paths %}
{% for path in attack_paths %}
### {{ path.name }}

{% if path.description %}
{{ path.description }}
{% endif %}

{% if path.start_point or path.end_point %}
**路径**: `{{ path.start_point }}` → `{{ path.end_point }}`
{% endif %}

{% if path.steps %}
#### 攻击步骤

{% for step in path.steps %}
**Step {{ step.order }}**{% if step.tool_used %} (`{{ step.tool_used }}`){% endif %}{% if step.target %} @ `{{ step.target }}`{% endif %}

{{ step.description }}

{% if step.result %}
> 结果: {{ step.result }}
{% endif %}

{% endfor %}
{% endif %}

---
{% endfor %}
{% else %}
未记录攻击路径。
{% endif %}

## 技术附录

{% if technical_appendix %}
{% for entry in technical_appendix %}
{% if entry.timestamp %}
> 🕐 `{{ entry.timestamp }}`
{% endif %}

{% if entry.command %}
```bash
$ {{ entry.command }}
```
{% endif %}

{% if entry.output %}
```
{{ entry.output }}
```
{% endif %}

---
{% endfor %}
{% else %}
无技术附录数据。
{% endif %}

## 合规声明

{{ compliance_notes or "未提供合规声明。" }}

---

*本报告由 PentestAgent M3 Reporter 模块自动生成。*

*报告ID: {{ report_id }} | 生成时间: {{ generated_at }}*

*{{ meta.disclaimer or '本报告内容仅供授权人员阅读，未经授权不得向第三方披露。' }}*
