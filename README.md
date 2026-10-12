# 泵站流量检测系统 Modbus TCP

## 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)（唯一需要手工安装的工具）

安装 uv：

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## 快速开始

```bash
# 1. 进入项目根目录
cd pump_modbus

# 2. 安装依赖（uv 会自动创建 .venv 并安装锁定版本）
uv sync --extra dev

# 3. 跑单元测试，确认环境正确
# 全部测试
uv run pytest

# 指定文件
uv run pytest tests/test_codec.py -v
uv run pytest tests/test_generator.py -v
uv run pytest tests/test_master_faults.py -v
uv run pytest tests/test_integration.py -v

# 带覆盖率
uv run pytest --cov --cov-report=term-missing
uv run pytest --cov --cov-report=html     # 生成 htmlcov/index.html

# 4. 启动从站（终端 A，覆盖模式 22 秒跑完全部测点）
# 默认：读 config/slave.yaml 的 coverage_mode（false=随机）
uv run python run_slave.py

# 覆盖模式（22 秒覆盖全部测点 + 3 种告警组合）
uv run python run_slave.py --mode coverage

# 随机模式 + 固定种子
uv run python run_slave.py --mode random --seed 42

# 非 root 端口（Linux/macOS 下 <1024 需 root）
uv run python run_slave.py --port 5020

# 5. 启动主站（终端 B）
uv run python run_master.py --ip 127.0.0.1 --port 5020

```

## 日志

- 从站日志：`logs/slave.log`
- 主站日志：`logs/master.log`
- 控制台同时输出

**务必从项目根目录启动**，否则日志文件会落到别的目录。

## 常用命令

| 目的 | 命令 |
|------|------|
| 安装依赖 | `uv sync --extra dev` |
| 跑测试 | `uv run pytest` |
| 带覆盖率 | `uv run pytest --cov --cov-report=term-missing` |
| 从站-覆盖模式 | `uv run python run_slave.py --mode coverage --port 5020` |
| 从站-随机模式 | `uv run python run_slave.py --mode random --seed 42 --port 5020` |
| 主站 | `uv run python run_master.py --port 5020` |
| 格式化 | `uv run ruff format .` |
| 静态检查 | `uv run ruff check .` |
| 类型检查 | `uv run mypy config core slave master` |

## 端口说明

- Linux / macOS 下 502 < 1024，需要 root
- **推荐使用 5020**，避免权限问题

## 配置

| 文件 | 用途 |
|------|------|
| `config/protocol.yaml` | 协议常量（单元号、块起始、偏移表） |
| `config/slave.yaml` | 从站参数（随机概率、覆盖序列、基准值） |
| `config/logging.yaml` | 日志（控制台 + slave.log + master.log） |

## 故障排查

| 现象 | 解决 |
|------|------|
| `uv: command not found` | 按上文安装 uv |
| `ModuleNotFoundError: config` | 确认在项目根目录运行 `uv sync --extra dev` |
| 端口 502 权限拒绝 | 改用 `--port 5020` |
| `FileNotFoundError: logs/...` | 从项目根目录启动，或手动 `mkdir logs` |