"""
响应转换器模块

负责将上游 API 响应转换为客户端格式，统一错误处理。
支持多种提供者类型的响应格式转换。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union, AsyncIterator
from enum import Enum
import json
import logging
from datetime import datetime

from .provider_manager import ProviderType, APIProvider

logger = logging.getLogger(__name__)


class ResponseStatus(Enum):
    """响应状态枚举"""
    SUCCESS = "success"
    ERROR = "error"
    STREAMING = "streaming"


@dataclass
class UsageInfo:
    """Token 使用信息"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str
    content: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"role": self.role}
        if self.content is not None:
            result["content"] = self.content
        if self.function_call:
            result["function_call"] = self.function_call
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        return result


@dataclass
class ChatChoice:
    """聊天选择项"""
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "index": self.index,
            "message": self.message.to_dict(),
        }
        if self.finish_reason:
            result["finish_reason"] = self.finish_reason
        return result


@dataclass
class UnifiedResponse:
    """
    统一响应数据类
    
    标准化的响应格式，无论上游 API 是什么格式
    """
    id: str
    object: str = "chat.completion"
    created: int = field(default_factory=lambda: int(datetime.now().timestamp()))
    model: str = ""
    choices: List[ChatChoice] = field(default_factory=list)
    usage: Optional[UsageInfo] = None
    status: ResponseStatus = ResponseStatus.SUCCESS
    provider_type: Optional[ProviderType] = None
    raw_response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "id": self.id,
            "object": self.object,
            "created": self.created,
            "model": self.model,
            "choices": [choice.to_dict() for choice in self.choices],
        }

        if self.usage:
            result["usage"] = self.usage.to_dict()

        if self.metadata:
            result["_metadata"] = self.metadata

        if self.error:
            result["error"] = {
                "message": self.error,
                "code": self.error_code,
            }

        return result

    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class StreamChunk:
    """流式响应块"""
    id: str
    object: str = "chat.completion.chunk"
    created: int = field(default_factory=lambda: int(datetime.now().timestamp()))
    model: str = ""
    choices: List[Dict[str, Any]] = field(default_factory=list)
    provider_type: Optional[ProviderType] = None
    usage: Optional[UsageInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "object": self.object,
            "created": self.created,
            "model": self.model,
            "choices": self.choices,
        }
        if self.usage:
            result["usage"] = self.usage.to_dict()
        return result

    def to_sse(self) -> str:
        """转换为 Server-Sent Events 格式"""
        return f"data: {json.dumps(self.to_dict(), ensure_ascii=False)}\n\n"

    def is_done(self) -> bool:
        """检查是否为结束块"""
        return any(
            choice.get("finish_reason") is not None
            for choice in self.choices
        )

    def get_content(self) -> str:
        """获取内容文本"""
        content = ""
        for choice in self.choices:
            delta = choice.get("delta", {})
            if delta and delta.get("content"):
                content += delta["content"]
        return content

    def get_role(self) -> Optional[str]:
        """获取角色信息"""
        for choice in self.choices:
            delta = choice.get("delta", {})
            if delta and delta.get("role"):
                return delta["role"]
        return None


@dataclass
class ErrorResponse:
    """错误响应"""
    error: str
    error_code: str
    status_code: int = 500
    provider_type: Optional[ProviderType] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "error": {
                "message": self.error,
                "type": "api_error",
                "code": self.error_code,
            }
        }
        if self.details:
            result["error"]["details"] = self.details
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class ResponseTransformer(ABC):
    """响应转换器抽象基类"""

    @abstractmethod
    def transform(self, response: Dict[str, Any], provider: APIProvider) -> UnifiedResponse:
        """
        转换上游响应为统一格式
        
        Args:
            response: 上游 API 的原始响应
            provider: 提供者信息
            
        Returns:
            统一响应对象
        """
        pass

    @abstractmethod
    def transform_stream_chunk(
        self, chunk: Union[str, bytes, Dict[str, Any]], provider: APIProvider
    ) -> Optional[StreamChunk]:
        """
        转换流式响应块
        
        Args:
            chunk: 流式响应块
            provider: 提供者信息
            
        Returns:
            转换后的流式块，None 表示结束
        """
        pass

    @abstractmethod
    def supports_provider(self, provider_type: ProviderType) -> bool:
        """检查是否支持指定类型的提供者"""
        pass

    @abstractmethod
    def transform_error(
        self, error: Exception, status_code: int = 500, provider: Optional[APIProvider] = None
    ) -> ErrorResponse:
        """
        转换错误为统一错误格式
        
        Args:
            error: 异常对象
            status_code: HTTP 状态码
            provider: 提供者信息
            
        Returns:
            错误响应对象
        """
        pass


