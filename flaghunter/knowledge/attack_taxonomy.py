"""Technique taxonomy: ATT&CK + OWASP WSTG tagging for FlagHunter's arsenal.

This is the **single source of truth** mapping FlagHunter's capabilities
(tools + attack-chain strategies) onto industry technique frameworks:

  * **MITRE ATT&CK** (``T####`` / ``T####.###``) — for tools, which are *actions*
    (recon, scanning, exploitation, execution).
  * **OWASP WSTG v4.2** (``WSTG-XXXX-##``) — for web attack-chain strategies,
    which map cleanly onto the Web Security Testing Guide checklist.

Before this module, coverage against a standard framework was aspirational
(docs only): neither :class:`~flaghunter.tools.registry.Tool` nor
:class:`~flaghunter.agents.pa_agent.strategy_registry.StrategyDefinition`
carried a technique field, so no coverage matrix or gap analysis was possible.

**Layering (I1):** this module lives in the CAPABILITY layer and imports nothing
above it — it holds pure data plus helpers that operate on objects passed in by
the caller. The cross-layer aggregator that reads *both* tools and strategies
lives in :mod:`flaghunter.agents.attack_coverage` (ORCHESTRATION), because
CAPABILITY must not import ORCHESTRATION (the strategy registry).

**Maintenance contract:** every offensive capability must appear here (enforced
by ``tests/unit/knowledge/test_attack_taxonomy.py``). Capabilities outside the
ATT&CK/WSTG scope (internal plumbing, CTF reverse-engineering / crypto solvers,
file forensics) are listed in the ``*_EXEMPT`` sets — an explicit "no technique"
declaration, not an oversight.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# --- ID format guards -------------------------------------------------------
_ATTACK_ID_RE = re.compile(r"^T\d{4}(\.\d{3})?$")
_WSTG_ID_RE = re.compile(r"^WSTG-[A-Z]{4}-\d{2}$")


def is_valid_technique_id(technique_id: str) -> bool:
    """True if ``technique_id`` is a well-formed ATT&CK or WSTG identifier."""
    return bool(_ATTACK_ID_RE.match(technique_id) or _WSTG_ID_RE.match(technique_id))


def framework_of(technique_id: str) -> str:
    """Return the framework bucket ("ATT&CK" / "WSTG") for an ID."""
    if _ATTACK_ID_RE.match(technique_id):
        return "ATT&CK"
    if _WSTG_ID_RE.match(technique_id):
        return "WSTG"
    return "unknown"


# --- Technique catalog: every ID used below must have a label here -----------
# (ATT&CK ``tactic`` / WSTG ``category`` is the coarse coverage bucket.)
TECHNIQUE_CATALOG: dict[str, dict[str, str]] = {
    # ATT&CK — Discovery
    "T1046": {"framework": "ATT&CK", "tactic": "Discovery", "name": "Network Service Discovery"},
    # ATT&CK — Reconnaissance (PRE)
    "T1595": {"framework": "ATT&CK", "tactic": "Reconnaissance", "name": "Active Scanning"},
    "T1595.002": {"framework": "ATT&CK", "tactic": "Reconnaissance", "name": "Active Scanning: Vulnerability Scanning"},
    "T1595.003": {"framework": "ATT&CK", "tactic": "Reconnaissance", "name": "Active Scanning: Wordlist Scanning"},
    "T1590": {"framework": "ATT&CK", "tactic": "Reconnaissance", "name": "Gather Victim Network Information"},
    "T1590.002": {"framework": "ATT&CK", "tactic": "Reconnaissance", "name": "Gather Victim Network Information: DNS"},
    "T1592": {"framework": "ATT&CK", "tactic": "Reconnaissance", "name": "Gather Victim Host Information"},
    "T1593": {"framework": "ATT&CK", "tactic": "Reconnaissance", "name": "Search Open Websites/Domains"},
    # ATT&CK — Initial Access / Execution
    "T1190": {"framework": "ATT&CK", "tactic": "Initial Access", "name": "Exploit Public-Facing Application"},
    "T1133": {"framework": "ATT&CK", "tactic": "Initial Access", "name": "External Remote Services"},
    "T1078": {"framework": "ATT&CK", "tactic": "Initial Access", "name": "Valid Accounts"},
    "T1203": {"framework": "ATT&CK", "tactic": "Execution", "name": "Exploitation for Client Execution"},
    "T1059": {"framework": "ATT&CK", "tactic": "Execution", "name": "Command and Scripting Interpreter"},
    "T1071.001": {"framework": "ATT&CK", "tactic": "Command and Control", "name": "Application Layer Protocol: Web Protocols"},
    # OWASP WSTG v4.2 — Input Validation
    "WSTG-INPV-01": {"framework": "WSTG", "category": "Input Validation", "name": "Reflected Cross Site Scripting"},
    "WSTG-INPV-02": {"framework": "WSTG", "category": "Input Validation", "name": "Stored Cross Site Scripting"},
    "WSTG-INPV-05": {"framework": "WSTG", "category": "Input Validation", "name": "SQL Injection"},
    "WSTG-INPV-07": {"framework": "WSTG", "category": "Input Validation", "name": "XML Injection"},
    "WSTG-INPV-11": {"framework": "WSTG", "category": "Input Validation", "name": "Code Injection"},
    "WSTG-INPV-12": {"framework": "WSTG", "category": "Input Validation", "name": "Command Injection"},
    "WSTG-INPV-18": {"framework": "WSTG", "category": "Input Validation", "name": "Server-side Template Injection"},
    "WSTG-INPV-19": {"framework": "WSTG", "category": "Input Validation", "name": "Server-Side Request Forgery"},
    # OWASP WSTG v4.2 — Configuration, Authorization, Session, Business Logic, API
    "WSTG-CONF-04": {"framework": "WSTG", "category": "Configuration", "name": "Review Old Backup and Unreferenced Files"},
    "WSTG-ATHZ-01": {"framework": "WSTG", "category": "Authorization", "name": "Directory Traversal / File Include"},
    "WSTG-ATHZ-04": {"framework": "WSTG", "category": "Authorization", "name": "Insecure Direct Object References"},
    "WSTG-CLNT-04": {"framework": "WSTG", "category": "Client-side", "name": "Client-side URL Redirect"},
    "WSTG-SESS-10": {"framework": "WSTG", "category": "Session Management", "name": "Testing JSON Web Tokens"},
    "WSTG-BUSL-01": {"framework": "WSTG", "category": "Business Logic", "name": "Business Logic Data Validation"},
    "WSTG-BUSL-07": {"framework": "WSTG", "category": "Business Logic", "name": "Defenses Against Application Misuse"},
    "WSTG-APIT-01": {"framework": "WSTG", "category": "API", "name": "GraphQL Testing"},
}


# --- Tool → ATT&CK ----------------------------------------------------------
# Tools are actions; ATT&CK is the right framework. Internal plumbing and
# CTF reverse-engineering / crypto solvers have no clean ATT&CK technique and
# are declared in TOOL_EXEMPT instead of force-fitted.
TOOL_TECHNIQUES: dict[str, list[str]] = {
    # Reconnaissance
    "nmap": ["T1046", "T1595.002"],
    "fscan": ["T1046", "T1595.002"],
    "subfinder": ["T1590.002"],
    "httpx_probe": ["T1595", "T1592"],
    "katana": ["T1595"],
    "gau": ["T1593"],
    "dirscan": ["T1595.003"],
    "gf": ["T1595.003"],
    "recon_bundle": ["T1595", "T1590"],
    "waf": ["T1595.002"],
    "web_search": ["T1593"],
    # HTTP / browser interaction primitives
    "http_request": ["T1071.001"],
    "browser": ["T1071.001"],
    "opencli_browser": ["T1071.001"],
    "login_flow": ["T1078"],
    # Vulnerability scanning / exploitation
    "nuclei": ["T1595.002"],
    "afrog": ["T1595.002"],
    "sqlmap": ["T1190"],
    "dalfox": ["T1190"],
    "msf": ["T1190", "T1203", "T1059"],
    "pwn": ["T1203"],
    "terminal": ["T1059"],
}

# Tools intentionally outside ATT&CK scope (internal plumbing, RE/crypto, etc.).
TOOL_EXEMPT: frozenset[str] = frozenset(
    {
        "binary",          # CTF binary triage (RE)
        "radare2",         # CTF reverse engineering
        "angr_solve",      # CTF symbolic execution
        "crypto_solve",    # CTF crypto
        "vision",          # image/screenshot analysis (support)
        "knowledge_search",  # internal RAG
        "shadowgraph",     # internal knowledge graph
        "notes",           # internal findings store
        "tool_search",     # meta
        "delegate_task",   # orchestration glue
        "generate_plan",   # planning
        "finish",          # workflow control
        "llm_payload_gen", # red-team payload factory for guardrail eval (generator, not a network action)
        "guardrail_probe", # red-team runner that probes a guardrail endpoint (eval harness, not a network action)
    }
)


# --- Strategy kind → WSTG (+ ATT&CK where apt) ------------------------------
STRATEGY_TECHNIQUES: dict[str, list[str]] = {
    "auth_form_sqli": ["WSTG-INPV-05", "T1190"],
    "generic_param_sqli": ["WSTG-INPV-05", "T1190"],
    "generic_param_cmdi": ["WSTG-INPV-12", "T1190"],
    "generic_param_ssrf": ["WSTG-INPV-19", "T1190"],
    "reflected_xss": ["WSTG-INPV-01", "T1059"],
    "xss_admin_bot_sid": ["WSTG-INPV-02", "T1190"],
    "unicode_numeric_form_bypass": ["WSTG-BUSL-01"],
    "contact_report_chain": ["WSTG-BUSL-07"],
    "backup_source_leak": ["WSTG-CONF-04"],
    "php_unserialize_magic_method": ["WSTG-INPV-11", "T1190"],
    "insecure_deserialization": ["WSTG-INPV-11", "T1190"],
    "file_read_endpoint": ["WSTG-ATHZ-01", "T1190"],
    "hash_guarded_file_read": ["WSTG-ATHZ-01", "T1190"],
    "hash_reconstruction_attack": ["WSTG-ATHZ-01"],
    "ssti_via_render_parameter": ["WSTG-INPV-18", "T1190"],
    "tornado_ssti": ["WSTG-INPV-18", "T1190"],
    "ssti_probe": ["WSTG-INPV-18"],
    "ssti_identify": ["WSTG-INPV-18"],
    "ssti_exploit": ["WSTG-INPV-18", "T1190"],
    "jwt_manipulation": ["WSTG-SESS-10"],
    "graphql_introspection": ["WSTG-APIT-01"],
    "nosql_injection": ["WSTG-INPV-05", "T1190"],
    "xxe_injection": ["WSTG-INPV-07", "T1190"],
    "idor_sequential": ["WSTG-ATHZ-04", "T1190"],
    "open_redirect": ["WSTG-CLNT-04"],
}

# Strategy kinds intentionally without a technique tag (meta / navigation /
# forensics that don't map onto a single WSTG/ATT&CK technique).
STRATEGY_EXEMPT: frozenset[str] = frozenset(
    {
        "llm_driven_exploration",  # LLM fallback (the "*" catch-all)
        "hint_chain_followup",     # hint-file navigation, not a vuln class
        "artifact_forensics",      # offline file forensics (CTF misc)
    }
)


# --- Backfill helpers (operate on caller-supplied objects; no upward import) -
def technique_ids_for_tool(tool_name: str) -> list[str]:
    """Canonical technique IDs for a tool name (empty if exempt/unknown)."""
    return list(TOOL_TECHNIQUES.get(tool_name, []))


def technique_ids_for_strategy(kind: str) -> list[str]:
    """Canonical technique IDs for a strategy kind (empty if exempt/unknown)."""
    return list(STRATEGY_TECHNIQUES.get(kind, []))


def tag_tools(tools: Iterable[Any]) -> None:
    """Backfill ``tool.technique_ids`` from :data:`TOOL_TECHNIQUES`.

    Idempotent and non-destructive: a tool that already declares its own
    ``technique_ids`` (inline via ``register_tool``) is left untouched, so an
    inline declaration always wins over the central map.
    """
    for tool in tools:
        if getattr(tool, "technique_ids", None):
            continue
        ids = TOOL_TECHNIQUES.get(getattr(tool, "name", ""))
        if ids:
            tool.technique_ids = list(ids)


def tag_strategies(strategies: Iterable[Any]) -> None:
    """Backfill ``strategy.technique_ids`` from :data:`STRATEGY_TECHNIQUES`."""
    for strategy in strategies:
        if getattr(strategy, "technique_ids", None):
            continue
        ids = STRATEGY_TECHNIQUES.get(getattr(strategy, "kind", ""))
        if ids:
            strategy.technique_ids = list(ids)


def label_for(technique_id: str) -> str:
    """Human label for an ID ("name (tactic/category)"), or the bare ID."""
    entry = TECHNIQUE_CATALOG.get(technique_id)
    if not entry:
        return technique_id
    bucket = entry.get("tactic") or entry.get("category") or ""
    return f"{entry['name']} ({bucket})" if bucket else entry["name"]


__all__ = [
    "TECHNIQUE_CATALOG",
    "TOOL_TECHNIQUES",
    "TOOL_EXEMPT",
    "STRATEGY_TECHNIQUES",
    "STRATEGY_EXEMPT",
    "is_valid_technique_id",
    "framework_of",
    "technique_ids_for_tool",
    "technique_ids_for_strategy",
    "tag_tools",
    "tag_strategies",
    "label_for",
]
