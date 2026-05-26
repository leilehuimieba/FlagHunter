"""GF — pattern matching filter for security-relevant strings in HTTP responses, URLs, and text."""

import re

from ...runtime.runtime import Runtime
from ...tools.registry import ToolSchema, register_tool

# Built-in security-relevant patterns (lightweight reimplementation of common gf patterns)
_BUILTIN_PATTERNS = {
    "ssrf": re.compile(
        r"(?i)(url[=_]?|target[=_]?|image[=_]?|feed[=_]?|dest[=_]?|redirect[=_]?|callback[=_]?|proxy[=_]?|host[=_]?|site[=_]?|path[=_]?|next[=_]?|return[=_]?|continue[=_]?|to[=_]?|from[=_]?|ref[=_]?|referer[=_]?|origin[=_]?)=([^&\s]{3,500})"
    ),
    "sqli": re.compile(
        r"(?i)(id[=_]?|user[=_]?|username[=_]?|pass[=_]?|password[=_]?|page[=_]?|file[=_]?|search[=_]?|query[=_]?|q[=_]?|s[=_]?|keyword[=_]?|sort[=_]?|order[=_]?|by[=_]?|column[=_]?|field[=_]?|name[=_]?|email[=_]?|phone[=_]?|code[=_]?|token[=_]?|key[=_]?)=([^&\s]{1,300})"
    ),
    "rce": re.compile(
        r"(?i)(cmd[=_]?|command[=_]?|exec[=_]?|execute[=_]?|ping[=_]?|nslookup[=_]?|dig[=_]?|system[=_]?|shell[=_]?|run[=_]?|eval[=_]?|code[=_]?|call[=_]?|func[=_]?|function[=_]?|method[=_]?|action[=_]?|do[=_]?)=([^&\s]{1,300})"
    ),
    "lfi": re.compile(
        r"(?i)(file[=_]?|path[=_]?|page[=_]?|template[=_]?|view[=_]?|include[=_]?|require[=_]?|source[=_]?|load[=_]?|read[=_]?|open[=_]?|document[=_]?|folder[=_]?|dir[=_]?|directory[=_]?|loc[=_]?|location[=_]?|uri[=_]?)=([^&\s]{1,300})"
    ),
    "redirect": re.compile(
        r"(?i)(redirect[=_]?|return[=_]?|return_url[=_]?|returnurl[=_]?|next[=_]?|url[=_]?|to[=_]?|goto[=_]?|redir[=_]?|r[=_]?|link[=_]?|target[=_]?|dest[=_]?|destination[=_]?|continue[=_]?|forward[=_]?)=([^&\s]{3,500})"
    ),
    "aws-keys": re.compile(r"(AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AROA[0-9A-Z]{16})", re.IGNORECASE),
    "s3-buckets": re.compile(
        r"([a-z0-9][a-z0-9\-]{2,62}\.s3[\-a-z0-9]*\.amazonaws\.com|s3://[a-z0-9][a-z0-9\-]{2,62})"
    ),
    "base64": re.compile(r"([A-Za-z0-9+/]{40,}={0,2})"),
    "api-keys": re.compile(
        r"(?i)(api[_-]?key[\"\']?\s*[:=]\s*[\"\']?([a-z0-9_\-]{16,})|api[_-]?secret[\"\']?\s*[:=]\s*[\"\']?([a-z0-9_\-]{16,})|token[\"\']?\s*[:=]\s*[\"\']?([a-z0-9_\-]{16,})|authorization[:\s]+(bearer\s+[a-z0-9_\-\.]+))"
    ),
    "jwt": re.compile(r"(eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*)", re.IGNORECASE),
    "ip": re.compile(r"(\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b|\b[0-9a-fA-F:]{4,39}\b)"),
    "email": re.compile(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"),
    "interesting": re.compile(
        r"(?i)(admin|root|config|backup|\.git|\.env|\.htaccess|phpinfo|debug|test|dev|staging|internal|secret|private|confidential|flag\{|ctf\{|password|passwd|credential|key|token|session|cookie|auth)"
    ),
}


@register_tool(
    name="gf",
    description="Pattern-match security-relevant strings in text, URLs, or HTTP responses. Built-in patterns: ssrf, sqli, rce, lfi, redirect, aws-keys, s3-buckets, base64, api-keys, jwt, ip, email, interesting. Useful for quickly extracting attack surface from large outputs.",
    schema=ToolSchema(
        type="object",
        properties={
            "pattern": {"type": "string", "description": "Pattern name (ssrf, sqli, rce, lfi, redirect, aws-keys, s3-buckets, base64, api-keys, jwt, ip, email, interesting) or 'all'", "default": "all"},
            "text": {"type": "string", "description": "Text to search in (URL list, HTTP response, source code, etc.)"},
            "max_results": {"type": "integer", "description": "Maximum matches per pattern (default: 50)", "default": 50},
        },
        required=["text"],
    ),
    category="recon",
)
async def gf(arguments: dict, runtime: Runtime) -> str:
    pattern_name = arguments.get("pattern", "all").lower().strip()
    text = arguments.get("text", "")
    max_results = arguments.get("max_results", 50)

    if not text:
        return "Error: text is required"

    patterns_to_run = []
    if pattern_name == "all":
        patterns_to_run = list(_BUILTIN_PATTERNS.items())
    elif pattern_name in _BUILTIN_PATTERNS:
        patterns_to_run = [(pattern_name, _BUILTIN_PATTERNS[pattern_name])]
    else:
        return (
            f"Unknown pattern: '{pattern_name}'\n"
            f"Available patterns: {', '.join(_BUILTIN_PATTERNS.keys())}, all"
        )

    results = {}
    for name, regex in patterns_to_run:
        matches = []
        seen = set()
        for match in regex.finditer(text):
            m = match.group(0)
            if m not in seen:
                seen.add(m)
                matches.append(m)
            if len(matches) >= max_results:
                break
        if matches:
            results[name] = matches

    if not results:
        return f"GF: No matches found for pattern '{pattern_name}' in provided text."

    lines = [f"GF Pattern Match Results (pattern={pattern_name})", "=" * 40]
    for name, matches in sorted(results.items()):
        lines.append(f"\n[{name}] {len(matches)} matches:")
        for m in matches[:20]:
            display = m[:200] + "..." if len(m) > 200 else m
            lines.append(f"  - {display}")
        if len(matches) > 20:
            lines.append(f"  ... and {len(matches) - 20} more")

    return "\n".join(lines)
