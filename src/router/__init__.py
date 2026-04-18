"""
路由器模块

多来源 API 路由核心，包括：
- 提供者管理器：管理多个 API 提供者
- 请求转换器：转换客户端请求到上游 API 格式
- 响应转换器：转换上游 API 响应到客户端格式
- 路由决策器：实现基于模型的路由逻辑
"""

from .provider_manager import (
    ProviderManager,
    ProviderConfig,
    ProviderType,
    APIProvider,
)

from .request_transformer import (
    ClientRequest,
    TransformedRequest,
    RequestTransformer,
    RequestTransformerFactory,
    OpenAIRequestTransformer,
    AnthropicRequestTransformer,
    RawRequestTransformer,
    transform_request,
    create_request_transformer,
)

from .response_transformer import (
    UnifiedResponse,
    StreamChunk,
    ErrorResponse,
    UsageInfo,
    ChatMessage,
    ChatChoice,
    ResponseStatus,
    ResponseTransformer,
    ResponseTransformerFactory,
    OpenAIResponseTransformer,
    AnthropicResponseTransformer,
    RawResponseTransformer,
    transform_response,
    transform_error,
    create_response_transformer,
)

from .router import (
    Router,
    AsyncRouter,
    RouterConfig,
    RoutingResult,
    create_router,
    create_async_router,
)

__all__ = [
    # 提供者管理
    "ProviderManager",
    "ProviderConfig",
    "ProviderType",
    "APIProvider",
    # 请求转换
    "ClientRequest",
    "TransformedRequest",
    "RequestTransformer",
    "RequestTransformerFactory",
    "OpenAIRequestTransformer",
    "AnthropicRequestTransformer",
    "RawRequestTransformer",
    "transform_request",
    "create_request_transformer",
    # 响应转换
    "UnifiedResponse",
    "StreamChunk",
    "ErrorResponse",
    "UsageInfo",
    "ChatMessage",
    "ChatChoice",
    "ResponseStatus",
    "ResponseTransformer",
    "ResponseTransformerFactory",
    "OpenAIResponseTransformer",
    "AnthropicResponseTransformer",
    "RawResponseTransformer",
    "transform_response",
    "transform_error",
    "create_response_transformer",
    # 路由
    "Router",
    "AsyncRouter",
    "RouterConfig",
    "RoutingResult",
    "create_router",
    "create_async_router",
]
