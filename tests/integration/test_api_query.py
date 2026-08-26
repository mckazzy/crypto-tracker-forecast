import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_duckdb, monkeypatch):
    from app.storage.duckdb_store import DuckDBStore

    store = DuckDBStore(tmp_duckdb)
    monkeypatch.setattr("app.api.routes.get_store", lambda: store)
    app.state.ws_worker_disabled = True
    with TestClient(app) as c:
        yield c


def seed(store, symbol="BTCUSDT", tf="1h", n=10, start_ms=1_760_000_000_000):
    from datetime import UTC, datetime, timedelta

    rows = []
    for i in range(n):
        ot = datetime.fromtimestamp((start_ms + i * 3_600_000) / 1000, tz=UTC)
        rows.append(
            {
                "open_time": ot,
                "close_time": ot + timedelta(hours=1) - timedelta(milliseconds=1),
                "symbol": symbol,
                "timeframe": tf,
                "open": 100.0 + i,
                "high": 110.0 + i,
                "low": 95.0 + i,
                "close": 105.0 + i,
                "volume": 10.0,
                "close_volume": 5.0,
                "trades": 100,
                "taker_buy_base": 4.0,
            }
        )
    store.upsert_klines(rows)


class TestKlinesQueryValidation:
    def test_rejects_unknown_symbol(self, client):
        resp = client.get("/api/klines", params={"symbol": "FOOBAR", "timeframe": "1h"})
        assert resp.status_code == 404

    def test_rejects_invalid_timeframe(self, client):
        resp = client.get("/api/klines", params={"symbol": "BTCUSDT", "timeframe": "2h"})
        assert resp.status_code == 400

    def test_rejects_limit_over_max(self, client):
        resp = client.get(
            "/api/klines",
            params={"symbol": "BTCUSDT", "timeframe": "1h", "limit": 99999},
        )
        assert resp.status_code == 422

    def test_rejects_start_after_end(self, client):
        store = __import__("app.api.routes", fromlist=["get_store"]).get_store()
        seed(store)
        resp = client.get(
            "/api/klines",
            params={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "start_time": 1_760_100_000_000,
                "end_time": 1_760_000_000_000,
            },
        )
        assert resp.status_code == 400

    def test_range_filter(self, client):
        from app.api.routes import get_store

        seed(get_store())
        resp = client.get(
            "/api/klines",
            params={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "start_time": 1_760_000_000_000 + 3_600_000 * 2,
                "end_time": 1_760_000_000_000 + 3_600_000 * 5,
            },
        )
        body = resp.json()
        assert [d["open_time"] for d in body["data"]] == [
            1_760_000_000_000 + 3_600_000 * i for i in (2, 3, 4)
        ]

    def test_symbol_case_insensitive(self, client):
        from app.api.routes import get_store

        seed(get_store())
        resp = client.get("/api/klines", params={"symbol": "btcusdt", "timeframe": "1H"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 10


class TestSymbolsEndpoint:
    def test_list_symbols_with_coverage(self, client):
        from app.api.routes import get_store

        seed(get_store())
        resp = client.get("/api/symbols")
        assert resp.status_code == 200
        body = resp.json()
        entry = next(s for s in body["symbols"] if s["symbol"] == "BTCUSDT")
        assert any(tf["count"] > 0 for tf in entry["timeframes"])


class TestHealthExtended:
    def test_health_reports_db_stats(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "db" in body
