"""Tests for the httpx_probe tool."""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from flaghunter.tools.httpx_probe import (
    _build_base_args,
    _probe_single,
    _run_httpx,
    _summarize,
    httpx_probe,
)


class TestBuildBaseArgs:
    def test_defaults(self):
        args = _build_base_args()
        assert "-json" in args
        assert "-no-color" in args
        assert "-threads" in args
        assert "50" in args
        assert "-timeout" in args
        assert "5" in args
        assert "-retries" in args
        assert "1" in args

    def test_with_ports(self):
        args = _build_base_args(ports="80,443")
        assert "-ports" in args
        assert "80,443" in args

    def test_no_redirects(self):
        args = _build_base_args(follow_redirects=False)
        assert "-follow-redirects" not in args

    def test_threads_override(self):
        args = _build_base_args(threads=100)
        assert "100" in args


class TestSummarize:
    def test_empty_entries(self):
        result = _summarize([])
        assert result["alive_count"] == 0
        assert result["dead_count"] == 0

    def test_single_alive(self):
        entries = [
            {
                "url": "https://example.com",
                "status_code": 200,
                "title": "Example Domain",
                "technologies": ["Nginx", "PHP"],
                "webserver": "nginx",
                "time": "12ms",
            }
        ]
        result = _summarize(entries)
        assert result["alive_count"] == 1
        assert result["dead_count"] == 0
        assert result["technologies_found"] == ["Nginx", "PHP"]
        assert result["web_servers"] == {"nginx": 1}
        assert result["status_codes"] == {200: 1}
        assert len(result["page_titles"]) == 1

    def test_mixed_alive_and_dead(self):
        entries = [
            {"url": "https://alive.com", "status_code": 200},
            {"url": "https://dead.com", "status_code": 0},
        ]
        result = _summarize(entries)
        assert result["alive_count"] == 1
        assert result["dead_count"] == 1
        assert "https://alive.com" in result["alive"]
        assert "https://dead.com" in result["dead"]

    def test_tls_extraction(self):
        entries = [
            {
                "url": "https://secure.com",
                "status_code": 200,
                "tls": {
                    "subject_name": "CN=secure.com",
                    "issuer_name": "C=US, O=Let's Encrypt",
                    "not_after": "2027-01-01",
                    "subject_an": ["secure.com", "www.secure.com"],
                },
            }
        ]
        result = _summarize(entries)
        assert len(result["tls_certificates"]) == 1
        cert = result["tls_certificates"][0]
        assert cert["subject"] == "CN=secure.com"
        assert cert["sans"] == ["secure.com", "www.secure.com"]

    def test_limit_truncation(self):
        entries = [{"url": f"https://site{i}.com", "status_code": 200} for i in range(100)]
        result = _summarize(entries)
        assert result["alive_count"] == 100
        assert len(result["alive"]) == 50


