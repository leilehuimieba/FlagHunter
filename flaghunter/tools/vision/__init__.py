"""Vision (image understanding) tool for FlagHunter.

Closes the loop opened by N7②/N7④: a screenshot (or any image) is turned into a
base64 data URL, packed into an OpenAI-style multimodal message, and fed to a
vision-capable LLM together with a natural-language question. The model's textual
analysis is returned to the agent.

Contract with N7① (``LLM.generate``): one message's ``content`` may be a list of
multimodal blocks, e.g.::

    content: [
        {"type": "text", "text": "<question>"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,<B64>"}},
    ]

This tool only *constructs* such messages; it never edits ``flaghunter/llm/llm.py``.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ...llm.llm import LLM
from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


_VISION_SYSTEM_PROMPT = (
    "You are a precise visual analysis assistant for an offensive-security agent. "
    "Examine the provided image (typically a web-page screenshot or a captured "
    "artifact) and answer the question factually. Transcribe any visible text, "
    "form fields, error messages, banners, version strings, flags, or UI state "
    "exactly as shown. Do not speculate beyond what is visible."
)

# Map common image suffixes to MIME media types for the data URL.
_MEDIA_TYPE_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def _media_type_for_path(path: Path) -> str:
    """Infer the image MIME media type from a file suffix (default PNG)."""
    return _MEDIA_TYPE_BY_SUFFIX.get(path.suffix.lower(), "image/png")


def _build_vision_llm() -> LLM:
    """Construct an LLM instance, preferring a vision-capable model.

    Honours the configured model/temperature/max_tokens (settings singleton =
    single source). When the M1 model router and provider inventory are
    reachable, asks the router for a vision-capable model (N7④
    ``require_vision``); otherwise degrades gracefully to the default model so
    the tool never hard-depends on the router being initialised.
    """
    from ...config.settings import get_settings
    from ...llm.config import ModelConfig

    settings = get_settings()
    model = settings.model

    try:
        import flaghunter.cpa_modules.m1_api_hub as m1_api_hub
        from flaghunter.cpa_modules.m1_api_hub.model_router import route

        provider_manager = m1_api_hub.get_provider_manager()
        available = (
            provider_manager.list_healthy_providers()
            or provider_manager.list_providers()
        )
        available_models = [
            provider.model for provider in available if getattr(provider, "model", "")
        ]
        if available_models:
            candidate = route(
                task_hint="analysis",
                available_providers=available_models,
                require_vision=True,
            )
            if candidate:
                model = candidate
    except Exception:
        # Router/provider inventory unavailable — fall back to the default model.
        pass

    return LLM(
        model=model,
        config=ModelConfig(
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        ),
    )


def _resolve_image_b64(arguments: dict) -> tuple[Optional[str], str, Optional[str]]:
    """Resolve the image to a (base64, media_type, error) triple.

    Prefers an inline ``image_base64``; otherwise reads ``image_path`` from disk
    and base64-encodes it (mirroring the N7② screenshot encoding). Returns an
    explicit error string instead of silently swallowing failures.
    """
    raw_b64 = arguments.get("image_base64")
    if isinstance(raw_b64, str) and raw_b64.strip():
        return raw_b64.strip(), "image/png", None

    raw_path = arguments.get("image_path")
    if isinstance(raw_path, str) and raw_path.strip():
        path = Path(raw_path.strip())
        try:
            image_bytes = path.read_bytes()
        except OSError as exc:
            return None, "image/png", f"Error: could not read image_path '{path}': {exc}"
        if not image_bytes:
            return None, "image/png", f"Error: image_path '{path}' is empty"
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return encoded, _media_type_for_path(path), None

    return (
        None,
        "image/png",
        "Error: provide either 'image_base64' or 'image_path'",
    )


@register_tool(
    name="vision",
    description=(
        "Analyze an image with a vision-capable LLM. Feed a screenshot (e.g. from "
        "the browser tool's screenshot action) or any image — by inline base64 or "
        "a file path — together with a question, and get back a textual analysis "
        "(transcribed text, form fields, error banners, flags, UI state, etc.)."
    ),
    schema=ToolSchema(
        properties={
            "question": {
                "type": "string",
                "description": "What to ask about the image (e.g. 'What error is shown?').",
            },
            "image_base64": {
                "type": "string",
                "description": "Base64-encoded image data (preferred). Raw base64, no data: prefix.",
            },
            "image_path": {
                "type": "string",
                "description": "Path to an image file on disk; read and base64-encoded automatically.",
            },
        },
        required=["question"],
    ),
    category="analysis",
)
async def vision(arguments: dict, runtime: "Runtime") -> str:
    """Analyze an image by question via a vision-capable LLM. See module docstring."""
    question = str(arguments.get("question") or "").strip()
    if not question:
        return "Error: 'question' is required"

    image_b64, media_type, error = _resolve_image_b64(arguments)
    if error is not None:
        return error
    assert image_b64 is not None  # guaranteed when error is None

    content = [
        {"type": "text", "text": question},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
        },
    ]
    messages = [{"role": "user", "content": content}]

    try:
        llm = _build_vision_llm()
        response = await llm.generate(
            system_prompt=_VISION_SYSTEM_PROMPT,
            messages=messages,
            task_hint="analysis",
        )
    except Exception as exc:
        return f"Error: vision analysis failed: {exc}"

    # LLM.generate returns errors in-band (content prefixed 'LLM Error:',
    # finish_reason 'error'/'budget_exhausted'/...). Surface them explicitly
    # instead of returning a misleading empty/garbled analysis.
    finish_reason = getattr(response, "finish_reason", "") or ""
    text = (getattr(response, "content", "") or "").strip()

    if finish_reason in ("error", "budget_exhausted", "provider_unavailable"):
        return f"Error: vision analysis failed: {text or finish_reason}"
    if text.startswith("LLM Error:"):
        return f"Error: vision analysis failed: {text}"
    if not text:
        return "Error: vision model returned an empty analysis"

    return text
