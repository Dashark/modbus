import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pymodbus.exceptions import ModbusIOException, ConnectionException
from pymodbus.pdu import ExceptionResponse

from config.settings import settings
from master.client import PumpMaster

P = settings.protocol


def _valid_data(counter=1):
    d = {k: 1.0 for k in P.OFFSET}
    d["lowFlowAlarm"] = 0
    d["highFlowAlarm"] = 0
    d["writeCounter"] = counter
    return d


class TestMasterFaults(unittest.TestCase):

    def _make_master(self):
        m = PumpMaster("127.0.0.1", 502)
        m.client = MagicMock()
        m.client.connected = True
        return m

    def test_timeout(self):
        m = self._make_master()
        m.client.read_holding_registers.side_effect = ConnectionException("timeout")
        self.assertIsNone(m.read_all())
        self.assertEqual(m.stats["timeout"], 1)

    def test_modbus_io_exception(self):
        m = self._make_master()
        m.client.read_holding_registers.side_effect = ModbusIOException("io")
        self.assertIsNone(m.read_all())
        self.assertEqual(m.stats["timeout"], 1)

    def test_exception_response_0x02(self):
        m = self._make_master()
        real = ExceptionResponse(function_code=3, exception_code=0x02)
        m.client.read_holding_registers.return_value = real
        self.assertIsNone(m.read_all())
        self.assertEqual(m.stats["exception"], 1)

    def test_exception_response_all_codes(self):
        for code in (0x01, 0x02, 0x03, 0x04):
            m = self._make_master()
            m.client.read_holding_registers.return_value = \
                ExceptionResponse(function_code=3, exception_code=code)
            self.assertIsNone(m.read_all())
            self.assertEqual(m.stats["exception"], 1, f"code=0x{code:02X}")

    def test_wrong_register_count(self):
        m = self._make_master()
        rr = MagicMock()
        rr.isError.return_value = False
        rr.registers = [0] * (P.READ_COUNT - 1)
        m.client.read_holding_registers.return_value = rr
        self.assertIsNone(m.read_all())
        self.assertEqual(m.stats["exception"], 1)

    def test_stale_counter(self):
        m = self._make_master()
        m.check_validity(_valid_data(100))
        m.check_validity(_valid_data(100))
        self.assertEqual(m.stats["stale"], 1)
        self.assertEqual(m.stale_count, 1)

    def test_counter_reset_clears_stale(self):
        m = self._make_master()
        m.check_validity(_valid_data(100))
        m.check_validity(_valid_data(100))
        m.check_validity(_valid_data(101))
        self.assertEqual(m.stale_count, 0)
        self.assertEqual(m.stats["stale"], 1)

    def test_reconnect_on_disconnect(self):
        m = self._make_master()
        m.client.connected = False
        with unittest.mock.patch.object(m, "connect", return_value=True) as mock_conn:
            m.ensure_connected()
            mock_conn.assert_called_once()

    def test_invalid_float_detected(self):
        m = self._make_master()
        data = _valid_data(1)
        data["instantInFlow"] = float("nan")
        ok = m.check_validity(data)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)