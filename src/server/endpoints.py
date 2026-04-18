"""
API 端点处理器模块

实现各个 API 端点的具体处理逻辑，包括：
- /v1/chat/completions
- /v1/models
- 健康检查端点
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, AsyncIterator
from datetime import datetime

from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response

from src.utils.logger import get_logger
from src.utils.exceptions import (
    AITunnelError,
    ValidationError,
    AuthenticationError,
    ServiceUnavailableError,
)
from src.router.router import AsyncRouter, ClientRequest
from src.config.settings import Settings


logger = get_logger("ai_tunnel.endpoints")


class EndpointHandler(ABC):
    """端点处理器基类
    
    所有端点处理器都应继承此类
    """
    
    def __init__(self, settings: Settings, router: AsyncRouter):
        """初始化端点处理器
        
        Args:
            settings: 应用配置
            router: 异步路由器
        """
        self.settings = settings
        self.router = router
        self.logger = get_logger(f"ai_tunnel.endpoints.{self.__class__.__name__}")
    
    @abstractmethod
    async def handle(self, request: Request) -> Response:
        """处理请求
        
        Args:
            request: HTTP 请求
            
        Returns:
            Response: HTTP 响应
        """
        pass
    
    def _json_response(
        self,
        data: Dict[str, Any],
        status: int = 200,
        headers: Optional[Dict[str, str]] = None
    ) -> Response:
        """创建 JSON 响应
        
        Args:
            data: 响应数据
            status: HTTP 状态码
            headers: 响应头
            
        Returns:
            Response: JSON 响应
        """
        return web.json_response(
            data=data,
            status=status,
            headers=headers
        )
    
    def _error_response(
        self,
        message: str,
        status: int = 500,
        error_type: Optional[str] = None,
        error_code: Optional[str] = None
    ) -> Response:
        """创建错误响应
        
        Args:
            message: 错误消息
            status: HTTP 状态码
            error_type: 错误类型
            error_code: 错误代码
            
        Returns:
            Response: 错误响应
        """
        error_data = {
            "error": {
                "message": message,
                "type": error_type or "error",
                "code": error_code or "unknown_error",
            }
        }
        return self._json_response(error_data, status=status)
    
    def _get_api_key(self, request: Request) -> Optional[str]:
        """从请求中获取 API 密钥
        
        Args:
            request: HTTP 请求
            
        Returns:
            Optional[str]: API 密钥
        """
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        
        return request.headers.get("X-API-Key")
    
    def _validate_api_key(self, request: Request) -> bool:
        """验证 API 密钥
        
        Args:
            request: HTTP 请求
            
        Returns:
            bool: 是否验证通过
            
        Raises:
            AuthenticationError: 认证失败
        """
        api_key = self.settings.security.api_key
        if not api_key:
            return True
        
        provided_key = self._get_api_key(request)
        if not provided_key or provided_key != api_key:
            raise AuthenticationError("无效的 API 密钥")
        
        return True
    
    async def _parse_json_body(self, request: Request) -> Dict[str, Any]:
        """解析 JSON 请求体
        
        Args:
            request: HTTP 请求
            
        Returns:
            Dict[str, Any]: 解析后的数据
            
        Raises:
            ValidationError: 解析失败
        """
        try:
            data = await request.json()
            return data or {}
        except json.JSONDecodeError as e:
            raise ValidationError(f"无效的 JSON 格式：{str(e)}")
        except Exception as e:
            raise ValidationError(f"请求体解析失败：{str(e)}")


class ChatCompletionsHandler(EndpointHandler):
    """聊天补全端点处理器
    
    处理 /v1/chat/completions 请求
    """
    
    async def handle(self, request: Request) -> Response:
        """处理聊天补全请求
        
        Args:
            request: HTTP 请求
            
        Returns:
            Response: 响应
        """
        try:
            self._validate_api_key(request)
            
            data = await self._parse_json_body(request)
            
            client_request = self._create_client_request(data)
            
            if request.headers.get("Accept") == "text/event-stream" or data.get("stream"):
                return await self._handle_stream(request, client_request)
            else:
                return await self._handle_normal(client_request)
                
        except AuthenticationError as e:
            self.logger.warning(f"认证失败：{e}")
            return self._error_response(str(e), status=401, error_code="authentication_error")
        except ValidationError as e:
            self.logger.warning(f"验证失败：{e}")
            return self._error_response(str(e), status=400, error_code="validation_error")
        except Exception as e:
            self.logger.exception(f"处理聊天补全请求失败：{e}")
            return self._error_response(str(e), status=500, error_code="internal_error")
    
    def _create_client_request(self, data: Dict[str, Any]) -> ClientRequest:
        """创建客户端请求对象
        
        Args:
            data: 请求数据
            
        Returns:
            ClientRequest: 客户端请求
            
        Raises:
            ValidationError: 数据验证失败
        """
        model = data.get("model")
        if not model:
            raise ValidationError("缺少必需字段：model")
        
        messages = data.get("messages")
        if not messages or not isinstance(messages, list):
            raise ValidationError("缺少必需字段：messages 或格式错误")
        
        # 构建额外参数
        extra_body = {}
        if "user" in data:
            extra_body["user"] = data.get("user")
        
        return ClientRequest(
            model=model,
            messages=messages,
            stream=data.get("stream", False),
            temperature=data.get("temperature"),
            top_p=data.get("top_p"),
            max_tokens=data.get("max_tokens"),
            presence_penalty=data.get("presence_penalty"),
            frequency_penalty=data.get("frequency_penalty"),
            stop=data.get("stop"),
            extra_body=extra_body,
        )
    
    async def _handle_normal(self, client_request: ClientRequest) -> Response:
        """处理普通请求
        
        Args:
            client_request: 客户端请求
            
        Returns:
            Response: 响应
        """
        self.logger.info(f"处理聊天补全请求：模型={client_request.model}")
        
        routing_result = await self.router.route_request_async(client_request)
        
        if not routing_result.success:
            return self._error_response(
                routing_result.error or "路由失败",
                status=503,
                error_code="routing_error"
            )
        
        provider = routing_result.provider
        transformed_request = routing_result.transformed_request
        
        try:
            raw_response = await self._send_to_provider(transformed_request)
            
            unified_response = await self.router.process_response_async(
                raw_response, provider
            )
            
            return self._json_response(
                data=self._format_response(unified_response),
                status=200
            )
            
        except Exception as e:
            self.logger.exception(f"上游请求失败：{e}")
            return self._error_response(
                f"上游服务请求失败：{str(e)}",
                status=503,
                error_code="upstream_error"
            )
    
    async def _handle_stream(
        self,
        request: Request,
        client_request: ClientRequest
    ) -> Response:
        """处理流式请求
        
        Args:
            request: HTTP 请求
            client_request: 客户端请求
            
        Returns:
            Response: 流式响应
        """
        self.logger.info(f"处理流式聊天补全请求：模型={client_request.model}")
        
        routing_result = await self.router.route_request_async(client_request)
        
        if not routing_result.success:
            return self._error_response(
                routing_result.error or "路由失败",
                status=503,
                error_code="routing_error"
            )
        
        provider = routing_result.provider
        
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
        
        await response.prepare(request)
        
        try:
            async for chunk in self.router.route_stream_with_fallback(client_request):
                if chunk and hasattr(chunk, "to_dict"):
                    formatted_chunk = chunk.to_dict()
                    try:
                        await response.write(f"data: {json.dumps(formatted_chunk)}\n\n".encode('utf-8'))
                        await response.drain()
                    except ConnectionResetError:
                        self.logger.info("客户端已断开连接，停止流式传输")
                        return response
                    except Exception as write_error:
                        if "closing transport" in str(write_error):
                            self.logger.info("传输通道正在关闭，客户端可能已断开")
                            return response
                        raise
            
            try:
                await response.write("data: [DONE]\n\n".encode('utf-8'))
                await response.drain()
            except ConnectionResetError:
                self.logger.info("客户端已断开连接，跳过完成标记发送")
            except Exception as write_error:
                if "closing transport" not in str(write_error):
                    raise
            
        except ConnectionResetError:
            self.logger.info("客户端在流式处理过程中断开连接")
            return response
        except Exception as e:
            self.logger.exception(f"流式处理失败：{e}")
            try:
                error_data = {
                    "error": {
                        "message": str(e),
                        "type": "stream_error",
                        "code": "stream_error"
                    }
                }
                await response.write(f"data: {json.dumps(error_data)}\n\n".encode('utf-8'))
                await response.drain()
            except Exception:
                pass
        finally:
            try:
                await response.write_eof()
            except Exception:
                pass
        
        return response
    
    async def _send_to_provider(self, transformed_request: Any) -> Dict[str, Any]:
        """发送请求到提供者
        
        Args:
            transformed_request: 转换后的请求
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        await asyncio.sleep(0.1)
        
        return {
            "id": f"chatcmpl-{datetime.now().timestamp()}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": transformed_request.model if hasattr(transformed_request, "model") else "unknown",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "这是一个模拟响应"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15
            }
        }
    
    async def _stream_from_provider(
        self,
        transformed_request: Any,
        provider: Any
    ) -> AsyncIterator[Dict[str, Any]]:
        """从提供者流式获取数据
        
        Args:
            transformed_request: 转换后的请求
            provider: 提供者信息
            
        Yields:
            Dict[str, Any]: 流式数据块
        """
        for i in range(5):
            await asyncio.sleep(0.1)
            yield {
                "id": f"chatcmpl-{datetime.now().timestamp()}",
                "object": "chat.completion.chunk",
                "created": int(datetime.now().timestamp()),
                "model": provider.name if hasattr(provider, "name") else "unknown",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": f"这是第 {i + 1} 个流式块"
                        },
                        "finish_reason": None
                    }
                ]
            }
    
    def _format_response(self, unified_response: Any) -> Dict[str, Any]:
        """格式化响应
        
        Args:
            unified_response: 统一响应
            
        Returns:
            Dict[str, Any]: 格式化后的响应
        """
        if hasattr(unified_response, "to_dict"):
            return unified_response.to_dict()
        
        return {
            "id": getattr(unified_response, "id", ""),
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": getattr(unified_response, "model", ""),
            "choices": getattr(unified_response, "choices", []),
            "usage": getattr(unified_response, "usage", {}),
        }


