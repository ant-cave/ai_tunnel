"""
SSE (Server-Sent Events) 解析器模块

负责解析 Server-Sent Events 格式的数据流，
支持 data:、event:、id:等字段解析，
处理流式数据块。
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, AsyncIterator, Union
from enum import Enum
import logging
import re

logger = logging.getLogger(__name__)


class SSEEventType(Enum):
    """SSE 事件类型"""
    MESSAGE = "message"
    ERROR = "error"
    DONE = "done"
    CUSTOM = "custom"


@dataclass
class SSEEvent:
    """
    SSE 事件数据类
    
    封装解析后的 SSE 事件信息
    """
    event_type: str = ""
    data: str = ""
    event_id: Optional[str] = None
    retry: Optional[int] = None
    raw: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "event_type": self.event_type,
            "data": self.data,
        }
        if self.event_id is not None:
            result["id"] = self.event_id
        if self.retry is not None:
            result["retry"] = self.retry
        return result

    def is_done(self) -> bool:
        """检查是否为结束事件"""
        return self.data.strip() == "[DONE]" or self.event_type == "done"

    def parse_data_json(self) -> Any:
        """解析 data 字段为 JSON 对象"""
        import json
        if not self.data:
            return None
        try:
            return json.loads(self.data)
        except json.JSONDecodeError as e:
            logger.warning(f"解析 SSE data JSON 失败：{e}")
            return None


@dataclass
class SSEParserState:
    """SSE 解析器状态"""
    last_event_id: Optional[str] = None
    buffer: str = ""
    current_event: Optional[SSEEvent] = None
    lines_processed: int = 0


class SSEParser:
    """
    SSE 解析器
    
    负责解析 Server-Sent Events 格式的数据流
    
    SSE 格式规范：
    - 每行以 LF(\n) 或 CRLF(\r\n) 结尾
    - 字段格式：field: value
    - 支持的字段：data, event, id, retry
    - 空行表示事件结束
    - 以冒号开头的行是注释，应忽略
    """

    def __init__(self):
        self.state = SSEParserState()
        self._current_data_lines: List[str] = []
        self._current_event_type: str = ""
        self._current_event_id: Optional[str] = None
        self._current_retry: Optional[int] = None

    def reset(self):
        """重置解析器状态"""
        self.state = SSEParserState()
        self._current_data_lines = []
        self._current_event_type = ""
        self._current_event_id = None
        self._current_retry = None
        logger.debug("SSE 解析器已重置")

    def parse_line(self, line: str) -> Optional[SSEEvent]:
        """
        解析单行 SSE 数据
        
        Args:
            line: 单行数据
            
        Returns:
            如果解析完成一个事件则返回 SSEEvent，否则返回 None
        """
        self.state.lines_processed += 1
        
        # 移除行尾的换行符
        line = line.rstrip('\r\n')
        
        # 空行表示事件结束
        if not line:
            return self._dispatch_event()
        
        # 注释行，忽略
        if line.startswith(':'):
            logger.debug(f"忽略 SSE 注释：{line}")
            return None
        
        # 解析字段
        field, value = self._parse_field(line)
        if field is None:
            logger.warning(f"无效的 SSE 行：{line}")
            return None
        
        # 处理不同字段
        if field == 'data':
            self._current_data_lines.append(value)
        elif field == 'event':
            self._current_event_type = value
        elif field == 'id':
            self._current_event_id = value
            self.state.last_event_id = value
        elif field == 'retry':
            try:
                self._current_retry = int(value)
            except ValueError:
                logger.warning(f"无效的 retry 值：{value}")
        
        return None

    def parse_chunk(self, chunk: Union[str, bytes]) -> List[SSEEvent]:
        """
        解析数据块（可能包含多行）
        
        Args:
            chunk: 数据块
            
        Returns:
            解析出的事件列表
        """
        if isinstance(chunk, bytes):
            chunk = chunk.decode('utf-8', errors='ignore')
        
        events = []
        lines = chunk.split('\n')
        
        for line in lines:
            event = self.parse_line(line)
            if event:
                events.append(event)
        
        return events

    async def parse_stream(self, stream: AsyncIterator[Union[str, bytes]]) -> AsyncIterator[SSEEvent]:
        """
        异步解析流式数据
        
        Args:
            stream: 异步数据流
            
        Yields:
            解析后的 SSE 事件
        """
        async for chunk in stream:
            events = self.parse_chunk(chunk)
            for event in events:
                yield event

    def _parse_field(self, line: str) -> tuple:
        """
        解析 SSE 字段
        
        Args:
            line: 单行数据
            
        Returns:
            (field, value) 元组，如果解析失败返回 (None, None)
        """
        # 查找第一个冒号
        colon_index = line.find(':')
        
        # 没有冒号，整行作为 field，value 为空
        if colon_index == -1:
            return (line, '')
        
        field = line[:colon_index]
        
        # value 是冒号后的内容，如果冒号后有空格则去掉
        value = line[colon_index + 1:]
        if value.startswith(' '):
            value = value[1:]
        
        return (field, value)

    def _dispatch_event(self) -> Optional[SSEEvent]:
        """
        分发当前累积的事件
        
        Returns:
            解析出的事件，如果没有数据则返回 None
        """
        # 如果没有数据行，不创建事件
        if not self._current_data_lines:
            self._reset_current_event()
            return None
        
        # 合并数据行（用换行符连接）
        data = '\n'.join(self._current_data_lines)
        
        # 创建事件
        event = SSEEvent(
            event_type=self._current_event_type or SSEEventType.MESSAGE.value,
            data=data,
            event_id=self._current_event_id,
            retry=self._current_retry,
            raw='\n'.join(self._current_data_lines),
        )
        
        logger.debug(f"解析 SSE 事件：type={event.event_type}, data_len={len(data)}")
        
        # 重置当前事件状态
        self._reset_current_event()
        
        return event

    def _reset_current_event(self):
        """重置当前事件状态"""
        self._current_data_lines = []
        self._current_event_type = ""
        self._current_event_id = None
        self._current_retry = None


class StreamingSSEParser:
    """
    流式 SSE 解析器
    
    专为高性能流式处理设计，支持增量解析
    """

    def __init__(self, buffer_size: int = 4096):
        self.buffer_size = buffer_size
        self._buffer = ""
        self._parser = SSEParser()
        self._position = 0

    def feed(self, data: Union[str, bytes]) -> List[SSEEvent]:
        """
        向解析器提供新数据
        
        Args:
            data: 新数据
            
        Returns:
            解析出的事件列表
        """
        if isinstance(data, bytes):
            data = data.decode('utf-8', errors='ignore')
        
        # 添加到缓冲区
        self._buffer += data
        
        # 查找完整的事件（以双换行符分隔）
        events = []
        
        while True:
            # 查找事件分隔符
            event_end = self._buffer.find('\n\n', self._position)
            
            if event_end == -1:
                # 没有找到完整事件，保留剩余数据
                self._buffer = self._buffer[self._position:]
                self._position = 0
                break
            
            # 提取事件数据
            event_data = self._buffer[self._position:event_end]
            self._position = event_end + 2  # 跳过 \n\n
            
            # 解析事件
            event = self._parse_single_event(event_data)
            if event:
                events.append(event)
        
        return events

    def _parse_single_event(self, event_data: str) -> Optional[SSEEvent]:
        """解析单个事件数据"""
        lines = event_data.split('\n')
        
        event_type = ""
        data_lines = []
        event_id = None
        retry = None
        
        for line in lines:
            line = line.rstrip('\r')
            
            if not line:
                continue
            
            if line.startswith(':'):
                continue
            
            field, value = self._parser._parse_field(line)
            
            if field == 'data':
                data_lines.append(value)
            elif field == 'event':
                event_type = value
            elif field == 'id':
                event_id = value
            elif field == 'retry':
                try:
                    retry = int(value)
                except ValueError:
                    pass
        
        if not data_lines:
            return None
        
        return SSEEvent(
            event_type=event_type or SSEEventType.MESSAGE.value,
            data='\n'.join(data_lines),
            event_id=event_id,
            retry=retry,
            raw=event_data,
        )

    def reset(self):
        """重置解析器"""
        self._buffer = ""
        self._position = 0
        self._parser.reset()

    def get_buffer_size(self) -> int:
        """获取当前缓冲区大小"""
        return len(self._buffer)


def parse_sse_stream(stream: Union[str, bytes, List[Union[str, bytes]]]) -> List[SSEEvent]:
    """
    便捷函数：解析 SSE 流
    
    Args:
        stream: SSE 流数据
        
    Returns:
        解析后的事件列表
    """
    parser = SSEParser()
    
    if isinstance(stream, (str, bytes)):
        return parser.parse_chunk(stream)
    elif isinstance(stream, list):
        events = []
        for chunk in stream:
            events.extend(parser.parse_chunk(chunk))
        return events
    
    return []


async def parse_sse_async_stream(
    stream: AsyncIterator[Union[str, bytes]]
) -> AsyncIterator[SSEEvent]:
    """
    便捷函数：异步解析 SSE 流
    
    Args:
        stream: 异步 SSE 流
        
    Yields:
        解析后的事件
    """
    parser = SSEParser()
    
    async for chunk in stream:
        events = parser.parse_chunk(chunk)
        for event in events:
            yield event
