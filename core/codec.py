"""
浮点/U16 编解码、字典 <-> 寄存器整块互转。
协议要求：低地址寄存器 = 浮点低16位，高地址寄存器 = 浮点高16位。
"""
import math
import struct
from typing import Dict, Any, List

from config.settings import settings

P = settings.protocol


def float_to_regs(value: float) -> List[int]:
    b = struct.pack(">f", value)
    high16 = (b[0] << 8) | b[1]
    low16 = (b[2] << 8) | b[3]
    return [low16, high16]


def regs_to_float(low_reg: int, high_reg: int) -> float:
    b = struct.pack(">HH", high_reg & 0xFFFF, low_reg & 0xFFFF)
    return struct.unpack(">f", b)[0]


def u16_to_reg(value: int) -> List[int]:
    return [value & 0xFFFF]


def reg_to_u16(reg: int) -> int:
    return reg & 0xFFFF


def is_valid_float(value: float) -> bool:
    return math.isfinite(value)


def is_invalid_float(value: float) -> bool:
    return not math.isfinite(value)


def dict_to_regs(data: Dict[str, Any], reg_count: int = None) -> List[int]:
    if reg_count is None:
        reg_count = P.REG_COUNT
    regs = [0] * reg_count
    for name, off in P.OFFSET.items():
        if name not in data:
            continue
        if name in P.U16_FIELDS:
            regs[off:off + 1] = u16_to_reg(int(data[name]))
        else:
            regs[off:off + 2] = float_to_regs(float(data[name]))
    return regs


def regs_to_dict(regs: List[int]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, off in P.OFFSET.items():
        if name in P.U16_FIELDS:
            out[name] = reg_to_u16(regs[off])
        else:
            out[name] = regs_to_float(regs[off], regs[off + 1])
    return out