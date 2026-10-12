import math
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import settings
from core.codec import (
    float_to_regs, regs_to_float, u16_to_reg, reg_to_u16,
    dict_to_regs, regs_to_dict, is_valid_float, is_invalid_float,
)
from core.exceptions import describe_exception

P = settings.protocol


class TestFloatCodec(unittest.TestCase):

    def test_doc_example_125_68(self):
        regs = float_to_regs(125.68)
        self.assertEqual(regs[0], 0x5C29)
        self.assertEqual(regs[1], 0x42FB)

    def test_doc_example_decode(self):
        self.assertAlmostEqual(regs_to_float(0x5C29, 0x42FB), 125.68, places=2)

    def test_roundtrip_many(self):
        import random
        for _ in range(2000):
            v = random.uniform(-1e6, 1e6)
            regs = float_to_regs(v)
            self.assertAlmostEqual(regs_to_float(*regs), v,
                                   delta=abs(v) * 1e-6 + 1e-6)

    def test_zero(self):
        self.assertEqual(float_to_regs(0.0), [0x0000, 0x0000])

    def test_negative(self):
        regs = float_to_regs(-12.5)
        self.assertAlmostEqual(regs_to_float(*regs), -12.5, places=3)

    def test_high_byte_first(self):
        regs = float_to_regs(125.68)
        self.assertEqual((regs[1] >> 8) & 0xFF, 0x42)
        self.assertEqual(regs[1] & 0xFF, 0xFB)

    def test_nan_invalid(self):
        regs = float_to_regs(P.INVALID_FLOAT)
        back = regs_to_float(*regs)
        self.assertTrue(math.isnan(back))
        self.assertTrue(is_invalid_float(back))
        self.assertFalse(is_valid_float(back))

    def test_inf_invalid(self):
        for v in (float("inf"), float("-inf")):
            self.assertTrue(is_invalid_float(regs_to_float(*float_to_regs(v))))


class TestU16(unittest.TestCase):
    def test_encode(self):
        self.assertEqual(u16_to_reg(0), [0])
        self.assertEqual(u16_to_reg(65535), [65535])
        self.assertEqual(u16_to_reg(65536), [0])
        self.assertEqual(u16_to_reg(-1), [65535])

    def test_decode(self):
        self.assertEqual(reg_to_u16(0xFFFF), 65535)
        self.assertEqual(reg_to_u16(0x10000), 0)


class TestBlockCodec(unittest.TestCase):
    def test_length(self):
        data = {k: 1.0 for k in P.OFFSET}
        data["lowFlowAlarm"] = 0
        data["highFlowAlarm"] = 1
        data["writeCounter"] = 42
        regs = dict_to_regs(data)
        self.assertEqual(len(regs), P.REG_COUNT)
        self.assertEqual(regs[P.OFFSET["writeCounter"]], 42)

    def test_roundtrip(self):
        data = {k: 1.5 for k in P.OFFSET}
        data["lowFlowAlarm"] = 0
        data["highFlowAlarm"] = 1
        data["writeCounter"] = 123
        back = regs_to_dict(dict_to_regs(data))
        self.assertEqual(back["writeCounter"], 123)
        self.assertAlmostEqual(back["instantInFlow"], 1.5, places=5)

    def test_all_fields(self):
        data = {k: 0.0 for k in P.OFFSET}
        back = regs_to_dict(dict_to_regs(data))
        for k in P.OFFSET:
            self.assertIn(k, back)


class TestExceptionDescribe(unittest.TestCase):
    def test_known(self):
        self.assertIn("非法功能码", describe_exception(0x01))
        self.assertIn("非法数据地址", describe_exception(0x02))
        self.assertIn("非法数据值", describe_exception(0x03))
        self.assertIn("从站设备故障", describe_exception(0x04))

    def test_unknown(self):
        self.assertIn("未知", describe_exception(0x7F))


class TestAddressMapping(unittest.TestCase):
    def test_read_count_within_limit(self):
        self.assertLessEqual(P.READ_COUNT, 125)

    def test_float_offsets_even(self):
        for k in P.FLOAT_FIELDS:
            self.assertEqual(P.OFFSET[k] % 2, 0, f"{k} 偏移应为偶数")


if __name__ == "__main__":
    unittest.main(verbosity=2)