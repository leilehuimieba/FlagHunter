"""
模块开关测试
覆盖: TC-M1-024
"""

import pytest
import os
from unittest.mock import patch

from cpa_modules.m1_api_hub import is_m1_enabled, init_m1


class TestTCM1024:
    """TC-M1-024: 模块开关（CPA_M1_API_HUB=false时不加载）"""

    @patch.dict(os.environ, {"CPA_M1_API_HUB": "false"})
    def test_module_disabled(self):
        """CPA_M1_API_HUB=false时模块不加载"""
        assert is_m1_enabled() is False

    @patch.dict(os.environ, {"CPA_M1_API_HUB": "false"})
    def test_init_returns_none_when_disabled(self):
        """禁用时init_m1应返回None"""
        result = init_m1()
        assert result is None

    @patch.dict(os.environ, {"CPA_M1_API_HUB": "true"})
    def test_module_enabled(self):
        """CPA_M1_API_HUB=true时模块正常加载"""
        assert is_m1_enabled() is True

    @patch.dict(os.environ, {"CPA_M1_API_HUB": "1"})
    def test_module_enabled_numeric_one(self):
        """数值1也视为启用"""
        assert is_m1_enabled() is True

    @patch.dict(os.environ, {"CPA_M1_API_HUB": "0"})
    def test_module_disabled_numeric_zero(self):
        """数值0也视为禁用"""
        assert is_m1_enabled() is False

    @patch.dict(os.environ, {"CPA_M1_API_HUB": "True"})
    def test_module_enabled_case_insensitive(self):
        """大小写不敏感"""
        assert is_m1_enabled() is True

    @patch.dict(os.environ, {"CPA_M1_API_HUB": "FALSE"})
    def test_module_disabled_case_insensitive(self):
        """大小写不敏感"""
        assert is_m1_enabled() is False

    def test_module_default_enabled(self):
        """默认情况下（无环境变量）应启用"""
        # 先清除环境变量
        with patch.dict(os.environ, {}, clear=True):
            # 注意：需要确保CPA_M1_API_HUB不在环境中
            if "CPA_M1_API_HUB" in os.environ:
                del os.environ["CPA_M1_API_HUB"]
            assert is_m1_enabled() is True  # 默认true

    @patch.dict(os.environ, {"CPA_M1_API_HUB": "false"})
    def test_no_side_effects_when_disabled(self):
        """禁用时init_m1不应有副作用"""
        # 确保即使被测代码有问题也不会真的初始化
        result = init_m1()
        assert result is None
        # 不应抛出异常
