from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd

from app.models.registry import model_registry

logger = logging.getLogger(__name__)


def build_retrain_dataset(store, symbol: str | None = None) -> pd.DataFrame:
    """Gom outcomes đã resolve → dataset (features từ klines + label từ outcome).

    User override ưu tiên: outcome có user_override=True thay thế label auto.
    """
    outcomes = store.get_outcomes(limit=5000)
    if symbol:
        outcomes = [o for o in outcomes if o["symbol"] == symbol]
    if not outcomes:
        return pd.DataFrame()

    rows = []
    for o in outcomes:
        if o["outcome"] not in ("win", "lose"):
            continue
        candles = store.get_klines(o["symbol"], o["timeframe"], limit=60)
        if len(candles) < 30:
            continue
        df = pd.DataFrame(candles)
        feats = _features(df)
        if feats.empty:
            continue
        label = 1 if o["outcome"] == "win" else 0
        rows.append(
            {
                "symbol": o["symbol"],
                "timeframe": o["timeframe"],
                "model": o.get("model"),
                "label": label,
                "user_override": o.get("user_override", False),
                **{c: feats[c].iloc[-1] for c in feats.columns},
            }
        )
    return pd.DataFrame(rows)


def _features(df: pd.DataFrame) -> pd.DataFrame:
    from app.forecast.features import build_features

    feats = build_features(df)
    cols = [
        c
        for c in feats.columns
        if c not in ("close", "open", "high", "low", "volume", "taker_buy_base", "close_time")
    ]
    return feats[cols]


def retrain_from_outcomes(store, symbol: str, timeframe: str, model_kind: str, registry=None) -> str | None:
    """Retrain model từ outcomes thật; champion-challenger: chỉ replace nếu thắng eval.

    Returns model name mới, None nếu không đủ data hoặc không thắng.
    """
    reg = registry or model_registry
    dataset = build_retrain_dataset(store, symbol=symbol)
    if dataset.empty or len(dataset) < 20:
        logger.info("not enough outcomes to retrain %s %s", symbol, timeframe)
        return None

    from app.models.intraday import train_intraday

    # lấy klines mới nhất để train (outcomes là label bổ sung — dùng klines chính)
    candles = store.get_klines(symbol, timeframe, limit=5000)
    if len(candles) < 60:
        return None

    # train model mới (giữ model cũ để champion-challenger)
    old_name = f"{model_kind}@{symbol}@{timeframe}"
    name = train_intraday(symbol, timeframe, candles, registry=reg)
    if reg.has(old_name):
        # champion-challenger: so Brier trên outcomes thật
        new_brier = _outcome_brier(dataset, name, reg)
        old_brier = _outcome_brier(dataset, old_name, reg)
        if old_brier is not None and new_brier is not None and new_brier >= old_brier:
            logger.info("new model %s not better (brier %.4f vs %.4f) — keep old", name, new_brier, old_brier)
            reg._model_path(name).unlink(missing_ok=True)
            reg._meta_path(name).unlink(missing_ok=True)
            return None
    return name


def _outcome_brier(dataset: pd.DataFrame, model_name: str, reg=None) -> float | None:
    """Brier score của model trên outcomes thật (dùng predict_proba)."""
    import numpy as np

    from app.forecast.metrics import brier_score

    reg = reg or model_registry
    try:
        model, _ = reg.load_model(model_name)
    except Exception:
        return None
    clf = model.get("clf") if isinstance(model, dict) else model
    numeric = dataset.select_dtypes(include=["number"]).columns.tolist()
    feature_cols = [
        c for c in numeric if c not in ("label", "user_override")
    ]
    # chỉ giữ 9 feature chuẩn của intraday (khớp n_features_in_)
    from app.models.intraday import FEATURE_COLS as INTRADAY_COLS

    feature_cols = [c for c in INTRADAY_COLS if c in feature_cols]
    X = dataset[feature_cols].to_numpy(dtype=float)
    proba = clf.predict_proba(X)
    p = proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]
    return float(brier_score(dataset["label"].to_numpy(), p))
