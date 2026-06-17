"""
M1模块测试共享Fixtures和Mock

提供:
- 虚拟Provider配置
- Mock的litellm.acompletion
- Mock的健康检查响应
- 模拟的CostTracker状态
"""

import pytest
import os
import sys
from datetime import datetime
from unittest.mock import Mock, MagicMock, AsyncMock, patch

# 将项目根目录加入路径
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

# ========== 数据模型Mock（当models.py不存在时使用） ==========

class MockProviderConfig:
    """ProviderConfig数据模型的Mock实现"""
    def __init__(self, id, name, model, api_base, api_key, timeout=30,
                 max_retries=3, rpm_limit=60, tpm_limit=100000,
                 priority=1, enabled=True, is_backup=False):
        self.id = id
        self.name = name
        self.model = model
        self.api_base = api_base
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self.priority = priority
        self.enabled = enabled
        self.is_backup = is_backup

    def __eq__(self, other):
        if isinstance(other, MockProviderConfig):
            return self.id == other.id
        return False

    def __repr__(self):
        return f"ProviderConfig(id={self.id}, name={self.name}, priority={self.priority})"


class MockProviderStatus:
    """ProviderStatus数据模型的Mock实现"""
    def __init__(self, provider_id, state="healthy", last_check_time=None,
                 last_error="", response_time_ms=0, consecutive_failures=0,
                 total_requests=0, total_tokens=0, estimated_cost_usd=0.0,
                 consecutive_successes=0):
        self.provider_id = provider_id
        self.state = state
        self.last_check_time = last_check_time or datetime.now()
        self.last_error = last_error
        self.response_time_ms = response_time_ms
        self.consecutive_failures = consecutive_failures
        self.consecutive_successes = consecutive_successes
        self.total_requests = total_requests
        self.total_tokens = total_tokens
        self.estimated_cost_usd = estimated_cost_usd


class MockRequestLog:
    """RequestLog数据模型的Mock实现"""
    def __init__(self, request_id, provider_id, model, prompt_tokens,
                 completion_tokens, response_time_ms, success=True,
                 error_message="", timestamp=None, cost_usd=0.0):
        self.request_id = request_id
        self.provider_id = provider_id
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.response_time_ms = response_time_ms
        self.success = success
        self.error_message = error_message
        self.timestamp = timestamp or datetime.now()
        self.cost_usd = cost_usd


# ========== Fixtures ==========

@pytest.fixture
def provider_config_factory():
    """ProviderConfig工厂函数"""
    def _make(idx=0, **overrides):
        defaults = {
            "id": f"test_provider_{idx}",
            "name": f"测试Provider-{idx}",
            "model": "openai/gpt-4",
            "api_base": f"https://api.test{idx}.com/v1",
            "api_key": f"sk-test-key-{idx}",
            "timeout": 30,
            "priority": idx + 1,
            "enabled": True,
            "is_backup": False,
        }
        defaults.update(overrides)
        return MockProviderConfig(**defaults)
    return _make


@pytest.fixture
def mock_provider_a():
    """Provider A - 主渠道，priority=1"""
    return MockProviderConfig(
        id="zhongzhuan_a_claude",
        name="中转站A-Claude",
        model="openai/claude-sonnet-4",
        api_base="https://api.zhongzhuan-a.com/v1",
        api_key="sk-test-key-a-12345",
        timeout=30,
        priority=1,
        enabled=True,
        is_backup=False,
    )


@pytest.fixture
def mock_provider_b():
    """Provider B - 备用渠道，priority=2"""
    return MockProviderConfig(
        id="zhongzhuan_b_claude",
        name="中转站B-Claude",
        model="openai/claude-sonnet-4",
        api_base="https://api.zhongzhuan-b.com/v1",
        api_key="sk-test-key-b-67890",
        timeout=30,
        priority=2,
        enabled=True,
        is_backup=True,
    )


@pytest.fixture
def mock_provider_c():
    """Provider C - GPT4，priority=3"""
    return MockProviderConfig(
        id="zhongzhuan_a_gpt4",
        name="中转站A-GPT4",
        model="openai/gpt-4",
        api_base="https://api.zhongzhuan-a.com/v1",
        api_key="sk-test-key-a-12345",
        timeout=45,
        priority=3,
        enabled=True,
    )


@pytest.fixture
def mock_provider_d():
    """Provider D - DeepSeek，priority=4"""
    return MockProviderConfig(
        id="deepseek_official",
        name="DeepSeek官方",
        model="deepseek/deepseek-chat",
        api_base="https://api.deepseek.com/v1",
        api_key="sk-test-key-deep-abcde",
        timeout=60,
        priority=4,
        enabled=True,
    )


@pytest.fixture
def mock_provider_e():
    """Provider E - 官方Claude，priority=5"""
    return MockProviderConfig(
        id="official_claude",
        name="官方-Claude",
        model="anthropic/claude-3-sonnet",
        api_base="https://api.anthropic.com/v1",
        api_key="sk-test-key-ant-fghij",
        timeout=30,
        priority=5,
        enabled=True,
    )


@pytest.fixture
def all_test_providers(mock_provider_a, mock_provider_b, mock_provider_c,
                       mock_provider_d, mock_provider_e):
    """5个测试Provider的完整列表"""
    return [mock_provider_a, mock_provider_b, mock_provider_c,
            mock_provider_d, mock_provider_e]


@pytest.fixture
def mock_litellm_response_ok():
    """litellm.acompletion成功响应"""
    return {
        "choices": [{"message": {"content": "OK"}}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}
    }


@pytest.fixture
def mock_litellm_response_slow():
    """litellm.acompletion慢响应（响应时间>5s）"""
    return {
        "choices": [{"message": {"content": "OK... eventually"}}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
    }


@pytest.fixture
def mock_request_logs():
    """10条测试请求日志"""
    logs = []
    for i in range(10):
        logs.append(MockRequestLog(
            request_id=f"req-{i:03d}",
            provider_id="provider_a" if i < 6 else "provider_b",
            model="gpt-4" if i < 6 else "claude-3",
            prompt_tokens=1000 + i * 100,
            completion_tokens=500,
            response_time_ms=1000 + i * 50,
            success=True,
            error_message="",
            timestamp=datetime.now(),
            cost_usd=0.02 + i * 0.005
        ))
    return logs


# ========== Mock litellm 模块（如果不存在） ==========

@pytest.fixture(autouse=True)
def mock_litellm_module():
    """自动Mock litellm模块（如果未安装）"""
    if "litellm" not in sys.modules:
        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock()
        sys.modules["litellm"] = mock_litellm
    yield
