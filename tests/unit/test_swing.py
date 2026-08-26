from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.models.registry import ModelRegistry
from app.models.swing import SwingProvider, train_swing
from app.forecast.schema import ForecastContext, SignalStatus


def make_ohlcv(n=150, seed=1):
    rng = np.random.default_rng(seed)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    closes = 40000 * np.exp(np.cumsum(rng.normal(0.0002, 0.003, n)))
    out = []
    for i in range(n):
        ot = t0 + timedelta(hours=i)
        c = float(closes[i])
        o = float(closes[i - 1]) if i > 0 else c
        out.append(
            {
                "open_time": ot,
                "open": o,
                "high": max(o, c) * 1.003,
                "low": min(o, c) * 0.997,
                "close": c,
                "volume": 100.0,
                "taker_buy_base": 55.0,
            }
        )
    return out


class TestTrainSwing:
    def test_train_saves_registry(self, tmp_path, monkeypatch):
        candles = make_ohlcv(150, seed=2)
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.swing.model_registry", reg)
        name = train_swing("BTCUSDT", "1h", candles, registry=reg)
        assert reg.has(name)
        model, meta = reg.load_model(name)
        assert meta["type"] == "meta_lgbm"
        assert "lgbm" in model and "logit" in model

    def test_too_few_candles_raises(self, tmp_path, monkeypatch):
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.swing.model_registry", reg)
        with pytest.raises(ValueError):
            train_swing("BTCUSDT", "1h", make_ohlcv(20, seed=3), registry=reg)


class TestSwingProvider:
    def test_forecast_ok(self, tmp_path, monkeypatch):
        candles = make_ohlcv(150, seed=4)
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.swing.model_registry", reg)
        name = train_swing("BTCUSDT", "1h", candles, registry=reg)
        p = SwingProvider(name, registry=reg)
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=candles))
        assert sig.status == SignalStatus.OK
        assert 0.0 <= sig.probability <= 1.0
        assert sig.direction.value in ("LONG", "SHORT")
        assert sig.entry is not None
        assert sig.take_profit  # TP từ barrier

    def test_too_few_candles_failed(self, tmp_path, monkeypatch):
        candles = make_ohlcv(150, seed=5)
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.swing.model_registry", reg)
        name = train_swing("BTCUSDT", "1h", candles, registry=reg)
        p = SwingProvider(name, registry=reg)
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=[]))
        assert sig.status == SignalStatus.FAILED
