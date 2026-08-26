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
CREATE TABLE IF NOT EXISTS forecasts (
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    provider VARCHAR NOT NULL,
    signal_json VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    token_cost BIGINT NOT NULL DEFAULT 0
);
CREATE SEQUENCE IF NOT EXISTS positions_seq START 1;
CREATE TABLE IF NOT EXISTS positions (
    id BIGINT PRIMARY KEY DEFAULT nextval('positions_seq'),
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    direction VARCHAR NOT NULL,
    entry DOUBLE NOT NULL,
    tp DOUBLE NOT NULL,
    sl DOUBLE NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    exit_price DOUBLE,
    pnl DOUBLE,
    status VARCHAR NOT NULL DEFAULT 'open',
    model VARCHAR,
    source_signal_id BIGINT
);
CREATE SEQUENCE IF NOT EXISTS alerts_seq START 1;
CREATE TABLE IF NOT EXISTS alerts (
    id BIGINT PRIMARY KEY DEFAULT nextval('alerts_seq'),
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    direction VARCHAR NOT NULL,
    entry DOUBLE,
    tp VARCHAR,
    sl DOUBLE,
    model VARCHAR,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    channel VARCHAR NOT NULL,
    status VARCHAR NOT NULL
);
CREATE SEQUENCE IF NOT EXISTS outcomes_seq START 1;
CREATE TABLE IF NOT EXISTS signal_outcomes (
    id BIGINT PRIMARY KEY DEFAULT nextval('outcomes_seq'),
    signal_id BIGINT,
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    model VARCHAR,
    direction VARCHAR NOT NULL,
    entry DOUBLE,
    tp DOUBLE,
    sl DOUBLE,
    outcome VARCHAR NOT NULL,
    user_override BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source VARCHAR NOT NULL DEFAULT 'auto'
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

    def save_forecast(self, symbol: str, timeframe: str, provider: str, signal: dict) -> None:
        """Persist a forecast signal snapshot (JSON) to the forecasts table."""
        import json as _json

        cur = self.cursor()
        try:
            cur.execute(
                "INSERT INTO forecasts (symbol, timeframe, provider, signal_json, status, token_cost) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    symbol,
                    timeframe,
                    provider,
                    _json.dumps(signal, default=str),
                    signal.get("status", "ok"),
                    int(signal.get("token_cost", 0)),
                ],
            )
        finally:
            cur.close()

    def get_forecasts(self, symbol: str | None = None, timeframe: str | None = None, limit: int = 100) -> list[dict]:
        """Latest forecasts, newest first, optional filters."""
        import json as _json

        sql = "SELECT symbol, timeframe, provider, signal_json, status, created_at, token_cost FROM forecasts"
        params: list = []
        conds = []
        if symbol:
            conds.append("symbol = ?")
            params.append(symbol)
        if timeframe:
            conds.append("timeframe = ?")
            params.append(timeframe)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = self.cursor()
        try:
            rows = cur.execute(sql, params).fetchall()
            return [
                {
                    "symbol": r[0],
                    "timeframe": r[1],
                    "provider": r[2],
                    "signal": _json.loads(r[3]),
                    "status": r[4],
                    "created_at": _ensure_utc(r[5]).isoformat() if r[5] else None,
                    "token_cost": r[6],
                }
                for r in rows
            ]
        finally:
            cur.close()

    # ---- Paper trading (SP4) ----

    def create_position(self, pos: dict) -> int:
        """Insert position, return id."""
        cur = self.cursor()
        try:
            cur.execute(
                "INSERT INTO positions (symbol, timeframe, direction, entry, tp, sl, model, source_signal_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                [
                    pos["symbol"],
                    pos["timeframe"],
                    pos["direction"],
                    pos["entry"],
                    pos["tp"],
                    pos["sl"],
                    pos.get("model"),
                    pos.get("source_signal_id"),
                ],
            )
            return int(cur.fetchone()[0])
        finally:
            cur.close()

    def get_positions(self, status: str | None = None) -> list[dict]:
        sql = ("SELECT id, symbol, timeframe, direction, entry, tp, sl, opened_at, closed_at, "
               "exit_price, pnl, status, model, source_signal_id FROM positions")
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY opened_at DESC"
        cur = self.cursor()
        try:
            rows = cur.execute(sql, params).fetchall()
            return [
                {
                    "id": r[0], "symbol": r[1], "timeframe": r[2], "direction": r[3],
                    "entry": r[4], "tp": r[5], "sl": r[6],
                    "opened_at": _ensure_utc(r[7]).isoformat() if r[7] else None,
                    "closed_at": _ensure_utc(r[8]).isoformat() if r[8] else None,
                    "exit_price": r[9], "pnl": r[10], "status": r[11],
                    "model": r[12], "source_signal_id": r[13],
                }
                for r in rows
            ]
        finally:
            cur.close()

    def close_position(self, pos_id: int, exit_price: float, pnl: float) -> None:
        cur = self.cursor()
        try:
            cur.execute(
                "UPDATE positions SET status='closed', closed_at=now(), exit_price=?, pnl=? WHERE id=?",
                [exit_price, pnl, pos_id],
            )
        finally:
            cur.close()

    def update_position_pnl(self, pos_id: int, pnl: float) -> None:
        cur = self.cursor()
        try:
            cur.execute("UPDATE positions SET pnl=? WHERE id=?", [pnl, pos_id])
        finally:
            cur.close()

    # ---- Alerts (SP4) ----

    def save_alert(self, alert: dict) -> int:
        cur = self.cursor()
        try:
            cur.execute(
                "INSERT INTO alerts (symbol, timeframe, direction, entry, tp, sl, model, channel, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                [
                    alert["symbol"],
                    alert["timeframe"],
                    alert["direction"],
                    alert.get("entry"),
                    alert.get("tp"),
                    alert.get("sl"),
                    alert.get("model"),
                    alert["channel"],
                    alert["status"],
                ],
            )
            return int(cur.fetchone()[0])
        finally:
            cur.close()

    def get_alerts(self, limit: int = 100) -> list[dict]:
        cur = self.cursor()
        try:
            rows = cur.execute(
                "SELECT id, symbol, timeframe, direction, entry, tp, sl, model, sent_at, channel, status "
                "FROM alerts ORDER BY sent_at DESC LIMIT ?",
                [limit],
            ).fetchall()
            return [
                {
                    "id": r[0], "symbol": r[1], "timeframe": r[2], "direction": r[3],
                    "entry": r[4], "tp": r[5], "sl": r[6], "model": r[7],
                    "sent_at": _ensure_utc(r[8]).isoformat() if r[8] else None,
                    "channel": r[9], "status": r[10],
                }
                for r in rows
            ]
        finally:
            cur.close()


def _ensure_utc(dt: datetime) -> datetime:
    """Naive datetimes are interpreted as UTC by convention (host may be UTC+7)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
