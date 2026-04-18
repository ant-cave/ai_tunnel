# AI Tunnel

AI API 隧道代理服务 - 统一的 AI 模型访问接口

## 项目简介

AI Tunnel 是一个高性能的 AI API 代理隧道服务，提供统一的接口来访问多个 AI 模型提供商。它支持请求路由、故障转移、健康检查、流式响应等功能，帮助企业和个人开发者轻松集成和管理多个 AI 服务。

## 主要特性

- **多提供商支持** - 支持配置多个 AI 模型提供商，统一接口访问
- **智能路由** - 根据配置自动路由请求到不同的提供商
- **故障转移** - 当主提供商不可用时，自动切换到备用提供商
- **健康检查** - 实时监控提供商服务状态，确保服务可用性
- **流式响应** - 完整支持 SSE 流式响应，提供流畅的对话体验
- **高性能** - 基于 asyncio 构建，支持高并发连接
- **灵活配置** - 使用 TOML 配置文件，支持热加载
- **安全可靠** - 支持 SSL/TLS 加密、API 密钥验证、速率限制

## 系统要求

- Python 3.8+
- Windows / Linux / macOS

## 安装

### 从源码安装

```bash
# 克隆仓库
git clone https://github.com/your-org/ai-tunnel.git
cd ai-tunnel

# 安装依赖
pip install -r requirements.txt

# 或者使用 pip 安装
pip install -e .
```

### 依赖项

主要依赖：
- `aiohttp` - 异步 HTTP 客户端/服务器
- `pydantic` - 数据验证和配置管理
- `tomli` / `toml` - TOML 配置文件解析
- `pyyaml` - YAML 支持
- `typing-extensions` - 类型提示扩展

## 快速开始

### 1. 生成配置文件

```bash
ai_tunnel init
```

这将在 `configs/` 目录下生成示例配置文件。

### 2. 配置提供商

编辑 `configs/config.toml` 文件，配置你的 AI 提供商：

```toml
# 服务器配置
[server]
host = "0.0.0.0"
port = 8080
workers = 4
max_connections = 1000
ssl_enabled = false

# 安全配置
[security]
api_key = "your-secret-api-key-here"
allowed_origins = ["*"]
rate_limit = 100

# API 提供商配置
[providers]

  [providers.provider_name]
  name = "provider_name"
  api_endpoint = "https://api.example.com"
  api_key = "your-api-key"
  timeout = 60
  retry_attempts = 3
  enabled = true
```

**重要提示：**
- 请勿将包含真实 API 密钥的配置文件提交到版本控制系统
- 使用 `.gitignore` 排除敏感配置文件
- 建议使用环境变量或密钥管理服务存储敏感信息

### 3. 启动服务

```bash
# 使用默认配置启动
ai_tunnel start

# 使用指定配置文件启动
ai_tunnel start -c configs/config.toml

# 验证配置文件
ai_tunnel validate -c configs/config.toml
```

## 命令行接口

```bash
# 查看帮助
ai_tunnel --help

# 查看版本
ai_tunnel --version

# 启动服务
ai_tunnel start [-c CONFIG_PATH]

# 验证配置
ai_tunnel validate [-c CONFIG_PATH]

# 生成配置示例
ai_tunnel init

# 显示配置信息
ai_tunnel show [-c CONFIG_PATH]
```

## API 使用

### 端点

AI Tunnel 提供以下 HTTP 端点：

- `POST /v1/chat/completions` - 聊天补全接口（兼容 OpenAI 格式）
- `GET /health` - 健康检查端点
- `GET /metrics` - 服务监控指标

### 请求示例

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "provider_name",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "stream": false
  }'
```

### 流式响应

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "provider_name",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "stream": true
  }'
```

## 配置说明

