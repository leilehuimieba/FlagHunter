"""
Token消耗和成本测试数据

用于测试CostTracker的预算追踪和告警功能
"""

import sys
import os
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

try:
    from flaghunter.cpa_modules.m1_api_hub.models import RequestLog
except ImportError:
    class RequestLog:
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


# ========== 单次请求数据 ==========

SINGLE_SMALL_REQUEST = RequestLog(
    request_id="req-small-001",
    provider_id="zhongzhuan_a_claude",
    model="openai/claude-sonnet-4",
    prompt_tokens=500,
    completion_tokens=200,
    response_time_ms=800,
    success=True,
    error_message="",
    timestamp=datetime.now(),
    cost_usd=0.015,
)

SINGLE_MEDIUM_REQUEST = RequestLog(
    request_id="req-medium-001",
    provider_id="zhongzhuan_a_claude",
    model="openai/claude-sonnet-4",
    prompt_tokens=5000,
    completion_tokens=2000,
    response_time_ms=2500,
    success=True,
    error_message="",
    timestamp=datetime.now(),
    cost_usd=0.15,
)

SINGLE_LARGE_REQUEST = RequestLog(
    request_id="req-large-001",
    provider_id="zhongzhuan_a_claude",
    model="openai/gpt-4",
    prompt_tokens=50000,
    completion_tokens=15000,
    response_time_ms=8000,
    success=True,
    error_message="",
    timestamp=datetime.now(),
    cost_usd=1.95,
)

# 超大请求（用于预算超限测试）
SINGLE_HUGE_REQUEST = RequestLog(
    request_id="req-huge-001",
    provider_id="zhongzhuan_a_gpt4",
    model="openai/gpt-4",
    prompt_tokens=1000000,      # 1M tokens
    completion_tokens=500000,   # 500K tokens
    response_time_ms=30000,
    success=True,
    error_message="",
    timestamp=datetime.now(),
    cost_usd=45.0,              # $45
)

# ========== 会话数据集 ==========

def generate_session_logs(provider_id, count, base_cost=0.02):
    """生成指定Provider的测试请求日志"""
    logs = []
    for i in range(count):
        logs.append(RequestLog(
            request_id=f"{provider_id}-req-{i:03d}",
            provider_id=provider_id,
            model="gpt-4" if "gpt" in provider_id else "claude-3",
            prompt_tokens=1000 + i * 200,
            completion_tokens=300 + i * 50,
            response_time_ms=800 + i * 100,
            success=True,
            error_message="",
            timestamp=datetime.now(),
            cost_usd=base_cost + i * 0.005
        ))
    return logs


# 小型会话：2个Provider，共8次请求，总消耗约$0.34
SESSION_SMALL = {
    "zhongzhuan_a_claude": generate_session_logs("zhongzhuan_a_claude", 5, 0.01),
    "zhongzhuan_b_claude": generate_session_logs("zhongzhuan_b_claude", 3, 0.015),
}

# 中型会话：3个Provider，共25次请求，总消耗约$2.5
SESSION_MEDIUM = {
    "zhongzhuan_a_claude": generate_session_logs("zhongzhuan_a_claude", 12, 0.02),
    "zhongzhuan_b_claude": generate_session_logs("zhongzhuan_b_claude", 8, 0.03),
    "deepseek_official": generate_session_logs("deepseek_official", 5, 0.01),
}

# 大型会话：用于预算告警测试
SESSION_LARGE = {
    "zhongzhuan_a_claude": generate_session_logs("zhongzhuan_a_claude", 50, 0.05),
    "zhongzhuan_b_claude": generate_session_logs("zhongzhuan_b_claude", 30, 0.08),
}

# 计算大型会话总消耗
SESSION_LARGE_TOTAL_COST = sum(
    log.cost_usd
    for provider_logs in SESSION_LARGE.values()
    for log in provider_logs
)  # 约 $8.5


# ========== 预算测试配置 ==========

BUDGET_CONFIGS = [
    # (每日预算, 告警阈值, 当前消耗, 预期告警, 预期暂停)
    {"daily_budget": 50.0, "threshold": 0.8, "spent": 30.0,
     "should_alert": False, "should_pause": False, "description": "正常: 60%已用"},
    {"daily_budget": 50.0, "threshold": 0.8, "spent": 42.0,
     "should_alert": True, "should_pause": False, "description": "告警: 84%已用"},
    {"daily_budget": 50.0, "threshold": 0.8, "spent": 55.0,
     "should_alert": True, "should_pause": True, "description": "暂停: 110%已用"},
    {"daily_budget": 10.0, "threshold": 0.75, "spent": 7.6,
     "should_alert": True, "should_pause": False, "description": "告警: 76%已用"},
    {"daily_budget": 10.0, "threshold": 0.75, "spent": 12.0,
     "should_alert": True, "should_pause": True, "description": "暂停: 120%已用"},
]
