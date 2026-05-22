# M3 模块（报告生成系统）多Agent并行开发调度手册

> **使用方式**：将此文档上传到新对话，按Phase分批创建Agent并执行  
> **前置条件**：M1+M2已完成，M3依赖M1的CostTracker获取Token消耗数据  
> **借鉴来源**：RedAmon的11章节专业HTML报告结构  

---

## M3模块设计概要

### 解决什么问题

PentestAgent原版报告能力极弱——纯文本输出，无格式化、无结构、无专业感。M3补齐**企业级专业报告**能力，让渗透测试的交付物可以直接提交给客户。

### 借鉴来源

| 借鉴对象 | 借鉴内容 | 改进点 |
|---------|---------|--------|
| **RedAmon** | 11章节报告结构 | 简化到8核心章节，保留关键内容 |
| **RedAmon** | Jinja2模板引擎 | 增加Markdown模板，双格式输出 |
| **RedAmon** | HTML报告+CSS样式 | 增加响应式设计、暗色模式支持 |
| **PentestAgent** | 已有Playwright依赖 | 用于PDF导出+截图，不新增依赖 |

### 报告结构（8核心章节）

```
1. 封面页        — 项目名称、日期、版本、保密声明
2. 执行摘要      — LLM生成：测试范围、关键发现、风险评级、建议概述
3. 测试范围      — 授权目标IP/域名/时间窗口、测试方法说明
4. 风险摘要      — 风险矩阵图表、高危/中危/低危数量统计
5. 详细发现      — 每个漏洞：标题、CVSS评分、描述、复现步骤、影响、修复建议
6. 攻击路径图    — 从入口到目标的完整攻击链可视化
7. 技术附录      — 所有执行的命令及其输出（审计日志导出）
8. 合规声明      — 授权确认、测试局限性、免责声明
```

### 架构设计

```
cpa_modules/m3_reporter/
├── __init__.py                  # 模块入口 + 开关（Agent-18实现）
├── report_models.py             # 数据模型：Report/Finding/AttackPath等（Agent-13）
├── template_engine.py           # Jinja2模板引擎：加载/渲染/缓存（Agent-13）
├── report_generator.py          # 报告生成核心：组装→渲染→导出（Agent-14）
├── html_exporter.py             # HTML导出器（Agent-15）
├── markdown_exporter.py         # Markdown导出器（Agent-15）
├── pdf_exporter.py              # PDF导出器（Playwright）（Agent-15）
├── screenshot_catcher.py        # 漏洞页面截图（Playwright）（Agent-16）
├── incremental_tracker.py       # 增量更新：边扫描边追加（Agent-16）
├── templates/                   # Jinja2模板文件（Agent-17）
│   ├── default.html             # 默认HTML模板（简洁版）
│   ├── default.md               # 默认Markdown模板
│   ├── pentest_full.html        # 完整渗透测试报告模板
│   └── components/              # 可复用模板组件
│       ├── cover.html           # 封面组件
│       ├── risk_matrix.html     # 风险矩阵图表
│       ├── finding_detail.html  # 单个漏洞详情
│       └── attack_path.html     # 攻击路径可视化
└── static/                      # 静态资源（CSS）
    └── style.css
```

### 关键设计约束

1. **不新增重量级依赖**：使用PentestAgent已有的Playwright做PDF导出，Jinja2是常见轻量模板引擎
2. **双格式输出**：同一份报告数据可同时生成HTML和Markdown
3. **增量生成**：支持"边扫描边生成"，新发现自动追加到报告
4. **模块化侵入<15行**：注册 `/report` 命令 + 1个settings字段 + 1个init hook
5. **Windows兼容**：所有文件操作使用Python标准库pathlib

### 环境变量开关

