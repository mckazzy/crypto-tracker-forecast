from __future__ import annotations

import numpy as np
import numpy.typing as npt


def directional_accuracy(y: npt.ArrayLike, p: npt.ArrayLike) -> float:
    """Fraction of predictions where sign(p-0.5) matches y (0/1)."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    if len(y) == 0:
        return 0.0
    pred = (p >= 0.5).astype(float)
    return float(np.mean(pred == y))


def brier_score(y: npt.ArrayLike, p: npt.ArrayLike) -> float:
    """Mean squared error between probability and outcome (0=perfect, 0.25=random)."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    if len(y) == 0:
        return 0.0
    return float(np.mean((p - y) ** 2))


def hit_rate_band(lows: npt.ArrayLike, highs: npt.ArrayLike, closes: npt.ArrayLike) -> float:
    """Fraction of closes within predicted [low, high] band (target 60-70%)."""
    lows = np.asarray(lows, dtype=float)
    highs = np.asarray(highs, dtype=float)
    closes = np.asarray(closes, dtype=float)
    if len(closes) == 0:
        return 0.0
    return float(np.mean((closes >= lows) & (closes <= highs)))