class ModelsHandler(EndpointHandler):
    """模型列表端点处理器
    
    处理 /v1/models 请求
    """
    
    async def handle(self, request: Request) -> Response:
        """处理模型列表请求
        
        Args:
            request: HTTP 请求
            
        Returns:
            Response: 响应
        """
        try:
            self._validate_api_key(request)
            
            models = await self._get_available_models()
            
            return self._json_response({
                "object": "list",
                "data": models
            })
            
        except AuthenticationError as e:
            return self._error_response(str(e), status=401, error_code="authentication_error")
        except Exception as e:
            self.logger.exception(f"获取模型列表失败：{e}")
            return self._error_response(str(e), status=500, error_code="internal_error")
    
    async def _get_available_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表
        
        Returns:
            List[Dict[str, Any]]: 模型列表
        """
        import aiohttp
        
        providers = self.router.provider_manager.get_all_providers()
        
        models = []
        for provider in providers:
            if not provider.enabled:
                continue
            
            try:
                # 从提供者的 API 端点获取模型列表
                async with aiohttp.ClientSession() as session:
                    url = f"{provider.base_url}/v1/models"
                    headers = {
                        "Authorization": f"Bearer {provider.api_key}",
                        "Content-Type": "application/json"
                    }
                    
                    async with session.get(url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            # 处理返回的模型列表
                            if "data" in data:
                                for model_info in data["data"]:
                                    models.append({
                                        "id": model_info.get("id"),
                                        "object": "model",
                                        "created": model_info.get("created", int(datetime.now().timestamp())),
                                        "owned_by": provider.name,
                                        "provider_type": provider.provider_type.value,
                                        "remote_model": model_info.get("id"),
                                    })
                        else:
                            self.logger.warning(f"获取提供者 {provider.name} 的模型列表失败，状态码: {response.status}")
            except Exception as e:
                self.logger.warning(f"获取提供者 {provider.name} 的模型列表时发生错误: {str(e)}")
                
                # 如果 API 请求失败，回退到使用配置中的模型
                if hasattr(provider.config, 'models') and isinstance(provider.config.models, list):
                    for model_name in provider.config.models:
                        models.append({
                            "id": model_name,
                            "object": "model",
                            "created": int(datetime.now().timestamp()),
                            "owned_by": provider.name,
                            "provider_type": provider.provider_type.value,
                            "remote_model": model_name,
                        })
        
        # 添加 auto 模型
        models.append({
            "id": "auto",
            "object": "model",
            "created": int(datetime.now().timestamp()),
            "owned_by": "system",
            "provider_type": "system",
            "remote_model": "auto",
            "description": "自动选择最优提供者"
        })
        
        return models


class HealthHandler(EndpointHandler):
    """健康检查端点处理器
    
    处理健康检查请求
    """
    
    async def handle(self, request: Request) -> Response:
        """处理健康检查请求
        
        Args:
            request: HTTP 请求
            
        Returns:
            Response: 响应
        """
        try:
            health_status = await self._get_health_status()
            
            status_code = 200 if health_status["status"] == "healthy" else 503
            
            return self._json_response(health_status, status=status_code)
            
        except Exception as e:
            self.logger.exception(f"健康检查失败：{e}")
            return self._error_response(str(e), status=500, error_code="internal_error")
    
    async def _get_health_status(self) -> Dict[str, Any]:
        """获取健康状态
        
        Returns:
            Dict[str, Any]: 健康状态
        """
        router_status = self.router.get_status()
        
        providers_status = []
        for provider in self.router.provider_manager.get_all_providers():
            providers_status.append({
                "name": provider.name,
                "type": provider.provider_type.value,
                "enabled": provider.enabled,
                "healthy": provider.healthy,
                "models_count": len(provider.config.models),
            })
        
        overall_status = "healthy"
        if router_status["healthy_providers"] == 0:
            overall_status = "unhealthy"
        elif router_status["healthy_providers"] < router_status["total_providers"]:
            overall_status = "degraded"
        
        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "router": router_status,
            "providers": providers_status,
        }


class StatusHandler(EndpointHandler):
    """服务器状态端点处理器
    
    处理 /status 请求
    """
    
    async def handle(self, request: Request) -> Response:
        """处理状态请求
        
        Args:
            request: HTTP 请求
            
        Returns:
            Response: 响应
        """
        try:
            status = self._get_server_status()
            
            return self._json_response(status)
            
        except Exception as e:
            self.logger.exception(f"获取状态失败：{e}")
            return self._error_response(str(e), status=500, error_code="internal_error")
    
    def _get_server_status(self) -> Dict[str, Any]:
        """获取服务器状态
        
        Returns:
            Dict[str, Any]: 服务器状态
        """
        return {
            "status": "running",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "settings": {
                "host": self.settings.server.host,
                "port": self.settings.server.port,
                "ssl_enabled": self.settings.server.ssl_enabled,
                "log_level": self.settings.log_level,
            }
        }


def create_endpoint_handlers(
    settings: Settings,
    router: AsyncRouter
) -> Dict[str, EndpointHandler]:
    """创建所有端点处理器
    
    Args:
        settings: 应用配置
        router: 异步路由器
        
    Returns:
        Dict[str, EndpointHandler]: 端点处理器字典
    """
    return {
        "chat": ChatCompletionsHandler(settings, router),
        "models": ModelsHandler(settings, router),
        "health": HealthHandler(settings, router),
        "status": StatusHandler(settings, router),
    }
