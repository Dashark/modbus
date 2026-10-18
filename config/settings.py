"""
配置加载：从 YAML 读取协议、从站、日志配置，并提供 Python 默认值兜底。
日志使用相对路径，由 logging.yaml 决定；请从项目根目录运行以落到 logs/。
"""
import os
import logging.config
from pathlib import Path
from types import SimpleNamespace

try:
    import yaml
except ImportError:
    yaml = None

# 项目根目录（settings.py 的上一级再上一级）
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)   # 仅保证 logs/ 存在，不改写 YAML 里的路径


def _load_yaml(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("需要 PyYAML: uv add pyyaml")
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Settings:
    def __init__(self):
        self._raw_protocol = _load_yaml(CONFIG_DIR / "protocol.yaml")
        self._raw_slave = _load_yaml(CONFIG_DIR / "slave.yaml")
        self._raw_logging = _load_yaml(CONFIG_DIR / "logging.yaml")
        self._raw_database = _load_yaml(CONFIG_DIR / "database.yaml")

    # ---- 协议 ----
    @property
    def protocol(self) -> SimpleNamespace:
        r = self._raw_protocol
        return SimpleNamespace(
            UNIT_ID=r["unit_id"],
            BLOCK_START_MW=r["block_start_mw"],
            REG_COUNT=r["reg_count"],
            READ_COUNT=r["read_count"],
            INVALID_FLOAT=r["invalid_float"],
            OFFSET=r["offsets"],
            FLOAT_FIELDS=r["float_fields"],
            U16_FIELDS=r["u16_fields"],
        )

    # ---- 从站 ----
    @property
    def slave(self) -> SimpleNamespace:
        r = self._raw_slave
        return SimpleNamespace(
            WRITE_PERIOD=r["write_period"],
            RANDOM=r["random"],
            COVERAGE_MODE=r["coverage_mode"],
            COVERAGE_SEQUENCE=r["coverage_sequence"],
            BASE_VALUES=r["base_values"],
        )

    # ---- 数据库 ----
    @property
    def database(self) -> SimpleNamespace:
        r = dict(self._raw_database)   # 浅拷贝，避免污染原始配置
        # 环境变量覆盖敏感/环境相关参数
        if os.getenv("PUMP_DB_HOST"):
            r["host"] = os.environ["PUMP_DB_HOST"]
        if os.getenv("PUMP_DB_PORT"):
            r["port"] = int(os.environ["PUMP_DB_PORT"])
        if os.getenv("PUMP_DB_NAME"):
            r["dbname"] = os.environ["PUMP_DB_NAME"]
        if os.getenv("PUMP_DB_USER"):
            r["user"] = os.environ["PUMP_DB_USER"]
        if os.getenv("PUMP_DB_PASSWORD"):
            r["password"] = os.environ["PUMP_DB_PASSWORD"]
        return SimpleNamespace(**r)

    # ---- 日志 ----
    def setup_logging(self):
        """
        直接加载 logging.yaml，不做路径改写。
        YAML 中的 filename（logs/slave.log、logs/master.log）
        按进程 CWD 解析，请从项目根目录启动。
        """
        logging.config.dictConfig(self._raw_logging)


settings = Settings()