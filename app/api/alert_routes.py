from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.alerts.engine import AlertEngine
from app.alerts.telegram import TelegramSender

router = APIRouter(prefix="/api")


class AlertRequest(BaseModel):
    symbol: str
    timeframe: str
    direction: str
    entry: float | None = None
    take_profit: list[float] = []
    stop_loss: float | None = None
    model: str | None = None


def _store():
    from app.api.routes import get_store

    return get_store()


@router.get("/alerts")
async def list_alerts(limit: int = Query(100, ge=1, le=500)) -> dict:
    return {"alerts": _store().get_alerts(limit=limit)}


@router.post("/alerts")
async def create_alert(req: AlertRequest) -> dict:
    """Manual alert dispatch (test/webhook) — dùng engine để dedup + lưu history."""
    if req.direction not in ("LONG", "SHORT"):
        raise HTTPException(400, "direction must be LONG|SHORT")
    engine = AlertEngine(_store())
    record = engine.dispatch(req.model_dump())
    return {"alert": record}
