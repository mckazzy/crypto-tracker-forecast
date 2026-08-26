from __future__ import annotations

import logging

import numpy as np

from app.forecast.backtest import simulate_trades

logger = logging.getLogger(__name__)


def compute_pnl(direction: str, entry: float, exit_price: float) -> float:
    """P&L với fee 0.1%/side + slippage 0.05%/side (dùng simulate_trades SP2)."""
    d = 1.0 if direction == "LONG" else -1.0
    res = simulate_trades(
        entries=np.array([entry]),
        directions=np.array([d]),
        exits=np.array([exit_price]),
    )
    return float(res["avg_pnl"])


def check_barrier(direction: str, high: float, low: float, tp: float, sl: float) -> str | None:
    """Kiểm tra candle high/low chạm barrier nào trước.

    Conservative: nếu cả TP và SL cùng chạm trong 1 candle, ưu tiên SL (thị trường có thể đảo).
    """
    hit_tp = high >= tp if direction == "LONG" else low <= tp
    hit_sl = low <= sl if direction == "LONG" else high >= sl
    if hit_sl:
        return "SL"
    if hit_tp:
        return "TP"
    return None


def resolve_open_positions(store, candles_by_key: dict) -> int:
    """Scan klines mới cho mọi vị thế open; đóng vị thế chạm TP/SL. Returns count closed."""
    closed = 0
    positions = store.get_positions(status="open")
    for pos in positions:
        key = (pos["symbol"], pos["timeframe"])
        candles = candles_by_key.get(key)
        if not candles:
            continue
        barrier = _scan_barriers(pos, candles)
        if barrier is None:
            continue
        if barrier == "TP":
            exit_price = pos["tp"]
        else:
            exit_price = pos["sl"]
        pnl = compute_pnl(pos["direction"], pos["entry"], exit_price)
        store.close_position(pos["id"], exit_price, pnl)
        closed += 1
        logger.info("position %d closed via %s pnl=%.4f", pos["id"], barrier, pnl)
    return closed


def _scan_barriers(pos: dict, candles: list[dict]) -> str | None:
    """Scan từ candle sau opened_at (candle đóng) — tìm barrier đầu tiên chạm."""
    from datetime import UTC, datetime

    raw = pos["opened_at"]
    if isinstance(raw, str):
        opened_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    else:
        opened_at = raw
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=UTC)
    else:
        opened_at = opened_at.astimezone(UTC)
    for c in candles:
        ot = c["open_time"]
        if ot.tzinfo is None:
            ot = ot.replace(tzinfo=UTC)
        else:
            ot = ot.astimezone(UTC)
        if ot <= opened_at:
            continue
        hit = check_barrier(pos["direction"], c["high"], c["low"], pos["tp"], pos["sl"])
        if hit:
            return hit
    return None
