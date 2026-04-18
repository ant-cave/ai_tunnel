"""
配置加载器模块

负责从 JSON 文件中加载配置
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.utils.exceptions import ConfigurationError


class ConfigLoader:
    """配置加载器类
    
    仅支持 JSON 配置文件格式
    """
    
    def __init__(self, config_path: str):
        """初始化配置加载器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        
        if not self.config_path.exists():
            raise ConfigurationError(f"配置文件不存在：{config_path}")
    
    def load(self) -> Dict[str, Any]:
        """加载配置文件
        
        Returns:
            Dict[str, Any]: 配置数据字典
            
        Raises:
            ConfigurationError: 配置文件加载失败
        """
        return self._load_json()
    
    def _load_json(self) -> Dict[str, Any]:
        """加载 JSON 配置文件
        
        Returns:
            Dict[str, Any]: 配置数据
            
        Raises:
            ConfigurationError: JSON 加载失败
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"JSON 文件格式错误：{str(e)}")
        except Exception as e:
            raise ConfigurationError(f"JSON 文件加载失败：{str(e)}")
