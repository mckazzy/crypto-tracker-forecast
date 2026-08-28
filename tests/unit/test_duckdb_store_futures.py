from datetime import UTC, datetime

import pytest

from app.auth.security import hash_password
from app.storage.duckdb_store import DuckDBStore

START_BALANCE = 10_000.0


@pytest.fixture
def store(tmp_duckdb) -> DuckDBStore:
    return DuckDBStore(tmp_duckdb)


def _user(store: DuckDBStore, username: str = "alice") -> int:
    return store.create_user(username, hash_password("password123"))


class TestUsers:
    def test_create_and_get_user(self, store):
        uid = _user(store, "bob")
        u = store.get_user_by_username("bob")
        assert u["id"] == uid
        assert u["username"] == "bob"
        assert u["password_hash"] != hash_password("password123")
        assert u["password_hash"].startswith("$2")

    def test_duplicate_username_raises(self, store):
        _user(store, "bob")
        with pytest.raises(Exception):
            _user(store, "bob")

    def test_sql_metacharacters_roundtrip_literal(self, store):
        """Username chứa SQL metacharacters được xử lý như literal (placeholder)."""
        tricky = "al'ice\"--; DROP TABLE users;"
        uid = store.create_user(tricky, "hash1")
        u = store.get_user_by_username(tricky)
        assert u["id"] == uid
        assert store.count_users() == 1

    def test_get_user_missing_returns_none(self, store):
        assert store.get_user_by_username("nobody") is None


class TestAccount:
    def test_new_user_has_10000_balance(self, store):
        uid = _user(store)
        acc = store.get_account(uid)
        assert acc["balance"] == START_BALANCE
        assert acc["margin_used"] == 0.0

    def test_get_account_missing_user_none(self, store):
        assert store.get_account(999) is None

    def test_update_balance_single_statement(self, store):
        uid = _user(store)
        store.update_account_balance(uid, -2500.0)
        assert store.get_account(uid)["balance"] == 7500.0

    def test_update_balance_wrong_user_noop(self, store):
        _user(store, "alice")
        uid_b = _user(store, "bob")
        store.update_account_balance(uid_b, 100.0)
        assert store.get_account(uid_b)["balance"] == START_BALANCE + 100.0


class TestOrders:
    def test_create_and_get_order_user_scoped(self, store):
        uid = _user(store)
        oid = store.create_order(
            {
                "user_id": uid,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "LIMIT",
                "price": 90000.0,
                "qty": 0.01,
                "leverage": 10,
                "tp": None,
                "sl": None,
            }
        )
        rows = store.get_orders(uid)
        assert len(rows) == 1
        assert rows[0]["id"] == oid
        assert rows[0]["status"] == "OPEN"
        assert rows[0]["type"] == "LIMIT"
        assert rows[0]["price"] == 90000.0

    def test_get_orders_other_user_empty(self, store):
        uid_a = _user(store, "alice")
        uid_b = _user(store, "bob")
        store.create_order(
            {
                "user_id": uid_a,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "MARKET",
                "price": None,
                "qty": 0.01,
                "leverage": 10,
                "tp": None,
                "sl": None,
            }
        )
        assert store.get_orders(uid_b) == []

    def test_get_order_by_id_requires_user(self, store):
        uid = _user(store)
        oid = store.create_order(
            {
                "user_id": uid,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "MARKET",
                "price": None,
                "qty": 0.01,
                "leverage": 10,
                "tp": None,
                "sl": None,
            }
        )
        assert store.get_order_by_id(uid, oid) is not None
        assert store.get_order_by_id(999, oid) is None

    def test_cancel_order_user_scoped(self, store):
        uid = _user(store)
        oid = store.create_order(
            {
                "user_id": uid,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "LIMIT",
                "price": 90000.0,
                "qty": 0.01,
                "leverage": 10,
                "tp": None,
                "sl": None,
            }
        )
        assert store.cancel_order(999, oid) is False
        assert store.cancel_order(uid, oid) is True
        row = store.get_order_by_id(uid, oid)
        assert row["status"] == "CANCELLED"

    def test_fill_order(self, store):
        uid = _user(store)
        oid = store.create_order(
            {
                "user_id": uid,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "LIMIT",
                "price": 90000.0,
                "qty": 0.01,
                "leverage": 10,
                "tp": None,
                "sl": None,
            }
        )
        store.fill_order(uid, oid, 90000.0)
        row = store.get_order_by_id(uid, oid)
        assert row["status"] == "FILLED"
        assert row["filled_at"] is not None


