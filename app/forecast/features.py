"""Feature pipeline implementation (SP2 Phase 2)."""

from __future__ import annotations

import pandas as pd


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series]:
    ema_fast = close.ewm(span=fast, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal, min_periods=signal).mean()
    return macd_line, macd_signal


def _bb_pct_b(close: pd.Series, window: int = 20) -> pd.Series:
    mid = close.rolling(window, min_periods=window).mean()
    std = close.rolling(window, min_periods=window).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    return (close - lower) / (upper - lower).replace(0, 1e-10)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build standardized feature columns from klines DataFrame.

    Input columns: open_time, open, high, low, close, volume, taker_buy_base.
    Output: DataFrame indexed by open_time with feature columns, warmup rows dropped.
    """
    out = df.copy()
    out = out.set_index("open_time") if "open_time" in out.columns else out
    out = out.sort_index()

    close = out["close"]
    out["ret_1"] = close.pct_change(1)
    out["ret_5"] = close.pct_change(5)
    out["ret_20"] = close.pct_change(20)
    out["rsi_14"] = _rsi(close)
    out["macd"], out["macd_signal"] = _macd(close)
    out["bb_pct_b"] = _bb_pct_b(close)
    out["vol_zscore_20"] = (out["volume"] - out["volume"].rolling(20, min_periods=20).mean()) / out[
        "volume"
    ].rolling(20, min_periods=20).std().replace(0, 1e-10)
    out["taker_buy_ratio"] = out["taker_buy_base"] / out["volume"].replace(0, 1e-10)

    # drop warmup rows (NaN from rolling/ema)
    out = out.dropna()
    return out
