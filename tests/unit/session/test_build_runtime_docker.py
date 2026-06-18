"""Wiring tests for the ``--docker`` runtime path.

Regression guard: a bare ``DockerRuntime()`` used to default to the local
``flaghunter:latest`` *base* tag and ``build_runtime`` never passed the
configured image through, so ``--docker`` silently ignored
``settings.docker_image`` (the published Kali sandbox). These tests pin both
the default and the wiring.
"""

import pytest

from flaghunter.config.constants import DOCKER_SANDBOX_IMAGE
from flaghunter.config.settings import Settings
from flaghunter.runtime.docker_runtime import DockerConfig
from flaghunter.session import initializer


class _FakeDockerRuntime:
    """Stand-in that records the config it was constructed with."""

    last_config = None

    def __init__(self, config=None, **kwargs):
        self.config = config
        type(self).last_config = config

    async def start(self):
        self.started = True


def test_docker_config_default_image_is_kali_sandbox_not_base():
    cfg = DockerConfig()
    # Must default to the published Kali sandbox, not the old base tag.
    assert cfg.image == DOCKER_SANDBOX_IMAGE
    assert cfg.image.endswith(":kali")
    assert cfg.image != "flaghunter:latest"
    assert "pentestagent" not in cfg.image


@pytest.mark.asyncio
async def test_build_runtime_docker_propagates_configured_image(monkeypatch):
    sentinel_image = "ghcr.io/example/flaghunter:kali-test"
    monkeypatch.setattr(
        "flaghunter.config.settings.get_settings",
        lambda: Settings(docker_image=sentinel_image, container_name="fh-test"),
    )
    monkeypatch.setattr(
        "flaghunter.runtime.docker_runtime.DockerRuntime", _FakeDockerRuntime
    )

    runtime, info = await initializer.build_runtime(docker=True)

    # The Docker primary is wrapped by HybridBrowserRuntime; the configured
    # image must still reach the underlying DockerRuntime.
    from flaghunter.runtime.hybrid_runtime import HybridBrowserRuntime

    assert isinstance(runtime, HybridBrowserRuntime)
    assert isinstance(runtime.primary, _FakeDockerRuntime)
    assert info["selected"] == "docker"
    assert _FakeDockerRuntime.last_config.image == sentinel_image
    assert _FakeDockerRuntime.last_config.container_name == "fh-test"
    assert sentinel_image in info["status_text"]
