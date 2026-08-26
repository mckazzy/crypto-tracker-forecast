from __future__ import annotations

import numpy as np


class TripleBarrierLabeler:
    """Triple-barrier labeling (López de Prado): TP/SL/time barriers.

    Label = +1 nếu chạm TP trước, -1 nếu chạm SL trước, 0 nếu hết time barrier.
    KHÔNG look-ahead: tại candle t, chỉ dùng dữ liệu từ t+1 đến t+max_hold.
    """

    def __init__(self, tp_pct: float = 0.01, sl_pct: float = 0.01, max_hold: int = 5):
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct
        self.max_hold = max_hold

    def label(self, candles: list[dict]) -> np.ndarray:
        n = len(candles)
        closes = np.array([c["close"] for c in candles])
        highs = np.array([c["high"] for c in candles])
        lows = np.array([c["low"] for c in candles])
        labels = np.zeros(n, dtype=float)
        for t in range(n - 1):
            entry = closes[t]
            tp = entry * (1 + self.tp_pct)
            sl = entry * (1 - self.sl_pct)
            hit = 0.0
            for s in range(1, min(self.max_hold, n - t - 1) + 1):
                if highs[t + s] >= tp:
                    hit = 1.0
                    break
                if lows[t + s] <= sl:
                    hit = -1.0
                    break
            labels[t] = hit
        return labels


def primary_signal_ema_breakout(
    candles: list[dict], fast: int = 12, slow: int = 26, breakout: int = 20
) -> np.ndarray:
    """Primary signal: EMA cross + Donchian breakout → boolean entry mask.

    Entry tại t nếu EMA_fast vừa cắt lên EMA_slow HOẶC close phá high N-candle trước.
    """
    import pandas as pd

    df = pd.DataFrame(candles)
    close = df["close"]
    ema_fast = close.ewm(span=fast, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, min_periods=slow).mean()
    cross_up = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
    donchian = close > close.rolling(breakout, min_periods=breakout).max().shift(1)
    entries = (cross_up | donchian).to_numpy()
    entries[:slow] = False  # warmup
    return entries


def stack_mtf_features(n: int, slow_series: np.ndarray, ratio: int) -> np.ndarray:
    """Align slower-timeframe series to faster grid, using PREVIOUS closed value.

    slow_series: one value per slower candle (length n//ratio).
    aligned[t] = slow_series[k-1] với k = t//ratio (candle slow vừa đóng tại t).
    Trước khi có slow candle đầu đóng (t < ratio) → dùng NaN.
    """
    aligned = np.full(n, np.nan)
    for t in range(n):
        k = t // ratio
        if k >= 1 and k <= len(slow_series):
            aligned[t] = slow_series[k - 1]
    return aligned
