"""
故障转移策略模块

实现智能故障转移机制，支持：
- 按顺序尝试多个提供者
- 快速失败策略
- 指数退避重试
- 超时控制
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Callable, Awaitable
from enum import Enum
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class FailoverStrategyType(Enum):
    """故障转移策略类型"""
    SEQUENTIAL = "sequential"  # 按顺序尝试
    FAST_FAILOVER = "fast_failover"  # 快速失败
    ROUND_ROBIN = "round_robin"  # 轮询
    PRIORITY_BASED = "priority"  # 基于优先级


class FailureType(Enum):
    """失败类型"""
    TIMEOUT = "timeout"  # 超时
    NETWORK_ERROR = "network_error"  # 网络错误
    SERVICE_UNAVAILABLE = "service_unavailable"  # 服务不可用
    RATE_LIMITED = "rate_limited"  # 速率限制
    AUTHENTICATION_ERROR = "authentication_error"  # 认证错误
    SERVER_ERROR = "server_error"  # 服务器错误
    UNKNOWN = "unknown"  # 未知错误


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3  # 最大重试次数
    initial_delay: float = 1.0  # 初始延迟（秒）
    max_delay: float = 60.0  # 最大延迟（秒）
    exponential_base: float = 2.0  # 指数退避基数
    jitter: bool = True  # 是否添加随机抖动
    
    def get_delay(self, attempt: int) -> float:
        """
        计算第 N 次重试的延迟时间
        
        Args:
            attempt: 当前重试次数（从 0 开始）
            
        Returns:
            float: 延迟时间（秒）
        """
        # 指数退避计算
        delay = self.initial_delay * (self.exponential_base ** attempt)
        
        # 限制最大延迟
        delay = min(delay, self.max_delay)
        
        # 添加随机抖动
        if self.jitter:
            import random
            jitter_range = delay * 0.1
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0, delay)


@dataclass
class FailoverConfig:
    """故障转移配置"""
    strategy: FailoverStrategyType = FailoverStrategyType.SEQUENTIAL
    timeout: float = 30.0  # 超时时间（秒）
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    max_failures: int = 5  # 最大失败次数
    failure_window: float = 60.0  # 失败时间窗口（秒）
    recovery_timeout: float = 300.0  # 恢复超时（秒）
    fast_failover_threshold: float = 5.0  # 快速失败阈值（秒）
    enabled: bool = True  # 是否启用故障转移
    max_retries: int = 5  # 最大重试次数


@dataclass
class ProviderState:
    """提供者状态"""
    name: str
    is_healthy: bool = True
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    consecutive_failures: int = 0
    total_requests: int = 0
    total_failures: int = 0
    avg_response_time: float = 0.0
    _failure_times: List[datetime] = field(default_factory=list)
    
    def record_failure(self, failure_type: FailureType):
        """记录失败"""
        now = datetime.now()
        self.failure_count += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure_time = now
        self._failure_times.append(now)
        
        # 清理旧的失败记录
        self._cleanup_failure_times()
    
    def record_success(self, response_time: float):
        """记录成功"""
        now = datetime.now()
        self.last_success_time = now
        self.consecutive_failures = 0
        
        # 更新平均响应时间（移动平均）
        alpha = 0.3  # 平滑因子
        self.avg_response_time = alpha * response_time + (1 - alpha) * self.avg_response_time
    
    def _cleanup_failure_times(self):
        """清理超出时间窗口的失败记录"""
        now = datetime.now()
        self._failure_times = [
            t for t in self._failure_times
            if (now - t).total_seconds() < 60.0  # 默认 60 秒窗口
        ]
    
    def get_failure_rate(self) -> float:
        """获取失败率"""
        if self.total_requests == 0:
            return 0.0
        return self.total_failures / self.total_requests
    
    def should_circuit_break(self, config: FailoverConfig) -> bool:
        """判断是否应该熔断"""
        # 检查连续失败次数
        if self.consecutive_failures >= config.max_failures:
            return True
        
        # 检查时间窗口内的失败次数
        if len(self._failure_times) >= config.max_failures:
            return True
        
        return False
    
    def can_recover(self, config: FailoverConfig) -> bool:
        """判断是否可以恢复"""
        if not self.last_failure_time:
            return True
        
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= config.recovery_timeout


@dataclass
class FailoverResult:
    """故障转移结果"""
    success: bool
    provider_name: Optional[str] = None
    response: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[FailureType] = None
    attempts: int = 0
    total_time: float = 0.0
    failover_occurred: bool = False
    tried_providers: List[str] = field(default_factory=list)


class FailoverStrategy:
    """
    故障转移策略基类
    """
    
    def __init__(self, config: FailoverConfig):
        self.config = config
        self.provider_states: Dict[str, ProviderState] = {}
    
    def initialize_provider(self, provider_name: str):
        """初始化提供者状态"""
        if provider_name not in self.provider_states:
            self.provider_states[provider_name] = ProviderState(name=provider_name)
            logger.debug(f"初始化提供者状态：{provider_name}")
    
    def get_provider_state(self, provider_name: str) -> Optional[ProviderState]:
        """获取提供者状态"""
        return self.provider_states.get(provider_name)
    
    def record_success(
        self,
        provider_name: str,
        response_time: float
    ):
        """记录成功"""
        self.initialize_provider(provider_name)
        state = self.provider_states[provider_name]
        state.total_requests += 1
        state.record_success(response_time)
        state.is_healthy = True
        logger.debug(f"提供者 {provider_name} 请求成功，响应时间：{response_time:.3f}s")
    
    def record_failure(
        self,
        provider_name: str,
        failure_type: FailureType
    ):
        """记录失败"""
        self.initialize_provider(provider_name)
        state = self.provider_states[provider_name]
        state.total_requests += 1
        state.record_failure(failure_type)
        
        # 根据失败类型判断是否应该标记为不健康
        if failure_type in [
            FailureType.SERVICE_UNAVAILABLE,
            FailureType.NETWORK_ERROR,
            FailureType.SERVER_ERROR
        ]:
            if state.should_circuit_break(self.config):
                state.is_healthy = False
                logger.warning(
                    f"提供者 {provider_name} 触发熔断，"
                    f"连续失败次数：{state.consecutive_failures}"
                )
        
        logger.warning(
            f"提供者 {provider_name} 请求失败：{failure_type.value}, "
            f"失败次数：{state.failure_count}"
        )
    
    def should_failover(
        self,
        provider_name: str,
        failure_type: FailureType
    ) -> bool:
        """
        判断是否应该触发故障转移
        
        Args:
            provider_name: 提供者名称
            failure_type: 失败类型
            
        Returns:
            bool: 是否应该故障转移
        """
        if not self.config.enabled:
            return False
        
        # 认证错误不触发故障转移
        if failure_type == FailureType.AUTHENTICATION_ERROR:
            return False
        
        # 速率限制不触发故障转移
        if failure_type == FailureType.RATE_LIMITED:
            return False
        
        # 其他错误类型触发故障转移
        return True
    
    async def select_next_provider(
        self,
        current_provider: str,
        available_providers: List[str],
        failure_type: FailureType
    ) -> Optional[str]:
        """
        选择下一个提供者
        
        Args:
            current_provider: 当前提供者
            available_providers: 可用提供者列表
            failure_type: 失败类型
            
        Returns:
            下一个提供者名称，没有则返回 None
        """
        raise NotImplementedError


class SequentialFailoverStrategy(FailoverStrategy):
    """
    顺序故障转移策略
    
    按照提供者列表顺序尝试，当前提供者失败时尝试下一个
    """
    
    async def select_next_provider(
        self,
        current_provider: str,
        available_providers: List[str],
        failure_type: FailureType
    ) -> Optional[str]:
        if not self.should_failover(current_provider, failure_type):
            return None
        
        current_index = -1
        for i, provider in enumerate(available_providers):
            if provider == current_provider:
                current_index = i
                break
        
        # 从当前提供者的下一个开始查找
        for i in range(current_index + 1, len(available_providers)):
            provider = available_providers[i]
            state = self.get_provider_state(provider)
            
            if state and not state.is_healthy:
                continue
            
            logger.info(f"故障转移：{current_provider} -> {provider}")
            return provider
        
        return None


class FastFailoverStrategy(FailoverStrategy):
    """
    快速失败故障转移策略
    
    当响应时间超过阈值时立即触发故障转移
    """
    
    async def select_next_provider(
        self,
        current_provider: str,
        available_providers: List[str],
        failure_type: FailureType
    ) -> Optional[str]:
        if not self.should_failover(current_provider, failure_type):
            return False
        
        # 超时错误触发快速故障转移
        if failure_type == FailureType.TIMEOUT:
            for provider in available_providers:
                if provider == current_provider:
                    continue
                
                state = self.get_provider_state(provider)
                if state and not state.is_healthy:
                    continue
                
                # 选择平均响应时间最快的提供者
                if not state or state.avg_response_time < self.config.fast_failover_threshold:
                    logger.info(f"快速故障转移：{current_provider} -> {provider}")
                    return provider
        
        # 其他错误使用顺序故障转移
        return await super().select_next_provider(
            current_provider, available_providers, failure_type
        )


class PriorityFailoverStrategy(FailoverStrategy):
    """
    优先级故障转移策略
    
    按照提供者优先级顺序尝试，高优先级提供者失败时尝试下一个
    """
    
    def __init__(self, config: FailoverConfig, provider_priorities: Dict[str, int]):
        super().__init__(config)
        self.provider_priorities = provider_priorities
    
    async def select_next_provider(
        self,
        current_provider: str,
        available_providers: List[str],
        failure_type: FailureType
    ) -> Optional[str]:
        if not self.should_failover(current_provider, failure_type):
            return None
        
        # 按优先级排序
        sorted_providers = sorted(
            available_providers,
            key=lambda p: self.provider_priorities.get(p, 0),
            reverse=True
        )
        
        current_index = -1
        for i, provider in enumerate(sorted_providers):
            if provider == current_provider:
                current_index = i
                break
        
        # 查找下一个可用的提供者
        for i in range(current_index + 1, len(sorted_providers)):
            provider = sorted_providers[i]
            state = self.get_provider_state(provider)
            
            if state and not state.is_healthy:
                continue
            
            logger.info(f"优先级故障转移：{current_provider} -> {provider}")
            return provider
        
        return None


class FailoverExecutor:
    """
    故障转移执行器
    
    负责执行带有故障转移逻辑的请求
    """
    
    def __init__(
        self,
        strategy: FailoverStrategy,
        config: FailoverConfig
    ):
        self.strategy = strategy
        self.config = config
        self._attempt = 0
    
    async def execute_with_failover(
        self,
        request_func: Callable[[str], Awaitable[Any]],
        provider_name: str,
        available_providers: List[str],
        detect_failure_type: Callable[[Exception], FailureType]
    ) -> FailoverResult:
        """
        执行带有故障转移的请求
        
        Args:
            request_func: 请求函数，接收提供者名称返回响应
            provider_name: 初始提供者名称
            available_providers: 可用提供者列表
            detect_failure_type: 失败类型检测函数
            
        Returns:
            FailoverResult: 故障转移结果
        """
        start_time = asyncio.get_event_loop().time()
        tried_providers = []
        current_provider = provider_name
        last_error = None
        last_failure_type = None
        
        for attempt in range(self.config.retry_config.max_retries + 1):
            self._attempt = attempt
            tried_providers.append(current_provider)
            
            try:
                # 执行请求
                logger.debug(
                    f"尝试提供者 {current_provider}, "
                    f"第 {attempt + 1} 次尝试"
                )
                
                # 带超时执行
                response = await asyncio.wait_for(
                    request_func(current_provider),
                    timeout=self.config.timeout
                )
                
                # 记录成功
                elapsed = asyncio.get_event_loop().time() - start_time
                self.strategy.record_success(current_provider, elapsed)
                
                return FailoverResult(
                    success=True,
                    provider_name=current_provider,
                    response=response,
                    attempts=attempt + 1,
                    total_time=elapsed,
                    failover_occurred=len(tried_providers) > 1,
                    tried_providers=tried_providers
                )
                
            except asyncio.TimeoutError as e:
                last_error = e
                last_failure_type = FailureType.TIMEOUT
                logger.warning(
                    f"提供者 {current_provider} 请求超时 "
                    f"({self.config.timeout}s)"
                )
                
            except Exception as e:
                last_error = e
                last_failure_type = detect_failure_type(e)
                logger.warning(
                    f"提供者 {current_provider} 请求失败：{last_failure_type.value}, "
                    f"错误：{str(e)}"
                )
            
            # 记录失败
            self.strategy.record_failure(current_provider, last_failure_type)
            
            # 检查是否可以重试
            if attempt < self.config.retry_config.max_retries:
                # 计算延迟
                delay = self.config.retry_config.get_delay(attempt)
                logger.debug(f"等待 {delay:.2f}s 后重试")
                await asyncio.sleep(delay)
                
                # 选择下一个提供者
                next_provider = await self.strategy.select_next_provider(
                    current_provider,
                    available_providers,
                    last_failure_type
                )
                
                if next_provider:
                    current_provider = next_provider
                else:
                    # 没有可用的提供者，使用轮询方式选择
                    for provider in available_providers:
                        if provider not in tried_providers:
                            current_provider = provider
                            break
                    else:
                        # 所有提供者都已尝试
                        break
            else:
                break
        
        # 所有尝试都失败
        elapsed = asyncio.get_event_loop().time() - start_time
        logger.error(
            f"所有提供者尝试失败，总耗时：{elapsed:.2f}s, "
            f"尝试的提供者：{tried_providers}"
        )
        
        return FailoverResult(
            success=False,
            error=str(last_error),
            error_type=last_failure_type,
            attempts=len(tried_providers),
            total_time=elapsed,
            failover_occurred=len(tried_providers) > 1,
            tried_providers=tried_providers
        )


def create_failover_strategy(
    strategy_type: FailoverStrategyType,
    config: Optional[FailoverConfig] = None,
    **kwargs
) -> FailoverStrategy:
    """
    创建故障转移策略
    
    Args:
        strategy_type: 策略类型
        config: 故障转移配置
        **kwargs: 额外参数
        
    Returns:
        FailoverStrategy: 故障转移策略实例
    """
    config = config or FailoverConfig()
    
    if strategy_type == FailoverStrategyType.SEQUENTIAL:
        return SequentialFailoverStrategy(config)
    elif strategy_type == FailoverStrategyType.FAST_FAILOVER:
        return FastFailoverStrategy(config)
    elif strategy_type == FailoverStrategyType.PRIORITY_BASED:
        provider_priorities = kwargs.get("provider_priorities", {})
        return PriorityFailoverStrategy(config, provider_priorities)
    else:
        raise ValueError(f"不支持的故障转移策略：{strategy_type}")


def detect_failure_type(exception: Exception) -> FailureType:
    """
    检测失败类型
    
    Args:
        exception: 异常对象
        
    Returns:
        FailureType: 失败类型
    """
    import aiohttp
    import socket
    
    error_message = str(exception).lower()
    
    # 超时
    if isinstance(exception, asyncio.TimeoutError):
        return FailureType.TIMEOUT
    
    # 网络错误
    if isinstance(exception, (aiohttp.ClientError, socket.error)):
        if "connection" in error_message or "network" in error_message:
            return FailureType.NETWORK_ERROR
    
    # 服务不可用
    if isinstance(exception, aiohttp.ClientResponseError):
        if exception.status == 503:
            return FailureType.SERVICE_UNAVAILABLE
        elif exception.status == 429:
            return FailureType.RATE_LIMITED
        elif exception.status >= 500:
            return FailureType.SERVER_ERROR
    
    # 认证错误
    if isinstance(exception, aiohttp.ClientResponseError):
        if exception.status in [401, 403]:
            return FailureType.AUTHENTICATION_ERROR
    
    # 根据错误消息判断
    if "timeout" in error_message:
        return FailureType.TIMEOUT
    elif "connection" in error_message:
        return FailureType.NETWORK_ERROR
    elif "503" in error_message or "unavailable" in error_message:
        return FailureType.SERVICE_UNAVAILABLE
    elif "429" in error_message or "rate limit" in error_message:
        return FailureType.RATE_LIMITED
    elif "401" in error_message or "403" in error_message or "auth" in error_message:
        return FailureType.AUTHENTICATION_ERROR
    elif "500" in error_message or "502" in error_message or "504" in error_message:
        return FailureType.SERVER_ERROR
    
    return FailureType.UNKNOWN
