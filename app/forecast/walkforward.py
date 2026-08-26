from __future__ import annotations

import numpy as np
import pandas as pd

from app.forecast.metrics import brier_score, directional_accuracy, hit_rate_band


def expanding_windows(n: int, train_size: int, test_size: int, embargo: int = 1):
    """Yield (train_idx, test_idx) expanding-window splits with embargo.

    train = [0, start), test = [start + embargo, start + test_size + embargo)
    """
    start = train_size
    while start + embargo + test_size <= n:
        train = slice(0, start)
        test = slice(start + embargo, start + embargo + test_size)
        yield train, test
        start += test_size


def evaluate_walkforward(
    df: pd.DataFrame,
    fit_predict,
    *,
    train_size: int,
    test_size: int,
    embargo: int = 1,
    horizon: int = 1,
) -> dict:
    """Run expanding-window walk-forward evaluation.

    fit_predict(train_df, test_df) -> (probabilities array, band_lows, band_highs)
    """
    closes = df["close"].to_numpy()
    all_probs: list[float] = []
    all_lows: list[float] = []
    all_highs: list[float] = []
    all_actual: list[float] = []
    all_direction_up: list[int] = []

    for train_sl, test_sl in expanding_windows(len(df), train_size, test_size, embargo):
        train_df = df.iloc[train_sl]
        test_df = df.iloc[test_sl]
        probs, lows, highs = fit_predict(train_df, test_df)
        for i in range(len(test_df)):
            t = test_sl.start + i
            if t + horizon >= len(df):
                continue
            future_close = closes[t + horizon]
            all_probs.append(float(probs[i]))
            all_lows.append(float(lows[i]))
            all_highs.append(float(highs[i]))
            all_actual.append(float(future_close))
            all_direction_up.append(1 if future_close > closes[t] else 0)

    if not all_probs:
        return {"n": 0}
    y = np.array(all_direction_up)
    p = np.array(all_probs)
    return {
        "n": int(len(y)),
        "directional_accuracy": directional_accuracy(y, p),
        "brier_score": brier_score(y, p),
        "hit_rate_band": hit_rate_band(
            np.array(all_lows), np.array(all_highs), np.array(all_actual)
        ),
    }


def fit_predict_baseline(train_df: pd.DataFrame, test_df: pd.DataFrame):
    """Baseline fit_predict: last close, p=0.5, band từ train EWMA vol."""
    closes = test_df["close"].to_numpy()
    n = len(closes)
    last = float(train_df["close"].iloc[-1]) if len(train_df) else float(closes[-1])
    rets = train_df["close"].pct_change().dropna()
    vol = float(rets.ewm(span=20).std().iloc[-1]) if len(rets) else 0.01
    band = max(last * vol, last * 0.001)
    probs = np.full(n, 0.5)
    lows = np.full(n, last - band)
    highs = np.full(n, last + band)
    return probs, lows, highs
