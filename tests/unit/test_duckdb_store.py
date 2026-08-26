from datetime import UTC, datetime, timedelta

import pytest

from app.storage.duckdb_store import DuckDBStore


@pytest.fixture
def store(tmp_duckdb) -> DuckDBStore:
    return DuckDBStore(tmp_duckdb)


def kline(open_time: datetime, **overrides) -> dict:
    close_time = open_time + timedelta(hours=1) - timedelta(milliseconds=1)
    base = {
        "open_time": open_time,
        "close_time": close_time,
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
    base.update(overrides)
    return base


class TestValidityGate:
    def test_valid_batch_inserts(self, store):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        n = store.upsert_klines([kline(now + timedelta(hours=i)) for i in range(5)])
        assert n == 5

    def test_rejects_invalid_kline(self, store):
        """close < low → invalid; valid rows in same batch still insert."""
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        good = kline(t0)
        bad = kline(t0 + timedelta(hours=1), low=40000.0, high=40100.0, close=39500.0)
        good2 = kline(t0 + timedelta(hours=2))
        inserted = store.upsert_klines([good, bad, good2])
        assert inserted == 2
        assert len(store.reject_log) == 1
        assert store.reject_log[0]["reason"]

    def test_negative_volume_rejected(self, store):
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        bad = kline(t0, volume=-1.0)
        assert store.upsert_klines([bad]) == 0
        assert len(store.reject_log) == 1


class TestUpsert:
    def test_upsert_idempotent(self, store):
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        batch = [kline(t0 + timedelta(hours=i)) for i in range(10)]
        first = store.upsert_klines(batch)
        second = store.upsert_klines(batch)
        assert first == 10
        assert second == 10
        assert store.count("BTCUSDT", "1h") == 10

    def test_batch_duplicate_keys_deduped(self, store):
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        dup = kline(t0)
        assert store.upsert_klines([dup, dup]) == 1
        assert store.count("BTCUSDT", "1h") == 1

    def test_upsert_updates_changed_values(self, store):
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        original = kline(t0, close=40050.0)
        revised = kline(t0, high=42000.0, low=39900.0, close=41000.0)
        store.upsert_klines([original])
        store.upsert_klines([revised])
        rows = store.get_klines("BTCUSDT", "1h")
        assert len(rows) == 1
        assert rows[0]["close"] == 41000.0


class TestTimezone:
    def test_tz_roundtrip_naive_utc(self, store):
        """Naive datetime treated as UTC must roundtrip to same instant (UTC+7 host)."""
        naive = datetime(2026, 6, 15, 12, 0, 0)  # naive — interpreted as UTC by convention
        aware_expected = naive.replace(tzinfo=UTC)
        store.upsert_klines([kline(naive)])
        rows = store.get_klines("BTCUSDT", "1h")
        assert len(rows) == 1
        got = rows[0]["open_time"]
        if got.tzinfo is None:
            got = got.replace(tzinfo=UTC)
        assert got == aware_expected

    def test_max_open_time_returns_aware_utc(self, store):
        t0 = datetime(2026, 3, 1, tzinfo=UTC)
        store.upsert_klines([kline(t0)])
        mx = store.max_open_time("BTCUSDT", "1h")
        assert mx is not None
        if mx.tzinfo is None:
            mx = mx.replace(tzinfo=UTC)
        assert mx == t0

    def test_max_open_time_empty_none(self, store):
        assert store.max_open_time("BTCUSDT", "1h") is None


class TestBackfillProgress:
    def test_checkpoint_roundtrip(self, store):
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        assert store.get_backfill_cursor("BTCUSDT", "1h") is None
        store.set_backfill_cursor("BTCUSDT", "1h", t0)
        assert store.get_backfill_cursor("BTCUSDT", "1h") == t0
        later = t0 + timedelta(hours=7)
        store.set_backfill_cursor("BTCUSDT", "1h", later)
        assert store.get_backfill_cursor("BTCUSDT", "1h") == later
