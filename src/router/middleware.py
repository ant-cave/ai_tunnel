"""
中间件模块

提供请求/响应处理的中间件机制
"""

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class Request:
    """请求对象
    
    封装 HTTP 请求的所有信息
    """
    method: str
    path: str
    headers: Dict[str, str] = None
    body: Any = None
    query_params: Dict[str, str] = None
    path_params: Dict[str, str] = None
    state: Dict[str, Any] = None
    
    def __post_init__(self):
        """初始化默认值"""
        if self.headers is None:
            self.headers = {}
        if self.query_params is None:
            self.query_params = {}
        if self.path_params is None:
            self.path_params = {}
        if self.state is None:
            self.state = {}


@dataclass
class Response:
    """响应对象
    
    封装 HTTP 响应的所有信息
    """
    status: int = 200
    body: Any = None
    headers: Dict[str, str] = None
    
    def __post_init__(self):
        """初始化默认值"""
        if self.headers is None:
            self.headers = {}


class Middleware(ABC):
    """中间件基类
    
    所有中间件都应继承此类并实现相应方法
    """
    
    @abstractmethod
    async def process_request(self, request: Request) -> Optional[Response]:
        """处理请求
        
        Args:
            request: 请求对象
            
        Returns:
            Optional[Response]: 如果返回 Response，则直接返回，不继续处理
        """
        pass
    
    @abstractmethod
    async def process_response(
        self,
        request: Request,
        response: Response
    ) -> Response:
        """处理响应
        
        Args:
            request: 请求对象
            response: 响应对象
            
        Returns:
            Response: 处理后的响应
        """
        pass


class MiddlewareChain:
    """中间件链
    
    管理中间件的执行顺序和调用
    """
    
    def __init__(self):
        """初始化中间件链"""
        self._middlewares: List[Middleware] = []
    
    def add(self, middleware: Middleware) -> None:
        """添加中间件到链尾
        
        Args:
            middleware: 中间件实例
        """
        self._middlewares.append(middleware)
    
    def insert(
        self,
        middleware: Middleware,
        index: int = 0
    ) -> None:
        """插入中间件到指定位置
        
        Args:
            middleware: 中间件实例
            index: 插入位置
        """
        self._middlewares.insert(index, middleware)
    
    def remove(self, middleware: Middleware) -> bool:
        """移除中间件
        
        Args:
            middleware: 要移除的中间件
            
        Returns:
            bool: 是否移除成功
        """
        try:
            self._middlewares.remove(middleware)
            return True
        except ValueError:
            return False
    
    async def process_request(self, request: Request) -> Optional[Response]:
        """按顺序处理请求
        
        Args:
            request: 请求对象
            
        Returns:
            Optional[Response]: 如果有中间件返回响应，则提前返回
        """
        for middleware in self._middlewares:
            response = await middleware.process_request(request)
            if response is not None:
                return response
        return None
    
    async def process_response(
        self,
        request: Request,
        response: Response
    ) -> Response:
        """逆序处理响应
        
        Args:
            request: 请求对象
            response: 响应对象
            
        Returns:
            Response: 最终响应
        """
        for middleware in reversed(self._middlewares):
            response = await middleware.process_response(request, response)
        return response
    
    async def execute(
        self,
        request: Request,
        handler: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """执行完整的中间件链
        
        Args:
            request: 请求对象
            handler: 最终处理函数
            
        Returns:
            Response: 最终响应
        """
        # 处理请求
        early_response = await self.process_request(request)
        if early_response:
            return early_response
        
        # 执行处理函数
        response = await handler(request)
        
        # 处理响应
        return await self.process_response(request, response)
    
    def __len__(self) -> int:
        """获取中间件数量"""
        return len(self._middlewares)
    
    def __iter__(self):
        """迭代中间件"""
        return iter(self._middlewares)


# 常用中间件实现示例
class LoggingMiddleware(Middleware):
    """日志中间件
    
    记录请求和响应信息
    """
    
    def __init__(self, logger=None):
        """初始化日志中间件
        
        Args:
            logger: 日志记录器
        """
        self.logger = logger
    
    async def process_request(self, request: Request) -> Optional[Response]:
        """记录请求信息"""
        if self.logger:
            self.logger.info(
                f"请求：{request.method} {request.path}"
            )
        return None
    
    async def process_response(
        self,
        request: Request,
        response: Response
    ) -> Response:
        """记录响应信息"""
        if self.logger:
            self.logger.info(
                f"响应：{request.method} {request.path} - {response.status}"
            )
        return response


class CORSMiddleware(Middleware):
    """CORS 中间件
    
    处理跨域请求
    """
    
    def __init__(
        self,
        allow_origins: List[str] = None,
        allow_methods: List[str] = None,
        allow_headers: List[str] = None
    ):
        """初始化 CORS 中间件
        
        Args:
            allow_origins: 允许的源
            allow_methods: 允许的方法
            allow_headers: 允许的头部
        """
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["*"]
        self.allow_headers = allow_headers or ["*"]
    
    async def process_request(self, request: Request) -> Optional[Response]:
        """处理 OPTIONS 预检请求"""
        if request.method == "OPTIONS":
            response = Response(status=200)
            self._add_cors_headers(response)
            return response
        return None
    
    async def process_response(
        self,
        request: Request,
        response: Response
    ) -> Response:
        """添加 CORS 头部"""
        self._add_cors_headers(response)
        return response
    
    def _add_cors_headers(self, response: Response) -> None:
        """添加 CORS 响应头"""
        response.headers["Access-Control-Allow-Origin"] = ", ".join(
            self.allow_origins
        )
        response.headers["Access-Control-Allow-Methods"] = ", ".join(
            self.allow_methods
        )
        response.headers["Access-Control-Allow-Headers"] = ", ".join(
            self.allow_headers
        )
