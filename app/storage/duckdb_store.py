import json
import logging
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS klines (
    open_time TIMESTAMPTZ NOT NULL,
    close_time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    volume DOUBLE NOT NULL,
    close_volume DOUBLE NOT NULL,
    trades BIGINT NOT NULL,
    taker_buy_base DOUBLE NOT NULL,
    PRIMARY KEY (symbol, timeframe, open_time)
);
CREATE TABLE IF NOT EXISTS backfill_progress (
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    cursor TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (symbol, timeframe)
);
"""

REQUIRED_FIELDS = (
    "open_time",
    "close_time",
    "symbol",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_volume",
    "trades",
    "taker_buy_base",
)


def validate_kline(k: dict) -> str | None:
    """Return reject reason string if invalid, None if valid."""
    for f in REQUIRED_FIELDS:
        if k.get(f) is None:
            return f"missing field {f}"
        v = k[f]
        if isinstance(v, float) and math.isnan(v):
            return f"NaN in {f}"
    for f in ("open", "high", "low", "close"):
        if k[f] < 0:
            return f"negative price in {f}"
    if k["high"] < k["low"]:
        return "high < low"
    if not (k["low"] <= k["close"] <= k["high"]):
        return f"close {k['close']} outside [low, high]"
    if not (k["low"] <= k["open"] <= k["high"]):
        return f"open {k['open']} outside [low, high]"
    if k["volume"] < 0 or k["close_volume"] < 0:
        return "negative volume"
    if k["trades"] < 0:
        return "negative trades"
    if k["close_time"] <= k["open_time"]:
        return "close_time <= open_time"
    return None


class DuckDBStore:
    def __init__(self, conn: duckdb.DuckDBPyConnection, reject_log_path: str | None = None):
        self._conn = conn
        conn.execute("SET TimeZone='UTC'")
        conn.execute(SCHEMA_SQL)
        self.reject_log: list[dict] = []
        self._reject_log_path = reject_log_path

    def cursor(self) -> duckdb.DuckDBPyConnection:
        cur = self._conn.cursor()
        cur.execute("SET TimeZone='UTC'")
        return cur

    def upsert_klines(self, batch: list[dict]) -> int:
        """Validate → dedupe by PK → insert; returns inserted count.

        Invalid rows go to reject log and are never inserted.
        """
        valid: list[dict] = []
        seen: set[tuple] = set()
        for k in batch:
            reason = validate_kline(k)
            if reason is not None:
                self._log_reject(k, reason)
                continue
            ot = _ensure_utc(k["open_time"])
            key = (k["symbol"], k["timeframe"], ot)
            if key in seen:
                continue
            seen.add(key)
            row = dict(k)
            row["open_time"] = ot
            row["close_time"] = _ensure_utc(k["close_time"])
            valid.append(row)

        if not valid:
            return 0

        cur = self.cursor()
        try:
            inserted = 0
            CHUNK = 1000
            for i in range(0, len(valid), CHUNK):
                chunk = valid[i : i + CHUNK]
                placeholders = ", ".join(["?"] * 12)
                values_sql = ", ".join([f"({placeholders})"] * len(chunk))
                params: list = []
                for row in chunk:
                    params.extend(
                        [
                            row["open_time"],
                            row["close_time"],
                            row["symbol"],
                            row["timeframe"],
                            row["open"],
                            row["high"],
                            row["low"],
                            row["close"],
                            row["volume"],
                            row["close_volume"],
                            row["trades"],
                            row["taker_buy_base"],
                        ]
                    )
                cur.execute(
                    f"INSERT INTO klines VALUES {values_sql} ON CONFLICT DO UPDATE SET "
                    "close_time = excluded.close_time, open = excluded.open, "
                    "high = excluded.high, low = excluded.low, close = excluded.close, "
                    "volume = excluded.volume, close_volume = excluded.close_volume, "
                    "trades = excluded.trades, taker_buy_base = excluded.taker_buy_base",
                    params,
                )
                inserted += len(chunk)
            return inserted
        finally:
            cur.close()

    def _log_reject(self, k: dict, reason: str) -> None:
        entry = {
            "symbol": k.get("symbol"),
            "timeframe": k.get("timeframe"),
            "open_time": str(k.get("open_time")),
            "reason": reason,
        }
        self.reject_log.append(entry)
        logger.warning("kline rejected: %s", entry)
        if self._reject_log_path:
            Path(self._reject_log_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self._reject_log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

    def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> list[dict]:
        sql = "SELECT * FROM klines WHERE symbol = ? AND timeframe = ?"
        params: list = [symbol, timeframe]
        if start is not None:
            sql += " AND open_time >= ?"
            params.append(start)
        if end is not None:
            sql += " AND open_time < ?"
            params.append(end)
        sql += " ORDER BY open_time LIMIT ?"
        params.append(limit)
        cur = self.cursor()
        try:
            rows = cur.execute(sql, params).fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]
        finally:
            cur.close()

    def count(self, symbol: str, timeframe: str) -> int:
        cur = self.cursor()
        try:
            return cur.execute(
                "SELECT count(*) FROM klines WHERE symbol = ? AND timeframe = ?",
                [symbol, timeframe],
            ).fetchone()[0]
        finally:
            cur.close()

    def max_open_time(self, symbol: str, timeframe: str) -> datetime | None:
        cur = self.cursor()
        try:
            row = cur.execute(
                "SELECT max(open_time) FROM klines WHERE symbol = ? AND timeframe = ?",
                [symbol, timeframe],
            ).fetchone()
            return _ensure_utc(row[0]) if row and row[0] else None
        finally:
            cur.close()

    def set_backfill_cursor(self, symbol: str, timeframe: str, cursor: datetime) -> None:
        cur = self.cursor()
        try:
            cur.execute(
                "INSERT INTO backfill_progress VALUES (?, ?, ?, now()) "
                "ON CONFLICT DO UPDATE SET cursor = excluded.cursor, "
                "updated_at = excluded.updated_at",
                [symbol, timeframe, _ensure_utc(cursor)],
            )
        finally:
            cur.close()

    def get_backfill_cursor(self, symbol: str, timeframe: str) -> datetime | None:
        cur = self.cursor()
        try:
            row = cur.execute(
                "SELECT cursor FROM backfill_progress WHERE symbol = ? AND timeframe = ?",
                [symbol, timeframe],
            ).fetchone()
            return _ensure_utc(row[0]) if row and row[0] else None
        finally:
            cur.close()


def _ensure_utc(dt: datetime) -> datetime:
    """Naive datetimes are interpreted as UTC by convention (host may be UTC+7)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
