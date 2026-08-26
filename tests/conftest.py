from datetime import UTC, datetime, timedelta

import duckdb
import pytest


@pytest.fixture
def sample_klines() -> list[dict]:
    """100 synthetic deterministic 1h BTCUSDT candles, tz-aware UTC."""
    candles = []
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(100):
        open_time = base + timedelta(hours=i)
        close_time = open_time + timedelta(hours=1) - timedelta(milliseconds=1)
        o = 40000.0 + i
        h = o + 50.0
        low = o - 40.0
        c = o + 10.0
        candles.append(
            {
                "open_time": open_time,
                "close_time": close_time,
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "open": o,
                "high": h,
                "low": low,
                "close": c,
                "volume": 100.0 + i,
                "close_volume": 200.0 + i,
                "trades": 1000 + i,
                "taker_buy_base": 60.0 + i,
            }
        )
    return candles


@pytest.fixture
def tmp_duckdb(tmp_path):
    """DuckDB connection with TimeZone='UTC' set."""
    conn = duckdb.connect(str(tmp_path / "test.duckdb"))
    conn.execute("SET TimeZone='UTC'")
    yield conn
    conn.close()