class OpenAIResponseTransformer(ResponseTransformer):
    """OpenAI 格式响应转换器"""

    def supports_provider(self, provider_type: ProviderType) -> bool:
        return provider_type in [ProviderType.OPENAI, ProviderType.AZURE]

    def transform(self, response: Dict[str, Any], provider: APIProvider) -> UnifiedResponse:
        """转换 OpenAI 响应为统一格式"""
        try:
            # 解析响应
            response_id = response.get("id", "")
            model = response.get("model", "")
            choices_data = response.get("choices", [])
            usage_data = response.get("usage", {})

            # 转换选择项
            choices = []
            for choice_data in choices_data:
                message_data = choice_data.get("message", {})
                message = ChatMessage(
                    role=message_data.get("role", "assistant"),
                    content=message_data.get("content"),
                    function_call=message_data.get("function_call"),
                    tool_calls=message_data.get("tool_calls"),
                )
                choice = ChatChoice(
                    index=choice_data.get("index", 0),
                    message=message,
                    finish_reason=choice_data.get("finish_reason"),
                )
                choices.append(choice)

            # 转换使用量信息
            usage = None
            if usage_data:
                usage = UsageInfo(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                )

            return UnifiedResponse(
                id=response_id,
                model=model,
                choices=choices,
                usage=usage,
                provider_type=provider.provider_type,
                raw_response=response,
            )

        except Exception as e:
            logger.error(f"转换 OpenAI 响应失败：{e}")
            return self._create_error_response(str(e), provider)

    def transform_stream_chunk(
        self, chunk: Union[str, bytes, Dict[str, Any]], provider: APIProvider
    ) -> Optional[StreamChunk]:
        """转换 OpenAI 流式响应块"""
        try:
            # 解析 chunk 数据
            if isinstance(chunk, (str, bytes)):
                chunk_str = chunk.decode() if isinstance(chunk, bytes) else chunk
                if chunk_str.strip() == "[DONE]":
                    return None
                if chunk_str.startswith("data: "):
                    chunk_str = chunk_str[6:]
                chunk_data = json.loads(chunk_str)
            else:
                chunk_data = chunk

            # 检查是否为结束标记
            choices_data = chunk_data.get("choices", [])
            if choices_data and choices_data[0].get("finish_reason") == "stop":
                # 创建结束块
                return StreamChunk(
                    id=chunk_data.get("id", ""),
                    model=chunk_data.get("model", ""),
                    choices=[{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }],
                    provider_type=provider.provider_type,
                )

            # 转换流式块
            choices = []
            for choice_data in choices_data:
                delta = choice_data.get("delta", {})
                choice = {
                    "index": choice_data.get("index", 0),
                    "delta": {
                        "role": delta.get("role"),
                        "content": delta.get("content"),
                    },
                    "finish_reason": choice_data.get("finish_reason"),
                }
                
                # 处理 tool_calls 和 function_call
                if delta.get("tool_calls"):
                    choice["delta"]["tool_calls"] = delta["tool_calls"]
                if delta.get("function_call"):
                    choice["delta"]["function_call"] = delta["function_call"]
                
                choices.append(choice)

            # 处理 usage 信息（某些提供者在最后一个块中返回）
            usage = None
            usage_data = chunk_data.get("usage")
            if usage_data:
                usage = UsageInfo(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                )

            return StreamChunk(
                id=chunk_data.get("id", ""),
                model=chunk_data.get("model", ""),
                choices=choices,
                provider_type=provider.provider_type,
                usage=usage,
            )

        except Exception as e:
            logger.error(f"转换 OpenAI 流式块失败：{e}")
            return None

    def transform_error(
        self, error: Exception, status_code: int = 500, provider: Optional[APIProvider] = None
    ) -> ErrorResponse:
        """转换 OpenAI 错误响应"""
        error_code = "api_error"
        error_message = str(error)

        # 尝试解析 OpenAI 错误格式
        if hasattr(error, "response"):
            try:
                error_data = error.response.json()
                if "error" in error_data:
                    error_code = error_data["error"].get("code", error_code)
                    error_message = error_data["error"].get("message", error_message)
            except:
                pass

        return ErrorResponse(
            error=error_message,
            error_code=error_code,
            status_code=status_code,
            provider_type=provider.provider_type if provider else None,
        )

    def _create_error_response(self, error_msg: str, provider: APIProvider) -> UnifiedResponse:
        """创建错误响应"""
        return UnifiedResponse(
            id="",
            model="",
            status=ResponseStatus.ERROR,
            error=error_msg,
            error_code="parse_error",
            provider_type=provider.provider_type,
        )


