import asyncio

import pytest


@pytest.fixture
def engine_client(client, monkeypatch):
    """Client có engine futures thật (queue nội bộ, không cần relay/network)."""
    from app.main import app
    from app.trading.futures_engine import FuturesEngine

    from app.api.routes import get_store

    store = get_store()
    engine = FuturesEngine(store, symbol_list=["BTCUSDT", "ETHUSDT"])
    engine.last_mark["BTCUSDT"] = 50000.0
    engine.last_mark["ETHUSDT"] = 3000.0
    engine.set_queue(asyncio.Queue())
    app.state.futures_engine = engine
    store._engine = engine
    monkeypatch.setattr("app.main._futures_queue", asyncio.Queue())
    yield client
    # cleanup: tránh state leak sang test khác (store cũ connection đã đóng)
    del app.state.futures_engine
    store._engine = None


def _register(client, username="alice", password="password123"):
    r = client.post("/api/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestAuthGuard:
    def test_register_login_flow(self, client):
        token = _register(client)
        assert token
        r = client.post(
            "/api/auth/login", json={"username": "alice", "password": "password123"}
        )
        assert r.status_code == 200
        assert r.json()["token"]

    def test_login_wrong_password_401_generic(self, client):
        _register(client)
        r = client.post(
            "/api/auth/login", json={"username": "alice", "password": "wrongpass1"}
        )
        assert r.status_code == 401
        assert "invalid credentials" in r.json()["detail"]

    def test_login_unknown_user_401(self, client):
        r = client.post(
            "/api/auth/login", json={"username": "nobody", "password": "whatever1"}
        )
        assert r.status_code == 401

    def test_duplicate_username_400(self, client):
        _register(client)
        r = client.post(
            "/api/auth/register", json={"username": "alice", "password": "password123"}
        )
        assert r.status_code == 400
        assert "already exists" in r.json()["detail"]

    def test_short_password_422(self, client):
        r = client.post("/api/auth/register", json={"username": "bob", "password": "short"})
        assert r.status_code == 422

    def test_futures_requires_token(self, client):
        assert client.get("/api/futures/account").status_code == 401
        assert client.post("/api/futures/orders", json={}).status_code == 401
        assert client.get("/api/futures/positions").status_code == 401


class TestAccount:
    def test_new_account_10000(self, client):
        token = _register(client)
        r = client.get("/api/futures/account", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["balance"] == 10000.0
        assert r.json()["margin_used"] == 0.0

    def test_reset_restores_balance(self, engine_client):
        client = engine_client
        token = _register(client)
        h = _auth(token)
        # mở 1 position bằng market order (Phase 3: engine fill ngay, trừ margin)
        r = client.post(
            "/api/futures/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "MARKET",
                "notional_usdt": 1000,
                "leverage": 10,
                "tp": None,
                "sl": None,
            },
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "FILLED"
        acc = client.get("/api/futures/account", headers=h).json()
        assert acc["margin_used"] > 0
        r = client.post("/api/futures/account/reset", headers=h)
        assert r.status_code == 200
        assert r.json()["balance"] == 10000.0
        acc = client.get("/api/futures/account", headers=h).json()
        assert acc["balance"] == 10000.0
        assert acc["margin_used"] == 0.0


class TestOrders:
    def test_place_market_and_limit(self, client):
        token = _register(client)
        h = _auth(token)
        r = client.post(
            "/api/futures/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "SHORT",
                "type": "LIMIT",
                "notional_usdt": 500,
                "leverage": 20,
                "price": 120000.0,
                "tp": None,
                "sl": None,
            },
            headers=h,
        )
        assert r.status_code == 200
        oid = r.json()["id"]
        orders = client.get("/api/futures/orders", headers=h).json()["orders"]
        assert len(orders) == 1
        assert orders[0]["status"] == "OPEN"
        assert orders[0]["type"] == "LIMIT"
        assert orders[0]["price"] == 120000.0

    def test_invalid_symbol_rejected(self, client):
        token = _register(client)
        h = _auth(token)
        r = client.post(
            "/api/futures/orders",
            json={
                "symbol": "DOGEUSDT",
                "side": "LONG",
                "type": "MARKET",
                "notional_usdt": 100,
                "leverage": 10,
            },
            headers=h,
        )
        assert r.status_code == 400

    def test_limit_requires_price(self, client):
        token = _register(client)
        h = _auth(token)
        r = client.post(
            "/api/futures/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "LIMIT",
                "notional_usdt": 100,
                "leverage": 10,
            },
            headers=h,
        )
        assert r.status_code == 400

    def test_cancel_order(self, client):
        token = _register(client)
        h = _auth(token)
        r = client.post(
            "/api/futures/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "LIMIT",
                "notional_usdt": 100,
                "leverage": 10,
                "price": 30000.0,
            },
            headers=h,
        )
        oid = r.json()["id"]
        assert client.delete(f"/api/futures/orders/{oid}", headers=h).status_code == 200
        assert client.delete(f"/api/futures/orders/{oid}", headers=h).status_code == 404


