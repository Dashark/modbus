"""
数据库数据源单元测试：
- SQL 列 -> 点表字段映射
- 布尔告警转 U16
- 缺失字段填无效编码 / 0
- calc_status 异常 -> 全无效
- calc_time 过期 -> 全无效
- 查询异常 -> 全无效
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import settings
from core.codec import is_invalid_float
from slave.db_source import DatabaseSource

P = settings.protocol
D = settings.database


def _make_row(**overrides):
    """构造一行典型 SQL 结果（含新增的 v_out_a/b/c/d）"""
    row = {
        "calc_time": datetime.now(timezone.utc),
        "calc_status": D.valid_calc_status,
        "q_in_raw": 125.68,
        "v_in_total": 123456.78,
        "outlet_a": 30.1,
        "outlet_b": 30.2,
        "outlet_c": 30.3,
        "outlet_d": 30.4,
        "v_out_a": 10000.1,
        "v_out_b": 10000.2,
        "v_out_c": 10000.3,
        "v_out_d": 10000.4,
        "v_out_total": 40001.0,          # = a+b+c+d
        "q_return": 5.5,
        "v_return_total": 5000.5,
        "q_total_out": 120.18,
        "v_day": 2880.0,
        "v_month": 86400.0,
        "v_year": 1051200.0,
        "flag_low_flow": False,
        "flag_high_flow": False,
    }
    row.update(overrides)
    return row


def _make_source():
    src = DatabaseSource.__new__(DatabaseSource)
    src.dsn = ""
    src.pool = None
    src.stats = {
        "ok": 0, "query_error": 0, "empty": 0,
        "stale": 0, "bad_status": 0,
        "consistency_mismatch": 0, "last_calc_time": None,
    }
    src._diag_cols = set(getattr(D, "diagnostic_columns", []) or [])
    return src


class TestDatabaseSourceMapping(unittest.TestCase):

    def setUp(self):
        self.src = _make_source()

    def test_basic_mapping(self):
        data = self.src._row_to_data(_make_row(), counter=1)
        self.assertAlmostEqual(data["instantInFlow"], 125.68, places=2)
        self.assertAlmostEqual(data["totalInFlow"], 123456.78, places=2)
        self.assertAlmostEqual(data["outInstantFlow_1"], 30.1, places=1)
        self.assertAlmostEqual(data["outInstantFlow_4"], 30.4, places=1)
        self.assertAlmostEqual(data["instantReturnFlow"], 5.5, places=1)
        self.assertAlmostEqual(data["totalReturnFlow"], 5000.5, places=1)
        self.assertAlmostEqual(data["pumpStationInstantTotalFlow"], 120.18, places=2)
        self.assertAlmostEqual(data["pumpStationDayTotalFlow"], 2880.0, places=1)
        self.assertEqual(data["writeCounter"], 1)

    def test_all_out_total_flows_mapped(self):
        """四个出水口累计都应有正确映射"""
        data = self.src._row_to_data(_make_row(), counter=1)
        self.assertAlmostEqual(data["outTotalFlow_1"], 10000.1, places=1)
        self.assertAlmostEqual(data["outTotalFlow_2"], 10000.2, places=1)
        self.assertAlmostEqual(data["outTotalFlow_3"], 10000.3, places=1)
        self.assertAlmostEqual(data["outTotalFlow_4"], 10000.4, places=1)

    def test_v_out_total_not_mapped(self):
        """v_out_total 不应写入任何点表字段"""
        data = self.src._row_to_data(_make_row(), counter=1)
        # 点表里没有字段等于 40001.0（除了被其他值巧合命中）
        for f in P.FLOAT_FIELDS:
            self.assertNotAlmostEqual(data[f], 40001.0, places=1,
                                      msg=f"{f} 不应等于 v_out_total")

    def test_bool_alarm_to_u16(self):
        data = self.src._row_to_data(
            _make_row(flag_low_flow=True, flag_high_flow=False), counter=1)
        self.assertEqual(data["lowFlowAlarm"], 1)
        self.assertEqual(data["highFlowAlarm"], 0)

    def test_bool_alarm_both_true(self):
        data = self.src._row_to_data(
            _make_row(flag_low_flow=True, flag_high_flow=True), counter=1)
        self.assertEqual(data["lowFlowAlarm"], 1)
        self.assertEqual(data["highFlowAlarm"], 1)

    def test_write_counter_masked(self):
        data = self.src._row_to_data(_make_row(), counter=65537)
        self.assertEqual(data["writeCounter"], 1)

    def test_all_float_fields_present(self):
        data = self.src._row_to_data(_make_row(), counter=1)
        for f in P.FLOAT_FIELDS:
            self.assertIn(f, data)

    def test_all_u16_fields_present(self):
        data = self.src._row_to_data(_make_row(), counter=1)
        for f in P.U16_FIELDS:
            self.assertIn(f, data)

    def test_no_missing_float_after_mapping(self):
        """正常行映射后，不应有浮点字段是无效编码"""
        data = self.src._row_to_data(_make_row(), counter=1)
        for f in P.FLOAT_FIELDS:
            self.assertFalse(is_invalid_float(data[f]),
                             f"{f} 不应为无效编码")


class TestDatabaseSourceConsistency(unittest.TestCase):

    def setUp(self):
        self.src = _make_source()

    def test_consistency_ok(self):
        self.src._check_consistency(_make_row())
        self.assertEqual(self.src.stats["consistency_mismatch"], 0)

    def test_consistency_mismatch(self):
        row = _make_row(v_out_total=99999.0)   # 与 a+b+c+d 不符
        self.src._check_consistency(row)
        self.assertEqual(self.src.stats["consistency_mismatch"], 1)

    def test_consistency_within_tolerance(self):
        row = _make_row(v_out_total=40001.005)  # 误差 0.005 < 0.01
        self.src._check_consistency(row)
        self.assertEqual(self.src.stats["consistency_mismatch"], 0)

    def test_consistency_missing_part(self):
        """部分 v_out_x 为 None 时跳过校验"""
        row = _make_row(v_out_a=None)
        self.src._check_consistency(row)
        self.assertEqual(self.src.stats["consistency_mismatch"], 0)


class TestDatabaseSourceValidity(unittest.TestCase):

    def setUp(self):
        self.src = _make_source()

    def test_status_ok(self):
        self.assertTrue(self.src._check_status(_make_row()))

    def test_status_bad(self):
        if D.valid_calc_status is None:
            self.skipTest("未配置 valid_calc_status")
        row = _make_row(calc_status=D.valid_calc_status + 1)
        self.assertFalse(self.src._check_status(row))
        self.assertEqual(self.src.stats["bad_status"], 1)

    def test_freshness_ok(self):
        self.assertTrue(self.src._check_freshness(_make_row()))

    def test_freshness_stale(self):
        old = datetime.now(timezone.utc) - timedelta(
            seconds=D.stale_threshold_sec + 10)
        row = _make_row(calc_time=old)
        self.assertFalse(self.src._check_freshness(row))
        self.assertEqual(self.src.stats["stale"], 1)


class TestDatabaseSourceQuery(unittest.TestCase):

    def setUp(self):
        self.src = _make_source()
        self.src.pool = MagicMock()

    def _mock_cursor(self, row_dict):
        """构造 cursor.description + fetchone 返回值"""
        cols = list(row_dict.keys())
        cur = MagicMock()
        cur.fetchone.return_value = tuple(row_dict[c] for c in cols)
        cur.description = []
        for c in cols:
            m = MagicMock()
            m.name = c
            cur.description.append(m)
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        self.src.pool.connection.return_value.__enter__.return_value = conn
        return cur

    def test_query_error_returns_none(self):
        self.src.pool.connection.side_effect = Exception("connection refused")
        self.assertIsNone(self.src._fetch_row())
        self.assertEqual(self.src.stats["query_error"], 1)

    def test_empty_row_returns_none(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        self.src.pool.connection.return_value.__enter__.return_value = conn
        self.assertIsNone(self.src._fetch_row())

    def test_next_round_on_empty(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        self.src.pool.connection.return_value.__enter__.return_value = conn

        data = self.src.next_round(counter=5)
        for f in P.FLOAT_FIELDS:
            self.assertTrue(is_invalid_float(data[f]),
                            f"{f} 应为无效编码")
        self.assertEqual(data["writeCounter"], 5)
        self.assertEqual(self.src.stats["empty"], 1)

    def test_next_round_ok(self):
        row = _make_row()
        self._mock_cursor(row)
        data = self.src.next_round(counter=7)
        self.assertAlmostEqual(data["instantInFlow"], 125.68, places=2)
        self.assertAlmostEqual(data["outTotalFlow_2"], 10000.2, places=1)
        self.assertEqual(data["writeCounter"], 7)
        self.assertEqual(self.src.stats["ok"], 1)

    def test_next_round_bad_status(self):
        if D.valid_calc_status is None:
            self.skipTest("未配置 valid_calc_status")
        row = _make_row(calc_status=99)
        self._mock_cursor(row)
        data = self.src.next_round(counter=6)
        for f in P.FLOAT_FIELDS:
            self.assertTrue(is_invalid_float(data[f]),
                            f"{f} 应为无效编码")
        self.assertEqual(self.src.stats["bad_status"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)