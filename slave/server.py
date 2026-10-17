"""
从站启动入口。
"""
import threading
import sys

from pymodbus.server import StartTcpServer
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext,
)

from config.settings import settings
from core.logger import setup_logging, get_logger
from .generator import make_generator
from .writer import RegisterWriter

P = settings.protocol
S = settings.slave
log = get_logger("slave")


def build_context():
    store = ModbusSlaveContext(
        hr=ModbusSequentialDataBlock(P.BLOCK_START_MW, [0] * P.REG_COUNT),
        zero_mode=False,
    )
    return store, ModbusServerContext(slaves={P.UNIT_ID: store}, single=False)


def build_source(kind: str):
    """按类型构造数据源"""
    if kind == "db":
        from .db_source import DatabaseSource
        return DatabaseSource()
    return make_generator()


def main(source_kind: str = "db", mode: str = None, seed: int = None,
         host: str = "0.0.0.0", port: int = 502):
    setup_logging()
    store, context = build_context()
    source = build_source(source_kind)
    writer = RegisterWriter(store, source)

    log.info("从站启动 单元号=%d 块起始=%%MW%d 寄存器数=%d 周期=%.1fs 数据源=%s",
             P.UNIT_ID, P.BLOCK_START_MW, P.REG_COUNT,
             S.WRITE_PERIOD, type(source).__name__)

    t = threading.Thread(target=writer.run_forever, daemon=True, name="writer")
    t.start()

    try:
        StartTcpServer(context=context, address=(host, port))
    except KeyboardInterrupt:
        log.info("收到 Ctrl+C，从站退出")
    except OSError as e:
        log.error("端口 %d 占用或权限不足: %s（Linux 下 502 需 root，"
                  "可改用 5020）", port, e)
        sys.exit(1)
    finally:
        try:
            source.close()
        except Exception:  # noqa
            pass
        log.info("从站统计: 成功写入=%d 异常=%d",
                 writer.stats["writes"], writer.stats["errors"])
        if hasattr(source, "stats"):
            log.info("数据源统计: %s", source.stats)


if __name__ == "__main__":
    main()