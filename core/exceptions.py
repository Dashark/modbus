EXCEPTION_DESC = {
    0x01: "Illegal Function（非法功能码）",
    0x02: "Illegal Data Address（非法数据地址）",
    0x03: "Illegal Data Value（非法数据值）",
    0x04: "Slave Device Failure（从站设备故障）",
    0x05: "Acknowledge（确认，正在处理）",
    0x06: "Slave Device Busy（从站忙）",
    0x08: "Memory Parity Error（存储器奇偶校验错）",
    0x0A: "Gateway Path Unavailable（网关路径不可用）",
    0x0B: "Gateway Target Device Failed to Respond（网关目标设备无响应）",
}


def describe_exception(code: int) -> str:
    return EXCEPTION_DESC.get(code, f"未知异常码 0x{code:02X}")