```bash
# .env
CPA_M3_REPORTER=true             # M3总开关
CPA_M3_OUTPUT_DIR=./reports      # 报告输出目录
CPA_M3_COMPANY_NAME=CPA安全团队   # 报告中的公司名
CPA_M3_COMPANY_LOGO=             # Logo图片路径（可选）
CPA_M3_TEMPLATE=default          # 默认模板名
CPA_M3_AUTO_SAVE=true            # 是否自动保存报告
```

---

## Phase 1：并行启动（3个Agent，无依赖）

### Agent-13：report_models.py + template_engine.py

**系统提示词：**
```
你是PentestAgent M3模块的报告数据模型和模板引擎开发专家。编写两个文件：report_models.py和template_engine.py。

技术要求：Python 3.10+，标准库dataclass，Jinja2模板引擎（import jinja2）。

【文件1：report_models.py】

定义以下数据模型（dataclass，每个字段中文docstring）：

1. Severity(str, Enum) — 严重程度：CRITICAL("严重", score=9.0-10.0)/HIGH("高危", 7.0-8.9)/MEDIUM("中危", 4.0-6.9)/LOW("低危", 0.1-3.9)/INFO("信息", 0.0)
   类方法：from_cvss(score: float) -> Severity
   属性：color — CRITICAL=#dc3545, HIGH=#fd7e14, MEDIUM=#ffc107, LOW=#17a2b8, INFO=#6c757d

2. Finding — 单个漏洞发现：
   id:str(如"FIND-001"), title:str, severity:Severity, cvss_score:float
   description:str, affected_target:str, proof_of_concept:str
   reproduction_steps:List[str], impact:str, remediation:str
   references:List[str], screenshots:List[str]=[], discovered_at:datetime=now
   verified:bool=False, cwe_id:str="", owasp_category:str=""
   方法：to_dict() -> dict; summary() -> str(一行摘要)

3. AttackStep — 攻击路径中的一个步骤：
   order:int, description:str, tool_used:str, target:str
   result:str, screenshot:str="", duration_ms:int=0

4. AttackPath — 完整的攻击路径：
   name:str, description:str, steps:List[AttackStep]
   start_point:str, end_point:str, total_duration_ms:int=0
   方法：to_mermaid() -> str(生成Mermaid流程图语法)

5. ReportMeta — 报告元数据：
   title:str, subtitle:str="", version:str="1.0"
   author:str, company_name:str, company_logo:str=""
   start_date:datetime, end_date:datetime
   scope:str, methodology:str="OWASP Testing Guide v4"
   classification:str="机密" — 保密级别
   disclaimer:str — 免责声明文本

6. RiskSummary — 风险摘要统计：
   critical:int=0, high:int=0, medium:int=0, low:int=0, info:int=0
   total_findings:int(计算属性)
   risk_score:float(计算属性 = weighted平均)
   方法：get_chart_data() -> dict(用于图表渲染)

7. PentestReport — 完整报告：
   meta:ReportMeta, executive_summary:str="", risk_summary:RiskSummary
   findings:List[Finding]=[], attack_paths:List[AttackPath]=[]
   technical_appendix:List[dict]=[], compliance_notes:str=""
   generated_at:datetime=now, report_id:str(UUID)
   方法：
   - add_finding(f: Finding) -> str(返回finding id)
   - add_attack_path(p: AttackPath) -> None
   - add_appendix_entry(cmd: str, output: str) -> None
   - update_executive_summary(summary: str) -> None
   - to_dict() -> dict(用于模板渲染)
   类方法：from_session(session_id: str) -> PentestReport(从PentestAgent会话数据构建)

【文件2：template_engine.py】

class TemplateEngine:
    """Jinja2模板引擎 — 管理模板加载、渲染和缓存"""
    
    def __init__(self, template_dir: str = "templates"):
        """初始化Jinja2 Environment，从template_dir加载模板"""
    
    def load_template(self, name: str) -> jinja2.Template:
        """加载指定模板，支持.html和.md后缀自动识别"""
    
    def list_templates(self) -> List[str]:
        """列出所有可用模板"""
    
    def render(self, template_name: str, data: dict) -> str:
        """渲染模板，传入数据字典，返回渲染后的字符串"""
    
    def render_string(self, template_string: str, data: dict) -> str:
        """从字符串直接渲染（用于内联模板）"""
    
    def register_filter(self, name: str, func: Callable) -> None:
        """注册自定义Jinja2过滤器"""
        # 内置过滤器：
        # - severity_color: Severity -> CSS颜色
        # - severity_label: Severity -> 中文标签
        # - format_datetime: datetime -> 格式化字符串
        # - truncate: str, int -> 截断文本
        # - cvss_badge: float -> CVSS评分徽章HTML
    
    def _setup_builtin_filters(self) -> None:
        """注册所有内置过滤器"""
    
    @staticmethod
    def _default_template_data() -> dict:
        """返回默认模板数据（CSS样式、通用变量等）"""

两个文件都要有完整的__all__导出。
输出：两个文件的完整代码，用"=== report_models.py ==="和"=== template_engine.py ==="分隔。
```

