"""FuturesEngine unit tests — fake in-memory store, no duckdb needed."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import pytest

from app.trading.futures_engine import FuturesEngine


@dataclass
class FakeStore:
    """In-memory fake mirroring DuckDBStore futures surface the engine uses."""

    balances: dict[int, float] = field(default_factory=dict)
    positions: dict[int, dict] = field(default_factory=dict)
    orders: dict[int, dict] = field(default_factory=dict)
    next_pid: int = 1
    next_oid: int = 1
    user_seq: int = 1
    start_balance: float = 10000.0

    # ---- accounts ----
    def get_account(self, user_id: int) -> dict | None:
        if user_id not in self.balances:
            return None
        margin_used = sum(
            p["margin"] for p in self.positions.values() if p["user_id"] == user_id and p["status"] == "OPEN"
        )
        return {"user_id": user_id, "balance": self.balances[user_id], "margin_used": margin_used}

    def update_account_balance(self, user_id: int, delta: float, cur=None) -> None:
        self.balances[user_id] = self.balances.get(user_id, self.start_balance) + delta

    # ---- orders ----
    def create_order(self, o: dict) -> int:
        oid = self.next_oid
        self.next_oid += 1
        self.orders[oid] = {**o, "id": oid, "status": "OPEN"}
        return oid

    def get_orders(self, user_id: int, status: str | None = None) -> list[dict]:
        return [
            {**o}
            for o in self.orders.values()
            if o["user_id"] == user_id and (status is None or o["status"] == status)
        ]

    def get_order_by_id(self, user_id: int, order_id: int) -> dict | None:
        o = self.orders.get(order_id)
        return {**o} if o and o["user_id"] == user_id else None

    def fill_order(self, user_id: int, order_id: int, price: float, cur=None) -> bool:
        o = self.orders.get(order_id)
        if o is None or o["user_id"] != user_id or o["status"] != "OPEN":
            return False
        o["status"] = "FILLED"
        o["filled_at"] = price
        return True

    def cancel_order(self, user_id: int, order_id: int) -> bool:
        o = self.orders.get(order_id)
        if o is None or o["user_id"] != user_id or o["status"] != "OPEN":
            return False
        o["status"] = "CANCELLED"
        return True

    def get_all_open_orders(self) -> list[dict]:
        return [{**o} for o in self.orders.values() if o["status"] == "OPEN"]

    def get_all_open_positions(self, symbol: str) -> list[dict]:
        return [
            {**p} for p in self.positions.values()
            if p["status"] == "OPEN" and p["symbol"] == symbol
        ]

    # ---- positions ----
    def insert_position(self, p: dict, cur=None) -> int:
        pid = self.next_pid
        self.next_pid += 1
        self.positions[pid] = {**p, "id": pid, "status": "OPEN"}
        return pid

    def get_positions_futures(self, user_id: int, status: str | None = None) -> list[dict]:
        return [
            {**p}
            for p in self.positions.values()
            if p["user_id"] == user_id and (status is None or p["status"] == status)
        ]

    def get_position_by_id(self, user_id: int, pos_id: int) -> dict | None:
        p = self.positions.get(pos_id)
        return {**p} if p and p["user_id"] == user_id else None

    def close_position_futures(self, user_id: int, pos_id: int, exit_price: float, pnl: float, reason: str, cur=None) -> bool:
        p = self.positions.get(pos_id)
        if p is None or p["user_id"] != user_id or p["status"] != "OPEN":
            return False
        p.update(status="CLOSED", exit_price=exit_price, pnl=pnl, close_reason=reason)
        return True

    def update_position_futures(self, user_id, pos_id, *, entry, qty, leverage, margin, liq_price, tp, sl, cur=None):
        p = self.positions.get(pos_id)
        if p is None or p["user_id"] != user_id:
            return
        p.update(entry=entry, qty=qty, leverage=leverage, margin=margin, liq_price=liq_price, tp=tp, sl=sl)

    # ---- transaction: engine cần 1 context manager async để bọc mutation ----
    @asynccontextmanager
    async def transaction(self):
        yield None

    # ---- reset (engine không dùng, route dùng) ----
    def _reset_account_inner(self, user_id: int, exit_mark: float, cur) -> None:
        for p in self.get_positions_futures(user_id, status="OPEN"):
            self.close_position_futures(user_id, p["id"], exit_mark, 0.0, "RESET")
        self.balances[user_id] = self.start_balance


def make_user(store: FakeStore, user_id: int = 1, balance: float = 10000.0) -> int:
    store.balances[user_id] = balance
    return user_id


def place_order(
    store: FakeStore,
    user_id: int,
    symbol: str = "BTCUSDT",
    side: str = "LONG",
    type_: str = "MARKET",
    price: float | None = None,
    qty: float = 0.01,
    leverage: int = 10,
    tp: float | None = None,
    sl: float | None = None,
) -> int:
    return store.create_order(
        {
            "user_id": user_id,
            "symbol": symbol,
            "side": side,
            "type": type_,
            "price": price,
            "qty": qty,
            "leverage": leverage,
            "tp": tp,
            "sl": sl,
        }
    )


async def tick(engine: FuturesEngine, mark: float, symbol: str = "BTCUSDT"):
    await engine.on_mark_price(symbol, mark)


class TestMarketFill:
    async def test_market_long_fill_at_mark(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        oid = place_order(store, uid, qty=0.01, leverage=10)
        await tick(engine, 90000.0)
        positions = store.get_positions_futures(uid)
        assert len(positions) == 1
        p = positions[0]
        assert p["entry"] == 90000.0
        assert p["side"] == "LONG"
        assert p["margin"] == pytest.approx(90.0)  # 0.01 * 90000 / 10
        assert store.get_order_by_id(uid, oid)["status"] == "FILLED"

    async def test_market_short_fill(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        place_order(store, uid, side="SHORT", qty=1.0, leverage=20)
        await tick(engine, 3000.0)
        p = store.get_positions_futures(uid)[0]
        assert p["side"] == "SHORT"
        assert p["margin"] == pytest.approx(150.0)

    async def test_margin_exceeds_available_rejected(self):
        store = FakeStore()
        uid = make_user(store, balance=100.0)
        engine = FuturesEngine(store)
        place_order(store, uid, qty=1.0, leverage=10)  # margin = mark*0.1 = 9000
        await tick(engine, 90000.0)
        assert store.get_positions_futures(uid) == []
        assert store.get_order_by_id(uid, 1)["status"] == "OPEN"  # giữ OPEN, không fill


class TestLimitFill:
    async def test_long_limit_not_filled_above_price(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        oid = place_order(store, uid, type_="LIMIT", price=85000.0, qty=0.01, leverage=10)
        await tick(engine, 90000.0)  # mark > price → chưa fill
        assert store.get_order_by_id(uid, oid)["status"] == "OPEN"
        assert store.get_positions_futures(uid) == []

    async def test_long_limit_fills_when_mark_crosses(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        oid = place_order(store, uid, type_="LIMIT", price=85000.0, qty=0.01, leverage=10)
        await tick(engine, 90000.0)
        await tick(engine, 84000.0)  # mark <= price → fill
        assert store.get_order_by_id(uid, oid)["status"] == "FILLED"
        p = store.get_positions_futures(uid)[0]
        assert p["entry"] == 85000.0

    async def test_short_limit_not_filled_below_price(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        oid = place_order(store, uid, side="SHORT", type_="LIMIT", price=3100.0, qty=1.0, leverage=10)
        await tick(engine, 3000.0)  # mark < price → chưa fill
        assert store.get_order_by_id(uid, oid)["status"] == "OPEN"

    async def test_short_limit_fills_when_mark_crosses(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        oid = place_order(store, uid, side="SHORT", type_="LIMIT", price=3100.0, qty=1.0, leverage=10)
        await tick(engine, 3000.0)
        await tick(engine, 3200.0)  # mark >= price → fill
        assert store.get_order_by_id(uid, oid)["status"] == "FILLED"


class TestTakeProfitStopLoss:
    async def test_tp_long_close_with_pnl(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        place_order(store, uid, qty=0.01, leverage=10, tp=95000.0)
        await tick(engine, 90000.0)  # mở LONG entry 90000, trừ margin 90
        assert store.balances[uid] == pytest.approx(9910.0)
        await tick(engine, 96000.0)  # mark >= tp → close
        pos = store.get_positions_futures(uid)[0]
        assert pos["status"] == "CLOSED"
        assert pos["close_reason"] == "TP"
        assert pos["exit_price"] == pytest.approx(96000.0)
        assert pos["pnl"] == pytest.approx(60.0)  # (96000-90000)*0.01
        # balance = 9910 (sau margin) + margin 90 + pnl 60 = 10060
        assert store.balances[uid] == pytest.approx(10060.0)

    async def test_sl_short_close_lose(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        place_order(store, uid, side="SHORT", qty=1.0, leverage=10, sl=3300.0)
        await tick(engine, 3000.0)  # entry 3000, margin = 300
        assert store.balances[uid] == pytest.approx(9700.0)
        await tick(engine, 3400.0)  # mark >= sl → close lose
        pos = store.get_positions_futures(uid)[0]
        assert pos["close_reason"] == "SL"
        assert pos["pnl"] == pytest.approx(-400.0)  # (3000-3400)*1
        # balance = 9700 + 300 - 400 = 9600
        assert store.balances[uid] == pytest.approx(9600.0)


class TestLiquidation:
    async def test_long_liquidation_no_margin_return(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        place_order(store, uid, qty=0.01, leverage=10)  # entry 90000, liq = 81455
        await tick(engine, 90000.0)
        assert store.balances[uid] == pytest.approx(9910.0)
        await tick(engine, 80000.0)  # mark <= liq
        pos = store.get_positions_futures(uid)[0]
        assert pos["status"] == "CLOSED"
        assert pos["close_reason"] == "LIQUIDATION"
        # margin 90 mất đứt — balance giữ 9910 (không hoàn margin, không âm)
        assert store.balances[uid] == pytest.approx(9910.0)

    async def test_short_liquidation(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        place_order(store, uid, side="SHORT", qty=1.0, leverage=10)  # entry 3000, liq=3298.5
        await tick(engine, 3000.0)
        assert store.balances[uid] == pytest.approx(9700.0)
        await tick(engine, 3400.0)
        pos = store.get_positions_futures(uid)[0]
        assert pos["close_reason"] == "LIQUIDATION"
        assert store.balances[uid] == pytest.approx(9700.0)


class TestHedgeModeNetting:
    async def test_same_direction_merges(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        place_order(store, uid, qty=0.01, leverage=10)
        place_order(store, uid, qty=0.01, leverage=10)
        await tick(engine, 90000.0)
        positions = store.get_positions_futures(uid)
        assert len(positions) == 1
        p = positions[0]
        assert p["qty"] == pytest.approx(0.02)
        assert p["entry"] == pytest.approx(90000.0)  # weighted average

    async def test_avg_entry_weighted(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        place_order(store, uid, qty=1.0, leverage=10)
        await tick(engine, 100.0)  # entry 100, margin 10
        assert store.balances[uid] == pytest.approx(9990.0)
        place_order(store, uid, qty=1.0, leverage=10)
        await tick(engine, 200.0)  # add 1.0 @ 200 → margin mới 30, trả lại 10
        p = store.get_positions_futures(uid)[0]
        assert p["qty"] == pytest.approx(2.0)
        assert p["entry"] == pytest.approx(150.0)
        assert p["margin"] == pytest.approx(30.0)  # 150*2/10
        # KHÔNG double-charge: 9990 + 10 (trả margin cũ) - 30 (margin mới) = 9970
        assert store.balances[uid] == pytest.approx(9970.0)

    async def test_opposite_direction_creates_separate_position(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        place_order(store, uid, qty=0.01, leverage=10)
        place_order(store, uid, side="SHORT", qty=0.01, leverage=10)
        await tick(engine, 90000.0)
        positions = store.get_positions_futures(uid)
        assert len(positions) == 2
        assert {p["side"] for p in positions} == {"LONG", "SHORT"}

    async def test_close_entire_position(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        place_order(store, uid, qty=0.02, leverage=10)
        await tick(engine, 90000.0)
        pid = store.get_positions_futures(uid)[0]["id"]
        from app.trading.formulas import calc_close_balance, calc_pnl

        p = store.get_position_by_id(uid, pid)
        pnl = calc_pnl(p["entry"], 92000.0, p["qty"], p["side"])
        async with store.transaction() as tx:
            store.close_position_futures(uid, pid, 92000.0, pnl, "MANUAL", cur=tx)
            store.update_account_balance(uid, p["margin"] + pnl, cur=tx)
        assert store.get_position_by_id(uid, pid)["status"] == "CLOSED"
        # 10000 - margin 180 + margin 180 + pnl 40 = 10040
        assert store.balances[uid] == pytest.approx(calc_close_balance(9820.0, 180.0, 40.0))


class TestEngineRobustness:
    async def test_exception_in_tick_does_not_kill_engine(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        place_order(store, uid, qty=0.01, leverage=10)
        # tick với mark None → exception bên trong, nhưng tick sau vẫn chạy
        with pytest.raises(Exception):
            await engine.on_mark_price("BTCUSDT", None)
        await tick(engine, 90000.0)
        assert len(store.get_positions_futures(uid)) == 1

    async def test_zero_clients_tick_still_reaches_engine(self):
        """Tick từ queue upstream (không phải client) — engine hoạt động độc lập."""
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        queue: asyncio.Queue = asyncio.Queue()
        engine.set_queue(queue)
        place_order(store, uid, qty=0.01, leverage=10)
        await queue.put({"symbol": "BTCUSDT", "mark": 90000.0})
        # Chạy 1 vòng consume duy nhất thủ công
        await engine._process_one()
        assert len(store.get_positions_futures(uid)) == 1

    async def test_startup_reconciliation_loads_open_orders(self):
        store = FakeStore()
        uid = make_user(store)
        # Order OPEN được tạo trước khi engine start (restart scenario)
        place_order(store, uid, type_="LIMIT", price=85000.0, qty=0.01, leverage=10)
        engine = FuturesEngine(store)
        engine._store = store  # fake store đã có data
        await tick(engine, 90000.0)  # không cross
        assert store.get_positions_futures(uid) == []
        await tick(engine, 84000.0)  # cross → fill sau restart
        assert len(store.get_positions_futures(uid)) == 1

    async def test_mutation_failure_rolls_back_balance(self):
        """Nếu position close thất bại → balance không đổi."""
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        place_order(store, uid, qty=0.01, leverage=10, tp=95000.0)
        await tick(engine, 90000.0)
        assert store.balances[uid] == pytest.approx(9910.0)

        class BoomStore(FakeStore):
            def close_position_futures(self, *a, **kw):
                raise RuntimeError("db write failed")

        engine._store = BoomStore()
        engine._store.balances = store.balances
        engine._store.positions = store.positions
        engine._store.orders = store.orders
        try:
            await tick(engine, 96000.0)
        except Exception:
            pass
        # close thất bại → transaction rollback → balance giữ nguyên (không cộng margin/pnl)
        assert store.balances[uid] == pytest.approx(9910.0)
        # position vẫn OPEN
        assert store.get_positions_futures(uid)[0]["status"] == "OPEN"


class TestLastMark:
    async def test_last_mark_cached(self):
        store = FakeStore()
        uid = make_user(store)
        engine = FuturesEngine(store)
        await tick(engine, 12345.0)
        assert engine.last_mark["BTCUSDT"] == 12345.0
