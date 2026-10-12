"""
第三方主站：仅功能码 03 批量读取，含完整异常处理与有效性判断。
"""
import time
from typing import Optional, Dict, Any

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import (
    ModbusException, ConnectionException, ModbusIOException,
)
from pymodbus.pdu import ExceptionResponse

from config.settings import settings
from core.codec import regs_to_dict, is_valid_float
from core.exceptions import describe_exception
from core.logger import get_logger

P = settings.protocol
log = get_logger("master")


class PumpMaster:
    def __init__(self, ip: str, port: int, unit: int = None,
                 poll_interval: float = 1.0, reconnect_interval: float = 3.0):
        self.ip = ip
        self.port = port
        self.unit = unit if unit is not None else P.UNIT_ID
        self.poll_interval = poll_interval
        self.reconnect_interval = reconnect_interval
        self.client: Optional[ModbusTcpClient] = None
        self.last_counter: Optional[int] = None
        self.stale_count = 0
        self.stats = {"ok": 0, "timeout": 0, "exception": 0, "stale": 0}

    # ---------- 连接管理 ----------
    def connect(self) -> bool:
        try:
            self.client = ModbusTcpClient(self.ip, port=self.port,
                                          timeout=3, retries=2)
            ok = self.client.connect()
            if ok:
                log.info("已连接 PLC %s:%d", self.ip, self.port)
            else:
                log.error("连接失败 PLC %s:%d", self.ip, self.port)
            return ok
        except Exception as e:  # noqa
            log.exception("建立连接异常: %s", e)
            return False

    def close(self):
        if self.client:
            try:
                self.client.close()
            except Exception:  # noqa
                pass

    def ensure_connected(self) -> bool:
        if self.client and self.client.connected:
            return True
        log.warning("链路断开，尝试重连 ...")
        self.close()
        return self.connect()

    # ---------- 读取 ----------
    def read_all(self) -> Optional[Dict[str, Any]]:
        if not self.ensure_connected():
            return None
        try:
            rr = self.client.read_holding_registers(
                address=P.BLOCK_START_MW, count=P.READ_COUNT, slave=self.unit,
            )
        except ConnectionException as e:
            self.stats["timeout"] += 1
            log.error("连接异常/超时: %s", e)
            return None
        except ModbusIOException as e:
            self.stats["timeout"] += 1
            log.error("Modbus IO 异常（可能超时）: %s", e)
            return None
        except ModbusException as e:
            self.stats["exception"] += 1
            log.error("Modbus 异常: %s", e)
            return None
        except Exception as e:  # noqa
            self.stats["exception"] += 1
            log.exception("未知读取异常: %s", e)
            return None

        # 异常响应判断
        if isinstance(rr, ExceptionResponse):
            code = rr.exception_code
            self.stats["exception"] += 1
            log.error("从站返回异常响应: 0x%02X %s",
                      code, describe_exception(code))
            return None
        if rr.isError():
            self.stats["exception"] += 1
            log.error("读取返回错误: %s", rr)
            return None
        if len(rr.registers) != P.READ_COUNT:
            self.stats["exception"] += 1
            log.error("寄存器数量不符: 期望 %d 实际 %d",
                      P.READ_COUNT, len(rr.registers))
            return None

        self.stats["ok"] += 1
        return regs_to_dict(rr.registers)

    # ---------- 有效性判断 ----------
    def check_validity(self, data: Dict[str, Any]) -> bool:
        counter = data.get("writeCounter")
        if self.last_counter is not None and counter == self.last_counter:
            self.stale_count += 1
            self.stats["stale"] += 1
            log.warning("writeCounter 未递增（=%s），数据可能为旧数据 "
                        "（连续 %d 次）", counter, self.stale_count)
        else:
            self.stale_count = 0
        self.last_counter = counter

        invalid = [k for k, v in data.items()
                   if k not in P.U16_FIELDS and not is_valid_float(v)]
        if invalid:
            log.warning("检测到无效测点编码: %s", ", ".join(invalid))
        return len(invalid) == 0

    # ---------- 打印 ----------
    def log_data(self, data: Dict[str, Any]):
        log.info(
            "writeCounter=%d | 进水瞬时=%.2f | 进水累计=%.2f | "
            "泵站总瞬时=%.2f | 日=%.2f 月=%.2f 年=%.2f | "
            "低告警=%d 高告警=%d",
            data["writeCounter"], data["instantInFlow"], data["totalInFlow"],
            data["pumpStationInstantTotalFlow"],
            data["pumpStationDayTotalFlow"],
            data["pumpStationMonthTotalFlow"],
            data["pumpStationYearTotalFlow"],
            data["lowFlowAlarm"], data["highFlowAlarm"],
        )
        for i in range(1, 5):
            log.info("  出水口%d: 瞬时=%.2f 累计=%.2f",
                     i, data[f"outInstantFlow_{i}"], data[f"outTotalFlow_{i}"])

    # ---------- 主循环 ----------
    def run(self):
        if not self.connect():
            log.error("初始连接失败，退出")
            return
        try:
            while True:
                data = self.read_all()
                if data is not None:
                    self.check_validity(data)
                    self.log_data(data)
                else:
                    time.sleep(self.reconnect_interval)
                    continue
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            log.info("收到 Ctrl+C，主站退出")
        finally:
            self.close()
            log.info("主站统计: %s", self.stats)