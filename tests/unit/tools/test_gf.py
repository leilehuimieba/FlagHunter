"""Tests for the gf (pattern matcher) tool."""

import asyncio
from unittest.mock import patch

import pytest

from pentestagent.tools.gf import gf, _BUILTIN_PATTERNS


class TestBuiltinPatternsExist:
    def test_all_expected_patterns(self):
        expected = {
            "ssrf", "sqli", "rce", "lfi", "redirect",
            "aws-keys", "s3-buckets", "base64", "api-keys",
            "jwt", "ip", "email", "interesting",
        }
        assert set(_BUILTIN_PATTERNS.keys()) == expected

    def test_patterns_are_compiled_regex(self):
        for name, regex in _BUILTIN_PATTERNS.items():
            assert hasattr(regex, "finditer"), f"{name} is not a compiled regex"


class TestGfAllPatterns:
    def test_empty_text(self):
        result = asyncio.run(gf({"text": ""}, None))
        assert "Error: text is required" in result

    def test_no_matches(self):
        result = asyncio.run(gf({"text": "hello world foo bar", "pattern": "all"}, None))
        assert "No matches found" in result

    def test_ssrf_pattern(self):
        text = "url=https://internal.com/api&target=http://127.0.0.1/admin"
        result = asyncio.run(gf({"text": text, "pattern": "ssrf"}, None))
        assert "[ssrf]" in result
        assert "https://internal.com/api" in result
        assert "http://127.0.0.1/admin" in result

    def test_sqli_pattern(self):
        text = "id=1' OR '1'='1&username=admin'--&password=123"
        result = asyncio.run(gf({"text": text, "pattern": "sqli"}, None))
        assert "[sqli]" in result
        assert "id=1'" in result  # sqli regex stops at whitespace, captures param prefix

    def test_rce_pattern(self):
        text = "cmd=whoami&exec=cat /etc/passwd&shell=bash -c 'id'"
        result = asyncio.run(gf({"text": text, "pattern": "rce"}, None))
        assert "[rce]" in result
        assert "whoami" in result

    def test_lfi_pattern(self):
        text = "file=../../../etc/passwd&path=/var/www/html/config.php"
        result = asyncio.run(gf({"text": text, "pattern": "lfi"}, None))
        assert "[lfi]" in result
        assert "../../../etc/passwd" in result

    def test_redirect_pattern(self):
        text = "redirect=https://evil.com&return_url=/admin&next=/dashboard"
        result = asyncio.run(gf({"text": text, "pattern": "redirect"}, None))
        assert "[redirect]" in result
        assert "https://evil.com" in result

    def test_aws_keys_pattern(self):
        text = "AKIAIOSFODNN7EXAMPLE some text ASIAIOSFODNN7EXAMPLE"
        result = asyncio.run(gf({"text": text, "pattern": "aws-keys"}, None))
        assert "[aws-keys]" in result
        assert "AKIAIOSFODNN7EXAMPLE" in result

    def test_s3_buckets_pattern(self):
        text = "my-bucket.s3.amazonaws.com s3://backup-bucket"
        result = asyncio.run(gf({"text": text, "pattern": "s3-buckets"}, None))
        assert "[s3-buckets]" in result
        assert "my-bucket.s3.amazonaws.com" in result

    def test_base64_pattern(self):
        text = "dGVzdGluZyBiYXNlNjQgZW5jb2Rpbmcgd2l0aCBzb21lIGRhdGE="  # 40+ chars
        result = asyncio.run(gf({"text": text, "pattern": "base64"}, None))
        assert "[base64]" in result
        assert "dGVzdGluZyBiYXNlNjQgZW5jb2Rpbmc" in result

    def test_api_keys_pattern(self):
        text = 'api_key: "sk-abc123def456ghi789" \n Authorization: bearer abcdef123456'
        result = asyncio.run(gf({"text": text, "pattern": "api-keys"}, None))
        assert "[api-keys]" in result

    def test_jwt_pattern(self):
        text = "Authorization: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.SflKxw"
        result = asyncio.run(gf({"text": text, "pattern": "jwt"}, None))
        assert "[jwt]" in result
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" in result

    def test_ip_pattern(self):
        text = "Server at 192.168.1.1 and 10.0.0.1, also ::1 and 2001:0db8::1"
        result = asyncio.run(gf({"text": text, "pattern": "ip"}, None))
        assert "[ip]" in result
        assert "192.168.1.1" in result

    def test_email_pattern(self):
        text = "Contact admin@example.com or support@company.co.uk"
        result = asyncio.run(gf({"text": text, "pattern": "email"}, None))
        assert "[email]" in result
        assert "admin@example.com" in result
        assert "support@company.co.uk" in result

    def test_interesting_pattern(self):
        text = "found .git/config and phpinfo.php, also flag{test123}"
        result = asyncio.run(gf({"text": text, "pattern": "interesting"}, None))
        assert "[interesting]" in result
        assert ".git" in result or "flag{" in result

    def test_all_patterns_combined(self):
        text = (
            "url=https://evil.com&id=1' OR '1'='1&cmd=whoami&file=/etc/passwd"
            "&redirect=https://evil.com&AKIAIOSFODNN7EXAMPLE&mybucket.s3.amazonaws.com"
            "&eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.SflKxw"
            "&192.168.1.1&admin@test.com&.git/config"
        )
        result = asyncio.run(gf({"text": text, "pattern": "all"}, None))
        # Should match at least several patterns
        found_patterns = []
        for name in _BUILTIN_PATTERNS:
            if f"[{name}]" in result:
                found_patterns.append(name)
        assert len(found_patterns) >= 5, f"Expected >=5 patterns, found {found_patterns}"


class TestGfEdgeCases:
    def test_unknown_pattern(self):
        result = asyncio.run(gf({"text": "hello", "pattern": "nonexistent"}, None))
        assert "Unknown pattern" in result
        assert "nonexistent" in result

    def test_max_results_truncation(self):
        # Generate 100 IPs
        text = " ".join(f"192.168.1.{i}" for i in range(100))
        result = asyncio.run(gf({"text": text, "pattern": "ip", "max_results": 10}, None))
        # Should show 10 matches + "... and X more"
        lines = result.splitlines()
        match_lines = [l for l in lines if l.strip().startswith("-")]
        # First 20 displayed in output, but max_results=10 means only 10 collected
        assert "10 matches" in result

    def test_long_match_truncation(self):
        # A single base64 string >200 chars (no '=' in the middle)
        text = "A" * 300  # 300 'A's is valid base64-ish and >200 chars
        result = asyncio.run(gf({"text": text, "pattern": "base64"}, None))
        assert "..." in result  # truncated with ellipsis since match >200 chars

    def test_deduplication(self):
        text = "url=https://example.com url=https://example.com url=https://example.com"
        result = asyncio.run(gf({"text": text, "pattern": "ssrf"}, None))
        # Should only show 1 match despite 3 occurrences
        assert "1 matches" in result or "1 match" in result

    def test_case_insensitive_pattern_names(self):
        text = "192.168.1.1"
        result = asyncio.run(gf({"text": text, "pattern": "IP"}, None))
        assert "[ip]" in result

        result = asyncio.run(gf({"text": text, "pattern": "Ip"}, None))
        assert "[ip]" in result

    def test_default_pattern_is_all(self):
        text = "192.168.1.1 admin@test.com"
        result = asyncio.run(gf({"text": text}, None))
        assert "[ip]" in result
        assert "[email]" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
