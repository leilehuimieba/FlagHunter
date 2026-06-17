"""
Token追踪与预算管理模块测试
覆盖: TC-M1-017 ~ TC-M1-020
"""

import pytest
import os
from datetime import datetime
from unittest.mock import patch

from flaghunter.cpa_modules.m1_api_hub.cost_tracker import CostTracker
from flaghunter.cpa_modules.m1_api_hub.models import RequestLog


# ========== TC-M1-017: 记录单次请求消耗 ==========

class TestTCM1017:
    """TC-M1-017: 记录单次请求消耗"""

    def test_record_single_request(self):
        """记录单次请求后能正确汇总"""
        tracker = CostTracker()
        log = RequestLog(
            request_id="req-001",
            provider_id="provider_a",
            model="openai/gpt-4",
            prompt_tokens=1000,
            completion_tokens=500,
            response_time_ms=1200,
            success=True,
            error_message="",
            timestamp=datetime.now(),
            cost_usd=0.03
        )
        
        tracker.record_request(log)
        
        summary = tracker.get_session_summary()
        assert summary["total_requests"] == 1
        assert summary["total_tokens"] == 1500
        assert summary["total_cost"] == 0.03
        assert "provider_a" in summary["by_provider"]

    def test_record_multiple_requests(self):
        """记录多次请求后汇总正确"""
        tracker = CostTracker()
        
        for i in range(5):
            tracker.record_request(RequestLog(
                request_id=f"req-{i:03d}",
                provider_id="provider_a",
                model="openai/gpt-4",
                prompt_tokens=1000,
                completion_tokens=500,
                response_time_ms=1000 + i * 100,
                success=True,
                error_message="",
                timestamp=datetime.now(),
                cost_usd=0.02
            ))
        
        summary = tracker.get_session_summary()
        assert summary["total_requests"] == 5
        assert summary["total_tokens"] == 7500
        assert summary["total_cost"] == 0.1

    def test_auto_cost_calculation(self):
        """未提供cost时自动估算"""
        tracker = CostTracker()
        log = RequestLog(
            request_id="req-auto",
            provider_id="p1",
            model="openai/gpt-4",
            prompt_tokens=1000,
            completion_tokens=500,
            response_time_ms=1000,
            success=True,
            error_message="",
            timestamp=datetime.now(),
            cost_usd=0  # 零成本，触发自动计算
        )
        
        tracker.record_request(log)
        
        summary = tracker.get_session_summary()
        # GPT-4: prompt $0.03/1K, completion $0.06/1K
        # 1000 prompt + 500 completion = 1 * 0.03 + 0.5 * 0.06 = 0.06
        assert summary["total_cost"] > 0

    def test_failed_request_no_cost(self):
        """失败请求不应计入成本"""
        tracker = CostTracker()
        tracker.record_request(RequestLog(
            request_id="req-fail",
            provider_id="p1",
            model="gpt-4",
            prompt_tokens=1000,
            completion_tokens=0,
            response_time_ms=500,
            success=False,  # 失败
            error_message="Timeout",
            timestamp=datetime.now(),
            cost_usd=0
        ))
        
        summary = tracker.get_session_summary()
        assert summary["total_requests"] == 1
        # 失败请求cost_usd=0，但prompt_tokens仍应计入
        assert summary["total_tokens"] == 1000


# ========== TC-M1-018: 会话消耗汇总 ==========

