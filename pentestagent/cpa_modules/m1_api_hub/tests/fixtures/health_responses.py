"""
健康检查Mock响应数据

用于模拟litellm.acompletion在不同场景下的返回值
"""

import asyncio

# ========== 成功响应 ==========

HEALTH_RESPONSE_OK = {
    "choices": [{"message": {"content": "OK"}}],
    "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}
}

HEALTH_RESPONSE_OK_VERBOSE = {
    "choices": [{"message": {"content": "OK, I'm here and responding normally."}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 8, "total_tokens": 13}
}

# ========== 慢响应（用于degraded测试） ==========

# 通过side_effect中的asyncio.sleep模拟慢响应

# ========== 异常响应 ==========

TIMEOUT_ERROR = asyncio.TimeoutError("Request timeout after 10 seconds")
CONNECTION_ERROR = ConnectionError("Connection refused by peer")
AUTH_ERROR = Exception("401 Unauthorized: Invalid API key")
RATE_LIMIT_ERROR = Exception("429 Rate limit exceeded")

# ========== 连续失败序列 ==========

FAIL_SEQUENCE_3X = [TIMEOUT_ERROR, TIMEOUT_ERROR, TIMEOUT_ERROR]
FAIL_SEQUENCE_2X_THEN_OK = [TIMEOUT_ERROR, TIMEOUT_ERROR, HEALTH_RESPONSE_OK]

# ========== 恢复序列 ==========

RECOVER_SEQUENCE_2X_OK = [HEALTH_RESPONSE_OK, HEALTH_RESPONSE_OK]
RECOVER_SEQUENCE_2X_OK_THEN_FAIL = [HEALTH_RESPONSE_OK, HEALTH_RESPONSE_OK, TIMEOUT_ERROR]

# ========== 状态转换测试数据 ==========

STATE_TRANSITION_MATRIX = [
    # (当前状态, 检查结果, 连续失败次数, 预期新状态)
    ("healthy", "success", 0, "healthy"),
    ("healthy", "timeout", 1, "degraded"),
    ("healthy", "timeout", 2, "degraded"),
    ("healthy", "timeout", 3, "down"),
    ("degraded", "success", 0, "healthy"),
    ("degraded", "timeout", 1, "degraded"),
    ("down", "success", 0, "down"),      # 需要连续2次成功
    ("down", "success", 1, "recovering"),  # 连续2次成功进入recovering
    ("recovering", "real_request_ok", 0, "healthy"),
    ("recovering", "real_request_fail", 0, "down"),
]
