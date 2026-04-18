"""
健康检查模块

实现 API 提供者的健康检查机制，支持：
- 定期主动健康检查
- 被动健康检查（基于请求结果）
- 健康状态管理
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable
from enum import Enum
import asyncio
import logging
from datetime import datetime, timedelta
import aiohttp

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"  # 健康
    UNHEALTHY = "unhealthy"  # 不健康
    UNKNOWN = "unknown"  # 未知
    DEGRADED = "degraded"  # 降级（部分功能可用）
    RECOVERING = "recovering"  # 恢复中


class HealthCheckType(Enum):
    """健康检查类型"""
    ACTIVE = "active"  # 主动检查
    PASSIVE = "passive"  # 被动检查
    HYBRID = "hybrid"  # 混合检查


@dataclass
class HealthCheckConfig:
    """健康检查配置"""
    enabled: bool = True  # 是否启用健康检查
    check_type: HealthCheckType = HealthCheckType.HYBRID
    interval: float = 60.0  # 检查间隔（秒）
    timeout: float = 10.0  # 检查超时（秒）
    unhealthy_threshold: int = 3  # 判定为不健康的失败次数
    healthy_threshold: int = 2  # 判定为健康的成功次数
    check_endpoint: str = "/health"  # 健康检查端点
    passive_check_enabled: bool = True  # 是否启用被动检查
    passive_check_window: float = 300.0  # 被动检查时间窗口（秒）
    recovery_mode: bool = True  # 是否启用恢复模式
    recovery_interval: float = 30.0  # 恢复检查间隔（秒）


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    is_healthy: bool
    status: HealthStatus
    response_time: Optional[float] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "is_healthy": self.is_healthy,
            "status": self.status.value,
            "response_time": self.response_time,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details
        }


@dataclass
class ProviderHealthMetrics:
    """提供者健康指标"""
    provider_name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    total_checks: int = 0
    total_successes: int = 0
    total_failures: int = 0
    avg_response_time: float = 0.0
    _recent_results: List[HealthCheckResult] = field(default_factory=list)
    
    def record_check(self, result: HealthCheckResult):
        """记录检查结果"""
        self.total_checks += 1
        self.last_check_time = result.timestamp
        
        if result.is_healthy:
            self.total_successes += 1
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            self.last_success_time = result.timestamp
            
            # 更新平均响应时间
            if result.response_time:
                alpha = 0.3
                self.avg_response_time = (
                    alpha * result.response_time +
                    (1 - alpha) * self.avg_response_time
                )
        else:
            self.total_failures += 1
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            self.last_failure_time = result.timestamp
        
        # 保存最近的结果
        self._recent_results.append(result)
        if len(self._recent_results) > 10:
            self._recent_results.pop(0)
        
        # 更新状态
        self._update_status()
    
    def _update_status(self):
        """更新健康状态"""
        if self.consecutive_failures >= 3:
            self.status = HealthStatus.UNHEALTHY
        elif self.consecutive_successes >= 2:
            self.status = HealthStatus.HEALTHY
        elif self.consecutive_failures > 0:
            self.status = HealthStatus.DEGRADED
        else:
            self.status = HealthStatus.UNKNOWN
    
    def get_failure_rate(self) -> float:
        """获取失败率"""
        if self.total_checks == 0:
            return 0.0
        return self.total_failures / self.total_checks
    
    def get_recent_failure_rate(self, window: int = 5) -> float:
        """获取最近 N 次检查的失败率"""
        if not self._recent_results:
            return 0.0
        
        recent = self._recent_results[-window:]
        failures = sum(1 for r in recent if not r.is_healthy)
        return failures / len(recent)


class HealthChecker:
    """
    健康检查器
    
    负责定期检查 API 提供者的健康状态
    """
    
    def __init__(
        self,
        config: Optional[HealthCheckConfig] = None,
        session: Optional[aiohttp.ClientSession] = None
    ):
        self.config = config or HealthCheckConfig()
        self._session = session
        self._provider_metrics: Dict[str, ProviderHealthMetrics] = {}
        self._check_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._passive_callbacks: List[Callable[[str, bool, float], None]] = []
    
    def initialize_provider(self, provider_name: str, base_url: str):
        """
        初始化提供者健康指标
        
        Args:
            provider_name: 提供者名称
            base_url: 提供者基础 URL
        """
        if provider_name not in self._provider_metrics:
            self._provider_metrics[provider_name] = ProviderHealthMetrics(
                provider_name=provider_name
            )
            logger.debug(f"初始化提供者健康指标：{provider_name}")
    
    def get_provider_metrics(self, provider_name: str) -> Optional[ProviderHealthMetrics]:
        """获取提供者健康指标"""
        return self._provider_metrics.get(provider_name)
    
    def get_provider_status(self, provider_name: str) -> HealthStatus:
        """获取提供者健康状态"""
        metrics = self.get_provider_metrics(provider_name)
        if metrics:
            return metrics.status
        return HealthStatus.UNKNOWN
    
    def is_provider_healthy(self, provider_name: str) -> bool:
        """判断提供者是否健康"""
        status = self.get_provider_status(provider_name)
        return status in [HealthStatus.HEALTHY, HealthStatus.RECOVERING]
    
    def is_provider_available(self, provider_name: str) -> bool:
        """判断提供者是否可用（健康或降级）"""
        status = self.get_provider_status(provider_name)
        return status in [
            HealthStatus.HEALTHY,
            HealthStatus.RECOVERING,
            HealthStatus.DEGRADED
        ]
    
    async def check_health(
        self,
        provider_name: str,
        base_url: str,
        api_key: Optional[str] = None,
        check_endpoint: Optional[str] = None
    ) -> HealthCheckResult:
        """
        主动健康检查
        
        Args:
            provider_name: 提供者名称
            base_url: 提供者基础 URL
            api_key: API 密钥
            check_endpoint: 健康检查端点
            
        Returns:
            HealthCheckResult: 健康检查结果
        """
        if not self.config.enabled:
            return HealthCheckResult(
                is_healthy=True,
                status=HealthStatus.UNKNOWN,
                details={"reason": "健康检查已禁用"}
            )
        
        endpoint = check_endpoint or self.config.check_endpoint
        url = f"{base_url.rstrip('/')}{endpoint}"
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # 创建临时 session 或使用已有 session
            close_session = False
            if not self._session:
                self._session = aiohttp.ClientSession()
                close_session = True
            
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            async with self._session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                response_time = asyncio.get_event_loop().time() - start_time
                
                if response.status == 200:
                    result = HealthCheckResult(
                        is_healthy=True,
                        status=HealthStatus.HEALTHY,
                        response_time=response_time,
                        details={
                            "status_code": response.status,
                            "url": url
                        }
                    )
                    logger.debug(
                        f"提供者 {provider_name} 健康检查通过，"
                        f"响应时间：{response_time:.3f}s"
                    )
                else:
                    result = HealthCheckResult(
                        is_healthy=False,
                        status=HealthStatus.UNHEALTHY,
                        response_time=response_time,
                        error=f"健康检查返回非 200 状态码：{response.status}",
                        details={
                            "status_code": response.status,
                            "url": url
                        }
                    )
                    logger.warning(
                        f"提供者 {provider_name} 健康检查失败：{response.status}"
                    )
            
            if close_session:
                await self._session.close()
                self._session = None
            
            # 更新指标
            self._update_metrics(provider_name, result)
            
            return result
            
        except asyncio.TimeoutError as e:
            response_time = asyncio.get_event_loop().time() - start_time
            result = HealthCheckResult(
                is_healthy=False,
                status=HealthStatus.UNHEALTHY,
                response_time=response_time,
                error=f"健康检查超时（{self.config.timeout}s）",
                details={"url": url}
            )
            logger.warning(f"提供者 {provider_name} 健康检查超时")
            self._update_metrics(provider_name, result)
            return result
            
        except aiohttp.ClientError as e:
            response_time = asyncio.get_event_loop().time() - start_time
            result = HealthCheckResult(
                is_healthy=False,
                status=HealthStatus.UNHEALTHY,
                response_time=response_time,
                error=f"健康检查网络错误：{str(e)}",
                details={"url": url}
            )
            logger.warning(f"提供者 {provider_name} 健康检查网络错误：{e}")
            self._update_metrics(provider_name, result)
            return result
            
        except Exception as e:
            response_time = asyncio.get_event_loop().time() - start_time
            result = HealthCheckResult(
                is_healthy=False,
                status=HealthStatus.UNHEALTHY,
                response_time=response_time,
                error=f"健康检查异常：{str(e)}",
                details={"url": url}
            )
            logger.error(f"提供者 {provider_name} 健康检查异常：{e}")
            self._update_metrics(provider_name, result)
            return result
    
    def record_passive_check(
        self,
        provider_name: str,
        success: bool,
        response_time: float = 0.0
    ):
        """
        被动健康检查（基于请求结果）
        
        Args:
            provider_name: 提供者名称
            success: 请求是否成功
            response_time: 响应时间
        """
        if not self.config.passive_check_enabled:
            return
        
        result = HealthCheckResult(
            is_healthy=success,
            status=HealthStatus.HEALTHY if success else HealthStatus.UNHEALTHY,
            response_time=response_time,
            details={"type": "passive"}
        )
        
        self._update_metrics(provider_name, result)
        
        # 通知回调
        for callback in self._passive_callbacks:
            try:
                callback(provider_name, success, response_time)
            except Exception as e:
                logger.error(f"被动检查回调执行失败：{e}")
    
    def _update_metrics(
        self,
        provider_name: str,
        result: HealthCheckResult
    ):
        """更新提供者健康指标"""
        self.initialize_provider(provider_name)
        metrics = self._provider_metrics[provider_name]
        metrics.record_check(result)
        
        logger.debug(
            f"提供者 {provider_name} 健康状态：{metrics.status.value}, "
            f"连续成功：{metrics.consecutive_successes}, "
            f"连续失败：{metrics.consecutive_failures}"
        )
    
    def start_periodic_check(
        self,
        provider_name: str,
        base_url: str,
        api_key: Optional[str] = None
    ):
        """
        启动定期检查
        
        Args:
            provider_name: 提供者名称
            base_url: 提供者基础 URL
            api_key: API 密钥
        """
        if not self.config.enabled:
            return
        
        if provider_name in self._check_tasks:
            logger.warning(f"提供者 {provider_name} 的定期检查已在运行")
            return
        
        async def check_loop():
            """定期检查循环"""
            while self._running:
                try:
                    await self.check_health(
                        provider_name,
                        base_url,
                        api_key
                    )
                    
                    # 根据状态调整检查频率
                    metrics = self.get_provider_metrics(provider_name)
                    if metrics and metrics.status == HealthStatus.UNHEALTHY:
                        # 不健康时减少检查频率
                        await asyncio.sleep(self.config.recovery_interval)
                    else:
                        await asyncio.sleep(self.config.interval)
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"定期检查执行失败：{e}")
                    await asyncio.sleep(self.config.interval)
        
        task = asyncio.create_task(check_loop())
        self._check_tasks[provider_name] = task
        logger.info(f"启动提供者 {provider_name} 的定期检查")
    
    def stop_periodic_check(self, provider_name: str):
        """停止定期检查"""
        if provider_name in self._check_tasks:
            task = self._check_tasks[provider_name]
            task.cancel()
            del self._check_tasks[provider_name]
            logger.info(f"停止提供者 {provider_name} 的定期检查")
    
    def stop_all_checks(self):
        """停止所有定期检查"""
        for provider_name in list(self._check_tasks.keys()):
            self.stop_periodic_check(provider_name)
        self._running = False
        logger.info("停止所有健康检查")
    
    def register_passive_callback(
        self,
        callback: Callable[[str, bool, float], None]
    ):
        """注册被动检查回调"""
        self._passive_callbacks.append(callback)
    
    def get_all_providers_status(self) -> Dict[str, HealthStatus]:
        """获取所有提供者状态"""
        return {
            name: metrics.status
            for name, metrics in self._provider_metrics.items()
        }
    
    def get_healthy_providers(self) -> List[str]:
        """获取健康提供者列表"""
        return [
            name for name, metrics in self._provider_metrics.items()
            if metrics.status == HealthStatus.HEALTHY
        ]
    
    def get_unhealthy_providers(self) -> List[str]:
        """获取不健康提供者列表"""
        return [
            name for name, metrics in self._provider_metrics.items()
            if metrics.status == HealthStatus.UNHEALTHY
        ]
    
    def get_status_summary(self) -> Dict[str, Any]:
        """获取健康状态摘要"""
        total = len(self._provider_metrics)
        healthy = len(self.get_healthy_providers())
        unhealthy = len(self.get_unhealthy_providers())
        
        return {
            "total_providers": total,
            "healthy": healthy,
            "unhealthy": unhealthy,
            "unknown": total - healthy - unhealthy,
            "health_rate": healthy / total if total > 0 else 0.0
        }
    
    def clear(self):
        """清空所有健康检查状态"""
        self.stop_all_checks()
        self._provider_metrics.clear()
        logger.info("清空所有健康检查状态")


class PassiveHealthChecker:
    """
    被动健康检查器
    
    仅基于请求结果进行健康判断，不主动发起检查
    """
    
    def __init__(self, config: Optional[HealthCheckConfig] = None):
        self.config = config or HealthCheckConfig()
        self._metrics: Dict[str, ProviderHealthMetrics] = {}
    
    def record_request(
        self,
        provider_name: str,
        success: bool,
        response_time: float,
        error: Optional[str] = None
    ):
        """
        记录请求结果
        
        Args:
            provider_name: 提供者名称
            success: 请求是否成功
            response_time: 响应时间
            error: 错误信息（如果失败）
        """
        if provider_name not in self._metrics:
            self._metrics[provider_name] = ProviderHealthMetrics(
                provider_name=provider_name
            )
        
        metrics = self._metrics[provider_name]
        result = HealthCheckResult(
            is_healthy=success,
            status=HealthStatus.HEALTHY if success else HealthStatus.UNHEALTHY,
            response_time=response_time,
            error=error,
            details={"type": "passive"}
        )
        
        metrics.record_check(result)
    
    def is_healthy(self, provider_name: str) -> bool:
        """判断提供者是否健康"""
        metrics = self._metrics.get(provider_name)
        if not metrics:
            return True  # 没有记录时默认健康
        
        # 基于最近的表现判断
        recent_failure_rate = metrics.get_recent_failure_rate(5)
        return recent_failure_rate < 0.5
    
    def get_status(self, provider_name: str) -> HealthStatus:
        """获取提供者状态"""
        metrics = self._metrics.get(provider_name)
        if not metrics:
            return HealthStatus.UNKNOWN
        return metrics.status
    
    def should_use_provider(self, provider_name: str) -> bool:
        """判断是否应该使用该提供者"""
        status = self.get_status(provider_name)
        return status in [HealthStatus.HEALTHY, HealthStatus.RECOVERING]
