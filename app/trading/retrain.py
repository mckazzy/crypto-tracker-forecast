from __future__ import annotations

import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.models.intraday import FEATURE_COLS as INTRADAY_COLS
from app.models.registry import model_registry

logger = logging.getLogger(__name__)


def build_retrain_dataset(store, symbol: str | None = None, timeframe: str | None = None) -> pd.DataFrame:
    """Gom outcomes đã resolve → dataset với point-in-time features chuẩn và trọng số phản hồi.

    - Lấy nến tại đúng mốc thời gian phát tín hiệu (signal_id / created_at) thay vì nến hiện tại.
    - Nhãn chuẩn xác theo hướng: LONG win -> 1, SHORT win -> 0.
    - Trọng số mẫu thích ứng (Sample Weighting): User override (3.5x), Hard mistakes (4.0x).
    """
    outcomes = store.get_outcomes(limit=5000)
    if symbol:
        outcomes = [o for o in outcomes if o.get("symbol") == symbol]
    if timeframe:
        outcomes = [o for o in outcomes if o.get("timeframe") == timeframe]
    if not outcomes:
        return pd.DataFrame()

    rows = []
    for o in outcomes:
        outcome_val = o.get("outcome")
        if outcome_val not in ("win", "lose"):
            continue

        sym = o.get("symbol")
        tf = o.get("timeframe", "4h")
        direction = o.get("direction", "LONG")
        sig_id = o.get("signal_id")
        created_at_dt = None

        if sig_id:
            fc = store.get_forecast_by_id(sig_id)
            if fc and fc.get("created_at"):
                try:
                    created_at_dt = datetime.fromisoformat(fc["created_at"])
                    if created_at_dt.tzinfo is None:
                        created_at_dt = created_at_dt.replace(tzinfo=UTC)
                except ValueError:
                    created_at_dt = None

        # Trích xuất nến tại thời điểm tạo signal (nếu có mốc thời gian)
        if created_at_dt:
            candles = store.get_klines(sym, tf, end=created_at_dt, limit=60)
        else:
            candles = store.get_klines(sym, tf, limit=60)

        if not candles or len(candles) < 15:
            # Fallback lấy nến chung
            candles = store.get_klines(sym, tf, limit=60)
            if len(candles) < 15:
                continue

        df = pd.DataFrame(candles)
        feats = _features(df)
        if feats.empty:
            continue

        # Xác định nhãn (label) phản ánh chiều giá tăng (1) hay giảm (0)
        if direction == "LONG":
            label = 1.0 if outcome_val == "win" else 0.0
        elif direction == "SHORT":
            label = 0.0 if outcome_val == "win" else 1.0
        else:
            label = 1.0 if outcome_val == "win" else 0.0

        # Tính toán trọng số mẫu (Sample Weight)
        weight = 1.0
        user_override = bool(o.get("user_override", False))
        if user_override:
            weight *= 3.5  # Phản hồi từ con người có trọng số cao nhất
        elif o.get("source") == "auto-score":
            weight *= 2.0  # Kết quả chốt nến tự động

        score = o.get("score")
        if score is not None:
            if score < 0:
                weight *= 1.5  # Tăng trọng số cho các lệnh bị lỗ ngược hướng
            elif score >= 100:
                weight *= 1.3  # Thưởng thêm cho các lệnh đạt mục tiêu TP tối đa

        rows.append(
            {
                "symbol": sym,
                "timeframe": tf,
                "model": o.get("model"),
                "direction": direction,
                "label": label,
                "sample_weight": weight,
                "user_override": user_override,
                "score": score,
                "resolved_at": o.get("resolved_at"),
                **{c: feats[c].iloc[-1] for c in feats.columns if c in INTRADAY_COLS},
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


def compute_sample_weights(candles: list[dict], dataset: pd.DataFrame | None = None) -> np.ndarray:
    """Tạo mảng trọng số mẫu kết hợp Recency Decay và Feedback Boosting."""
    n = len(candles)
    if n == 0:
        return np.array([], dtype=float)

    # 1. Base weights: Recency exponential decay (nến mới nhất có trọng số x1.0, nến xa nhất x0.6)
    base_weights = np.exp(np.linspace(-0.5, 0.0, n))

    # 2. Feedback boost: nếu nến nằm gần các mốc outcomes đã resolve
    if dataset is not None and not dataset.empty and "resolved_at" in dataset.columns:
        resolved_dates = pd.to_datetime(dataset["resolved_at"].dropna(), utc=True)
        for i, c in enumerate(candles):
            ot = c.get("open_time")
            if ot:
                if isinstance(ot, str):
                    ot_dt = pd.to_datetime(ot, utc=True)
                else:
                    ot_dt = ot if ot.tzinfo else ot.replace(tzinfo=UTC)
                # Nếu nến nằm trong vòng 24h so với 1 outcome đã chốt
                diffs = np.abs((resolved_dates - ot_dt).dt.total_seconds().to_numpy())
                if len(diffs) > 0 and diffs.min() < 86400:
                    base_weights[i] *= 2.0

    return base_weights


def evaluate_model_on_outcomes(dataset: pd.DataFrame, model_name: str, reg=None) -> dict[str, float] | None:
    """Đánh giá model trên dataset outcomes bằng Brier Score và Directional Accuracy."""
    from app.forecast.metrics import brier_score, directional_accuracy

    reg = reg or model_registry
    try:
        model, _ = reg.load_model(model_name)
    except Exception:
        return None

    clf = model.get("clf") if isinstance(model, dict) else model
    feature_cols = [c for c in INTRADAY_COLS if c in dataset.columns]
    if len(feature_cols) < len(INTRADAY_COLS):
        return None

    X = dataset[feature_cols].to_numpy(dtype=float)
    y = dataset["label"].to_numpy(dtype=float)

    proba = clf.predict_proba(X)
    p = proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]

    brier = float(brier_score(y, p))
    acc = float(directional_accuracy(y, p))
    return {"brier": brier, "accuracy": acc}


def retrain_from_outcomes_detailed(
    store,
    symbol: str,
    timeframe: str,
    model_kind: str = "intraday_lgbm",
    min_outcomes: int = 5,
    registry=None,
) -> dict:
    """Retrain model từ feedback outcomes có kiểm tra Tournament đa tiêu chí và trọng số mẫu.

    Returns dict chứa:
    - retrained (bool): Có thay thế model mới hay không
    - model (str): Tên model
    - outcomes_used (int): Số outcomes dùng huấn luyện & kiểm tra
    - old_brier, new_brier, accuracy_gain, message
    """
    reg = registry or model_registry
    symbol_u = symbol.upper()
    tf = timeframe.lower()

    dataset = build_retrain_dataset(store, symbol=symbol_u, timeframe=tf)
    if dataset.empty or len(dataset) < min_outcomes:
        # Fallback thử gom outcomes của symbol không phân biệt timeframe nếu chưa đủ
        if dataset.empty or len(dataset) < min_outcomes:
            dataset = build_retrain_dataset(store, symbol=symbol_u)

    if dataset.empty or len(dataset) < min_outcomes:
        count = len(dataset) if not dataset.empty else 0
        msg = f"Chưa đủ dữ liệu phản hồi (cần ít nhất {min_outcomes} outcomes, hiện có {count})"
        logger.info(msg)
        return {
            "retrained": False,
            "model": f"{model_kind}@{symbol_u}@{tf}",
            "outcomes_used": count,
            "message": msg,
        }

    from app.models.intraday import train_intraday

    # Lấy klines lịch sử để train
    candles = store.get_klines(symbol_u, tf, limit=5000)
    if len(candles) < 30:
        return {
            "retrained": False,
            "model": f"{model_kind}@{symbol_u}@{tf}",
            "outcomes_used": len(dataset),
            "message": "Không đủ nến lịch sử để huấn luyện mô hình",
        }

    # Tính toán Sample Weights kết hợp Recency Decay và Feedback Boosting
    sample_weights = compute_sample_weights(candles, dataset)

    # Huấn luyện candidate challenger model
    old_name = f"{model_kind}@{symbol_u}@{tf}"
    has_old = reg.has(old_name)

    # Train challenger
    challenger_name = train_intraday(symbol_u, tf, candles, sample_weight=sample_weights, registry=reg)

    if has_old:
        # Champion-Challenger Tournament
        old_metrics = evaluate_model_on_outcomes(dataset, old_name, reg)
        new_metrics = evaluate_model_on_outcomes(dataset, challenger_name, reg)

        if old_metrics and new_metrics:
            old_brier = old_metrics["brier"]
            new_brier = new_metrics["brier"]
            old_acc = old_metrics["accuracy"]
            new_acc = new_metrics["accuracy"]

            # Challenger thắng nếu Brier thấp hơn (hoặc Brier tương đương nhưng Accuracy cao hơn)
            challenger_won = (new_brier < old_brier) or (new_brier <= old_brier * 1.02 and new_acc > old_acc)

            if not challenger_won:
                logger.info(
                    "New model %s not better (brier %.4f vs %.4f, acc %.1f%% vs %.1f%%) — keeping champion",
                    challenger_name,
                    new_brier,
                    old_brier,
                    new_acc * 100,
                    old_acc * 100,
                )
                reg._model_path(challenger_name).unlink(missing_ok=True)
                reg._meta_path(challenger_name).unlink(missing_ok=True)
                return {
                    "retrained": False,
                    "model": old_name,
                    "outcomes_used": len(dataset),
                    "old_brier": old_brier,
                    "new_brier": new_brier,
                    "old_accuracy": old_acc,
                    "new_accuracy": new_acc,
                    "message": f"Mô hình hiện tại vẫn tối ưu hơn model thử nghiệm (Brier {old_brier:.4f} vs {new_brier:.4f}) — tiếp tục duy trì",
                }

            # Cập nhật metadata của model mới
            try:
                _, meta = reg.load_model(challenger_name)
                meta["retrained_from_outcomes"] = True
                meta["outcomes_count"] = len(dataset)
                meta["brier_before"] = old_brier
                meta["brier_after"] = new_brier
                meta["acc_before"] = old_acc
                meta["acc_after"] = new_acc
                reg.save_model(challenger_name, reg.load_model(challenger_name)[0], meta)
            except Exception:
                pass

            msg = f"Học lại thành công ({len(dataset)} outcomes): Brier cải thiện từ {old_brier:.4f} ➔ {new_brier:.4f}, Accuracy: {new_acc * 100:.1f}%"
            logger.info(msg)
            return {
                "retrained": True,
                "model": challenger_name,
                "outcomes_used": len(dataset),
                "old_brier": old_brier,
                "new_brier": new_brier,
                "accuracy": new_acc,
                "message": msg,
            }

    # Chưa có model cũ -> model mới được lưu luôn
    return {
        "retrained": True,
        "model": challenger_name,
        "outcomes_used": len(dataset),
        "message": f"Đã huấn luyện và khởi tạo thành công mô hình {challenger_name} từ {len(dataset)} outcomes",
    }


def retrain_from_outcomes(
    store,
    symbol: str,
    timeframe: str,
    model_kind: str = "intraday_lgbm",
    registry=None,
) -> str | None:
    """Wrapper tương thích ngược trả về model name nếu retrained thành công, None nếu thất bại."""
    res = retrain_from_outcomes_detailed(store, symbol, timeframe, model_kind=model_kind, registry=registry)
    if res.get("retrained"):
        return res.get("model")
    return None