**期望输出**：`report_models.py`（200-250行）+ `template_engine.py`（150-200行）

---

### Agent-14：report_generator.py 报告生成核心

**系统提示词：**
```
你是PentestAgent M3模块的报告生成核心开发专家。编写report_generator.py，实现报告的组装、渲染和导出流程。

你依赖的接口（假设已由Agent-13提供）：

from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

@dataclass class PentestReport:
    meta: ReportMeta; executive_summary: str=""; risk_summary: RiskSummary
    findings: List[Finding]=[]; attack_paths: List[AttackPath]=[]
    technical_appendix: List[dict]=[]; compliance_notes: str=""
    generated_at: datetime; report_id: str
    def add_finding(self, f: Finding) -> str: ...
    def add_attack_path(self, p: AttackPath) -> None: ...
    def add_appendive_entry(self, cmd: str, output: str) -> None: ...
    def update_executive_summary(self, summary: str) -> None: ...
    def to_dict(self) -> dict: ...

class TemplateEngine:
    def render(self, template_name: str, data: dict) -> str: ...
    def load_template(self, name: str) -> jinja2.Template: ...

def html_export(report: PentestReport, output_path: str) -> str: ...  # 返回文件路径
def markdown_export(report: PentestReport, output_path: str) -> str: ...
def pdf_export(report: PentestReport, output_path: str) -> str: ...

请实现ReportGenerator类：

class ReportGenerator:
    """报告生成器 — 组装报告数据、渲染模板、导出多种格式"""
    
    def __init__(self, template_engine: TemplateEngine, output_dir: str = "./reports"):
        """初始化，传入TemplateEngine实例和输出目录"""
        self._engine = template_engine
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._current_report: Optional[PentestReport] = None
    
    # === 报告生命周期 ===
    def create_report(self, meta: ReportMeta) -> PentestReport:
        """创建一个新的空报告，设置元数据"""
    
    def get_current_report(self) -> Optional[PentestReport]:
        """获取当前正在编辑的报告"""
    
    def finalize_report(self) -> PentestReport:
        """完成报告：自动生成executive_summary（调用LLM）、更新risk_summary统计、标记完成时间"""
    
    # === 增量更新 ===
    def add_finding(self, title: str, severity: str, description: str, target: str,
                   proof: str = "", steps: List[str] = None, impact: str = "",
                   remediation: str = "", cvss: float = None) -> str:
        """添加一个漏洞发现到当前报告。返回finding_id。
        这是增量接口：边扫描边调用，实时追加到报告。"""
    
    def add_screenshot_to_finding(self, finding_id: str, screenshot_path: str) -> None:
        """为指定漏洞添加截图"""
    
    def add_command_output(self, command: str, output: str, target: str = "") -> None:
        """添加一条命令执行记录到技术附录"""
    
    def add_attack_path(self, name: str, steps: List[AttackStep]) -> None:
        """添加一条攻击路径"""
    
    # === 导出 ===
    def export_html(self, report: PentestReport = None, template: str = "default") -> str:
        """导出HTML报告。返回生成的文件路径。"""
        # 流程：report.to_dict() -> template_engine.render(template+".html", data) -> 写入文件
    
    def export_markdown(self, report: PentestReport = None, template: str = "default") -> str:
        """导出Markdown报告。返回文件路径。"""
    
    def export_pdf(self, report: PentestReport = None, template: str = "default") -> str:
        """导出PDF报告（调用pdf_exporter，底层用Playwright）。返回文件路径。"""
    
    def export_all(self, report: PentestReport = None, template: str = "default") -> dict:
        """同时导出HTML+Markdown+PDF，返回 {html: path, md: path, pdf: path}"""
    
    def auto_save(self, report: PentestReport = None) -> str:
        """自动保存报告到output_dir/auto_save/目录，以时间戳命名"""
    
    # === 辅助 ===
    def _generate_executive_summary(self, report: PentestReport) -> str:
        """自动生成执行摘要（基于报告数据拼接文本，后续可接入LLM生成）
        当前版本：基于统计数据生成固定格式摘要"""
    
    def _update_risk_summary(self, report: PentestReport) -> None:
        """根据findings列表自动更新risk_summary统计"""

每个方法完整实现，中文docstring。
输出：完整的report_generator.py文件。
```

