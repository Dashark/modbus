"""
集成测试：启动从站覆盖模式 + 主站读取，验证 22 轮覆盖序列全部命中。
需要本机 5020 端口可绑定（非 root）。
"""
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import settings
from core.logger import setup_logging
from slave.server import build_context
from slave.generator import CoverageGenerator
from slave.writer import RegisterWriter
from master.client import PumpMaster
from core.codec import is_invalid_float

P = settings.protocol

# 集成测试用内存 store，不启动 TCP server
class TestIntegrationMemory(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        setup_logging()

    def test_coverage_roundtrip_via_registers(self):
        """覆盖模式 -> 写入寄存器 -> 主站解码，验证 16 测点全覆盖"""
        store, _ = build_context()
        gen = CoverageGenerator()
        writer = RegisterWriter(store, gen)

        seen_invalid = set()
        seen_alarm = set()
        n = len(gen.sequence)

        for i in range(n):
            writer.counter = i + 1
            data = gen.next_round(writer.counter)
            writer.write_round(data)

            # 从寄存器读回（模拟主站）
            regs = store.getValues(3, P.BLOCK_START_MW, P.REG_COUNT)
            from core.codec import regs_to_dict
            back = regs_to_dict(regs)

            for k in P.FLOAT_FIELDS:
                if is_invalid_float(back[k]):
                    seen_invalid.add(k)
            seen_alarm.add((back["lowFlowAlarm"], back["highFlowAlarm"]))

        self.assertEqual(set(P.FLOAT_FIELDS) - seen_invalid, set(),
                         f"未覆盖测点: {set(P.FLOAT_FIELDS) - seen_invalid}")
        self.assertIn((1, 0), seen_alarm)
        self.assertIn((0, 1), seen_alarm)
        self.assertIn((1, 1), seen_alarm)


if __name__ == "__main__":
    unittest.main(verbosity=2)