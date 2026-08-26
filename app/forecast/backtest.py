from __future__ import annotations

import numpy as np

FEE_RATE = 0.001  # 0.1% per side
SLIPPAGE = 0.0005  # 0.05%


def simulate_trades(
    entries: np.ndarray,
    directions: np.ndarray,  # +1 LONG, -1 SHORT
    exits: np.ndarray,
    fee_rate: float = FEE_RATE,
    slippage: float = SLIPPAGE,
) -> dict:
    """Simulate round-trip trades with fees + slippage. Returns P&L stats.

    PnL per trade = direction * (exit/entry - 1) - 2*fee - 2*slippage
    (slippage applied on both entry and exit as fraction of price).
    """
    entries = np.asarray(entries, dtype=float)
    exits = np.asarray(exits, dtype=float)
    directions = np.asarray(directions, dtype=float)
    if len(entries) == 0:
        return {"n": 0, "total_pnl": 0.0, "win_rate": 0.0, "avg_pnl": 0.0}

    gross = directions * (exits / entries - 1)
    cost = 2 * fee_rate + 2 * slippage
    pnl = gross - cost
    wins = pnl > 0
    return {
        "n": int(len(pnl)),
        "total_pnl": float(pnl.sum()),
        "win_rate": float(wins.mean()) if len(pnl) else 0.0,
        "avg_pnl": float(pnl.mean()),
    }
