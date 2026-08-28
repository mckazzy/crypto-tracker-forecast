"""Binance USDT-M isolated-margin formulas (pure functions, no IO).

Demo approximation: trading fees (~0.05% taker) are intentionally ignored.
Liq price includes a 0.5% maintenance-margin buffer (MMR) so liquidation
fires before bankruptcy price — closer to real Binance behavior.
"""


def calc_margin(qty: float, entry: float, leverage: int) -> float:
    """Isolated margin required: qty * entry / leverage."""
    return qty * entry / leverage


def calc_liq_price(entry: float, leverage: int, side: str, mmr: float = 0.005) -> float:
    """Liquidation price with MMR buffer.

    LONG:  entry * (1 - 1/leverage + mmr)  — higher than bankruptcy price
    SHORT: entry * (1 + 1/leverage - mmr)  — lower than bankruptcy price
    """
    if side.upper() == "LONG":
        return entry * (1 - 1 / leverage + mmr)
    return entry * (1 + 1 / leverage - mmr)


def calc_pnl(entry: float, mark: float, qty: float, side: str) -> float:
    """Unrealized/realized PnL."""
    if side.upper() == "LONG":
        return (mark - entry) * qty
    return (entry - mark) * qty


def calc_roi(pnl: float, margin: float) -> float:
    """Return on margin; 0 when margin is 0 (guard div-by-zero)."""
    if margin == 0:
        return 0.0
    return pnl / margin


def calc_close_balance(balance: float, margin: float, pnl: float) -> float:
    """Balance after closing a position; never negative."""
    return max(0.0, balance + margin + pnl)


def calc_liq_balance(balance: float) -> float:
    """Balance after liquidation: margin is lost, balance unchanged (never negative)."""
    return max(0.0, balance)


def calc_margin_available(balance: float, margin_used: float) -> float:
    """Free margin available for new positions; clamped >= 0."""
    return max(0.0, balance - margin_used)


def calc_qty_from_notional(notional_usdt: float, mark: float, precision: int = 6) -> float:
    """Convert notional USDT to coin qty, rounded to `precision` decimals."""
    return round(notional_usdt / mark, precision)
