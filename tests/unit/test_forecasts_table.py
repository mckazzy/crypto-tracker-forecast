from datetime import UTC, datetime, timedelta

import pytest

from app.storage.duckdb_store import DuckDBStore


@pytest.fixture
def store(tmp_duckdb) -> DuckDBStore:
    return DuckDBStore(tmp_duckdb)


class TestForecastsTable:
    def test_save_and_get(self, store):
        signal = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "direction": "LONG",
            "probability": 0.63,
            "model": "ai",
            "status": "ok",
            "token_cost": 120,
        }
        store.save_forecast("BTCUSDT", "1h", "ai", signal)
        rows = store.get_forecasts()
        assert len(rows) == 1
        assert rows[0]["provider"] == "ai"
        assert rows[0]["signal"]["direction"] == "LONG"
        assert rows[0]["token_cost"] == 120
        assert rows[0]["created_at"] is not None

    def test_filter_by_symbol_timeframe(self, store):
        base = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "direction": "LONG",
            "probability": 0.5,
            "model": "x",
            "status": "ok",
        }
        store.save_forecast("BTCUSDT", "1h", "a", base)
        store.save_forecast("BTCUSDT", "4h", "a", base)
        store.save_forecast("ETHUSDT", "1h", "a", base)
        assert len(store.get_forecasts(symbol="BTCUSDT")) == 2
        assert len(store.get_forecasts(timeframe="1h")) == 2
        assert len(store.get_forecasts(symbol="BTCUSDT", timeframe="4h")) == 1

    def test_newest_first(self, store):
        base = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "direction": "LONG",
            "probability": 0.5,
            "model": "x",
            "status": "ok",
        }
        store.save_forecast("BTCUSDT", "1h", "a", base)
        store.save_forecast("BTCUSDT", "1h", "b", base)
        rows = store.get_forecasts(symbol="BTCUSDT", timeframe="1h")
        assert rows[0]["provider"] == "b"  # newest first
