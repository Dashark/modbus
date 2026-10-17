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
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import settings
from core.codec import is_invalid_float
from slave.db_source import DatabaseSource

P = settings.protocol
D = settings.database


def _make_row(**overrides):
    """构造一行典型 SQL 结果"""
    row = {
        "calc_time": datetime.now(timezone.utc),
        "calc_status": D.valid_calc_status,
        "q_in_raw": 125.68,
        "v_in_total": 123456.78,
        "outlet_a": 30.1,
        "outlet_b": 30.2,
        "outlet_c": 30.3,
        "outlet_d": 30.4,
        "v_out_total": 10000.1,
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


class TestDatabaseSourceMapping(unittest.TestCase):

    def setUp(self):
        self.src = DatabaseSource.__new__(DatabaseSource)  # 不走 __init__
        self.src.dsn = ""
        self.src.pool = None
        self.src.stats = {
            "ok": 0, "query_error": 0, "empty": 0,
            "stale": 0, "bad_status": 0, "last_calc_time": None,
        }

    def test_basic_mapping(self):
        data = self.src._row_to_data(_make_row(), counter=1)
        self.assertAlmostEqual(data["instantInFlow"], 125.68, places=2)
        self.assertAlmostEqual(data["totalInFlow"], 123456.78, places=2)
        self.assertAlmostEqual(data["outInstantFlow_1"], 30.1, places=1)
        self.assertAlmostEqual(data["outInstantFlow_4"], 30.4, places=1)
        self.assertAlmostEqual(data["outTotalFlow_1"], 10000.1, places=1)
        self.assertAlmostEqual(data["instantReturnFlow"], 5.5, places=1)
        self.assertAlmostEqual(data["totalReturnFlow"], 5000.5, places=1)
        self.assertAlmostEqual(data["pumpStationInstantTotalFlow"], 120.18, places=2)
        self.assertEqual(data["writeCounter"], 1)

    def test_missing_out_total_flow_2_3_4(self):
        """SQL 未提供 outTotalFlow_2/3/4，按 default_for_missing 处理"""
        data = self.src._row_to_data(_make_row(), counter=1)
        for f in ("outTotalFlow_2", "outTotalFlow_3", "outTotalFlow_4"):
            if D.default_for_missing == "invalid":
                self.assertTrue(is_invalid_float(data[f]),
                                f"{f} 应为无效编码")
            else:
                self.assertEqual(data[f], float(D.default_for_missing))

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


class TestDatabaseSourceValidity(unittest.TestCase):

    def setUp(self):
        self.src = DatabaseSource.__new__(DatabaseSource)
        self.src.dsn = ""
        self.src.pool = None
        self.src.stats = {
            "ok": 0, "query_error": 0, "empty": 0,
            "stale": 0, "bad_status": 0, "last_calc_time": None,
        }

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
        self.src = DatabaseSource.__new__(DatabaseSource)
        self.src.dsn = ""
        self.src.pool = MagicMock()
        self.src.stats = {
            "ok": 0, "query_error": 0, "empty": 0,
            "stale": 0, "bad_status": 0, "last_calc_time": None,
        }

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
        self.assertEqual(self.src.stats["query_error"], 0)

    def test_next_round_on_empty(self):
        """无数据时返回全无效编码"""
        self.src.pool = MagicMock()
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

    def test_next_round_bad_status(self):
        """calc_status 异常 -> 全无效"""
        if D.valid_calc_status is None:
            self.skipTest("未配置 valid_calc_status")
        row = _make_row(calc_status=99)
        cols = list(row.keys())
        cur = MagicMock()
        cur.fetchone.return_value = tuple(row[c] for c in cols)
        cur.description = [MagicMock(name=c) for c in cols]
        for m, c in zip(cur.description, cols):
            m.name = c
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        self.src.pool.connection.return_value.__enter__.return_value = conn

        data = self.src.next_round(counter=6)
        for f in P.FLOAT_FIELDS:
            self.assertTrue(is_invalid_float(data[f]),
                            f"{f} 应为无效编码")
        self.assertEqual(self.src.stats["bad_status"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)