**期望输出**：`report_generator.py`（250-350行）

---

### Agent-15：html_exporter.py + markdown_exporter.py + pdf_exporter.py

**系统提示词：**
```
你是PentestAgent M3模块的导出器开发专家。编写三个导出器文件。

【文件1：html_exporter.py】

依赖接口（假设存在）：
class TemplateEngine: def render(self, template_name: str, data: dict) -> str: ...
@dataclass class PentestReport: def to_dict(self) -> dict: ...

实现：
def export_html(report: PentestReport, output_path: str, template_engine: TemplateEngine, template_name: str = "default") -> str:
    """导出HTML报告。
    1. 准备数据：report.to_dict() + 添加CSS样式 + 添加通用变量
    2. 渲染模板：template_engine.render(template_name + ".html", data)
    3. 写入文件：output_path（如以/结尾则自动生成文件名）
    4. 返回最终文件路径
    """

def _get_default_css() -> str:
    """返回默认内联CSS样式（确保HTML文件独立可查看，不依赖外部CSS文件）
    样式要求：
    - 专业安全报告的配色（低饱和度、深蓝/灰色系）
    - 响应式布局（max-width: 1200px居中）
    - 表格样式（发现列表用斑马纹表格）
    - Severity颜色：CRITICAL=#dc3545, HIGH=#fd7e14, MEDIUM=#ffc107, LOW=#17a2b8, INFO=#6c757d
    - 打印友好（@media print适配）
    """

【文件2：markdown_exporter.py】

实现：
def export_markdown(report: PentestReport, output_path: str, template_engine: TemplateEngine, template_name: str = "default") -> str:
    """导出Markdown报告。
    1. 准备数据：report.to_dict()
    2. 渲染模板：template_engine.render(template_name + ".md", data)
    3. 写入文件
    4. 返回文件路径
    注意：Markdown模板生成的是标准GFM格式（GitHub Flavored Markdown），
    可直接在GitHub/GitLab查看，也可用Pandoc转其他格式。
    """

def _get_default_md_template() -> str:
    """返回默认Markdown模板字符串（内联备用，当模板文件不存在时使用）
    模板应包含以下章节：
    # {{ meta.title }}
    ## 执行摘要
    ## 测试范围
    ## 风险摘要（用ASCII表格展示统计）
    ## 详细发现（每个发现用 ### 标题）
    ## 攻击路径
    ## 技术附录
    ## 合规声明
    """

【文件3：pdf_exporter.py】

实现：
def export_pdf(report: PentestReport, output_path: str, template_engine: TemplateEngine, template_name: str = "default") -> str:
    """导出PDF报告。
    使用Playwright生成PDF（PentestAgent已有playwright依赖）：
    1. 先调用export_html生成临时HTML文件
    2. 用playwright打开HTML，调用page.pdf()生成PDF
    3. 删除临时HTML文件
    4. 返回PDF文件路径
    
    PDF配置：A4纸张、打印背景、页眉页脚（页码和报告标题）
    """

导入方式（延迟加载Playwright）：
_PW_AVAILABLE = False
_pw = None

def _get_playwright():
    global _PW_AVAILABLE, _pw
    if _pw is None:
        try:
            from playwright.async_api import async_playwright
            _pw = async_playwright
            _PW_AVAILABLE = True
        except ImportError:
            pass
    return _pw

输出：三个文件的完整代码，用"=== html_exporter.py ==="等分隔。
```

