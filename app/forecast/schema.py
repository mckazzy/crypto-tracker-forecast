from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class SignalStatus(str, Enum):
    OK = "ok"
    FAILED = "failed"


class Signal(BaseModel):
    """Chuẩn output của mọi ForecastProvider — JSON mode compatible."""

    version: str = "1.0"
    symbol: str
    timeframe: str
    direction: SignalDirection
    probability: float = Field(ge=0.0, le=1.0)
    entry: float | None = None
    take_profit: list[float] = Field(default_factory=list)
    stop_loss: float | None = None
    rr_ratio: float | None = None
    model: str
    valid_until: datetime | None = None
    status: SignalStatus = SignalStatus.OK
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    token_cost: int = 0

    @field_validator("take_profit")
    @classmethod
    def _tp_positive(cls, v: list[float]) -> list[float]:
        for tp in v:
            if tp <= 0:
                raise ValueError("take_profit must be positive")
        return v

    @field_validator("entry", "stop_loss")
    @classmethod
    def _price_positive(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("price must be positive")
        return v


@dataclass
class ForecastContext:
    """Input context cho provider — candles gần đây + indicator snapshot."""

    symbol: str
    timeframe: str
    candles: list[dict] = field(default_factory=list)
    indicators: dict = field(default_factory=dict)
    as_of: datetime | None = None


class UserForecastInput(BaseModel):
    """Payload từ UI khi người dùng tự tạo dự đoán của mình."""

    symbol: str
    timeframe: str
    direction: SignalDirection
    entry: float | None = None
    take_profit: list[float] = Field(default_factory=list)
    stop_loss: float | None = None
    probability: float = Field(default=1.0, ge=0.0, le=1.0)
