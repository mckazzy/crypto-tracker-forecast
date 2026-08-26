import pytest
from fastapi.testclient import TestClient

from app.alerts.engine import AlertEngine
from app.storage.duckdb_store import DuckDBStore


@pytest.fixture
def store(tmp_duckdb) -> DuckDBStore:
    return DuckDBStore(tmp_duckdb)


@pytest.fixture
def client(tmp_duckdb, monkeypatch):
    from app.main import app
    from app.storage.duckdb_store import DuckDBStore

    store = DuckDBStore(tmp_duckdb)
    monkeypatch.setattr("app.api.routes.get_store", lambda: store)
    app.state.ws_worker_disabled = True
    with TestClient(app) as c:
        yield c


def signal(direction="LONG", entry=67200.0, sl=66100.0):
    return {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "direction": direction,
        "entry": entry,
        "take_profit": [68500.0],
        "stop_loss": sl,
        "model": "test",
    }


class TestAlertEngine:
    def test_first_signal_alerts(self, store):
        engine = AlertEngine(store)
        assert engine.should_alert(signal()) is True

    def test_same_signal_dedup(self, store):
        engine = AlertEngine(store)
        engine.dispatch(signal())
        assert engine.should_alert(signal()) is False

    def test_direction_change_alerts(self, store):
        engine = AlertEngine(store)
        engine.dispatch(signal("LONG"))
        assert engine.should_alert(signal("SHORT")) is True

    def test_entry_change_alerts(self, store):
        engine = AlertEngine(store)
        engine.dispatch(signal(entry=67200.0))
        assert engine.should_alert(signal(entry=70000.0)) is True

    def test_dispatch_saves_history(self, store):
        engine = AlertEngine(store)
        record = engine.dispatch(signal())
        assert record["channel"] == "webhook"  # telegram chưa cấu hình
        assert record["status"] == "sent"
        alerts = store.get_alerts()
        assert len(alerts) == 1
        assert alerts[0]["symbol"] == "BTCUSDT"


class TestAlertsApi:
    def test_list_empty(self, client):
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        assert resp.json()["alerts"] == []

    def test_create_alert(self, client):
        resp = client.post(
            "/api/alerts",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "LONG",
                "entry": 67200.0,
                "take_profit": [68500.0],
                "stop_loss": 66100.0,
                "model": "test",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["alert"]["channel"] == "webhook"

    def test_create_invalid_direction(self, client):
        resp = client.post(
            "/api/alerts",
            json={"symbol": "BTCUSDT", "timeframe": "1h", "direction": "X"},
        )
        assert resp.status_code == 400
