"""Tests for the katana tool."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from flaghunter.tools.katana import katana


class TestKatana:
    @patch("flaghunter.tools.katana.find_tool")
    def test_empty_url(self, mock_find):
        mock_find.return_value = "/usr/bin/katana"
        result = asyncio.run(katana({"url": ""}, None))
        assert "Error: url is required" in result

    @patch("flaghunter.tools.katana.find_tool")
    def test_binary_not_found(self, mock_find):
        mock_find.return_value = None
        result = asyncio.run(katana({"url": "https://example.com"}, None))
        assert "not installed" in result

    @patch("flaghunter.tools.katana.find_tool")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_successful_crawl(self, mock_remove, mock_exists, mock_find):
        mock_find.return_value = "/usr/bin/katana"
        mock_exists.return_value = True

        file_content = (
            '{"url":"https://example.com/","path":"/"}\n'
            '{"url":"https://example.com/api/users","path":"/api/users","params":["id","page"]}\n'
            '{"url":"https://example.com/app.js","path":"/app.js"}\n'
            '{"url":"https://example.com/login","path":"/login","type":"form","params":["username","password"]}\n'
        )
        mopen = mock_open(read_data=file_content)

        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

        with patch("builtins.open", mopen):
            result = asyncio.run(katana({"url": "https://example.com", "depth": 2}, runtime))
        assert "Katana Crawl Results for https://example.com" in result
        assert "Total Endpoints: 4" in result
        assert "JS Files: 1" in result
        assert "Forms Detected: 1" in result
        assert "Unique Parameters: 4" in result
        assert "https://example.com/api/users" in result
        assert "https://example.com/app.js" in result

    @patch("flaghunter.tools.katana.find_tool")
    def test_execution_failure_no_output(self, mock_find):
        mock_find.return_value = "/usr/bin/katana"
        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(
            exit_code=1, stdout="", stderr="connection refused"
        ))

        with patch("os.path.exists", return_value=False):
            result = asyncio.run(katana({"url": "https://dead.com"}, runtime))
        assert "Katana execution failed" in result
        assert "connection refused" in result

    @patch("flaghunter.tools.katana.find_tool")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_json_decode_error_ignored(self, mock_remove, mock_exists, mock_find):
        mock_find.return_value = "/usr/bin/katana"
        mock_exists.return_value = True

        file_content = (
            '{"url":"https://example.com/","path":"/"}\n'
            'not valid json\n'
            '{"url":"https://example.com/page","path":"/page"}\n'
        )
        mopen = mock_open(read_data=file_content)

        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

        with patch("builtins.open", mopen):
            result = asyncio.run(katana({"url": "https://example.com"}, runtime))
        assert "Total Endpoints: 2" in result

    @patch("flaghunter.tools.katana.find_tool")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_js_render_and_headless_flags(self, mock_remove, mock_exists, mock_find):
        mock_find.return_value = "/usr/bin/katana"
        mock_exists.return_value = True

        mopen = mock_open(read_data="")
        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

        with patch("builtins.open", mopen):
            asyncio.run(katana({
                "url": "https://example.com",
                "js_render": True,
                "headless": True,
                "scope": "subdomain",
                "output_fields": "url,path,host",
            }, runtime))

        call_args = runtime.execute_command.call_args
        cmd = call_args[0][0]
        assert "-jc" in cmd
        assert "-headless" in cmd
        assert "-scope subdomain" in cmd
        assert "-f url,path,host" in cmd

    @patch("flaghunter.tools.katana.find_tool")
    @patch("os.path.exists")
    def test_file_read_exception(self, mock_exists, mock_find):
        mock_find.return_value = "/usr/bin/katana"
        mock_exists.return_value = True

        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="output", stderr=""))

        with patch("builtins.open", side_effect=IOError("permission denied")):
            result = asyncio.run(katana({"url": "https://example.com"}, runtime))
        assert "Error parsing katana output" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
