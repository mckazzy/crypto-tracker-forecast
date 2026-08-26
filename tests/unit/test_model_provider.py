from datetime import UTC, datetime, timedelta

import pytest

from app.models.provider import ModelProvider
from app.models.registry import ModelRegistry
from app.forecast.schema import ForecastContext, SignalStatus


def make_candles(n=60, seed=1):
    import numpy as np

    rng = np.random.default_rng(seed)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    closes = 40000 + np.cumsum(rng.normal(0, 50, n))
    out = []
    for i in range(n):
        ot = t0 + timedelta(hours=i)
        out.append(
            {
                "open_time": ot,
                "open": float(closes[i - 1] if i else closes[i]),
                "high": float(closes[i] * 1.01),
                "low": float(closes[i] * 0.99),
                "close": float(closes[i]),
                "volume": 100.0,
                "taker_buy_base": 50.0,
            }
        )
    return out


class StubModel:
    """Minimal sklearn-like classifier: predict_proba → fixed probs."""

    def __init__(self, prob=0.63):
        self.prob = prob

    def predict_proba(self, X):
        import numpy as np

        n = len(X)
        return np.tile([1 - self.prob, self.prob], (n, 1))


@pytest.fixture
def registry(tmp_path, monkeypatch):
    r = ModelRegistry(base_dir=str(tmp_path / "models"))
    monkeypatch.setattr("app.models.registry.model_registry", r)
    return r


class TestModelProvider:
    def test_forecast_returns_signal(self, registry):
        registry.save_model(
            "intraday_lgbm@1h",
            StubModel(0.63),
            {"type": "intraday_lgbm", "features": ["ret_1", "rsi_14"], "trained_at": "2026-01-01"},
        )
        p = ModelProvider("intraday_lgbm@1h", registry=registry)
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=make_candles()))
        assert sig.status == SignalStatus.OK
        assert sig.model == "intraday_lgbm@1h"
        assert 0.0 <= sig.probability <= 1.0

    def test_missing_model_failed_signal(self, registry):
        p = ModelProvider("nonexistent")
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h"))
        assert sig.status == SignalStatus.FAILED

    def test_too_few_candles_failed(self, registry):
        registry.save_model("m", StubModel(), {"type": "t", "features": ["ret_1"]})
        p = ModelProvider("m")
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=[]))
        assert sig.status == SignalStatus.FAILED
