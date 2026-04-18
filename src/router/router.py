"""
路由决策器模块

实现基于模型的路由逻辑，处理特殊模型（如"auto"），
整合提供者管理器、请求转换器和响应转换器。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union, AsyncIterator, Callable, Awaitable
import logging
from contextlib import asynccontextmanager
import asyncio

from .provider_manager import (
    ProviderManager,
    ProviderConfig,
    ProviderType,
    APIProvider,
)
from .request_transformer import (
    ClientRequest,
    TransformedRequest,
    RequestTransformerFactory,
    transform_request,
)
from .response_transformer import (
    UnifiedResponse,
    StreamChunk,
    ErrorResponse,
    ResponseTransformerFactory,
    transform_response,
    transform_error,
)
from .streaming_proxy import (
    StreamingProxy,
    StreamingConfig,
    StreamForwarder,
    forward_stream_request,
    StreamingError,
)
from .failover import (
    FailoverConfig,
    FailoverResult,
    FailoverExecutor,
    FailoverStrategyType,
    FailoverStrategy,
    FailureType,
    RetryConfig,
    create_failover_strategy,
    detect_failure_type,
)
from .health_check import (
    HealthChecker,
    HealthCheckConfig,
    HealthStatus,
    PassiveHealthChecker,
)

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    """路由结果数据类"""
    success: bool
    provider: Optional[APIProvider] = None
    transformed_request: Optional[TransformedRequest] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RouterConfig:
    """路由器配置"""
    default_timeout: int = 30
    max_retries: int = 3
    enable_fallback: bool = True
    enable_health_check: bool = True
    health_check_interval: int = 60
    log_requests: bool = True
    log_responses: bool = False
    # 故障转移配置
    enable_failover: bool = True
    failover_strategy: FailoverStrategyType = FailoverStrategyType.SEQUENTIAL
    failover_timeout: float = 30.0
    failover_max_retries: int = 3
    failover_initial_delay: float = 1.0
    failover_max_delay: float = 60.0
    auto_failover: bool = True  # auto 模型自动故障转移


class Router:
    """
    API 路由器
    
    核心路由决策组件，负责：
    - 接收客户端请求
    - 选择合适的提供者
    - 转换请求和响应
    - 处理错误和重试
    - 故障转移和自动切换
    """

    def __init__(self, config: Optional[RouterConfig] = None):
        self.config = config or RouterConfig()
        self.provider_manager = ProviderManager()
        self.request_transformer_factory = RequestTransformerFactory()
        self.response_transformer_factory = ResponseTransformerFactory()
        self._request_log: List[Dict[str, Any]] = []
        self.streaming_config = StreamingConfig()
        self.stream_forwarder = StreamForwarder(self.streaming_config)
        
        # 初始化故障转移组件
        self._init_failover_components()
        
        # 初始化健康检查组件
        self._init_health_check_components()
    
    def _init_failover_components(self):
        """初始化故障转移组件"""
        if self.config.enable_failover:
            retry_config = RetryConfig(
                max_retries=self.config.failover_max_retries,
                initial_delay=self.config.failover_initial_delay,
                max_delay=self.config.failover_max_delay,
            )
            
            failover_config = FailoverConfig(
                strategy=self.config.failover_strategy,
                timeout=self.config.failover_timeout,
                retry_config=retry_config,
                enabled=self.config.enable_failover,
            )
            
            self.failover_strategy = create_failover_strategy(
                self.config.failover_strategy,
                failover_config
            )
            
            self.failover_executor = FailoverExecutor(
                self.failover_strategy,
                failover_config
            )
            
            logger.info(f"初始化故障转移：策略={self.config.failover_strategy.value}")
        else:
            self.failover_strategy = None
            self.failover_executor = None
    
    def _init_health_check_components(self):
        """初始化健康检查组件"""
        if self.config.enable_health_check:
            health_check_config = HealthCheckConfig(
                enabled=True,
                interval=self.config.health_check_interval,
                timeout=self.config.default_timeout,
                passive_check_enabled=True,
            )
            
            self.health_checker = HealthChecker(health_check_config)
            self.passive_health_checker = PassiveHealthChecker(health_check_config)
            
            logger.info("初始化健康检查组件")
        else:
            self.health_checker = None
            self.passive_health_checker = None

    def add_provider(self, config: ProviderConfig) -> APIProvider:
        """
        添加 API 提供者
        
        Args:
            config: 提供者配置
            
        Returns:
            创建的提供者实例
        """
        provider = self.provider_manager.add_provider(config)
        logger.info(f"路由器添加提供者：{provider.name} ({provider.provider_type.value})")
        
        # 初始化健康检查
        if self.health_checker:
            self.health_checker.initialize_provider(
                provider.name,
                provider.base_url
            )
        
        return provider

    def remove_provider(self, name: str) -> bool:
        """移除提供者"""
        return self.provider_manager.remove_provider(name)

    def get_provider(self, name: str) -> Optional[APIProvider]:
        """获取提供者"""
        return self.provider_manager.get_provider(name)

    def route_request(self, client_request: ClientRequest) -> RoutingResult:
        """
        路由客户端请求
        
        核心路由逻辑：
        1. 根据模型名称选择提供者
        2. 转换请求格式
        3. 返回路由结果
        
        Args:
            client_request: 客户端请求
            
        Returns:
            路由结果
        """
        model_name = client_request.model
        logger.info(f"收到请求：模型={model_name}, 流式={client_request.stream}")

        # 记录请求日志
        if self.config.log_requests:
            self._log_request(client_request)

        # 1. 选择提供者
        provider = self.provider_manager.select_provider_for_model(model_name)
        if not provider:
            logger.error(f"无法为模型 {model_name} 找到合适的提供者")
            return RoutingResult(
                success=False,
                error=f"没有可用的提供者处理模型：{model_name}",
                error_code="no_provider",
            )

        logger.info(f"选择提供者：{provider.name} (类型：{provider.provider_type.value})")

        # 2. 转换请求
        try:
            transformed_request = self.request_transformer_factory.transform(
                client_request, provider
            )
        except Exception as e:
            logger.error(f"请求转换失败：{e}")
            return RoutingResult(
                success=False,
                provider=provider,
                error=f"请求转换失败：{str(e)}",
                error_code="transform_error",
            )

        # 3. 返回路由结果
        return RoutingResult(
            success=True,
            provider=provider,
            transformed_request=transformed_request,
            metadata={
                "model": model_name,
                "provider_type": provider.provider_type.value,
            },
        )

    async def route_stream_request(
        self, client_request: ClientRequest
    ) -> AsyncIterator[StreamChunk]:
        """
        路由流式请求
        
        支持流式模式的请求路由，实时转发上游的流式响应
        
        Args:
            client_request: 客户端流式请求
            
        Yields:
            转换后的流式块
        """
        # 确保请求标记为流式
        client_request.stream = True
        
        # 路由请求
        routing_result = self.route_request(client_request)
        
        if not routing_result.success:
            raise ValueError(f"路由失败：{routing_result.error}")
        
        provider = routing_result.provider
        transformed_request = routing_result.transformed_request
        
        logger.info(
            f"开始流式路由：模型={client_request.model}, "
            f"提供者={provider.name}"
        )
        
        try:
            # 转发流式请求
            async for chunk in self.stream_forwarder.forward_stream(
                transformed_request, provider
            ):
                yield chunk
                
        except Exception as e:
            logger.error(f"流式路由失败：{e}")
            # 标记提供者为不健康
            provider.mark_unhealthy()
            raise

    def process_response(
        self, raw_response: Dict[str, Any], provider: APIProvider
    ) -> UnifiedResponse:
        """
        处理上游响应
        
        Args:
            raw_response: 上游 API 的原始响应
            provider: 提供者信息
            
        Returns:
            统一响应对象
        """
        try:
            unified_response = self.response_transformer_factory.transform(
                raw_response, provider
            )
            unified_response.model = provider.config.name

            if self.config.log_responses:
                self._log_response(unified_response)

            return unified_response

        except Exception as e:
            logger.error(f"响应处理失败：{e}")
            return UnifiedResponse(
                id="",
                model="",
                status=UnifiedResponse.status.__class__.ERROR,
                error=f"响应处理失败：{str(e)}",
                error_code="process_error",
                provider_type=provider.provider_type,
            )

    def process_error(
        self, error: Exception, status_code: int = 500, provider: Optional[APIProvider] = None
    ) -> ErrorResponse:
        """
        处理错误
        
        Args:
            error: 异常对象
            status_code: HTTP 状态码
            provider: 提供者信息
            
        Returns:
            错误响应对象
        """
        logger.error(f"处理错误：{error} (状态码：{status_code})")
        return self.response_transformer_factory.transform_error(
            error, status_code, provider
        )

    def mark_provider_unhealthy(self, provider_name: str):
        """标记提供者为不健康"""
        provider = self.provider_manager.get_provider(provider_name)
        if provider:
            provider.mark_unhealthy()

    def mark_provider_healthy(self, provider_name: str):
        """标记提供者为健康"""
        provider = self.provider_manager.get_provider(provider_name)
        if provider:
            provider.mark_healthy()

    def _log_request(self, request: ClientRequest):
        """记录请求日志"""
        log_entry = {
            "timestamp": self._get_timestamp(),
            "model": request.model,
            "stream": request.stream,
            "message_count": len(request.messages),
        }
        self._request_log.append(log_entry)
        logger.debug(f"请求日志：{log_entry}")

    def _log_response(self, response: UnifiedResponse):
        """记录响应日志"""
        logger.debug(
            f"响应日志：ID={response.id}, "
            f"模型={response.model}, "
            f"选择数={len(response.choices)}"
        )

    def _get_timestamp(self) -> str:
        """获取时间戳字符串"""
        from datetime import datetime
        return datetime.now().isoformat()

    def get_status(self) -> Dict[str, Any]:
        """获取路由器状态"""
        providers = self.provider_manager.get_all_providers()
        healthy_count = len(self.provider_manager.get_healthy_providers())

        status = {
            "total_providers": len(providers),
            "healthy_providers": healthy_count,
            "enabled_providers": len(self.provider_manager.get_enabled_providers()),
            "default_provider": self.provider_manager.get_default_provider().name if self.provider_manager.get_default_provider() else None,
            "request_count": len(self._request_log),
        }
        
        # 添加故障转移状态
        if self.failover_strategy:
            status["failover_enabled"] = True
            status["failover_strategy"] = self.config.failover_strategy.value
        
        # 添加健康检查状态
        if self.health_checker:
            status["health_check"] = self.health_checker.get_status_summary()
        
        return status

    def clear(self):
        """清空路由器状态"""
        self.provider_manager.clear()
        self._request_log.clear()
        
        # 清空健康检查
        if self.health_checker:
            self.health_checker.clear()
        
        logger.info("路由器已清空")


class AsyncRouter(Router):
    """
    异步路由器
    
    支持异步请求处理和流式响应，集成故障转移机制
    """

    async def route_request_async(
        self, client_request: ClientRequest
    ) -> RoutingResult:
        """异步路由请求"""
        return self.route_request(client_request)
    
    async def execute_with_failover(
        self,
        request_func: Callable[[str], Awaitable[Any]],
        model_name: str,
        provider: Optional[APIProvider] = None
    ) -> FailoverResult:
        """
        执行带故障转移的请求
        
        Args:
            request_func: 请求函数，接收提供者名称
            model_name: 模型名称
            provider: 初始提供者（可选）
            
        Returns:
            FailoverResult: 故障转移结果
        """
        if not self.config.enable_failover or not self.failover_executor:
            # 不使用故障转移，直接执行
            try:
                provider_name = provider.name if provider else "unknown"
                response = await request_func(provider_name)
                return FailoverResult(
                    success=True,
                    provider_name=provider_name,
                    response=response,
                    attempts=1,
                    total_time=0.0
                )
            except Exception as e:
                return FailoverResult(
                    success=False,
                    error=str(e),
                    error_type=detect_failure_type(e),
                    attempts=1,
                    total_time=0.0
                )
        
        # 确定初始提供者
        if not provider:
            selected_provider = self.provider_manager.select_provider_for_model(model_name)
            if not selected_provider:
                return FailoverResult(
                    success=False,
                    error=f"没有可用的提供者处理模型：{model_name}",
                    error_type=FailureType.SERVICE_UNAVAILABLE,
                    attempts=0
                )
        else:
            selected_provider = provider
        
        # 获取可用提供者列表
        available_providers = [
            p.name for p in self.provider_manager.get_healthy_providers()
        ]
        
        if not available_providers:
            available_providers = [
                p.name for p in self.provider_manager.get_enabled_providers()
            ]
        
        # 执行带故障转移的请求
        result = await self.failover_executor.execute_with_failover(
            request_func=request_func,
            provider_name=selected_provider.name,
            available_providers=available_providers,
            detect_failure_type=detect_failure_type
        )
        
        # 更新健康状态
        if self.passive_health_checker:
            for tried_provider in result.tried_providers:
                if tried_provider == result.provider_name and result.success:
                    self.passive_health_checker.record_request(
                        tried_provider,
                        success=True,
                        response_time=result.total_time / result.attempts
                    )
                else:
                    self.passive_health_checker.record_request(
                        tried_provider,
                        success=False,
                        response_time=0.0
                    )
        
        return result
    
    async def send_request_with_auto_failover(
        self,
        client_request: ClientRequest,
        send_func: Callable[[TransformedRequest, APIProvider], Awaitable[Any]]
    ) -> Dict[str, Any]:
        """
        发送请求并自动故障转移
        
        专为 auto 模型设计，支持在多个提供者之间自动切换
        
        Args:
            client_request: 客户端请求
            send_func: 发送函数，接收转换后的请求和提供者
            
        Returns:
            Dict[str, Any]: 响应数据
            
        Raises:
            Exception: 当所有提供者都失败时抛出异常
        """
        model_name = client_request.model
        is_auto_model = model_name.lower() == "auto"
        
        logger.info(
            f"发送带自动故障转移的请求：模型={model_name}, "
            f"auto={is_auto_model}"
        )
        
        # 定义请求执行函数
        async def execute_request(provider_name: str) -> Any:
            """执行单个提供者的请求"""
            provider = self.provider_manager.get_provider(provider_name)
            if not provider:
                raise ValueError(f"提供者不存在：{provider_name}")
            
            # 路由请求
            routing_result = self.route_request(client_request)
            if not routing_result.success:
                raise ValueError(routing_result.error)
            
            # 发送请求
            response = await send_func(
                routing_result.transformed_request,
                provider
            )
            
            return response
        
        # 执行带故障转移的请求
        failover_result = await self.execute_with_failover(
            request_func=execute_request,
            model_name=model_name
        )
        
        if not failover_result.success:
            # 所有提供者都失败
            logger.error(
                f"所有提供者故障转移失败："
                f"尝试的提供者={failover_result.tried_providers}, "
                f"错误={failover_result.error}"
            )
            
            # 抛出异常
            raise Exception(
                f"所有提供者不可用："
                f"{failover_result.error} "
                f"(尝试了 {failover_result.attempts} 个提供者)"
            )
        
        logger.info(
            f"请求成功，提供者={failover_result.provider_name}, "
            f"尝试次数={failover_result.attempts}, "
            f"故障转移={failover_result.failover_occurred}"
        )
        
        return failover_result.response

    async def process_response_async(
        self, raw_response: Dict[str, Any], provider: APIProvider
    ) -> UnifiedResponse:
        """异步处理响应"""
        return self.process_response(raw_response, provider)

    async def process_stream_async(
        self,
        stream_iterator: AsyncIterator[Union[str, bytes, Dict[str, Any]]],
        provider: APIProvider,
    ) -> AsyncIterator[StreamChunk]:
        """
        异步处理流式响应
        
        Args:
            stream_iterator: 流式响应迭代器
            provider: 提供者信息
            
        Yields:
            转换后的流式块
        """
        async for chunk in stream_iterator:
            transformed_chunk = self.response_transformer_factory.transform_stream_chunk(
                chunk, provider
            )
            if transformed_chunk:
                yield transformed_chunk
    
    async def process_stream_chunk_async(
        self,
        chunk: Union[str, bytes, Dict[str, Any]],
        provider: APIProvider,
    ) -> Optional[Dict[str, Any]]:
        """
        异步处理单个流式块
        
        Args:
            chunk: 流式块数据
            provider: 提供者信息
            
        Returns:
            Optional[Dict[str, Any]]: 转换后的数据
        """
        transformed_chunk = self.response_transformer_factory.transform_stream_chunk(
            chunk, provider
        )
        if transformed_chunk and hasattr(transformed_chunk, "to_dict"):
            return transformed_chunk.to_dict()
        return transformed_chunk

    async def route_stream_with_fallback(
        self, client_request: ClientRequest
    ) -> AsyncIterator[StreamChunk]:
        """
        带故障转移的流式路由
        
        当主提供者失败时，自动切换到备用提供者
        
        Args:
            client_request: 客户端流式请求
            
        Yields:
            转换后的流式块
        """
        model_name = client_request.model
        is_auto_model = model_name.lower() == "auto"
        logger.info(f"开始带故障转移的流式路由：模型={model_name}, auto={is_auto_model}")
        
        # 获取所有健康的提供者
        providers = self.provider_manager.get_healthy_providers()
        
        if not providers:
            # 尝试使用所有启用的提供者
            providers = self.provider_manager.get_enabled_providers()
        
        if not providers:
            raise ValueError("没有可用的提供者")
        
        # 如果是特定模型，只选择支持该模型的提供者（不进行故障转移到其他提供者）
        if not is_auto_model:
            # 找到支持该模型的提供者
            supporting_providers = [
                p for p in providers if p.supports_model(model_name)
            ]
            
            if supporting_providers:
                # 显式指定模型时，只尝试优先级最高的那个提供者，不进行故障转移
                providers = [max(supporting_providers, key=lambda p: p.priority)]
                logger.info(f"显式指定模型，只尝试提供者：{providers[0].name}")
            else:
                # 没有找到支持该模型的提供者
                raise ValueError(f"没有提供者支持模型：{model_name}")
        
        # 按优先级排序
        providers = sorted(providers, key=lambda p: p.priority, reverse=True)
        
        logger.info(f"尝试 {len(providers)} 个提供者进行流式故障转移")
        
        last_error = None
        tried_providers = []
        
        for provider in providers:
            tried_providers.append(provider.name)
            
            try:
                logger.info(f"尝试提供者：{provider.name}")
                
                # 创建请求
                client_request.model = model_name
                routing_result = self.route_request(client_request)
                
                if not routing_result.success:
                    logger.warning(f"提供者 {provider.name} 路由失败：{routing_result.error}")
                    continue
                
                # 转发流式请求
                # 如果是显式指定的模型，不启用内部重试，快速失败
                async for chunk in self.stream_forwarder.forward_with_fallback(
                    routing_result.transformed_request,
                    [provider],
                    enable_internal_retries=is_auto_model,
                ):
                    yield chunk
                
                # 成功则标记为健康并返回
                provider.mark_healthy()
                logger.info(f"流式传输成功，提供者：{provider.name}")
                return
                
            except Exception as e:
                last_error = e
                if is_auto_model or len(providers) > 1:
                    logger.warning(
                        f"提供者 {provider.name} 流式失败：{e}, "
                        f"尝试下一个提供者"
                    )
                else:
                    logger.error(
                        f"提供者 {provider.name} 流式失败：{e}, "
                        f"无其他提供者可用"
                    )
                provider.mark_unhealthy()
                
                # 更新健康检查
                if self.passive_health_checker:
                    self.passive_health_checker.record_request(
                        provider.name,
                        success=False,
                        response_time=0.0
                    )
        
        # 所有提供者都失败
        raise StreamingError(
            f"所有提供者流式失败：{last_error}",
            providers=tried_providers,
        )

    @asynccontextmanager
    async def request_context(self, client_request: ClientRequest):
        """
        请求上下文管理器
        
        提供完整的请求处理生命周期管理
        
        Usage:
            async with router.request_context(request) as context:
                # 发送请求到上游
                response = await send_to_upstream(context.transformed_request)
                # 处理响应
                result = await router.process_response_async(response, context.provider)
        """
        routing_result = self.route_request(client_request)

        if not routing_result.success:
            raise ValueError(f"路由失败：{routing_result.error}")

        context = {
            "provider": routing_result.provider,
            "transformed_request": routing_result.transformed_request,
            "metadata": routing_result.metadata,
        }

        try:
            yield context
        except Exception as e:
            logger.error(f"请求上下文处理失败：{e}")
            if routing_result.provider:
                self.mark_provider_unhealthy(routing_result.provider.name)
            raise


def create_router(config: Optional[RouterConfig] = None) -> Router:
    """
    创建路由器实例
    
    Args:
        config: 路由器配置
        
    Returns:
        路由器实例
    """
    return Router(config)


def create_async_router(config: Optional[RouterConfig] = None) -> AsyncRouter:
    """
    创建异步路由器实例
    
    Args:
        config: 路由器配置
        
    Returns:
        异步路由器实例
    """
    return AsyncRouter(config)
