"""N7① guard tests: the LLM message pipeline must carry multimodal (list-form)
content through to ``litellm.acompletion`` unflattened, and helpers that extract
text must tolerate list content.

Contract (relied on by the vision tool, N7③): ``generate()`` must allow a
message whose ``content`` is an OpenAI-style list of blocks
(``[{"type":"text",...}, {"type":"image_url",...}]``) and pass it through to
``litellm.acompletion`` without dropping the image block — while leaving the
legacy str-content path byte-for-byte unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaghunter.llm.config import ModelConfig
from flaghunter.llm.llm import LLM, _coerce_content_to_text, _extract_content


# --------------------------------------------------------------------------- #
# Test doubles                                                                 #
# --------------------------------------------------------------------------- #
class _PassthroughMemory:
    """Memory stub that returns history verbatim (no summarization)."""

    async def get_messages_with_summary(self, messages, llm_call=None):
        return list(messages)

    def clear_summary_cache(self):
        return None


class _CapturingLiteLLM:
    """Captures the kwargs of the final acompletion call."""

    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    async def acompletion(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self._response


def _fake_response(content="ok", *, model="gpt-4o"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=None,
        model=model,
    )


def _build_llm(fake_litellm) -> LLM:
    llm = object.__new__(LLM)
    llm.model = "gpt-4o"
    llm.config = ModelConfig(max_retries=0, retry_delay=0.0)
    llm.rag_engine = None
    llm.memory = _PassthroughMemory()
    llm._litellm = fake_litellm
    return llm


_IMAGE_URL = "data:image/png;base64,AAAABBBBCCCC"


def _multimodal_message():
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "What is in this screenshot?"},
            {"type": "image_url", "image_url": {"url": _IMAGE_URL}},
        ],
    }


# --------------------------------------------------------------------------- #
# generate(): image block survives the request pipeline                        #
# --------------------------------------------------------------------------- #
async def test_generate_passes_image_block_through(monkeypatch):
    monkeypatch.setenv("CPA_M1_API_HUB", "false")  # force the plain acompletion path
    fake = _CapturingLiteLLM(_fake_response("looks like a login page"))
    llm = _build_llm(fake)

    resp = await llm.generate(
        system_prompt="you are a pentester",
        messages=[_multimodal_message()],
    )

    assert resp.finish_reason == "stop"
    assert len(fake.calls) == 1
    sent = fake.calls[0]["messages"]

    # System prompt + our one user message.
    user_msg = next(m for m in sent if m["role"] == "user")
    assert isinstance(user_msg["content"], list)

    blocks = user_msg["content"]
    # The image block must NOT be flattened/dropped.
    image_blocks = [b for b in blocks if b.get("type") == "image_url"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["image_url"]["url"] == _IMAGE_URL
    # The text block is still present too.
    assert any(b.get("type") == "text" for b in blocks)


# --------------------------------------------------------------------------- #
# generate(): legacy str-content path is unchanged (regression lock)           #
# --------------------------------------------------------------------------- #
async def test_generate_str_content_unchanged(monkeypatch):
    monkeypatch.setenv("CPA_M1_API_HUB", "false")
    fake = _CapturingLiteLLM(_fake_response("hello back"))
    llm = _build_llm(fake)

    resp = await llm.generate(
        system_prompt="sys",
        messages=[{"role": "user", "content": "plain string question"}],
    )

    assert resp.content == "hello back"
    sent = fake.calls[0]["messages"]
    user_msg = next(m for m in sent if m["role"] == "user")
    # Exact str passthrough — no wrapping into a list, no mutation.
    assert user_msg["content"] == "plain string question"


# --------------------------------------------------------------------------- #
# _extract_content / _coerce_content_to_text robustness                        #
# --------------------------------------------------------------------------- #
def test_extract_content_list_returns_joined_text_no_raise():
    msg = SimpleNamespace(
        content=[
            {"type": "text", "text": "alpha "},
            {"type": "image_url", "image_url": {"url": _IMAGE_URL}},
            {"type": "text", "text": "beta"},
        ]
    )
    out = _extract_content(msg)
    assert isinstance(out, str)
    assert "alpha " in out
    assert "beta" in out
    # raw base64 image payload must not leak into the extracted text
    assert _IMAGE_URL not in out


def test_extract_content_str_unchanged():
    msg = SimpleNamespace(content="just text")
    assert _extract_content(msg) == "just text"


def test_coerce_handles_edge_cases():
    assert _coerce_content_to_text("x") == "x"
    assert _coerce_content_to_text(None) == ""
    assert _coerce_content_to_text([]) == ""
    assert _coerce_content_to_text(["a", "b"]) == "ab"
    # text-only block list flattens to its text
    assert (
        _coerce_content_to_text([{"type": "text", "text": "hi"}]) == "hi"
    )