class TestPositions:
    def test_insert_and_get_position_user_scoped(self, store):
        uid = _user(store)
        pid = store.insert_position(
            {
                "user_id": uid,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "entry": 90000.0,
                "qty": 0.01,
                "leverage": 10,
                "margin": 90.0,
                "liq_price": 81455.0,
                "tp": 95000.0,
                "sl": None,
            }
        )
        rows = store.get_positions_futures(uid)
        assert len(rows) == 1
        assert rows[0]["id"] == pid
        assert rows[0]["status"] == "OPEN"
        assert rows[0]["side"] == "LONG"

    def test_get_positions_other_user_empty(self, store):
        uid_a = _user(store, "alice")
        uid_b = _user(store, "bob")
        store.insert_position(
            {
                "user_id": uid_a,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "entry": 90000.0,
                "qty": 0.01,
                "leverage": 10,
                "margin": 90.0,
                "liq_price": 81455.0,
                "tp": None,
                "sl": None,
            }
        )
        assert store.get_positions_futures(uid_b) == []

    def test_get_position_by_id_requires_user(self, store):
        uid = _user(store)
        pid = store.insert_position(
            {
                "user_id": uid,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "entry": 90000.0,
                "qty": 0.01,
                "leverage": 10,
                "margin": 90.0,
                "liq_price": 81455.0,
                "tp": None,
                "sl": None,
            }
        )
        assert store.get_position_by_id(uid, pid) is not None
        assert store.get_position_by_id(999, pid) is None

    def test_close_position_sets_pnl_and_reason(self, store):
        uid = _user(store)
        pid = store.insert_position(
            {
                "user_id": uid,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "entry": 90000.0,
                "qty": 0.01,
                "leverage": 10,
                "margin": 90.0,
                "liq_price": 81455.0,
                "tp": None,
                "sl": None,
            }
        )
        store.close_position_futures(uid, pid, exit_price=91000.0, pnl=10.0, reason="MANUAL")
        row = store.get_position_by_id(uid, pid)
        assert row["status"] == "CLOSED"
        assert row["pnl"] == 10.0
        assert row["exit_price"] == 91000.0
        assert row["close_reason"] == "MANUAL"
        assert row["closed_at"] is not None

    def test_close_position_other_user_noop(self, store):
        uid_a = _user(store, "alice")
        uid_b = _user(store, "bob")
        pid = store.insert_position(
            {
                "user_id": uid_a,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "entry": 90000.0,
                "qty": 0.01,
                "leverage": 10,
                "margin": 90.0,
                "liq_price": 81455.0,
                "tp": None,
                "sl": None,
            }
        )
        assert store.close_position_futures(uid_b, pid, 91000.0, 10.0, "MANUAL") is False
        row = store.get_position_by_id(uid_a, pid)
        assert row["status"] == "OPEN"

    def test_get_closed_positions_filters(self, store):
        uid = _user(store)
        pid_open = store.insert_position(
            {
                "user_id": uid,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "entry": 90000.0,
                "qty": 0.01,
                "leverage": 10,
                "margin": 90.0,
                "liq_price": 81455.0,
                "tp": None,
                "sl": None,
            }
        )
        pid_closed = store.insert_position(
            {
                "user_id": uid,
                "symbol": "ETHUSDT",
                "side": "SHORT",
                "entry": 3000.0,
                "qty": 1.0,
                "leverage": 10,
                "margin": 300.0,
                "liq_price": 3298.5,
                "tp": None,
                "sl": None,
            }
        )
        store.close_position_futures(uid, pid_closed, 2900.0, 100.0, "TP")
        open_rows = store.get_positions_futures(uid, status="OPEN")
        closed_rows = store.get_positions_futures(uid, status="CLOSED")
        assert [p["id"] for p in open_rows] == [pid_open]
        assert [p["id"] for p in closed_rows] == [pid_closed]


class TestReset:
    def test_reset_account_closes_all_and_restores_balance(self, store):
        uid = _user(store)
        store.insert_position(
            {
                "user_id": uid,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "entry": 90000.0,
                "qty": 0.01,
                "leverage": 10,
                "margin": 90.0,
                "liq_price": 81455.0,
                "tp": None,
                "sl": None,
            }
        )
        store.create_order(
            {
                "user_id": uid,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "LIMIT",
                "price": 85000.0,
                "qty": 0.01,
                "leverage": 10,
                "tp": None,
                "sl": None,
            }
        )
        store.update_account_balance(uid, -90.0)  # margin locked
        store.reset_account(uid, exit_mark=90000.0)
        acc = store.get_account(uid)
        assert acc["balance"] == START_BALANCE
        assert acc["margin_used"] == 0.0
        assert store.get_positions_futures(uid, status="OPEN") == []
        assert store.get_positions_futures(uid, status="CLOSED") != []
        assert store.get_orders(uid, status="OPEN") == []


class TestTransaction:
    async def test_transaction_rollback_on_exception(self, store):
        uid = _user(store)
        store.update_account_balance(uid, -5000.0)
        with pytest.raises(RuntimeError):
            async with store.transaction() as cur:
                cur.execute(
                    "UPDATE futures_accounts SET balance = balance - 1000 WHERE user_id = ?",
                    [uid],
                )
                raise RuntimeError("boom")
        assert store.get_account(uid)["balance"] == 5000.0

    async def test_transaction_commit(self, store):
        uid = _user(store)
        async with store.transaction() as cur:
            cur.execute(
                "UPDATE futures_accounts SET balance = balance - 1000 WHERE user_id = ?",
                [uid],
            )
            cur.execute(
                "UPDATE futures_accounts SET balance = balance - 500 WHERE user_id = ?",
                [uid],
            )
        assert store.get_account(uid)["balance"] == 8500.0

    async def test_reset_account_atomic(self, store):
        """reset_account trong 1 transaction — rollback giữ balance nguyên."""
        uid = _user(store)
        store.insert_position(
            {
                "user_id": uid,
                "symbol": "BTCUSDT",
                "side": "LONG",
                "entry": 90000.0,
                "qty": 0.01,
                "leverage": 10,
                "margin": 90.0,
                "liq_price": 81455.0,
                "tp": None,
                "sl": None,
            }
        )
        store.update_account_balance(uid, -90.0)
        with pytest.raises(RuntimeError):
            async with store.transaction() as cur:
                store.reset_account(uid, exit_mark=90000.0, cur=cur)
                raise RuntimeError("boom")
        assert store.get_account(uid)["balance"] == 9910.0
        assert len(store.get_positions_futures(uid, status="OPEN")) == 1
