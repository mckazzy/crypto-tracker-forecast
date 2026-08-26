from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.forecast.registry import registry
from app.forecast.schema import ForecastContext
from app.storage.duckdb_store import DuckDBStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/forecast")
leaderboard_router = APIRouter(prefix="/api")


def _store() -> DuckDBStore:
    from app.api.routes import get_store

    return get_store()


@router.get("/health")
async def forecast_health() -> dict:
    return {"providers": registry.health()}


@router.get("/{symbol}/{timeframe}")
async def get_forecast(
    symbol: str,
    timeframe: str,
    provider: str | None = Query(None),
) -> dict:
    """Forecast qua registry. Provider mặc định: provider đầu tiên hoặc fallback baseline."""
    symbol_u = symbol.upper()
    tf = timeframe.lower()

    if provider is not None:
        prov = registry.get(provider)
        if prov is None:
            raise HTTPException(404, f"unknown provider: {provider}")
        candidates = [prov]
    else:
        names = registry.list()
        if not names:
            raise HTTPException(503, "no forecast providers registered")
        candidates = [registry.get(n) for n in names]
        candidates = [c for c in candidates if c is not None]

    store = _store()
    candles = store.get_klines(symbol_u, tf, limit=100)
    ctx = ForecastContext(symbol=symbol_u, timeframe=tf, candles=candles)

    last_error = None
    for prov in candidates:
        try:
            signal = prov.forecast(ctx)
            registry.record_success(prov.name)
            payload = signal.model_dump(mode="json")
            # cache mọi kết quả (kể cả failed) vào forecasts table
            try:
                store.save_forecast(symbol_u, tf, prov.name, payload)
            except Exception:
                logger.exception("failed to cache forecast")
            return payload
        except Exception as e:
            logger.warning("provider %s failed: %s", prov.name, e)
            registry.record_error(prov.name, str(e))
            last_error = e
    raise HTTPException(502, f"all providers failed: {last_error}")


@leaderboard_router.get("/leaderboard")
async def leaderboard(
    symbol: str | None = Query(None),
    timeframe: str | None = Query(None),
) -> dict:
    """Xếp hạng provider theo số signal + token cost (từ forecasts table)."""
    store = _store()
    rows = store.get_forecasts(symbol=symbol.upper() if symbol else None,
                               timeframe=timeframe.lower() if timeframe else None,
                               limit=5000)
    by_provider: dict[str, dict] = {}
    for r in rows:
        name = r["provider"]
        entry = by_provider.setdefault(
            name, {"name": name, "signals": 0, "ok_signals": 0, "total_token_cost": 0}
        )
        entry["signals"] += 1
        if r["status"] == "ok":
            entry["ok_signals"] += 1
        entry["total_token_cost"] += int(r["token_cost"] or 0)
    providers = sorted(
        by_provider.values(),
        key=lambda p: (-p["total_token_cost"], -p["signals"]),
    )
    return {"symbol": symbol, "timeframe": timeframe, "providers": providers}
