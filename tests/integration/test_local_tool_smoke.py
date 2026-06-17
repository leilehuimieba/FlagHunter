"""Local project-tools smoke tests using a temporary localhost target."""

from __future__ import annotations

import os
import threading
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from flaghunter.tools._tool_env import find_tool, patch_tool_path
from flaghunter.tools.dirscan import run_dirscan
from flaghunter.tools.nmap import run_nmap
from flaghunter.tools.nuclei import run_nuclei
from flaghunter.tools.sqlmap import run_sqlmap


pytestmark = [
    pytest.mark.localtools,
    pytest.mark.skipif(
        os.getenv("RUN_LOCAL_TOOL_SMOKE") != "1",
        reason="set RUN_LOCAL_TOOL_SMOKE=1 to run local tool smoke tests",
    ),
]


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        pass


@pytest.fixture
def smoke_site(tmp_path: Path):
    root = tmp_path / "site"
    root.mkdir(parents=True, exist_ok=True)
    (root / "admin").mkdir(parents=True, exist_ok=True)

    (root / "index.html").write_text(
        '<html><body><h1>tool smoke</h1><a href="/admin/">admin</a></body></html>',
        encoding="utf-8",
    )
    (root / "robots.txt").write_text(
        "User-agent: *\nDisallow: /admin/\n",
        encoding="utf-8",
    )
    (root / "login.php").write_text('<?php echo "login"; ?>', encoding="utf-8")
    (root / "admin" / "index.html").write_text(
        "<html><body>admin panel</body></html>",
        encoding="utf-8",
    )
    (root / "item").write_text("item page\n", encoding="utf-8")

    handler = partial(_QuietHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{server.server_port}"
    for _ in range(20):
        try:
            with urllib.request.urlopen(base_url, timeout=2):
                break
        except Exception:
            continue

    yield {
        "base_url": base_url,
        "port": server.server_port,
    }

    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def _require_tool(name: str) -> str:
    patch_tool_path()
    path = find_tool(name)
    if not path:
        pytest.skip(f"{name} not available in local project toolset")
    return path


@pytest.mark.asyncio
async def test_local_nmap_smoke(smoke_site):
    _require_tool("nmap")

    result = await run_nmap(
        target="127.0.0.1",
        ports=str(smoke_site["port"]),
        scan_type="version",
        runtime=None,
    )

    assert result["status"] == "up"
    assert any(
        port["port"] == smoke_site["port"] and port["state"] == "open"
        for port in result["ports"]
    )


@pytest.mark.asyncio
async def test_local_dirscan_smoke(smoke_site):
    _require_tool("ffuf")

    project_root = Path(__file__).resolve().parents[2]
    wordlist = project_root / "tools" / "wordlists" / "minimal-web.txt"
    assert wordlist.exists()

    result = await run_dirscan(
        url=smoke_site["base_url"],
        wordlist=str(wordlist),
        extensions=["php"],
        tool="auto",
        runtime=None,
    )

    found_paths = {entry["path"] for entry in result["found"]}
    assert result["tool_used"] in {"ffuf", "gobuster", "dirsearch"}
    assert {"/admin", "/login.php", "/robots.txt", "/item"}.issubset(found_paths)


@pytest.mark.asyncio
async def test_local_nuclei_smoke(smoke_site):
    _require_tool("nuclei")

    project_root = Path(__file__).resolve().parents[2]
    templates_dir = (
        project_root / "tools" / "nuclei" / "nuclei-templates" / "http" / "technologies"
    )
    assert templates_dir.exists()

    result = await run_nuclei(
        target=smoke_site["base_url"],
        templates=[str(templates_dir)],
        severity=["info", "low", "medium", "high", "critical"],
        tags=[],
        runtime=None,
    )

    assert "error" not in result
    assert result["total"] >= 1


@pytest.mark.asyncio
async def test_local_sqlmap_smoke(smoke_site):
    _require_tool("sqlmap")

    result = await run_sqlmap(
        url=f"{smoke_site['base_url']}/item?id=1",
        level=1,
        risk=1,
        runtime=None,
    )

    assert result["vulnerable"] is False
    assert "sqlmap not installed" not in result.get("error", "")
    lowered_raw = result["raw"].lower()
    assert (
        "testing connection to the target url" in lowered_raw
        or "all tested parameters do not appear to be injectable" in lowered_raw
    )