class AnthropicResponseTransformer(ResponseTransformer):
    """Anthropic 格式响应转换器"""

    def supports_provider(self, provider_type: ProviderType) -> bool:
        return provider_type == ProviderType.ANTHROPIC

    def transform(self, response: Dict[str, Any], provider: APIProvider) -> UnifiedResponse:
        """转换 Anthropic 响应为统一格式"""
        try:
            response_id = response.get("id", "")
            model = response.get("model", "")

            # Anthropic 的消息格式
            content_list = response.get("content", [])
            content = ""
            if content_list:
                for content_item in content_list:
                    if content_item.get("type") == "text":
                        content += content_item.get("text", "")

            # 转换使用量（Anthropic 使用不同的字段名）
            usage_data = response.get("usage", {})
            usage = UsageInfo(
                prompt_tokens=usage_data.get("input_tokens", 0),
                completion_tokens=usage_data.get("output_tokens", 0),
            )
            usage.total_tokens = usage.prompt_tokens + usage.completion_tokens

            # 创建选择项
            message = ChatMessage(
                role="assistant",
                content=content,
            )
            choice = ChatChoice(
                index=0,
                message=message,
                finish_reason=response.get("stop_reason"),
            )

            return UnifiedResponse(
                id=response_id,
                model=model,
                choices=[choice],
                usage=usage,
                provider_type=provider.provider_type,
                raw_response=response,
            )

        except Exception as e:
            logger.error(f"转换 Anthropic 响应失败：{e}")
            return self._create_error_response(str(e), provider)

    def transform_stream_chunk(
        self, chunk: Union[str, bytes, Dict[str, Any]], provider: APIProvider
    ) -> Optional[StreamChunk]:
        """转换 Anthropic 流式响应块"""
        try:
            if isinstance(chunk, (str, bytes)):
                chunk_str = chunk.decode() if isinstance(chunk, bytes) else chunk
                if chunk_str.strip() == "event: message_stop":
                    # 创建结束块
                    return StreamChunk(
                        id="",
                        model="",
                        choices=[{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop",
                        }],
                        provider_type=provider.provider_type,
                    )
                if chunk_str.startswith("data: "):
                    chunk_str = chunk_str[6:]
                chunk_data = json.loads(chunk_str)
            else:
                chunk_data = chunk

            # 处理不同类型的流式事件
            event_type = chunk_data.get("type", "")

            if event_type == "content_block_delta":
                delta = chunk_data.get("delta", {})
                content = delta.get("text", "")
                return StreamChunk(
                    id=chunk_data.get("message_id", ""),
                    model=chunk_data.get("model", ""),
                    choices=[{
                        "index": 0,
                        "delta": {"content": content},
                    }],
                    provider_type=provider.provider_type,
                )
            elif event_type == "message_delta":
                # 处理消息结束
                stop_reason = chunk_data.get("delta", {}).get("stop_reason")
                return StreamChunk(
                    id=chunk_data.get("message_id", ""),
                    model=chunk_data.get("model", ""),
                    choices=[{
                        "index": 0,
                        "delta": {},
                        "finish_reason": stop_reason,
                    }],
                    provider_type=provider.provider_type,
                )
            elif event_type == "message_stop":
                return None
            elif event_type == "content_block_start":
                # 处理内容块开始（可能包含 role 信息）
                content_block = chunk_data.get("content_block", {})
                if content_block.get("type") == "text":
                    return StreamChunk(
                        id=chunk_data.get("message_id", ""),
                        model=chunk_data.get("model", ""),
                        choices=[{
                            "index": 0,
                            "delta": {"role": "assistant"},
                        }],
                        provider_type=provider.provider_type,
                    )

            return None

        except Exception as e:
            logger.error(f"转换 Anthropic 流式块失败：{e}")
            return None

    def transform_error(
        self, error: Exception, status_code: int = 500, provider: Optional[APIProvider] = None
    ) -> ErrorResponse:
        """转换 Anthropic 错误响应"""
        error_code = "api_error"
        error_message = str(error)

        return ErrorResponse(
            error=error_message,
            error_code=error_code,
            status_code=status_code,
            provider_type=provider.provider_type if provider else None,
        )

    def _create_error_response(self, error_msg: str, provider: APIProvider) -> UnifiedResponse:
        """创建错误响应"""
        return UnifiedResponse(
            id="",
            model="",
            status=ResponseStatus.ERROR,
            error=error_msg,
            error_code="parse_error",
            provider_type=provider.provider_type,
        )


