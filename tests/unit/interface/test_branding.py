"""Branding guards for the FlagHunter rename."""

from __future__ import annotations

import inspect
import importlib
import sys

import pytest

from flaghunter.config.constants import APP_NAME, APP_VERSION
from flaghunter.interface import cli, utils

main_module = importlib.import_module("flaghunter.interface.main")


def test_version_flag_uses_flaghunter_name_and_app_version(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["flaghunter", "--version"])

    with pytest.raises(SystemExit) as raised:
        main_module.parse_arguments()

    output = capsys.readouterr().out
    assert raised.value.code == 0
    assert output.strip() == f"{APP_NAME} {APP_VERSION}"
    assert "PentestAgent" not in output
    assert "PENTESTAGENT" not in output


def test_cli_startup_panel_uses_flaghunter_brand():
    source = inspect.getsource(cli.run_cli)

    assert '"FLAGHUNTER"' in source
    assert "PENTESTAGENT" not in source


def test_text_banner_uses_flaghunter_brand_and_version():
    source = inspect.getsource(utils.print_banner)

    assert "FLAGHUNTER" in source
    assert "PENTESTAGENT" not in source
    assert "APP_VERSION" in source
