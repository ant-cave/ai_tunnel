"""
基础模型模块

提供所有模型的基类，支持序列化和反序列化
"""

from abc import ABC
from dataclasses import asdict, fields
from typing import Any, Dict, Type, TypeVar

T = TypeVar("T", bound="BaseModel")


class BaseModel(ABC):
    """模型基类
    
    提供通用的序列化和反序列化方法
    所有数据模型都应继承此类
    """
    
    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """从字典创建模型实例
        
        Args:
            data: 包含模型字段的数据字典
            
        Returns:
            T: 模型实例
        """
        field_names = {f.name for f in fields(cls)}
        filtered_data = {
            k: v for k, v in data.items() if k in field_names
        }
        return cls(**filtered_data)
    
    def to_dict(self) -> Dict[str, Any]:
        """将模型转换为字典
        
        Returns:
            Dict[str, Any]: 模型数据字典
        """
        return asdict(self)
    
    def to_json(self) -> str:
        """将模型转换为 JSON 字符串
        
        Returns:
            str: JSON 字符串
        """
        import json
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls: Type[T], json_str: str) -> T:
        """从 JSON 字符串创建模型实例
        
        Args:
            json_str: JSON 字符串
            
        Returns:
            T: 模型实例
        """
        import json
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def update(self, **kwargs) -> None:
        """更新模型字段
        
        Args:
            **kwargs: 要更新的字段和值
        """
        field_names = {f.name for f in fields(self)}
        for key, value in kwargs.items():
            if key in field_names:
                setattr(self, key, value)
    
    def __repr__(self) -> str:
        """获取模型字符串表示"""
        class_name = self.__class__.__name__
        fields_str = ", ".join(
            f"{f.name}={getattr(self, f.name)!r}"
            for f in fields(self)
        )
        return f"{class_name}({fields_str})"
