from __future__ import annotations

import logging
from datetime import UTC, datetime

import numpy as np

from app.models.provider import ModelProvider
from app.models.registry import model_registry
from app.forecast.schema import ForecastContext, Signal, SignalDirection, SignalStatus

logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "ret_1",
    "ret_5",
    "ret_20",
    "rsi_14",
    "macd",
    "macd_signal",
    "bb_pct_b",
    "vol_zscore_20",
    "taker_buy_ratio",
]


def build_labels(df) -> np.ndarray:
    """Next-candle up/down (1/0), last row NaN (no next candle)."""
    shifted = df["close"].shift(-1)
    labels = (shifted > df["close"]).astype(float)
    labels[shifted.isna()] = np.nan
    return labels


class GarchVolEstimator:
    """GARCH(1,1) đơn giản: sigma²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}.

    Fit bằng MLE qua scipy optimize; fallback EWMA std nếu không converge.
    """

    def __init__(self):
        self._omega = 1e-6
        self._alpha = 0.1
        self._beta = 0.85

    def predict_vol(self, closes: list[float]) -> float | None:
        import pandas as pd

        if len(closes) < 30:
            return None
        returns = pd.Series(closes).pct_change().dropna()
        if len(returns) < 20:
            return None
        try:
            from scipy.optimize import minimize

            r = returns.to_numpy()

            def neg_log_lik(params):
                omega, alpha, beta = np.exp(params[0]), params[1], params[2]
                if alpha < 0 or beta < 0 or alpha + beta >= 1:
                    return 1e10
                sigma2 = np.full(len(r), omega / (1 - alpha - beta))
                for t in range(1, len(r)):
                    sigma2[t] = omega + alpha * r[t - 1] ** 2 + beta * sigma2[t - 1]
                return float(0.5 * np.sum(np.log(sigma2) + r**2 / sigma2))

            res = minimize(
                neg_log_lik,
                x0=[np.log(1e-6), 0.1, 0.85],
                method="Nelder-Mead",
                options={"maxiter": 500},
            )
            omega, alpha, beta = np.exp(res.x[0]), res.x[1], res.x[2]
            if not (0 < alpha + beta < 1):
                raise ValueError("non-stationary")
            sigma2 = omega / (1 - alpha - beta)
            return float(np.sqrt(sigma2))
        except Exception as e:
            logger.warning("GARCH fit failed (%s), fallback EWMA", e)
            return float(returns.ewm(span=20).std().iloc[-1])


def train_intraday(
    symbol: str,
    timeframe: str,
    candles: list[dict],
    registry=None,
) -> str:
    """Train LightGBM + Isotonic calibration, save to registry."""
    import pandas as pd
    from lightgbm import LGBMClassifier
    from sklearn.calibration import IsotonicRegression
    from sklearn.model_selection import cross_val_predict

    reg = registry or model_registry
    df = pd.DataFrame(candles)
    feats = _feature_df(df)
    if len(feats) < 40:
        raise ValueError("not enough candles for intraday training")

    X = feats[FEATURE_COLS].to_numpy()
    y = build_labels(feats).to_numpy()
    # drop last row (NaN label)
    valid = ~np.isnan(y)
    X, y = X[valid], y[valid]
    if len(y) < 30:
        raise ValueError("too few labeled samples")

    clf = LGBMClassifier(
        n_estimators=100, learning_rate=0.05, max_depth=4, subsample=0.8,
        verbose=-1, random_state=42,
    )
    # OOF probabilities for calibration
    oof = cross_val_predict(clf, X, y, cv=5, method="predict_proba", n_jobs=1)[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(oof, y)
    clf.fit(X, y)

    meta = {
        "type": "intraday_lgbm",
        "symbol": symbol,
        "timeframe": timeframe,
        "trained_at": datetime.now(UTC).isoformat(),
        "features": FEATURE_COLS,
    }
    name = f"intraday_lgbm@{symbol}@{timeframe}"
    reg.save_model(name, {"clf": clf, "iso": iso}, meta)
    logger.info("trained intraday %s %s", symbol, timeframe)
    return name


def _feature_df(df: pd.DataFrame) -> pd.DataFrame:
    from app.forecast.features import build_features

    return build_features(df)


class IntradayProvider(ModelProvider):
    """Intraday LightGBM + GARCH vol band → Signal."""

    def __init__(self, model_name: str, registry=None):
        super().__init__(model_name, registry=registry)
        self._garch = GarchVolEstimator()

    def forecast(self, ctx: ForecastContext) -> Signal:
        candles = ctx.candles
        if len(candles) < 30:
            return self._failed(ctx, "not enough candles")
        import pandas as pd

        try:
            model, meta = self._registry.load_model(self.model_name)
        except Exception as e:
            return self._failed(ctx, str(e))
        df = pd.DataFrame(candles)
        feats = _feature_df(df)
        if len(feats) == 0:
            return self._failed(ctx, "feature warmup")
        X = feats[FEATURE_COLS].to_numpy()[-1:].reshape(1, -1)
        proba = model["clf"].predict_proba(X)[0, 1]
        prob_cal = float(model["iso"].predict([proba])[0])

        last_close = float(candles[-1]["close"])
        vol = self._garch.predict_vol([c["close"] for c in candles]) or 0.01
        band = max(last_close * vol, last_close * 0.001)
        direction = SignalDirection.LONG if prob_cal >= 0.5 else SignalDirection.SHORT
        sig = Signal(
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            direction=direction,
            probability=prob_cal,
            entry=last_close,
            model=self.name,
            status=SignalStatus.OK,
        )
        if direction == SignalDirection.LONG:
            sig.take_profit = [round(last_close + band, 2)]
            sig.stop_loss = round(max(last_close - band, 0.01), 2)
        else:
            sig.take_profit = [round(max(last_close - band, 0.01), 2)]
            sig.stop_loss = round(last_close + band, 2)
        return sig
