"""N7-② Guard tests: LocalRuntime.browser_action screenshot returns base64.

The screenshot action must return the on-disk path (backward compatible) AND
an additive base64 / media_type field so the image can be fed to vision LLMs.
"""

import base64

import pytest

from flaghunter.runtime.runtime import LocalRuntime


# Minimal 1x1 PNG (valid file bytes) used as the "captured" screenshot.
_FAKE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class _FakePage:
    """Stand-in for a Playwright Page: writes the fake PNG to the given path."""

    def __init__(self):
        self.url = "http://example.test/"

    async def screenshot(self, path: str, full_page: bool = False):
        with open(path, "wb") as fh:
            fh.write(_FAKE_PNG)


@pytest.mark.asyncio
async def test_screenshot_returns_path_and_base64(tmp_path, monkeypatch):
    # Redirect the workspace loot dir into tmp so the screenshot lands here.
    import flaghunter.workspaces.utils as ws_utils

    def _fake_get_loot_file(rel):
        # browser_action does get_loot_file("artifacts/screenshots").parent
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(ws_utils, "get_loot_file", _fake_get_loot_file)

    rt = LocalRuntime()
    rt._page = _FakePage()

    result = await rt.browser_action(action="screenshot")

    # Backward compatible path field still present and on disk.
    assert "path" in result
    assert result["path"]

    # Additive base64 channel present and correctly encoded.
    assert "base64" in result
    assert result.get("media_type") == "image/png"

    decoded = base64.b64decode(result["base64"].encode("ascii"))
    assert decoded == _FAKE_PNG

    # base64 is plain ascii text.
    assert result["base64"].encode("ascii")


@pytest.mark.asyncio
async def test_screenshot_base64_survives_roundtrip_to_file(tmp_path, monkeypatch):
    import flaghunter.workspaces.utils as ws_utils

    monkeypatch.setattr(
        ws_utils,
        "get_loot_file",
        lambda rel: (tmp_path / rel),
    )
    (tmp_path / "artifacts").mkdir(parents=True, exist_ok=True)

    rt = LocalRuntime()
    rt._page = _FakePage()

    result = await rt.browser_action(action="screenshot")

    on_disk = open(result["path"], "rb").read()
    assert base64.b64decode(result["base64"]) == on_disk
