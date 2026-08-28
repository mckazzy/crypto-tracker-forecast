from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.storage.duckdb_store import DuckDBStore
from app.trading.retrain import (
    build_retrain_dataset,
    compute_sample_weights,
    evaluate_model_on_outcomes,
    retrain_from_outcomes,
    retrain_from_outcomes_detailed,
)


@pytest.fixture
def store(tmp_duckdb, monkeypatch) -> DuckDBStore:
    s = DuckDBStore(tmp_duckdb)
    return s


def make_candles(n=60, seed=1):
    rng = np.random.default_rng(seed)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    closes = 40000 + np.cumsum(rng.normal(0, 50, n))
    rows = []
    for i in range(n):
        ot = t0 + timedelta(hours=i)
        c = float(closes[i])
        o = float(closes[i - 1]) if i else c
        rows.append(
            {
                "open_time": ot,
                "close_time": ot + timedelta(hours=1) - timedelta(milliseconds=1),
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "open": o,
                "high": max(o, c) * 1.01,
                "low": min(o, c) * 0.99,
                "close": c,
                "volume": 100.0,
                "close_volume": 60.0,
                "trades": 100,
                "taker_buy_base": 55.0,
            }
        )
    return rows


def seed_outcomes(store, n=30):
    for i in range(n):
        store.save_outcome(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "LONG" if i % 2 == 0 else "SHORT",
                "outcome": "win" if i % 3 == 0 else "lose",
                "entry": 100.0,
                "tp": 108.0,
                "sl": 90.0,
                "model": "test",
                "source": "auto-score",
                "score": 95.0 if i % 3 == 0 else -50.0,
                "resolved_at": (datetime(2026, 1, 2, tzinfo=UTC) + timedelta(hours=i)).isoformat(),
            }
        )


class TestBuildRetrainDataset:
    def test_empty_no_outcomes(self, store):
        df = build_retrain_dataset(store)
        assert df.empty

    def test_builds_rows_with_labels_and_weights(self, store, tmp_duckdb):
        store.upsert_klines(make_candles(60))
        seed_outcomes(store, 5)
        df = build_retrain_dataset(store, symbol="BTCUSDT")
        assert len(df) == 5
        assert set(df["label"]) <= {0.0, 1.0}
        assert "sample_weight" in df.columns
        assert (df["sample_weight"] >= 1.0).all()
        assert "rsi_14" in df.columns  # features từ klines

    def test_user_override_priority(self, store):
        store.upsert_klines(make_candles(60))
        store.save_outcome(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "direction": "LONG",
                "outcome": "win",
                "user_override": True,
                "source": "user",
            }
        )
        df = build_retrain_dataset(store, symbol="BTCUSDT")
        assert len(df) == 1
        assert df.iloc[0]["label"] == 1.0
        assert df.iloc[0]["sample_weight"] >= 3.5  # user override has highest sample weight boost


class TestSampleWeightsAndEvaluation:
    def test_compute_sample_weights_decay_and_boost(self):
        candles = make_candles(30)
        weights = compute_sample_weights(candles)
        assert len(weights) == 30
        assert weights[-1] > weights[0]  # recency decay: recent candles have higher weight

    def test_evaluate_model_on_outcomes(self, store, tmp_path, monkeypatch):
        from app.models.registry import ModelRegistry
        from app.models.intraday import train_intraday

        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        candles = make_candles(80)
        store.upsert_klines(candles)
        name = train_intraday("BTCUSDT", "1h", candles, registry=reg)

        seed_outcomes(store, 10)
        df = build_retrain_dataset(store, symbol="BTCUSDT")
        metrics = evaluate_model_on_outcomes(df, name, reg=reg)
        assert metrics is not None
        assert "brier" in metrics
        assert "accuracy" in metrics
        assert 0.0 <= metrics["brier"] <= 1.0
        assert 0.0 <= metrics["accuracy"] <= 1.0


class TestRetrainFromOutcomes:
    def test_returns_none_without_data(self, store):
        res = retrain_from_outcomes_detailed(store, "BTCUSDT", "1h", "intraday_lgbm", min_outcomes=5)
        assert res["retrained"] is False
        assert "Chưa đủ dữ liệu" in res["message"]

    def test_retrains_with_adaptive_outcomes_and_detailed_report(self, store, tmp_path, monkeypatch):
        from app.models.registry import ModelRegistry

        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.trading.retrain.model_registry", reg)

        store.upsert_klines(make_candles(150))
        seed_outcomes(store, 10)  # 10 outcomes >= min_outcomes=5

        res = retrain_from_outcomes_detailed(store, "BTCUSDT", "1h", "intraday_lgbm", min_outcomes=5, registry=reg)
        assert "retrained" in res
        assert "outcomes_used" in res
        assert res["outcomes_used"] == 10
        assert "message" in res
        name = res.get("model")
        if res.get("retrained"):
            assert reg.has(name)
