import numpy as np
import pandas as pd
import pytest

from app.forecast.metrics import (
    brier_score,
    directional_accuracy,
    hit_rate_band,
)


class TestDirectionalAccuracy:
    def test_perfect(self):
        y = np.array([1, 0, 1, 1, 0])
        p = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
        assert directional_accuracy(y, p) == 1.0

    def test_worst(self):
        y = np.array([1, 0])
        p = np.array([0.0, 1.0])
        assert directional_accuracy(y, p) == 0.0

    def test_random(self):
        y = np.array([1, 0, 1])
        p = np.array([0.5, 0.5, 0.5])
        # p >= 0.5 → predict up → matches y[0], y[2] = 2/3
        assert abs(directional_accuracy(y, p) - 2 / 3) < 1e-9


class TestBrierScore:
    def test_perfect(self):
        y = np.array([1, 0, 1])
        p = np.array([1.0, 0.0, 1.0])
        assert brier_score(y, p) == 0.0

    def test_calibrated_reference(self):
        # p=0.62 should score better than random 0.5 when y matches freq
        y = np.array([1, 1, 1, 1, 1, 1, 0, 0, 0, 0])
        p = np.full(10, 0.62)
        assert brier_score(y, p) < brier_score(y, np.full(10, 0.5))

    def test_always_wrong(self):
        y = np.array([1, 0])
        p = np.array([0.0, 1.0])
        assert brier_score(y, p) == 1.0


class TestHitRateBand:
    def test_target_band_coverage(self):
        """close in [low, high] of predicted band → hit."""
        lows = np.array([100.0, 100.0, 100.0])
        highs = np.array([110.0, 110.0, 110.0])
        closes = np.array([105.0, 95.0, 112.0])
        rate = hit_rate_band(lows, highs, closes)
        assert rate == 1 / 3

    def test_all_hit(self):
        lows = np.array([100.0])
        highs = np.array([110.0])
        closes = np.array([107.5])
        assert hit_rate_band(lows, highs, closes) == 1.0

    def test_none_hit(self):
        lows = np.array([100.0])
        highs = np.array([110.0])
        closes = np.array([50.0])
        assert hit_rate_band(lows, highs, closes) == 0.0
