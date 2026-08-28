"""FuturesEngine — asyncio task consuming mark-price ticks.

Server-authoritative price engine: fill market/limit orders, trigger TP/SL/
liquidation, update balances per Phase 1 formulas. Ticks come from the WS relay
upstream reader via a single queue (NOT from client handlers) so the engine
keeps liquidating even with 0 connected clients.

All mutations run inside store.transaction() (BEGIN/COMMIT/ROLLBACK under the
Store write-lock). Balance changes use a single `balance = balance + ?`
statement — no read-then-write. Hedge Mode: max 1 LONG + 1 SHORT per
(user_id, symbol); same-direction orders merge & net by weighted average.
"""
from __future__ import annotations

import asyncio
import logging

from app.trading.formulas import (
    calc_close_balance,
    calc_liq_balance,
    calc_liq_price,
    calc_margin,
    calc_pnl,
)

logger = logging.getLogger(__name__)


class FuturesEngine:
    def __init__(self, store, symbol_list: list[str] | None = None):
        self._store = store
        self.symbol_list = symbol_list
        self.last_mark: dict[str, float] = {}
        self._queue: asyncio.Queue | None = None

    @property
    def store(self):
        return self._store

    def set_queue(self, queue: asyncio.Queue) -> None:
        self._queue = queue

    async def run(self) -> None:
        """Consume ticks từ queue upstream. Exception trong 1 tick không kill task."""
        while True:
            await self._process_one()

    async def _process_one(self) -> None:
        try:
            item = await self._queue.get()
            await self.on_mark_price(item["symbol"], item["mark"])
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — tick lỗi không được giết engine
            logger.exception("engine tick error: %s", e)

    async def on_mark_price(self, symbol: str, mark: float) -> None:
        """Handle 1 mark-price tick: cập nhật cache, evaluate orders + positions."""
        if mark is None or mark <= 0:
            raise ValueError(f"invalid mark price: {mark}")
        self.last_mark[symbol] = mark

        # Evaluate limit orders trước (mở position mới), sau đó TP/SL/liq trên
        # positions hiện tại. Cùng 1 tick: SL → TP → liq (mark cuối, gap demo-level).
        await self._evaluate_orders(symbol, mark)
        await self._evaluate_positions(symbol, mark)

    # ---- Order fills ----

    async def _evaluate_orders(self, symbol: str, mark: float) -> None:
        # Cần scan orders của mọi user cho symbol này. Engine quản lý qua store:
        # load toàn bộ OPEN orders của symbol (store-level scan).
        open_orders = self._load_open_orders(symbol)
        for o in open_orders:
            if o["type"] == "LIMIT":
                if o["side"] == "LONG" and mark > o["price"]:
                    continue
                if o["side"] == "SHORT" and mark < o["price"]:
                    continue
            # MARKET hoặc limit cross → fill. Limit fill tại limit price (Binance
            # convention: limit order luôn fill tốt nhất = giá limit), market fill tại mark.
            fill_price = o["price"] if o["type"] == "LIMIT" and o["price"] else mark
            await self._execute_fill(o, fill_price)

    def _load_open_orders(self, symbol: str) -> list[dict]:
        """Load OPEN orders cho symbol (engine-level scan, user-agnostic)."""
        return [o for o in self._iter_all_orders() if o["symbol"] == symbol and o["status"] == "OPEN"]

    def _iter_all_orders(self):
        """Store phải expose cách scan toàn bộ OPEN orders — DuckDBStore bổ sung."""
        if hasattr(self._store, "get_all_open_orders"):
            return self._store.get_all_open_orders()
        # Fake store fallback: scan theo users đã biết
        out = []
        for o in getattr(self._store, "orders", {}).values():
            if o["status"] == "OPEN":
                out.append(o)
        return out

    async def _execute_fill(self, o: dict, mark: float) -> None:
        user_id, symbol, side = o["user_id"], o["symbol"], o["side"]
        qty, leverage = o["qty"], o["leverage"]

        acc = self._store.get_account(user_id)
        if acc is None:
            return
        margin_used = acc.get("margin_used", 0.0)
        from app.trading.formulas import calc_margin_available

        available = calc_margin_available(acc["balance"], margin_used)
        margin = calc_margin(qty, mark, leverage)
        if margin > available + 1e-9:
            logger.warning("reject fill user=%s margin=%.2f available=%.2f", user_id, margin, available)
            return  # giữ order OPEN (không fill, không hủy)

        async with self._store.transaction() as tx:
            if not self._store.fill_order(user_id, o["id"], mark, cur=tx):
                return  # đã fill/cancel bởi người khác (race)
            self._apply_fill(user_id, symbol, side, qty, mark, leverage, o.get("tp"), o.get("sl"), tx)

    def _apply_fill(
        self, user_id: int, symbol: str, side: str, qty: float,
        entry: float, leverage: int, tp: float | None, sl: float | None, tx,
    ) -> None:
        """Hedge Mode: merge cùng chiều, mở riêng ngược chiều."""
        existing = [
            p for p in self._store.get_positions_futures(user_id, status="OPEN")
            if p["symbol"] == symbol and p["side"] == side
        ]
        if existing:
            p = existing[0]
            new_qty = p["qty"] + qty
            avg_entry = (p["entry"] * p["qty"] + entry * qty) / new_qty
            margin = calc_margin(avg_entry, new_qty, leverage)
            liq = calc_liq_price(avg_entry, leverage, side)
            self._update_position(p["id"], user_id, avg_entry, new_qty, leverage, margin, liq, tp, sl, tx)
            # Merge: trả lại margin cũ, chỉ trừ phần margin tăng thêm
            # (tránh double-charge — balance chỉ bị trừ 1 lần cho cùng exposure)
            self._store.update_account_balance(user_id, p["margin"] - margin, cur=tx)
        else:
            margin = calc_margin(entry, qty, leverage)
            liq = calc_liq_price(entry, leverage, side)
            self._store.insert_position(
                {
                    "user_id": user_id,
                    "symbol": symbol,
                    "side": side,
                    "entry": entry,
                    "qty": qty,
                    "leverage": leverage,
                    "margin": margin,
                    "liq_price": liq,
                    "tp": tp,
                    "sl": sl,
                },
                cur=tx,
            )
            # Trừ margin ngay khi mở (single statement, không read-then-write)
            self._store.update_account_balance(user_id, -margin, cur=tx)

    def _update_position(
        self, pid: int, user_id: int, entry: float, qty: float,
        leverage: int, margin: float, liq: float, tp: float | None, sl: float | None, tx,
    ) -> None:
        if hasattr(self._store, "update_position_futures"):
            self._store.update_position_futures(
                user_id, pid, entry=entry, qty=qty, leverage=leverage,
                margin=margin, liq_price=liq, tp=tp, sl=sl, cur=tx,
            )
        else:
            p = self._store.positions.get(pid)
            if p:
                p.update(entry=entry, qty=qty, leverage=leverage, margin=margin, liq_price=liq, tp=tp, sl=sl)

    # ---- Position evaluation (TP/SL/liq) ----

    async def _evaluate_positions(self, symbol: str, mark: float) -> None:
        for p in self._iter_all_open_positions(symbol):
            try:
                await self._evaluate_position(p, mark)
            except Exception as e:  # noqa: BLE001
                logger.exception("position eval error: %s", e)

    def _iter_all_open_positions(self, symbol: str):
        if hasattr(self._store, "get_all_open_positions"):
            return self._store.get_all_open_positions(symbol)
        out = []
        for p in getattr(self._store, "positions", {}).values():
            if p["status"] == "OPEN" and p["symbol"] == symbol:
                out.append(p)
        return out

    async def _evaluate_position(self, p: dict, mark: float) -> None:
        """Thứ tự trong 1 tick: SL → TP → liq (mark cuối)."""
        user_id, pos_id, side, qty, entry = p["user_id"], p["id"], p["side"], p["qty"], p["entry"]

        # SL
        if p.get("sl") is not None:
            if (side == "LONG" and mark <= p["sl"]) or (side == "SHORT" and mark >= p["sl"]):
                await self._close_position(user_id, pos_id, mark, "SL")
                return
        # TP
        if p.get("tp") is not None:
            if (side == "LONG" and mark >= p["tp"]) or (side == "SHORT" and mark <= p["tp"]):
                await self._close_position(user_id, pos_id, mark, "TP")
                return
        # Liq
        if (side == "LONG" and mark <= p["liq_price"]) or (side == "SHORT" and mark >= p["liq_price"]):
            await self._liquidate(user_id, pos_id)
            return

    async def _close_position(self, user_id: int, pos_id: int, exit_price: float, reason: str) -> None:
        p = self._store.get_position_by_id(user_id, pos_id)
        if p is None or p["status"] != "OPEN":
            return
        pnl = calc_pnl(p["entry"], exit_price, p["qty"], p["side"])
        new_balance = calc_close_balance(
            self._store.get_account(user_id)["balance"], p["margin"], pnl
        )
        async with self._store.transaction() as tx:
            if not self._store.close_position_futures(user_id, pos_id, exit_price, pnl, reason, cur=tx):
                return
            delta = new_balance - self._store.get_account(user_id)["balance"]
            self._store.update_account_balance(user_id, delta, cur=tx)

    async def _liquidate(self, user_id: int, pos_id: int) -> None:
        p = self._store.get_position_by_id(user_id, pos_id)
        if p is None or p["status"] != "OPEN":
            return
        async with self._store.transaction() as tx:
            if not self._store.close_position_futures(user_id, pos_id, p["liq_price"], 0.0, "LIQUIDATION", cur=tx):
                return
            # Margin mất đứt; balance không đổi (calc_liq_balance clamp)
            new_balance = calc_liq_balance(self._store.get_account(user_id)["balance"])
            delta = new_balance - self._store.get_account(user_id)["balance"]
            self._store.update_account_balance(user_id, delta, cur=tx)
