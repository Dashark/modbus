"""
容器健康检查：尝试连接从站并读取 1 个寄存器。
"""
import os
import sys
from pymodbus.client import ModbusTcpClient

host = os.getenv("HEALTHCHECK_HOST", "127.0.0.1")
port = int(os.getenv("MODBUS_PORT", "502"))
unit = int(os.getenv("MODBUS_UNIT", "1"))

client = ModbusTcpClient(host, port=port, timeout=2)
try:
    if not client.connect():
        print("healthcheck: connect failed", file=sys.stderr)
        sys.exit(1)
    rr = client.read_holding_registers(address=1000, count=1, slave=unit)
    if rr.isError():
        print(f"healthcheck: read error {rr}", file=sys.stderr)
        sys.exit(1)
    print("healthcheck: ok")
    sys.exit(0)
finally:
    client.close()