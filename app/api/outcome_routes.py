from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.trading.outcomes import auto_resolve_outcome, user_override_allowed

router = APIRouter(prefix="/api")


class OutcomeRequest(BaseModel):
    symbol: str
    timeframe: str
    direction: str
    outcome: str
    entry: float | None = None
    tp: float | None = None
    sl: float | None = None
    model: str | None = None
    signal_id: int | None = None


def _store():
    from app.api.routes import get_store

    return get_store()


@router.get("/outcomes")
async def list_outcomes(limit: int = Query(500, ge=1, le=5000)) -> dict:
    return {"outcomes": _store().get_outcomes(limit=limit)}


@router.post("/outcomes")
async def create_outcome(req: OutcomeRequest) -> dict:
    """User nhập win/lose — guard: cần track record ≥ N signals."""
    if req.outcome not in ("win", "lose", "neutral"):
        raise HTTPException(400, "outcome must be win|lose|neutral")
    if req.direction not in ("LONG", "SHORT"):
        raise HTTPException(400, "direction must be LONG|SHORT")

    store = _store()
    allowed = user_override_allowed(store, settings.feedback_min_signals)
    outcome_id = store.save_outcome(
        {
            "signal_id": req.signal_id,
            "symbol": req.symbol,
            "timeframe": req.timeframe,
            "model": req.model,
            "direction": req.direction,
            "entry": req.entry,
            "tp": req.tp,
            "sl": req.sl,
            "outcome": req.outcome,
            "user_override": True,
            "source": "user",
        }
    )
    return {"id": outcome_id, "trusted": allowed}


@router.post("/outcomes/auto-resolve")
async def auto_resolve(req: OutcomeRequest) -> dict:
    """Auto-resolve outcome từ giá (klines đã đóng) — TP→win, SL→lose."""
    store = _store()
    candles = store.get_klines(req.symbol, req.timeframe, limit=100)
    if not candles or req.entry is None or req.tp is None or req.sl is None:
        raise HTTPException(400, "insufficient data or missing prices")
    outcome = auto_resolve_outcome(
        req.symbol, req.timeframe, req.direction, req.entry, req.tp, req.sl, candles
    )
    if outcome is None:
        return {"outcome": None, "resolved": False}
    store.save_outcome(
        {
            "signal_id": req.signal_id,
            "symbol": req.symbol,
            "timeframe": req.timeframe,
            "model": req.model,
            "direction": req.direction,
            "entry": req.entry,
            "tp": req.tp,
            "sl": req.sl,
            "outcome": outcome,
            "user_override": False,
            "source": "auto",
        }
    )
    return {"outcome": outcome, "resolved": True}
