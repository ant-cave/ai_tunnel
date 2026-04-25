"""
HTTP 服务器模块

提供基于 aiohttp 的 HTTP/HTTPS 服务器实现，支持路由配置和中间件
"""

import asyncio
import logging
import ssl
from pathlib import Path
from typing import Dict, List, Optional, Callable, Awaitable, Any
from dataclasses import dataclass, field
from enum import Enum

from aiohttp import web
from aiohttp.web_app import Application
from aiohttp.web_runner import AppRunner, TCPSite
from aiohttp.web_middlewares import middleware

from src.config.settings import Settings, ServerConfig
from src.utils.logger import get_logger
from src.utils.exceptions import AITunnelError, ConfigurationError
from src.router.middleware import MiddlewareChain, Request, Response


@dataclass
class RouteConfig:
    """路由配置"""
    path: str
    method: str = "GET"
    handler: Optional[Callable] = None
    middlewares: List[Callable] = field(default_factory=list)
    name: Optional[str] = None


@dataclass
class ServerStats:
    """服务器统计信息"""
    start_time: Optional[float] = None
    request_count: int = 0
    error_count: int = 0
    active_connections: int = 0


class HTTPServer:
    """
    HTTP 服务器类
    
    基于 aiohttp 实现，支持：
    - HTTP 和 HTTPS
    - 路由配置
    - 中间件支持
    - 优雅关闭
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        ssl_enabled: bool = False,
        ssl_cert_path: Optional[str] = None,
        ssl_key_path: Optional[str] = None,
        logger: Optional[logging.Logger] = None
    ):
        """初始化 HTTP 服务器
        
        Args:
            host: 监听主机
            port: 监听端口
            ssl_enabled: 是否启用 SSL
            ssl_cert_path: SSL 证书路径
            ssl_key_path: SSL 密钥路径
            logger: 日志记录器
        """
        self.host = host
        self.port = port
        self.ssl_enabled = ssl_enabled
        self.ssl_cert_path = ssl_cert_path
        self.ssl_key_path = ssl_key_path
        
        self.logger = logger or get_logger("ai_tunnel.server")
        
        self._app: Optional[Application] = None
        self._runner: Optional[AppRunner] = None
        self._site: Optional[TCPSite] = None
        self._ssl_context: Optional[ssl.SSLContext] = None
        
        self._routes: Dict[str, RouteConfig] = {}
        self._middlewares: MiddlewareChain = MiddlewareChain()
        self._stats = ServerStats()
        self._shutdown_event = asyncio.Event()
        
        self._setup_application()
    
    @classmethod
    def from_settings(cls, settings: Settings, logger: Optional[logging.Logger] = None) -> "HTTPServer":
        """从配置创建服务器实例
        
        Args:
            settings: 应用配置
            logger: 日志记录器
            
        Returns:
            HTTPServer: 服务器实例
        """
        server_config = settings.server
        return cls(
            host=server_config.host,
            port=server_config.port,
            ssl_enabled=server_config.ssl_enabled,
            ssl_cert_path=server_config.ssl_cert_path,
            ssl_key_path=server_config.ssl_key_path,
            logger=logger
        )
    
    def _setup_application(self) -> None:
        """设置 aiohttp 应用"""
        self._app = Application(
            middlewares=[
                self._request_logger_middleware,
                self._error_handler_middleware,
                self._cors_middleware,
            ]
        )
        
        self._app.on_startup.append(self._on_startup)
        self._app.on_shutdown.append(self._on_shutdown)
        self._app.on_cleanup.append(self._on_cleanup)
    
    async def _on_startup(self, app: Application) -> None:
        """应用启动时的回调"""
        self._stats.start_time = asyncio.get_event_loop().time()
        self.logger.info(f"服务器启动在 http://{self.host}:{self.port}")
        
        if self.ssl_enabled:
            self.logger.info("SSL 已启用")
    
    async def _on_shutdown(self, app: Application) -> None:
        """应用关闭时的回调"""
        self.logger.info("服务器正在关闭...")
        self._shutdown_event.set()
    
    async def _on_cleanup(self, app: Application) -> None:
        """应用清理时的回调"""
        self.logger.info("服务器清理完成")
    
    @middleware
    async def _request_logger_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.Response]]
    ) -> web.Response:
        """请求日志中间件"""
        self._stats.request_count += 1
        self.logger.debug(f"请求：{request.method} {request.path}")
        
        try:
            response = await handler(request)
            self.logger.debug(f"响应：{request.method} {request.path} - {response.status}")
            return response
        except Exception as e:
            self._stats.error_count += 1
            self.logger.error(f"请求处理失败：{request.method} {request.path} - {e}")
            raise
    
    @middleware
    async def _error_handler_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.Response]]
    ) -> web.Response:
        """错误处理中间件"""
        try:
            return await handler(request)
        except web.HTTPException:
            raise
        except Exception as e:
            self._stats.error_count += 1
            self.logger.exception(f"未处理的异常：{e}")
            
            return web.json_response(
                data={
                    "error": {
                        "message": str(e),
                        "type": type(e).__name__,
                        "code": "internal_error"
                    }
                },
                status=500
            )
    
    @middleware
    async def _cors_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.Response]]
    ) -> web.Response:
        """CORS 中间件"""
        if request.method == "OPTIONS":
            return web.Response(
                status=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
                    "Access-Control-Max-Age": "86400",
                }
            )
        
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response
    
    def add_route(
        self,
        path: str,
        handler: Callable[[web.Request], Awaitable[web.Response]],
        method: str = "GET",
        name: Optional[str] = None,
        middlewares: Optional[List[Callable]] = None
    ) -> None:
        """添加路由
        
        Args:
            path: 路由路径
            handler: 处理函数
            method: HTTP 方法
            name: 路由名称
            middlewares: 中间件列表
        """
        route_config = RouteConfig(
            path=path,
            method=method.upper(),
            handler=handler,
            middlewares=middlewares or [],
            name=name
        )
        
        self._routes[f"{method.upper()}:{path}"] = route_config
        
        if self._app:
            self._app.router.add_route(method, path, handler)
        
        self.logger.debug(f"添加路由：{method} {path}")
    
    def add_get(
        self,
        path: str,
        handler: Callable[[web.Request], Awaitable[web.Response]],
        name: Optional[str] = None
    ) -> None:
        """添加 GET 路由"""
        self.add_route(path, handler, method="GET", name=name)
    
    def add_post(
        self,
        path: str,
        handler: Callable[[web.Request], Awaitable[web.Response]],
        name: Optional[str] = None
    ) -> None:
        """添加 POST 路由"""
        self.add_route(path, handler, method="POST", name=name)
    
    def add_put(
        self,
        path: str,
        handler: Callable[[web.Request], Awaitable[web.Response]],
        name: Optional[str] = None
    ) -> None:
        """添加 PUT 路由"""
        self.add_route(path, handler, method="PUT", name=name)
    
    def add_delete(
        self,
        path: str,
        handler: Callable[[web.Request], Awaitable[web.Response]],
        name: Optional[str] = None
    ) -> None:
        """添加 DELETE 路由"""
        self.add_route(path, handler, method="DELETE", name=name)
    
    def add_static(self, prefix: str, path: str, name: Optional[str] = None) -> None:
        """注册静态文件路由

        Args:
            prefix: URL 前缀
            path: 静态文件目录路径
            name: 路由名称
        """
        static_path = Path(path).resolve()
        if not static_path.exists():
            self.logger.warning(f"静态文件目录不存在：{static_path}")
            return

        if not static_path.is_dir():
            self.logger.warning(f"静态文件路径不是目录：{static_path}")
            return

        if self._app:
            self._app.router.add_static(prefix, str(static_path), name=name)

        self.logger.info(f"注册静态文件路由：{prefix} -> {static_path}")

    def add_middleware(self, middleware: Callable) -> None:
        """添加中间件
        
        Args:
            middleware: 中间件函数
        """
        self._middlewares.add(middleware)
        self.logger.debug(f"添加中间件：{middleware.__name__}")
    
    def _create_ssl_context(self) -> ssl.SSLContext:
        """创建 SSL 上下文
        
        Returns:
            ssl.SSLContext: SSL 上下文
            
        Raises:
            ConfigurationError: SSL 配置错误
        """
        if not self.ssl_enabled:
            raise ConfigurationError("SSL 未启用")
        
        if not self.ssl_cert_path or not self.ssl_key_path:
            raise ConfigurationError("SSL 证书或密钥路径未指定")
        
        cert_path = Path(self.ssl_cert_path)
        key_path = Path(self.ssl_key_path)
        
        if not cert_path.exists():
            raise ConfigurationError(f"SSL 证书文件不存在：{cert_path}")
        
        if not key_path.exists():
            raise ConfigurationError(f"SSL 密钥文件不存在：{key_path}")
        
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(str(cert_path), str(key_path))
        
        return context
    
    async def start(self) -> None:
        """启动服务器
        
        Raises:
            AITunnelError: 启动失败
        """
        try:
            self._runner = AppRunner(self._app)
            await self._runner.setup()
            
            if self.ssl_enabled:
                self._ssl_context = self._create_ssl_context()
            
            self._site = TCPSite(
                self._runner,
                self.host,
                self.port,
                ssl_context=self._ssl_context
            )
            
            await self._site.start()
            
            self.logger.info(f"服务器运行在 http://{self.host}:{self.port}")
            if self.ssl_enabled:
                self.logger.info(f"HTTPS 运行在 https://{self.host}:{self.port}")
            
        except Exception as e:
            self.logger.exception(f"服务器启动失败：{e}")
            raise AITunnelError(f"服务器启动失败：{str(e)}")
    
    async def stop(self, timeout: int = 30) -> None:
        """停止服务器
        
        Args:
            timeout: 超时时间（秒）
        """
        self.logger.info("正在停止服务器...")
        
        if self._runner:
            await self._runner.cleanup()
        
        self._shutdown_event.set()
        self.logger.info("服务器已停止")
    
    async def wait_for_shutdown(self) -> None:
        """等待关闭信号"""
        await self._shutdown_event.wait()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取服务器统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        uptime = 0
        if self._stats.start_time:
            uptime = asyncio.get_event_loop().time() - self._stats.start_time
        
        return {
            "uptime": uptime,
            "request_count": self._stats.request_count,
            "error_count": self._stats.error_count,
            "active_connections": self._stats.active_connections,
            "routes_count": len(self._routes),
            "ssl_enabled": self.ssl_enabled,
        }
    
    @property
    def app(self) -> Application:
        """获取 aiohttp 应用实例"""
        return self._app
    
    @property
    def is_running(self) -> bool:
        """检查服务器是否运行中"""
        return self._runner is not None and self._runner.server is not None


class ServerManager:
    """
    服务器管理器
    
    管理多个服务器实例，提供统一的生命周期管理
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """初始化服务器管理器
        
        Args:
            logger: 日志记录器
        """
        self.logger = logger or get_logger("ai_tunnel.server_manager")
        self._servers: Dict[str, HTTPServer] = {}
        self._shutdown_event = asyncio.Event()
    
    def add_server(self, name: str, server: HTTPServer) -> None:
        """添加服务器
        
        Args:
            name: 服务器名称
            server: 服务器实例
        """
        if name in self._servers:
            self.logger.warning(f"服务器 {name} 已存在，将被覆盖")
        
        self._servers[name] = server
        self.logger.info(f"添加服务器：{name}")
    
    def remove_server(self, name: str) -> bool:
        """移除服务器
        
        Args:
            name: 服务器名称
            
        Returns:
            bool: 是否成功移除
        """
        if name not in self._servers:
            return False
        
        del self._servers[name]
        self.logger.info(f"移除服务器：{name}")
        return True
    
    def get_server(self, name: str) -> Optional[HTTPServer]:
        """获取服务器
        
        Args:
            name: 服务器名称
            
        Returns:
            Optional[HTTPServer]: 服务器实例
        """
        return self._servers.get(name)
    
    async def start_all(self) -> None:
        """启动所有服务器"""
        self.logger.info(f"启动 {len(self._servers)} 个服务器")
        
        for name, server in self._servers.items():
            try:
                await server.start()
                self.logger.info(f"服务器 {name} 启动成功")
            except Exception as e:
                self.logger.exception(f"服务器 {name} 启动失败：{e}")
                raise
    
    async def stop_all(self, timeout: int = 30) -> None:
        """停止所有服务器
        
        Args:
            timeout: 超时时间（秒）
        """
        self.logger.info("停止所有服务器")
        
        for name, server in self._servers.items():
            try:
                await server.stop(timeout)
                self.logger.info(f"服务器 {name} 已停止")
            except Exception as e:
                self.logger.error(f"服务器 {name} 停止失败：{e}")
        
        self._shutdown_event.set()
    
    async def wait_for_shutdown(self) -> None:
        """等待所有服务器关闭"""
        await self._shutdown_event.wait()
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有服务器的统计信息
        
        Returns:
            Dict[str, Dict[str, Any]]: 统计信息
        """
        return {
            name: server.get_stats()
            for name, server in self._servers.items()
        }


class ServerMode(Enum):
    """服务器运行模式"""
    HTTP_ONLY = "http_only"
    HTTPS_ONLY = "https_only"
    DUAL_MODE = "dual_mode"


class HTTPSServer:
    """
    HTTPS 服务器类
    
    支持 HTTP 和 HTTPS 模式，根据配置自动选择
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8443,
        ssl_cert_path: Optional[str] = None,
        ssl_key_path: Optional[str] = None,
        ssl_ca_bundle: Optional[str] = None,
        ssl_verify_client: bool = False,
        ssl_min_version: str = "TLSv1.2",
        logger: Optional[logging.Logger] = None
    ):
        """初始化 HTTPS 服务器
        
        Args:
            host: 监听主机
            port: 监听端口
            ssl_cert_path: SSL 证书路径
            ssl_key_path: SSL 私钥路径
            ssl_ca_bundle: CA 证书包路径
            ssl_verify_client: 是否验证客户端证书
            ssl_min_version: 最低 TLS 版本
            logger: 日志记录器
        """
        self.host = host
        self.port = port
        self.ssl_cert_path = ssl_cert_path
        self.ssl_key_path = ssl_key_path
        self.ssl_ca_bundle = ssl_ca_bundle
        self.ssl_verify_client = ssl_verify_client
        self.ssl_min_version = ssl_min_version
        
        self.logger = logger or get_logger("ai_tunnel.https_server")
        
        self._app: Optional[Application] = None
        self._runner: Optional[AppRunner] = None
        self._site: Optional[TCPSite] = None
        self._ssl_context: Optional[ssl.SSLContext] = None
        
        self._routes: Dict[str, RouteConfig] = {}
        self._stats = ServerStats()
        self._shutdown_event = asyncio.Event()
        
        self._setup_application()
    
    def _setup_application(self) -> None:
        """设置 aiohttp 应用"""
        self._app = Application(
            middlewares=[
                self._request_logger_middleware,
                self._error_handler_middleware,
                self._cors_middleware,
            ]
        )
        
        self._app.on_startup.append(self._on_startup)
        self._app.on_shutdown.append(self._on_shutdown)
        self._app.on_cleanup.append(self._on_cleanup)
    
    def _create_ssl_context(self) -> ssl.SSLContext:
        """创建 SSL 上下文
        
        Returns:
            ssl.SSLContext: SSL 上下文
            
        Raises:
            ConfigurationError: SSL 配置错误
        """
        if not self.ssl_cert_path or not self.ssl_key_path:
            raise ConfigurationError("SSL 证书或密钥路径未指定")
        
        cert_path = Path(self.ssl_cert_path)
        key_path = Path(self.ssl_key_path)
        
        if not cert_path.exists():
            raise ConfigurationError(f"SSL 证书文件不存在：{cert_path}")
        
        if not key_path.exists():
            raise ConfigurationError(f"SSL 密钥文件不存在：{key_path}")
        
        # 创建 SSL 上下文
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        
        # 加载证书链
        context.load_cert_chain(str(cert_path), str(key_path))
        
        # 如果提供了 CA bundle，加载它
        if self.ssl_ca_bundle:
            ca_path = Path(self.ssl_ca_bundle)
            if ca_path.exists():
                context.load_verify_locations(str(ca_path))
            else:
                self.logger.warning(f"CA 证书包文件不存在：{ca_path}")
        
        # 设置客户端证书验证
        if self.ssl_verify_client:
            context.verify_mode = ssl.CERT_REQUIRED
        else:
            context.verify_mode = ssl.CERT_NONE
        
        # 设置最低 TLS 版本
        if self.ssl_min_version == "TLSv1.3":
            context.minimum_version = ssl.TLSVersion.TLSv1_3
        else:
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        
        return context
    
    async def _on_startup(self, app: Application) -> None:
        """应用启动时的回调"""
        self._stats.start_time = asyncio.get_event_loop().time()
        protocol = "https" if self._ssl_context else "http"
        self.logger.info(f"服务器启动在 {protocol}://{self.host}:{self.port}")
    
    async def _on_shutdown(self, app: Application) -> None:
        """应用关闭时的回调"""
        self.logger.info("服务器正在关闭...")
        self._shutdown_event.set()
    
    async def _on_cleanup(self, app: Application) -> None:
        """应用清理时的回调"""
        self.logger.info("服务器清理完成")
    
    async def _request_logger_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.Response]]
    ) -> web.Response:
        """请求日志中间件"""
        self._stats.request_count += 1
        self.logger.debug(f"请求：{request.method} {request.path}")
        
        try:
            response = await handler(request)
            self.logger.debug(f"响应：{request.method} {request.path} - {response.status}")
            return response
        except Exception as e:
            self._stats.error_count += 1
            self.logger.error(f"请求处理失败：{request.method} {request.path} - {e}")
            raise
    
    async def _error_handler_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.Response]]
    ) -> web.Response:
        """错误处理中间件"""
        try:
            return await handler(request)
        except web.HTTPException:
            raise
        except Exception as e:
            self._stats.error_count += 1
            self.logger.exception(f"未处理的异常：{e}")
            
            return web.json_response(
                data={
                    "error": {
                        "message": str(e),
                        "type": type(e).__name__,
                        "code": "internal_error"
                    }
                },
                status=500
            )
    
    async def _cors_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.Response]]
    ) -> web.Response:
        """CORS 中间件"""
        if request.method == "OPTIONS":
            return web.Response(
                status=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
                    "Access-Control-Max-Age": "86400",
                }
            )
        
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response
    
    def add_route(
        self,
        path: str,
        handler: Callable[[web.Request], Awaitable[web.Response]],
        method: str = "GET",
        name: Optional[str] = None,
        middlewares: Optional[List[Callable]] = None
    ) -> None:
        """添加路由"""
        route_config = RouteConfig(
            path=path,
            method=method.upper(),
            handler=handler,
            middlewares=middlewares or [],
            name=name
        )
        
        self._routes[f"{method.upper()}:{path}"] = route_config
        
        if self._app:
            self._app.router.add_route(method, path, handler)
        
        self.logger.debug(f"添加路由：{method} {path}")
    
    def add_get(self, path: str, handler: Callable, name: Optional[str] = None) -> None:
        """添加 GET 路由"""
        self.add_route(path, handler, method="GET", name=name)
    
    def add_post(self, path: str, handler: Callable, name: Optional[str] = None) -> None:
        """添加 POST 路由"""
        self.add_route(path, handler, method="POST", name=name)
    
    def add_put(self, path: str, handler: Callable, name: Optional[str] = None) -> None:
        """添加 PUT 路由"""
        self.add_route(path, handler, method="PUT", name=name)
    
    def add_delete(self, path: str, handler: Callable, name: Optional[str] = None) -> None:
        """添加 DELETE 路由"""
        self.add_route(path, handler, method="DELETE", name=name)
    
    def add_static(self, prefix: str, path: str, name: Optional[str] = None) -> None:
        """注册静态文件路由

        Args:
            prefix: URL 前缀
            path: 静态文件目录路径
            name: 路由名称
        """
        static_path = Path(path).resolve()
        if not static_path.exists():
            self.logger.warning(f"静态文件目录不存在：{static_path}")
            return

        if not static_path.is_dir():
            self.logger.warning(f"静态文件路径不是目录：{static_path}")
            return

        if self._app:
            self._app.router.add_static(prefix, str(static_path), name=name)

        self.logger.info(f"注册静态文件路由：{prefix} -> {static_path}")

    async def start(self) -> None:
        """启动服务器"""
        try:
            self._runner = AppRunner(self._app)
            await self._runner.setup()
            
            # 如果配置了 SSL 证书，创建 SSL 上下文
            if self.ssl_cert_path and self.ssl_key_path:
                self._ssl_context = self._create_ssl_context()
            
            self._site = TCPSite(
                self._runner,
                self.host,
                self.port,
                ssl_context=self._ssl_context
            )
            
            await self._site.start()
            
            protocol = "https" if self._ssl_context else "http"
            self.logger.info(f"服务器运行在 {protocol}://{self.host}:{self.port}")
            
        except Exception as e:
            self.logger.exception(f"服务器启动失败：{e}")
            raise AITunnelError(f"服务器启动失败：{str(e)}")
    
    async def stop(self, timeout: int = 30) -> None:
        """停止服务器"""
        self.logger.info("正在停止服务器...")
        
        if self._runner:
            await self._runner.cleanup()
        
        self._shutdown_event.set()
        self.logger.info("服务器已停止")
    
    async def wait_for_shutdown(self) -> None:
        """等待关闭信号"""
        await self._shutdown_event.wait()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取服务器统计信息"""
        uptime = 0
        if self._stats.start_time:
            uptime = asyncio.get_event_loop().time() - self._stats.start_time
        
        return {
            "uptime": uptime,
            "request_count": self._stats.request_count,
            "error_count": self._stats.error_count,
            "ssl_enabled": self._ssl_context is not None,
        }
    
    @property
    def app(self) -> Application:
        """获取 aiohttp 应用实例"""
        return self._app
    
    @property
    def is_running(self) -> bool:
        """检查服务器是否运行中"""
        return self._runner is not None and self._runner.server is not None


class DualModeServer:
    """
    双模式服务器
    
    支持同时运行 HTTP 和 HTTPS 服务器
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        http_port: int = 8080,
        https_port: int = 8443,
        ssl_cert_path: Optional[str] = None,
        ssl_key_path: Optional[str] = None,
        mode: ServerMode = ServerMode.DUAL_MODE,
        logger: Optional[logging.Logger] = None
    ):
        """初始化双模式服务器
        
        Args:
            host: 监听主机
            http_port: HTTP 端口
            https_port: HTTPS 端口
            ssl_cert_path: SSL 证书路径
            ssl_key_path: SSL 私钥路径
            mode: 服务器模式
            logger: 日志记录器
        """
        self.host = host
        self.http_port = http_port
        self.https_port = https_port
        self.mode = mode
        self.ssl_cert_path = ssl_cert_path
        self.ssl_key_path = ssl_key_path
        self.logger = logger or get_logger("ai_tunnel.dual_server")
        
        self._http_server: Optional[HTTPSServer] = None
        self._https_server: Optional[HTTPSServer] = None
        self._shutdown_event = asyncio.Event()
        
        self._setup_servers()
    
    def _setup_servers(self) -> None:
        """设置服务器"""
        if self.mode in [ServerMode.HTTP_ONLY, ServerMode.DUAL_MODE]:
            self._http_server = HTTPSServer(
                host=self.host,
                port=self.http_port,
                logger=self.logger
            )
            self.logger.info(f"HTTP 服务器配置：{self.host}:{self.http_port}")
        
        if self.mode in [ServerMode.HTTPS_ONLY, ServerMode.DUAL_MODE]:
            if self.ssl_cert_path and self.ssl_key_path:
                self._https_server = HTTPSServer(
                    host=self.host,
                    port=self.https_port,
                    ssl_cert_path=self.ssl_cert_path,
                    ssl_key_path=self.ssl_key_path,
                    logger=self.logger
                )
                self.logger.info(f"HTTPS 服务器配置：{self.host}:{self.https_port}")
            else:
                self.logger.warning("HTTPS 模式但未配置 SSL 证书，将使用 HTTP 模式")
                if self.mode == ServerMode.HTTPS_ONLY:
                    self._http_server = HTTPSServer(
                        host=self.host,
                        port=self.http_port,
                        logger=self.logger
                    )
    
    async def start(self) -> None:
        """启动所有服务器"""
        self.logger.info(f"启动双模式服务器 (模式：{self.mode.value})")
        
        try:
            if self._http_server:
                await self._http_server.start()
            
            if self._https_server:
                await self._https_server.start()
            
            self.logger.info("所有服务器启动成功")
            
        except Exception as e:
            self.logger.exception(f"服务器启动失败：{e}")
            raise AITunnelError(f"服务器启动失败：{str(e)}")
    
    async def stop(self, timeout: int = 30) -> None:
        """停止所有服务器"""
        self.logger.info("正在停止所有服务器...")
        
        if self._http_server:
            await self._http_server.stop(timeout)
        
        if self._https_server:
            await self._https_server.stop(timeout)
        
        self._shutdown_event.set()
        self.logger.info("所有服务器已停止")
    
    async def wait_for_shutdown(self) -> None:
        """等待关闭信号"""
        await self._shutdown_event.wait()
    
    def add_route(
        self,
        path: str,
        handler: Callable[[web.Request], Awaitable[web.Response]],
        method: str = "GET",
        name: Optional[str] = None
    ) -> None:
        """添加路由到所有服务器"""
        if self._http_server:
            self._http_server.add_route(path, handler, method, name)
        
        if self._https_server:
            self._https_server.add_route(path, handler, method, name)
    
    def add_get(self, path: str, handler: Callable, name: Optional[str] = None) -> None:
        """添加 GET 路由"""
        self.add_route(path, handler, "GET", name)
    
    def add_post(self, path: str, handler: Callable, name: Optional[str] = None) -> None:
        """添加 POST 路由"""
        self.add_route(path, handler, "POST", name)
    
    def add_static(self, prefix: str, path: str, name: Optional[str] = None) -> None:
        """注册静态文件路由到所有服务器

        Args:
            prefix: URL 前缀
            path: 静态文件目录路径
            name: 路由名称
        """
        if self._http_server:
            self._http_server.add_static(prefix, path, name)

        if self._https_server:
            self._https_server.add_static(prefix, path, name)

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有服务器统计信息"""
        stats = {}
        if self._http_server:
            stats["http"] = self._http_server.get_stats()
        if self._https_server:
            stats["https"] = self._https_server.get_stats()
        return stats


def create_server(
    settings: Settings,
    logger: Optional[logging.Logger] = None
) -> DualModeServer:
    """根据配置创建服务器实例
    
    Args:
        settings: 应用配置
        logger: 日志记录器
        
    Returns:
        DualModeServer: 服务器实例
    """
    server_config = settings.server
    
    # 确定服务器模式
    if server_config.ssl and server_config.ssl.is_enabled:
        mode = ServerMode.DUAL_MODE
    else:
        mode = ServerMode.HTTP_ONLY
    
    return DualModeServer(
        host=server_config.host,
        http_port=server_config.port,
        https_port=server_config.port + 443 if server_config.port < 1000 else server_config.port + 1,
        ssl_cert_path=server_config.ssl.cert_path if server_config.ssl else None,
        ssl_key_path=server_config.ssl.key_path if server_config.ssl else None,
        mode=mode,
        logger=logger
    )
