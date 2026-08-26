from __future__ import annotations

import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.models.provider import ModelProvider
from app.models.registry import model_registry
from app.forecast.schema import ForecastContext, Signal, SignalDirection, SignalStatus

logger = logging.getLogger(__name__)

MOM_COLS = ["mom_30", "mom_90", "ret_7", "vol_30"]


def build_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """Momentum features từ close series — chỉ dùng quá khứ (không look-ahead)."""
    out = df.copy()
    close = out["close"]
    out["mom_30"] = close / close.shift(30) - 1
    out["mom_90"] = close / close.shift(90) - 1
    out["ret_7"] = close.pct_change(7)
    out["vol_30"] = close.pct_change().rolling(30, min_periods=30).std()
    return out


def train_positional(
    symbol: str,
    timeframe: str,
    candles: list[dict],
    registry=None,
) -> str:
    """Train ElasticNet logistic trên momentum features → registry."""
    from sklearn.linear_model import LogisticRegression

    reg = registry or model_registry
    df = pd.DataFrame(candles)
    feats = build_momentum_features(df)
    feats = feats.dropna()
    if len(feats) < 30:
        raise ValueError("not enough candles for positional training")

    X = feats[MOM_COLS].to_numpy()
    y = (feats["close"].shift(-1) > feats["close"]).astype(int).to_numpy()[:-1]
    X = X[:-1]
    if len(y) < 20:
        raise ValueError("too few labeled positional samples")

    clf = LogisticRegression(
        l1_ratio=0.5,
        solver="saga",
        C=1.0,
        max_iter=2000,
    )
    clf.fit(X, y)

    meta = {
        "type": "elasticnet",
        "symbol": symbol,
        "timeframe": timeframe,
        "trained_at": datetime.now(UTC).isoformat(),
        "features": MOM_COLS,
    }
    name = f"elasticnet@{symbol}@{timeframe}"
    reg.save_model(name, {"clf": clf}, meta)
    logger.info("trained positional %s %s (n=%d)", symbol, timeframe, len(y))
    return name


class PositionalProvider(ModelProvider):
    """ElasticNet positional model → Signal."""

    def __init__(self, model_name: str, registry=None):
        super().__init__(model_name, registry=registry)

    def forecast(self, ctx: ForecastContext) -> Signal:
        candles = ctx.candles
        if len(candles) < 100:
            return self._failed(ctx, "not enough candles (need ~100 for mom_90)")
        try:
            model, meta = self._registry.load_model(self.model_name)
        except Exception as e:
            return self._failed(ctx, str(e))

        df = pd.DataFrame(candles)
        feats = build_momentum_features(df).dropna()
        if len(feats) == 0:
            return self._failed(ctx, "feature warmup")
        X = feats[MOM_COLS].to_numpy()[-1:].reshape(1, -1)
        prob_up = float(model["clf"].predict_proba(X)[0, 1])

        last_close = float(candles[-1]["close"])
        direction = SignalDirection.LONG if prob_up >= 0.5 else SignalDirection.SHORT
        sig = Signal(
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            direction=direction,
            probability=prob_up,
            entry=last_close,
            model=self.name,
            status=SignalStatus.OK,
        )
        band = last_close * 0.02  # 2% band cho positional
        if direction == SignalDirection.LONG:
            sig.take_profit = [round(last_close + band, 2)]
            sig.stop_loss = round(max(last_close - band, 0.01), 2)
        else:
            sig.take_profit = [round(max(last_close - band, 0.01), 2)]
            sig.stop_loss = round(last_close + band, 2)
        return sig
