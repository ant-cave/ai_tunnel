"""
健康检查模块单元测试

测试健康检查器、健康状态、被动健康检查等
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any

from src.router.health_check import (
    HealthStatus,
    HealthCheckType,
    HealthCheckConfig,
    HealthCheckResult,
    HealthChecker,
    ProviderHealthMetrics,
    PassiveHealthChecker,
)


class TestHealthStatus:
    """测试健康状态枚举"""
    
    def test_health_status_values(self):
        """测试健康状态值"""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.RECOVERING.value == "recovering"


class TestHealthCheckConfig:
    """测试健康检查配置"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = HealthCheckConfig()
        
        assert config.enabled is True
        assert config.check_type == HealthCheckType.HYBRID
        assert config.interval == 60.0
        assert config.timeout == 10.0
        assert config.unhealthy_threshold == 3
        assert config.healthy_threshold == 2
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = HealthCheckConfig(
            enabled=False,
            interval=30.0,
            timeout=5.0,
            unhealthy_threshold=5
        )
        
        assert config.enabled is False
        assert config.interval == 30.0
        assert config.timeout == 5.0
        assert config.unhealthy_threshold == 5


class TestHealthCheckResult:
    """测试健康检查结果"""
    
    def test_healthy_result(self):
        """测试健康结果"""
        result = HealthCheckResult(
            is_healthy=True,
            status=HealthStatus.HEALTHY,
            response_time=0.5
        )
        
        assert result.is_healthy is True
        assert result.status == HealthStatus.HEALTHY
        assert result.response_time == 0.5
        assert result.error is None
    
    def test_unhealthy_result(self):
        """测试不健康结果"""
        result = HealthCheckResult(
            is_healthy=False,
            status=HealthStatus.UNHEALTHY,
            error="Connection timeout"
        )
        
        assert result.is_healthy is False
        assert result.status == HealthStatus.UNHEALTHY
        assert result.error == "Connection timeout"
    
    def test_to_dict(self):
        """测试转换为字典"""
        result = HealthCheckResult(
            is_healthy=True,
            status=HealthStatus.HEALTHY,
            response_time=0.3
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["is_healthy"] is True
        assert result_dict["status"] == "healthy"
        assert result_dict["response_time"] == 0.3
        assert "timestamp" in result_dict


class TestProviderHealthMetrics:
    """测试提供者健康指标"""
    
    def test_initial_metrics(self):
        """测试初始指标"""
        metrics = ProviderHealthMetrics(provider_name="test_provider")
        
        assert metrics.provider_name == "test_provider"
        assert metrics.status == HealthStatus.UNKNOWN
        assert metrics.consecutive_successes == 0
        assert metrics.consecutive_failures == 0
        assert metrics.total_checks == 0
    
    def test_record_successful_check(self):
        """测试记录成功检查"""
        metrics = ProviderHealthMetrics(provider_name="test_provider")
        
        result = HealthCheckResult(
            is_healthy=True,
            status=HealthStatus.HEALTHY,
            response_time=0.5
        )
        
        metrics.record_check(result)
        
        assert metrics.total_checks == 1
        assert metrics.total_successes == 1
        assert metrics.consecutive_successes == 1
        assert metrics.consecutive_failures == 0
        assert metrics.avg_response_time > 0
    
    def test_record_failed_check(self):
        """测试记录失败检查"""
        metrics = ProviderHealthMetrics(provider_name="test_provider")
        
        result = HealthCheckResult(
            is_healthy=False,
            status=HealthStatus.UNHEALTHY,
            error="Timeout"
        )
        
        metrics.record_check(result)
        
        assert metrics.total_checks == 1
        assert metrics.total_failures == 1
        assert metrics.consecutive_failures == 1
        assert metrics.consecutive_successes == 0
    
    def test_status_update_on_failures(self):
        """测试失败时状态更新"""
        metrics = ProviderHealthMetrics(provider_name="test_provider")
        
        # 连续失败 3 次
        for _ in range(3):
            result = HealthCheckResult(
                is_healthy=False,
                status=HealthStatus.UNHEALTHY
            )
            metrics.record_check(result)
        
        assert metrics.status == HealthStatus.UNHEALTHY
    
    def test_status_update_on_successes(self):
        """测试成功时状态更新"""
        metrics = ProviderHealthMetrics(provider_name="test_provider")
        
        # 先失败
        result = HealthCheckResult(
            is_healthy=False,
            status=HealthStatus.UNHEALTHY
        )
        metrics.record_check(result)
        
        # 连续成功 2 次
        for _ in range(2):
            result = HealthCheckResult(
                is_healthy=True,
                status=HealthStatus.HEALTHY,
                response_time=0.3
            )
            metrics.record_check(result)
        
        assert metrics.status == HealthStatus.HEALTHY
    
    def test_get_failure_rate(self):
        """测试获取失败率"""
        metrics = ProviderHealthMetrics(provider_name="test_provider")
        
        # 初始失败率为 0
        assert metrics.get_failure_rate() == 0.0
        
        # 记录 3 次检查，2 次失败
        metrics.record_check(HealthCheckResult(is_healthy=True, status=HealthStatus.HEALTHY))
        metrics.record_check(HealthCheckResult(is_healthy=False, status=HealthStatus.UNHEALTHY))
        metrics.record_check(HealthCheckResult(is_healthy=False, status=HealthStatus.UNHEALTHY))
        
        assert abs(metrics.get_failure_rate() - 0.667) < 0.001
    
    def test_get_recent_failure_rate(self):
        """测试获取最近失败率"""
        metrics = ProviderHealthMetrics(provider_name="test_provider")
        
        # 记录 10 次检查
        for i in range(10):
            metrics.record_check(HealthCheckResult(
                is_healthy=i % 2 == 0,  # 交替成功和失败
                status=HealthStatus.HEALTHY if i % 2 == 0 else HealthStatus.UNHEALTHY
            ))
        
        # 最近 5 次的失败率
        recent_rate = metrics.get_recent_failure_rate(5)
        assert 0.4 <= recent_rate <= 0.6


class TestHealthChecker:
    """测试健康检查器"""
    
    def test_initialize_provider(self):
        """测试初始化提供者"""
        checker = HealthChecker()
        
        checker.initialize_provider("provider1", "http://localhost:8000")
        
        metrics = checker.get_provider_metrics("provider1")
        assert metrics is not None
        assert metrics.provider_name == "provider1"
    
    def test_get_provider_status(self):
        """测试获取提供者状态"""
        checker = HealthChecker()
        
        # 未初始化的提供者返回 UNKNOWN
        assert checker.get_provider_status("unknown") == HealthStatus.UNKNOWN
        
        # 初始化后
        checker.initialize_provider("provider1", "http://localhost:8000")
        assert checker.get_provider_status("provider1") == HealthStatus.UNKNOWN
    
    def test_is_provider_healthy(self):
        """测试判断提供者是否健康"""
        checker = HealthChecker()
        checker.initialize_provider("provider1", "http://localhost:8000")
        
        # 初始状态不健康
        assert not checker.is_provider_healthy("provider1")
        
        # 手动更新状态
        checker._provider_metrics["provider1"].status = HealthStatus.HEALTHY
        
        assert checker.is_provider_healthy("provider1")
    
    def test_is_provider_available(self):
        """测试判断提供者是否可用"""
        checker = HealthChecker()
        checker.initialize_provider("provider1", "http://localhost:8000")
        
        metrics = checker._provider_metrics["provider1"]
        
        # 健康状态可用
        metrics.status = HealthStatus.HEALTHY
        assert checker.is_provider_available("provider1")
        
        # 降级状态可用
        metrics.status = HealthStatus.DEGRADED
        assert checker.is_provider_available("provider1")
        
        # 不健康状态不可用
        metrics.status = HealthStatus.UNHEALTHY
        assert not checker.is_provider_available("provider1")
    
    @pytest.mark.asyncio
    async def test_check_health_disabled(self):
        """测试禁用的健康检查"""
        config = HealthCheckConfig(enabled=False)
        checker = HealthChecker(config)
        
        result = await checker.check_health(
            "provider1",
            "http://localhost:8000"
        )
        
        assert not result.is_healthy
        assert result.status == HealthStatus.UNKNOWN
    
    def test_record_passive_check(self):
        """测试记录被动检查"""
        checker = HealthChecker()
        checker.initialize_provider("provider1", "http://localhost:8000")
        
        # 记录成功
        checker.record_passive_check("provider1", success=True, response_time=0.5)
        
        metrics = checker.get_provider_metrics("provider1")
        assert metrics.consecutive_successes == 1
        
        # 记录失败
        checker.record_passive_check("provider1", success=False, response_time=0.0)
        
        metrics = checker.get_provider_metrics("provider1")
        assert metrics.consecutive_failures == 1
    
    def test_get_all_providers_status(self):
        """测试获取所有提供者状态"""
        checker = HealthChecker()
        
        checker.initialize_provider("provider1", "http://localhost:8000")
        checker.initialize_provider("provider2", "http://localhost:8001")
        
        checker._provider_metrics["provider1"].status = HealthStatus.HEALTHY
        checker._provider_metrics["provider2"].status = HealthStatus.UNHEALTHY
        
        status_map = checker.get_all_providers_status()
        
        assert status_map["provider1"] == HealthStatus.HEALTHY
        assert status_map["provider2"] == HealthStatus.UNHEALTHY
    
    def test_get_healthy_providers(self):
        """测试获取健康提供者列表"""
        checker = HealthChecker()
        
        checker.initialize_provider("provider1", "http://localhost:8000")
        checker.initialize_provider("provider2", "http://localhost:8001")
        checker.initialize_provider("provider3", "http://localhost:8002")
        
        checker._provider_metrics["provider1"].status = HealthStatus.HEALTHY
        checker._provider_metrics["provider2"].status = HealthStatus.UNHEALTHY
        checker._provider_metrics["provider3"].status = HealthStatus.HEALTHY
        
        healthy = checker.get_healthy_providers()
        
        assert len(healthy) == 2
        assert "provider1" in healthy
        assert "provider3" in healthy
    
    def test_get_unhealthy_providers(self):
        """测试获取不健康提供者列表"""
        checker = HealthChecker()
        
        checker.initialize_provider("provider1", "http://localhost:8000")
        checker.initialize_provider("provider2", "http://localhost:8001")
        
        checker._provider_metrics["provider1"].status = HealthStatus.UNHEALTHY
        checker._provider_metrics["provider2"].status = HealthStatus.HEALTHY
        
        unhealthy = checker.get_unhealthy_providers()
        
        assert len(unhealthy) == 1
        assert "provider1" in unhealthy
    
    def test_get_status_summary(self):
        """测试获取状态摘要"""
        checker = HealthChecker()
        
        checker.initialize_provider("provider1", "http://localhost:8000")
        checker.initialize_provider("provider2", "http://localhost:8001")
        checker.initialize_provider("provider3", "http://localhost:8002")
        
        checker._provider_metrics["provider1"].status = HealthStatus.HEALTHY
        checker._provider_metrics["provider2"].status = HealthStatus.UNHEALTHY
        checker._provider_metrics["provider3"].status = HealthStatus.UNKNOWN
        
        summary = checker.get_status_summary()
        
        assert summary["total_providers"] == 3
        assert summary["healthy"] == 1
        assert summary["unhealthy"] == 1
        assert summary["unknown"] == 1
    
    def test_clear(self):
        """测试清空状态"""
        checker = HealthChecker()
        
        checker.initialize_provider("provider1", "http://localhost:8000")
        checker.initialize_provider("provider2", "http://localhost:8001")
        
        checker.clear()
        
        assert len(checker._provider_metrics) == 0


class TestPassiveHealthChecker:
    """测试被动健康检查器"""
    
    def test_record_request(self):
        """测试记录请求"""
        checker = PassiveHealthChecker()
        
        checker.record_request(
            "provider1",
            success=True,
            response_time=0.5
        )
        
        metrics = checker._metrics["provider1"]
        assert metrics.total_requests == 1
        assert metrics.total_successes == 1
    
    def test_is_healthy_no_records(self):
        """测试无记录时判断健康"""
        checker = PassiveHealthChecker()
        
        # 没有记录时默认健康
        assert checker.is_healthy("unknown_provider")
    
    def test_is_healthy_with_good_performance(self):
        """测试良好表现时判断健康"""
        checker = PassiveHealthChecker()
        
        # 记录 5 次成功
        for _ in range(5):
            checker.record_request("provider1", success=True, response_time=0.3)
        
        assert checker.is_healthy("provider1")
    
    def test_is_healthy_with_poor_performance(self):
        """测试差表现时判断不健康"""
        checker = PassiveHealthChecker()
        
        # 记录 5 次失败
        for _ in range(5):
            checker.record_request("provider1", success=False, response_time=0.0)
        
        assert not checker.is_healthy("provider1")
    
    def test_get_status(self):
        """测试获取状态"""
        checker = PassiveHealthChecker()
        
        # 未记录的提供者
        assert checker.get_status("unknown") == HealthStatus.UNKNOWN
        
        # 记录的提供者
        checker.record_request("provider1", success=True, response_time=0.3)
        assert checker.get_status("provider1") == HealthStatus.HEALTHY
    
    def test_should_use_provider(self):
        """测试是否应该使用提供者"""
        checker = PassiveHealthChecker()
        
        # 健康提供者应该使用
        checker.record_request("provider1", success=True, response_time=0.3)
        assert checker.should_use_provider("provider1")
        
        # 不健康提供者不应该使用
        checker.record_request("provider2", success=False, response_time=0.0)
        checker.record_request("provider2", success=False, response_time=0.0)
        checker.record_request("provider2", success=False, response_time=0.0)
        assert not checker.should_use_provider("provider2")


class TestHealthCheckerPeriodicCheck:
    """测试定期检查"""
    
    def test_start_stop_periodic_check(self):
        """测试启动和停止定期检查"""
        checker = HealthChecker()
        checker._running = True
        
        checker.start_periodic_check(
            "provider1",
            "http://localhost:8000"
        )
        
        assert "provider1" in checker._check_tasks
        
        checker.stop_periodic_check("provider1")
        
        assert "provider1" not in checker._check_tasks
    
    def test_stop_all_checks(self):
        """测试停止所有检查"""
        checker = HealthChecker()
        checker._running = True
        
        checker.start_periodic_check("provider1", "http://localhost:8000")
        checker.start_periodic_check("provider2", "http://localhost:8001")
        
        checker.stop_all_checks()
        
        assert len(checker._check_tasks) == 0
        assert checker._running is False


class TestHealthCheckIntegration:
    """健康检查集成测试"""
    
    def test_health_check_workflow(self):
        """测试健康检查工作流"""
        config = HealthCheckConfig(
            unhealthy_threshold=3,
            healthy_threshold=2
        )
        checker = HealthChecker(config)
        
        provider_name = "test_provider"
        checker.initialize_provider(provider_name, "http://localhost:8000")
        
        # 初始状态未知
        assert checker.get_provider_status(provider_name) == HealthStatus.UNKNOWN
        
        # 模拟连续失败
        for _ in range(3):
            checker.record_passive_check(provider_name, success=False)
        
        # 应该标记为不健康
        assert checker.get_provider_status(provider_name) == HealthStatus.UNHEALTHY
        
        # 模拟连续成功
        for _ in range(2):
            checker.record_passive_check(provider_name, success=True, response_time=0.3)
        
        # 应该恢复健康
        assert checker.get_provider_status(provider_name) == HealthStatus.HEALTHY
    
    def test_passive_health_check_workflow(self):
        """测试被动健康检查工作流"""
        checker = PassiveHealthChecker()
        
        provider_name = "test_provider"
        
        # 模拟请求序列
        sequence = [True, True, False, True, True]
        
        for success in sequence:
            checker.record_request(
                provider_name,
                success=success,
                response_time=0.3 if success else 0.0
            )
        
        # 最终应该是健康的
        assert checker.is_healthy(provider_name)
        assert checker.should_use_provider(provider_name)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
