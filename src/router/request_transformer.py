"""
请求转换器模块

负责将客户端请求转换为上游 API 格式，处理认证信息和请求参数。
支持多种提供者类型的请求格式转换。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
import json
import logging

from .provider_manager import ProviderType, APIProvider

logger = logging.getLogger(__name__)


class RequestFormat(Enum):
    """请求格式类型"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    RAW = "raw"


@dataclass
class ClientRequest:
    """
    客户端请求数据类
    
    封装来自客户端的原始请求信息
    """
    model: str
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop: Optional[List[str]] = None
    extra_body: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransformedRequest:
    """
    转换后的请求数据类
    
    包含发送到上游 API 所需的所有信息
    """
    url: str
    method: str = "POST"
    headers: Dict[str, str] = field(default_factory=dict)
    body: Dict[str, Any] = field(default_factory=dict)
    raw_body: Optional[str] = None
    timeout: int = 30
    provider_type: ProviderType = ProviderType.CUSTOM

    def to_http_kwargs(self) -> Dict[str, Any]:
        """转换为 HTTP 请求参数字典"""
        kwargs = {
            "method": self.method,
            "headers": self.headers,
            "timeout": self.timeout,
        }

        if self.raw_body:
            kwargs["data"] = self.raw_body
            kwargs["headers"]["Content-Type"] = "application/json"
        else:
            kwargs["json"] = self.body

        return kwargs


class RequestTransformer(ABC):
    """请求转换器抽象基类"""

    @abstractmethod
    def transform(self, request: ClientRequest, provider: APIProvider) -> TransformedRequest:
        """
        转换客户端请求为上游 API 格式
        
        Args:
            request: 客户端请求
            provider: 目标提供者
            
        Returns:
            转换后的请求
        """
        pass

    @abstractmethod
    def supports_provider(self, provider_type: ProviderType) -> bool:
        """检查是否支持指定类型的提供者"""
        pass


class OpenAIRequestTransformer(RequestTransformer):
    """OpenAI 格式请求转换器"""

    def supports_provider(self, provider_type: ProviderType) -> bool:
        return provider_type in [ProviderType.OPENAI, ProviderType.AZURE]

    def transform(self, request: ClientRequest, provider: APIProvider) -> TransformedRequest:
        """转换为 OpenAI API 格式"""
        # 处理 auto 模型
        model_name = request.model
        if model_name.lower() == "auto" and provider.models:
            model_name = provider.models[0]
            logger.info(f"Auto 模型选择提供者 {provider.name} 的默认模型: {model_name}")
        
        # 构建请求体
        body = {
            "model": model_name,
            "messages": request.messages,
        }

        # 添加可选参数
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.stream:
            body["stream"] = True
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.frequency_penalty is not None:
            body["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty is not None:
            body["presence_penalty"] = request.presence_penalty
        if request.stop is not None:
            body["stop"] = request.stop

        # 合并额外参数
        body.update(request.extra_body)

        # 构建请求头
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider.api_key}",
        }

        # 添加自定义请求头
        headers.update(request.headers)

        # 处理 Azure 特殊情况
        if provider.provider_type == ProviderType.AZURE:
            api_version = provider.get_extra_config("api_version", "2023-05-15")
            headers["api-key"] = provider.api_key
            # Azure 使用不同的 URL 格式（使用转换后的模型名称）
            url = f"{provider.base_url}/openai/deployments/{model_name}/chat/completions?api-version={api_version}"
        else:
            url = f"{provider.base_url}/v1/chat/completions"

        logger.debug(f"转换为 OpenAI 格式请求：{url}")
        return TransformedRequest(
            url=url,
            method="POST",
            headers=headers,
            body=body,
            provider_type=provider.provider_type,
        )


