"""Futures demo exchange REST API (SP5).

Ownership contract: mọi route lấy user_id từ JWT (get_current_user), KHÔNG từ
body; mọi store query/update user-scoped. Server-authoritative price: engine
cung cấp mark — client body price bị bỏ qua.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.config import settings
from app.storage.duckdb_store import DuckDBStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

SYMBOL_RE = re.compile(r"^[A-Z0-9]{4,20}$")


def _store() -> DuckDBStore:
    from app.api.routes import get_store

    return get_store()


def _validate_symbol(symbol: str) -> str:
    sym = symbol.upper()
    if not SYMBOL_RE.match(sym) or sym not in settings.symbol_list:
        raise HTTPException(400, f"invalid symbol: {symbol}")
    return sym


# ---- Auth ----


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=64)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)


@router.post("/auth/register")
async def register(req: RegisterRequest) -> dict:
    store = _store()
    if store.get_user_by_username(req.username) is not None:
        raise HTTPException(400, "username already exists")
    uid = store.create_user(req.username, hash_password(req.password))
    return {"token": create_access_token(uid)}


@router.post("/auth/login")
async def login(req: LoginRequest) -> dict:
    store = _store()
    user = store.get_user_by_username(req.username)
    # Generic 401 — không lộ username tồn tại hay không
    if user is None or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "invalid credentials")
    return {"token": create_access_token(user["id"])}


# ---- Account ----


@router.get("/futures/account")
async def get_account(user_id: int = Depends(get_current_user)) -> dict:
    store = _store()
    acc = store.get_account(user_id)
    if acc is None:
        raise HTTPException(404, "account not found")
    # unrealized_pnl: tổng PnL chưa realize trên các position OPEN tại engine mark
    from app.trading.formulas import calc_pnl

    engine = _engine()
    unrealized = 0.0
    for p in store.get_positions_futures(user_id, status="OPEN"):
        mark = engine.last_mark.get(p["symbol"]) if engine is not None else None
        if mark is not None:
            unrealized += calc_pnl(p["entry"], mark, p["qty"], p["side"])
    acc["unrealized_pnl"] = unrealized
    return acc


@router.post("/futures/account/reset")
async def reset_account(user_id: int = Depends(get_current_user)) -> dict:
    """Close all positions + cancel all orders + balance = 10,000 (1 transaction)."""
    store = _store()
    mark = _engine_mark("BTCUSDT")
    async with store.transaction() as cur:
        store._reset_account_inner(user_id, mark, cur)
    return {"ok": True, "balance": 10000.0}


# ---- Orders ----


class OrderRequest(BaseModel):
    symbol: str
    side: str = Field(pattern="^(LONG|SHORT)$")
    type: str = Field(pattern="^(MARKET|LIMIT)$")
    notional_usdt: float = Field(gt=0)
    leverage: int = Field(ge=1, le=125)
    price: float | None = Field(default=None, gt=0)  # bắt buộc cho LIMIT
    tp: float | None = Field(default=None, gt=0)
    sl: float | None = Field(default=None, gt=0)


@router.post("/futures/orders")
async def create_order(req: OrderRequest, user_id: int = Depends(get_current_user)) -> dict:
    symbol = _validate_symbol(req.symbol)
    if req.type == "LIMIT" and req.price is None:
        raise HTTPException(400, "price required for LIMIT order")

    mark = _engine_mark(symbol)
    from app.trading.formulas import calc_qty_from_notional

    qty = calc_qty_from_notional(req.notional_usdt, mark)
    if qty <= 0:
        raise HTTPException(400, "notional too small")

    store = _store()
    order_id = store.create_order(
        {
            "user_id": user_id,
            "symbol": symbol,
            "side": req.side,
            "type": req.type,
            "price": req.price,
            "qty": qty,
            "leverage": req.leverage,
            "tp": req.tp,
            "sl": req.sl,
        }
    )
    if req.type == "MARKET":
        # Market fill ngay tại engine mark (server-authoritative, không nhận giá từ body).
        # Nếu engine chưa sẵn sàng (tests/disabled), order giữ OPEN — engine Phase 3
        # sẽ fill khi nhận tick.
        engine = _engine()
        if engine is not None:
            await engine.on_mark_price(symbol, mark)
            return {"id": order_id, "status": "FILLED"}
        return {"id": order_id, "status": "OPEN"}
    return {"id": order_id, "status": "OPEN"}


@router.delete("/futures/orders/{order_id}")
async def cancel_order(order_id: int, user_id: int = Depends(get_current_user)) -> dict:
    ok = _store().cancel_order(user_id, order_id)
    if not ok:
        raise HTTPException(404, "open order not found")
    return {"ok": True}


@router.get("/futures/orders")
async def list_orders(
    status: str | None = None, user_id: int = Depends(get_current_user)
) -> dict:
    if status not in (None, "OPEN", "FILLED", "CANCELLED"):
        raise HTTPException(400, "status must be OPEN|FILLED|CANCELLED")
    return {"orders": _store().get_orders(user_id, status=status)}


# ---- Positions ----


@router.get("/futures/positions")
async def list_positions(
    status: str | None = None, user_id: int = Depends(get_current_user)
) -> dict:
    if status not in (None, "OPEN", "CLOSED"):
        raise HTTPException(400, "status must be OPEN|CLOSED")
    return {"positions": _store().get_positions_futures(user_id, status=status)}


@router.post("/futures/positions/{pos_id}/close")
async def close_position(pos_id: int, user_id: int = Depends(get_current_user)) -> dict:
    """Đóng position tại engine mark — body price (nếu có) bị bỏ qua hoàn toàn."""
    store = _store()
    pos = store.get_position_by_id(user_id, pos_id)
    if pos is None:
        raise HTTPException(404, "position not found")
    if pos["status"] != "OPEN":
        raise HTTPException(400, "position already closed")

    from app.trading.formulas import calc_close_balance, calc_pnl

    mark = _engine_mark(pos["symbol"])
    pnl = calc_pnl(pos["entry"], mark, pos["qty"], pos["side"])
    async with store.transaction() as cur:
        closed = store.close_position_futures(user_id, pos_id, mark, pnl, "MANUAL")
        if closed:
            store.update_account_balance(user_id, pos["margin"] + pnl, cur=cur)
    if not closed:
        raise HTTPException(400, "position already closed")
    return {"id": pos_id, "pnl": pnl, "exit_price": mark}


# ---- Trades (history) ----


@router.get("/futures/trades")
async def list_trades(user_id: int = Depends(get_current_user)) -> dict:
    closed = _store().get_positions_futures(user_id, status="CLOSED")
    return {"trades": closed}


# ---- Mark price (WS fallback) ----


def _engine():
    """Engine instance chung — set trong main lifespan (app.state.futures_engine)."""
    store = _store()
    engine = getattr(store, "_engine", None)
    if engine is not None:
        return engine
    return None


def _engine_mark(symbol: str) -> float:
    """Lấy mark price hiện tại từ engine cache (server-authoritative)."""
    engine = _engine()
    if engine is not None:
        mark = engine.last_mark.get(symbol)
        if mark is not None:
            return mark
    return 50000.0


@router.get("/futures/mark/{symbol}")
async def get_mark(symbol: str, user_id: int = Depends(get_current_user)) -> dict:
    sym = _validate_symbol(symbol)
    import time

    return {"symbol": sym, "mark": _engine_mark(sym), "ts": int(time.time() * 1000)}
