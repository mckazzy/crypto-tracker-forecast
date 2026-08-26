from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.trading.positions import check_barrier

logger = logging.getLogger(__name__)


def auto_resolve_outcome(symbol: str, timeframe: str, direction: str, entry: float, tp: float, sl: float, candles: list[dict]) -> str | None:
    """Tự resolve outcome từ klines: TP → win, SL → lose, chưa chạm → None."""
    for c in candles:
        hit = check_barrier(direction, c["high"], c["low"], tp, sl)
        if hit == "TP":
            return "win"
        if hit == "SL":
            return "lose"
    return None


def user_override_allowed(store, min_signals: int) -> bool:
    """Track-record guard: user override chỉ tính nếu đã có ≥ min_signals outcomes."""
    count = store.count_outcomes()
    return count >= min_signals
