"""
日志模块

提供统一的日志配置和管理功能
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logger(
    name: str = "ai_tunnel",
    level: str = "INFO",
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    format_string: Optional[str] = None
) -> logging.Logger:
    """设置并返回日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径（可选）
        max_bytes: 单个日志文件最大大小（字节）
        backup_count: 保留的备份文件数量
        format_string: 日志格式字符串
        
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    # 获取或创建 logger
    logger = logging.getLogger(name)
    
    # 如果已经配置过，直接返回
    if logger.handlers:
        return logger
    
    # 设置日志级别
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    
    # 设置日志格式
    if format_string is None:
        format_string = (
            "%(asctime)s - %(name)s - [%(levelname)s] "
            "%(filename)s:%(lineno)d - %(funcName)s() - %(message)s"
        )
    formatter = logging.Formatter(format_string)
    
    # 添加控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 添加文件处理器（如果指定了日志文件）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # 防止日志传播到父 logger
    logger.propagate = False
    
    return logger


def get_logger(name: str = "ai_tunnel") -> logging.Logger:
    """获取已存在的日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        logging.Logger: 日志记录器
    """
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """日志适配器
    
    可以在日志中添加额外的上下文信息
    """
    
    def process(self, msg: str, kwargs) -> tuple:
        """处理日志消息
        
        Args:
            msg: 日志消息
            kwargs: 其他参数
            
        Returns:
            tuple: (处理后的消息，kwargs)
        """
        prefix = self.extra.get("prefix", "")
        if prefix:
            return f"[{prefix}] {msg}", kwargs
        return msg, kwargs
