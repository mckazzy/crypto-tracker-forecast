from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.trading.positions import compute_pnl

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class OpenPositionRequest(BaseModel):
    symbol: str
    timeframe: str
    direction: str
    entry: float
    tp: float
    sl: float
    model: str | None = None
    source_signal_id: int | None = None


class ClosePositionRequest(BaseModel):
    exit_price: float


def _store():
    from app.api.routes import get_store

    return get_store()


@router.get("/positions")
async def list_positions(status: str | None = Query(None)) -> dict:
    if status not in (None, "open", "closed"):
        raise HTTPException(400, "status must be open|closed")
    return {"positions": _store().get_positions(status=status)}


@router.post("/positions")
async def open_position(req: OpenPositionRequest) -> dict:
    if req.direction not in ("LONG", "SHORT"):
        raise HTTPException(400, "direction must be LONG|SHORT")
    if req.entry <= 0 or req.tp <= 0 or req.sl <= 0:
        raise HTTPException(400, "prices must be positive")
    pos_id = _store().create_position(req.model_dump())
    return {"id": pos_id}


@router.post("/positions/{pos_id}/close")
async def close_position(pos_id: int, req: ClosePositionRequest) -> dict:
    store = _store()
    pos = next((p for p in store.get_positions() if p["id"] == pos_id), None)
    if pos is None:
        raise HTTPException(404, f"position {pos_id} not found")
    if pos["status"] == "closed":
        raise HTTPException(400, "position already closed")
    pnl = compute_pnl(pos["direction"], pos["entry"], req.exit_price)
    store.close_position(pos_id, req.exit_price, pnl)
    return {"id": pos_id, "pnl": pnl}


@router.get("/positions/pnl")
async def positions_pnl() -> dict:
    positions = _store().get_positions()
    closed = [p for p in positions if p["status"] == "closed"]
    total = sum(p["pnl"] or 0.0 for p in closed)
    wins = sum(1 for p in closed if (p["pnl"] or 0.0) > 0)
    return {
        "total_closed": len(closed),
        "total_open": len(positions) - len(closed),
        "total_pnl": total,
        "win_rate": (wins / len(closed)) if closed else 0.0,
        "avg_pnl": (total / len(closed)) if closed else 0.0,
    }
