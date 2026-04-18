"""
异常处理模块

定义项目中使用的各种异常类
"""

from typing import Optional, Any, Dict


class AITunnelError(Exception):
    """AI Tunnel 基础异常类
    
    所有自定义异常都应继承此类
    """
    
    def __init__(
        self,
        message: str = "AI Tunnel 发生错误",
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """初始化异常
        
        Args:
            message: 错误消息
            code: 错误代码
            details: 详细错误信息
        """
        super().__init__(message)
        self.message = message
        self.code = code or "UNKNOWN_ERROR"
        self.details = details or {}
    
    def __str__(self) -> str:
        """获取异常字符串表示"""
        if self.details:
            return f"{self.code}: {self.message} - {self.details}"
        return f"{self.code}: {self.message}"
    
    def to_dict(self) -> Dict[str, Any]:
        """将异常转换为字典
        
        Returns:
            Dict[str, Any]: 异常信息字典
        """
        return {
            "error": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "details": self.details
        }


class ConfigurationError(AITunnelError):
    """配置错误
    
    当配置文件加载或验证失败时抛出
    """
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """初始化配置错误
        
        Args:
            message: 错误消息
            details: 详细错误信息
        """
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            details=details
        )


class TunnelConnectionError(AITunnelError):
    """隧道连接错误
    
    当隧道连接建立或维护失败时抛出
    """
    
    def __init__(
        self,
        message: str,
        source: Optional[str] = None,
        target: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """初始化连接错误
        
        Args:
            message: 错误消息
            source: 源地址
            target: 目标地址
            details: 详细错误信息
        """
        details = details or {}
        if source:
            details["source"] = source
        if target:
            details["target"] = target
            
        super().__init__(
            message=message,
            code="TUNNEL_CONNECTION_ERROR",
            details=details
        )


class AuthenticationError(AITunnelError):
    """认证错误
    
    当用户认证失败时抛出
    """
    
    def __init__(self, message: str = "认证失败", details: Optional[Dict[str, Any]] = None):
        """初始化认证错误
        
        Args:
            message: 错误消息
            details: 详细错误信息
        """
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            details=details
        )


class AuthorizationError(AITunnelError):
    """授权错误
    
    当用户没有权限执行操作时抛出
    """
    
    def __init__(self, message: str = "没有权限", details: Optional[Dict[str, Any]] = None):
        """初始化授权错误
        
        Args:
            message: 错误消息
            details: 详细错误信息
        """
        super().__init__(
            message=message,
            code="AUTHORIZATION_ERROR",
            details=details
        )


class ResourceNotFoundError(AITunnelError):
    """资源未找到错误
    
    当请求的资源不存在时抛出
    """
    
    def __init__(
        self,
        resource_type: str = "资源",
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """初始化资源未找到错误
        
        Args:
            resource_type: 资源类型
            resource_id: 资源 ID
            details: 详细错误信息
        """
        message = f"{resource_type}未找到"
        if resource_id:
            message += f": {resource_id}"
            
        details = details or {}
        if resource_id:
            details["resource_id"] = resource_id
        details["resource_type"] = resource_type
        
        super().__init__(
            message=message,
            code="RESOURCE_NOT_FOUND",
            details=details
        )


class ValidationError(AITunnelError):
    """验证错误
    
    当数据验证失败时抛出
    """
    
    def __init__(
        self,
        message: str = "数据验证失败",
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """初始化验证错误
        
        Args:
            message: 错误消息
            field: 出错的字段
            details: 详细错误信息
        """
        details = details or {}
        if field:
            details["field"] = field
            
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details=details
        )


class ServiceUnavailableError(AITunnelError):
    """服务不可用错误
    
    当服务暂时不可用时抛出
    """
    
    def __init__(self, message: str = "服务暂时不可用", retry_after: Optional[int] = None):
        """初始化服务不可用错误
        
        Args:
            message: 错误消息
            retry_after: 建议重试时间（秒）
        """
        details = {}
        if retry_after:
            details["retry_after"] = retry_after
            
        super().__init__(
            message=message,
            code="SERVICE_UNAVAILABLE",
            details=details
        )


class StreamingError(AITunnelError):
    """流式传输错误
    
    当流式传输过程中发生错误时抛出
    """
    
    def __init__(
        self,
        message: str = "流式传输错误",
        provider_type: Optional[Any] = None,
        providers: Optional[list] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """初始化流式传输错误
        
        Args:
            message: 错误消息
            provider_type: 提供者类型
            providers: 提供者列表
            details: 详细错误信息
        """
        self.provider_type = provider_type
        self.providers = providers
        details = details or {}
        if provider_type:
            details["provider_type"] = str(provider_type)
        if providers:
            details["providers"] = providers
            
        super().__init__(
            message=message,
            code="STREAMING_ERROR",
            details=details,
        )


class UpstreamAPIError(AITunnelError):
    """上游 API 错误
    
    当上游 API 返回错误时抛出
    """
    
    def __init__(
        self,
        message: str = "上游 API 错误",
        status_code: int = 500,
        provider_type: Optional[Any] = None,
        response_body: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """初始化上游 API 错误
        
        Args:
            message: 错误消息
            status_code: HTTP 状态码
            provider_type: 提供者类型
            response_body: 响应体
            details: 详细错误信息
        """
        self.status_code = status_code
        self.provider_type = provider_type
        self.response_body = response_body
        details = details or {}
        details["status_code"] = status_code
        if provider_type:
            details["provider_type"] = str(provider_type)
        if response_body:
            details["response_body"] = response_body
            
        super().__init__(
            message=message,
            code=f"UPSTREAM_ERROR_{status_code}",
            details=details,
        )


def handle_exception(
    exception: Exception,
    logger: Optional[Any] = None
) -> AITunnelError:
    """统一异常处理函数
    
    将普通异常转换为 AITunnelError
    
    Args:
        exception: 原始异常
        logger: 日志记录器（可选）
        
    Returns:
        AITunnelError: 包装后的异常
    """
    if isinstance(exception, AITunnelError):
        return exception
    
    error = AITunnelError(
        message=str(exception),
        code=exception.__class__.__name__,
        details={"type": type(exception).__name__}
    )
    
    if logger:
        logger.error(f"未处理的异常：{error}", exc_info=True)
    
    return error
