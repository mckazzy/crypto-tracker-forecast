import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_duckdb, monkeypatch):
    """TestClient with API store pointed at tmp DuckDB and ws worker disabled."""
    from app.storage.duckdb_store import DuckDBStore

    store = DuckDBStore(tmp_duckdb)
    monkeypatch.setattr("app.api.routes.get_store", lambda: store)

    app.state.ws_worker_disabled = True
    with TestClient(app) as c:
        yield c


def test_klines_validation_bad_timeframe(client):
    resp = client.get("/api/klines", params={"symbol": "BTCUSDT", "timeframe": "2h"})
    assert resp.status_code == 400


def test_klines_empty(client):
    resp = client.get("/api/klines", params={"symbol": "BTCUSDT", "timeframe": "1h"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["data"] == []


def test_klines_returns_stored_data(client):
    from datetime import UTC, datetime, timedelta

    from tests.integration.test_backfill import raw_row

    # insert via store directly
    store = client.app.extra.get("_store") if False else None  # noqa: F841
    from app.api.routes import get_store

    store = get_store()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(5):
        ot = t0 + timedelta(hours=i)
        r = dict(
            zip(
                [
                    "open_time",
                    "close_time",
                    "symbol",
                    "timeframe",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_volume",
                    "trades",
                    "taker_buy_base",
                ],
                [ot, ot + timedelta(hours=1), "BTCUSDT", "1h", 100.0, 110.0, 95.0, 105.0, 10.0, 5.0, 100, 4.0],
            )
        )
        rows.append(r)
    store.upsert_klines(rows)

    resp = client.get("/api/klines", params={"symbol": "BTCUSDT", "timeframe": "1h"})
    body = resp.json()
    assert body["count"] == 5
    first = body["data"][0]
    assert first["open_time"] == int(t0.timestamp() * 1000)
    assert first["close"] == 105.0
