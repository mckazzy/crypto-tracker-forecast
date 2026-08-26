import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_duckdb, monkeypatch):
    from app.main import app
    from app.storage.duckdb_store import DuckDBStore

    store = DuckDBStore(tmp_duckdb)
    monkeypatch.setattr("app.api.routes.get_store", lambda: store)
    app.state.ws_worker_disabled = True
    with TestClient(app) as c:
        yield c


class TestPositionsApi:
    def test_open_and_list(self, client):
        resp = client.post(
            "/api/positions",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "LONG",
                "entry": 100.0,
                "tp": 108.0,
                "sl": 90.0,
                "model": "test",
            },
        )
        assert resp.status_code == 200
        pos_id = resp.json()["id"]

        resp = client.get("/api/positions")
        body = resp.json()
        assert len(body["positions"]) == 1
        assert body["positions"][0]["id"] == pos_id
        assert body["positions"][0]["status"] == "open"

    def test_open_invalid_direction(self, client):
        resp = client.post(
            "/api/positions",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "SIDEWAYS",
                "entry": 100.0,
                "tp": 108.0,
                "sl": 90.0,
            },
        )
        assert resp.status_code == 400

    def test_close_position(self, client):
        pos_id = client.post(
            "/api/positions",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "LONG",
                "entry": 100.0,
                "tp": 108.0,
                "sl": 90.0,
            },
        ).json()["id"]
        resp = client.post(f"/api/positions/{pos_id}/close", json={"exit_price": 110.0})
        assert resp.status_code == 200
        assert resp.json()["pnl"] > 0

    def test_close_missing_404(self, client):
        resp = client.post("/api/positions/999/close", json={"exit_price": 100.0})
        assert resp.status_code == 404

    def test_pnl_summary(self, client):
        for price in (110.0, 90.0):
            pos_id = client.post(
                "/api/positions",
                json={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "direction": "LONG",
                    "entry": 100.0,
                    "tp": 108.0,
                    "sl": 90.0,
                },
            ).json()["id"]
            client.post(f"/api/positions/{pos_id}/close", json={"exit_price": price})

        resp = client.get("/api/positions/pnl")
        body = resp.json()
        assert body["total_closed"] == 2
        assert body["win_rate"] == 0.5
        assert body["total_pnl"] < 0  # 1 win ~+9.7%, 1 lose ~-10.3% → âm
