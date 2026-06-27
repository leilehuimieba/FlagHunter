"""Tests for the vision (image understanding) tool."""

import base64
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from flaghunter.tools import vision as vision_module
from flaghunter.tools.loader import list_tool_index
from flaghunter.tools.registry import get_tool
from flaghunter.tools.vision import vision


def _make_fake_llm(response):
    """Build a fake LLM class that records construction + generate() inputs."""
    captured: dict = {}

    class _FakeLLM:
        def __init__(self, model=None, config=None, **_kw):
            captured["model"] = model
            captured["config"] = config

        async def generate(self, system_prompt, messages, task_hint="default", **_kw):
            captured["system_prompt"] = system_prompt
            captured["messages"] = messages
            captured["task_hint"] = task_hint
            return response

    return _FakeLLM, captured


def _ok_response(text="analysis text"):
    return SimpleNamespace(content=text, finish_reason="stop")


# --------------------------------------------------------------------------- #
# Registration                                                                 #
# --------------------------------------------------------------------------- #


def test_vision_tool_registered():
    tool = get_tool("vision")
    assert tool is not None
    assert tool.category == "analysis"
    assert "question" in (tool.schema.required or [])


def test_vision_tool_discoverable_in_index():
    names = {item["name"] for item in list_tool_index()}
    assert "vision" in names


# --------------------------------------------------------------------------- #
# Happy path — multimodal message construction                                 #
# --------------------------------------------------------------------------- #


async def test_base64_path_builds_multimodal_image_block():
    fake_cls, captured = _make_fake_llm(_ok_response("a login form"))
    b64 = base64.b64encode(b"ABC").decode("ascii")

    with patch.object(vision_module, "LLM", fake_cls):
        result = await vision(
            {"question": "What is shown?", "image_base64": b64}, runtime=None
        )

    assert result == "a login form"

    content = captured["messages"][0]["content"]
    # text block carries the question
    assert content[0] == {"type": "text", "text": "What is shown?"}
    # image block is a proper base64 data URL
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == f"data:image/png;base64,{b64}"
    assert captured["messages"][0]["role"] == "user"
    assert captured["task_hint"] == "analysis"
    assert captured["system_prompt"]


async def test_image_path_is_read_and_base64_encoded(tmp_path):
    img = tmp_path / "shot.png"
    raw = b"\x89PNG\r\n\x1a\nfake-bytes"
    img.write_bytes(raw)
    expected_b64 = base64.b64encode(raw).decode("ascii")

    fake_cls, captured = _make_fake_llm(_ok_response("path analysis"))
    with patch.object(vision_module, "LLM", fake_cls):
        result = await vision(
            {"question": "describe", "image_path": str(img)}, runtime=None
        )

    assert result == "path analysis"
    content = captured["messages"][0]["content"]
    assert content[1]["image_url"]["url"] == f"data:image/png;base64,{expected_b64}"


async def test_image_path_jpeg_media_type(tmp_path):
    img = tmp_path / "shot.jpg"
    img.write_bytes(b"jpeg-bytes")
    fake_cls, captured = _make_fake_llm(_ok_response())
    with patch.object(vision_module, "LLM", fake_cls):
        await vision({"question": "q", "image_path": str(img)}, runtime=None)

    url = captured["messages"][0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")


async def test_base64_preferred_over_path(tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"on-disk")
    inline = base64.b64encode(b"inline").decode("ascii")

    fake_cls, captured = _make_fake_llm(_ok_response())
    with patch.object(vision_module, "LLM", fake_cls):
        await vision(
            {"question": "q", "image_base64": inline, "image_path": str(img)},
            runtime=None,
        )

    url = captured["messages"][0]["content"][1]["image_url"]["url"]
    assert url == f"data:image/png;base64,{inline}"


# --------------------------------------------------------------------------- #
# Input validation — explicit errors, never silent                            #
# --------------------------------------------------------------------------- #


async def test_missing_question_returns_error():
    result = await vision({"image_base64": "QUJD"}, runtime=None)
    assert result.startswith("Error:")
    assert "question" in result


async def test_missing_image_returns_error():
    result = await vision({"question": "what?"}, runtime=None)
    assert result.startswith("Error:")
    assert "image_base64" in result and "image_path" in result


async def test_unreadable_path_returns_error():
    result = await vision(
        {"question": "q", "image_path": "/no/such/file_xyz.png"}, runtime=None
    )
    assert result.startswith("Error:")
    assert "could not read" in result


async def test_empty_image_file_returns_error(tmp_path):
    img = tmp_path / "empty.png"
    img.write_bytes(b"")
    result = await vision(
        {"question": "q", "image_path": str(img)}, runtime=None
    )
    assert result.startswith("Error:")
    assert "empty" in result


# --------------------------------------------------------------------------- #
# Backend failures must surface, never be swallowed                            #
# --------------------------------------------------------------------------- #


async def test_llm_inband_error_is_surfaced():
    err_resp = SimpleNamespace(content="LLM Error: boom", finish_reason="error")
    fake_cls, _ = _make_fake_llm(err_resp)
    with patch.object(vision_module, "LLM", fake_cls):
        result = await vision(
            {"question": "q", "image_base64": "QUJD"}, runtime=None
        )
    assert result.startswith("Error:")
    assert "boom" in result


async def test_llm_exception_is_surfaced():
    fake_cls, _ = _make_fake_llm(_ok_response())

    async def _boom(*_a, **_k):
        raise RuntimeError("network down")

    with patch.object(vision_module, "LLM", fake_cls):
        with patch.object(fake_cls, "generate", _boom):
            result = await vision(
                {"question": "q", "image_base64": "QUJD"}, runtime=None
            )
    assert result.startswith("Error:")
    assert "network down" in result


async def test_empty_analysis_returns_error():
    fake_cls, _ = _make_fake_llm(SimpleNamespace(content="", finish_reason="stop"))
    with patch.object(vision_module, "LLM", fake_cls):
        result = await vision(
            {"question": "q", "image_base64": "QUJD"}, runtime=None
        )
    assert result.startswith("Error:")
    assert "empty" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
