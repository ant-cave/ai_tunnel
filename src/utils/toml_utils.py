"""
TOML 工具模块

提供 Python 3.10 和 3.11+ 兼容的 TOML 加载功能
"""
import sys
from pathlib import Path
from typing import Any, Dict


def load_toml(file_path: Path) -> Dict[str, Any]:
    """
    加载 TOML 文件，兼容 Python 3.10 和 3.11+
    
    Args:
        file_path: TOML 文件路径
        
    Returns:
        解析后的字典
        
    Raises:
        FileNotFoundError: 文件不存在
        ImportError: 未安装必要的 TOML 库
    """
    if not file_path.exists():
        raise FileNotFoundError(f"TOML 文件不存在：{file_path}")
    
    try:
        tomllib = _get_tomllib()
        with open(file_path, "rb") as f:
            return tomllib.load(f)
    except ImportError as e:
        raise ImportError(
            "需要安装 tomli 库：pip install tomli"
        ) from e


def _get_tomllib():
    """
    获取 TOML 加载模块
    
    Python 3.11+ 使用内置的 tomllib
    Python 3.10 及以下使用 tomli 库
    
    Returns:
        tomllib 或 tomli 模块
        
    Raises:
        ImportError: 未安装必要的库
    """
    if sys.version_info >= (3, 11):
        import tomllib
        return tomllib
    else:
        try:
            import tomli
            return tomli
        except ImportError:
            raise ImportError(
                "Python 3.10 及以下版本需要安装 tomli 库：pip install tomli"
            )


def loads_toml(content: str) -> Dict[str, Any]:
    """
    从字符串加载 TOML 内容
    
    Args:
        content: TOML 格式的字符串
        
    Returns:
        解析后的字典
        
    Raises:
        ImportError: 未安装必要的 TOML 库
    """
    try:
        tomllib = _get_tomllib()
        return tomllib.loads(content)
    except ImportError as e:
        raise ImportError(
            "需要安装 tomli 库：pip install tomli"
        ) from e
