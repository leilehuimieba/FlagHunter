"""Knowledge-base document HTTP route handlers for the web console.

Fourth slice extracted from ``web_server._make_handlers`` (the ~1270-line route
factory), following the memory / settings / attachment extractions. These six
handlers list, read, open, upload and reindex knowledge-base documents. They
close over ``project_root`` only; every helper they call except one is an
already-extracted leaf — ``_build_knowledge_doc``/``_decode_doc_key``
(``web_knowledge_docs``) and ``_now_iso`` (``web_leaf_utils``).

The single web_server-resident dependency, ``_build_knowledge_usage`` (a ~120-line
session-scanning aggregator with its own helper subtree), is **injected** as a
parameter rather than imported, so this sibling still imports nothing from
``web_server`` (no cycle) and the ~120-line helper stays put. The parameter keeps
the ``_build_knowledge_usage`` name so the handler bodies are byte-identical to
the originals.

``make_knowledge_handlers(project_root, _build_knowledge_usage)`` returns the same
``{route_name: handler}`` slice the factory produced inline; ``_make_handlers``
merges it via ``**knowledge_handlers`` so the route wiring in ``create_app`` is
unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from aiohttp import web

from .web_knowledge_docs import _build_knowledge_doc, _decode_doc_key
from .web_leaf_utils import _now_iso

# Same logger name as web_server so error-log records stay byte-identical after
# the extraction.
logger = logging.getLogger("flaghunter.interface.web_server")


def make_knowledge_handlers(project_root: Path, _build_knowledge_usage: Callable) -> dict[str, Callable]:
    async def get_knowledge(req: web.Request) -> web.Response:
        kb_dir = project_root / "knowledge"
        docs = []
        if kb_dir.exists():
            for f in kb_dir.rglob("*.md"):
                doc = _build_knowledge_doc(project_root, f, include_content=False)
                usage = _build_knowledge_usage(project_root, f)
                doc["hitCount"] = usage["hitCount"]
                doc["lastHitAt"] = usage["lastHitAt"]
                docs.append(doc)
        return web.json_response(docs)

    async def post_knowledge_reindex(req: web.Request) -> web.Response:
        from ..knowledge import RAGEngine

        knowledge_path = project_root / "knowledge"
        knowledge_path.mkdir(parents=True, exist_ok=True)
        rag = RAGEngine(knowledge_path=knowledge_path, use_local_embeddings=True)
        rag.index_documents(force=True)
        documents = list(getattr(rag, "documents", []) or [])
        doc_count = len({str(getattr(doc, "source", "")) for doc in documents if getattr(doc, "source", "")})
        chunk_count = len(documents)
        return web.json_response({
            "ok": True,
            "reindexed": True,
            "docCount": doc_count,
            "chunkCount": chunk_count,
            "updatedAt": _now_iso(),
        })

    async def get_knowledge_doc(req: web.Request) -> web.Response:
        doc_key = req.match_info["docKey"]
        source_path = _decode_doc_key(doc_key)
        if not source_path:
            return web.json_response({"error": "not found"}, status=404)
        path = (project_root / source_path).resolve()
        kb_root = (project_root / "knowledge").resolve()
        if not path.exists() or kb_root not in path.parents:
            return web.json_response({"error": "not found"}, status=404)
        doc = _build_knowledge_doc(project_root, path, include_content=True)
        usage = _build_knowledge_usage(project_root, path)
        doc.update(usage)
        return web.json_response(doc)

    async def open_knowledge_doc(req: web.Request) -> web.Response:
        doc_key = req.match_info["docKey"]
        source_path = _decode_doc_key(doc_key)
        if not source_path:
            return web.json_response({"error": "not found"}, status=404)
        path = (project_root / source_path).resolve()
        kb_root = (project_root / "knowledge").resolve()
        if not path.exists() or kb_root not in path.parents:
            return web.json_response({"error": "not found"}, status=404)
        if path.suffix.lower() not in {".md", ".txt", ".json"}:
            return web.json_response({"error": "unsupported file type"}, status=400)
        return web.json_response({
            "ok": True,
            "openUrl": f"/api/knowledge/{doc_key}/content",
            "sourcePath": str(path.relative_to(project_root)).replace("\\", "/"),
        })

    async def get_knowledge_doc_content(req: web.Request) -> web.Response:
        doc_key = req.match_info["docKey"]
        source_path = _decode_doc_key(doc_key)
        if not source_path:
            return web.json_response({"error": "not found"}, status=404)
        path = (project_root / source_path).resolve()
        kb_root = (project_root / "knowledge").resolve()
        if not path.exists() or kb_root not in path.parents:
            return web.json_response({"error": "not found"}, status=404)
        content_types = {
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".json": "application/json",
        }
        suffix = path.suffix.lower()
        if suffix not in content_types:
            return web.json_response({"error": "unsupported file type"}, status=400)
        return web.Response(body=path.read_bytes(), content_type=content_types[suffix])

    async def post_knowledge_document(req: web.Request) -> web.Response:
        from ..knowledge import RAGEngine

        knowledge_dir = project_root / "knowledge" / "sources"
        knowledge_dir.mkdir(parents=True, exist_ok=True)

        allowed_suffixes = {".md", ".txt", ".json"}
        saved_path: Path | None = None

        try:
            reader = await req.multipart()
            async for part in reader:
                if part.name != "file":
                    continue

                filename = Path(part.filename or "document.md").name or "document.md"
                suffix = Path(filename).suffix.lower()
                if suffix not in allowed_suffixes:
                    return web.json_response({"ok": False, "error": "unsupported file type"}, status=400)

                dest = knowledge_dir / filename
                stem, final_suffix = dest.stem, dest.suffix
                counter = 1
                while dest.exists():
                    dest = knowledge_dir / f"{stem}_{counter}{final_suffix}"
                    counter += 1

                with dest.open("wb") as fh:
                    while True:
                        chunk = await part.read_chunk(65536)
                        if not chunk:
                            break
                        fh.write(chunk)

                saved_path = dest
                break
        except Exception as exc:
            logger.exception("post_knowledge_document error: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

        if saved_path is None:
            return web.json_response({"ok": False, "error": "file required"}, status=400)

        rag = RAGEngine(knowledge_path=project_root / "knowledge", use_local_embeddings=True)
        rag.index_documents(force=True)
        documents = list(getattr(rag, "documents", []) or [])
        doc_count = len({str(getattr(doc, "source", "")) for doc in documents if getattr(doc, "source", "")})
        chunk_count = len(documents)

        document = _build_knowledge_doc(project_root, saved_path, include_content=False)
        document["chunkCount"] = sum(1 for doc in documents if str(getattr(doc, "source", "")) == str(saved_path))

        return web.json_response({
            "ok": True,
            "saved": True,
            "document": document,
            "reindexed": True,
            "docCount": doc_count,
            "chunkCount": chunk_count,
            "updatedAt": _now_iso(),
        })

    return {
        "get_knowledge": get_knowledge,
        "post_knowledge_reindex": post_knowledge_reindex,
        "get_knowledge_doc": get_knowledge_doc,
        "open_knowledge_doc": open_knowledge_doc,
        "get_knowledge_doc_content": get_knowledge_doc_content,
        "post_knowledge_document": post_knowledge_document,
    }
