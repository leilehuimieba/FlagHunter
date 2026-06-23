"""Tests for flaghunter.llm.config."""

import pytest

from flaghunter.llm.config import ModelConfig


class TestModelConfigDefaults:
    def test_temperature_default_range(self):
        cfg = ModelConfig()
        assert 0.0 <= cfg.temperature <= 2.0

    def test_max_tokens_positive(self):
        cfg = ModelConfig()
        assert cfg.max_tokens > 0

    def test_top_p_range(self):
        cfg = ModelConfig()
        assert 0.0 <= cfg.top_p <= 1.0

    def test_max_context_tokens_positive(self):
        cfg = ModelConfig()
        assert cfg.max_context_tokens > 0

    def test_max_retries_positive(self):
        cfg = ModelConfig()
        assert cfg.max_retries > 0

    def test_retry_delay_positive(self):
        cfg = ModelConfig()
        assert cfg.retry_delay > 0

    def test_timeout_positive(self):
        cfg = ModelConfig()
        assert cfg.timeout > 0


class TestModelConfigToDict:
    def test_to_dict_has_required_keys(self):
        cfg = ModelConfig()
        d = cfg.to_dict()
        assert "temperature" in d
        assert "max_tokens" in d
        assert "top_p" in d

    def test_to_dict_values_match(self):
        cfg = ModelConfig(temperature=0.5, max_tokens=1024)
        d = cfg.to_dict()
        assert d["temperature"] == 0.5
        assert d["max_tokens"] == 1024

    def test_to_dict_does_not_include_context_tokens(self):
        cfg = ModelConfig()
        d = cfg.to_dict()
        assert "max_context_tokens" not in d

    def test_to_dict_does_not_include_retry_settings(self):
        cfg = ModelConfig()
        d = cfg.to_dict()
        assert "max_retries" not in d
        assert "retry_delay" not in d
