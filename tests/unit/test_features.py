from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.forecast.features import build_features


def make_candles(n=120, start="2026-01-01", seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t0 = datetime.fromisoformat(start).replace(tzinfo=UTC)
    idx = [t0 + timedelta(hours=i) for i in range(n)]
    closes = 40000 + np.cumsum(rng.normal(0, 50, n))
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) + rng.uniform(0, 30, n)
    lows = np.minimum(opens, closes) - rng.uniform(0, 30, n)
    vols = rng.uniform(50, 200, n)
    taker = rng.uniform(0.3, 0.7, n)
    return pd.DataFrame(
        {
            "open_time": idx,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": vols,
            "taker_buy_base": taker,
        }
    )


class TestBuildFeatures:
    def test_columns_present(self):
        df = build_features(make_candles())
        for col in [
            "ret_1",
            "ret_5",
            "ret_20",
            "rsi_14",
            "macd",
            "macd_signal",
            "bb_pct_b",
            "vol_zscore_20",
            "taker_buy_ratio",
        ]:
            assert col in df.columns, f"missing {col}"

    def test_index_is_open_time(self):
        df = build_features(make_candles())
        assert df.index.name == "open_time"
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_no_nan_after_warmup(self):
        df = build_features(make_candles(150))
        assert not df.isna().any().any()

    def test_warmup_rows_dropped(self):
        df = build_features(make_candles(40))
        # need ~27 rows warmup (ret_20 + RSI + MACD) → 40 rows leaves ~13
        assert len(df) < 40
        assert len(df) > 0

    def test_no_lookahead_ret(self):
        """ret_1 at row t must equal (close_t - close_{t-1}) / close_{t-1}."""
        df = build_features(make_candles(50, seed=7))
        closes = df["close"]
        expected = closes.pct_change().iloc[1:]
        actual = df["ret_1"].iloc[1:]
        pd.testing.assert_series_equal(
            actual.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_rsi_range(self):
        df = build_features(make_candles(120, seed=3))
        assert df["rsi_14"].between(0, 100).all()

    def test_deterministic(self):
        a = build_features(make_candles(80, seed=1))
        b = build_features(make_candles(80, seed=1))
        pd.testing.assert_frame_equal(a, b)
