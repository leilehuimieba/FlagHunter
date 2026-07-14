"""Constants for FlagHunter."""

import os
from typing import Optional

# Load .env file before reading environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Honour legacy PENTESTAGENT_* env vars as aliases for the FLAGHUNTER_* names.
from .env import apply_legacy_env_aliases

apply_legacy_env_aliases()

# Application Info
APP_NAME = "FlagHunter"
APP_VERSION = "0.4.1"
APP_DESCRIPTION = "AI-powered CTF & authorised penetration testing automation framework"

# Agent States
AGENT_STATE_IDLE = "idle"
AGENT_STATE_THINKING = "thinking"
AGENT_STATE_EXECUTING = "executing"
AGENT_STATE_WAITING_INPUT = "waiting_input"
AGENT_STATE_COMPLETE = "complete"
AGENT_STATE_ERROR = "error"

# Tool Categories
TOOL_CATEGORY_EXECUTION = "execution"
TOOL_CATEGORY_WEB = "web"
TOOL_CATEGORY_NETWORK = "network"
TOOL_CATEGORY_RECON = "reconnaissance"
TOOL_CATEGORY_EXPLOITATION = "exploitation"
TOOL_CATEGORY_MCP = "mcp"

# Default Timeouts (in seconds)
DEFAULT_COMMAND_TIMEOUT = 300
DEFAULT_VPN_TIMEOUT = 30
DEFAULT_MCP_TIMEOUT = 60

# Docker Settings
DOCKER_SANDBOX_IMAGE = "ghcr.io/leilehuimieba/flaghunter:kali"
DOCKER_NETWORK_MODE = "bridge"

# RAG Settings
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_RAG_TOP_K = 3

# Memory Settings
MEMORY_RESERVE_RATIO = 0.8  # Reserve 20% of context for response

# OpenAI-compatible endpoint
# Returns the configured base URL with no trailing slash, or None if not set.
def get_openai_api_base() -> Optional[str]:
    """Return the configured OpenAI-compatible API base URL, or None."""
    base = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL")
    return base.rstrip("/") if base else None

# LLM Defaults (set FLAGHUNTER_MODEL in .env or shell)
# Intentionally NO fallback — an unset model is a hard config error, not a
# silent default (avoids silently running the wrong model / surprise API costs).
# Every entry point validates BEFORE constructing LLM and emits a clear error:
#   - session/initializer.py:333  (组合根 build_agent_components, raises RuntimeError)
#   - interface/main.py:1728      (TUI bootstrap guard)
#   - interface/tui.py:3062       (TUI status message)
# So DEFAULT_MODEL=None never reaches LiteLLM on any production path; do NOT
# "fix" this by adding a default model here.
DEFAULT_MODEL = os.environ.get("FLAGHUNTER_MODEL")
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8192

# Agent Defaults
AGENT_MAX_ITERATIONS = int(os.environ.get("FLAGHUNTER_AGENT_MAX_ITERATIONS", "50"))
ORCHESTRATOR_MAX_ITERATIONS = int(
    os.environ.get("FLAGHUNTER_ORCHESTRATOR_MAX_ITERATIONS", "50")
)
CTF_HINT_SEARCH_THRESHOLD = int(
    os.environ.get("FLAGHUNTER_CTF_HINT_SEARCH_THRESHOLD", "2")
)
CTF_WP_SEARCH_THRESHOLD = int(
    os.environ.get("FLAGHUNTER_CTF_WP_SEARCH_THRESHOLD", "4")
)

# CTF Solver P1 canonical Claim / VerificationRecord migration switch.
# Runtime-backed evidence is intentionally not a top-level Claim level in P1;
# it is represented later by VerificationRecord.method/decision metadata.
CTF_CLAIMS_V1_ENV_VAR = "FLAGHUNTER_CTF_CLAIMS_V1"
CTF_CLAIMS_V1_DEFAULT = False
CTF_P1_CLAIM_KIND_ALLOWLIST = (
    "flag_found",
    "credential_valid",
    "endpoint_exists",
    "exploit_succeeded",
)
CTF_RUNTIME_IS_VERIFICATION_SEMANTIC = True


def env_flag_enabled(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def is_ctf_claims_v1_enabled() -> bool:
    """Return the live P1 canonical claim-store feature switch."""
    return env_flag_enabled(CTF_CLAIMS_V1_ENV_VAR, default=CTF_CLAIMS_V1_DEFAULT)

# File Extensions
KNOWLEDGE_TEXT_EXTENSIONS = [".txt", ".md"]
KNOWLEDGE_DATA_EXTENSIONS = [".json"]

# MCP Transport Types
MCP_TRANSPORT_STDIO = "stdio"
MCP_TRANSPORT_SSE = "sse"

# MCP protocol version advertised in initialize handshakes — single source so
# the client request (mcp/manager.py) and server response (mcp/server/mcp_core.py)
# stay aligned (H17).
MCP_PROTOCOL_VERSION = "2025-11-25"

# Exit Commands
EXIT_COMMANDS = ["exit", "quit", "q", "bye"]
