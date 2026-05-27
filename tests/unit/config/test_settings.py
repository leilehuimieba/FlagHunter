"""Tests for pentestagent.config.settings and related constants."""

import os
from unittest.mock import patch

import pytest

from pentestagent.config.constants import get_openai_api_base
from pentestagent.config.settings import Settings, get_settings, update_settings


class TestGetOpenaiApiBase:
    def test_returns_none_when_not_set(self):
        clean = {k: v for k, v in os.environ.items()
                 if k not in ("OPENAI_API_BASE", "OPENAI_BASE_URL")}
        with patch.dict(os.environ, clean, clear=True):
            assert get_openai_api_base() is None

    def test_reads_openai_api_base(self):
        with patch.dict(os.environ, {"OPENAI_API_BASE": "https://relay.example/v1"}, clear=True):
            assert get_openai_api_base() == "https://relay.example/v1"

    def test_reads_openai_base_url(self):
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://other.example/v1"}, clear=True):
            assert get_openai_api_base() == "https://other.example/v1"

    def test_strips_trailing_slash(self):
        with patch.dict(os.environ, {"OPENAI_API_BASE": "https://relay.example/v1/"}, clear=True):
            assert get_openai_api_base() == "https://relay.example/v1"

    def test_openai_api_base_takes_precedence_over_base_url(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_BASE": "https://primary.example/v1", "OPENAI_BASE_URL": "https://secondary.example"},
            clear=True,
        ):
            assert get_openai_api_base() == "https://primary.example/v1"


class TestSettingsApiBase:
    def test_openai_api_base_is_none_by_default(self):
        clean = {k: v for k, v in os.environ.items()
                 if k not in ("OPENAI_API_BASE", "OPENAI_BASE_URL")}
        with patch.dict(os.environ, clean, clear=True):
            s = Settings()
            assert s.openai_api_base is None

    def test_openai_api_base_from_env(self):
        with patch.dict(os.environ, {"OPENAI_API_BASE": "https://api.example/v1"}, clear=True):
            s = Settings()
            assert s.openai_api_base == "https://api.example/v1"

    def test_openai_api_key_from_env(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai"}):
            s = Settings()
            assert s.openai_api_key == "sk-test-openai"

    def test_anthropic_api_key_from_env(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            s = Settings()
            assert s.anthropic_api_key == "sk-ant-test"

    def test_missing_api_keys_are_none(self):
        clean = {
            k: v
            for k, v in os.environ.items()
            if k not in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
        }
        with patch.dict(os.environ, clean, clear=True):
            s = Settings()
            assert s.openai_api_key is None


class TestGetSettings:
    def test_get_settings_returns_settings_instance(self):
        import pentestagent.config.settings as settings_module
        settings_module._settings = None
        result = get_settings()
        assert isinstance(result, Settings)

    def test_get_settings_returns_singleton(self):
        import pentestagent.config.settings as settings_module
        settings_module._settings = None
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_update_settings_replaces_singleton(self):
        import pentestagent.config.settings as settings_module
        settings_module._settings = None
        s1 = get_settings()
        s2 = update_settings(max_iterations=5)
        assert get_settings() is s2
        assert s2.max_iterations == 5
