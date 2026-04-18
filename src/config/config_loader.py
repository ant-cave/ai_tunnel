"""
配置加载器模块

负责从不同格式的文件中加载配置（支持 TOML、JSON、YAML）
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.utils.exceptions import ConfigurationError


class ConfigLoader:
    """配置加载器类
    
    支持多种配置文件格式：
    - TOML (.toml)
    - JSON (.json)
    - YAML (.yaml, .yml)
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
        suffix = self.config_path.suffix.lower()
        
        if suffix == ".toml":
            return self._load_toml()
        elif suffix == ".json":
            return self._load_json()
        elif suffix in [".yaml", ".yml"]:
            return self._load_yaml()
        else:
            raise ConfigurationError(f"不支持的配置文件格式：{suffix}")
    
    def _load_toml(self) -> Dict[str, Any]:
        """加载 TOML 配置文件
        
        Returns:
            Dict[str, Any]: 配置数据
            
        Raises:
            ConfigurationError: TOML 加载失败
        """
        try:
            import tomli
        except ImportError:
            try:
                import toml as tomli
            except ImportError:
                raise ConfigurationError("需要安装 toml 库：pip install tomli")
        
        try:
            with open(self.config_path, "rb") as f:
                return tomli.load(f)
        except Exception as e:
            raise ConfigurationError(f"TOML 文件加载失败：{str(e)}")
    
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
        except Exception as e:
            raise ConfigurationError(f"JSON 文件加载失败：{str(e)}")
    
    def _load_yaml(self) -> Dict[str, Any]:
        """加载 YAML 配置文件
        
        Returns:
            Dict[str, Any]: 配置数据
            
        Raises:
            ConfigurationError: YAML 加载失败
        """
        try:
            import yaml
        except ImportError:
            raise ConfigurationError("需要安装 PyYAML 库：pip install pyyaml")
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise ConfigurationError(f"YAML 文件加载失败：{str(e)}")
