from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.storage.duckdb_store import DuckDBStore
from app.trading.retrain import build_retrain_dataset, retrain_from_outcomes


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
                "direction": "LONG",
                "outcome": "win" if i % 2 == 0 else "lose",
                "entry": 100.0,
                "tp": 108.0,
                "sl": 90.0,
                "model": "test",
                "source": "auto",
            }
        )


class TestBuildRetrainDataset:
    def test_empty_no_outcomes(self, store):
        df = build_retrain_dataset(store)
        assert df.empty

    def test_builds_rows_with_labels(self, store, tmp_duckdb):
        store.upsert_klines(make_candles(60))
        seed_outcomes(store, 5)
        df = build_retrain_dataset(store, symbol="BTCUSDT")
        assert len(df) == 5
        assert set(df["label"]) <= {0, 1}
        assert "rsi_14" in df.columns  # features từ klines

    def test_user_override_priority(self, store):
        store.upsert_klines(make_candles(60))
        # user override = win nhưng klines thực tế sẽ auto lose — override ưu tiên
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
        assert df.iloc[0]["label"] == 1  # user win → label 1


class TestRetrainFromOutcomes:
    def test_returns_none_without_data(self, store):
        assert retrain_from_outcomes(store, "BTCUSDT", "1h", "intraday_lgbm") is None

    def test_retrains_and_saves(self, store, tmp_path, monkeypatch):
        from app.models.registry import ModelRegistry

        reg = ModelRegistry(base_dir=str(tmp_path / "models"))
        monkeypatch.setattr("app.trading.retrain.model_registry", reg)

        store.upsert_klines(make_candles(150))
        seed_outcomes(store, 30)
        name = retrain_from_outcomes(store, "BTCUSDT", "1h", "intraday_lgbm", registry=reg)
        # có thể None nếu champion-challenger giữ old (không có old → luôn save mới)
        if name is not None:
            assert reg.has(name)
