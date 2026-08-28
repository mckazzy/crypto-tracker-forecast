"""Tests cho forecast compare + history + retrain endpoints."""
from datetime import UTC, datetime, timedelta

from app.forecast.schema import Signal, SignalDirection


def seed_klines(client, symbol="BTCUSDT", tf="4h", n=100):
    """Insert n synthetic klines via store để forecast có data."""
    from app.api.routes import get_store

    store = get_store()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    step = timedelta(hours=4)
    rows = []
    for i in range(n):
        ot = base + i * step
        rows.append(
            {
                "open_time": ot,
                "close_time": ot + step - timedelta(milliseconds=1),
                "symbol": symbol,
                "timeframe": tf,
                "open": 40000.0 + i,
                "high": 40100.0 + i,
                "low": 39900.0 + i,
                "close": 40050.0 + i,
                "volume": 100.0,
                "close_volume": 50.0,
                "trades": 1000,
                "taker_buy_base": 60.0,
            }
        )
    store.upsert_klines(rows)


def test_compare_returns_ai_and_offline(client, monkeypatch):
    seed_klines(client)

    # giả lập AI provider (tránh gọi OpenRouter thật)
    class FakeAI:
        name = "ai"

        def forecast(self, ctx):
            return Signal(
                symbol=ctx.symbol, timeframe=ctx.timeframe,
                direction=SignalDirection.LONG, probability=0.63,
                entry=40050.0, take_profit=[41000.0], stop_loss=39500.0,
                model="ai",
            )

    # đăng ký AI + model provider giả (offline)
    from app.forecast.registry import registry

    registry._entries.clear()
    registry.register(FakeAI())

    from app.models.provider import ModelProvider

    class FakeModelProvider(ModelProvider):
        def forecast(self, ctx):
            return Signal(
                symbol=ctx.symbol, timeframe=ctx.timeframe,
                direction=SignalDirection.SHORT, probability=0.42,
                entry=40050.0, model=self.name,
            )

    registry.register(FakeModelProvider("intraday_lgbm@BTCUSDT@4h"))

    resp = client.get("/api/forecast/compare/BTCUSDT/4h")
    assert resp.status_code == 200
    body = resp.json()
    assert "ai" in body["results"]
    assert body["results"]["ai"]["direction"] == "LONG"
    assert "intraday_lgbm@BTCUSDT@4h" in body["results"]
    assert body["results"]["intraday_lgbm@BTCUSDT@4h"]["direction"] == "SHORT"


def test_history_lists_forecasts_with_valid_until(client, monkeypatch):
    seed_klines(client)

    from app.forecast.registry import registry
    from app.forecast.schema import Signal, SignalDirection

    class FakeAI:
        name = "ai"

        def forecast(self, ctx):
            return Signal(
                symbol=ctx.symbol, timeframe=ctx.timeframe,
                direction=SignalDirection.LONG, probability=0.6,
                entry=40050.0, model="ai",
            )

    registry._entries.clear()
    registry.register(FakeAI())
    client.get("/api/forecast/compare/BTCUSDT/4h")

    resp = client.get("/api/forecast/history?symbol=BTCUSDT&timeframe=4h")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["forecasts"]) >= 1
    f = body["forecasts"][0]
    # provider có thể là ai hoặc offline model (tùy model file tồn tại) — chỉ check contract
    assert f["provider"]
    assert f["valid_until"] is not None
    assert f["outcome"] is None


def test_retrain_returns_message_when_not_enough_outcomes(client):
    resp = client.post("/api/forecast/retrain?symbol=BTCUSDT&timeframe=4h")
    assert resp.status_code == 200
    body = resp.json()
    assert body["retrained"] is False
    assert "outcomes" in body["message"].lower() or "chưa đủ" in body["message"].lower()


def test_create_user_forecast(client):
    seed_klines(client, symbol="BTCUSDT", tf="4h")
    payload = {
        "symbol": "BTCUSDT",
        "timeframe": "4h",
        "direction": "LONG",
        "entry": 40100.0,
        "take_profit": [42000.0],
        "stop_loss": 39500.0,
        "probability": 0.85,
    }
    resp = client.post("/api/forecast/user", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "user"
    assert data["signal"]["direction"] == "LONG"
    assert data["signal"]["rr_ratio"] == 3.17  # (42000 - 40100) / (40100 - 39500) = 1900 / 600 = 3.17
    assert data["valid_until"] is not None

    # Check that it appears in /forecasts with source 'User'
    list_resp = client.get("/api/forecast/forecasts?symbol=BTCUSDT&timeframe=4h")
    assert list_resp.status_code == 200
    forecasts = list_resp.json()["forecasts"]
    user_fc = [f for f in forecasts if f["id"] == data["id"]]
    assert len(user_fc) == 1
    assert user_fc[0]["source"] == "User"

