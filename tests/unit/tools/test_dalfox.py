"""Tests for the dalfox tool."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pentestagent.tools.dalfox import dalfox


class TestDalfox:
    @patch("pentestagent.tools.dalfox.find_tool")
    def test_empty_url(self, mock_find):
        mock_find.return_value = "/usr/bin/dalfox"
        result = asyncio.run(dalfox({"url": ""}, None))
        assert "Error: url is required" in result

    @patch("pentestagent.tools.dalfox.find_tool")
    def test_binary_not_found(self, mock_find):
        mock_find.return_value = None
        result = asyncio.run(dalfox({"url": "https://example.com"}, None))
        assert "not installed" in result

    @patch("pentestagent.tools.dalfox.find_tool")
    @patch("builtins.open")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_no_findings(self, mock_remove, mock_exists, mock_open, mock_find):
        mock_find.return_value = "/usr/bin/dalfox"
        mock_exists.return_value = True

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = ""
        mock_open.return_value = mock_file

        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="clean", stderr=""))

        result = asyncio.run(dalfox({"url": "https://example.com"}, runtime))
        assert "No XSS vulnerabilities detected" in result

    @patch("pentestagent.tools.dalfox.find_tool")
    @patch("builtins.open")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_findings_list_format(self, mock_remove, mock_exists, mock_open, mock_find):
        mock_find.return_value = "/usr/bin/dalfox"
        mock_exists.return_value = True

        findings = [
            {"type": "REFLECTED", "param": "q", "payload": "<script>alert(1)</script>", "severity": "high"},
            {"type": "STORED", "parameter": "comment", "payload": "<img src=x onerror=alert(1)>", "severity": "critical"},
        ]
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = json.dumps(findings)
        mock_open.return_value = mock_file

        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

        result = asyncio.run(dalfox({"url": "https://example.com"}, runtime))
        assert "Dalfox XSS Scan Results for https://example.com" in result
        assert "Findings: 2" in result
        assert "REFLECTED" in result
        assert "STORED" in result
        assert "q" in result
        assert "comment" in result
        assert "<script>alert(1)</script>" in result

    @patch("pentestagent.tools.dalfox.find_tool")
    @patch("builtins.open")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_findings_dict_format(self, mock_remove, mock_exists, mock_open, mock_find):
        mock_find.return_value = "/usr/bin/dalfox"
        mock_exists.return_value = True

        data = {"findings": [{"type": "DOM", "param": "id", "payload": "#<img src=x>", "severity": "medium"}]}
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = json.dumps(data)
        mock_open.return_value = mock_file

        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

        result = asyncio.run(dalfox({"url": "https://example.com"}, runtime))
        assert "DOM" in result
        assert "id" in result

    @patch("pentestagent.tools.dalfox.find_tool")
    @patch("builtins.open")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_findings_jsonl_format(self, mock_remove, mock_exists, mock_open, mock_find):
        mock_find.return_value = "/usr/bin/dalfox"
        mock_exists.return_value = True

        lines = (
            '{"type":"REFLECTED","param":"search","payload":"<svg onload=alert(1)>","severity":"high"}\n'
            '{"type":"BLIND","param":"callback","payload":"//xss.com","severity":"high"}\n'
        )
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = lines
        mock_open.return_value = mock_file

        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

        result = asyncio.run(dalfox({"url": "https://example.com"}, runtime))
        assert "Findings: 2" in result
        assert "BLIND" in result

    @patch("pentestagent.tools.dalfox.find_tool")
    def test_post_method_and_options(self, mock_find):
        mock_find.return_value = "/usr/bin/dalfox"

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = ""

        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

        with patch("builtins.open", return_value=mock_file), \
             patch("os.path.exists", return_value=True), \
             patch("os.remove"):
            result = asyncio.run(dalfox({
                "url": "https://example.com",
                "method": "POST",
                "data": "username=test",
                "cookie": "session=abc123",
                "headers": "X-Custom: value,Authorization: bearer token",
                "blind": "https://xss-callback.com",
                "only_custom_payload": True,
                "waf_evasion": True,
            }, runtime))

        cmd = runtime.execute_command.call_args[0][0]
        assert "--method POST" in cmd
        assert "--data username=test" in cmd
        assert "--cookie session=abc123" in cmd
        assert "--header X-Custom: value" in cmd
        assert "--header Authorization: bearer token" in cmd
        assert "--blind https://xss-callback.com" in cmd
        assert "--only-custom-payload" in cmd
        assert "--waf-evasion" in cmd

    @patch("pentestagent.tools.dalfox.find_tool")
    @patch("builtins.open")
    @patch("os.path.exists")
    def test_file_exception(self, mock_exists, mock_open, mock_find):
        mock_find.return_value = "/usr/bin/dalfox"
        mock_exists.return_value = True
        mock_open.side_effect = IOError("permission denied")

        runtime = MagicMock()
        runtime.execute_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="raw", stderr=""))

        result = asyncio.run(dalfox({"url": "https://example.com"}, runtime))
        assert "Error parsing dalfox output" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