class AnthropicRequestTransformer(RequestTransformer):
    """Anthropic 格式请求转换器"""

    def supports_provider(self, provider_type: ProviderType) -> bool:
        return provider_type == ProviderType.ANTHROPIC

    def transform(self, request: ClientRequest, provider: APIProvider) -> TransformedRequest:
        """转换为 Anthropic API 格式"""
        # 处理 auto 模型
        model_name = request.model
        if model_name.lower() == "auto" and provider.models:
            model_name = provider.models[0]
            logger.info(f"Auto 模型选择提供者 {provider.name} 的默认模型: {model_name}")
        
        # Anthropic 使用不同的消息格式
        anthropic_messages = self._convert_messages(request.messages)

        # 构建请求体
        body = {
            "model": model_name,
            "messages": anthropic_messages,
            "max_tokens": request.max_tokens or 1024,
        }

        # 添加可选参数
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.stream:
            body["stream"] = True
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.stop is not None:
            body["stop_sequences"] = request.stop

        # 合并额外参数
        body.update(request.extra_body)

        # 构建请求头
        headers = {
            "Content-Type": "application/json",
            "x-api-key": provider.api_key,
            "anthropic-version": provider.get_extra_config("api_version", "2023-06-01"),
        }

        # 添加自定义请求头
        headers.update(request.headers)

        url = f"{provider.base_url}/v1/messages"

        logger.debug(f"转换为 Anthropic 格式请求：{url}")
        return TransformedRequest(
            url=url,
            method="POST",
            headers=headers,
            body=body,
            provider_type=provider.provider_type,
        )

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        转换消息格式到 Anthropic 格式
        
        OpenAI 格式：{"role": "system", "content": "..."}
        Anthropic 格式：{"role": "user", "content": "..."}
        """
        converted = []
        system_message = None

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                # Anthropic 将 system message 单独处理
                system_message = content
                continue
            elif role == "assistant":
                converted.append({"role": "assistant", "content": content})
            else:
                # user 和其他角色都转为 user
                converted.append({"role": "user", "content": content})

        return converted


class RawRequestTransformer(RequestTransformer):
    """原始请求转换器，直接传递请求不做转换"""

    def supports_provider(self, provider_type: ProviderType) -> bool:
        return provider_type == ProviderType.CUSTOM

    def transform(self, request: ClientRequest, provider: APIProvider) -> TransformedRequest:
        """保持原始请求格式"""
        # 处理 auto 模型
        model_name = request.model
        if model_name.lower() == "auto" and provider.models:
            model_name = provider.models[0]
            logger.info(f"Auto 模型选择提供者 {provider.name} 的默认模型: {model_name}")
        
        headers = {
            "Content-Type": "application/json",
        }

        # 如果有认证信息，添加
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        headers.update(request.headers)

        body = {
            "model": model_name,
            "messages": request.messages,
            **request.extra_body,
        }

        url = provider.base_url

        logger.debug(f"原始请求格式：{url}")
        return TransformedRequest(
            url=url,
            method="POST",
            headers=headers,
            body=body,
            provider_type=provider.provider_type,
        )


class RequestTransformerFactory:
    """
    请求转换器工厂类
    
    负责创建和管理不同类型的请求转换器
    """

    def __init__(self):
        self._transformers: Dict[ProviderType, RequestTransformer] = {}
        self._register_default_transformers()

    def _register_default_transformers(self):
        """注册默认的转换器"""
        self.register_transformer(OpenAIRequestTransformer())
        self.register_transformer(AnthropicRequestTransformer())
        self.register_transformer(RawRequestTransformer())

    def register_transformer(self, transformer: RequestTransformer):
        """
        注册请求转换器
        
        Args:
            transformer: 请求转换器实例
        """
        for provider_type in ProviderType:
            if transformer.supports_provider(provider_type):
                self._transformers[provider_type] = transformer
                logger.debug(f"注册转换器：{provider_type.value} -> {transformer.__class__.__name__}")

    def get_transformer(self, provider_type: ProviderType) -> RequestTransformer:
        """
        获取指定提供者类型的转换器
        
        Args:
            provider_type: 提供者类型
            
        Returns:
            对应的请求转换器
            
        Raises:
            ValueError: 当没有找到对应的转换器时
        """
        if provider_type not in self._transformers:
            logger.warning(f"未找到 {provider_type.value} 的转换器，使用 RawRequestTransformer")
            return self._transformers.get(ProviderType.CUSTOM, RawRequestTransformer())

        return self._transformers[provider_type]

    def transform(self, request: ClientRequest, provider: APIProvider) -> TransformedRequest:
        """
        根据提供者类型转换请求
        
        Args:
            request: 客户端请求
            provider: 目标提供者
            
        Returns:
            转换后的请求
        """
        transformer = self.get_transformer(provider.provider_type)
        logger.info(
            f"使用 {transformer.__class__.__name__} 转换请求 "
            f"(提供者：{provider.name}, 模型：{request.model})"
        )
        return transformer.transform(request, provider)


# 全局工厂实例
_default_factory = RequestTransformerFactory()


def transform_request(request: ClientRequest, provider: APIProvider) -> TransformedRequest:
    """
    便捷函数：转换客户端请求
    
    Args:
        request: 客户端请求
        provider: 目标提供者
        
    Returns:
        转换后的请求
    """
    return _default_factory.transform(request, provider)


def create_request_transformer() -> RequestTransformerFactory:
    """创建新的请求转换器工厂实例"""
    return RequestTransformerFactory()
