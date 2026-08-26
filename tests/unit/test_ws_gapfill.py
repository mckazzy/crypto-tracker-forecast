import json
from datetime import UTC, datetime, timedelta

from app.connectors.binance_rest import MS_PER_UNIT
from app.storage.duckdb_store import DuckDBStore


def kline_event(symbol="BTCUSDT", interval="1h", open_ms=None, closed=True):
    open_ms = open_ms or 1_760_000_000_000
    return {
        "e": "kline",
        "s": symbol,
        "k": {
            "t": open_ms,
            "T": open_ms + 3_600_000 - 1,
            "s": symbol,
            "i": interval,
            "o": "40000.0",
            "c": "40100.0",
            "h": "40200.0",
            "l": "39900.0",
            "v": "123.4",
            "V": "60.0",
            "n": 500,
            "x": closed,
        },
    }


def store_kline_at(store: DuckDBStore, open_ms: int, symbol="BTCUSDT", tf="1h") -> None:
    ot = datetime.fromtimestamp(open_ms / 1000, tz=UTC)
    close_t = ot + timedelta(hours=1) - timedelta(milliseconds=1)
    store.upsert_klines(
        [
            {
                "open_time": ot,
                "close_time": close_t,
                "symbol": symbol,
                "timeframe": tf,
                "open": 100.0,
                "high": 110.0,
                "low": 95.0,
                "close": 105.0,
                "volume": 10.0,
                "close_volume": 5.0,
                "trades": 100,
                "taker_buy_base": 4.0,
            }
        ]
    )


class TestGapDetection:
    def test_detect_gap_returns_missing_range(self):
        from app.ingest.ws_worker import detect_gap

        hour = 3_600_000
        t0 = 1_760_000_000_000
        # DB has candle at t0 only; incoming candle is t0 + 3*hour → 2 missing
        missing = detect_gap(last_stored=t0, incoming=t0 + 3 * hour, step=hour)
        assert missing == [t0 + hour, t0 + 2 * hour]

    def test_no_gap_when_adjacent(self):
        from app.ingest.ws_worker import detect_gap

        hour = 3_600_000
        assert detect_gap(1_760_000_000_000, 1_760_000_000_000 + hour, hour) == []

    def test_first_candle_no_gap(self):
        from app.ingest.ws_worker import detect_gap

        assert detect_gap(None, 1_760_000_000_000, 3_600_000) == []
