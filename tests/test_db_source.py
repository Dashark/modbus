import os
import sys
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import settings
from core.codec import is_invalid_float
from slave.db_source import DatabaseSource

P = settings.protocol
D = settings.database
TZ = ZoneInfo(getattr(D, "calc_timezone", "Asia/Shanghai"))


def _make_row(**overrides):
    row = {
        "calc_time": datetime.now(TZ),
        "calc_status": "OK",
        "q_in_raw": 125.6849,
        "v_in_total": 123456.789,
        "outlet_a": 30.123,
        "outlet_b": 30.456,
        "outlet_c": 30.789,
        "outlet_d": 30.999,
        "v_out_a": 10000.111,
        "v_out_b": 10000.222,
        "v_out_c": 10000.333,
        "v_out_d": 10000.444,
        "v_out_total": 40001.110,
        "q_return": 5.555,
        "v_return_total": 5000.555,
        "q_total_out": 120.185,
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
    src.tz = TZ
    src.decimal_places = getattr(D, "decimal_places", 2)
    src.valid_statuses = src._normalize_valid_statuses()
    src.stats = {
        "ok": 0, "query_error": 0, "empty": 0, "stale": 0,
        "bad_status": 0, "consistency_mismatch": 0,
        "last_calc_time": None, "last_calc_status": None,
    }
    src._diag_cols = set(getattr(D, "diagnostic_columns", []) or [])
    return src


class TestDecimalRounding(unittest.TestCase):
    def setUp(self):
        self.src = _make_source()

    def test_round_to_2(self):
        data = self.src._row_to_data(_make_row(), counter=1)
        self.assertEqual(data["instantInFlow"], 125.68)
        self.assertEqual(data["totalInFlow"], 123456.79)
        self.assertEqual(data["outInstantFlow_1"], 30.12)
        self.assertEqual(data["outTotalFlow_1"], 10000.11)
        self.assertEqual(data["pumpStationInstantTotalFlow"], 120.19)  # 银行家舍入
        # 无 None 时不应出现无效编码
        for f in P.FLOAT_FIELDS:
            self.assertFalse(is_invalid_float(data[f]), f"{f} 不应无效")

    def test_round_bankers_example(self):
        # Python round 是银行家舍入：2.5->2, 3.5->4
        data = self.src._row_to_data(_make_row(q_in_raw=2.5), counter=1)
        self.assertEqual(data["instantInFlow"], 2.0)
        data = self.src._row_to_data(_make_row(q_in_raw=3.5), counter=1)
        self.assertEqual(data["instantInFlow"], 4.0)

    def test_none_keeps_invalid(self):
        data = self.src._row_to_data(_make_row(q_in_raw=None), counter=1)
        self.assertTrue(is_invalid_float(data["instantInFlow"]))


class TestCalcStatusEnum(unittest.TestCase):
    def setUp(self):
        self.src = _make_source()

    def test_ok_valid(self):
        self.assertTrue(self.src._check_status(_make_row(calc_status="OK")))

    def test_degraded_valid(self):
        self.assertTrue(self.src._check_status(_make_row(calc_status="DEGRADED")))

    def test_stopped_invalid(self):
        self.assertFalse(self.src._check_status(_make_row(calc_status="STOPPED")))
        self.assertEqual(self.src.stats["bad_status"], 1)

    def test_error_invalid(self):
        self.assertFalse(self.src._check_status(_make_row(calc_status="ERROR")))
        self.assertEqual(self.src.stats["bad_status"], 1)

    def test_case_insensitive(self):
        self.assertTrue(self.src._check_status(_make_row(calc_status="ok")))
        self.assertFalse(self.src._check_status(_make_row(calc_status="error")))

    def test_unknown_invalid(self):
        self.assertFalse(self.src._check_status(_make_row(calc_status="UNKNOWN")))

    def test_stats_last_status(self):
        self.src._check_status(_make_row(calc_status="DEGRADED"))
        self.assertEqual(self.src.stats["last_calc_status"], "DEGRADED")


class TestCalcTimeTimezone(unittest.TestCase):
    def setUp(self):
        self.src = _make_source()

    def test_naive_treated_as_local(self):
        naive = datetime.now(TZ).replace(tzinfo=None)
        local = self.src._to_local(naive)
        self.assertIsNotNone(local)
        self.assertEqual(local.tzinfo, TZ)

    def test_aware_converted_to_local(self):
        from datetime import timezone as _tz
        utc = datetime.now(_tz.utc)
        local = self.src._to_local(utc)
        self.assertEqual(local.tzinfo, TZ)
        # 时差应为 8 小时（上海 UTC+8）
        delta = (local - utc).total_seconds()
        self.assertAlmostEqual(delta, 0, places=0)  # 同一时刻

    def test_fresh_local(self):
        row = _make_row(calc_time=datetime.now(TZ))
        self.assertTrue(self.src._check_freshness(row))

    def test_stale_local(self):
        old = datetime.now(TZ) - timedelta(seconds=D.stale_threshold_sec + 10)
        row = _make_row(calc_time=old)
        self.assertFalse(self.src._check_freshness(row))
        self.assertEqual(self.src.stats["stale"], 1)

    def test_last_calc_time_stored_local(self):
        row = _make_row(calc_time=datetime.now(TZ))
        self.src._check_freshness(row)
        self.assertEqual(self.src.stats["last_calc_time"].tzinfo, TZ)


if __name__ == "__main__":
    unittest.main(verbosity=2)