class TestHttpxProbe:
    @patch("flaghunter.tools.httpx_probe.find_tool")
    def test_binary_not_found(self, mock_find):
        mock_find.return_value = None
        result = asyncio.run(httpx_probe({"target": "https://example.com"}, None))
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "not found" in parsed["message"]

    @patch("flaghunter.tools.httpx_probe.find_tool")
    @patch("flaghunter.tools.httpx_probe._run_httpx")
    def test_single_mode_alive(self, mock_run, mock_find):
        mock_find.return_value = "/usr/bin/httpx"
        mock_run.return_value = [
            {
                "url": "https://example.com",
                "status_code": 200,
                "title": "Example",
                "webserver": "nginx",
                "technologies": ["Nginx"],
                "content_type": "text/html",
                "content_length": 1256,
                "time": "15ms",
                "cnames": [],
                "chain_status_codes": [301, 200],
            }
        ]
        result = asyncio.run(httpx_probe({"target": "https://example.com", "mode": "single"}, None))
        parsed = json.loads(result)
        assert parsed["status"] == "alive"
        assert parsed["status_code"] == 200
        assert parsed["title"] == "Example"
        assert parsed["technologies"] == ["Nginx"]

    @patch("flaghunter.tools.httpx_probe.find_tool")
    @patch("flaghunter.tools.httpx_probe._run_httpx")
    def test_single_mode_dead(self, mock_run, mock_find):
        mock_find.return_value = "/usr/bin/httpx"
        mock_run.return_value = []
        result = asyncio.run(httpx_probe({"target": "https://dead.com", "mode": "single"}, None))
        parsed = json.loads(result)
        assert parsed["status"] == "dead"

    @patch("flaghunter.tools.httpx_probe.find_tool")
    @patch("flaghunter.tools.httpx_probe._run_httpx")
    def test_batch_mode(self, mock_run, mock_find):
        mock_find.return_value = "/usr/bin/httpx"
        mock_run.return_value = [
            {"url": "https://a.com", "status_code": 200, "webserver": "nginx"},
            {"url": "https://b.com", "status_code": 200, "webserver": "apache"},
        ]
        result = asyncio.run(httpx_probe(
            {"target": "https://a.com,https://b.com", "mode": "batch", "threads": 10},
            None,
        ))
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["targets_scanned"] == 2
        assert parsed["alive_count"] == 2
        assert parsed["web_servers"] == {"nginx": 1, "apache": 1}

    @patch("flaghunter.tools.httpx_probe.find_tool")
    def test_invalid_mode(self, mock_find):
        mock_find.return_value = "/usr/bin/httpx"
        result = asyncio.run(httpx_probe({"target": "https://example.com", "mode": "invalid"}, None))
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "Unknown mode" in parsed["message"]

    @patch("flaghunter.tools.httpx_probe.find_tool")
    def test_empty_targets(self, mock_find):
        mock_find.return_value = "/usr/bin/httpx"
        result = asyncio.run(httpx_probe({"target": ""}, None))
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "No target" in parsed["message"]

    @patch("flaghunter.tools.httpx_probe.find_tool")
    @patch("flaghunter.tools.httpx_probe._run_httpx")
    def test_include_response(self, mock_run, mock_find):
        mock_find.return_value = "/usr/bin/httpx"
        mock_run.return_value = [
            {
                "url": "https://example.com",
                "status_code": 200,
                "header": {"Server": "nginx"},
            }
        ]
        result = asyncio.run(httpx_probe(
            {"target": "https://example.com", "mode": "single", "include_response": True},
            None,
        ))
        parsed = json.loads(result)
        assert "headers" in parsed
        assert parsed["headers"]["Server"] == "nginx"

    @patch("flaghunter.tools.httpx_probe.find_tool")
    @patch("flaghunter.tools.httpx_probe._run_httpx")
    def test_tls_in_single_mode(self, mock_run, mock_find):
        mock_find.return_value = "/usr/bin/httpx"
        mock_run.return_value = [
            {
                "url": "https://example.com",
                "status_code": 200,
                "tls": {
                    "subject_name": "CN=example.com",
                    "issuer_name": "C=US",
                    "not_before": "2026-01-01",
                    "not_after": "2027-01-01",
                    "subject_an": ["example.com"],
                },
            }
        ]
        result = asyncio.run(httpx_probe({"target": "https://example.com", "mode": "single"}, None))
        parsed = json.loads(result)
        assert "tls" in parsed
        assert parsed["tls"]["subject"] == "CN=example.com"


class TestProbeSingle:
    @patch("flaghunter.tools.httpx_probe.find_tool")
    @patch("flaghunter.tools.httpx_probe._run_httpx")
    def test_run_failure_returns_error(self, mock_run, mock_find):
        mock_find.return_value = "/usr/bin/httpx"
        mock_run.return_value = None
        result = _probe_single("https://example.com")
        assert result["status"] == "error"


class TestRunHttpx:
    @patch("flaghunter.tools.httpx_probe.find_tool")
    @patch("subprocess.run")
    def test_success(self, mock_subprocess, mock_find):
        mock_find.return_value = "/usr/bin/httpx"
        mock_subprocess.return_value = MagicMock(
            stdout='{"url":"https://a.com","status_code":200}\n{"url":"https://b.com","status_code":0}\n',
            stderr="",
        )
        result = _run_httpx(["https://a.com", "https://b.com"], ["-json"])
        assert len(result) == 2
        assert result[0]["status_code"] == 200
        assert result[1]["status_code"] == 0

    @patch("flaghunter.tools.httpx_probe.find_tool")
    def test_binary_not_found(self, mock_find):
        mock_find.return_value = None
        result = _run_httpx(["https://example.com"], [])
        assert result is None

    @patch("flaghunter.tools.httpx_probe.find_tool")
    @patch("subprocess.run")
    def test_timeout(self, mock_subprocess, mock_find):
        import subprocess as sp
        mock_find.return_value = "/usr/bin/httpx"
        mock_subprocess.side_effect = sp.TimeoutExpired("httpx", 120)
        result = _run_httpx(["https://example.com"], [])
        assert result is None

    @patch("flaghunter.tools.httpx_probe.find_tool")
    @patch("subprocess.run")
    def test_invalid_json_lines_ignored(self, mock_subprocess, mock_find):
        mock_find.return_value = "/usr/bin/httpx"
        mock_subprocess.return_value = MagicMock(
            stdout='{"url":"https://a.com","status_code":200}\nnot json\n',
            stderr="",
        )
        result = _run_httpx(["https://a.com"], ["-json"])
        assert len(result) == 1
        assert result[0]["url"] == "https://a.com"

    @patch("flaghunter.tools.httpx_probe.find_tool")
    @patch("subprocess.run")
    def test_cleanup_on_exception(self, mock_subprocess, mock_find):
        mock_find.return_value = "/usr/bin/httpx"
        mock_subprocess.side_effect = Exception("boom")
        result = _run_httpx(["https://example.com"], [])
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
