"""
pytest 配置文件

提供全局的 pytest 配置和 fixtures
"""

import pytest
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def test_config():
    """测试配置 fixture"""
    return {
        "server": {
            "host": "127.0.0.1",
            "port": 8080
        },
        "logging": {
            "level": "DEBUG"
        }
    }


@pytest.fixture
def sample_connection_data():
    """示例连接数据 fixture"""
    return {
        "id": "test_conn_001",
        "name": "Test Connection",
        "source_host": "localhost",
        "source_port": 8080,
        "target_host": "remote",
        "target_port": 443
    }


@pytest.fixture
def sample_request():
    """示例请求 fixture"""
    from src.router.middleware import Request
    
    return Request(
        method="GET",
        path="/test",
        headers={"Content-Type": "application/json"},
        query_params={"key": "value"}
    )


@pytest.fixture
def sample_response():
    """示例响应 fixture"""
    from src.router.middleware import Response
    
    return Response(
        status=200,
        body={"message": "success"},
        headers={"Content-Type": "application/json"}
    )


@pytest.fixture
def temp_config_file(tmp_path):
    """临时配置文件 fixture"""
    def _create_config(content, suffix=".json"):
        config_file = tmp_path / f"config{suffix}"
        config_file.write_text(content)
        return str(config_file)
    
    return _create_config
