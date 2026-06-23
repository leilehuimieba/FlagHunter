"""GSSC context assembly pipeline for agent system prompts.

Gather → Select → Structure → Compress: collects knowledge from notes,
strategy memory, project memory, and RAG, filters by current pentest phase,
formats into prompt-friendly sections, and truncates to a token budget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..base_agent import BaseAgent

_PHASE_PRIORITIES: dict[str, list[str]] = {
    "recon": ["finding", "task"],
    "vuln": ["vulnerability", "finding"],
    "exploit": ["credential", "vulnerability"],
    "post": ["credential", "artifact"],
}
_DEFAULT_PRIORITIES = ["credential", "vulnerability", "finding", "artifact", "task"]
_MAX_CHARS = 1200
_MAX_ITEM_CHARS = 200
_SCAN_TOOLS = {"nmap", "fscan", "subfinder", "httpx", "whatweb"}
_VULN_TOOLS = {"nuclei", "nikto", "sqlmap", "afrog", "waf"}
_EXPLOIT_TOOLS = {"hydra", "hashcat", "msf", "dirscan", "browser"}


class ContextAssembler:
    """Gather → Select → Structure → Compress pipeline for LLM context."""

    def __init__(self, agent: BaseAgent):
        self._agent = agent

    def assemble(self, phase: str = "") -> str:
        """Run the full pipeline and return a prompt-ready context string."""
        sources = self._gather()
        selected = self._select(sources, phase or self._detect_phase())
        structured = self._structure(selected)
        return self._compress(structured)

    def _gather(self) -> dict[str, list[dict[str, Any]]]:
        """Collect all available context sources."""
        sources: dict[str, list[dict[str, Any]]] = {}
        agent = self._agent

        # 1. Notes — skip; already handled by pa_agent.get_system_prompt()
        sources["notes"] = []

        # 2. Project memory
        try:
            from flaghunter.knowledge.project_memory import ProjectMemory
            pm = ProjectMemory()
            target = getattr(agent, "target", "") or ""
            pm_ctx = pm.get_context_for_prompt(target=target, phase=self._detect_phase())
            if pm_ctx:
                sources["project"] = [{"key": "project_memory", "content": pm_ctx, "category": "info", "confidence": "high"}]
            else:
                sources["project"] = []
        except Exception:
            sources["project"] = []

        # 3. Harness session context
        sources["session"] = []
        session_context = self._build_session_context_summary()
        if session_context:
            sources["session"] = [
                {
                    "key": "session_context",
                    "content": session_context,
                    "category": "task",
                    "confidence": "high",
                }
            ]

        # 4. RAG (only if engine is available)
        sources["rag"] = []
        rag_engine = getattr(agent, "rag_engine", None)
        if rag_engine and agent.conversation_history:
            try:
                last_msg = agent.conversation_history[-1].content
                if isinstance(last_msg, list):
                    last_msg = " ".join(
                        str(p.get("text", "")) for p in last_msg if isinstance(p, dict)
                    )
                if last_msg:
                    rag_results = rag_engine.search(last_msg)
                    if rag_results:
                        sources["rag"] = [
                            {"key": f"rag_{i}", "content": r, "category": "info", "confidence": "medium"}
                            for i, r in enumerate(rag_results)
                        ]
            except Exception:
                pass

        return sources

    def _build_session_context_summary(self) -> str:
        run_id = str(getattr(self._agent, "run_id", "") or "").strip()
        project_root = getattr(self._agent, "project_root", None)
        if not run_id or project_root is None:
            return ""
        try:
            from pathlib import Path
            from .session_context import SessionContextView

            root = Path(project_root)
            context = SessionContextView(
                ledger_root=root / "loot" / "session_ledgers",
                artifact_root=root / "loot" / "artifact_registry",
                checkpoint_root=root / "loot" / "checkpoints",
            ).build_run_context(run_id, event_limit=5, artifact_limit=5)
        except Exception:
            return ""

        recent_event_types = [
            str(item.get("type") or "").strip()
            for item in list(context.get("recentEvents") or [])
            if str(item.get("type") or "").strip()
        ]
        resume_context = (
            context.get("resumeContext")
            if isinstance(context.get("resumeContext"), dict)
            else None
        )
        resume_ingress = (
            context.get("resumeIngress")
            if isinstance(context.get("resumeIngress"), dict)
            else None
        )
        resume_summary = (
            str(resume_context.get("summary") or "").strip()
            if resume_context
            else ""
        )
        artifact_titles = [
            str(item.get("title") or "").strip()
            for item in list(context.get("artifacts") or [])
            if str(item.get("title") or "").strip()
        ]
        local_challenge_summary = self._build_local_challenge_summary(
            list(context.get("artifacts") or [])
        )
        latest_checkpoint = (
            context.get("latestCheckpoint")
            if isinstance(context.get("latestCheckpoint"), dict)
            else None
        )
        resume_run_id = (
            str(resume_ingress.get("runId") or "").strip()
            if resume_ingress
            else ""
        )
        resume_checkpoint_id = (
            str(resume_ingress.get("checkpointId") or "").strip()
            if resume_ingress
            else ""
        )
        if resume_summary:
            lineage_parts: list[str] = []
            if resume_run_id:
                lineage_parts.append(f"resumed_from_run={resume_run_id}")
            if resume_checkpoint_id:
                lineage_parts.append(f"resumed_from_checkpoint={resume_checkpoint_id}")
            if local_challenge_summary:
                lineage_parts.append(local_challenge_summary)
            if lineage_parts:
                return "; ".join(lineage_parts) + "; " + resume_summary
            return resume_summary
        if not recent_event_types and not artifact_titles and not latest_checkpoint:
            return ""

        parts = [f"run_id={run_id}"]
        if resume_run_id:
            parts.append("resumed_from_run=" + resume_run_id)
        if resume_checkpoint_id:
            parts.append("resumed_from_checkpoint=" + resume_checkpoint_id)
        if latest_checkpoint:
            label = str(latest_checkpoint.get("label") or "").strip()
            stop_reason = str(latest_checkpoint.get("stopReason") or "").strip()
            verified_flags = [
                str(item).strip()
                for item in list(latest_checkpoint.get("verifiedFlags") or [])
                if str(item).strip()
            ]
            if label:
                parts.append("latest_checkpoint=" + label)
            if stop_reason:
                parts.append("stop_reason=" + stop_reason)
            if verified_flags:
                parts.append("verified_flags=" + ", ".join(verified_flags))
        if recent_event_types:
            parts.append("recent_events=" + ", ".join(recent_event_types))
        if artifact_titles:
            parts.append("artifacts=" + ", ".join(artifact_titles))
        if local_challenge_summary:
            parts.append(local_challenge_summary)
        return "; ".join(parts)

    def _build_local_challenge_summary(self, artifacts: list[dict[str, Any]]) -> str:
        summary_artifact = None
        for item in reversed(list(artifacts or [])):
            if str(item.get("kind") or "").strip() == "local_challenge_root_summary":
                summary_artifact = item
                break
        if not isinstance(summary_artifact, dict):
            return ""
        metadata = (
            summary_artifact.get("metadata")
            if isinstance(summary_artifact.get("metadata"), dict)
            else {}
        )
        root_name = str(metadata.get("root_name") or "").strip()
        detected_stack = [
            str(item).strip()
            for item in list(metadata.get("detected_stack") or [])
            if str(item).strip()
        ]
        key_files = [
            str(item).strip()
            for item in list(metadata.get("key_files") or [])
            if str(item).strip()
        ]
        has_compose = bool(metadata.get("has_compose"))

        parts: list[str] = []
        if root_name:
            parts.append("local_root=" + root_name)
        if detected_stack:
            parts.append("local_stack=" + ",".join(detected_stack))
        if key_files:
            parts.append("local_key_files=" + ", ".join(key_files[:5]))
        if has_compose:
            parts.append("local_has_compose=true")
        return "; ".join(parts)

    def _select(self, sources: dict[str, list[dict[str, Any]]], phase: str) -> list[dict[str, Any]]:
        """Filter context items by current pentest phase."""
        priorities = _PHASE_PRIORITIES.get(phase, _DEFAULT_PRIORITIES)
        selected: list[dict[str, Any]] = []

        for source_name, items in sources.items():
            for item in items:
                category = str(item.get("category", "")).lower()
                confidence = str(item.get("confidence", "medium")).lower()
                if category in priorities and confidence in ("high", "medium"):
                    selected.append(item)

        # Sort: prioritized categories first, then by confidence
        def _sort_key(item: dict[str, Any]) -> tuple[int, int]:
            cat = str(item.get("category", "")).lower()
            prio = priorities.index(cat) if cat in priorities else 99
            conf = 0 if str(item.get("confidence", "")).lower() == "high" else 1
            return (prio, conf)

        selected.sort(key=_sort_key)
        return selected

    def _structure(self, items: list[dict[str, Any]]) -> str:
        """Format selected items into prompt-friendly sections."""
        if not items:
            return ""

        grouped: dict[str, list[str]] = {}
        for item in items:
            cat = str(item.get("category", "info")).capitalize()
            content = str(item.get("content", ""))
            if len(content) > _MAX_ITEM_CHARS:
                content = content[:_MAX_ITEM_CHARS - 3] + "..."
            grouped.setdefault(cat, []).append(content)

        sections: list[str] = []
        priority_order = ["Credential", "Vulnerability", "Finding", "Artifact", "Task", "Info"]
        for cat in priority_order:
            entries = grouped.pop(cat, None)
            if entries:
                sections.append(f"[{cat}]\n" + "\n".join(f"- {e}" for e in entries))
        for cat, entries in sorted(grouped.items()):
            sections.append(f"[{cat}]\n" + "\n".join(f"- {e}" for e in entries))

        return "\n\n".join(sections)

    def _compress(self, text: str, max_chars: int = _MAX_CHARS) -> str:
        """Truncate to fit within the character budget, preserving structure."""
        if len(text) <= max_chars:
            return text
        lines = text.split("\n")
        result: list[str] = []
        budget = max_chars
        for line in lines:
            if len(line) + 1 <= budget:
                result.append(line)
                budget -= len(line) + 1
            else:
                truncated = line[: budget - 4] + "..."
                if len(truncated) > 4:
                    result.append(truncated)
                break
        return "\n".join(result)

    def _detect_phase(self) -> str:
        """Infer current pentest phase from recent tool calls in conversation."""
        agent = self._agent
        recent_tool_names: set[str] = set()
        for msg in reversed(agent.conversation_history[-10:]):
            if msg.tool_results:
                for tr in msg.tool_results:
                    recent_tool_names.add(getattr(tr, "tool_name", ""))

        if recent_tool_names & _EXPLOIT_TOOLS:
            return "exploit"
        if recent_tool_names & _VULN_TOOLS:
            return "vuln"
        if recent_tool_names & _SCAN_TOOLS:
            return "recon"
        return "recon"
