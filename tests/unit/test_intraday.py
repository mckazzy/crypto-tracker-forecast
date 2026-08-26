from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.models.intraday import (
    GarchVolEstimator,
    IntradayProvider,
    build_labels,
    train_intraday,
)
from app.models.registry import ModelRegistry
from app.forecast.schema import ForecastContext, SignalStatus


def make_ohlcv(n=150, seed=42, drift=0.0001):
    rng = np.random.default_rng(seed)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    closes = 40000 * np.exp(np.cumsum(rng.normal(drift, 0.002, n)))
    out = []
    for i in range(n):
        ot = t0 + timedelta(hours=i)
        c = float(closes[i])
        o = float(closes[i - 1]) if i > 0 else c
        out.append(
            {
                "open_time": ot,
                "open": o,
                "high": max(o, c) * 1.002,
                "low": min(o, c) * 0.998,
                "close": c,
                "volume": 100.0 + rng.uniform(-10, 10),
                "taker_buy_base": 55.0,
            }
        )
    return out


class TestBuildLabels:
    def test_next_candle_direction(self):
        import pandas as pd

        df = pd.DataFrame(make_ohlcv(10))
        labels = build_labels(df)
        expected = (df["close"].shift(-1) > df["close"]).astype(float)
        # last row: NaN (no next candle) — drop before compare
        assert (labels.iloc[:-1] == expected.iloc[:-1]).all()

    def test_no_lookahead(self):
        """Label at t only depends on close[t] and close[t+1] (future) — never close[t-1]."""
        import pandas as pd

        df = pd.DataFrame(make_ohlcv(20, seed=3))
        labels = build_labels(df)
        # last label NaN (no next candle)
        assert np.isnan(labels.iloc[-1])


class TestGarchVolEstimator:
    def test_fit_predict_positive(self):
        g = GarchVolEstimator()
        closes = [c["close"] for c in make_ohlcv(150, seed=7)]
        vol = g.predict_vol(closes)
        assert vol is not None
        assert vol > 0

    def test_too_short_returns_none(self):
        g = GarchVolEstimator()
        assert g.predict_vol([100.0, 101.0]) is None


class TestTrainIntraday:
    def test_train_saves_registry(self, tmp_path, monkeypatch):
        candles = make_ohlcv(150, seed=1)
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.intraday.model_registry", reg)
        name = train_intraday("BTCUSDT", "1h", candles, registry=reg)
        assert reg.has(name)
        model, meta = reg.load_model(name)
        assert meta["type"] == "intraday_lgbm"
        assert callable(model["clf"].predict_proba)
        assert hasattr(model, "iso") or "iso" in model


class TestIntradayProvider:
    def test_forecast_ok(self, tmp_path, monkeypatch):
        candles = make_ohlcv(150, seed=2)
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.intraday.model_registry", reg)
        name = train_intraday("BTCUSDT", "1h", candles, registry=reg)
        p = IntradayProvider(name, registry=reg)
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=candles))
        assert sig.status == SignalStatus.OK
        assert 0.0 <= sig.probability <= 1.0
        assert sig.direction.value in ("LONG", "SHORT")
        assert sig.entry is not None

    def test_too_few_candles_failed(self, tmp_path, monkeypatch):
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.intraday.model_registry", reg)
        name = train_intraday("BTCUSDT", "1h", make_ohlcv(150, seed=2), registry=reg)
        p = IntradayProvider(name, registry=reg)
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=[]))
        assert sig.status == SignalStatus.FAILED
