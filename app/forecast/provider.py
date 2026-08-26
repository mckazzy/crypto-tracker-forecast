from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.forecast.schema import ForecastContext, Signal


@runtime_checkable
class ForecastProvider(Protocol):
    """Contract chuẩn cho mọi provider (local ML, AI, baseline)."""

    name: str

    def forecast(self, ctx: ForecastContext) -> Signal: ...
