"""
寄存器写入器：把生成的一轮数据编码并写入从站保持寄存器。
支持暂停开关（用于触发主站 stale 判断）。
"""
import threading
import time
import struct
from typing import Dict, Any

from pymodbus.datastore import ModbusSlaveContext

from config.settings import settings
from core.codec import dict_to_regs
from core.logger import get_logger

P = settings.protocol
S = settings.slave
log = get_logger("slave.writer")


class RegisterWriter:
    def __init__(self, store: ModbusSlaveContext, generator):
        self.store = store
        self.generator = generator
        self.counter = 0
        self.stats = {"writes": 0, "errors": 0}
        self.pause_event = threading.Event()   # set 时暂停写入

    # ---- 暂停 / 恢复（供外部或测试调用） ----
    def pause(self):
        self.pause_event.set()
        log.warning("写入已暂停")

    def resume(self):
        self.pause_event.clear()
        log.info("写入已恢复")

    # ---- 单轮写入 ----
    def write_round(self, data: Dict[str, Any]) -> bool:
        try:
            regs = dict_to_regs(data)
            self.store.setValues(3, P.BLOCK_START_MW, regs)
            self.stats["writes"] += 1
            return True
        except struct.error as e:
            self.stats["errors"] += 1
            log.error("结构体编码异常: %s", e)
        except (TypeError, ValueError) as e:
            self.stats["errors"] += 1
            log.error("数据编码异常: %s", e)
        except Exception as e:  # noqa
            self.stats["errors"] += 1
            log.exception("未知写入异常: %s", e)
        return False

    # ---- 主循环 ----
    def run_forever(self):
        while True:
            if self.pause_event.is_set():
                log.info("写入暂停中，writeCounter 保持 = %d", self.counter)
                time.sleep(S.WRITE_PERIOD)
                continue

            self.counter = (self.counter + 1) & 0xFFFF
            data = self.generator.next_round(self.counter)
            if self.write_round(data):
                log.info(
                    "第 %d 轮写入成功 | 进水瞬时=%.2f | 泵站总瞬时=%.2f | "
                    "低告警=%d 高告警=%d | 写计数=%d",
                    self.stats["writes"],
                    data["instantInFlow"],
                    data["pumpStationInstantTotalFlow"],
                    data["lowFlowAlarm"],
                    data["highFlowAlarm"],
                    data["writeCounter"],
                )
            time.sleep(S.WRITE_PERIOD)