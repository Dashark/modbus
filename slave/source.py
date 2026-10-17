"""
数据源抽象：所有数据源实现 next_round(counter) -> Dict[str, Any]。
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class DataSource(ABC):
    @abstractmethod
    def next_round(self, counter: int) -> Dict[str, Any]:
        """返回一轮完整的点表数据字典（含 writeCounter）"""
        raise NotImplementedError

    def close(self):
        """释放资源，默认无操作"""
        pass