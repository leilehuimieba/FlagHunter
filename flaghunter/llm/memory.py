"""Conversation memory management for FlagHunter."""

import json
import re
from html import unescape
from typing import Awaitable, Callable, Dict, List, Optional

SUMMARY_FIELDS = (
    "confirmed_facts",
    "open_hypotheses",
    "rejected_payloads",
    "pending_followups",
)

SUMMARY_PROMPT = """Summarize the following conversation segment as structured reasoning
state for a penetration testing agent.
Return valid JSON only. Do not include markdown fences, prose, or comments.

Use exactly this JSON object shape:
{{
  "confirmed_facts": [],
  "open_hypotheses": [],
  "rejected_payloads": [],
  "pending_followups": []
}}

What to preserve:
- Confirmed targets, endpoints, services, versions, redirects, status codes,
  technologies, credentials, tokens, flags, and exact identifiers
- Open hypotheses with their supporting observations
- Rejected payloads, failed paths, negative test outcomes, and why they failed
- Pending follow-ups, next checks, unresolved errors, and verification steps

Compression approach:
- Preserve source pointers such as tool names, URLs, paths, params, hosts, and
  line-level facts
- Consolidate redundant findings into single JSON array entries
- Keep exact paths, URLs, params, version strings, payloads, status codes, and
  exception classes
- Separate confirmed facts from hypotheses and rejected payloads

Conversation segment:
{conversation}

JSON reasoning state:"""


