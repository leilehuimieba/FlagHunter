"""Application settings for PentestAgent."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from .constants import (
    AGENT_MAX_ITERATIONS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    get_openai_api_base,
)


@dataclass
class Settings:
    """Application settings."""

    # LLM Settings
    model: str = field(default_factory=lambda: DEFAULT_MODEL)
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_context_tokens: int = 128000

    # API Keys (loaded from environment)
    openai_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY")
    )
    # Optional OpenAI-compatible API base URL (e.g. a relay or local inference server).
    # Reads OPENAI_API_BASE or OPENAI_BASE_URL; None means use the provider default.
    openai_api_base: Optional[str] = field(default_factory=get_openai_api_base)
    anthropic_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY")
    )

    # Paths
    knowledge_path: Path = field(default_factory=lambda: Path("knowledge"))
    mcp_config_path: Path = field(default_factory=lambda: Path("mcp.json"))

    # Docker Settings
    container_name: str = "flaghunter-sandbox"
    docker_image: str = "ghcr.io/gh05tcrew/pentestagent:kali"

    # Agent Settings
    max_iterations: int = AGENT_MAX_ITERATIONS

    # VPN Settings
    vpn_config_path: Optional[Path] = None

    # Interface Settings
    default_interface: str = "tui"  # "tui" or "cli"

    # Prompt Modules
    prompt_modules: List[str] = field(default_factory=list)

    # Target Settings
    target: Optional[str] = None
    scope: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Convert string paths to Path objects if needed."""
        if isinstance(self.knowledge_path, str):
            self.knowledge_path = Path(self.knowledge_path)
        if isinstance(self.mcp_config_path, str):
            self.mcp_config_path = Path(self.mcp_config_path)
        if isinstance(self.vpn_config_path, str):
            self.vpn_config_path = Path(self.vpn_config_path)

    def __repr__(self) -> str:
        # Mask API keys so they never appear in logs or tracebacks.
        return (
            f"Settings(model={self.model!r}, temperature={self.temperature}, "
            f"max_tokens={self.max_tokens}, max_context_tokens={self.max_context_tokens}, "
            f"openai_api_key={'***' if self.openai_api_key else None}, "
            f"anthropic_api_key={'***' if self.anthropic_api_key else None}, "
            f"target={self.target!r}, scope={self.scope!r}, "
            f"max_iterations={self.max_iterations})"
        )

    def __str__(self) -> str:
        return self.__repr__()


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def update_settings(**kwargs) -> Settings:
    """Update global settings with new values."""
    global _settings
    _settings = Settings(**kwargs)
    return _settings


def resolve_model_provider(
    *,
    explicit_provider: str = "",
    api_base: str | None = None,
    openai_api_key: str | None = None,
    anthropic_api_key: str | None = None,
) -> str:
    provider = str(explicit_provider or "").strip()
    normalized_api_base = str(api_base or "").strip()
    if provider:
        return provider
    lowered_base = normalized_api_base.lower()
    if "su8.codes" in lowered_base:
        return "su8.codes"
    if "moonshot" in lowered_base:
        return "kimi"
    if "deepseek" in lowered_base:
        return "deepseek"
    if "mimo" in lowered_base:
        return "mimo"
    if anthropic_api_key:
        return "anthropic"
    if openai_api_key:
        return "openai"
    return "custom"


def resolve_model_readiness(
    *,
    provider: str,
    model: str | None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    normalized_provider = str(provider or "").strip() or "custom"
    normalized_model = str(model or "").strip()
    normalized_api_base = str(api_base or "").strip()
    normalized_api_key = str(api_key or "").strip()

    if not normalized_model:
        return {
            "ready": False,
            "reason": "model_unconfigured",
            "provider": normalized_provider,
            "model": normalized_model,
        }

    if normalized_provider == "custom" and not normalized_api_base:
        return {
            "ready": False,
            "reason": "custom_provider_unconfigured",
            "provider": normalized_provider,
            "model": normalized_model,
        }

    if normalized_provider == "openai" and not normalized_api_key:
        return {
            "ready": False,
            "reason": "openai_api_key_missing",
            "provider": normalized_provider,
            "model": normalized_model,
        }

    if normalized_provider == "anthropic" and not normalized_api_key:
        return {
            "ready": False,
            "reason": "anthropic_api_key_missing",
            "provider": normalized_provider,
            "model": normalized_model,
        }

    return {
        "ready": True,
        "reason": "",
        "provider": normalized_provider,
        "model": normalized_model,
    }
