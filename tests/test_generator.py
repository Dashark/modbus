import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import settings
from core.codec import is_invalid_float
from slave.generator import DataGenerator, CoverageGenerator, make_generator

P = settings.protocol


class TestRandomGenerator(unittest.TestCase):

    def test_fields_present(self):
        gen = DataGenerator(invalid_prob=0.0, alarm_prob=0.0, seed=1)
        data = gen.next_round(1)
        for k in P.OFFSET:
            self.assertIn(k, data)
        self.assertEqual(data["writeCounter"], 1)
        self.assertIn(data["lowFlowAlarm"], (0, 1))
        self.assertIn(data["highFlowAlarm"], (0, 1))

    def test_invalid_prob_1(self):
        gen = DataGenerator(invalid_prob=1.0, alarm_prob=0.0, seed=2)
        data = gen.next_round(2)
        for k in P.FLOAT_FIELDS:
            self.assertTrue(is_invalid_float(data[k]),
                            f"{k} 应为无效编码")

    def test_invalid_prob_0(self):
        gen = DataGenerator(invalid_prob=0.0, alarm_prob=0.0, seed=3)
        for _ in range(50):
            data = gen.next_round(1)
            for k in P.FLOAT_FIELDS:
                self.assertFalse(is_invalid_float(data[k]))


class TestCoverageGenerator(unittest.TestCase):

    def test_covers_all_float_fields(self):
        """覆盖模式一个完整周期内，每个浮点测点至少被注入一次 NaN"""
        gen = CoverageGenerator()
        n = len(gen.sequence)
        seen = set()
        for i in range(n):
            data = gen.next_round(i + 1)
            for k in P.FLOAT_FIELDS:
                if is_invalid_float(data[k]):
                    seen.add(k)
        missing = set(P.FLOAT_FIELDS) - seen
        self.assertEqual(missing, set(), f"未覆盖的测点: {missing}")

    def test_covers_alarm_kinds(self):
        """覆盖模式应至少触发 low/high/both 三种告警组合"""
        gen = CoverageGenerator()
        n = len(gen.sequence)
        combos = set()
        for i in range(n):
            data = gen.next_round(i + 1)
            combos.add((data["lowFlowAlarm"], data["highFlowAlarm"]))
        self.assertIn((1, 0), combos)
        self.assertIn((0, 1), combos)
        self.assertIn((1, 1), combos)

    def test_normal_round(self):
        """覆盖模式应存在一轮全部正常"""
        gen = CoverageGenerator()
        n = len(gen.sequence)
        found_normal = False
        for i in range(n):
            data = gen.next_round(i + 1)
            invalid = [k for k in P.FLOAT_FIELDS if is_invalid_float(data[k])]
            if not invalid and data["lowFlowAlarm"] == 0 and data["highFlowAlarm"] == 0:
                found_normal = True
                break
        self.assertTrue(found_normal, "覆盖序列中缺少全正常轮次")

    def test_sequence_length_matches_config(self):
        gen = CoverageGenerator()
        self.assertEqual(len(gen.sequence), len(settings.slave.COVERAGE_SEQUENCE))

    def test_factory(self):
        self.assertIsInstance(make_generator(mode="coverage"), CoverageGenerator)
        self.assertIsInstance(make_generator(mode="random"), DataGenerator)


if __name__ == "__main__":
    unittest.main(verbosity=2)