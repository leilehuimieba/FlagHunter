"""Tests for misc chain extraction."""

from __future__ import annotations

import importlib
import importlib.util

from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher


def test_misc_chain_mixin_module_exists():
    spec = importlib.util.find_spec("flaghunter.agents.pa_agent.chains.misc")
    assert spec is not None
    module = importlib.import_module("flaghunter.agents.pa_agent.chains.misc")
    assert hasattr(module, "MiscChainMixin")


def test_dispatcher_misc_chain_method_comes_from_misc_mixin():
    assert (
        CTFTaskDispatcher._execute_misc_chain.__module__
        == "flaghunter.agents.pa_agent.chains.misc"
    )
