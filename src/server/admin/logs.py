import logging
import threading
from datetime import datetime
from typing import Optional

from aiohttp import web
from aiohttp.web_request import Request

logger = logging.getLogger("ai_tunnel.admin.logs")


class MemoryLogHandler(logging.Handler):
    """基于环形缓冲区的内存日志处理器"""

    def __init__(self, capacity: int = 1000):
        super().__init__()
        self.capacity = capacity
        self._buffer = []
        self._index = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord):
        entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "filename": record.pathname,
            "lineno": record.lineno,
        }
        with self._lock:
            if len(self._buffer) < self.capacity:
                self._buffer.append(entry)
            else:
                self._buffer[self._index] = entry
            self._index = (self._index + 1) % self.capacity

    def get_logs(self, level: Optional[str] = None, limit: int = 100, search: Optional[str] = None) -> list:
        with self._lock:
            logs = list(self._buffer)

        if level:
            level_upper = level.upper()
            logs = [log for log in logs if log["level"] == level_upper]

        if search:
            search_lower = search.lower()
            logs = [log for log in logs if search_lower in log["message"].lower()]

        logs.reverse()
        return logs[:limit]

    def clear(self):
        with self._lock:
            self._buffer.clear()
            self._index = 0


_memory_handler = None


def setup_log_memory_handler(capacity: int = 1000, logger_name: str = "ai_tunnel") -> MemoryLogHandler:
    """设置内存日志处理器

    Args:
        capacity: 环形缓冲区容量
        logger_name: 要监听的日志记录器名称

    Returns:
        MemoryLogHandler 实例
    """
    global _memory_handler
    target_logger = logging.getLogger(logger_name)
    for handler in target_logger.handlers[:]:
        if isinstance(handler, MemoryLogHandler):
            target_logger.removeHandler(handler)
    handler = MemoryLogHandler(capacity=capacity)
    target_logger.addHandler(handler)
    _memory_handler = handler
    return handler


def clear_logs():
    """清空内存日志"""
    global _memory_handler
    if _memory_handler:
        _memory_handler.clear()


def create_get_logs_handler():
    async def get_logs(request: Request, **kwargs) -> web.Response:
        global _memory_handler
        level = request.query.get("level")
        limit_str = request.query.get("limit", "100")
        search = request.query.get("search")
        try:
            limit = int(limit_str)
        except ValueError:
            limit = 100
        if _memory_handler:
            logs = _memory_handler.get_logs(level=level, limit=limit, search=search)
        else:
            logs = []
        return web.json_response({"logs": logs, "total": len(logs)})
    return get_logs