class RawResponseTransformer(ResponseTransformer):
    """原始响应转换器，直接返回响应"""

    def supports_provider(self, provider_type: ProviderType) -> bool:
        return provider_type == ProviderType.CUSTOM

    def transform(self, response: Dict[str, Any], provider: APIProvider) -> UnifiedResponse:
        """保持原始响应格式"""
        return UnifiedResponse(
            id=response.get("id", ""),
            model=response.get("model", ""),
            choices=[],
            raw_response=response,
            provider_type=provider.provider_type,
        )

    def transform_stream_chunk(
        self, chunk: Union[str, bytes, Dict[str, Any]], provider: APIProvider
    ) -> Optional[StreamChunk]:
        """保持原始流式格式"""
        return None

    def transform_error(
        self, error: Exception, status_code: int = 500, provider: Optional[APIProvider] = None
    ) -> ErrorResponse:
        """转换错误响应"""
        return ErrorResponse(
            error=str(error),
            error_code="api_error",
            status_code=status_code,
        )


class ResponseTransformerFactory:
    """
    响应转换器工厂类
    
    负责创建和管理不同类型的响应转换器
    """

    def __init__(self):
        self._transformers: Dict[ProviderType, ResponseTransformer] = {}
        self._register_default_transformers()

    def _register_default_transformers(self):
        """注册默认的转换器"""
        self.register_transformer(OpenAIResponseTransformer())
        self.register_transformer(AnthropicResponseTransformer())
        self.register_transformer(RawResponseTransformer())

    def register_transformer(self, transformer: ResponseTransformer):
        """注册响应转换器"""
        for provider_type in ProviderType:
            if transformer.supports_provider(provider_type):
                self._transformers[provider_type] = transformer

    def get_transformer(self, provider_type: ProviderType) -> ResponseTransformer:
        """获取指定提供者类型的转换器"""
        if provider_type not in self._transformers:
            logger.warning(f"未找到 {provider_type.value} 的转换器，使用 RawResponseTransformer")
            return self._transformers.get(ProviderType.CUSTOM, RawResponseTransformer())
        return self._transformers[provider_type]

    def transform(self, response: Dict[str, Any], provider: APIProvider) -> UnifiedResponse:
        """转换响应"""
        transformer = self.get_transformer(provider.provider_type)
        return transformer.transform(response, provider)

    def transform_stream_chunk(
        self, chunk: Union[str, bytes, Dict[str, Any]], provider: APIProvider
    ) -> Optional[StreamChunk]:
        """转换流式块"""
        transformer = self.get_transformer(provider.provider_type)
        return transformer.transform_stream_chunk(chunk, provider)

    def transform_error(
        self, error: Exception, status_code: int = 500, provider: Optional[APIProvider] = None
    ) -> ErrorResponse:
        """转换错误"""
        if provider:
            transformer = self.get_transformer(provider.provider_type)
        else:
            transformer = self._transformers.get(ProviderType.CUSTOM, RawResponseTransformer())
        return transformer.transform_error(error, status_code, provider)


# 全局工厂实例
_default_factory = ResponseTransformerFactory()


def transform_response(response: Dict[str, Any], provider: APIProvider) -> UnifiedResponse:
    """便捷函数：转换响应"""
    return _default_factory.transform(response, provider)


def transform_error(
    error: Exception, status_code: int = 500, provider: Optional[APIProvider] = None
) -> ErrorResponse:
    """便捷函数：转换错误"""
    return _default_factory.transform_error(error, status_code, provider)


def create_response_transformer() -> ResponseTransformerFactory:
    """创建新的响应转换器工厂实例"""
    return ResponseTransformerFactory()