class TestTCM1018:
    """TC-M1-018: 会话消耗汇总"""

    def test_session_summary_by_provider(self):
        """按Provider分组的统计正确"""
        tracker = CostTracker()
        
        # provider_a: 6次请求
        for i in range(6):
            tracker.record_request(RequestLog(
                request_id=f"pa-{i}",
                provider_id="provider_a",
                model="openai/gpt-4",
                prompt_tokens=1000 + i * 100,
                completion_tokens=300 + i * 50,
                response_time_ms=800 + i * 100,
                success=True,
                error_message="",
                timestamp=datetime.now(),
                cost_usd=0.02 + i * 0.005
            ))
        
        # provider_b: 4次请求
        for i in range(4):
            tracker.record_request(RequestLog(
                request_id=f"pb-{i}",
                provider_id="provider_b",
                model="anthropic/claude-3",
                prompt_tokens=2000 + i * 200,
                completion_tokens=600 + i * 100,
                response_time_ms=1200 + i * 150,
                success=True,
                error_message="",
                timestamp=datetime.now(),
                cost_usd=0.03 + i * 0.008
            ))
        
        summary = tracker.get_session_summary()
        
        assert summary["total_requests"] == 10
        assert summary["total_tokens"] > 0
        assert summary["total_cost"] > 0
        assert summary["by_provider"]["provider_a"]["requests"] == 6
        assert summary["by_provider"]["provider_b"]["requests"] == 4
        assert summary["by_provider"]["provider_a"]["cost"] > 0
        assert summary["by_provider"]["provider_b"]["cost"] > 0

    def test_provider_usage_query(self):
        """查询单个Provider的使用统计"""
        tracker = CostTracker()
        
        tracker.record_request(RequestLog(
            request_id="r1", provider_id="p_a", model="gpt-4",
            prompt_tokens=1000, completion_tokens=500,
            response_time_ms=1000, success=True,
            error_message="", timestamp=datetime.now(), cost_usd=0.03
        ))
        tracker.record_request(RequestLog(
            request_id="r2", provider_id="p_b", model="gpt-4",
            prompt_tokens=2000, completion_tokens=1000,
            response_time_ms=2000, success=True,
            error_message="", timestamp=datetime.now(), cost_usd=0.06
        ))
        
        usage_a = tracker.get_provider_usage("p_a")
        assert usage_a["provider_id"] == "p_a"
        assert usage_a["requests"] == 1
        assert usage_a["tokens"] == 1500
        
        usage_b = tracker.get_provider_usage("p_b")
        assert usage_b["requests"] == 1
        assert usage_b["tokens"] == 3000

    def test_budget_usage_ratio(self):
        """预算使用率计算正确"""
        tracker = CostTracker()
        # 假设日预算$50
        tracker._daily_budget = 50.0
        
        tracker.record_request(RequestLog(
            request_id="r1", provider_id="p1", model="gpt-4",
            prompt_tokens=100000, completion_tokens=50000,
            response_time_ms=5000, success=True,
            error_message="", timestamp=datetime.now(), cost_usd=10.0  # $10
        ))
        
        summary = tracker.get_session_summary()
        assert summary["budget_used_ratio"] == 0.2  # 10/50 = 20%

    def test_export_csv(self):
        """导出CSV格式日志"""
        tracker = CostTracker()
        tracker.record_request(RequestLog(
            request_id="req-001", provider_id="p1", model="gpt-4",
            prompt_tokens=1000, completion_tokens=500,
            response_time_ms=1000, success=True,
            error_message="", timestamp=datetime.now(), cost_usd=0.03
        ))
        
        csv = tracker.export_session_log()
        
        assert "request_id" in csv  # 表头
        assert "req-001" in csv    # 数据行
        assert "p1" in csv
        assert "0.030000" in csv or "0.03" in csv


# ========== TC-M1-019: 预算告警触发 ==========