class ConversationMemory:
    """Manages conversation history with token limits and summarization."""

    def __init__(
        self,
        max_tokens: int = 128000,
        reserve_ratio: float = 0.8,
        recent_to_keep: int = 10,
        summarize_threshold: float = 0.6,
    ):
        """
        Initialize conversation memory.

        Args:
            max_tokens: Maximum context tokens
            reserve_ratio: Ratio of tokens to use (leave room for response)
            recent_to_keep: Number of recent messages to keep in full
            summarize_threshold: Summarize when history exceeds this ratio of budget
        """
        self.max_tokens = max_tokens
        self.reserve_ratio = reserve_ratio
        self.recent_to_keep = recent_to_keep
        self.summarize_threshold = summarize_threshold
        self._encoder = None
        self._cached_summary: Optional[str] = None
        self._summarized_count: int = 0

    @property
    def encoder(self):
        """Lazy load the tokenizer."""
        if self._encoder is None:
            try:
                import tiktoken

                self._encoder = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                self._encoder = None
        return self._encoder

    def _count_tokens_with_litellm(self, text: str, model: str) -> Optional[int]:
        """Try to count tokens using litellm for better accuracy."""
        try:
            import litellm

            count = litellm.token_counter(model=model, text=text)
            return int(count)
        except Exception:
            return None

    @property
    def token_budget(self) -> int:
        """Available tokens for history."""
        return int(self.max_tokens * self.reserve_ratio)

    def get_messages(self, messages: List[dict]) -> List[dict]:
        """
        Get messages that fit within token limit (sync, no summarization).
        Falls back to truncation if over budget.

        Args:
            messages: Full conversation history

        Returns:
            Messages that fit within the token budget
        """
        if not messages:
            return []

        # If we have a cached summary, prepend it
        if self._cached_summary and len(messages) > self._summarized_count:
            result = [
                {
                    "role": "system",
                    "content": (
                        "Previous conversation summary:\n"
                        f"{self._cached_summary}"
                    ),
                }
            ]
            # Add messages after the summarized portion
            recent = messages[self._summarized_count :]
            result.extend(
                self._truncate_to_fit(
                    recent, self.token_budget - self._count_tokens(result[0])
                )
            )
            return result

        return self._truncate_to_fit(messages, self.token_budget)

    async def get_messages_with_summary(
        self, messages: List[dict], llm_call: Callable[[str], Awaitable[str]]
    ) -> List[dict]:
        """
        Get messages, summarizing older ones if needed.

        Args:
            messages: Full conversation history
            llm_call: Async function to call LLM for summarization

        Returns:
            Messages with older ones summarized if over threshold
        """
        if not messages:
            return []

        total_tokens = self.get_total_tokens(messages)
        threshold_tokens = int(self.token_budget * self.summarize_threshold)

        # Check if we need to summarize
        if total_tokens <= threshold_tokens:
            return messages

        # Don't summarize if we don't have enough messages
        if len(messages) <= self.recent_to_keep:
            return self._truncate_to_fit(messages, self.token_budget)

        # Split messages: older to summarize, recent to keep
        split_point = len(messages) - self.recent_to_keep
        older = messages[:split_point]
        recent = messages[-self.recent_to_keep :]

        # Check if we already summarized these messages
        if split_point <= self._summarized_count and self._cached_summary:
            result = [
                {
                    "role": "system",
                    "content": (
                        "Previous conversation summary:\n"
                        f"{self._cached_summary}"
                    ),
                }
            ]
            result.extend(recent)
            return result

        # Summarize older messages
        summary = await self._summarize(older, llm_call)

        # Cache the summary
        self._cached_summary = summary
        self._summarized_count = split_point

        # Build result
        result = [
            {"role": "system", "content": f"Previous conversation summary:\n{summary}"}
        ]
        result.extend(recent)

        return result

    async def _summarize(
        self, messages: List[dict], llm_call: Callable[[str], Awaitable[str]]
    ) -> str:
        """
        Summarize a list of messages using chunked approach for better granularity.

        Args:
            messages: Messages to summarize
            llm_call: Async function to call LLM

        Returns:
            Summary string
        """
        if not messages:
            return self._dump_summary_state(self._empty_summary_state())

        # Use chunked summarization for better context preservation
        # Process in chunks of 8-12 messages for balance between detail and efficiency
        chunk_size = 10
        summary_states = []

        for i in range(0, len(messages), chunk_size):
            chunk = messages[i : i + chunk_size]
            conversation_text = self._format_for_summary(chunk)
            prompt = SUMMARY_PROMPT.format(conversation=conversation_text)

            try:
                chunk_summary = await llm_call(prompt)
                if chunk_summary and chunk_summary.strip():
                    summary_states.append(
                        self._normalize_summary_state(
                            chunk_summary, fallback_messages=chunk
                        )
                    )
            except Exception as e:
                fallback = self._fallback_summary_state(chunk)
                fallback["pending_followups"].append(
                    f"Segment {i // chunk_size + 1} summary failed: {e}"
                )
                summary_states.append(fallback)

        if not summary_states:
            return self._dump_summary_state(self._fallback_summary_state(messages))

        return self._dump_summary_state(self._merge_summary_states(summary_states))

    def _format_for_summary(self, messages: List[dict]) -> str:
        """Format messages as text for summarization."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            tool_name = msg.get("name", "tool")
            content = self._compress_content(content, role=role, tool_name=tool_name)

            # Preserve more content for tool outputs (they contain findings)
            # but still limit to avoid overwhelming the summarizer
            max_length = 4000 if role == "tool" else 2000
            if len(content) > max_length:
                # For tool outputs, try to preserve beginning and end
                if role == "tool":
                    half = max_length // 2
                    content = (
                        content[:half]
                        + f"\n...[{len(content) - max_length} chars truncated]...\n"
                        + content[-half:]
                    )
                else:
                    content = content[:max_length] + "...[truncated]"

            if role == "user":
                lines.append(f"User: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")
            elif role == "tool":
                lines.append(f"Tool ({tool_name}): {content}")
            elif role == "system":
                # Skip system messages in summarization input
                continue

        return "\n\n".join(lines)

    def _truncate_to_fit(self, messages: List[dict], budget: int) -> List[dict]:
        """Truncate messages from the beginning to fit budget."""
        total_tokens = 0
        result = []

        for msg in reversed(messages):
            compressed_msg = self._compress_message(msg)
            msg_tokens = self._count_tokens(compressed_msg)
            if total_tokens + msg_tokens > budget:
                break
            result.insert(0, compressed_msg)
            total_tokens += msg_tokens

        return result

    def _compress_message(self, message: dict) -> dict:
        """Return a copy of a message with compressible noise reduced."""
        content = message.get("content", "")
        if not isinstance(content, str) or not content:
            return message

        compressed = self._compress_content(
            content,
            role=message.get("role", "unknown"),
            tool_name=message.get("name", ""),
        )
        if compressed == content:
            return message

        updated = dict(message)
        updated["content"] = compressed
        return updated

    def _compress_content(self, content: str, role: str, tool_name: str = "") -> str:
        """Route content through source-aware compression heuristics."""
        if not isinstance(content, str) or not content:
            return content

        if self._looks_like_error(content):
            return self._compress_error(content)
        if self._looks_like_http(content, tool_name):
            return self._compress_http(content)
        if self._looks_like_shell(content, role, tool_name):
            return self._compress_shell(content)
        return self._compress_repeated_lines(content)

    def _looks_like_http(self, content: str, tool_name: str) -> bool:
        lowered_tool = tool_name.lower()
        return (
            "http" in lowered_tool
            or bool(re.search(r"^HTTP/\d(?:\.\d)?\s+\d{3}\b", content, re.MULTILINE))
            or bool(re.search(r"\bStatus(?: Code)?:\s*\d{3}\b", content, re.IGNORECASE))
            or ("<html" in content.lower() and "</html>" in content.lower())
        )

    def _looks_like_shell(self, content: str, role: str, tool_name: str) -> bool:
        lowered_tool = tool_name.lower()
        return (
            role == "tool"
            and any(
                name in lowered_tool
                for name in ("shell", "terminal", "cmd", "bash", "powershell")
            )
        ) or bool(
            re.search(
                r"^\s*(stdout|stderr)\s*:",
                content,
                re.IGNORECASE | re.MULTILINE,
            )
        )

    def _looks_like_error(self, content: str) -> bool:
        return (
            "Traceback (most recent call last)" in content
            or bool(
                re.search(
                    r"^\s*(?:File \".+\", line \d+|[A-Za-z_][\w.]*Error:)",
                    content,
                    re.MULTILINE,
                )
            )
            or bool(
                re.search(
                    r"^\s*(?:Exception|RuntimeError|ValueError|TypeError|KeyError):",
                    content,
                    re.MULTILINE,
                )
            )
        )

    def _compress_http(self, content: str) -> str:
        """Preserve HTTP status/redirect/facts while stripping markup boilerplate."""
        lines = content.splitlines()
        kept = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"^HTTP/\d(?:\.\d)?\s+\d{3}\b", stripped):
                kept.append(stripped)
                continue
            if re.match(
                (
                    r"^(Status(?: Code)?|Location|Redirect(?:ed)?(?:-To)?|URL|"
                    r"Final-URL|Set-Cookie|Content-Type):"
                ),
                stripped,
                re.IGNORECASE,
            ):
                kept.append(stripped)

        body = re.sub(r"(?is)<script\b.*?</script>", " ", content)
        body = re.sub(r"(?is)<style\b.*?</style>", " ", body)
        body = re.sub(r"(?is)<(nav|footer|header|aside)\b.*?</\1>", " ", body)
        body = re.sub(r"(?is)<!--.*?-->", " ", body)
        body = re.sub(r"(?is)<[^>]+>", " ", body)
        body = unescape(body)

        for line in self._meaningful_lines(body):
            if self._is_key_signal(line) or self._looks_like_endpoint_line(line):
                kept.append(line)

        return self._join_unique(kept) or self._compress_repeated_lines(body)

    def _compress_shell(self, content: str) -> str:
        """Keep stdout data and demote stderr progress/banner noise."""
        stdout_lines = []
        stderr_lines = []
        current = stdout_lines

        for line in content.splitlines():
            stripped = line.strip()
            marker = re.match(r"^(stdout|stderr)\s*:\s*(.*)$", stripped, re.IGNORECASE)
            if marker:
                current = (
                    stderr_lines
                    if marker.group(1).lower() == "stderr"
                    else stdout_lines
                )
                stripped = marker.group(2).strip()
                if not stripped:
                    continue

            if current is stderr_lines and self._is_shell_noise(stripped):
                continue
            if stripped:
                current.append(stripped)

        output = []
        if stdout_lines:
            output.append("stdout:")
            output.extend(self._dedupe_lines(stdout_lines, limit=120))
        if stderr_lines:
            important_stderr = [
                line
                for line in stderr_lines
                if self._is_key_signal(line) or self._looks_like_error(line)
            ]
            if important_stderr:
                output.append("stderr:")
                output.extend(self._dedupe_lines(important_stderr, limit=40))

        return "\n".join(output) if output else self._compress_repeated_lines(content)

    def _compress_error(self, content: str) -> str:
        """Keep the primary exception and de-duplicated stack context."""
        lines = [line.rstrip() for line in content.splitlines() if line.strip()]
        exception_lines = [
            line.strip()
            for line in lines
            if re.match(r"^[A-Za-z_][\w.]*(?:Error|Exception|Warning):", line.strip())
            or re.match(
                r"^(Exception|RuntimeError|ValueError|TypeError|KeyError):",
                line.strip(),
            )
        ]
        file_lines = [
            line.strip()
            for line in lines
            if re.match(r"^File \".+\", line \d+", line.strip())
        ]
        key_lines = [line.strip() for line in lines if self._is_key_signal(line)]
        kept = []
        if exception_lines:
            kept.append(f"primary_exception: {exception_lines[-1]}")
        kept.extend(file_lines[:8])
        kept.extend(key_lines[:20])
        return self._join_unique(kept) or self._join_unique(lines[:20])

    def _compress_repeated_lines(self, content: str) -> str:
        lines = self._meaningful_lines(content)
        if len(lines) <= 80 and len(content) <= 4000:
            return content

        kept = [line for line in lines if self._is_key_signal(line)]
        if not kept:
            kept = lines[:40] + lines[-20:]
        return self._join_unique(kept)

    def _meaningful_lines(self, content: str) -> List[str]:
        """Normalize text into non-boilerplate lines."""
        rough_lines = []
        for line in content.splitlines():
            for part in re.split(r"\s{2,}", line):
                stripped = re.sub(r"\s+", " ", part).strip()
                if stripped:
                    rough_lines.append(stripped)

        return [
            line
            for line in rough_lines
            if not self._is_html_boilerplate(line) and len(line) <= 800
        ]

    def _is_html_boilerplate(self, line: str) -> bool:
        lowered = line.lower()
        if lowered in {"html", "head", "body", "main"}:
            return True
        return bool(
            re.search(
                (
                    r"\b(layout filler|copyright|home about contact|tracking|"
                    r"display:block|banner nav menu)\b"
                ),
                lowered,
            )
        )

    def _is_shell_noise(self, line: str) -> bool:
        lowered = line.lower()
        return bool(
            re.search(
                (
                    r"(\bprogress\b|\bbanner\b|\bspinner\b|\beta\b|"
                    r"\bdownload(?:ing)?\b|\bloaded\b|^\[[-=/#\\|]+\]$)"
                ),
                lowered,
            )
        )

    def _is_key_signal(self, line: str) -> bool:
        return bool(
            re.search(
                r"\b("
                r"confirmed fact|target|endpoint|credential|creds|token|cookie|flag|"
                r"vuln|cve|redirect|location|status|payload|rejected|failed|"
                r"403|401|500|admin|export|backup|found|discovered|service|"
                r"version|port|exception|error|"
                r"hypothesis|suspected|next|todo|follow.?up"
                r")\b",
                line,
                re.IGNORECASE,
            )
        )

    def _looks_like_endpoint_line(self, line: str) -> bool:
        return bool(re.search(r"(?<!\w)/(?:[A-Za-z0-9._~!$&'()*+,;=:@%-]+/?)+", line))

    def _join_unique(self, lines: List[str], limit: int = 160) -> str:
        return "\n".join(self._dedupe_lines(lines, limit=limit))

    def _dedupe_lines(self, lines: List[str], limit: int = 160) -> List[str]:
        seen = set()
        result = []
        for line in lines:
            normalized = re.sub(r"\s+", " ", line).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
            if len(result) >= limit:
                break
        return result

    def _empty_summary_state(self) -> Dict[str, List[str]]:
        return {field: [] for field in SUMMARY_FIELDS}

    def _normalize_summary_state(
        self, raw_summary: str, fallback_messages: Optional[List[dict]] = None
    ) -> Dict[str, List[str]]:
        try:
            parsed = self._parse_summary_json(raw_summary)
        except (TypeError, ValueError, json.JSONDecodeError):
            return self._fallback_summary_state(fallback_messages or [])

        state = self._empty_summary_state()
        for field in SUMMARY_FIELDS:
            value = parsed.get(field, [])
            if isinstance(value, list):
                state[field] = [
                    str(item).strip() for item in value if str(item).strip()
                ]
            elif value:
                state[field] = [str(value).strip()]
        return state

    def _parse_summary_json(self, raw_summary: str) -> dict:
        text = raw_summary.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("summary did not contain a JSON object")
            text = text[start : end + 1]

        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("summary JSON must be an object")
        return parsed

    def _fallback_summary_state(self, messages: List[dict]) -> Dict[str, List[str]]:
        state = self._empty_summary_state()

        for msg in messages:
            role = msg.get("role", "unknown")
            tool_name = msg.get("name", "")
            content = self._compress_content(
                msg.get("content", ""), role=role, tool_name=tool_name
            )
            for line in self._meaningful_lines(content):
                lowered = line.lower()
                if re.search(
                    r"\b(rejected|failed|forbidden|403|401|blocked)\b", lowered
                ):
                    state["rejected_payloads"].append(line)
                elif re.search(
                    r"\b(hypothesis|suspected|maybe|may|might|possible)\b",
                    lowered,
                ):
                    state["open_hypotheses"].append(line)
                elif re.search(
                    r"\b(next|todo|follow.?up|pending|try|verify)\b", lowered
                ):
                    state["pending_followups"].append(line)
                elif self._is_key_signal(line):
                    state["confirmed_facts"].append(line)

        return {
            field: self._dedupe_lines(values, limit=80)
            for field, values in state.items()
        }

    def _merge_summary_states(
        self, states: List[Dict[str, List[str]]]
    ) -> Dict[str, List[str]]:
        merged = self._empty_summary_state()
        for state in states:
            for field in SUMMARY_FIELDS:
                merged[field].extend(state.get(field, []))

        return {
            field: self._dedupe_lines(values, limit=120)
            for field, values in merged.items()
        }

    def _dump_summary_state(self, state: Dict[str, List[str]]) -> str:
        normalized = self._empty_summary_state()
        for field in SUMMARY_FIELDS:
            normalized[field] = [
                str(item) for item in state.get(field, []) if str(item)
            ]
        return json.dumps(normalized, ensure_ascii=False, indent=2)

    def _count_tokens(self, message: dict) -> int:
        """Count tokens in a message."""
        content = message.get("content", "")

        if isinstance(content, str):
            if self.encoder:
                return len(self.encoder.encode(content))
            else:
                return int(len(content.split()) * 1.3)

        return 0

    def get_total_tokens(self, messages: List[dict]) -> int:
        """Get total token count for messages."""
        return sum(self._count_tokens(msg) for msg in messages)

    def fits_in_context(self, messages: List[dict]) -> bool:
        """Check if messages fit in context window."""
        return self.get_total_tokens(messages) <= self.token_budget

    def clear_summary_cache(self):
        """Clear the cached summary (call when conversation is cleared)."""
        self._cached_summary = None
        self._summarized_count = 0

    def get_stats(self) -> dict:
        """Get memory statistics."""
        return {
            "max_tokens": self.max_tokens,
            "token_budget": self.token_budget,
            "summarize_threshold": int(self.token_budget * self.summarize_threshold),
            "recent_to_keep": self.recent_to_keep,
            "has_summary": self._cached_summary is not None,
            "summarized_message_count": self._summarized_count,
        }
