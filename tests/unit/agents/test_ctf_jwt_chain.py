"""Tests for JWT chain extraction."""

from __future__ import annotations

import importlib
import importlib.util
import inspect

from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher


def test_jwt_chain_mixin_module_exists():
    spec = importlib.util.find_spec("flaghunter.agents.pa_agent.chains.jwt")
    assert spec is not None
    module = importlib.import_module("flaghunter.agents.pa_agent.chains.jwt")
    assert hasattr(module, "JWTChainMixin")


def test_dispatcher_jwt_chain_handler_delegates_to_jwt_mixin():
    source = inspect.getsource(CTFTaskDispatcher._chain_handler_map)

    assert "_execute_jwt_chain" in source
    assert (
        CTFTaskDispatcher._execute_jwt_chain.__module__
        == "flaghunter.agents.pa_agent.chains.jwt"
    )
