from __future__ import annotations

import logging

from app.forecast.provider import ForecastProvider
from app.forecast.schema import ForecastContext, Signal, SignalDirection, SignalStatus
from app.models.registry import model_registry

logger = logging.getLogger(__name__)


class ModelProvider(ForecastProvider):
    """Wrapper biến model registry thành ForecastProvider (SP2 contract)."""

    def __init__(self, model_name: str, registry=None):
        self.name = model_name
        self.model_name = model_name
        self._registry = registry or model_registry

    def forecast(self, ctx: ForecastContext) -> Signal:
        try:
            model, meta = self._registry.load_model(self.model_name)
        except (FileNotFoundError, ValueError) as e:
            logger.warning("model %s unavailable: %s", self.model_name, e)
            return self._failed(ctx, str(e))

        candles = ctx.candles
        if len(candles) < 30:
            return self._failed(ctx, "not enough candles")
        try:
            X = self._build_features(candles)
            if len(X) == 0:
                return self._failed(ctx, "feature warmup insufficient")
            proba = model.predict_proba(X)
            prob_up = float(proba[-1][1]) if proba.shape[1] > 1 else float(proba[-1][0])
        except Exception as e:
            logger.exception("model %s predict failed", self.model_name)
            return self._failed(ctx, str(e))

        direction = SignalDirection.LONG if prob_up >= 0.5 else SignalDirection.SHORT
        last_close = float(candles[-1]["close"])
        return Signal(
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            direction=direction,
            probability=prob_up,
            entry=last_close,
            model=self.name,
            status=SignalStatus.OK,
        )

    def _build_features(self, candles: list[dict]):
        from app.forecast.features import build_features

        import pandas as pd

        df = pd.DataFrame(candles)
        feats = build_features(df)
        feature_cols = [c for c in feats.columns if c not in ("close", "open", "high", "low", "volume", "taker_buy_base")]
        return feats[feature_cols].to_numpy()

    def _failed(self, ctx: ForecastContext, reason: str) -> Signal:
        return Signal(
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            direction=SignalDirection.FLAT,
            probability=0.5,
            model=self.name,
            status=SignalStatus.FAILED,
        )
