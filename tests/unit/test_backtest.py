import numpy as np
import pytest

from app.forecast.backtest import simulate_trades


class TestSimulateTrades:
    def test_profitable_long(self):
        res = simulate_trades(
            entries=np.array([100.0]),
            directions=np.array([1.0]),
            exits=np.array([110.0]),
        )
        # gross 10%, cost 2*0.001 + 2*0.0005 = 0.003 → pnl 9.7%
        assert res["n"] == 1
        assert abs(res["avg_pnl"] - (0.10 - 0.003)) < 1e-9
        assert res["win_rate"] == 1.0

    def test_profitable_short(self):
        res = simulate_trades(
            entries=np.array([100.0]),
            directions=np.array([-1.0]),
            exits=np.array([90.0]),
        )
        assert abs(res["avg_pnl"] - (0.10 - 0.003)) < 1e-9

    def test_fees_wipe_small_gain(self):
        res = simulate_trades(
            entries=np.array([100.0]),
            directions=np.array([1.0]),
            exits=np.array([100.2]),  # 0.2% gross < 0.3% cost
        )
        assert res["avg_pnl"] < 0

    def test_empty(self):
        res = simulate_trades(np.array([]), np.array([]), np.array([]))
        assert res["n"] == 0

    def test_mixed(self):
        res = simulate_trades(
            entries=np.array([100.0, 100.0]),
            directions=np.array([1.0, -1.0]),
            exits=np.array([110.0, 110.0]),  # long +10%, short -10% gross
        )
        assert res["n"] == 2
        assert abs(res["avg_pnl"] - (0.0 - 0.003)) < 1e-9
        assert res["win_rate"] == 0.5
