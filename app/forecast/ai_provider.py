from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

from pydantic import ValidationError

from app.config import settings
from app.forecast.llm_client import LLMClient
from app.forecast.schema import ForecastContext, Signal, SignalDirection, SignalStatus
from app.forecast.provider import ForecastProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a crypto market analyst. Respond ONLY with a JSON object matching "
    'this exact schema: {"direction": "LONG"|"SHORT"|"FLAT", "probability": float '
    'between 0 and 1, "entry": float, "take_profit": [float], "stop_loss": float, '
    '"rr_ratio": float}. No extra text, no markdown, no code fences. '
    "Use ONLY the historical candles provided (past data). "
    "probability must reflect real confidence — 0.62 means you expect ~62% win rate."
)


class TokenBudget:
    """Daily token budget tracker (per-day window, rough estimate)."""

    def __init__(self, daily_budget: int):
        self.daily_budget = daily_budget
        self._day = None
        self._used = 0

    def record(self, tokens: int) -> None:
        today = datetime.now(UTC).date()
        if self._day != today:
            self._day = today
            self._used = 0
        self._used += tokens

    def over_budget(self, estimated: int = 0) -> bool:
        today = datetime.now(UTC).date()
        if self._day != today:
            self._day = today
            self._used = 0
        return (self._used + estimated) > self.daily_budget

    @property
    def used(self) -> int:
        return self._used


class AIProvider(ForecastProvider):
    """LLM-based forecast provider — dual-mode (9router subscription / API key).

    JSON mode + Pydantic validate + retry 1 lần + fail-open (signal failed).
    """

    name = "ai"

    def __init__(self, client: LLMClient | None = None, budget: TokenBudget | None = None):
        self.client = client or LLMClient(
            base_url=settings.ai_base_url,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
        )
        self.budget = budget or TokenBudget(settings.ai_daily_token_budget)

    def forecast(self, ctx: ForecastContext) -> Signal:
        if self.budget.over_budget():
            logger.warning("AI token budget exceeded — skipping")
            return self._failed_signal(ctx, "token budget exceeded")

        user_prompt = self._build_prompt(ctx)
        try:
            signal = self._attempt(ctx, user_prompt)
            if signal.status == SignalStatus.FAILED:
                # retry 1 lần kèm error message
                user_prompt_retry = user_prompt + (
                    "\n\nYour previous response was invalid. Error: "
                    f"{signal.model}. Fix the JSON and respond again."
                )
                signal = self._attempt(ctx, user_prompt_retry)
            return signal
        except Exception as e:
            logger.warning("AI provider failed: %s", e)
            return self._failed_signal(ctx, str(e))

    def _attempt(self, ctx: ForecastContext, user_prompt: str) -> Signal:
        try:
            raw = self.client.chat_json(SYSTEM_PROMPT, user_prompt)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("AI non-JSON response: %s", e)
            return self._failed_signal(ctx, f"non-JSON response: {e}")
        return self._parse_signal(ctx, raw)

    def _build_prompt(self, ctx: ForecastContext) -> str:
        # context tối giản: 30 candles gần nhất, chỉ OHLCV
        recent = ctx.candles[-30:]
        lines = [
            f"Symbol: {ctx.symbol}  Timeframe: {ctx.timeframe}",
            "Recent closed candles (open_time, open, high, low, close, volume):",
        ]
        for c in recent:
            ot = c["open_time"]
            ot_s = ot.isoformat() if hasattr(ot, "isoformat") else str(ot)
            lines.append(
                f"{ot_s},{c['open']},{c['high']},{c['low']},{c['close']},{c['volume']}"
            )
        return "\n".join(lines)

    def _parse_signal(self, ctx: ForecastContext, raw: dict) -> Signal:
        try:
            sig = Signal(
                symbol=ctx.symbol,
                timeframe=ctx.timeframe,
                direction=SignalDirection(raw["direction"]),
                probability=float(raw["probability"]),
                entry=float(raw.get("entry")) if raw.get("entry") is not None else None,
                take_profit=[float(x) for x in raw.get("take_profit", [])],
                stop_loss=float(raw["stop_loss"]) if raw.get("stop_loss") is not None else None,
                rr_ratio=float(raw["rr_ratio"]) if raw.get("rr_ratio") is not None else None,
                model=self.name,
            )
            return sig
        except (ValidationError, KeyError, TypeError, ValueError) as e:
            logger.warning("AI invalid signal schema: %s (raw=%s)", e, raw)
            return self._failed_signal(ctx, f"invalid schema: {e}")

    def _failed_signal(self, ctx: ForecastContext, reason: str) -> Signal:
        return Signal(
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            direction=SignalDirection.FLAT,
            probability=0.5,
            model=self.name,
            status=SignalStatus.FAILED,
        )
