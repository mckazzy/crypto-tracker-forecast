from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.forecast.registry import registry
from app.forecast.schema import ForecastContext
from app.storage.duckdb_store import DuckDBStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/forecast")


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
            return signal.model_dump(mode="json")
        except Exception as e:
            logger.warning("provider %s failed: %s", prov.name, e)
            registry.record_error(prov.name, str(e))
            last_error = e
    raise HTTPException(502, f"all providers failed: {last_error}")
