"""
模型模块测试
"""

import pytest
from datetime import datetime
from src.models.base import BaseModel
from src.models.connection import Connection, ConnectionStatus


class TestBaseModel:
    """基础模型测试"""
    
    def test_from_dict(self):
        """测试从字典创建模型"""
        class TestModel(BaseModel):
            name: str
            value: int
        
        data = {"name": "test", "value": 42, "extra": "ignored"}
        model = TestModel.from_dict(data)
        
        assert model.name == "test"
        assert model.value == 42
    
    def test_to_dict(self):
        """测试转换为字典"""
        class TestModel(BaseModel):
            name: str
            value: int
        
        model = TestModel(name="test", value=42)
        data = model.to_dict()
        
        assert data["name"] == "test"
        assert data["value"] == 42
    
    def test_update(self):
        """测试更新字段"""
        class TestModel(BaseModel):
            name: str
            value: int
        
        model = TestModel(name="test", value=42)
        model.update(name="updated", value=100)
        
        assert model.name == "updated"
        assert model.value == 100
    
    def test_repr(self):
        """测试字符串表示"""
        class TestModel(BaseModel):
            name: str
        
        model = TestModel(name="test")
        repr_str = repr(model)
        
        assert "TestModel" in repr_str
        assert "name='test'" in repr_str


class TestConnection:
    """连接模型测试"""
    
    def test_connection_creation(self):
        """测试连接创建"""
        conn = Connection(id="conn_001", name="Test Connection")
        
        assert conn.id == "conn_001"
        assert conn.name == "Test Connection"
        assert conn.status == ConnectionStatus.PENDING
        assert conn.bytes_sent == 0
        assert conn.bytes_received == 0
    
    def test_is_active(self):
        """测试活跃状态检查"""
        conn = Connection(id="conn_001")
        
        assert conn.is_active() is False
        
        conn.status = ConnectionStatus.CONNECTED
        assert conn.is_active() is True
        
        conn.status = ConnectionStatus.CONNECTING
        assert conn.is_active() is True
    
    def test_update_status(self):
        """测试状态更新"""
        conn = Connection(id="conn_001")
        old_updated_at = conn.updated_at
        
        conn.update_status(ConnectionStatus.CONNECTED)
        
        assert conn.status == ConnectionStatus.CONNECTED
        assert conn.updated_at > old_updated_at
    
    def test_add_bytes(self):
        """测试字节数增加"""
        conn = Connection(id="conn_001")
        
        conn.add_bytes_sent(100)
        conn.add_bytes_received(200)
        
        assert conn.bytes_sent == 100
        assert conn.bytes_received == 200
        assert conn.get_total_bytes() == 300
    
    def test_increment_connections(self):
        """测试连接计数增加"""
        conn = Connection(id="conn_001")
        
        conn.increment_connections()
        conn.increment_connections()
        
        assert conn.connections_count == 2
    
    def test_set_error(self):
        """测试设置错误"""
        conn = Connection(id="conn_001")
        
        conn.set_error("Connection failed")
        
        assert conn.status == ConnectionStatus.ERROR
        assert conn.error_message == "Connection failed"
    
    def test_to_dict(self):
        """测试转换为字典"""
        conn = Connection(id="conn_001", name="Test")
        data = conn.to_dict()
        
        assert data["id"] == "conn_001"
        assert data["name"] == "Test"
        assert data["status"] == "pending"
        assert "created_at" in data
        assert "updated_at" in data
    
    def test_from_string_status(self):
        """测试从字符串状态创建"""
        conn = Connection(
            id="conn_001",
            status="connected"  # 字符串形式
        )
        
        assert conn.status == ConnectionStatus.CONNECTED
