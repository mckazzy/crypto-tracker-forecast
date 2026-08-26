from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.forecast.baselines import EwmaVolProvider, RandomWalkProvider
from app.forecast.schema import ForecastContext, Signal


def make_candles(n=100, start="2026-01-01", drift=0.0, seed=42) -> list[dict]:
    rng = np.random.default_rng(seed)
    t0 = datetime.fromisoformat(start).replace(tzinfo=UTC)
    closes = 40000 + np.cumsum(rng.normal(drift, 50, n))
    out = []
    for i in range(n):
        ot = t0 + timedelta(hours=i)
        c = closes[i]
        o = closes[i - 1] if i > 0 else c
        out.append(
            {
                "open_time": ot,
                "close_time": ot + timedelta(hours=1) - timedelta(milliseconds=1),
                "open": float(o),
                "high": float(max(o, c) * 1.001),
                "low": float(min(o, c) * 0.999),
                "close": float(c),
                "volume": 100.0,
                "close_volume": 60.0,
                "trades": 100,
                "taker_buy_base": 55.0,
            }
        )
    return out


class TestRandomWalkProvider:
    def test_provider_contract(self):
        p = RandomWalkProvider()
        assert p.name == "random_walk"

    def test_forecast_returns_signal(self):
        p = RandomWalkProvider()
        ctx = ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=make_candles())
        sig = p.forecast(ctx)
        assert isinstance(sig, Signal)
        assert sig.model == "random_walk"
        assert 0.0 <= sig.probability <= 1.0
        assert sig.entry is not None and sig.entry > 0

    def test_probability_half(self):
        p = RandomWalkProvider()
        ctx = ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=make_candles(50, seed=1))
        sig = p.forecast(ctx)
        assert sig.probability == 0.5

    def test_empty_candles_still_returns_signal(self):
        p = RandomWalkProvider()
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h"))
        assert sig.entry is None


class TestEwmaVolProvider:
    def test_provider_contract(self):
        p = EwmaVolProvider()
        assert p.name == "ewma_vol"

    def test_forecast_returns_signal(self):
        p = EwmaVolProvider()
        ctx = ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=make_candles())
        sig = p.forecast(ctx)
        assert isinstance(sig, Signal)
        assert sig.model == "ewma_vol"
        assert sig.entry is not None

    def test_direction_sign_of_last_return(self):
        p = EwmaVolProvider()
        # force last return positive
        candles = make_candles(30, seed=5)
        candles[-1]["close"] = candles[-2]["close"] * 1.01
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=candles))
        assert sig.direction.value == "LONG"

    def test_direction_sign_of_last_return_negative(self):
        p = EwmaVolProvider()
        candles = make_candles(30, seed=5)
        candles[-1]["close"] = candles[-2]["close"] * 0.99
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=candles))
        assert sig.direction.value == "SHORT"

    def test_take_profit_stop_loss_consistent(self):
        p = EwmaVolProvider()
        ctx = ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=make_candles(60, seed=2))
        sig = p.forecast(ctx)
        if sig.entry is not None and sig.take_profit:
            if sig.direction.value == "LONG":
                assert sig.take_profit[0] > sig.entry
                assert sig.stop_loss is not None and sig.stop_loss < sig.entry
            elif sig.direction.value == "SHORT":
                assert sig.take_profit[0] < sig.entry
                assert sig.stop_loss is not None and sig.stop_loss > sig.entry
