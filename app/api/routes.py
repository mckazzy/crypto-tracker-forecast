import logging
import os
from functools import lru_cache
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.connectors.binance_rest import BinanceRestClient, MS_PER_UNIT
from app.config import settings
from app.ingest.backfill import BackfillRunner
from app.storage.duckdb_store import DuckDBStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@lru_cache(maxsize=1)
def get_store() -> DuckDBStore:
    import duckdb as _duckdb

    os.makedirs(settings.data_dir, exist_ok=True)
    try:
        conn = _duckdb.connect(settings.db_path)
    except Exception:
        # WAL corrupt (crash không graceful) → xóa WAL, data chính vẫn trong .duckdb
        logger.warning("DuckDB open failed — removing stale WAL and retrying")
        wal = settings.db_path + ".wal"
        if os.path.exists(wal):
            os.remove(wal)
        conn = _duckdb.connect(settings.db_path)
    reject_path = os.path.join(settings.data_dir, "rejects", "klines-reject.log")
    return DuckDBStore(conn, reject_log_path=reject_path)


@router.get("/klines")
async def get_klines(
    symbol: str = Query(...),
    timeframe: str = Query(...),
    limit: int = Query(500, ge=1, le=5000),
    start_time: int | None = Query(None, ge=0),
    end_time: int | None = Query(None, ge=0),
) -> dict:
    tf_norm = timeframe.lower()
    if tf_norm not in MS_PER_UNIT:
        raise HTTPException(400, f"invalid timeframe, must be one of {sorted(MS_PER_UNIT)}")
    if start_time is not None and end_time is not None and start_time >= end_time:
        raise HTTPException(400, "start_time must be < end_time")

    symbol_u = symbol.upper()
    tf_l = timeframe.lower()
    store = get_store()

    known = {s.upper() for s in settings.symbol_list}
    if symbol_u not in known:
        raise HTTPException(404, f"unknown symbol: {symbol_u}")

    start_dt = datetime.fromtimestamp(start_time / 1000, tz=UTC) if start_time else None
    end_dt = datetime.fromtimestamp(end_time / 1000, tz=UTC) if end_time else None
    rows = store.get_klines(symbol_u, tf_l, start=start_dt, end=end_dt, limit=limit)
    return {
        "symbol": symbol_u,
        "timeframe": tf_l,
        "count": len(rows),
        "data": [
            {
                "open_time": int(r["open_time"].timestamp() * 1000),
                "close_time": int(r["close_time"].timestamp() * 1000),
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r["volume"],
            }
            for r in rows
        ],
    }


@router.get("/symbols")
async def list_symbols() -> dict:
    """Configured symbols with per-timeframe stored-candle counts."""
    store = get_store()
    out = []
    for sym in settings.symbol_list:
        tfs = [
            {"timeframe": tf, "count": store.count(sym, tf)}
            for tf in settings.timeframe_list
        ]
        out.append({"symbol": sym, "timeframes": tfs})
    return {"symbols": out}


class BackfillRequest(BaseModel):
    symbol: str | None = None
    timeframes: str | None = None
    days: int = 365
    resume: bool = False


@router.post("/backfill")
async def run_backfill(req: BackfillRequest) -> dict:
    """Trigger historical backfill; runs synchronously and returns counts."""
    symbol = (req.symbol or settings.symbol_list[0]).upper()
    tfs = (
        [t.strip() for t in req.timeframes.split(",")]
        if req.timeframes
        else settings.timeframe_list
    )
    for tf in tfs:
        if tf not in MS_PER_UNIT:
            raise HTTPException(400, f"invalid timeframe: {tf}")
    client = BinanceRestClient(base_url=settings.binance_rest_base)
    try:
        client.ping()
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    store = get_store()
    runner = BackfillRunner(store=store, client=client)
    inserted = runner.backfill(symbol, tfs, days=req.days, resume=req.resume)
    return {
        "symbol": symbol,
        "timeframes": tfs,
        "days": req.days,
        "inserted": inserted,
        "rejected": len(store.reject_log),
    }