**期望输出**：3个导出器文件，各80-120行

---

## Phase 1 返回检查点

**三个Agent完成后，把代码复制回主控。主控审查：**
1. report_models.py中PentestReport.to_dict()的输出结构是否与TemplateEngine.render()的data参数匹配
2. report_generator.export_html()是否正确调用了html_exporter.export_html()
3. 三个导出器的函数签名是否一致（参数名称、顺序、返回值类型）

---

## Phase 2：并行启动（2个Agent，依赖Phase 1的模型）

### Agent-16：screenshot_catcher.py + incremental_tracker.py

**系统提示词：**
```
你是PentestAgent M3模块的截图捕获和增量追踪开发专家。编写两个文件。

【文件1：screenshot_catcher.py】

技术要求：延迟加载Playwright，异常安全，中文docstring。

实现：
class ScreenshotCatcher:
    """漏洞页面截图捕获器 — 用Playwright对漏洞页面自动截图"""
    
    def __init__(self, output_dir: str = "./reports/screenshots"):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
    
    async def capture(self, url: str, finding_id: str = None, 
                      full_page: bool = False, wait_for: str = None) -> str:
        """对指定URL截图。
        1. 启动Playwright浏览器（headless）
        2. 访问URL
        3. 如指定wait_for，等待该CSS选择器出现
        4. 截图保存到output_dir/{finding_id or timestamp}.png
        5. 关闭浏览器
        6. 返回截图文件路径
        注意：捕获所有异常，失败返回空字符串。
        """
    
    async def capture_element(self, url: str, selector: str, finding_id: str = None) -> str:
        """对页面的指定元素截图（如错误弹窗、SQL注入结果区域）"""
    
    async def capture_multiple(self, urls: List[str], finding_id: str = None) -> List[str]:
        """批量截图，返回文件路径列表"""
    
    def _generate_filename(self, finding_id: str = None) -> str:
        """生成截图文件名：{finding_id}_{timestamp}.png 或 screenshot_{timestamp}.png"""

【文件2：incremental_tracker.py】

实现：
class IncrementalTracker:
        """增量报告追踪器 — 边扫描边更新报告，支持实时预览"""
    
    def __init__(self, report_generator: ReportGenerator, auto_save_interval: int = 300):
        """初始化，传入ReportGenerator实例和自动保存间隔（秒，默认5分钟）"""
        self._generator = report_generator
        self._interval = auto_save_interval
        self._last_save = 0
        self._pending_findings: List[Finding] = []  # 待写入的发现
        self._pending_appendix: List[dict] = []      # 待写入的附录
    
    def queue_finding(self, finding: Finding) -> None:
        """将发现加入待写入队列"""
    
    def queue_appendix(self, command: str, output: str) -> None:
        """将命令输出加入待写入队列"""
    
    async def flush(self) -> None:
        """将队列中的所有待写入项实际写入报告，并触发自动保存（如超过间隔）"""
    
    async def auto_flush_loop(self) -> None:
        """后台自动flush循环（每auto_save_interval秒执行一次flush）"""
    
    def get_preview(self) -> str:
        """获取当前报告的实时预览摘要（用于TUI显示）
        返回格式："报告: 3个发现(1高1中1低) | 上次保存: 2分钟前"
        """

每个方法完整实现，中文docstring。
输出：两个文件的完整代码，用"=== screenshot_catcher.py ==="和"=== incremental_tracker.py ==="分隔。
```

