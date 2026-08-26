from __future__ import annotations

import logging
from datetime import UTC, datetime

import numpy as np

from app.models.registry import model_registry

logger = logging.getLogger(__name__)


class DummyClassifier:
    """Stub model — Phase 2+ thay bằng LightGBM thật. Dự đoán theo momentum đơn giản."""

    def __init__(self):
        self.prob = 0.55

    def fit(self, X, y):
        # learn base rate of up-moves
        if len(y) > 0:
            self.prob = float(np.mean(y))
        return self

    def predict_proba(self, X):
        n = len(X)
        return np.tile([1 - self.prob, self.prob], (n, 1))


def train_model(symbol: str, timeframe: str, model_kind: str) -> str:
    """Train + save model; Phase 1 uses DummyClassifier stub."""
    from app.api.routes import get_store
    from app.forecast.features import build_features

    store = get_store()
    rows = store.get_klines(symbol, timeframe, limit=5000)
    if len(rows) < 60:
        logger.warning("not enough data for %s %s (%d rows)", symbol, timeframe, len(rows))
        return _save(symbol, timeframe, model_kind, DummyClassifier().fit(np.zeros((10, 1)), np.zeros(10)))

    import pandas as pd

    df = pd.DataFrame(rows)
    feats = build_features(df)
    if len(feats) < 40:
        return _save(symbol, timeframe, model_kind, DummyClassifier().fit(np.zeros((10, 1)), np.zeros(10)))

    feature_cols = [
        c
        for c in feats.columns
        if c not in ("close", "open", "high", "low", "volume", "taker_buy_base")
    ]
    X = feats[feature_cols].to_numpy()
    y = (feats["close"].shift(-1) > feats["close"]).astype(int).to_numpy()[:-1]
    X = X[:-1]
    model = DummyClassifier().fit(X, y)
    return _save(symbol, timeframe, model_kind, model, feature_cols)


def _save(symbol: str, timeframe: str, model_kind: str, model, features: list | None = None) -> str:
    name = f"{model_kind}@{symbol}@{timeframe}"
    meta = {
        "type": model_kind,
        "symbol": symbol,
        "timeframe": timeframe,
        "trained_at": datetime.now(UTC).isoformat(),
        "features": features or [],
    }
    model_registry.save_model(name, model, meta)
    logger.info("saved %s", name)
    return name


def retrain_from_feedback(symbol: str, timeframe: str, model_kind: str = "intraday_lgbm") -> str | None:
    """CLI hook: retrain model từ feedback outcomes (SP4 Phase 5)."""
    from app.api.routes import get_store
    from app.trading.retrain import retrain_from_outcomes

    store = get_store()
    return retrain_from_outcomes(store, symbol, timeframe, model_kind)
