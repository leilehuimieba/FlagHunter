"""source_audit — white-box 源码漏洞 triage(纯 Python 模式匹配)。

让 code_audit profile 长出真白盒能力的第一块:遍历已摄取的源码目录,按语言
套一组**漏洞 sink 模式**(PHP unserialize/eval/system、Python pickle/eval/
subprocess shell=True、Node child_process/eval、Java readObject、通用硬编码
密钥 / SQL 拼接),报出 ``file:line + 规则 + CWE + 片段`` 作为"可疑点",供
planner 回灌到线上验证(doc 线 34 白盒环)。

**诚实边界**:这是基于模式的源码 *triage*,**不是 taint/dataflow 分析**
(那需 semgrep/CodeQL)——它指出"值得人/LLM 看的点",不证明可达可利用。
纯 Python,无外部二进制(与 recon 三件套一致)。结果仅供授权目标审计。

白盒源码审计在黑盒 ATT&CK/WSTG 编目之外(属 OWASP Code Review 域),故本
工具在 ``attack_taxonomy.TOOL_EXEMPT`` 显式声明豁免。

Layer note (I1): CAPABILITY 层(``tools/``),只 import stdlib;不 import agents。
``scan_source`` 抽成模块级纯函数,既供工具包装也供 profile 自动扫接线复用。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


# Directories never worth auditing (deps / VCS / build output).
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "__pycache__",
    ".venv", "venv", "dist", "build", ".idea", ".pytest_cache", "target",
}
_MAX_FILE_BYTES = 1_000_000  # skip files larger than ~1MB (likely data/minified)

# Extension → language label (also the scan allow-list).
_EXT_LANG: dict[str, str] = {
    ".php": "php", ".phtml": "php", ".php5": "php", ".inc": "php",
    ".py": "python",
    ".js": "javascript", ".ts": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".java": "java",
    ".rb": "ruby",
    ".go": "go",
}

# A rule = (name, compiled regex, languages or None=all, cwe, severity).
# Patterns intentionally conservative (clear sink tokens) to limit false positives.
_RULES: list[tuple[str, "re.Pattern[str]", set[str] | None, str, str]] = [
    # --- PHP -----------------------------------------------------------------
    ("php_unserialize", re.compile(r"\bunserialize\s*\("), {"php"}, "CWE-502", "high"),
    ("php_code_eval", re.compile(r"\b(eval|assert|create_function)\s*\("), {"php"}, "CWE-95", "high"),
    ("php_cmd_exec", re.compile(r"\b(system|exec|passthru|shell_exec|popen|proc_open)\s*\("), {"php"}, "CWE-78", "high"),
    ("php_dynamic_include", re.compile(r"\b(include|include_once|require|require_once)\s*\(?\s*\$"), {"php"}, "CWE-98", "high"),
    ("php_preg_e", re.compile(r"preg_replace\s*\(\s*['\"][^'\"]*/e"), {"php"}, "CWE-95", "high"),
    ("php_tainted_input", re.compile(r"\$_(GET|POST|REQUEST|COOKIE|FILES)\b"), {"php"}, "CWE-20", "info"),
    # --- Python --------------------------------------------------------------
    ("py_pickle_load", re.compile(r"\b(c?pickle|pickle)\s*\.\s*loads?\s*\("), {"python"}, "CWE-502", "high"),
    ("py_code_eval", re.compile(r"\b(eval|exec)\s*\("), {"python"}, "CWE-95", "high"),
    ("py_os_system", re.compile(r"\bos\s*\.\s*system\s*\("), {"python"}, "CWE-78", "high"),
    ("py_subprocess_shell", re.compile(r"shell\s*=\s*True"), {"python"}, "CWE-78", "high"),
    ("py_yaml_load", re.compile(r"\byaml\s*\.\s*load\s*\((?![^)]*Loader)"), {"python"}, "CWE-502", "medium"),
    ("py_marshal_load", re.compile(r"\bmarshal\s*\.\s*loads?\s*\("), {"python"}, "CWE-502", "medium"),
    ("py_ssti_render_string", re.compile(r"render_template_string\s*\("), {"python"}, "CWE-94", "medium"),
    # --- JavaScript / Node ---------------------------------------------------
    ("js_child_process", re.compile(r"child_process|\.exec\s*\(|execSync\s*\("), {"javascript"}, "CWE-78", "high"),
    ("js_code_eval", re.compile(r"\beval\s*\(|new\s+Function\s*\("), {"javascript"}, "CWE-95", "high"),
    ("js_dom_sink", re.compile(r"\.innerHTML\s*=|document\.write\s*\("), {"javascript"}, "CWE-79", "medium"),
    # --- Java ----------------------------------------------------------------
    ("java_runtime_exec", re.compile(r"Runtime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*exec|new\s+ProcessBuilder"), {"java"}, "CWE-78", "high"),
    ("java_deserialize", re.compile(r"ObjectInputStream|\.readObject\s*\("), {"java"}, "CWE-502", "high"),
    # --- Generic (all languages) --------------------------------------------
    ("hardcoded_secret", re.compile(r"(?i)(password|passwd|secret|api_?key|access_?token|private_?key)\s*[=:]\s*['\"][^'\"]{4,}['\"]"), None, "CWE-798", "medium"),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}"), None, "CWE-798", "high"),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), None, "CWE-798", "high"),
    ("sql_string_concat", re.compile(r"(?i)(select|insert|update|delete)\b.{0,80}(\.\s*\$|\"\s*\+|\bf\"|%\s*\()"), None, "CWE-89", "medium"),
]

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def _iter_source_files(root: Path, *, max_files: int) -> list[Path]:
    """Yield auditable source files under ``root`` (allow-listed extensions)."""
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if len(files) >= max_files:
            break
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in _EXT_LANG:
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        files.append(path)
    return files


def scan_source(
    path: str | Path,
    *,
    max_files: int = 400,
    max_findings: int = 200,
) -> dict[str, Any]:
    """Scan a source tree for vulnerability sink patterns (pure, no IO beyond reads).

    Returns a JSON-serializable report. Shared by the ``source_audit`` tool and
    the code_audit profile auto-scan wiring. Honest triage: pattern matches, not
    proof of reachability.
    """
    root = Path(str(path))
    if not root.exists():
        return {"path": str(root), "error": "path does not exist", "findings": []}
    if root.is_file():
        candidates = [root]
    else:
        candidates = _iter_source_files(root, max_files=max_files)

    findings: list[dict[str, Any]] = []
    scanned = 0
    truncated = False
    for file_path in candidates:
        lang = _EXT_LANG.get(file_path.suffix.lower())
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, ValueError):
            continue
        scanned += 1
        rel = str(file_path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if len(line) > 600:  # skip minified / data lines
                continue
            for name, pattern, langs, cwe, severity in _RULES:
                if langs is not None and lang not in langs:
                    continue
                if pattern.search(line):
                    findings.append(
                        {
                            "file": rel,
                            "line": lineno,
                            "rule": name,
                            "cwe": cwe,
                            "severity": severity,
                            "snippet": line.strip()[:200],
                        }
                    )
                    if len(findings) >= max_findings:
                        truncated = True
                        break
            if truncated:
                break
        if truncated:
            break

    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f["severity"], 9), f["file"], f["line"]))
    by_severity: dict[str, int] = {}
    for f in findings:
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1

    return {
        "path": str(root),
        "files_scanned": scanned,
        "findings": findings,
        "total_findings": len(findings),
        "by_severity": by_severity,
        "truncated": truncated,
    }


@register_tool(
    name="source_audit",
    description=(
        "White-box source-code vulnerability triage. Walks an ingested source tree "
        "and flags sink patterns (deserialization, code/command exec, SSTI, hardcoded "
        "secrets, SQL string-building) as file:line suspicious points to verify "
        "against the live target. Pattern triage, not taint analysis."
    ),
    schema=ToolSchema(
        properties={
            "path": {"type": "string", "description": "Source root directory (or single file) to audit"},
            "max_files": {"type": "integer", "description": "Max files to scan", "default": 400},
            "max_findings": {"type": "integer", "description": "Max findings to return", "default": 200},
        },
        required=["path"],
    ),
    category="audit",
)
async def source_audit(arguments: dict, runtime: "Runtime") -> str:
    path = arguments.get("path")
    if not path:
        return "Error: path is required"
    max_files = int(arguments.get("max_files", 400))
    max_findings = int(arguments.get("max_findings", 200))
    try:
        result = scan_source(path, max_files=max_files, max_findings=max_findings)
    except Exception as exc:  # never let an audit error crash the caller
        return json.dumps({"path": str(path), "error": str(exc), "findings": []}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


__all__ = ["source_audit", "scan_source"]
