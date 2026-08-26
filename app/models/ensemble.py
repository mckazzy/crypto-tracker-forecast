from __future__ import annotations

import logging

from app.models.provider import ModelProvider
from app.models.registry import model_registry
from app.forecast.schema import ForecastContext, Signal, SignalDirection, SignalStatus

logger = logging.getLogger(__name__)


def inverse_brier_weights(briers: dict[str, float]) -> dict[str, float]:
    """Inverse-error weighting: w_i = (1/b_i) / sum(1/b_j)."""
    inv = {k: 1.0 / max(v, 1e-6) for k, v in briers.items()}
    total = sum(inv.values())
    return {k: v / total for k, v in inv.items()}


class EnsembleProvider(ModelProvider):
    """Ensemble nhiều model đã train — weighted vote theo inverse-Brier (meta brier)."""

    def __init__(self, model_names: list[str], registry=None):
        self.name = "ensemble"
        self.model_names = model_names
        self._registry = registry or model_registry

    def forecast(self, ctx: ForecastContext) -> Signal:
        weights: dict[str, float] = {}
        probs: dict[str, float] = {}
        for name in self.model_names:
            try:
                model, meta = self._registry.load_model(name)
            except Exception as e:
                logger.warning("ensemble member %s unavailable: %s", name, e)
                continue
            try:
                prob = self._predict(model, ctx)
                probs[name] = prob
                weights[name] = float(meta.get("brier", 0.25))
            except Exception as e:
                logger.warning("ensemble member %s predict failed: %s", name, e)

        if not probs:
            return Signal(
                symbol=ctx.symbol,
                timeframe=ctx.timeframe,
                direction=SignalDirection.FLAT,
                probability=0.5,
                model=self.name,
                status=SignalStatus.FAILED,
            )
        w = inverse_brier_weights(weights)
        prob = sum(probs[n] * w[n] for n in probs)
        last_close = float(ctx.candles[-1]["close"]) if ctx.candles else None
        direction = SignalDirection.LONG if prob >= 0.5 else SignalDirection.SHORT
        return Signal(
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            direction=direction,
            probability=round(float(prob), 4),
            entry=last_close,
            model=self.name,
            status=SignalStatus.OK,
        )

    def _predict(self, model, ctx: ForecastContext) -> float:
        import pandas as pd

        from app.forecast.features import build_features

        df = pd.DataFrame(ctx.candles)
        feats = build_features(df)
        cols = [
            c
            for c in feats.columns
            if c not in ("close", "open", "high", "low", "volume", "taker_buy_base")
        ]
        X = feats[cols].to_numpy()[-1:].reshape(1, -1)
        if isinstance(model, dict):
            clf = model.get("clf")
            if clf is None:
                raise ValueError("no clf in model dict")
        else:
            clf = model
        proba = clf.predict_proba(X)
        return float(proba[0, 1]) if proba.shape[1] > 1 else float(proba[0, 0])