**期望输出**：`screenshot_catcher.py`（100-150行）+ `incremental_tracker.py`（100-150行）

---

### Agent-17：templates/（HTML和Markdown默认模板）

**系统提示词：**
```
你是PentestAgent M3模块的模板设计师。编写3个Jinja2模板文件。

模板变量说明（由report_models.py的PentestReport.to_dict()提供）：

{
  "meta": {
    "title", "subtitle", "version", "author", "company_name",
    "start_date", "end_date", "scope", "methodology", "classification", "disclaimer"
  },
  "executive_summary": "...",
  "risk_summary": {
    "critical", "high", "medium", "low", "info",
    "total_findings", "risk_score"
  },
  "findings": [
    {
      "id", "title", "severity", "severity_color", "cvss_score",
      "description", "affected_target", "proof_of_concept",
      "reproduction_steps", "impact", "remediation",
      "references", "screenshots", "discovered_at", "cwe_id"
    }
  ],
  "attack_paths": [
    {
      "name", "description", "start_point", "end_point",
      "steps": [{"order", "description", "tool_used", "target", "result"}]
    }
  ],
  "technical_appendix": [{"command", "output", "timestamp"}],
  "compliance_notes": "...",
  "generated_at", "report_id",
  "css": "..."  # html_exporter注入的CSS
}

【模板1：templates/default.html】

编写一个完整的、专业的HTML报告模板：
- 使用Jinja2语法 {{ variable }} 和 {% for %} {% if %}
- 响应式布局，max-width: 1200px居中
- 封面页：大标题、公司名、日期、保密声明
- 执行摘要：用卡片式布局展示
- 风险摘要：用彩色徽章统计各severity数量
- 详细发现：每个发现用折叠面板（或独立区块），包含severity颜色条
- 攻击路径：用有序列表展示步骤
- 技术附录：用代码块展示命令输出
- 页脚：页码和生成时间

CSS内联在<style>标签中（使用{{ css }}变量），确保HTML文件独立可查看。
Severity颜色：CRITICAL=#dc3545, HIGH=#fd7e14, MEDIUM=#ffc107, LOW=#17a2b8, INFO=#6c757d

【模板2：templates/default.md】

编写GitHub Flavored Markdown格式模板：
- # 标题
- ## 章节
- 用表格展示风险统计
- 每个发现用 ### 子标题
- 代码块展示命令输出（```bash 和 ```）
- 用emoji标识severity：🔴严重 🟠高危 🟡中危 🔵低危 ⚪信息

【模板3：templates/pentest_full.html】

在default.html基础上增强的完整版：
- 更精美的封面页（带公司Logo占位）
- 目录导航（TOC锚点链接）
- 风险矩阵图表（用CSS Grid实现2D矩阵）
- CVSS评分可视化（进度条）
- 攻击路径Mermaid图表（如果attack_path.to_mermaid()有值）
- 分页打印控制（page-break-before）

输出：3个模板的完整内容，用"=== templates/default.html ==="等分隔。
注意：模板是文本文件（不是Python代码），直接输出模板内容即可。
```

**期望输出**：3个模板文件，各150-250行

---

## Phase 2 返回检查点

**两个Agent完成后，把代码复制回主控。主控审查：**
1. ScreenshotCatcher的capture()返回值（文件路径）是否与Finding.screenshots字段匹配
2. IncrementalTracker.flush()是否正确调用了ReportGenerator.add_finding()
3. 模板的Jinja2变量名是否与PentestReport.to_dict()的键名一致

---

