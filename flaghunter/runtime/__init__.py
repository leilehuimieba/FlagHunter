"""Runtime environment for FlagHunter."""

from .docker_runtime import DockerRuntime
from .ssh_runtime import SSHRuntime
from .runtime import CommandResult, EnvironmentInfo, LocalRuntime, Runtime

__all__ = [
    "Runtime",
    "CommandResult",
    "LocalRuntime",
    "DockerRuntime",
    "SSHRuntime",
    "EnvironmentInfo",
]
