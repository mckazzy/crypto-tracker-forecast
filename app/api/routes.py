import logging
import os
from functools import lru_cache
from datetime import UTC, datetime

import duckdb
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
    os.makedirs(settings.data_dir, exist_ok=True)
    conn = duckdb.connect(settings.db_path)
    reject_path = os.path.join(settings.data_dir, "rejects", "klines-reject.log")
    return DuckDBStore(conn, reject_log_path=reject_path)


@router.get("/klines")
async def get_klines(
    symbol: str = Query(...),
    timeframe: str = Query(...),
    limit: int = Query(500, ge=1, le=5000),
) -> dict:
    if timeframe not in MS_PER_UNIT:
        raise HTTPException(400, f"invalid timeframe, must be one of {sorted(MS_PER_UNIT)}")
    store = get_store()
    rows = store.get_klines(symbol.upper(), timeframe, limit=limit)
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
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
