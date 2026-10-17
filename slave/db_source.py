"""
数据库数据源：从 PostgreSQL / TimescaleDB 读取 flow_calc_latest 最新一行，
映射为点表字典。
"""
from datetime import datetime, timezone
from typing import Dict, Any, Optional

try:
    import psycopg
    from psycopg_pool import ConnectionPool
except ImportError:
    psycopg = None
    ConnectionPool = None

from config.settings import settings
from core.logger import get_logger
from .source import DataSource

P = settings.protocol
D = settings.database
log = get_logger("slave.db_source")

INVALID_FLOAT = P.INVALID_FLOAT


class DatabaseSource(DataSource):
    """
    从数据库读取最新流量计算结果。
    - 连接池复用连接
    - 查询失败/超时/数据过期/calc_status 异常 -> 返回全无效编码
    - v_out_total 一致性校验（仅告警，不阻断写入）
    """

    def __init__(self, dsn: Optional[str] = None):
        if psycopg is None or ConnectionPool is None:
            raise RuntimeError("需要 psycopg: pip install 'psycopg[binary,pool]'")

        self.dsn = dsn or self._build_dsn()
        self.pool: Optional[ConnectionPool] = None
        self.stats = {
            "ok": 0,
            "query_error": 0,
            "empty": 0,
            "stale": 0,
            "bad_status": 0,
            "consistency_mismatch": 0,
            "last_calc_time": None,
        }
        # 诊断列集合（不参与寄存器映射）
        self._diag_cols = set(getattr(D, "diagnostic_columns", []) or [])

    # ---------- DSN ----------
    def _build_dsn(self) -> str:
        return (
            f"host={D.host} port={D.port} dbname={D.dbname} "
            f"user={D.user} password={D.password} "
            f"connect_timeout={D.connect_timeout}"
        )

    # ---------- 连接池 ----------
    def open(self):
        if self.pool is not None:
            return
        self.pool = ConnectionPool(
            conninfo=self.dsn,
            min_size=D.pool_min,
            max_size=D.pool_max,
            open=True,
            timeout=D.connect_timeout,
        )
        log.info("数据库连接池已建立: %s:%s/%s", D.host, D.port, D.dbname)

    def close(self):
        if self.pool is not None:
            self.pool.close()
            self.pool = None
            log.info("数据库连接池已关闭")

    # ---------- 查询 ----------
    def _fetch_row(self) -> Optional[Dict[str, Any]]:
        """执行参数化查询，返回列名字典"""
        assert self.pool is not None
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET statement_timeout = %s",
                                (int(D.query_timeout * 1000),))
                    cur.execute(D.query, (D.pump_room_id,))
                    row = cur.fetchone()
                    if row is None:
                        return None
                    cols = [d.name for d in cur.description]
                    return dict(zip(cols, row))
        except Exception as e:  # noqa
            self.stats["query_error"] += 1
            log.error("数据库查询失败: %s", e)
            return None

    # ---------- 数据映射 ----------
    def _row_to_data(self, row: Dict[str, Any], counter: int) -> Dict[str, Any]:
        """SQL 行 -> 点表字典"""
        data: Dict[str, Any] = {}

        # 1) 按 column_mapping 填充
        for col, field in D.column_mapping.items():
            if col not in row:
                continue
            val = row[col]
            if field in P.U16_FIELDS:
                if D.bool_to_u16 and isinstance(val, bool):
                    val = 1 if val else 0
                data[field] = int(val) if val is not None else 0
            else:
                data[field] = float(val) if val is not None else INVALID_FLOAT

        # 2) 未映射浮点字段兜底（正常路径不会触发）
        for field in P.FLOAT_FIELDS:
            if field not in data:
                if D.default_for_missing == "invalid":
                    data[field] = INVALID_FLOAT
                else:
                    data[field] = float(D.default_for_missing)

        # 3) 未映射 U16 字段（除 writeCounter）填 0
        for field in P.U16_FIELDS:
            if field == "writeCounter":
                continue
            data.setdefault(field, 0)

        # 4) writeCounter
        data["writeCounter"] = counter & 0xFFFF
        return data

    # ---------- 一致性校验 ----------
    def _check_consistency(self, row: Dict[str, Any]):
        """
        校验 v_out_total ≈ v_out_a + v_out_b + v_out_c + v_out_d。
        仅告警，不影响数据写入。
        """
        cfg = getattr(D, "consistency_check", None) or {}
        if not cfg.get("enabled", False):
            return
        try:
            total = row.get("v_out_total")
            parts = [row.get(k) for k in ("v_out_a", "v_out_b", "v_out_c", "v_out_d")]
            if total is None or any(p is None for p in parts):
                return
            s = sum(float(p) for p in parts)
            diff = abs(float(total) - s)
            tol = float(cfg.get("tolerance", 0.01))
            if diff > tol:
                self.stats["consistency_mismatch"] += 1
                log.warning(
                    "v_out_total 一致性异常: total=%.4f sum(a+b+c+d)=%.4f diff=%.4f > tol=%.4f",
                    float(total), s, diff, tol,
                )
        except Exception as e:  # noqa
            log.error("一致性校验异常: %s", e)

    # ---------- 诊断日志 ----------
    def _log_diagnostics(self, row: Dict[str, Any]):
        if not self._diag_cols:
            return
        diag = {k: row.get(k) for k in self._diag_cols if k in row}
        if diag:
            log.info("诊断列: %s", diag)

    # ---------- 有效性 ----------
    def _check_status(self, row: Dict[str, Any]) -> bool:
        if D.valid_calc_status is None:
            return True
        status = row.get("calc_status")
        if status is None:
            return True
        ok = (status == D.valid_calc_status)
        if not ok:
            self.stats["bad_status"] += 1
            log.warning("calc_status=%s 不等于 %s，数据视为无效",
                        status, D.valid_calc_status)
        return ok

    def _check_freshness(self, row: Dict[str, Any]) -> bool:
        ct = row.get("calc_time")
        if ct is None:
            return True
        self.stats["last_calc_time"] = ct
        if isinstance(ct, datetime):
            now = datetime.now(timezone.utc)
            if ct.tzinfo is None:
                ct = ct.replace(tzinfo=timezone.utc)
            age = (now - ct).total_seconds()
            if age > D.stale_threshold_sec:
                self.stats["stale"] += 1
                log.warning("calc_time 过期: age=%.1fs > %ds",
                            age, D.stale_threshold_sec)
                return False
        return True

    # ---------- 主入口 ----------
    def next_round(self, counter: int) -> Dict[str, Any]:
        if self.pool is None:
            self.open()

        row = self._fetch_row()
        if row is None:
            self.stats["empty"] += 1
            log.warning("数据库无 pump_room_id=%s 的数据，写无效编码",
                        D.pump_room_id)
            return self._row_to_data({}, counter)

        self._log_diagnostics(row)
        self._check_consistency(row)

        if not self._check_status(row) or not self._check_freshness(row):
            return self._row_to_data({}, counter)

        self.stats["ok"] += 1
        return self._row_to_data(row, counter)