class TestTCM1019:
    """TC-M1-019: 预算告警触发"""

    @patch.dict(os.environ, {
        "CPA_M1_DAILY_BUDGET_USD": "10",
        "CPA_M1_BUDGET_ALERT_THRESHOLD": "0.8"
    })
    def test_alert_triggered_at_80_percent(self):
        """消耗超过80%阈值时触发告警"""
        tracker = CostTracker()  # 预算$10，阈值80%即$8
        
        tracker.record_request(RequestLog(
            request_id="req-big",
            provider_id="p1", model="openai/gpt-4",
            prompt_tokens=850000, completion_tokens=200000,
            response_time_ms=5000, success=True,
            error_message="", timestamp=datetime.now(),
            cost_usd=8.5  # 超过$8阈值
        ))
        
        alert = tracker.check_budget_alert()
        
        assert alert is not None
        assert "告警" in alert or "alert" in alert.lower()
        assert "8.5" in alert or "$8" in alert

    @patch.dict(os.environ, {
        "CPA_M1_DAILY_BUDGET_USD": "10",
        "CPA_M1_BUDGET_ALERT_THRESHOLD": "0.8"
    })
    def test_no_alert_below_threshold(self):
        """未超过阈值时不应触发告警"""
        tracker = CostTracker()
        
        tracker.record_request(RequestLog(
            request_id="req-small",
            provider_id="p1", model="gpt-4",
            prompt_tokens=100000, completion_tokens=50000,
            response_time_ms=2000, success=True,
            error_message="", timestamp=datetime.now(),
            cost_usd=5.0  # 未超过$8阈值
        ))
        
        alert = tracker.check_budget_alert()
        assert alert is None

    def test_alert_exactly_at_threshold(self):
        """刚好在阈值边界应触发告警"""
        tracker = CostTracker()
        tracker._daily_budget = 10.0
        tracker._alert_threshold = 0.8  # $8
        
        tracker.record_request(RequestLog(
            request_id="req-exact",
            provider_id="p1", model="gpt-4",
            prompt_tokens=800000, completion_tokens=200000,
            response_time_ms=4000, success=True,
            error_message="", timestamp=datetime.now(),
            cost_usd=8.0  # 刚好$8
        ))
        
        alert = tracker.check_budget_alert()
        assert alert is not None


# ========== TC-M1-020: 预算超限暂停 ==========

class TestTCM1020:
    """TC-M1-020: 预算超限暂停"""

    @patch.dict(os.environ, {
        "CPA_M1_DAILY_BUDGET_USD": "5",
        "CPA_M1_BUDGET_ALERT_THRESHOLD": "0.8"
    })
    def test_budget_exceeded_pause(self):
        """超过100%预算时应暂停服务"""
        tracker = CostTracker()  # 预算$5
        
        tracker.record_request(RequestLog(
            request_id="req-over",
            provider_id="p1", model="openai/gpt-4",
            prompt_tokens=500000, completion_tokens=150000,
            response_time_ms=3000, success=True,
            error_message="", timestamp=datetime.now(),
            cost_usd=5.5  # 超过$5预算
        ))
        
        assert tracker.is_budget_exceeded() is True
        assert tracker.allow_request() is False

    def test_allow_request_when_under_budget(self):
        """预算内应允许请求"""
        tracker = CostTracker()
        tracker._daily_budget = 50.0
        
        tracker.record_request(RequestLog(
            request_id="r1", provider_id="p1", model="gpt-4",
            prompt_tokens=1000, completion_tokens=500,
            response_time_ms=1000, success=True,
            error_message="", timestamp=datetime.now(),
            cost_usd=0.5
        ))
        
        assert tracker.is_budget_exceeded() is False
        assert tracker.allow_request() is True

    def test_daily_reset_clears_pause(self):
        """每日重置后应恢复允许请求"""
        tracker = CostTracker()
        tracker._daily_budget = 1.0
        
        tracker.record_request(RequestLog(
            request_id="r1", provider_id="p1", model="gpt-4",
            prompt_tokens=10000, completion_tokens=5000,
            response_time_ms=2000, success=True,
            error_message="", timestamp=datetime.now(),
            cost_usd=2.0  # 超过$1预算
        ))
        
        assert tracker.is_budget_exceeded() is True
        assert tracker.allow_request() is False
        
        # 每日重置
        tracker.daily_reset()
        
        assert tracker.is_budget_exceeded() is False
        assert tracker.allow_request() is True
        assert tracker.get_session_summary()["total_cost"] == 0

    @patch.dict(os.environ, {
        "CPA_M1_DAILY_BUDGET_USD": "0",
    })
    def test_zero_budget_always_exceeded(self):
        """零预算时任何消耗都超限"""
        tracker = CostTracker()
        
        tracker.record_request(RequestLog(
            request_id="r1", provider_id="p1", model="gpt-4",
            prompt_tokens=1, completion_tokens=1,
            response_time_ms=10, success=True,
            error_message="", timestamp=datetime.now(),
            cost_usd=0.001
        ))
        
        assert tracker.is_budget_exceeded() is True
