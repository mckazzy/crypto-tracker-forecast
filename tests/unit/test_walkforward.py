import numpy as np
import pandas as pd
import pytest

from app.forecast.walkforward import (
    evaluate_walkforward,
    expanding_windows,
    fit_predict_baseline,
)


def make_df(n=200, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    closes = 40000 + np.cumsum(rng.normal(0, 50, n))
    return pd.DataFrame(
        {"close": closes, "open": closes, "high": closes * 1.01, "low": closes * 0.99},
        index=idx,
    )


class TestExpandingWindows:
    def test_basic_splits(self):
        splits = list(expanding_windows(100, train_size=30, test_size=10, embargo=1))
        # start: 30 → 40 → 50 → 60 → 70 → 80 (90+1+10=101 > 100 stop)
        assert len(splits) == 6
        first_train, first_test = splits[0]
        assert first_train == slice(0, 30)
        assert first_test == slice(31, 41)  # embargo 1

    def test_embargo_enforced(self):
        _, test = list(expanding_windows(100, 30, 10, embargo=2))[0]
        assert test == slice(32, 42)

    def test_respects_bounds(self):
        splits = list(expanding_windows(50, 20, 10, embargo=0))
        # start 20,30,40 → 3 splits; 50+0 not < 50... 40+0+10=50 ok
        assert len(splits) == 3


class TestEvaluateWalkforward:
    def test_runs_and_returns_metrics(self):
        df = make_df(300)
        res = evaluate_walkforward(
            df,
            fit_predict_baseline,
            train_size=60,
            test_size=20,
            embargo=1,
            horizon=1,
        )
        assert res["n"] > 0
        assert 0.0 <= res["directional_accuracy"] <= 1.0
        assert 0.0 <= res["brier_score"] <= 1.0
        assert 0.0 <= res["hit_rate_band"] <= 1.0

    def test_n_zero_when_too_little_data(self):
        df = make_df(40)
        res = evaluate_walkforward(df, fit_predict_baseline, train_size=60, test_size=20)
        assert res["n"] == 0
