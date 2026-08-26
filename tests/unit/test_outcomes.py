from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.storage.duckdb_store import DuckDBStore
from app.trading.outcomes import auto_resolve_outcome, user_override_allowed


@pytest.fixture
def store(tmp_duckdb) -> DuckDBStore:
    return DuckDBStore(tmp_duckdb)


@pytest.fixture
def client(tmp_duckdb, monkeypatch):
    from app.main import app
    from app.storage.duckdb_store import DuckDBStore

    store = DuckDBStore(tmp_duckdb)
    monkeypatch.setattr("app.api.routes.get_store", lambda: store)
    monkeypatch.setattr("app.config.settings.feedback_min_signals", 2)
    app.state.ws_worker_disabled = True
    with TestClient(app) as c:
        yield c


def make_candles(entries: list[tuple[int, float, float]]):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    out = []
    for dh, high, low in entries:
        ot = base + timedelta(hours=dh)
        out.append(
            {
                "open_time": ot,
                "high": high,
                "low": low,
                "close": (high + low) / 2,
                "volume": 100.0,
            }
        )
    return out


class TestAutoResolve:
    def test_tp_hit_win(self):
        candles = make_candles([(1, 110.0, 95.0)])
        outcome = auto_resolve_outcome("BTCUSDT", "1h", "LONG", 100.0, 108.0, 90.0, candles)
        assert outcome == "win"

    def test_sl_hit_lose(self):
        candles = make_candles([(1, 105.0, 88.0)])
        outcome = auto_resolve_outcome("BTCUSDT", "1h", "LONG", 100.0, 108.0, 90.0, candles)
        assert outcome == "lose"

    def test_no_barrier_none(self):
        candles = make_candles([(1, 105.0, 95.0)])
        outcome = auto_resolve_outcome("BTCUSDT", "1h", "LONG", 100.0, 108.0, 90.0, candles)
        assert outcome is None


class TestUserOverrideGuard:
    def test_below_min_not_allowed(self, store):
        assert user_override_allowed(store, min_signals=10) is False

    def test_above_min_allowed(self, store):
        for i in range(10):
            store.save_outcome(
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "direction": "LONG",
                    "outcome": "win",
                    "source": "auto",
                }
            )
        assert user_override_allowed(store, min_signals=10) is True


class TestOutcomesApi:
    def test_create_outcome(self, client):
        resp = client.post(
            "/api/outcomes",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "LONG",
                "outcome": "win",
                "entry": 100.0,
                "tp": 108.0,
                "sl": 90.0,
                "model": "test",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["trusted"] is False  # chưa đủ min_signals
        assert body["id"] > 0

    def test_create_invalid_outcome(self, client):
        resp = client.post(
            "/api/outcomes",
            json={"symbol": "BTCUSDT", "timeframe": "1h", "direction": "LONG", "outcome": "maybe"},
        )
        assert resp.status_code == 400

    def test_list_outcomes(self, client):
        client.post(
            "/api/outcomes",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "LONG",
                "outcome": "win",
            },
        )
        resp = client.get("/api/outcomes")
        assert resp.status_code == 200
        assert len(resp.json()["outcomes"]) == 1
