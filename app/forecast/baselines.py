from __future__ import annotations

import numpy as np
import pandas as pd

from app.forecast.schema import ForecastContext, Signal, SignalDirection


def _last_close(candles: list[dict]) -> float | None:
    if not candles:
        return None
    return float(candles[-1]["close"])


def _ewma_vol(closes: list[float], span: int = 20) -> float | None:
    if len(closes) < 2:
        return None
    s = pd.Series(closes).pct_change().dropna()
    if len(s) < 2:
        return None
    return float(s.ewm(span=span).std().iloc[-1])


class RandomWalkProvider:
    """Baseline: forecast = last close, p=0.5, band từ EWMA vol (chặn dưới 0)."""

    name = "random_walk"

    def forecast(self, ctx: ForecastContext) -> Signal:
        closes = [c["close"] for c in ctx.candles]
        entry = _last_close(ctx.candles)
        vol = _ewma_vol(closes)
        sig = Signal(
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            direction=SignalDirection.FLAT,
            probability=0.5,
            entry=entry,
            model=self.name,
        )
        if entry is not None and vol is not None:
            band = max(entry * vol, entry * 0.001)
            sig.take_profit = [round(entry + band, 2)]
            sig.stop_loss = round(max(entry - band, 0.01), 2)
        return sig


class EwmaVolProvider:
    """Baseline: direction = sign(last return), p=0.5, TP/SL theo EWMA vol."""

    name = "ewma_vol"

    def forecast(self, ctx: ForecastContext) -> Signal:
        closes = [c["close"] for c in ctx.candles]
        entry = _last_close(ctx.candles)
        vol = _ewma_vol(closes)
        direction = SignalDirection.FLAT
        if len(closes) >= 2:
            direction = (
                SignalDirection.LONG
                if closes[-1] > closes[-2]
                else SignalDirection.SHORT
            )
        sig = Signal(
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            direction=direction,
            probability=0.5,
            entry=entry,
            model=self.name,
        )
        if entry is not None and vol is not None:
            band = max(entry * vol, entry * 0.001)
            if direction == SignalDirection.LONG:
                sig.take_profit = [round(entry + band, 2)]
                sig.stop_loss = round(max(entry - band, 0.01), 2)
            elif direction == SignalDirection.SHORT:
                sig.take_profit = [round(max(entry - band, 0.01), 2)]
                sig.stop_loss = round(entry + band, 2)
        return sig
