"""
流式转发器模块

负责转发流式请求和响应，支持异步流式处理，
实现实时转发，无缓冲延迟。
"""

from typing import Dict, Any, Optional, AsyncIterator, Union, Callable, Awaitable
from dataclasses import dataclass, field
import logging
import asyncio
from contextlib import asynccontextmanager

import httpx

from .provider_manager import APIProvider
from .request_transformer import ClientRequest, TransformedRequest
from .response_transformer import StreamChunk, ResponseTransformerFactory
try:
    from ..utils.sse_parser import SSEParser, SSEEvent, StreamingSSEParser
    from ..utils.exceptions import StreamingError, UpstreamAPIError
except (ImportError, ValueError):
    from utils.sse_parser import SSEParser, SSEEvent, StreamingSSEParser
    from utils.exceptions import StreamingError, UpstreamAPIError

logger = logging.getLogger(__name__)


@dataclass
class StreamingConfig:
    """流式传输配置"""
    buffer_size: int = 4096
    chunk_timeout: float = 30.0
    connect_timeout: float = 10.0
    max_retries: int = 3
    retry_delay: float = 1.0
    enable_compression: bool = True
    keep_alive: bool = True


@dataclass
class StreamContext:
    """流式传输上下文"""
    provider: APIProvider
    request: TransformedRequest
    config: StreamingConfig
    stream_id: str = ""
    start_time: float = 0.0
    chunks_sent: int = 0
    bytes_sent: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class StreamingProxy:
    """
    流式代理
    
    负责将客户端的流式请求转发到上游 API，
    并将上游的流式响应实时转发回客户端。
    
    特性：
    - 异步流式处理
    - 实时转发，无缓冲延迟
    - 支持 SSE 格式解析
    - 自动重试机制
    - 流式传输统计
    """

    def __init__(self, config: Optional[StreamingConfig] = None):
        self.config = config or StreamingConfig()
        self._parser = SSEParser()
        self._streaming_parser = StreamingSSEParser(
            buffer_size=self.config.buffer_size
        )
        self._response_transformer_factory = ResponseTransformerFactory()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        # 创建 HTTP 客户端，对于 HTTPS 连接禁用 SSL 验证
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                timeout=self.config.chunk_timeout,
                connect=self.config.connect_timeout,
            ),
            follow_redirects=False,
            verify=False,  # 禁用 SSL 验证以支持自签名证书
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def forward_stream(
        self,
        request: TransformedRequest,
        provider: APIProvider,
        chunk_handler: Optional[Callable[[StreamChunk], Awaitable[None]]] = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        转发流式请求
        
        Args:
            request: 转换后的请求
            provider: 提供者信息
            chunk_handler: 可选的块处理回调
            
        Yields:
            转换后的流式块
            
        Raises:
            StreamingError: 流式传输错误
            UpstreamAPIError: 上游 API 错误
        """
        context = StreamContext(
            provider=provider,
            request=request,
            config=self.config,
            stream_id=self._generate_stream_id(),
        )
        
        logger.info(f"开始流式转发：{context.stream_id}, 提供者={provider.name}")
        
        retry_count = 0
        last_error = None
        
        while retry_count <= self.config.max_retries:
            try:
                async for chunk in self._send_stream_request(context):
                    if chunk_handler:
                        await chunk_handler(chunk)
                    yield chunk
                
                logger.info(f"流式传输完成：{context.stream_id}, 发送块数={context.chunks_sent}")
                return
                
            except (httpx.ReadTimeout, httpx.ConnectError) as e:
                last_error = e
                retry_count += 1
                logger.warning(
                    f"流式传输错误（重试 {retry_count}/{self.config.max_retries}）: {e}"
                )
                
                if retry_count <= self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay * retry_count)
                else:
                    logger.error(f"流式传输失败，已达最大重试次数：{e}")
                    raise UpstreamAPIError(
                        f"流式传输失败：{str(e)}",
                        status_code=503,
                        provider_type=provider.provider_type,
                    ) from e
                    
            except Exception as e:
                logger.error(f"流式传输异常：{e}")
                raise StreamingError(
                    f"流式传输异常：{str(e)}",
                    provider_type=provider.provider_type,
                ) from e

    async def _send_stream_request(
        self, context: StreamContext
    ) -> AsyncIterator[StreamChunk]:
        """
        发送流式请求到上游 API
        
        Args:
            context: 流式上下文
            
        Yields:
            转换后的流式块
        """
        if not self._client:
            raise StreamingError("HTTP 客户端未初始化")
        
        try:
            # 构建请求
            request_kwargs = context.request.to_http_kwargs()
            # 移除 method 键，因为会通过位置参数传递
            request_kwargs.pop("method", None)
            
            logger.debug(
                f"发送流式请求到：{context.request.url}, "
                f"方法：{context.request.method}"
            )
            
            # 发送请求
            async with self._client.stream(
                context.request.method,
                context.request.url,
                **request_kwargs,
            ) as response:
                logger.debug(
                    f"收到流式响应：状态码={response.status_code}, "
                    f"headers={dict(response.headers)}"
                )
                
                # 检查响应状态
                if response.status_code != 200:
                    error_body = await response.aread()
                    raise UpstreamAPIError(
                        f"上游 API 错误：{response.status_code}",
                        status_code=response.status_code,
                        provider_type=context.provider.provider_type,
                        response_body=error_body.decode('utf-8', errors='ignore'),
                    )
                
                # 解析流式响应
                async for chunk in self._parse_stream_response(response, context):
                    yield chunk
                    
        except httpx.HTTPError as e:
            logger.error(f"HTTP 错误：{e}")
            raise
        except Exception as e:
            logger.error(f"解析流式响应失败：{e}")
            raise StreamingError(
                f"解析流式响应失败：{str(e)}",
                provider_type=context.provider.provider_type,
            ) from e

    async def _parse_stream_response(
        self,
        response: httpx.Response,
        context: StreamContext,
    ) -> AsyncIterator[StreamChunk]:
        """
        解析流式响应
        
        Args:
            response: HTTP 响应
            context: 流式上下文
            
        Yields:
            转换后的流式块
        """
        transformer = self._response_transformer_factory.get_transformer(
            context.provider.provider_type
        )
        
        # 检查是否为 SSE 格式
        content_type = response.headers.get("content-type", "").lower()
        is_sse = "text/event-stream" in content_type
        
        logger.debug(f"响应内容类型：{content_type}, 是 SSE: {is_sse}")
        
        if is_sse:
            # SSE 格式解析
            async for event in self._parse_sse_stream(response):
                if event.is_done():
                    logger.debug("收到流式结束标记")
                    break
                
                # 转换 SSE 事件为 StreamChunk
                chunk = transformer.transform_stream_chunk(
                    event.data,
                    context.provider,
                )
                
                if chunk:
                    context.chunks_sent += 1
                    context.bytes_sent += len(event.data)
                    yield chunk
        else:
            # 非 SSE 格式（可能是 NDJSON 或其他）
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                
                # 尝试解析为 SSE 或直接处理
                if line.startswith("data: "):
                    line = line[6:]
                
                chunk = transformer.transform_stream_chunk(
                    line,
                    context.provider,
                )
                
                if chunk:
                    context.chunks_sent += 1
                    context.bytes_sent += len(line)
                    yield chunk

    async def _parse_sse_stream(
        self, response: httpx.Response
    ) -> AsyncIterator[SSEEvent]:
        """
        解析 SSE 流
        
        Args:
            response: HTTP 响应
            
        Yields:
            SSE 事件
        """
        async for chunk in response.aiter_bytes(self.config.buffer_size):
            events = self._streaming_parser.feed(chunk)
            for event in events:
                yield event
        
        # 处理缓冲区剩余数据
        remaining = self._streaming_parser._buffer
        if remaining.strip():
            events = self._streaming_parser.feed("\n\n")
            for event in events:
                yield event

    def _generate_stream_id(self) -> str:
        """生成流式 ID"""
        import uuid
        return f"stream_{uuid.uuid4().hex[:12]}"

    def get_stream_stats(self, context: StreamContext) -> Dict[str, Any]:
        """
        获取流式传输统计
        
        Args:
            context: 流式上下文
            
        Returns:
            统计信息字典
        """
        return {
            "stream_id": context.stream_id,
            "provider": context.provider.name,
            "chunks_sent": context.chunks_sent,
            "bytes_sent": context.bytes_sent,
            "duration": asyncio.get_event_loop().time() - context.start_time,
        }


class StreamForwarder:
    """
    流式转发器（高级封装）
    
    提供更高级的流式转发接口，支持：
    - 自动连接管理
    - 流式故障转移
    - 并发流式处理
    """

    def __init__(self, config: Optional[StreamingConfig] = None):
        self.config = config or StreamingConfig()
        self._proxies: Dict[str, StreamingProxy] = {}

    async def forward_with_fallback(
        self,
        request: TransformedRequest,
        providers: list[APIProvider],
        chunk_handler: Optional[Callable[[StreamChunk], Awaitable[None]]] = None,
        enable_internal_retries: bool = True,
    ) -> AsyncIterator[StreamChunk]:
        """
        带故障转移的流式转发
        
        Args:
            request: 转换后的请求
            providers: 提供者列表（按优先级排序）
            chunk_handler: 块处理回调
            enable_internal_retries: 是否启用每个提供者内部的重试机制
            
        Yields:
            流式块
            
        Raises:
            StreamingError: 所有提供者都失败
        """
        last_error = None
        
        for provider in providers:
            try:
                logger.info(f"尝试流式转发到提供者：{provider.name}")
                
                # 如果不启用内部重试，临时修改配置
                original_max_retries = self.config.max_retries
                if not enable_internal_retries:
                    self.config.max_retries = 0
                
                async with StreamingProxy(self.config) as proxy:
                    async for chunk in proxy.forward_stream(
                        request, provider, chunk_handler
                    ):
                        yield chunk
                
                # 恢复配置
                self.config.max_retries = original_max_retries
                
                # 成功则返回
                return
                
            except Exception as e:
                # 恢复配置
                self.config.max_retries = original_max_retries
                
                last_error = e
                logger.warning(
                    f"提供者 {provider.name} 流式失败：{e}, "
                    f"尝试下一个提供者"
                )
                provider.mark_unhealthy()
        
        # 所有提供者都失败
        raise StreamingError(
            f"所有提供者流式失败：{last_error}",
            providers=[p.name for p in providers],
        )

    async def forward_concurrent_streams(
        self,
        requests: list[tuple[TransformedRequest, APIProvider]],
        merge_handler: Optional[Callable[[StreamChunk, APIProvider], Awaitable[None]]] = None,
    ) -> AsyncIterator[tuple[StreamChunk, APIProvider]]:
        """
        并发流式转发多个请求
        
        Args:
            requests: (请求，提供者) 元组列表
            merge_handler: 合并处理回调
            
        Yields:
            (流式块，提供者) 元组
        """
        tasks = []
        
        for request, provider in requests:
            task = asyncio.create_task(
                self._forward_single_stream(request, provider)
            )
            tasks.append((task, provider))
        
        # 使用队列收集结果
        queue = asyncio.Queue()
        
        async def collect_results(task, provider):
            try:
                async for chunk in task:
                    await queue.put((chunk, provider))
            except Exception as e:
                logger.error(f"并发流式错误：{e}")
            finally:
                await queue.put(None)  # 结束标记
        
        # 启动收集任务
        collector_tasks = [
            asyncio.create_task(collect_results(task, provider))
            for task, provider in tasks
        ]
        
        # 从队列中获取结果
        finished = 0
        while finished < len(tasks):
            item = await queue.get()
            if item is None:
                finished += 1
                continue
            
            chunk, provider = item
            if merge_handler:
                await merge_handler(chunk, provider)
            yield chunk
        
        # 等待所有任务完成
        await asyncio.gather(*collector_tasks, return_exceptions=True)

    async def _forward_single_stream(
        self, request: TransformedRequest, provider: APIProvider
    ) -> AsyncIterator[StreamChunk]:
        """转发单个流式请求"""
        async with StreamingProxy(self.config) as proxy:
            async for chunk in proxy.forward_stream(request, provider):
                yield chunk


@asynccontextmanager
async def create_streaming_proxy(config: Optional[StreamingConfig] = None):
    """
    创建流式代理的上下文管理器
    
    Usage:
        async with create_streaming_proxy() as proxy:
            async for chunk in proxy.forward_stream(request, provider):
                yield chunk
    """
    proxy = StreamingProxy(config or StreamingConfig())
    try:
        await proxy.__aenter__()
        yield proxy
    finally:
        await proxy.__aexit__(None, None, None)


async def forward_stream_request(
    request: TransformedRequest,
    provider: APIProvider,
    config: Optional[StreamingConfig] = None,
) -> AsyncIterator[StreamChunk]:
    """
    便捷函数：转发流式请求
    
    Args:
        request: 转换后的请求
        provider: 提供者信息
        config: 流式配置
        
    Yields:
        流式块
    """
    async with create_streaming_proxy(config) as proxy:
        async for chunk in proxy.forward_stream(request, provider):
            yield chunk
