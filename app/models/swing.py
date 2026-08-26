from __future__ import annotations

import logging
from datetime import UTC, datetime

import numpy as np

from app.models.intraday import FEATURE_COLS
from app.models.labels import TripleBarrierLabeler, primary_signal_ema_breakout
from app.models.registry import model_registry
from app.models.provider import ModelProvider
from app.forecast.schema import ForecastContext, Signal, SignalDirection, SignalStatus

logger = logging.getLogger(__name__)

BARRIER_TP = 0.01  # 2×ATR thay bằng pct đơn giản (scale-invariant)
BARRIER_SL = 0.005
MAX_HOLD = 8


def train_swing(
    symbol: str,
    timeframe: str,
    candles: list[dict],
    registry=None,
) -> str:
    """Train swing meta-model: chỉ học trên primary-signal entries + triple-barrier labels."""
    import pandas as pd
    from lightgbm import LGBMClassifier
    from sklearn.linear_model import LogisticRegression

    reg = registry or model_registry
    df = pd.DataFrame(candles)
    feats = _feature_df(df)
    if len(feats) < 60:
        raise ValueError("not enough candles for swing training")

    labeler = TripleBarrierLabeler(tp_pct=BARRIER_TP, sl_pct=BARRIER_SL, max_hold=MAX_HOLD)
    labels = labeler.label(candles[: len(feats)])
    entries = primary_signal_ema_breakout(candles[: len(feats)])
    # chỉ train trên primary entries (meta-labeling)
    mask = entries & (labels != 0)
    if mask.sum() < 30:
        # fallback: dùng mọi label khác 0 nếu primary quá ít
        mask = labels != 0

    X = feats[FEATURE_COLS].to_numpy()[mask]
    y = labels[mask]
    if len(y) < 20:
        raise ValueError("too few labeled swing samples")

    lgbm = LGBMClassifier(
        n_estimators=80, learning_rate=0.05, max_depth=3, verbose=-1, random_state=42
    )
    logit = LogisticRegression(C=1.0, max_iter=1000)
    lgbm.fit(X, y)
    logit.fit(X, y)

    meta = {
        "type": "meta_lgbm",
        "symbol": symbol,
        "timeframe": timeframe,
        "trained_at": datetime.now(UTC).isoformat(),
        "features": FEATURE_COLS,
        "barrier_tp": BARRIER_TP,
        "barrier_sl": BARRIER_SL,
        "max_hold": MAX_HOLD,
    }
    name = f"meta_lgbm@{symbol}@{timeframe}"
    reg.save_model(name, {"lgbm": lgbm, "logit": logit}, meta)
    logger.info("trained swing %s %s (n=%d)", symbol, timeframe, len(y))
    return name


def _feature_df(df: pd.DataFrame) -> pd.DataFrame:
    from app.forecast.features import build_features

    return build_features(df)


class SwingProvider(ModelProvider):
    """Swing meta-model ensemble (LightGBM + Logistic average) → Signal."""

    def __init__(self, model_name: str, registry=None):
        super().__init__(model_name, registry=registry)

    def forecast(self, ctx: ForecastContext) -> Signal:
        candles = ctx.candles
        if len(candles) < 30:
            return self._failed(ctx, "not enough candles")
        import pandas as pd

        try:
            model, meta = self._registry.load_model(self.model_name)
        except Exception as e:
            return self._failed(ctx, str(e))

        df = pd.DataFrame(candles)
        feats = _feature_df(df)
        if len(feats) == 0:
            return self._failed(ctx, "feature warmup")
        X = feats[FEATURE_COLS].to_numpy()[-1:].reshape(1, -1)
        p_lgbm = model["lgbm"].predict_proba(X)[0, 1]
        p_logit = model["logit"].predict_proba(X)[0, 1]
        prob = 0.5 * p_lgbm + 0.5 * p_logit

        last_close = float(candles[-1]["close"])
        direction = SignalDirection.LONG if prob >= 0.5 else SignalDirection.SHORT
        sig = Signal(
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            direction=direction,
            probability=float(prob),
            entry=last_close,
            model=self.name,
            status=SignalStatus.OK,
        )
        band = last_close * BARRIER_TP
        if direction == SignalDirection.LONG:
            sig.take_profit = [round(last_close + band, 2)]
            sig.stop_loss = round(max(last_close - band * 0.5, 0.01), 2)
        else:
            sig.take_profit = [round(max(last_close - band, 0.01), 2)]
            sig.stop_loss = round(last_close + band * 0.5, 2)
        return sig
