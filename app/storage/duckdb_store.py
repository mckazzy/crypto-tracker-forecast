import asyncio
import json
import logging
import math
from contextlib import asynccontextmanager
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
CREATE SEQUENCE IF NOT EXISTS forecasts_seq START 1;
CREATE TABLE IF NOT EXISTS forecasts (
    id BIGINT PRIMARY KEY DEFAULT nextval('forecasts_seq'),
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
    source VARCHAR NOT NULL DEFAULT 'auto',
    score DOUBLE,
    exit_price DOUBLE
);
-- ---- Futures demo exchange (SP5) ----
CREATE SEQUENCE IF NOT EXISTS users_seq START 1;
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY DEFAULT nextval('users_seq'),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS futures_accounts (
    id INTEGER PRIMARY KEY DEFAULT nextval('users_seq'),
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
    balance DOUBLE NOT NULL DEFAULT 10000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reset_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE SEQUENCE IF NOT EXISTS futures_orders_seq START 1;
CREATE TABLE IF NOT EXISTS futures_orders (
    id INTEGER PRIMARY KEY DEFAULT nextval('futures_orders_seq'),
    user_id INTEGER NOT NULL REFERENCES users(id),
    symbol VARCHAR NOT NULL,
    side VARCHAR NOT NULL,
    type VARCHAR NOT NULL,
    price DOUBLE,
    qty DOUBLE NOT NULL,
    leverage INTEGER NOT NULL,
    tp DOUBLE,
    sl DOUBLE,
    status VARCHAR NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    filled_at TIMESTAMPTZ
);
CREATE SEQUENCE IF NOT EXISTS futures_positions_seq START 1;
CREATE TABLE IF NOT EXISTS futures_positions (
    id INTEGER PRIMARY KEY DEFAULT nextval('futures_positions_seq'),
    user_id INTEGER NOT NULL REFERENCES users(id),
    symbol VARCHAR NOT NULL,
    side VARCHAR NOT NULL,
    entry DOUBLE NOT NULL,
    qty DOUBLE NOT NULL,
    leverage INTEGER NOT NULL,
    margin DOUBLE NOT NULL,
    liq_price DOUBLE NOT NULL,
    tp DOUBLE,
    sl DOUBLE,
    status VARCHAR NOT NULL DEFAULT 'OPEN',
    pnl DOUBLE,
    exit_price DOUBLE,
    closed_at TIMESTAMPTZ,
    close_reason VARCHAR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_futures_orders_user_status ON futures_orders(user_id, status);
CREATE INDEX IF NOT EXISTS idx_futures_positions_user_status ON futures_positions(user_id, status);
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
        self._migrate()
        self.reject_log: list[dict] = []
        self._reject_log_path = reject_log_path
        # DuckDB là single-writer: mọi write operation đi qua lock này để tránh
        # TransactionException / Catalog Write-Write Conflict giữa các async task.
        self._write_lock = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self):
        """BEGIN/COMMIT/ROLLBACK trên connection chính, đồng bộ bằng _write_lock.

        DuckDB transaction gắn với connection: mọi mutation bên trong context
        phải execute trên chính connection được yield (truyền `cur=tx` vào store
        methods), nếu không sẽ autocommit ngoài transaction.
        """
        async with self._write_lock:
            self._conn.execute("BEGIN TRANSACTION")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except BaseException:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def _migrate(self) -> None:
        """Migration cho DB cũ: thêm cột thiếu nếu chưa có (idempotent)."""
        cur = self.cursor()
        try:
            # forecasts.id (BIGSERIAL) — tạo lại bảng nếu thiếu PK id
            cols = [r[1] for r in cur.execute("PRAGMA table_info('forecasts')").fetchall()]
            if "id" not in cols:
                cur.execute("CREATE SEQUENCE IF NOT EXISTS forecasts_seq START 1")
                cur.execute(
                    "ALTER TABLE forecasts ADD COLUMN id BIGINT DEFAULT nextval('forecasts_seq')"
                )
            # signal_outcomes.score / exit_price
            ocols = [r[1] for r in cur.execute("PRAGMA table_info('signal_outcomes')").fetchall()]
            if "score" not in ocols:
                cur.execute("ALTER TABLE signal_outcomes ADD COLUMN score DOUBLE")
            if "exit_price" not in ocols:
                cur.execute("ALTER TABLE signal_outcomes ADD COLUMN exit_price DOUBLE")
        except Exception as e:
            logger.warning("migration skipped: %s", e)
        finally:
            cur.close()

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
        """Lấy candles. Khi có start/end → window tăng dần từ start.

        Khi không có start (chỉ limit) → trả limit candles MỚI NHẤT theo thứ tự
        tăng dần (DESC + reverse) — để dashboard luôn hiển thị data gần hiện tại.
        """
        sql = "SELECT * FROM klines WHERE symbol = ? AND timeframe = ?"
        params: list = [symbol, timeframe]
        if start is not None:
            sql += " AND open_time >= ?"
            params.append(start)
        if end is not None:
            sql += " AND open_time < ?"
            params.append(end)
        if start is None:
            # latest-window: mới nhất trước, reverse sau
            sql += " ORDER BY open_time DESC LIMIT ?"
            params.append(limit)
            cur = self.cursor()
            try:
                rows = cur.execute(sql, params).fetchall()
                cols = [d[0] for d in cur.description]
                out = [dict(zip(cols, r)) for r in rows]
                out.reverse()
                return out
            finally:
                cur.close()
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

    def save_forecast(self, symbol: str, timeframe: str, provider: str, signal: dict) -> int:
        """Persist a forecast signal snapshot (JSON) to the forecasts table. Returns id."""
        import json as _json

        cur = self.cursor()
        try:
            cur.execute(
                "INSERT INTO forecasts (symbol, timeframe, provider, signal_json, status, token_cost) "
                "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
                [
                    symbol,
                    timeframe,
                    provider,
                    _json.dumps(signal, default=str),
                    signal.get("status", "ok"),
                    int(signal.get("token_cost", 0)),
                ],
            )
            return int(cur.fetchone()[0])
        finally:
            cur.close()

    def get_forecasts(self, symbol: str | None = None, timeframe: str | None = None, limit: int = 100) -> list[dict]:
        """Latest forecasts, newest first, optional filters."""
        import json as _json

        sql = "SELECT id, symbol, timeframe, provider, signal_json, status, created_at, token_cost FROM forecasts"
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
                    "id": r[0],
                    "symbol": r[1],
                    "timeframe": r[2],
                    "provider": r[3],
                    "signal": _json.loads(r[4]),
                    "status": r[5],
                    "created_at": _ensure_utc(r[6]).isoformat() if r[6] else None,
                    "token_cost": r[7],
                }
                for r in rows
            ]
        finally:
            cur.close()

    def get_forecast_by_id(self, forecast_id: int) -> dict | None:
        """Lấy 1 forecast theo id."""
        import json as _json

        cur = self.cursor()
        try:
            row = cur.execute(
                "SELECT id, symbol, timeframe, provider, signal_json, status, created_at, token_cost "
                "FROM forecasts WHERE id = ?",
                [forecast_id],
            ).fetchone()
            if row is None:
                return None
            return {
                "id": row[0], "symbol": row[1], "timeframe": row[2], "provider": row[3],
                "signal": _json.loads(row[4]), "status": row[5],
                "created_at": _ensure_utc(row[6]).isoformat() if row[6] else None,
                "token_cost": row[7],
            }
        finally:
            cur.close()

    def delete_forecast(self, forecast_id: int) -> bool:
        """Xóa 1 forecast theo id và các outcome liên quan."""
        cur = self.cursor()
        try:
            cur.execute("DELETE FROM signal_outcomes WHERE signal_id = ?", [forecast_id])
            cur.execute("DELETE FROM forecasts WHERE id = ?", [forecast_id])
            return True
        finally:
            cur.close()

    def delete_forecasts(self, ids: list[int]) -> int:
        """Xóa danh sách forecasts theo ids."""
        if not ids:
            return 0
        cur = self.cursor()
        try:
            placeholders = ", ".join(["?"] * len(ids))
            cur.execute(f"DELETE FROM signal_outcomes WHERE signal_id IN ({placeholders})", ids)
            cur.execute(f"DELETE FROM forecasts WHERE id IN ({placeholders})", ids)
            return len(ids)
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

    # ---- Feedback loop (SP4) ----

    def save_outcome(self, outcome: dict) -> int:
        cur = self.cursor()
        try:
            cur.execute(
                "INSERT INTO signal_outcomes (signal_id, symbol, timeframe, model, direction, entry, tp, sl, outcome, user_override, source, score, exit_price) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                [
                    outcome.get("signal_id"),
                    outcome["symbol"],
                    outcome["timeframe"],
                    outcome.get("model"),
                    outcome["direction"],
                    outcome.get("entry"),
                    outcome.get("tp"),
                    outcome.get("sl"),
                    outcome["outcome"],
                    outcome.get("user_override", False),
                    outcome.get("source", "auto"),
                    outcome.get("score"),
                    outcome.get("exit_price"),
                ],
            )
            return int(cur.fetchone()[0])
        finally:
            cur.close()

    def get_outcomes(self, limit: int = 500) -> list[dict]:
        cur = self.cursor()
        try:
            rows = cur.execute(
                "SELECT id, signal_id, symbol, timeframe, model, direction, entry, tp, sl, outcome, user_override, resolved_at, source, score, exit_price "
                "FROM signal_outcomes ORDER BY resolved_at DESC LIMIT ?",
                [limit],
            ).fetchall()
            return [
                {
                    "id": r[0], "signal_id": r[1], "symbol": r[2], "timeframe": r[3],
                    "model": r[4], "direction": r[5], "entry": r[6], "tp": r[7], "sl": r[8],
                    "outcome": r[9], "user_override": r[10],
                    "resolved_at": _ensure_utc(r[11]).isoformat() if r[11] else None,
                    "source": r[12], "score": r[13], "exit_price": r[14],
                }
                for r in rows
            ]
        finally:
            cur.close()

    def get_outcome_by_signal_id(self, signal_id: int) -> dict | None:
        """Lấy outcome chính xác theo signal_id (forecast_id)."""
        cur = self.cursor()
        try:
            row = cur.execute(
                "SELECT id, signal_id, symbol, timeframe, model, direction, entry, tp, sl, outcome, user_override, resolved_at, source, score, exit_price "
                "FROM signal_outcomes WHERE signal_id = ? ORDER BY resolved_at DESC LIMIT 1",
                [signal_id],
            ).fetchone()
            if row is None:
                return None
            return {
                "id": row[0], "signal_id": row[1], "symbol": row[2], "timeframe": row[3],
                "model": row[4], "direction": row[5], "entry": row[6], "tp": row[7], "sl": row[8],
                "outcome": row[9], "user_override": row[10],
                "resolved_at": _ensure_utc(row[11]).isoformat() if row[11] else None,
                "source": row[12], "score": row[13], "exit_price": row[14],
            }
        finally:
            cur.close()

    def count_outcomes(self) -> int:
        cur = self.cursor()
        try:
            return int(cur.execute("SELECT count(*) FROM signal_outcomes").fetchone()[0])
        finally:
            cur.close()

    # ---- Futures demo exchange (SP5) ----
    # Mọi query/update futures đều user-scoped: WHERE id = ? AND user_id = ?

    def create_user(self, username: str, password_hash: str) -> int:
        cur = self.cursor()
        try:
            cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?) RETURNING id",
                [username, password_hash],
            )
            uid = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO futures_accounts (user_id, balance) VALUES (?, 10000)", [uid]
            )
            return uid
        finally:
            cur.close()

    def get_user_by_username(self, username: str) -> dict | None:
        cur = self.cursor()
        try:
            row = cur.execute(
                "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
                [username],
            ).fetchone()
            if row is None:
                return None
            return {
                "id": row[0],
                "username": row[1],
                "password_hash": row[2],
                "created_at": _ensure_utc(row[3]).isoformat() if row[3] else None,
            }
        finally:
            cur.close()

    def count_users(self) -> int:
        cur = self.cursor()
        try:
            return int(cur.execute("SELECT count(*) FROM users").fetchone()[0])
        finally:
            cur.close()

    def get_account(self, user_id: int) -> dict | None:
        cur = self.cursor()
        try:
            row = cur.execute(
                "SELECT a.id, a.user_id, a.balance, a.created_at, a.reset_at, "
                "COALESCE(SUM(CASE WHEN p.status = 'OPEN' THEN p.margin ELSE 0 END), 0) "
                "FROM futures_accounts a LEFT JOIN futures_positions p ON p.user_id = a.user_id "
                "WHERE a.user_id = ? GROUP BY a.id, a.user_id, a.balance, a.created_at, a.reset_at",
                [user_id],
            ).fetchone()
            if row is None:
                return None
            return {
                "id": row[0],
                "user_id": row[1],
                "balance": row[2],
                "margin_used": row[5],
                "created_at": _ensure_utc(row[3]).isoformat() if row[3] else None,
                "reset_at": _ensure_utc(row[4]).isoformat() if row[4] else None,
            }
        finally:
            cur.close()

    def update_account_balance(self, user_id: int, delta: float, cur=None) -> None:
        """Cộng delta vào balance bằng 1 statement (không read-then-write).

        `cur` truyền vào khi gọi bên trong store.transaction() để thao tác
        trên đúng connection đang BEGIN (DuckDB transaction theo connection).
        """
        cursor = cur or self.cursor()
        try:
            cursor.execute(
                "UPDATE futures_accounts SET balance = balance + ? WHERE user_id = ?",
                [delta, user_id],
            )
        finally:
            if cur is None:
                cursor.close()

    def set_account_balance(self, user_id: int, balance: float) -> None:
        cur = self.cursor()
        try:
            cur.execute(
                "UPDATE futures_accounts SET balance = ?, reset_at = now() WHERE user_id = ?",
                [balance, user_id],
            )
        finally:
            cur.close()

    def create_order(self, o: dict) -> int:
        cur = self.cursor()
        try:
            cur.execute(
                "INSERT INTO futures_orders (user_id, symbol, side, type, price, qty, leverage, tp, sl, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN') RETURNING id",
                [
                    o["user_id"],
                    o["symbol"],
                    o["side"],
                    o["type"],
                    o.get("price"),
                    o["qty"],
                    o["leverage"],
                    o.get("tp"),
                    o.get("sl"),
                ],
            )
            return int(cur.fetchone()[0])
        finally:
            cur.close()

    def get_orders(self, user_id: int, status: str | None = None) -> list[dict]:
        sql = ("SELECT id, user_id, symbol, side, type, price, qty, leverage, tp, sl, "
               "status, created_at, filled_at FROM futures_orders WHERE user_id = ?")
        params: list = [user_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        cur = self.cursor()
        try:
            rows = cur.execute(sql, params).fetchall()
            return [
                {
                    "id": r[0], "user_id": r[1], "symbol": r[2], "side": r[3],
                    "type": r[4], "price": r[5], "qty": r[6], "leverage": r[7],
                    "tp": r[8], "sl": r[9], "status": r[10],
                    "created_at": _ensure_utc(r[11]).isoformat() if r[11] else None,
                    "filled_at": _ensure_utc(r[12]).isoformat() if r[12] else None,
                }
                for r in rows
            ]
        finally:
            cur.close()

    def get_order_by_id(self, user_id: int, order_id: int) -> dict | None:
        cur = self.cursor()
        try:
            row = cur.execute(
                "SELECT id, user_id, symbol, side, type, price, qty, leverage, tp, sl, "
                "status, created_at, filled_at FROM futures_orders "
                "WHERE id = ? AND user_id = ?",
                [order_id, user_id],
            ).fetchone()
            if row is None:
                return None
            return {
                "id": row[0], "user_id": row[1], "symbol": row[2], "side": row[3],
                "type": row[4], "price": row[5], "qty": row[6], "leverage": row[7],
                "tp": row[8], "sl": row[9], "status": row[10],
                "created_at": _ensure_utc(row[11]).isoformat() if row[11] else None,
                "filled_at": _ensure_utc(row[12]).isoformat() if row[12] else None,
            }
        finally:
            cur.close()

    def cancel_order(self, user_id: int, order_id: int) -> bool:
        cur = self.cursor()
        try:
            row = cur.execute(
                "UPDATE futures_orders SET status = 'CANCELLED' "
                "WHERE id = ? AND user_id = ? AND status = 'OPEN' RETURNING id",
                [order_id, user_id],
            ).fetchone()
            return row is not None
        finally:
            cur.close()

    def fill_order(self, user_id: int, order_id: int, price: float, cur=None) -> bool:
        cursor = cur or self.cursor()
        try:
            row = cursor.execute(
                "UPDATE futures_orders SET status = 'FILLED', filled_at = now(), price = ? "
                "WHERE id = ? AND user_id = ? AND status = 'OPEN' RETURNING id",
                [price, order_id, user_id],
            ).fetchone()
            return row is not None
        finally:
            if cur is None:
                cursor.close()

    def insert_position(self, p: dict, cur=None) -> int:
        cursor = cur or self.cursor()
        try:
            row = cursor.execute(
                "INSERT INTO futures_positions (user_id, symbol, side, entry, qty, leverage, "
                "margin, liq_price, tp, sl, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN') RETURNING id",
                [
                    p["user_id"], p["symbol"], p["side"], p["entry"], p["qty"],
                    p["leverage"], p["margin"], p["liq_price"], p.get("tp"), p.get("sl"),
                ],
            ).fetchone()
            return int(row[0])
        finally:
            if cur is None:
                cursor.close()

    def _position_from_row(self, r: tuple) -> dict:
        return {
            "id": r[0], "user_id": r[1], "symbol": r[2], "side": r[3],
            "entry": r[4], "qty": r[5], "leverage": r[6], "margin": r[7],
            "liq_price": r[8], "tp": r[9], "sl": r[10], "status": r[11],
            "pnl": r[12], "exit_price": r[13],
            "closed_at": _ensure_utc(r[14]).isoformat() if r[14] else None,
            "close_reason": r[15],
            "created_at": _ensure_utc(r[16]).isoformat() if r[16] else None,
        }

    _POSITION_COLS = (
        "id, user_id, symbol, side, entry, qty, leverage, margin, liq_price, tp, sl, "
        "status, pnl, exit_price, closed_at, close_reason, created_at"
    )

    def get_positions_futures(self, user_id: int, status: str | None = None) -> list[dict]:
        sql = f"SELECT {self._POSITION_COLS} FROM futures_positions WHERE user_id = ?"
        params: list = [user_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        cur = self.cursor()
        try:
            rows = cur.execute(sql, params).fetchall()
            return [self._position_from_row(r) for r in rows]
        finally:
            cur.close()

    def get_position_by_id(self, user_id: int, pos_id: int) -> dict | None:
        cur = self.cursor()
        try:
            row = cur.execute(
                f"SELECT {self._POSITION_COLS} FROM futures_positions "
                "WHERE id = ? AND user_id = ?",
                [pos_id, user_id],
            ).fetchone()
            return self._position_from_row(row) if row else None
        finally:
            cur.close()

    def close_position_futures(
        self, user_id: int, pos_id: int, exit_price: float, pnl: float, reason: str, cur=None
    ) -> bool:
        cursor = cur or self.cursor()
        try:
            row = cursor.execute(
                "UPDATE futures_positions SET status = 'CLOSED', closed_at = now(), "
                "exit_price = ?, pnl = ?, close_reason = ? "
                "WHERE id = ? AND user_id = ? AND status = 'OPEN' RETURNING id",
                [exit_price, pnl, reason, pos_id, user_id],
            ).fetchone()
            return row is not None
        finally:
            if cur is None:
                cursor.close()

    def update_position_futures(
        self, user_id: int, pos_id: int, *, entry: float, qty: float, leverage: int,
        margin: float, liq_price: float, tp: float | None, sl: float | None, cur=None,
    ) -> None:
        """Cập nhật position sau khi merge/nett (Hedge Mode)."""
        cursor = cur or self.cursor()
        try:
            cursor.execute(
                "UPDATE futures_positions SET entry = ?, qty = ?, leverage = ?, margin = ?, "
                "liq_price = ?, tp = ?, sl = ? WHERE id = ? AND user_id = ? AND status = 'OPEN'",
                [entry, qty, leverage, margin, liq_price, tp, sl, pos_id, user_id],
            )
        finally:
            if cur is None:
                cursor.close()

    def get_all_open_orders(self) -> list[dict]:
        """Engine-level scan: toàn bộ OPEN orders (mọi user) để evaluate tick."""
        return self.get_orders_by_status_all("OPEN")

    def get_orders_by_status_all(self, status: str) -> list[dict]:
        cur = self.cursor()
        try:
            rows = cur.execute(
                "SELECT id, user_id, symbol, side, type, price, qty, leverage, tp, sl, "
                "status, created_at, filled_at FROM futures_orders WHERE status = ?",
                [status],
            ).fetchall()
            return [
                {
                    "id": r[0], "user_id": r[1], "symbol": r[2], "side": r[3],
                    "type": r[4], "price": r[5], "qty": r[6], "leverage": r[7],
                    "tp": r[8], "sl": r[9], "status": r[10],
                    "created_at": _ensure_utc(r[11]).isoformat() if r[11] else None,
                    "filled_at": _ensure_utc(r[12]).isoformat() if r[12] else None,
                }
                for r in rows
            ]
        finally:
            cur.close()

    def get_all_open_positions(self, symbol: str) -> list[dict]:
        """Engine-level scan: OPEN positions của 1 symbol (mọi user)."""
        cur = self.cursor()
        try:
            rows = cur.execute(
                f"SELECT {self._POSITION_COLS} FROM futures_positions "
                "WHERE status = 'OPEN' AND symbol = ?",
                [symbol],
            ).fetchall()
            return [self._position_from_row(r) for r in rows]
        finally:
            cur.close()

    def reset_account(self, user_id: int, exit_mark: float, cur=None) -> None:
        """Đóng mọi OPEN position + hủy mọi OPEN order + balance = 10,000.

        Gọi bên trong store.transaction() (không để margin locked rơi vãi);
        nếu không truyền `cur`, tự mở transaction an toàn.
        """
        from app.trading.formulas import calc_pnl

        async def _run():
            async with self.transaction() as tx:
                self._reset_account_inner(user_id, exit_mark, tx)

        if cur is not None:
            self._reset_account_inner(user_id, exit_mark, cur)
        else:
            import asyncio

            asyncio.run(_run())

    def _reset_account_inner(self, user_id: int, exit_mark: float, cur) -> None:
        from app.trading.formulas import calc_pnl

        for p in self.get_positions_futures(user_id, status="OPEN"):
            pnl = calc_pnl(p["entry"], exit_mark, p["qty"], p["side"])
            cur.execute(
                "UPDATE futures_positions SET status = 'CLOSED', closed_at = now(), "
                "exit_price = ?, pnl = ?, close_reason = 'RESET' "
                "WHERE id = ? AND user_id = ?",
                [exit_mark, pnl, p["id"], user_id],
            )
        cur.execute(
            "UPDATE futures_orders SET status = 'CANCELLED' "
            "WHERE user_id = ? AND status = 'OPEN'",
            [user_id],
        )
        cur.execute(
            "UPDATE futures_accounts SET balance = 10000, reset_at = now() WHERE user_id = ?",
            [user_id],
        )


def _ensure_utc(dt: datetime) -> datetime:
    """Naive datetimes are interpreted as UTC by convention (host may be UTC+7)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