### 服务器配置 (`[server]`)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `host` | string | "0.0.0.0" | 监听地址 |
| `port` | int | 8080 | 监听端口 |
| `workers` | int | 4 | 工作进程数 |
| `max_connections` | int | 1000 | 最大连接数 |
| `keep_alive_timeout` | int | 60 | Keep-Alive 超时时间 (秒) |
| `request_timeout` | int | 30 | 请求超时时间 (秒) |
| `ssl_enabled` | bool | false | 是否启用 SSL |
| `ssl_cert_path` | string | - | SSL 证书路径 |
| `ssl_key_path` | string | - | SSL 私钥路径 |

### 安全配置 (`[security]`)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `api_key` | string | - | API 密钥 |
| `allowed_origins` | list | ["*"] | 允许的 CORS 源 |
| `rate_limit` | int | 100 | 速率限制 (请求/分钟) |
| `encryption_enabled` | bool | true | 是否启用加密 |

### 日志配置 (`[logging]`)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `level` | string | "INFO" | 日志级别 |
| `file` | string | - | 日志文件路径 |
| `max_size` | int | 10485760 | 日志文件最大大小 (字节) |
| `backup_count` | int | 5 | 日志文件备份数量 |

### 提供商配置 (`[providers]`)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | string | - | 提供商名称 |
| `api_endpoint` | string | - | API 端点 URL |
| `api_key` | string | - | API 密钥 |
| `timeout` | int | 60 | 超时时间 (秒) |
| `retry_attempts` | int | 3 | 重试次数 |
| `enabled` | bool | true | 是否启用 |

## 架构设计

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│         HTTP Server                 │
│  (aiohttp + SSL/TLS Support)        │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│         Router                      │
│  (Request Routing + Failover)       │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│      Provider Manager               │
│  (Health Check + Load Balancing)    │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────┴─────────────┐
│                           │
▼                           ▼
┌──────────────┐   ┌──────────────┐
│  Provider A  │   │  Provider B  │
└──────────────┘   └──────────────┘
```

### 核心模块

- **HTTP Server** (`src/server/`) - 异步 HTTP 服务器，处理请求和响应
- **Router** (`src/router/`) - 请求路由、故障转移、健康检查
- **Config** (`src/config/`) - 配置加载、验证、设置管理
- **Models** (`src/models/`) - 数据模型和配置对象
- **Utils** (`src/utils/`) - 工具函数、日志、异常处理、SSE 解析

## 开发

### 安装开发依赖

```bash
pip install -e ".[dev]"
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=src --cov-report=html

# 运行特定测试文件
pytest tests/test_router.py
```

### 代码格式化

```bash
# 格式化代码
black src/ tests/

# 排序导入
isort src/ tests/

# 代码检查
flake8 src/ tests/

# 类型检查
mypy src/
```

## 安全建议

1. **保护 API 密钥**
   - 不要将包含真实密钥的配置文件提交到 Git
   - 使用环境变量或密钥管理服务
   - 定期轮换 API 密钥

2. **启用 SSL/TLS**
   - 在生产环境中始终启用 HTTPS
   - 使用有效的 SSL 证书

3. **配置速率限制**
   - 根据实际需求调整速率限制
   - 防止滥用和 DDoS 攻击

4. **限制 CORS 源**
   - 不要在生产环境使用 `"*"`
   - 明确指定允许的域名

## 故障排除

### 常见问题

**Q: 无法连接到提供商**
- 检查提供商的 `api_endpoint` 配置是否正确
- 确认网络连接正常
- 检查防火墙设置

**Q: SSL 证书错误**
- 确保证书和私钥路径正确
- 检查证书格式是否正确
- 验证证书未过期

**Q: 性能问题**
- 增加 `workers` 数量
- 调整 `max_connections` 限制
- 优化提供商的 `timeout` 设置

### 日志查看

日志级别可通过配置文件或环境变量调整：

```bash
# 设置调试日志级别
export AI_TUNNEL_LOG_LEVEL=DEBUG
```

## 贡献

欢迎贡献代码！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 致谢

感谢所有为本项目做出贡献的开发者！

---

**注意**: 本项目仅供学习和研究使用。使用本服务时，请遵守相关服务提供商的使用条款和政策。
