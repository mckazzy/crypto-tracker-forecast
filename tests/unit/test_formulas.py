import pytest

from app.trading.formulas import (
    calc_close_balance,
    calc_liq_balance,
    calc_liq_price,
    calc_margin,
    calc_margin_available,
    calc_pnl,
    calc_qty_from_notional,
    calc_roi,
)


class TestCalcMargin:
    def test_normal(self):
        assert calc_margin(2.0, 50000.0, 10) == 10000.0

    def test_leverage_one(self):
        assert calc_margin(1.0, 100.0, 1) == 100.0

    def test_zero_qty(self):
        assert calc_margin(0.0, 100.0, 10) == 0.0


class TestCalcLiqPrice:
    def test_long_buffer_higher_than_bankruptcy(self):
        # entry=100, lev=10: bankruptcy 90.0, liq với MMR buffer 0.5% = 90.5
        assert calc_liq_price(100.0, 10, "LONG") == 90.5

    def test_short_buffer_lower_than_bankruptcy(self):
        # entry=100, lev=10: bankruptcy 110.0, liq = 109.5
        assert calc_liq_price(100.0, 10, "SHORT") == pytest.approx(109.5)

    def test_long_leverage_one(self):
        # 100 * (1 - 1 + 0.005) = 0.5
        assert calc_liq_price(100.0, 1, "LONG") == 0.5

    def test_short_leverage_one(self):
        # 100 * (1 + 1 - 0.005) = 199.5
        assert calc_liq_price(100.0, 1, "SHORT") == 199.5


class TestCalcPnl:
    def test_long_profit(self):
        assert calc_pnl(50000.0, 51000.0, 1.0, "LONG") == 1000.0

    def test_long_loss(self):
        assert calc_pnl(50000.0, 49000.0, 1.0, "LONG") == -1000.0

    def test_short_profit(self):
        assert calc_pnl(50000.0, 49000.0, 1.0, "SHORT") == 1000.0

    def test_mark_equals_entry_zero(self):
        assert calc_pnl(50000.0, 50000.0, 2.5, "LONG") == 0.0


class TestCalcRoi:
    def test_normal(self):
        assert calc_roi(1000.0, 10000.0) == 0.1

    def test_zero_margin_guard(self):
        assert calc_roi(1000.0, 0.0) == 0.0


class TestCalcCloseBalance:
    def test_win_credits_margin_plus_pnl(self):
        assert calc_close_balance(5000.0, 1000.0, 500.0) == 6500.0

    def test_lose_reduces_balance(self):
        assert calc_close_balance(5000.0, 1000.0, -800.0) == 5200.0

    def test_loss_bigger_than_balance_clamps_zero(self):
        assert calc_close_balance(10.0, 1000.0, -1500.0) == 0.0


class TestCalcLiqBalance:
    def test_margin_lost_balance_unchanged(self):
        # Liquidation: margin coi như mất, balance không âm
        assert calc_liq_balance(5000.0) == 5000.0

    def test_zero_balance(self):
        assert calc_liq_balance(0.0) == 0.0


class TestCalcMarginAvailable:
    def test_normal(self):
        assert calc_margin_available(10000.0, 4000.0) == 6000.0

    def test_margin_used_exceeds_balance_clamps_zero(self):
        assert calc_margin_available(1000.0, 2000.0) == 0.0


class TestCalcQtyFromNotional:
    def test_normal(self):
        assert calc_qty_from_notional(100.0, 50000.0) == 0.002

    def test_precision_six(self):
        # 100 / 33333.333333 → 0.003 làm tròn 6 chữ số
        assert calc_qty_from_notional(100.0, 33333.333333) == 0.003

    def test_large_notional(self):
        assert calc_qty_from_notional(100000.0, 50000.0) == 2.0
