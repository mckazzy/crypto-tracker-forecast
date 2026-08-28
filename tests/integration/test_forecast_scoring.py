"""Tests cho run forecast, scoring, analytics, export CSV."""
from datetime import UTC, datetime, timedelta

from app.forecast.schema import Signal, SignalDirection


def seed_klines(client, symbol="BTCUSDT", tf="4h", n=100, base=None):
    from app.api.routes import get_store

    store = get_store()
    base = base or datetime(2026, 1, 1, tzinfo=UTC)
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


def _register_fake_ai():
    from app.forecast.registry import registry

    class FakeAI:
        name = "ai"

        def forecast(self, ctx):
            return Signal(
                symbol=ctx.symbol, timeframe=ctx.timeframe,
                direction=SignalDirection.LONG, probability=0.63,
                entry=40050.0, take_profit=[41000.0], stop_loss=39500.0,
                model="ai",
            )

    registry._entries.clear()
    registry.register(FakeAI())
    return registry


def _make_expired_forecast(store, symbol="BTCUSDT", tf="4h", provider="ai", direction="LONG"):
    """Tạo forecast đã quá hạn (valid_until trong quá khứ)."""
    import json

    from datetime import UTC, datetime, timedelta

    past = datetime.now(UTC) - timedelta(hours=1)
    sig = {
        "direction": direction,
        "probability": 0.6,
        "entry": 40050.0,
        "take_profit": [41000.0],
        "stop_loss": 39500.0,
        "model": provider,
        "valid_until": past.isoformat(),
    }
    return store.save_forecast(symbol, tf, provider, sig)


def test_run_forecast_ai(client):
    seed_klines(client)
    _register_fake_ai()

    resp = client.post("/api/forecast/run", params={"provider": "ai", "symbol": "BTCUSDT", "timeframe": "4h"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] > 0
    assert body["provider"] == "ai"
    assert body["valid_until"] is not None
    assert body["signal"]["direction"] == "LONG"


def test_run_forecast_unknown_provider(client):
    resp = client.post("/api/forecast/run", params={"provider": "nope", "symbol": "BTCUSDT", "timeframe": "4h"})
    assert resp.status_code == 404


def test_run_forecast_local_resolves_offline(client, monkeypatch):
    """provider=local phải resolve thành intraday_lgbm@SYMBOL@TF."""
    seed_klines(client)

    from app.forecast.registry import registry
    from app.forecast.schema import Signal, SignalDirection

    class FakeLocal:
        name = "intraday_lgbm@BTCUSDT@4h"

        def forecast(self, ctx):
            return Signal(
                symbol=ctx.symbol, timeframe=ctx.timeframe,
                direction=SignalDirection.SHORT, probability=0.41,
                entry=40050.0, model=self.name,
            )

    registry._entries.clear()
    registry.register(FakeLocal())

    resp = client.post("/api/forecast/run", params={"provider": "local", "symbol": "BTCUSDT", "timeframe": "4h"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "intraday_lgbm@BTCUSDT@4h"
    assert body["signal"]["direction"] == "SHORT"


def test_list_forecasts_with_source_and_expired(client):
    seed_klines(client)
    from app.api.routes import get_store

    store = get_store()
    _make_expired_forecast(store)

    resp = client.get("/api/forecast/forecasts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["forecasts"]) >= 1
    f = body["forecasts"][0]
    assert "id" in f
    assert f["source"] in ("AI", "Local")
    assert f["expired"] is True
    assert f["scored"] is False

def test_score_expired_forecast(client):
    seed_klines(client)
    from app.api.routes import get_store

    store = get_store()
    fid = _make_expired_forecast(store)
    # thêm klines quanh thời điểm chốt (quá khứ) để có giá kết thúc
    base = datetime.now(UTC) - timedelta(hours=2)
    seed_klines(client, base=base - timedelta(days=60))

    resp = client.post(f"/api/forecast/forecasts/{fid}/score")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scored"] is True
    assert body["score"] is not None
    assert body["exit_price"] is not None


def test_analytics_shape(client):
    seed_klines(client)
    from app.api.routes import get_store

    store = get_store()
    _make_expired_forecast(store, direction="LONG")
    _make_expired_forecast(store, direction="SHORT")

    resp = client.get("/api/forecast/forecasts/analytics")
    assert resp.status_code == 200
    body = resp.json()
    assert "direction_split" in body
    assert "by_source" in body
    assert "avg_accuracy" in body


def test_export_csv(client):
    seed_klines(client)
    from app.api.routes import get_store

    store = get_store()
    _make_expired_forecast(store)

    resp = client.get("/api/forecast/forecasts/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    text = resp.text
    assert "id,symbol,timeframe" in text
    assert "BTCUSDT" in text


def test_score_all_skips_future_and_scores_expired(client):
    seed_klines(client)
    from app.api.routes import get_store

    store = get_store()
    # forecast quá hạn (valid_until quá khứ)
    _make_expired_forecast(store)
    # forecast tương lai — chưa nên chấm
    import json
    from datetime import timedelta

    future = datetime.now(UTC) + timedelta(hours=1)
    store.save_forecast(
        "BTCUSDT", "4h", "ai",
        {
            "direction": "LONG", "probability": 0.6, "entry": 40050.0,
            "take_profit": [41000.0], "stop_loss": 39500.0,
            "valid_until": future.isoformat(),
        },
    )

    resp = client.post("/api/forecast/forecasts/score-all")
    assert resp.status_code == 200
    body = resp.json()
    # expired có entry + klines đóng quanh mốc → được chấm
    assert body["scored"] >= 1
    assert body["skipped"] >= 1
