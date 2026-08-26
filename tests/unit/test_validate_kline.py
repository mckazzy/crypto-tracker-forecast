from datetime import UTC, datetime, timedelta

import pytest

from app.storage.duckdb_store import validate_kline


def valid_kline(open_time: datetime) -> dict:
    return {
        "open_time": open_time,
        "close_time": open_time + timedelta(hours=1) - timedelta(milliseconds=1),
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "open": 40000.0,
        "high": 40100.0,
        "low": 39900.0,
        "close": 40050.0,
        "volume": 100.0,
        "close_volume": 60.0,
        "trades": 1500,
        "taker_buy_base": 55.0,
    }


class TestValidateKline:
    def test_valid(self):
        assert validate_kline(valid_kline(datetime(2026, 1, 1, tzinfo=UTC))) is None

    def test_close_below_low_invalid(self):
        k = valid_kline(datetime(2026, 1, 1, tzinfo=UTC))
        k["close"] = 39000.0
        reason = validate_kline(k)
        assert reason is not None and "close" in reason

    def test_high_below_low_invalid(self):
        k = valid_kline(datetime(2026, 1, 1, tzinfo=UTC))
        k["high"] = 39500.0
        k["low"] = 39900.0
        assert validate_kline(k) is not None

    def test_negative_price_invalid(self):
        k = valid_kline(datetime(2026, 1, 1, tzinfo=UTC))
        k["low"] = -1.0
        assert validate_kline(k) is not None

    def test_negative_volume_invalid(self):
        k = valid_kline(datetime(2026, 1, 1, tzinfo=UTC))
        k["volume"] = -0.5
        assert validate_kline(k) is not None

    def test_nan_invalid(self):
        k = valid_kline(datetime(2026, 1, 1, tzinfo=UTC))
        k["close"] = float("nan")
        assert validate_kline(k) is not None

    def test_negative_trades_invalid(self):
        k = valid_kline(datetime(2026, 1, 1, tzinfo=UTC))
        k["trades"] = -10
        assert validate_kline(k) is not None

    def test_open_time_after_close_time_invalid(self):
        k = valid_kline(datetime(2026, 1, 1, tzinfo=UTC))
        k["close_time"] = k["open_time"] - timedelta(hours=1)
        assert validate_kline(k) is not None