## Phase 3：启动（1个Agent，依赖全部前置输出）

### Agent-18：__init__.py + M0侵入层代码

**系统提示词：**
```
你是PentestAgent M3模块的系统集成开发专家。编写__init__.py和M0侵入层代码。

【Part 1：__init__.py】

实现M3模块入口：
1. 开关控制：CPA_M3_REPORTER环境变量（默认true）
2. 初始化函数init_m3()：创建TemplateEngine、ReportGenerator、ScreenshotCatcher、IncrementalTracker
3. 公共API导出：get_report_generator(), get_screenshot_catcher(), get_incremental_tracker()
4. is_m3_enabled() -> bool

导入：
from .template_engine import TemplateEngine
from .report_generator import ReportGenerator
from .screenshot_catcher import ScreenshotCatcher
from .incremental_tracker import IncrementalTracker

【Part 2：M0侵入层代码】

提供以下HOOK点（用 === CPA M3 HOOK BEGIN/END === 包裹）：

侵入点1：pentestagent/__main__.py — main()函数
```python
# === CPA M3 HOOK BEGIN ===
if os.getenv("CPA_M3_REPORTER", "true").lower() == "true":
    try:
        from cpa_modules.m3_reporter import init_m3
        import asyncio
        asyncio.run(init_m3())
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"M3模块初始化失败: {e}")
# === CPA M3 HOOK END ===
```

侵入点2：pentestagent/interface/commands.py — 命令注册
注册/report系列命令：
```python
# === CPA M3 HOOK BEGIN ===
if os.getenv("CPA_M3_REPORTER", "true").lower() == "true":
    try:
        from cpa_modules.m3_reporter import get_report_generator
        # 注册命令：
        # /report new <title>              — 创建新报告
        # /report status                   — 查看当前报告状态
        # /report add <title> <severity>   — 添加发现
        # /report screenshot <url>         — 截图并附加到报告
        # /report export [html|md|pdf|all] — 导出报告
        # /report preview                  — 查看报告预览
        # /report auto_save                — 手动触发自动保存
    except Exception:
        pass
# === CPA M3 HOOK END ===
```

侵入点3：pentestagent/config/settings.py — Settings类
```python
# === CPA M3 HOOK BEGIN ===
cpa_m3_reporter: bool = field(default_factory=lambda: os.getenv("CPA_M3_REPORTER", "true").lower() == "true")
cpa_m3_output_dir: str = field(default_factory=lambda: os.getenv("CPA_M3_OUTPUT_DIR", "./reports"))
cpa_m3_company_name: str = field(default_factory=lambda: os.getenv("CPA_M3_COMPANY_NAME", ""))
# === CPA M3 HOOK END ===
```

侵入点4：pentestagent/agents/ — Agent执行后钩子
在Agent完成任务后自动追加到报告：
```python
# === CPA M3 HOOK BEGIN ===
# 在Agent执行完一个工具命令后，自动调用：
# report_generator.add_command_output(command, output, target)
# 在Agent发现漏洞后，自动调用：
# report_generator.add_finding(title, severity, description, target, ...)
# === CPA M3 HOOK END ===
```

输出：__init__.py完整代码 + 4个侵入点代码和位置说明。
```

**期望输出**：`__init__.py`（80-120行）+ 4个M0侵入点

---

## 最终集成清单

**Agent-18完成后，全部到齐。主控做最终集成审阅：**

1. **文件完整性**：9个文件（7个py + 2个模板目录下的文件）
2. **模板变量一致性**：Jinja2模板中的变量名 vs to_dict()的键名
3. **导出链路**：export_html → render → 写入文件，端到端通路
4. **增量链路**：Agent执行 → queue_finding → flush → add_finding → auto_save
5. **M0侵入量**：4个HOOK点，预计<15行
6. **Playwright延迟加载**：pdf_exporter和screenshot_catcher的延迟导入

**审阅通过后，M3模块开发完成。**
