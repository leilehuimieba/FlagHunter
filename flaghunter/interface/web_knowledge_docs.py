"""Knowledge-document parsing / matching helpers split out of web_server (god-module 分簇).

Leaf, down-closed cluster: these 7 pure functions key/decode/tag/chunk a markdown
knowledge source and match it against conversation text. They call only each other +
stdlib (no back-call into web_server), so the split introduces no import cycle. web_server
re-imports every name here so existing ``web_server._build_knowledge_doc`` etc. references
keep resolving. The back-calling integrator ``_build_knowledge_usage`` stays in web_server.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _doc_key(source_path: str) -> str:
    token = base64.urlsafe_b64encode(source_path.encode("utf-8")).decode("ascii")
    return token.rstrip("=")


def _decode_doc_key(token: str) -> str | None:
    if not token:
        return None
    padding = "=" * (-len(token) % 4)
    try:
        return base64.urlsafe_b64decode((token + padding).encode("ascii")).decode("utf-8")
    except Exception:
        return None


def _knowledge_tags_for(relative_path: str) -> list[str]:
    lower = relative_path.replace("\\", "/").lower()
    tags: list[str] = []
    if "recon" in lower:
        tags.append("recon")
    if any(k in lower for k in ("reverse", "ghidra", "pwn")):
        tags.append("reverse")
    if any(k in lower for k in ("wal", "forensic")):
        tags.append("forensics")
    if any(k in lower for k in ("methodologies", "project", "retrospective", "guide")):
        tags.append("meta")
    if any(k in lower for k in ("sql", "xss", "ssrf", "web", "upload", "lfi", "cmd_injection", "php")):
        tags.append("web")
    if not tags:
        tags.append("misc")
    return list(dict.fromkeys(tags))


def _chunk_markdown(text: str, chunk_size: int = 1000) -> list[dict[str, Any]]:
    if not text:
        return []
    chunks = []
    for idx, start in enumerate(range(0, len(text), chunk_size), start=1):
        chunk_text = text[start:start + chunk_size].strip()
        if not chunk_text:
            continue
        chunks.append({
            "id": f"chunk_{idx:03d}",
            "idx": idx,
            "text": chunk_text,
            "hits": 0,
        })
    return chunks


def _build_knowledge_doc(project_root: Path, path: Path, include_content: bool = False) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        text = ""

    relative_path = str(path.relative_to(project_root)).replace("\\", "/")
    chunks = _chunk_markdown(text)
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    summary = paragraphs[0] if paragraphs else ""
    if len(summary) > 220:
        summary = summary[:217].rstrip() + "..."

    payload = {
        "id": path.stem,
        "docKey": _doc_key(relative_path),
        "title": path.stem.replace("_", " ").replace("-", " "),
        "sourcePath": relative_path,
        "type": "markdown",
        "chunkCount": len(chunks),
        "hitCount": 0,
        "tags": _knowledge_tags_for(relative_path),
        "lastHitAt": None,
        "updatedAt": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "summary": summary,
        "preview": text[:4000],
    }
    if include_content:
        payload["content"] = text
        payload["chunks"] = chunks
        payload["hitHistory"] = []
        payload["relatedRuns"] = []
        payload["citedBy"] = []
        payload["heatmap"] = [0] * 24
    return payload


def _doc_match_tokens(relative_path: str, stem: str, title: str) -> list[str]:
    normalized = relative_path.replace("\\", "/").lower()
    tokens = {
        normalized,
        Path(normalized).name,
        stem.lower(),
        title.lower(),
    }
    return [token for token in tokens if token]


def _message_mentions_doc(message: str, tokens: list[str]) -> bool:
    lower = str(message or "").lower()
    return any(token in lower for token in tokens)
