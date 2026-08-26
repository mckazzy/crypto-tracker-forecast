from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.trading.positions import (
    check_barrier,
    compute_pnl,
    resolve_open_positions,
)
from app.storage.duckdb_store import DuckDBStore


@pytest.fixture
def store(tmp_duckdb) -> DuckDBStore:
    return DuckDBStore(tmp_duckdb)


def make_candles(entries: list[dict], base: datetime | None = None) -> list[dict]:
    """entries: (open_time_delta_hours, high, low)"""
    base = base or datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    out = []
    for i, (dh, high, low) in enumerate(entries):
        ot = base + timedelta(hours=dh)
        out.append(
            {
                "open_time": ot,
                "close_time": ot + timedelta(hours=1),
                "open": (high + low) / 2,
                "high": high,
                "low": low,
                "close": (high + low) / 2,
                "volume": 100.0,
            }
        )
    return out


class TestComputePnl:
    def test_long_profit_after_fees(self):
        pnl = compute_pnl("LONG", 100.0, 110.0)
        assert abs(pnl - (0.10 - 0.003)) < 1e-9

    def test_short_profit(self):
        pnl = compute_pnl("SHORT", 100.0, 90.0)
        assert abs(pnl - (0.10 - 0.003)) < 1e-9

    def test_loss_amplified_by_fees(self):
        pnl = compute_pnl("LONG", 100.0, 99.0)
        assert pnl < -0.003


class TestCheckBarrier:
    def test_long_tp_hit(self):
        assert check_barrier("LONG", high=110.0, low=95.0, tp=108.0, sl=90.0) == "TP"

    def test_long_sl_hit(self):
        assert check_barrier("LONG", high=105.0, low=88.0, tp=108.0, sl=90.0) == "SL"

    def test_both_hit_prefers_sl(self):
        """Conservative: SL trước khi cả 2 chạm cùng candle."""
        assert check_barrier("LONG", high=120.0, low=85.0, tp=108.0, sl=90.0) == "SL"

    def test_short_tp_hit(self):
        assert check_barrier("SHORT", high=105.0, low=88.0, tp=90.0, sl=110.0) == "TP"

    def test_no_hit(self):
        assert check_barrier("LONG", high=105.0, low=95.0, tp=108.0, sl=90.0) is None


class TestResolveOpenPositions:
    def test_resolves_tp_and_closes(self, store):
        pos_id = store.create_position(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "LONG",
                "entry": 100.0,
                "tp": 108.0,
                "sl": 90.0,
                "model": "test",
            }
        )
        candles = {
            ("BTCUSDT", "1h"): make_candles([(1, 110.0, 95.0)]),
        }
        closed = resolve_open_positions(store, candles)
        assert closed == 1
        pos = store.get_positions()[0]
        assert pos["status"] == "closed"
        assert pos["exit_price"] == 108.0
        assert pos["pnl"] is not None

    def test_no_resolve_if_no_barrier(self, store):
        store.create_position(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "LONG",
                "entry": 100.0,
                "tp": 108.0,
                "sl": 90.0,
                "model": "test",
            }
        )
        candles = {("BTCUSDT", "1h"): make_candles([(1, 105.0, 95.0)])}
        assert resolve_open_positions(store, candles) == 0
        assert store.get_positions()[0]["status"] == "open"

    def test_skips_candles_before_opened(self, store):
        """Candle tại opened_at không tính (chưa đóng khi mở vị thế)."""
        pos_id = store.create_position(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "LONG",
                "entry": 100.0,
                "tp": 108.0,
                "sl": 90.0,
                "model": "test",
            }
        )
        # candle đầu tiên (t=0) chạm TP nhưng nó mở TRƯỚC vị thế → bỏ qua
        candles = {("BTCUSDT", "1h"): make_candles([(0, 110.0, 95.0), (1, 105.0, 95.0)])}
        assert resolve_open_positions(store, candles) == 0
