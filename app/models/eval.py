from __future__ import annotations

import numpy as np

from app.forecast.metrics import brier_score, directional_accuracy
from app.forecast.walkforward import evaluate_walkforward, fit_predict_baseline


def eval_symbol(symbol: str, timeframe: str, model_name: str | None = None) -> dict:
    """Walk-forward eval cho (symbol, timeframe); so model với baseline."""
    from app.api.routes import get_store
    from app.forecast.features import build_features
    from app.models.registry import model_registry

    store = get_store()
    rows = store.get_klines(symbol, timeframe, limit=5000)
    if len(rows) < 100:
        return {"symbol": symbol, "timeframe": timeframe, "n": 0}

    import pandas as pd

    feats = build_features(pd.DataFrame(rows))
    if len(feats) < 80:
        return {"symbol": symbol, "timeframe": timeframe, "n": 0}

    baseline = evaluate_walkforward(feats, fit_predict_baseline, train_size=60, test_size=20)

    if model_name and model_registry.has(model_name):
        model, meta = model_registry.load_model(model_name)

        def fit_predict_model(train_df, test_df):
            cols = [
                c
                for c in train_df.columns
                if c not in ("close", "open", "high", "low", "volume", "taker_buy_base")
            ]
            X_train = train_df[cols].to_numpy()
            y_train = (train_df["close"].shift(-1) > train_df["close"]).astype(int).to_numpy()[:-1]
            X_train = X_train[:-1]
            if len(y_train) < 10:
                return np.full(len(test_df), 0.5), np.full(len(test_df), 0.0), np.full(len(test_df), 1.0)
            m = model.__class__()
            m.fit(X_train, y_train)
            X_test = test_df[cols].to_numpy()
            proba = m.predict_proba(X_test)
            probs = proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]
            vol = float(train_df["close"].pct_change().dropna().ewm(span=20).std().iloc[-1]) or 0.01
            last = float(test_df["close"].iloc[0])
            band = max(last * vol, last * 0.001)
            return probs, np.full(len(test_df), last - band), np.full(len(test_df), last + band)

        model_metrics = evaluate_walkforward(feats, fit_predict_model, train_size=60, test_size=20)
    else:
        model_metrics = {"n": 0}

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "n": baseline["n"],
        "baseline_accuracy": baseline.get("directional_accuracy", 0.0),
        "baseline_brier": baseline.get("brier_score", 0.0),
        "model_accuracy": model_metrics.get("directional_accuracy"),
        "model_brier": model_metrics.get("brier_score"),
        "model_beats_baseline": bool(
            model_metrics.get("n", 0) > 0
            and model_metrics.get("brier_score", 1.0) < baseline.get("brier_score", 1.0)
        ),
    }
