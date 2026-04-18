"""
连接模型模块

定义隧道连接相关的数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from src.models.base import BaseModel


class ConnectionStatus(str, Enum):
    """连接状态枚举"""
    
    PENDING = "pending"  # 等待连接
    CONNECTING = "connecting"  # 连接中
    CONNECTED = "connected"  # 已连接
    DISCONNECTED = "disconnected"  # 已断开
    ERROR = "error"  # 错误状态


@dataclass
class Connection(BaseModel):
    """连接模型
    
    表示一个隧道连接的所有信息
    """
    
    # 连接标识
    id: str
    name: str = "未命名连接"
    
    # 连接信息
    source_host: str = "localhost"
    source_port: int = 0
    target_host: str = "localhost"
    target_port: int = 0
    
    # 状态信息
    status: ConnectionStatus = ConnectionStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # 连接统计
    bytes_sent: int = 0
    bytes_received: int = 0
    connections_count: int = 0
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 错误信息
    error_message: Optional[str] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if isinstance(self.status, str):
            self.status = ConnectionStatus(self.status)
    
    def is_active(self) -> bool:
        """检查连接是否活跃
        
        Returns:
            bool: 连接是否活跃
        """
        return self.status in [
            ConnectionStatus.CONNECTING,
            ConnectionStatus.CONNECTED
        ]
    
    def update_status(self, status: ConnectionStatus) -> None:
        """更新连接状态
        
        Args:
            status: 新的连接状态
        """
        self.status = status
        self.updated_at = datetime.now()
    
    def add_bytes_sent(self, bytes_count: int) -> None:
        """增加发送字节数
        
        Args:
            bytes_count: 发送的字节数
        """
        self.bytes_sent += bytes_count
        self.updated_at = datetime.now()
    
    def add_bytes_received(self, bytes_count: int) -> None:
        """增加接收字节数
        
        Args:
            bytes_count: 接收的字节数
        """
        self.bytes_received += bytes_count
        self.updated_at = datetime.now()
    
    def increment_connections(self) -> None:
        """增加连接计数"""
        self.connections_count += 1
        self.updated_at = datetime.now()
    
    def set_error(self, error_message: str) -> None:
        """设置错误信息
        
        Args:
            error_message: 错误信息
        """
        self.error_message = error_message
        self.status = ConnectionStatus.ERROR
        self.updated_at = datetime.now()
    
    def get_total_bytes(self) -> int:
        """获取总字节数
        
        Returns:
            int: 发送和接收的总字节数
        """
        return self.bytes_sent + self.bytes_received
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（重写以处理 datetime 和 enum）
        
        Returns:
            Dict[str, Any]: 字典数据
        """
        data = super().to_dict()
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data
