"""
数据生成器：随机模式 + 覆盖模式。
所有参数来自 config/slave.yaml。
"""
import random
from typing import Dict, Any, Optional

from config.settings import settings
from core.logger import get_logger

P = settings.protocol
S = settings.slave
log = get_logger("slave.generator")

INVALID_FLOAT = P.INVALID_FLOAT


class BaseGenerator:
    """公共基准值管理与漂移逻辑"""

    def __init__(self, base_values: Optional[Dict[str, float]] = None):
        self.base = dict(base_values or S.BASE_VALUES)

    def _drift(self, key: str, amp: float) -> float:
        self.base[key] += random.uniform(-amp, amp)
        if self.base[key] < 0:
            self.base[key] = 0.0
        return self.base[key]

    def _accumulate(self, key: str, inc_max: float) -> float:
        self.base[key] += random.uniform(0, inc_max)
        return self.base[key]

    def _build_normal(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        r = S.RANDOM
        for k in P.FLOAT_FIELDS:
            if k.startswith("total") or k.startswith("outTotal") \
                    or k.startswith("pumpStation"):
                data[k] = self._accumulate(k, r["total_increment_max"])
            else:
                data[k] = self._drift(k, amp=r["drift_amp"])
        data["lowFlowAlarm"] = 0
        data["highFlowAlarm"] = 0
        return data


class DataGenerator(BaseGenerator):
    """随机模式：每个测点独立按概率注入 NaN / 告警"""

    def __init__(self, invalid_prob=None, alarm_prob=None,
                 base_values=None, seed=None):
        super().__init__(base_values)
        r = S.RANDOM
        self.invalid_prob = invalid_prob if invalid_prob is not None else r["invalid_prob"]
        self.alarm_prob = alarm_prob if alarm_prob is not None else r["alarm_prob"]
        if seed is not None:
            random.seed(seed)

    def next_round(self, counter: int) -> Dict[str, Any]:
        data = self._build_normal()
        for k in P.FLOAT_FIELDS:
            if random.random() < self.invalid_prob:
                data[k] = INVALID_FLOAT
                log.warning("测点 %s 本轮生成无效编码 (NaN)", k)
        data["lowFlowAlarm"] = 1 if random.random() < self.alarm_prob else 0
        data["highFlowAlarm"] = 1 if random.random() < self.alarm_prob else 0
        data["writeCounter"] = counter & 0xFFFF
        return data


class CoverageGenerator(BaseGenerator):
    """
    覆盖模式：按 config 中的 coverage_sequence 轮转注入故障，
    保证所有测点与告警组合都被覆盖。
    """

    def __init__(self, sequence=None, base_values=None):
        super().__init__(base_values)
        self.sequence = sequence or S.COVERAGE_SEQUENCE
        self.idx = 0

    def next_round(self, counter: int) -> Dict[str, Any]:
        data = self._build_normal()
        item = self.sequence[self.idx]
        self.idx = (self.idx + 1) % len(self.sequence)
        kind = item.get("kind")

        if kind == "single_nan":
            target = item["target"]
            data[target] = INVALID_FLOAT
            log.warning("[覆盖] 单点无效: %s", target)
        elif kind == "multi_nan":
            targets = item["targets"]
            for t in targets:
                data[t] = INVALID_FLOAT
            log.warning("[覆盖] 多点无效: %s", ", ".join(targets))
        elif kind == "all_nan":
            for k in P.FLOAT_FIELDS:
                data[k] = INVALID_FLOAT
            log.warning("[覆盖] 全部浮点无效")
        elif kind == "alarm_low":
            data["lowFlowAlarm"] = 1
            log.warning("[覆盖] 低流量告警 = 1")
        elif kind == "alarm_high":
            data["highFlowAlarm"] = 1
            log.warning("[覆盖] 高流量告警 = 1")
        elif kind == "alarm_both":
            data["lowFlowAlarm"] = 1
            data["highFlowAlarm"] = 1
            log.warning("[覆盖] 双告警 = 1")
        elif kind == "normal":
            log.info("[覆盖] 本轮全部正常")
        else:
            log.error("[覆盖] 未知故障类型: %s", kind)

        data["writeCounter"] = counter & 0xFFFF
        return data


def make_generator(mode: str = None, seed: Optional[int] = None):
    """
    工厂方法：
      - mode="coverage" -> CoverageGenerator
      - mode="random"   -> DataGenerator
      - mode=None       -> 按 config/slave.yaml 的 coverage_mode 决定
    """
    if mode is None:
        mode = "coverage" if S.COVERAGE_MODE else "random"
    if mode == "coverage":
        return CoverageGenerator()
    return DataGenerator(seed=seed)