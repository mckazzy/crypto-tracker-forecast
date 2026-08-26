from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.models.positional import (
    PositionalProvider,
    build_momentum_features,
    train_positional,
)
from app.models.registry import ModelRegistry
from app.forecast.schema import ForecastContext, SignalStatus


def make_ohlcv(n=120, seed=1):
    rng = np.random.default_rng(seed)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    closes = 40000 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
    out = []
    for i in range(n):
        ot = t0 + timedelta(days=i)
        c = float(closes[i])
        o = float(closes[i - 1]) if i > 0 else c
        out.append(
            {
                "open_time": ot,
                "open": o,
                "high": max(o, c) * 1.01,
                "low": min(o, c) * 0.99,
                "close": c,
                "volume": 100.0,
                "taker_buy_base": 55.0,
            }
        )
    return out


class TestMomentumFeatures:
    def test_columns_present(self):
        import pandas as pd

        df = pd.DataFrame(make_ohlcv(120, seed=2))
        feats = build_momentum_features(df)
        for col in ["mom_30", "mom_90", "ret_7", "vol_30"]:
            assert col in feats.columns

    def test_no_lookahead(self):
        import pandas as pd

        df = pd.DataFrame(make_ohlcv(120, seed=3))
        feats = build_momentum_features(df)
        # mom_30 tại t = close[t]/close[t-30] - 1 (chỉ dùng quá khứ)
        expected = df["close"] / df["close"].shift(30) - 1
        # NaN rows đầu (chưa đủ 30) — drop
        valid = ~feats["mom_30"].isna()
        np.testing.assert_allclose(
            feats.loc[valid, "mom_30"].to_numpy(),
            expected.loc[valid].to_numpy(),
            rtol=1e-6,
        )


class TestTrainPositional:
    def test_train_saves_registry(self, tmp_path, monkeypatch):
        candles = make_ohlcv(120, seed=4)
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.positional.model_registry", reg)
        name = train_positional("BTCUSDT", "1d", candles, registry=reg)
        assert reg.has(name)
        model, meta = reg.load_model(name)
        assert meta["type"] == "elasticnet"
        assert callable(model["clf"].predict_proba)

    def test_too_few_candles_raises(self, tmp_path, monkeypatch):
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.positional.model_registry", reg)
        with pytest.raises(ValueError):
            train_positional("BTCUSDT", "1d", make_ohlcv(20, seed=5), registry=reg)


class TestPositionalProvider:
    def test_forecast_ok(self, tmp_path, monkeypatch):
        candles = make_ohlcv(120, seed=6)
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.positional.model_registry", reg)
        name = train_positional("BTCUSDT", "1d", candles, registry=reg)
        p = PositionalProvider(name, registry=reg)
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1d", candles=candles))
        assert sig.status == SignalStatus.OK
        assert 0.0 <= sig.probability <= 1.0
        assert sig.direction.value in ("LONG", "SHORT")
