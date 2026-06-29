"""P6 — CLI ``chains`` subcommand: mine emergent tool chains from provenance.

Verifies the read-only wiring (parser registration + handler reads provenance →
miner → prints) without running any agent.
"""

from __future__ import annotations

import importlib
import json
import sys
from argparse import Namespace

from flaghunter.tools import provenance

# ``from flaghunter.interface import main`` resolves to main() via the package's
# lazy __getattr__; import the submodule explicitly.
main_mod = importlib.import_module("flaghunter.interface.main")


def _seed_provenance(tmp_path):
    provenance.set_provenance_file(tmp_path / "provenance.jsonl")
    # two runs sharing an a→b sequence, the second ending in a flag
    provenance.record_call_sync(tool_name="a", run_id="r1")
    provenance.record_call_sync(tool_name="b", run_id="r1")
    provenance.record_call_sync(tool_name="a", run_id="r2")
    provenance.record_call_sync(tool_name="b", run_id="r2", found_flag=True)


def test_chains_subcommand_registered():
    sys_argv = ["flaghunter", "chains", "--json", "--top", "3"]
    old = sys.argv
    sys.argv = sys_argv
    try:
        _, args = main_mod.parse_arguments()
    finally:
        sys.argv = old
    assert args.command == "chains"
    assert args.json is True
    assert args.top == 3


def test_handle_chains_command_text_output(tmp_path, capsys):
    _seed_provenance(tmp_path)
    try:
        main_mod.handle_chains_command(Namespace(json=False, top=10))
        out = capsys.readouterr().out
        assert "Emergent tool-chain report" in out
        assert "a → b" in out
    finally:
        provenance.clear()


def test_handle_chains_command_json_output(tmp_path, capsys):
    _seed_provenance(tmp_path)
    try:
        main_mod.handle_chains_command(Namespace(json=True, top=10))
        out = capsys.readouterr().out
        report = json.loads(out)
        assert report["summary"]["total_runs"] == 2
        assert report["summary"]["flag_runs"] == 1
        chains = {tuple(c["chain"]) for c in report["chains"]}
        assert ("a", "b") in chains
    finally:
        provenance.clear()


def test_handle_chains_command_empty_log(tmp_path, capsys):
    provenance.set_provenance_file(tmp_path / "empty.jsonl")
    try:
        main_mod.handle_chains_command(Namespace(json=False, top=10))
        out = capsys.readouterr().out
        assert "No recurring chains yet" in out
    finally:
        provenance.clear()
