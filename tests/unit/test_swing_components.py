from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.models.labels import (
    TripleBarrierLabeler,
    primary_signal_ema_breakout,
    stack_mtf_features,
)
from app.models.regimes import HMMRegimeFilter


def make_ohlcv(n=120, seed=1):
    rng = np.random.default_rng(seed)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    closes = 40000 * np.exp(np.cumsum(rng.normal(0.0002, 0.003, n)))
    out = []
    for i in range(n):
        ot = t0 + timedelta(hours=i)
        c = float(closes[i])
        o = float(closes[i - 1]) if i > 0 else c
        out.append(
            {
                "open_time": ot,
                "open": o,
                "high": max(o, c) * 1.003,
                "low": min(o, c) * 0.997,
                "close": c,
                "volume": 100.0,
                "taker_buy_base": 55.0,
            }
        )
    return out


class TestTripleBarrierLabeler:
    def test_labels_within_range(self):
        labeler = TripleBarrierLabeler(tp_pct=0.01, sl_pct=0.01, max_hold=5)
        labels = labeler.label(make_ohlcv(60, seed=2))
        assert set(np.unique(labels)) <= {1.0, -1.0, 0.0}
        assert len(labels) == 60

    def test_known_uptrend_labels(self):
        """Strong uptrend: hầu hết label = +1 (chạm TP trước SL)."""
        candles = []
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        price = 100.0
        for i in range(60):
            ot = t0 + timedelta(hours=i)
            price *= 1.005  # +0.5% mỗi candle — uptrend mạnh
            candles.append(
                {
                    "open_time": ot,
                    "open": price / 1.005,
                    "high": price * 1.01,
                    "low": price / 1.01,
                    "close": price,
                    "volume": 100.0,
                    "taker_buy_base": 55.0,
                }
            )
        labeler = TripleBarrierLabeler(tp_pct=0.005, sl_pct=0.01, max_hold=5)
        labels = labeler.label(candles)
        # không look-ahead: label cuối (không đủ future) = 0
        positives = np.sum(labels == 1.0)
        negatives = np.sum(labels == -1.0)
        assert positives > negatives

    def test_no_lookahead_last_label_zero(self):
        labeler = TripleBarrierLabeler(tp_pct=0.01, sl_pct=0.01, max_hold=5)
        labels = labeler.label(make_ohlcv(30, seed=5))
        # vài label cuối = 0 (không đủ max_hold candles phía trước)
        assert labels[-1] == 0.0


class TestPrimarySignal:
    def test_ema_cross_generates_entries(self):
        entries = primary_signal_ema_breakout(make_ohlcv(100, seed=3))
        assert isinstance(entries, np.ndarray)
        assert entries.dtype == bool
        assert entries.shape[0] == 100

    def test_not_all_entries(self):
        entries = primary_signal_ema_breakout(make_ohlcv(80, seed=4))
        assert entries.sum() < len(entries)  # không phải mọi candle đều là entry


class TestHMMRegimeFilter:
    def test_fit_predict_regime_probs(self):
        filter_ = HMMRegimeFilter(n_states=3)
        closes = [c["close"] for c in make_ohlcv(120, seed=6)]
        probs = filter_.fit_predict_probs(closes)
        assert probs.shape[0] == len(closes)
        assert probs.shape[1] == 3
        # mỗi row sum ~ 1
        np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-6)

    def test_short_series_raises(self):
        filter_ = HMMRegimeFilter(n_states=3)
        with pytest.raises(ValueError):
            filter_.fit_predict_probs([100.0, 101.0, 102.0])


class TestMTFStacking:
    def test_align_lagged_no_lookahead(self):
        # 1h series, 4h features: feature tại t chỉ dùng candle 4h đã đóng trước t
        rng = np.random.default_rng(0)
        n = 40
        slow = np.array([rng.normal(0, 1) for _ in range(n // 4)])  # 10 4h-candles
        aligned = stack_mtf_features(n, slow, ratio=4)
        assert len(aligned) == n
        # aligned[0..3] (trong 4h đầu) dùng slow[0] — nhưng slow[0] chưa đóng
        # tại t<4; theo thiết kế ta dùng slow[i//4 - 1] (previous closed)
        # → aligned[0..3] phải bằng slow[-1] sentinel? Kiểm tra: không look-ahead
        # bằng cách so aligned[4] == slow[0] (4h đầu đóng tại t=4)
        assert aligned[4] == slow[0]
        assert np.isnan(aligned[0])  # chưa có 4h nào đóng → NaN, không giả dữ liệu

    def test_lag_uses_previous_closed(self):
        n = 8
        slow = np.array([10.0, 20.0])  # 2 4h candles
        aligned = stack_mtf_features(n, slow, ratio=4)
        # tại t=0..3 chưa có 4h đóng → NaN hoặc sentinel; t=4..7 dùng slow[0]
        assert aligned[4] == 10.0
        assert aligned[5] == 10.0
