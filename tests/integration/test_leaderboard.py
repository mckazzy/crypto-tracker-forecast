import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.forecast.walkforward import evaluate_walkforward, fit_predict_baseline


def make_df(n=300, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    closes = 40000 + np.cumsum(rng.normal(0, 50, n))
    return pd.DataFrame(
        {
            "close": closes,
            "open": closes,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "volume": 100.0,
            "taker_buy_base": rng.uniform(30, 70, n),
        },
        index=idx,
    )


@pytest.fixture
def client(tmp_duckdb, monkeypatch):
    from app.main import app
    from app.storage.duckdb_store import DuckDBStore

    store = DuckDBStore(tmp_duckdb)
    monkeypatch.setattr("app.api.routes.get_store", lambda: store)
    app.state.ws_worker_disabled = True
    with TestClient(app) as c:
        yield c


def seed_forecasts(store, n=3):
    for i in range(n):
        store.save_forecast(
            "BTCUSDT",
            "1h",
            f"p{i}",
            {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "LONG" if i % 2 == 0 else "SHORT",
                "probability": 0.5 + i * 0.05,
                "model": f"p{i}",
                "status": "ok",
                "token_cost": i * 100,
            },
        )


class TestLeaderboardEndpoint:
    def test_empty_no_forecasts(self, client):
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        assert resp.json()["providers"] == []

    def test_returns_providers_with_metrics(self, client):
        from app.api.routes import get_store

        seed_forecasts(get_store())
        resp = client.get("/api/leaderboard?symbol=BTCUSDT&timeframe=1h")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["providers"]) == 3
        p = body["providers"][0]
        assert "name" in p
        assert "signals" in p
        assert "total_token_cost" in p
        assert p["signals"] >= 1

    def test_filters_by_symbol(self, client):
        from app.api.routes import get_store

        store = get_store()
        seed_forecasts(store)
        store.save_forecast(
            "ETHUSDT",
            "1h",
            "p0",
            {
                "symbol": "ETHUSDT",
                "timeframe": "1h",
                "direction": "LONG",
                "probability": 0.5,
                "model": "p0",
                "status": "ok",
            },
        )
        resp = client.get("/api/leaderboard?symbol=ETHUSDT")
        body = resp.json()
        assert len(body["providers"]) == 1
        assert body["providers"][0]["name"] == "p0"


class TestWalkforwardIntegration:
    def test_evaluate_walkforward_on_real_features(self):
        from app.forecast.features import build_features

        df = build_features(make_df(300))
        res = evaluate_walkforward(df, fit_predict_baseline, train_size=60, test_size=20)
        assert res["n"] > 0
