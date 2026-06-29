"""P5 — CLI ``--profile`` selection wiring (single real selection entry)."""

from __future__ import annotations

import importlib
import inspect
import sys

import flaghunter.interface.cli as cli

# ``from flaghunter.interface import main`` resolves to the main() *function* via
# the package's lazy __getattr__; import the submodule explicitly.
main_mod = importlib.import_module("flaghunter.interface.main")


def test_run_cli_accepts_profile_defaulting_to_ctf():
    params = inspect.signature(cli.run_cli).parameters
    assert "profile" in params
    assert params["profile"].default == "ctf"


def test_run_cli_forwards_profile_to_dispatcher_and_crew():
    # Both the single-agent dispatcher and the crew runner get the profile.
    src = inspect.getsource(cli.run_cli)
    assert src.count("profile=profile") >= 2


def test_run_ctf_crew_solve_accepts_and_forwards_profile():
    from flaghunter.agents.pa_agent import ctf_crew_runner

    params = inspect.signature(ctf_crew_runner.run_ctf_crew_solve).parameters
    assert "profile" in params
    assert params["profile"].default == "ctf"
    # Forwarded to BOTH the planning and worker dispatcher constructions.
    src = inspect.getsource(ctf_crew_runner.run_ctf_crew_solve)
    assert src.count("profile=profile") >= 2


def test_run_command_parser_registers_profile(monkeypatch):
    monkeypatch.setattr(
        sys, "argv",
        ["flaghunter", "run", "-t", "x", "--profile", "code_audit", "scan"],
    )
    _, args = main_mod.parse_arguments()
    assert args.profile == "code_audit"


def test_run_command_parser_profile_defaults_to_ctf(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["flaghunter", "run", "-t", "x", "scan"])
    _, args = main_mod.parse_arguments()
    assert args.profile == "ctf"
