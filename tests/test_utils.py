"""
工具模块测试
"""

import pytest
import logging
import tempfile
from pathlib import Path

from src.utils.logger import setup_logger, get_logger, LoggerAdapter
from src.utils.exceptions import (
    AITunnelError, ConfigurationError, TunnelConnectionError,
    AuthenticationError, ResourceNotFoundError, ValidationError,
    handle_exception
)


class TestLogger:
    """日志工具测试"""
    
    def test_setup_logger(self):
        """测试设置日志"""
        logger = setup_logger(name="test_logger", level="DEBUG")
        
        assert logger.name == "test_logger"
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) >= 1
    
    def test_get_logger(self):
        """测试获取日志"""
        logger1 = setup_logger(name="shared_logger")
        logger2 = get_logger(name="shared_logger")
        
        assert logger1 is logger2
    
    def test_logger_with_file(self):
        """测试日志写入文件"""
        with tempfile.NamedTemporaryFile(suffix='.log', delete=False) as f:
            log_path = f.name
        
        try:
            logger = setup_logger(
                name="file_logger",
                log_file=log_path,
                level="INFO"
            )
            
            logger.info("Test message")
            
            # 关闭 handlers 以便文件可以读取
            for handler in logger.handlers:
                handler.close()
            
            # 验证日志文件内容
            content = Path(log_path).read_text()
            assert "Test message" in content
        finally:
            Path(log_path).unlink()
    
    def test_logger_adapter(self):
        """测试日志适配器"""
        logger = setup_logger(name="adapter_logger")
        adapter = LoggerAdapter(logger, extra={"prefix": "TEST"})
        
        # 不应该抛出异常
        adapter.info("Test message")


class TestExceptions:
    """异常类测试"""
    
    def test_aitunnel_error(self):
        """测试基础异常"""
        error = AITunnelError(message="Test error", code="TEST_ERROR")
        
        assert str(error) == "TEST_ERROR: Test error"
        assert error.code == "TEST_ERROR"
        assert error.message == "Test error"
    
    def test_aitunnel_error_with_details(self):
        """测试带详细信息的异常"""
        error = AITunnelError(
            message="Test error",
            details={"key": "value"}
        )
        
        assert "key" in error.details
        assert error.details["key"] == "value"
    
    def test_aitunnel_error_to_dict(self):
        """测试异常转字典"""
        error = AITunnelError(
            message="Test error",
            code="TEST_ERROR",
            details={"key": "value"}
        )
        
        error_dict = error.to_dict()
        
        assert error_dict["error"] == "AITunnelError"
        assert error_dict["code"] == "TEST_ERROR"
        assert error_dict["message"] == "Test error"
    
    def test_configuration_error(self):
        """测试配置错误"""
        error = ConfigurationError("Invalid config")
        
        assert error.code == "CONFIGURATION_ERROR"
        assert "Invalid config" in str(error)
    
    def test_tunnel_connection_error(self):
        """测试连接错误"""
        error = TunnelConnectionError(
            message="Connection failed",
            source="127.0.0.1:8080",
            target="192.168.1.1:443"
        )
        
        assert error.details["source"] == "127.0.0.1:8080"
        assert error.details["target"] == "192.168.1.1:443"
    
    def test_authentication_error(self):
        """测试认证错误"""
        error = AuthenticationError("Invalid credentials")
        
        assert error.code == "AUTHENTICATION_ERROR"
    
    def test_resource_not_found_error(self):
        """测试资源未找到错误"""
        error = ResourceNotFoundError(
            resource_type="用户",
            resource_id="123"
        )
        
        assert "用户未找到" in str(error)
        assert error.details["resource_id"] == "123"
    
    def test_validation_error(self):
        """测试验证错误"""
        error = ValidationError(
            message="Invalid email",
            field="email"
        )
        
        assert error.code == "VALIDATION_ERROR"
        assert error.details["field"] == "email"
    
    def test_handle_exception(self):
        """测试异常处理函数"""
        try:
            raise ValueError("Test error")
        except Exception as e:
            wrapped_error = handle_exception(e)
            
            assert isinstance(wrapped_error, AITunnelError)
            assert wrapped_error.code == "ValueError"
    
    def test_handle_aitunnel_error(self):
        """测试处理已包装的异常"""
        original_error = AITunnelError("Original error")
        wrapped_error = handle_exception(original_error)
        
        assert wrapped_error is original_error