class TestIdor:
    def test_user_cannot_touch_others(self, client):
        token_a = _register(client, "alice")
        token_b = _register(client, "bob")
        ha, hb = _auth(token_a), _auth(token_b)
        r = client.post(
            "/api/futures/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "LIMIT",
                "notional_usdt": 100,
                "leverage": 10,
                "price": 30000.0,
            },
            headers=ha,
        )
        oid = r.json()["id"]
        assert client.delete(f"/api/futures/orders/{oid}", headers=hb).status_code == 404
        assert client.get("/api/futures/positions", headers=hb).json()["positions"] == []

    def test_client_supplied_mark_ignored(self, engine_client):
        """Order payload không có price/mark cho MARKET — giá từ engine server."""
        client = engine_client
        token = _register(client)
        h = _auth(token)
        r = client.post(
            "/api/futures/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "MARKET",
                "notional_usdt": 1000,
                "leverage": 10,
            },
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "FILLED"
        # entry = engine mark (50000), không phải giá client gửi
        pos = client.get("/api/futures/positions", headers=h).json()["positions"][0]
        assert pos["entry"] == 50000.0


class TestMark:
    def test_mark_endpoint(self, client):
        token = _register(client)
        r = client.get("/api/futures/mark/BTCUSDT", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["symbol"] == "BTCUSDT"
        assert body["mark"] > 0

    def test_mark_invalid_symbol(self, client):
        token = _register(client)
        assert client.get("/api/futures/mark/DOGEUSDT", headers=_auth(token)).status_code == 400


class TestFuturesKlines:
    """Endpoint public market data — seed chart futures, KHÔNG cần auth."""

    RAW_ROW = [1700000000000, "59900", "60100", "59800", "60000", "100.5", 1700000005999, "99.5", 100, "50.5", "49.5", "0"]

    def test_klines_public_no_auth(self, client, monkeypatch):
        async def fake_fetch(symbol, timeframe, limit):
            return [self.RAW_ROW, [1700000006000, "60000", "60200", "59900", "60100", "120.5", 1700000011999, "119.5", 120, "60.5", "59.5", "0"]]

        monkeypatch.setattr("app.api.futures_routes._fetch_upstream_klines", fake_fetch)
        # KHÔNG auth header — public market data
        r = client.get("/api/futures/klines/BTCUSDT")
        assert r.status_code == 200
        body = r.json()
        assert body["symbol"] == "BTCUSDT"
        assert body["timeframe"] == "1m"
        assert len(body["klines"]) == 2
        k = body["klines"][0]
        assert k["type"] == "kline"
        assert k["open_time"] == 1700000000000
        assert k["close_time"] == 1700000005999
        assert k["open"] == 59900.0
        assert k["high"] == 60100.0
        assert k["low"] == 59800.0
        assert k["close"] == 60000.0
        assert k["volume"] == 100.5
        # close_time (2023-11) < now → is_closed True
        assert k["is_closed"] is True

    def test_klines_invalid_symbol(self, client):
        assert client.get("/api/futures/klines/DOGEUSDT").status_code == 400

    def test_klines_bad_timeframe(self, client):
        assert client.get("/api/futures/klines/BTCUSDT?timeframe=3m").status_code == 400

    def test_klines_upstream_failure_502(self, client, monkeypatch):
        async def fake_fetch(symbol, timeframe, limit):
            return None

        monkeypatch.setattr("app.api.futures_routes._fetch_upstream_klines", fake_fetch)
        r = client.get("/api/futures/klines/BTCUSDT")
        assert r.status_code == 502


class TestEngineFlow:
    """Phase 3: market order fill qua engine, close tính pnl bằng mark server."""

    def test_market_order_creates_position(self, engine_client):
        client = engine_client
        token = _register(client)
        h = _auth(token)
        r = client.post(
            "/api/futures/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "MARKET",
                "notional_usdt": 1000,
                "leverage": 10,
            },
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "FILLED"
        positions = client.get("/api/futures/positions", headers=h).json()["positions"]
        assert len(positions) == 1
        p = positions[0]
        assert p["status"] == "OPEN"
        assert p["side"] == "LONG"
        assert p["entry"] == 50000.0
        acc = client.get("/api/futures/account", headers=h).json()
        assert acc["margin_used"] == pytest.approx(p["margin"])
        assert acc["balance"] == pytest.approx(10000.0 - p["margin"])

    def test_close_position_uses_engine_mark(self, engine_client):
        client = engine_client
        token = _register(client)
        h = _auth(token)
        client.post(
            "/api/futures/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "MARKET",
                "notional_usdt": 1000,
                "leverage": 10,
            },
            headers=h,
        )
        pid = client.get("/api/futures/positions", headers=h).json()["positions"][0]["id"]
        mark_before = client.get("/api/futures/mark/BTCUSDT", headers=h).json()["mark"]
        r = client.post(f"/api/futures/positions/{pid}/close", headers=h, json={})
        assert r.status_code == 200
        body = r.json()
        assert body["exit_price"] == mark_before
        assert "pnl" in body
        acc = client.get("/api/futures/account", headers=h).json()
        assert acc["margin_used"] == 0.0

    def test_limit_order_stays_open_then_fills(self, engine_client):
        client = engine_client
        token = _register(client)
        h = _auth(token)
        r = client.post(
            "/api/futures/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "LONG",
                "type": "LIMIT",
                "notional_usdt": 1000,
                "leverage": 10,
                "price": 1000000.0,  # giá rất cao — chưa cross
            },
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "OPEN"
        assert client.get("/api/futures/positions", headers=h).json()["positions"] == []
        # engine nhận tick mark thấp hơn → limit fill
        engine = _get_engine()
        asyncio.run(engine.on_mark_price("BTCUSDT", 30000.0))
        positions = client.get("/api/futures/positions", headers=h).json()["positions"]
        assert len(positions) == 1


def _get_engine():
    from app.main import app

    return getattr(app.state, "futures_engine", None)
