"""
PlaybookEngine — CTF Playbook 解析执行引擎

功能：
    - 从 YAML 文件加载 CTF 解题 Playbook
    - 异步按阶段（Phase）执行解题流程
    - 支持工具调用、LLM 分析提示词、Fallback 策略
    - 提供进度追踪与结果汇总

用法：
    engine = PlaybookEngine("./playbooks")
    engine.load_all_playbooks()
    result = await engine.execute("web_standard", "http://target.example.com")
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """单次工具调用的定义"""
    tool: str                           # 工具名称，如 "nmap", "pwntools_remote"
    args: dict = field(default_factory=dict)
    condition: Optional[str] = None     # 执行条件（可选，简单表达式）


@dataclass
class FallbackStrategy:
    """阶段失败时的回退策略"""
    action: str                         # "skip" | "retry" | "alternative_tool" | "manual"
    alternative: Optional[str] = None   # 替代工具或策略名称
    max_retries: int = 1


@dataclass
class Phase:
    """Playbook 中的单个解题阶段"""
    name: str
    description: str
    tools: List[ToolCall]
    llm_prompt: str                     # 发给 LLM 的分析提示词
    expected_output: Optional[str] = None
    timeout: int = 300                  # 单阶段超时（秒）
    critical: bool = False              # True 时失败则整个 Playbook 失败


@dataclass
class CtfPlaybook:
    """CTF Playbook 根对象"""
    name: str
    category: str                       # web / pwn / crypto / reverse / misc
    description: str
    difficulty: str                     # easy / medium / hard / expert
    phases: List[Phase]
    fallback: Optional[FallbackStrategy] = None
    required_tools: List[str] = field(default_factory=list)
    estimated_time: str = "30min"


@dataclass
class PhaseResult:
    """单个阶段的执行结果"""
    phase_name: str
    success: bool
    output: str
    llm_analysis: str
    tool_results: List[dict]
    duration_ms: int
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PlaybookResult:
    """整个 Playbook 的执行结果"""
    playbook_name: str
    target: str
    success: bool
    phase_results: List[PhaseResult]
    flag: Optional[str] = None
    total_duration_ms: int = 0
    summary: str = ""


# ---------------------------------------------------------------------------
# 引擎核心
# ---------------------------------------------------------------------------

class PlaybookEngine:
    """
    CTF Playbook 引擎 — 解析并执行 YAML 格式的解题流程。

    支持：
        - 从 YAML 文件加载 Playbook
        - 异步阶段执行（半自动，每阶段后暂停等待外部确认）
        - Fallback 策略（跳过 / 重试 / 替代工具 / 手动）
        - 关键阶段保护（critical=True 时失败终止整体流程）
        - 执行进度查询
    """

    def __init__(self, playbook_dir: str | None = None) -> None:
        """
        初始化引擎。

        :param playbook_dir: Playbook YAML 文件所在目录；None 时使用内置 playbooks/ 目录。
        """
        if playbook_dir is None:
            playbook_dir = os.path.join(os.path.dirname(__file__), "playbooks")
        self._playbook_dir: str = playbook_dir
        self._playbooks: Dict[str, CtfPlaybook] = {}

        # 运行时状态
        self._current_playbook: Optional[str] = None
        self._current_phase: int = 0
        self._phase_results: List[PhaseResult] = []
        self._running: bool = False
        self._paused: bool = False
        self._resume_event: asyncio.Event = asyncio.Event()
        self._resume_event.set()  # 初始未暂停

    # ------------------------------------------------------------------
    # Playbook 加载与管理
    # ------------------------------------------------------------------

    def load_playbook(self, name: str) -> CtfPlaybook:
        """
        从 YAML 文件加载单个 Playbook。

        :param name: Playbook 名称（不含 .yaml 后缀）。
        :raises FileNotFoundError: 找不到对应 YAML 文件。
        :raises ValueError: YAML 解析或字段校验失败。
        :return: 构建好的 CtfPlaybook 对象。
        """
        filepath = os.path.join(self._playbook_dir, f"{name}.yaml")
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Playbook 文件不存在: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            raw: dict = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise ValueError(f"YAML 根节点应为字典: {filepath}")

        playbook = self._yaml_to_playbook(raw)
        self._playbooks[name] = playbook
        return playbook

    def load_all_playbooks(self) -> Dict[str, CtfPlaybook]:
        """
        加载目录下所有 *.yaml Playbook 文件。

        :return: 名称 -> CtfPlaybook 的字典。
        """
        if not os.path.isdir(self._playbook_dir):
            return self._playbooks

        for entry in sorted(os.listdir(self._playbook_dir)):
            if entry.endswith(".yaml") or entry.endswith(".yml"):
                name = entry.rsplit(".", 1)[0]
                try:
                    self.load_playbook(name)
                except Exception as exc:
                    print(f"[PlaybookEngine] 加载失败 {entry}: {exc}")
        return self._playbooks

    def list_playbooks(self) -> List[str]:
        """
        列出所有已加载的 Playbook 名称。

        :return: Playbook 名称列表。
        """
        return list(self._playbooks.keys())

    def list_by_category(self, category: str) -> List[str]:
        """
        按题型类别过滤 Playbook。

        :param category: 类别，如 "web", "pwn", "crypto", "reverse", "misc"。
        :return: 符合条件的 Playbook 名称列表。
        """
        return [
            name
            for name, pb in self._playbooks.items()
            if pb.category.lower() == category.lower()
        ]

    # ------------------------------------------------------------------
    # 核心执行逻辑
    # ------------------------------------------------------------------

    async def execute(
        self,
        playbook_name: str,
        target: str,
        context: dict | None = None,
    ) -> PlaybookResult:
        """
        执行指定的 Playbook。

        流程：
            1. 加载 Playbook。
            2. 按顺序遍历 phases。
            3. 对每个 phase：执行工具调用 → 汇总输出 → 记录结果。
            4. phase 执行后暂停，等待外部确认再继续（半自动模式）。
            5. phase 失败时应用 fallback 策略。
            6. critical=True 的 phase 失败则终止整个 Playbook。

        :param playbook_name: Playbook 名称。
        :param target: 目标地址 / 连接字符串 / 文件路径。
        :param context: 额外上下文变量，可覆盖模板中的占位符。
        :return: PlaybookResult 执行结果。
        """
        ctx = context or {}
        self._running = True
        self._paused = False
        self._phase_results = []
        self._current_phase = 0
        self._current_playbook = playbook_name
        self._resume_event.set()

        # 加载 Playbook（若尚未加载）
        if playbook_name not in self._playbooks:
            self.load_playbook(playbook_name)
        playbook = self._playbooks[playbook_name]

        start_all = datetime.now()
        overall_success = True
        captured_flag: Optional[str] = None

        print(f"[PlaybookEngine] 开始执行 Playbook: {playbook.name} | 目标: {target}")

        for idx, phase in enumerate(playbook.phases):
            if not self._running:
                print("[PlaybookEngine] 执行已手动终止。")
                overall_success = False
                break

            self._current_phase = idx + 1
            print(f"\n[Phase {idx + 1}/{len(playbook.phases)}] {phase.name} — {phase.description}")

            # 执行阶段
            result = await self.execute_phase(phase, target, ctx)
            self._phase_results.append(result)

            if result.success:
                print(f"  [OK] 阶段完成，耗时 {result.duration_ms}ms")
                # 尝试从输出中提取 flag
                if not captured_flag:
                    captured_flag = self._extract_flag(result.output)
            else:
                print(f"  [FAIL] 阶段失败: {result.output[:200]}")
                # Fallback 处理
                fb = phase.critical if False else (playbook.fallback if not phase.critical else None)
                fb = playbook.fallback if not phase.critical else None
                if phase.critical:
                    # critical 阶段直接失败
                    overall_success = False
                    print(f"  [CRITICAL] 关键阶段失败，终止 Playbook。")
                    break
                elif playbook.fallback:
                    fb_result = await self._apply_fallback(playbook.fallback, phase, target, ctx)
                    if not fb_result:
                        overall_success = False
                        break

            # ---- 半自动暂停：等待外部继续信号 ----
            if self._running and idx < len(playbook.phases) - 1:
                self._paused = True
                self._resume_event.clear()
                print(f"  [PAUSE] 阶段 {idx + 1} 完成，等待继续指令（调用 resume() 继续）...")
                await self._resume_event.wait()
                self._paused = False

        total_ms = int((datetime.now() - start_all).total_seconds() * 1000)
        self._running = False

        summary = self._build_summary(playbook, self._phase_results, overall_success, captured_flag)

        return PlaybookResult(
            playbook_name=playbook.name,
            target=target,
            success=overall_success,
            phase_results=self._phase_results,
            flag=captured_flag,
            total_duration_ms=total_ms,
            summary=summary,
        )

    async def execute_phase(
        self,
        phase: Phase,
        target: str,
        context: dict | None = None,
    ) -> PhaseResult:
        """
        执行单个 Phase。

        流程：
            1. 遍历 phase.tools 中的每个 ToolCall。
            2. 解析 args 中的模板占位符（如 {{target}}）。
            3. 模拟异步工具调用（实际集成时替换为真实工具调用）。
            4. 汇总工具输出，包装为 PhaseResult。

        :param phase: 要执行的 Phase 对象。
        :param target: 目标地址。
        :param context: 上下文变量，用于渲染模板占位符。
        :return: PhaseResult 阶段执行结果。
        """
        ctx = context or {}
        start = datetime.now()
        tool_outputs: List[dict] = []
        combined_output_parts: List[str] = []

        for tc in phase.tools:
            # 条件判断
            if tc.condition and not self._eval_condition(tc.condition, ctx):
                continue

            # 渲染参数模板
            rendered_args = self._render_template(tc.args, target, ctx)
            print(f"    [Tool] {tc.tool}({rendered_args})")

            try:
                # 模拟异步工具调用（真实场景下替换为实际调用）
                output = await self._call_tool(tc.tool, rendered_args, timeout=phase.timeout)
                tool_outputs.append({
                    "tool": tc.tool,
                    "args": rendered_args,
                    "success": True,
                    "output": output,
                })
                combined_output_parts.append(f"[{tc.tool}]\n{output}")
            except Exception as exc:
                err_msg = str(exc)
                tool_outputs.append({
                    "tool": tc.tool,
                    "args": rendered_args,
                    "success": False,
                    "output": err_msg,
                })
                combined_output_parts.append(f"[{tc.tool}] ERROR: {err_msg}")

        combined_output = "\n---\n".join(combined_output_parts)
        duration_ms = int((datetime.now() - start).total_seconds() * 1000)

        # 模拟 LLM 分析（实际场景发送 phase.llm_prompt + output 给 LLM）
        llm_analysis = (
            f"[LLM 分析提示] {phase.llm_prompt[:120]}...\n"
            f"基于工具输出（{len(tool_outputs)} 个工具），建议下一步操作。"
        )

        success = any(r["success"] for r in tool_outputs) if tool_outputs else True

        return PhaseResult(
            phase_name=phase.name,
            success=success,
            output=combined_output,
            llm_analysis=llm_analysis,
            tool_results=tool_outputs,
            duration_ms=duration_ms,
        )

    def resume(self) -> None:
        """
        继续执行（在半自动暂停后调用）。
        """
        if self._paused:
            self._resume_event.set()
            print("[PlaybookEngine] 已发出继续信号。")

    def stop(self) -> None:
        """
        停止 Playbook 执行。
        """
        self._running = False
        self._resume_event.set()  # 确保阻塞的 execute 能退出
        print("[PlaybookEngine] 执行停止信号已发出。")

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_current_phase(self) -> PhaseResult | None:
        """
        获取当前阶段的执行结果。

        :return: 最新的 PhaseResult，若尚未执行则返回 None。
        """
        if not self._phase_results:
            return None
        return self._phase_results[-1]

    def get_progress(self) -> dict:
        """
        返回当前执行进度。

        :return: 字典，包含 current_phase（当前阶段序号）、total_phases（总阶段数）、
                 completed_phases（已完成阶段数）、status（状态字符串）。
        """
        completed = len(self._phase_results)
        if self._current_playbook and self._current_playbook in self._playbooks:
            total = len(self._playbooks[self._current_playbook].phases)
        else:
            total = 0

        if not self._running and completed == 0:
            status = "idle"
        elif self._paused:
            status = "paused"
        elif self._running:
            status = "running"
        else:
            status = "completed"

        return {
            "current_phase": self._current_phase,
            "total_phases": total,
            "completed_phases": completed,
            "status": status,
        }

    # ------------------------------------------------------------------
    # YAML 反序列化
    # ------------------------------------------------------------------

    def _yaml_to_playbook(self, data: dict) -> CtfPlaybook:
        """
        从解析后的 YAML 字典构建 CtfPlaybook 对象。

        :param data: yaml.safe_load 返回的字典。
        :raises ValueError: 缺少必要字段时抛出。
        :return: CtfPlaybook 实例。
        """
        meta = data.get("metadata", {})
        if not meta:
            raise ValueError("YAML 缺少 metadata 节")

        name = meta.get("name", "")
        category = meta.get("category", "misc")
        description = meta.get("description", "")
        difficulty = meta.get("difficulty", "medium")
        estimated_time = meta.get("estimated_time", "30min")
        required_tools = meta.get("required_tools", [])

        # phases
        phases: List[Phase] = []
        for ph in data.get("phases", []):
            tools: List[ToolCall] = []
            for tc in ph.get("tools", []):
                tools.append(
                    ToolCall(
                        tool=tc.get("tool", ""),
                        args=tc.get("args", {}),
                        condition=tc.get("condition"),
                    )
                )
            phases.append(
                Phase(
                    name=ph.get("name", ""),
                    description=ph.get("description", ""),
                    tools=tools,
                    llm_prompt=ph.get("llm_prompt", ""),
                    expected_output=ph.get("expected_output"),
                    timeout=ph.get("timeout", 300),
                    critical=ph.get("critical", False),
                )
            )

        # fallback
        fallback: Optional[FallbackStrategy] = None
        fb = data.get("fallback")
        if fb:
            fallback = FallbackStrategy(
                action=fb.get("action", "manual"),
                alternative=fb.get("alternative"),
                max_retries=fb.get("max_retries", 1),
            )

        return CtfPlaybook(
            name=name,
            category=category,
            description=description,
            difficulty=difficulty,
            phases=phases,
            fallback=fallback,
            required_tools=required_tools,
            estimated_time=estimated_time,
        )

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    async def _call_tool(self, tool: str, args: dict, timeout: int) -> str:
        """
        模拟异步工具调用。

        实际集成时应根据 tool 名称分发到真实工具实现。
        此处仅模拟等待并返回占位输出，方便测试引擎流程。

        :param tool: 工具名称。
        :param args: 渲染后的参数字典。
        :param timeout: 超时秒数。
        :return: 工具输出字符串。
        """
        await asyncio.sleep(0.05)  # 模拟 I/O 延迟
        return f"[模拟输出] 工具 {tool} 执行完成，参数: {args}"

    async def _apply_fallback(
        self,
        fallback: FallbackStrategy,
        phase: Phase,
        target: str,
        context: dict,
    ) -> bool:
        """
        应用 Fallback 策略。

        :param fallback: FallbackStrategy 对象。
        :param phase: 失败的 Phase。
        :param target: 目标地址。
        :param context: 上下文。
        :return: True 表示处理后可继续，False 表示终止 Playbook。
        """
        print(f"  [Fallback] 策略: {fallback.action}")
        if fallback.action == "skip":
            return True
        elif fallback.action == "retry":
            for attempt in range(1, fallback.max_retries + 1):
                print(f"  [Retry] 第 {attempt}/{fallback.max_retries} 次重试...")
                result = await self.execute_phase(phase, target, context)
                self._phase_results.append(result)
                if result.success:
                    return True
            return False
        elif fallback.action == "alternative_tool" and fallback.alternative:
            print(f"  [Alt] 切换到替代工具: {fallback.alternative}")
            alt_phase = Phase(
                name=f"{phase.name}_alt",
                description=f"使用替代工具 {fallback.alternative}",
                tools=[ToolCall(tool=fallback.alternative, args={})],
                llm_prompt=phase.llm_prompt,
                timeout=phase.timeout,
            )
            result = await self.execute_phase(alt_phase, target, context)
            self._phase_results.append(result)
            return result.success
        else:
            print("  [Manual] 需要手动处理，终止自动流程。")
            return False

    def _render_template(self, args: dict, target: str, context: dict) -> dict:
        """
        渲染参数字典中的模板占位符。

        支持的占位符：
            - {{target}}        -> target 整体
            - {{target_host}}   -> target 的主机部分（若适用）
            - {{target_port}}   -> target 的端口部分（若适用）
            - {{context_key}}   -> context 中的同名变量

        :param args: 原始参数字典。
        :param target: 目标字符串。
        :param context: 上下文变量。
        :return: 渲染后的参数字典。
        """
        rendered: dict = {}
        # 简单解析 target 为 host / port
        host, port = self._parse_target(target)

        for k, v in args.items():
            if isinstance(v, str):
                s = v
                s = s.replace("{{target}}", target)
                s = s.replace("{{target_host}}", host)
                s = s.replace("{{target_port}}", str(port) if port else "")
                for ck, cv in context.items():
                    s = s.replace(f"{{{{{ck}}}}}", str(cv))
                rendered[k] = s
            else:
                rendered[k] = v
        return rendered

    @staticmethod
    def _parse_target(target: str) -> tuple[str, int | None]:
        """
        简单解析 target 字符串，提取 host 和 port。

        :param target: 如 "127.0.0.1:1337" 或 "http://example.com"
        :return: (host, port) 元组，port 解析不到时为 None。
        """
        if "://" in target:
            # URL 格式
            from urllib.parse import urlparse
            parsed = urlparse(target)
            h = parsed.hostname or target
            p = parsed.port
            return h, p
        elif ":" in target:
            parts = target.rsplit(":", 1)
            try:
                return parts[0], int(parts[1])
            except ValueError:
                return target, None
        return target, None

    @staticmethod
    def _eval_condition(condition: str, context: dict) -> bool:
        """
        简单条件表达式求值（仅做演示，实际可扩展为真表达式引擎）。

        :param condition: 条件字符串，如 "os == 'linux'" 或 "port == 80"。
        :param context: 上下文变量。
        :return: 条件是否成立。
        """
        try:
            return bool(eval(condition, {"__builtins__": {}}, context))
        except Exception:
            return True  # 无法判断时默认执行

    @staticmethod
    def _extract_flag(text: str) -> str | None:
        """
        从文本中提取 CTF flag（常见格式 flag{...}）。

        :param text: 工具输出文本。
        :return: 提取到的 flag 字符串，未找到则返回 None。
        """
        import re
        patterns = [
            r"flag\{[^}]+\}",
            r"FLAG\{[^}]+\}",
            r"ctf\{[^}]+\}",
            r"CTF\{[^}]+\}",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(0)
        return None

    @staticmethod
    def _build_summary(
        playbook: CtfPlaybook,
        phase_results: List[PhaseResult],
        overall_success: bool,
        flag: str | None,
    ) -> str:
        """
        构建执行摘要。

        :param playbook: 当前 Playbook。
        :param phase_results: 各阶段结果。
        :param overall_success: 整体是否成功。
        :param flag: 提取到的 flag。
        :return: 摘要字符串。
        """
        lines = [
            f"Playbook: {playbook.name} ({playbook.category})",
            f"阶段: {len(phase_results)}/{len(playbook.phases)} 完成",
            f"整体状态: {'成功' if overall_success else '失败'}",
        ]
        if flag:
            lines.append(f"Flag: {flag}")
        lines.append("阶段详情:")
        for pr in phase_results:
            icon = "✓" if pr.success else "✗"
            lines.append(f"  [{icon}] {pr.phase_name} — {pr.duration_ms}ms")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 便捷入口（用于直接测试）
# ---------------------------------------------------------------------------

async def main() -> None:
    """简单自测入口"""
    engine = PlaybookEngine()
    engine.load_all_playbooks()
    print("可用 Playbooks:", engine.list_playbooks())

    # 演示：列出 web 类型
    print("Web 类型:", engine.list_by_category("web"))

    # 演示执行（使用模拟工具调用，不会真实攻击任何目标）
    if engine.list_playbooks():
        pb_name = engine.list_playbooks()[0]
        result = await engine.execute(pb_name, "127.0.0.1:8080")
        print("\n=== 执行结果 ===")
        print(result.summary)


if __name__ == "__main__":
    asyncio.run(main())
