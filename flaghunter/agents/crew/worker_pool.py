"""Worker pool for managing concurrent agent execution."""

import asyncio
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .models import AgentStatus, AgentWorker, WorkerCallback
from .swarm_bridge import on_worker_complete

if TYPE_CHECKING:
    from ...llm import LLM
    from ...runtime import Runtime
    from ...tools import Tool


class WorkerPool:
    """Manages concurrent execution of worker agents."""

    def __init__(
        self,
        llm: "LLM",
        tools: List["Tool"],
        runtime: "Runtime",
        target: str = "",
        rag_engine: Any = None,
        on_worker_event: Optional[WorkerCallback] = None,
    ):
        self.llm = llm
        self.tools = tools
        self.runtime = runtime
        self.target = target
        self.rag_engine = rag_engine
        self.on_worker_event = on_worker_event

        self._workers: Dict[str, AgentWorker] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._results: Dict[str, str] = {}
        self._next_id = 0
        self._lock = asyncio.Lock()

    _SKILL_TOOLS: dict[str, set[str]] = {
        "web": {
            "dirscan",
            "nuclei",
            "sqlmap",
            "browser",
            "opencli_browser",
            "notes",
            "finish",
            "afrog",
            "web_search",
            "waf",
            "login_flow",
        },
        "recon": {"nmap", "fscan", "subfinder", "notes", "finish"},
        "exploit": {"sqlmap", "afrog", "pwn", "msf", "notes", "finish"},
        "crypto": {"pwn", "notes", "finish"},
        "default": set(),
    }
    _ALWAYS_KEEP_TOOLS = {"notes", "finish", "terminal"}
    _WORKER_TYPE_PROMPTS: dict[str, str] = {
        "web": (
            "You are a specialized web worker. Focus on HTTP enumeration, "
            "content discovery, template-driven web validation, sessions, "
            "and injection testing. "
            "Run waf detect first to fingerprint any WAF, then use bypass_config "
            "to adapt dirscan/nuclei/sqlmap parameters accordingly. "
            "Use login_flow for authenticated testing before running scanners."
        ),
        "recon": (
            "You are a specialized recon worker. Focus on host discovery, "
            "port scanning, service identification, and subdomain enumeration."
        ),
        "exploit": (
            "You are a specialized exploit worker. Focus on validating and "
            "exploiting concrete vulnerabilities with minimal noise. "
            "Use sqlmap for SQL injection, afrog for vulnerability scanning, "
            "msf (Metasploit RPC) for module-based exploitation and session management. "
            "Prefer msf run action for service exploits; use msf exec to interact "
            "with established sessions."
        ),
        "crypto": (
            "You are a specialized crypto worker. Focus on encoded data, "
            "transform chains, cryptographic weaknesses, and pwn/crypto tasks."
        ),
    }

    def _emit(self, worker_id: str, event: str, data: Dict[str, Any]) -> None:
        """Emit event to callback if registered."""
        if self.on_worker_event:
            self.on_worker_event(worker_id, event, data)

    def _generate_id(self) -> str:
        """Generate unique worker ID."""
        worker_id = f"agent-{self._next_id}"
        self._next_id += 1
        return worker_id

    async def spawn(
        self,
        task: str,
        priority: int = 1,
        depends_on: Optional[List[str]] = None,
        worker_type: str = "default",
    ) -> str:
        """
        Spawn a new worker agent.

        Args:
            task: The task description for the agent
            priority: Higher priority runs first (for future use)
            depends_on: List of agent IDs that must complete first

        Returns:
            The worker ID
        """
        async with self._lock:
            worker_id = self._generate_id()
            normalized_worker_type = (
                worker_type
                if worker_type in self._SKILL_TOOLS
                else "default"
            )

            worker = AgentWorker(
                id=worker_id,
                task=task,
                worker_type=normalized_worker_type,
                priority=priority,
                depends_on=depends_on or [],
            )
            self._workers[worker_id] = worker

            # Emit spawn event for UI
            self._emit(
                worker_id,
                "spawn",
                {
                    "worker_type": worker.worker_type,
                    "task": task,
                },
            )

            # Start the agent task
            self._tasks[worker_id] = asyncio.create_task(self._run_worker(worker))

            return worker_id

    async def _run_worker(self, worker: AgentWorker) -> None:
        """Run a single worker agent."""
        from ..pa_agent import FlagHunterAgent

        # Wait for dependencies
        if worker.depends_on:
            await self._wait_for_dependencies(worker.depends_on)

        worker.status = AgentStatus.RUNNING
        worker.started_at = time.time()
        self._emit(worker.id, "status", {"status": "running"})

        # Create isolated runtime for this worker (prevents browser state conflicts)
        from ...runtime.runtime import LocalRuntime

        worker_runtime = LocalRuntime()
        await worker_runtime.start()

        from ...config.constants import AGENT_MAX_ITERATIONS

        # ── Worker skill-based tool filtering ────────────────────────────────
        _allowed = self._SKILL_TOOLS.get(worker.worker_type, set())
        worker_tools = (
            [t for t in self.tools if t.name in _allowed]
            if _allowed
            else list(self.tools)
        )
        for t in self.tools:
            if t.name in self._ALWAYS_KEEP_TOOLS and t not in worker_tools:
                worker_tools.append(t)
        # ── End tool filtering ────────────────────────────────────────────────

        agent = FlagHunterAgent(
            llm=self.llm,
            tools=worker_tools,
            runtime=worker_runtime,  # Use isolated runtime
            target=self.target,
            rag_engine=self.rag_engine,
            max_iterations=AGENT_MAX_ITERATIONS,
        )

        worker_prompt = self._WORKER_TYPE_PROMPTS.get(worker.worker_type)
        if worker_prompt:
            _base_get_system_prompt = agent.get_system_prompt
            agent.get_system_prompt = (
                lambda mode="agent", _base=_base_get_system_prompt, _extra=worker_prompt:
                _base(mode) + f"\n\nWorker specialization:\n{_extra}"
            )

        try:
            final_response = ""
            hit_max_iterations = False
            is_infeasible = False

            async for response in agent.agent_loop(worker.task):
                # Track tool calls
                if response.tool_calls:
                    for tc in response.tool_calls:
                        if tc.name not in worker.tools_used:
                            worker.tools_used.append(tc.name)
                            self._emit(worker.id, "tool", {"tool": tc.name})

                # Track tokens (avoid double counting)
                if response.usage:
                    total = response.usage.get("total_tokens", 0)
                    is_intermediate = response.metadata.get("intermediate", False)
                    has_tools = bool(response.tool_calls)

                    # Same logic as CLI to avoid double counting
                    should_count = False
                    if is_intermediate:
                        should_count = True
                        worker.last_msg_intermediate = True
                    elif has_tools:
                        if not getattr(worker, "last_msg_intermediate", False):
                            should_count = True
                        worker.last_msg_intermediate = False
                    else:
                        should_count = True
                        worker.last_msg_intermediate = False

                    if should_count and total > 0:
                        self._emit(worker.id, "tokens", {"tokens": total})

                # Capture final response (text without tool calls)
                if response.content and not response.tool_calls:
                    final_response = response.content

                # Check metadata flags
                if response.metadata:
                    if response.metadata.get("max_iterations_reached"):
                        hit_max_iterations = True
                    if response.metadata.get("replan_impossible"):
                        is_infeasible = True

            # Prioritize structured results from the plan over chatty summaries
            plan_summary = ""
            plan = getattr(worker_runtime, "plan", None)
            if plan and plan.steps:
                from ...tools.finish import StepStatus

                # Include ALL steps regardless of status - skips and failures are valuable context
                # Note: PlanStep stores failure/skip reasons in the 'result' field
                steps_with_info = [s for s in plan.steps if s.result]
                if steps_with_info:
                    summary_lines = []
                    for s in steps_with_info:
                        status_marker = {
                            StepStatus.COMPLETE: "✓",
                            StepStatus.SKIP: "⊘",
                            StepStatus.FAIL: "✗",
                        }.get(s.status, "·")
                        info = s.result or "No details"
                        summary_lines.append(f"{status_marker} {s.description}: {info}")
                    plan_summary = "\n".join(summary_lines)

            # Use plan summary if available, otherwise fallback to chat response
            worker.result = plan_summary or final_response or "No findings."

            worker.completed_at = time.time()
            self._results[worker.id] = worker.result

            if is_infeasible:
                worker.status = AgentStatus.FAILED
                self._emit(
                    worker.id,
                    "failed",
                    {
                        "summary": worker.result[:200],
                        "reason": "Task determined infeasible",
                    },
                )
                await on_worker_complete(
                    agent_id=worker.id,
                    task=worker.task,
                    target=self.target,
                    result=worker.result or "",
                    success=False,
                )
            elif hit_max_iterations:
                worker.status = AgentStatus.WARNING
                self._emit(
                    worker.id,
                    "warning",
                    {
                        "summary": worker.result[:200],
                        "reason": "Max iterations reached",
                    },
                )
                await on_worker_complete(
                    agent_id=worker.id,
                    task=worker.task,
                    target=self.target,
                    result=worker.result or "",
                    success=False,
                )
            else:
                worker.status = AgentStatus.COMPLETE
                self._emit(
                    worker.id,
                    "complete",
                    {
                        "summary": worker.result[:200],
                    },
                )
                await on_worker_complete(
                    agent_id=worker.id,
                    task=worker.task,
                    target=self.target,
                    result=worker.result or "",
                    success=True,
                )

        except asyncio.CancelledError:
            worker.status = AgentStatus.CANCELLED
            worker.completed_at = time.time()
            self._emit(worker.id, "cancelled", {})
            raise

        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(
                "Worker execution failed (%s): %s", worker.id, e
            )
            try:
                from ...interface.notifier import notify

                notify("warning", f"Worker execution failed ({worker.id}): {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about worker execution failure: %s", ne
                )
            worker.error = str(e)
            worker.status = AgentStatus.ERROR
            worker.completed_at = time.time()
            self._emit(worker.id, "error", {"error": str(e)})
            await on_worker_complete(
                agent_id=worker.id,
                task=worker.task,
                target=self.target,
                result=worker.error or "",
                success=False,
            )

        finally:
            # Cleanup worker's isolated runtime
            try:
                await worker_runtime.stop()
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(
                    "Failed to stop worker runtime for %s: %s", worker.id, e
                )
                try:
                    from ...interface.notifier import notify

                    notify(
                        "warning", f"Failed to stop worker runtime for {worker.id}: {e}"
                    )
                except Exception as ne:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about worker runtime stop failure: %s",
                        ne,
                    )

    async def _wait_for_dependencies(self, depends_on: List[str]) -> None:
        """Wait for dependent workers to complete."""
        for dep_id in depends_on:
            if dep_id in self._tasks:
                try:
                    await self._tasks[dep_id]
                except (asyncio.CancelledError, Exception) as e:
                    import logging

                    logging.getLogger(__name__).exception(
                        "Dependency wait failed for %s: %s", dep_id, e
                    )
                    try:
                        from ...interface.notifier import notify

                        notify("warning", f"Dependency wait failed for {dep_id}: {e}")
                    except Exception as ne:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about dependency wait failure: %s",
                            ne,
                        )
                    # Dependency failed, but we continue

    async def wait_for(self, agent_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Wait for specified agents (or all) to complete.

        Args:
            agent_ids: List of agent IDs to wait for. None = wait for all.

        Returns:
            Dict mapping agent_id to result/error
        """
        if agent_ids is None:
            agent_ids = list(self._tasks.keys())

        results = {}
        for agent_id in agent_ids:
            if agent_id in self._tasks:
                try:
                    await self._tasks[agent_id]
                except (asyncio.CancelledError, Exception) as e:
                    import logging

                    logging.getLogger(__name__).exception(
                        "Waiting for agent task %s failed: %s", agent_id, e
                    )
                    try:
                        from ...interface.notifier import notify

                        notify("warning", f"Waiting for agent {agent_id} failed: {e}")
                    except Exception as ne:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about wait_for agent failure: %s",
                            ne,
                        )

                worker = self._workers.get(agent_id)
                if worker:
                    results[agent_id] = {
                        "task": worker.task,
                        "status": worker.status.value,
                        "result": worker.result,
                        "error": worker.error,
                        "tools_used": worker.tools_used,
                    }

        return results

    def get_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific agent."""
        worker = self._workers.get(agent_id)
        if not worker:
            return None
        return worker.to_dict()

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all agents."""
        return {wid: w.to_dict() for wid, w in self._workers.items()}

    async def cancel(self, agent_id: str) -> bool:
        """Cancel a running agent."""
        if agent_id not in self._tasks:
            return False

        task = self._tasks[agent_id]
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return True
        return False

    async def cancel_all(self) -> None:
        """Cancel all running agents."""
        for task in self._tasks.values():
            if not task.done():
                task.cancel()

        # Wait for all to finish
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    def get_results(self) -> Dict[str, str]:
        """Get results from all completed agents."""
        return dict(self._results)

    def get_workers(self) -> List[AgentWorker]:
        """Get all workers."""
        return list(self._workers.values())

    def reset(self) -> None:
        """Reset the pool for a new task."""
        self._workers.clear()
        self._tasks.clear()
        self._results.clear()
        self._next_id = 0
