import pytest

from app.models.ensemble import EnsembleProvider, inverse_brier_weights
from app.models.registry import ModelRegistry
from app.forecast.schema import ForecastContext, SignalStatus


class StubModel:
    def __init__(self, prob):
        self.prob = prob

    def predict_proba(self, X):
        import numpy as np

        n = len(X)
        return np.tile([1 - self.prob, self.prob], (n, 1))


def make_candles(n=60):
    from datetime import UTC, datetime, timedelta

    import numpy as np

    rng = np.random.default_rng(1)
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


class TestInverseBrierWeights:
    def test_better_model_gets_higher_weight(self):
        # model A brier 0.10 (tốt), model B brier 0.30 (kém)
        weights = inverse_brier_weights({"a": 0.10, "b": 0.30})
        assert weights["a"] > weights["b"]
        assert abs(sum(weights.values()) - 1.0) < 1e-9

    def test_equal_briers_equal_weights(self):
        weights = inverse_brier_weights({"a": 0.2, "b": 0.2})
        assert abs(weights["a"] - 0.5) < 1e-9


class TestEnsembleProvider:
    def test_forecast_weighted_vote(self, tmp_path, monkeypatch):
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.ensemble.model_registry", reg)
        reg.save_model("m1", StubModel(0.7), {"type": "t", "brier": 0.10})
        reg.save_model("m2", StubModel(0.5), {"type": "t", "brier": 0.30})
        # weights: m1 > m2 → prob weighted về phía 0.7
        p = EnsembleProvider(["m1", "m2"], registry=reg)
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=make_candles()))
        assert sig.status == SignalStatus.OK
        assert sig.probability > 0.6  # weighted về phía m1 (0.7)
        assert sig.model.startswith("ensemble")

    def test_missing_models_failed(self, tmp_path, monkeypatch):
        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.models.ensemble.model_registry", reg)
        p = EnsembleProvider(["ghost"], registry=reg)
        sig = p.forecast(ForecastContext(symbol="BTCUSDT", timeframe="1h", candles=make_candles()))
        assert sig.status == SignalStatus.FAILED
