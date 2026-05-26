"""Tests for the gau tool."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from pentestagent.tools.gau import gau


class TestGau:
    @patch("pentestagent.tools.gau.find_tool")
    def test_empty_domain(self, mock_find):
        mock_find.return_value = "/usr/bin/gau"
        result = asyncio.run(gau({"domain": ""}, None))
        assert "Error: domain is required" in result

    @patch("pentestagent.tools.gau.find_tool")
    def test_binary_not_found(self, mock_find):
        mock_find.return_value = None
        result = asyncio.run(gau({"domain": "example.com"}, None))
        assert "not installed" in result

    @patch("pentestagent.tools.gau.find_tool")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_successful_scan(self, mock_remove, mock_exists, mock_find):
        mock_find.return_value = "/usr/bin/gau"
        mock_exists.return_value = True

        urls = (
            "https://example.com/\n"
            "https://example.com/api/users?id=1\n"
            "https://example.com/api/users?page=2\n"
            "https://example.com/static/app.js\n"
            "https://example.com/admin/login\n"
            "https://example.com/.env\n"
            "https://example.com/flag.txt\n"
            "https://example.com/graphql\n"
        )
        mopen = mock_open(read_data=urls)

        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

        with patch("builtins.open", mopen):
            result = asyncio.run(gau({"domain": "example.com"}, runtime))
        assert "GAU Historical URL Results for example.com" in result
        assert "Total URLs: 8" in result
        assert "API Endpoints: 3" in result  # /api/users?id=1, /api/users?page=2, /graphql
        assert "JS Files: 1" in result
        assert "Interesting Paths: 3" in result  # admin, .env, flag
        assert "Unique Parameters: 2" in result  # id, page
        assert "https://example.com/admin/login" in result
        assert "https://example.com/static/app.js" in result

    @patch("pentestagent.tools.gau.find_tool")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_no_urls_found(self, mock_remove, mock_exists, mock_find):
        mock_find.return_value = "/usr/bin/gau"
        mock_exists.return_value = True

        mopen = mock_open(read_data="")
        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

        with patch("builtins.open", mopen):
            result = asyncio.run(gau({"domain": "new-domain.com"}, runtime))
        assert "No historical URLs found" in result

    @patch("pentestagent.tools.gau.find_tool")
    def test_custom_options(self, mock_find):
        mock_find.return_value = "/usr/bin/gau"

        mopen = mock_open(read_data="https://example.com/\n")
        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

        with patch("builtins.open", mopen), \
             patch("os.path.exists", return_value=True), \
             patch("os.remove"):
            result = asyncio.run(gau({
                "domain": "example.com",
                "subs": False,
                "providers": "wayback",
                "blacklist": "png,jpg",
                "timeout": 120,
                "max_urls": 100,
            }, runtime))

        cmd = runtime.execute_command.call_args[0][0]
        assert "--subs" not in cmd  # subs=False
        assert "--providers wayback" in cmd
        assert "--blacklist png,jpg" in cmd

    @patch("pentestagent.tools.gau.find_tool")
    def test_default_blacklist(self, mock_find):
        mock_find.return_value = "/usr/bin/gau"

        mopen = mock_open(read_data="https://example.com/\n")
        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

        with patch("builtins.open", mopen), \
             patch("os.path.exists", return_value=True), \
             patch("os.remove"):
            asyncio.run(gau({"domain": "example.com"}, runtime))

        cmd = runtime.execute_command.call_args[0][0]
        assert "--blacklist png,jpg,gif,css,woff,ttf,svg,ico,pdf,zip" in cmd

    @patch("pentestagent.tools.gau.find_tool")
    def test_execution_failure_no_output(self, mock_find):
        mock_find.return_value = "/usr/bin/gau"
        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(
            exit_code=1, stdout="", stderr="connection timeout"
        ))

        with patch("os.path.exists", return_value=False):
            result = asyncio.run(gau({"domain": "dead.com"}, runtime))
        assert "GAU execution failed" in result
        assert "connection timeout" in result

    @patch("pentestagent.tools.gau.find_tool")
    @patch("os.path.exists")
    def test_file_exception(self, mock_exists, mock_find):
        mock_find.return_value = "/usr/bin/gau"
        mock_exists.return_value = True

        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="raw", stderr=""))

        with patch("builtins.open", side_effect=IOError("permission denied")):
            result = asyncio.run(gau({"domain": "example.com"}, runtime))
        assert "Error reading GAU output" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
