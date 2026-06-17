"""Integration tests for new CTF tools (crypto_solve, angr_solve, radare2).

These tests require a Kali VM runtime and are skipped if SSHRuntime is unavailable.
"""

import json
import os
import pytest

from flaghunter.tools.crypto_solve import crypto_solve
from flaghunter.tools.angr_solve import angr_solve
from flaghunter.tools.radare2 import radare2


# Determine if Kali VM is reachable for integration tests
def _kali_available() -> bool:
    import subprocess
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", "-p", "2222", "user1@127.0.0.1", "echo ok"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and "ok" in result.stdout
    except Exception:
        return False


KALI_AVAILABLE = _kali_available()


class _SSHRuntimeWrapper:
    """Minimal wrapper around SSHRuntime for testing."""

    def __init__(self):
        from flaghunter.runtime.ssh_runtime import SSHRuntime
        self._runtime = SSHRuntime(
            host="127.0.0.1",
            port=2222,
            user="user1",
            key_path=None,  # Uses agent or default key
        )

    async def execute_command(self, cmd: str, timeout: int = 60):
        return await self._runtime.execute_command(cmd, timeout=timeout)



@pytest.fixture
async def kali_runtime():
    """Yield a Kali VM runtime if available."""
    if not KALI_AVAILABLE:
        pytest.skip("Kali VM not available on 127.0.0.1:2222")
    runtime = _SSHRuntimeWrapper()
    await runtime._runtime.start()
    yield runtime


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(not KALI_AVAILABLE, reason="Kali VM not available")
async def test_crypto_solve_rsa_small_e_on_kali(kali_runtime):
    result = await crypto_solve({
        "task": "rsa_small_e",
        "params": {"c": 74088, "e": 3, "n": 1022117},
    }, runtime=kali_runtime)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["plaintext_int"] == 42


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(not KALI_AVAILABLE, reason="Kali VM not available")
async def test_crypto_solve_base64_on_kali(kali_runtime):
    result = await crypto_solve({
        "task": "base64_decode",
        "params": {"data": "ZmxhZ3t0ZXN0fQ=="},
    }, runtime=kali_runtime)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["decoded"] == "flag{test}"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(not KALI_AVAILABLE, reason="Kali VM not available")
async def test_radare2_analyze_crackme_on_kali(kali_runtime):
    # Use the simple crackme uploaded during P0 validation
    result = await radare2({
        "binary_path": "/tmp/crackme_simple",
        "commands": ["afl", "iz"],
    }, runtime=kali_runtime)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["binary"] == "/tmp/crackme_simple"
    assert any(r["command"] == "afl" for r in parsed["results"])


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(not KALI_AVAILABLE, reason="Kali VM not available")
async def test_angr_solve_simple_crackme_on_kali(kali_runtime):
    result = await angr_solve({
        "binary_path": "/tmp/crackme_simple",
        "find_addrs": ["0x40120c"],
        "avoid_addrs": ["0x401213"],
        "input_length": 12,
        "stdin_mode": True,
        "arg_mode": False,
    }, runtime=kali_runtime)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["solution_bytes"] == "CTF{angr_ok}"
