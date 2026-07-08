"""Strategy-memory HTTP route handlers for the web console.

Extracted verbatim from ``web_server._make_handlers`` (the ~1270-line route
factory) as the first, least-coupled slice: these handlers close over
``project_root`` only and up-call no ``web_server`` module state (no ``_tasks``/
``_settings_to_api``/``_build_*``/``_bus``), so they move out cleanly without a
``web_server`` import (no cycle) and without touching any monkeypatch surface.

``make_memory_handlers(project_root)`` mirrors the closure the factory used: it
returns the same ``{route_name: handler}`` slice that ``_make_handlers``
previously produced inline, and ``_make_handlers`` merges it into its dict so the
public route wiring in ``create_app`` is unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from aiohttp import web

# Same logger name as web_server so error-log records stay byte-identical after
# the extraction (these handlers only ever touch the logger on error paths).
logger = logging.getLogger("flaghunter.interface.web_server")


def make_memory_handlers(project_root: Path) -> dict[str, Callable]:
    def _get_mem_store():
        try:
            from flaghunter.agents.pa_agent.strategy_memory import StrategyMemoryStore
            return StrategyMemoryStore(project_root / "loot" / "strategy_memory.json")
        except Exception:
            return None

    async def get_memory(req: web.Request) -> web.Response:
        store = _get_mem_store()
        if store is None:
            return web.json_response([])
        params = req.rel_url.query
        status_filter = params.get("status") or None
        sort_by = params.get("sort_by", "recent")
        limit = int(params.get("limit", "200"))
        try:
            entries = await store.list_entries(
                limit=limit,
                manual_status=status_filter,
                sort_by=sort_by,
            )
            return web.json_response([e.to_dict() for e in entries])
        except Exception as exc:
            logger.exception("get_memory error: %s", exc)
            return web.json_response([])

    async def get_memory_stats(req: web.Request) -> web.Response:
        store = _get_mem_store()
        if store is None:
            return web.json_response({"total": 0, "active": 0, "muted": 0, "deprecated": 0, "audit_candidates": 0})
        try:
            all_entries = await store.list_entries(limit=10000)
            total = len(all_entries)
            active = sum(1 for e in all_entries if e.metadata.manual_status == "active")
            muted = sum(1 for e in all_entries if e.metadata.manual_status == "muted")
            deprecated = sum(1 for e in all_entries if e.metadata.manual_status == "deprecated")
            audit_candidates = sum(
                1 for e in all_entries
                if e.metadata.manual_status == "active"
                and e.metadata.applied_count >= 3
                and e.metadata.success_correlation < 0.3
            )
            return web.json_response({
                "total": total,
                "active": active,
                "muted": muted,
                "deprecated": deprecated,
                "audit_candidates": audit_candidates,
            })
        except Exception as exc:
            logger.exception("get_memory_stats error: %s", exc)
            return web.json_response({"total": 0, "active": 0, "muted": 0, "deprecated": 0, "audit_candidates": 0})

    async def get_memory_entry(req: web.Request) -> web.Response:
        entry_id = req.match_info.get("entryId", "")
        store = _get_mem_store()
        if store is None:
            return web.json_response(None)
        try:
            entry = await store.get_entry(entry_id)
            if entry is None:
                return web.Response(status=404, text="Not found")
            return web.json_response(entry.to_dict())
        except Exception as exc:
            logger.exception("get_memory_entry error: %s", exc)
            return web.Response(status=500, text=str(exc))

    async def mute_memory_entry(req: web.Request) -> web.Response:
        entry_id = req.match_info.get("entryId", "")
        store = _get_mem_store()
        if store is None:
            return web.json_response({"ok": False})
        try:
            entry = await store.mute_entry(entry_id)
            if entry is None:
                return web.Response(status=404, text="Not found")
            return web.json_response(entry.to_dict())
        except Exception as exc:
            logger.exception("mute_memory_entry error: %s", exc)
            return web.Response(status=500, text=str(exc))

    async def activate_memory_entry(req: web.Request) -> web.Response:
        entry_id = req.match_info.get("entryId", "")
        store = _get_mem_store()
        if store is None:
            return web.json_response({"ok": False})
        try:
            entry = await store.activate_entry(entry_id)
            if entry is None:
                return web.Response(status=404, text="Not found")
            return web.json_response(entry.to_dict())
        except Exception as exc:
            logger.exception("activate_memory_entry error: %s", exc)
            return web.Response(status=500, text=str(exc))

    async def delete_memory_entry(req: web.Request) -> web.Response:
        entry_id = req.match_info.get("entryId", "")
        store = _get_mem_store()
        if store is None:
            return web.json_response({"ok": False})
        try:
            ok = await store.delete_entry(entry_id)
            if not ok:
                return web.Response(status=404, text="Not found")
            return web.json_response({"ok": True, "id": entry_id})
        except Exception as exc:
            logger.exception("delete_memory_entry error: %s", exc)
            return web.Response(status=500, text=str(exc))

    async def get_memory_graph(req: web.Request) -> web.Response:
        """Return nodes+edges for force-directed graph visualization."""
        store = _get_mem_store()
        if store is None:
            return web.json_response({"nodes": [], "edges": []})
        params = req.rel_url.query
        status_filter = params.get("status") or None
        try:
            entries = await store.list_entries(limit=2000, manual_status=status_filter)
        except Exception:
            return web.json_response({"nodes": [], "edges": []})

        TYPE_COLORS: dict[str, str] = {
            "web": "#4fc3f7", "crypto": "#ffb74d", "reverse": "#4db6ac",
            "pwn": "#ef5350", "misc": "#ce93d8", "forensics": "#f06292",
        }

        nodes: list[dict] = []
        node_ids: set[str] = set()
        for e in entries:
            ntype = (e.fingerprint.detected_type or "misc").lower()
            nodes.append({
                "id": e.id,
                "type": ntype,
                "color": TYPE_COLORS.get(ntype, "#90a4ae"),
                "appliedCount": e.metadata.applied_count,
                "successCorrelation": e.metadata.success_correlation,
                "status": e.metadata.manual_status,
                "solved": e.solved,
                "techStack": e.fingerprint.tech_stack,
            })
            node_ids.add(e.id)

        # Build edges: group nodes by detected_type, then connect pairs
        # within each group that share hypothesis kinds. Cap edges per node
        # to keep the graph readable and the response size manageable.
        nodes_by_type: dict[str, list[int]] = {}
        for idx, e in enumerate(entries):
            ntype = (e.fingerprint.detected_type or "misc").lower()
            nodes_by_type.setdefault(ntype, []).append(idx)

        edges: list[dict] = []
        edge_seen: set[tuple] = set()
        edge_count_per_node: dict[str, int] = {}
        MAX_EDGES_PER_NODE = 12

        for indices in nodes_by_type.values():
            for i_idx, i in enumerate(indices):
                a = entries[i]
                a_kinds = set(a.winning_hypothesis_kinds or [])
                if not a_kinds:
                    continue
                for j in indices[i_idx + 1:]:
                    if edge_count_per_node.get(a.id, 0) >= MAX_EDGES_PER_NODE:
                        break
                    b = entries[j]
                    b_kinds = set(b.winning_hypothesis_kinds or [])
                    if not b_kinds:
                        continue
                    if edge_count_per_node.get(b.id, 0) >= MAX_EDGES_PER_NODE:
                        continue
                    key = tuple(sorted([a.id, b.id]))
                    if key in edge_seen:
                        continue
                    shared_kinds = a_kinds & b_kinds
                    if not shared_kinds:
                        continue
                    edges.append({
                        "source": a.id, "target": b.id,
                        "kind": "hypothesis", "weight": len(shared_kinds),
                    })
                    edge_seen.add(key)
                    edge_count_per_node[a.id] = edge_count_per_node.get(a.id, 0) + 1
                    edge_count_per_node[b.id] = edge_count_per_node.get(b.id, 0) + 1

        return web.json_response({"nodes": nodes, "edges": edges})

    return {
        "get_memory": get_memory,
        "get_memory_stats": get_memory_stats,
        "get_memory_entry": get_memory_entry,
        "mute_memory_entry": mute_memory_entry,
        "activate_memory_entry": activate_memory_entry,
        "delete_memory_entry": delete_memory_entry,
        "get_memory_graph": get_memory_graph,
    }
