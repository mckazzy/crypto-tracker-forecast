from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def score_forecast(direction: str, entry: float, tp: float | None, sl: float | None, exit_price: float) -> float:
    """Chấm điểm % đạt được so với TP tại thời điểm kết thúc khung dự đoán.

    - Từ entry đến TP là 100%.
    - Đúng hướng Long/Short so với TP thì điểm +, ngược hướng thì điểm -.
    - LONG:  tp > entry → score = ((exit_price - entry) / (tp - entry)) * 100
    - SHORT: tp < entry → score = ((entry - exit_price) / (entry - tp)) * 100
    - Nếu không có TP hợp lệ: tính % thay đổi giá so với entry.
    """
    if entry <= 0 or exit_price <= 0:
        return 0.0

    if direction == "LONG":
        if tp is not None and tp > entry:
            progress = ((exit_price - entry) / (tp - entry)) * 100.0
            return round(progress, 1)
        # fallback khi không có TP hợp lệ: % thay đổi giá so với entry
        return round(((exit_price - entry) / entry) * 100.0, 1)

    if direction == "SHORT":
        if tp is not None and tp < entry:
            progress = ((entry - exit_price) / (entry - tp)) * 100.0
            return round(progress, 1)
        # fallback khi không có TP hợp lệ: % thay đổi giá so với entry
        return round(((entry - exit_price) / entry) * 100.0, 1)

    return 0.0


def exit_price_at(
    store,
    symbol: str,
    timeframe: str,
    valid_until: datetime,
    client: object | None = None,
) -> float | None:
    """Lấy giá thực tế tại thời điểm kết thúc khung dự đoán (valid_until).

    Cơ chế:
    1. Nếu valid_until vừa kết thúc hoặc trong quá khứ:
       - Thử gọi Binance REST API lấy giá live realtime ticker hoặc nến thực tế tại mốc valid_until.
       - Tự động đồng bộ các nến thực mới lấy được vào store.
    2. Fallback: Nếu không có kết nối mạng (hoặc môi trường test/mock):
       - Tìm candle có open_time <= valid_until trong store cục bộ.
    """
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=UTC)

    now = datetime.now(UTC)

    # 1. Thử lấy giá thực realtime từ Binance REST nếu có kết nối
    try:
        from app.config import settings
        from app.connectors.binance_rest import MS_PER_UNIT, BinanceRestClient

        rest_client = client or BinanceRestClient(base_url=settings.binance_rest_base)
        step_ms = MS_PER_UNIT.get(timeframe, 14_400_000)

        # Nếu valid_until vừa kết thúc gần đây (trong vòng 5 phút quanh hiện tại),
        # ưu tiên lấy giá live ticker realtime
        diff_sec = abs((now - valid_until).total_seconds())
        if diff_sec <= 300:
            ticker_price = rest_client.get_ticker_price(symbol)
            if ticker_price is not None and ticker_price > 0:
                return float(ticker_price)

        # Lấy nến thực từ Binance quanh mốc valid_until
        target_ms = int(valid_until.timestamp() * 1000)
        start_ms = max(0, target_ms - step_ms * 2)
        end_ms = target_ms + step_ms * 2
        klines = rest_client.fetch_recent_klines(
            symbol, timeframe, start_ms=start_ms, end_ms=end_ms, limit=10
        )
        if klines:
            try:
                store.upsert_klines(klines)
            except Exception:
                pass
            target = None
            for c in klines:
                ot = c["open_time"]
                if ot.tzinfo is None:
                    ot = ot.replace(tzinfo=UTC)
                if ot <= valid_until:
                    target = c
                else:
                    break
            if target is not None:
                return float(target["close"])
            if klines:
                return float(klines[-1]["close"])
    except Exception as e:
        logger.debug("Binance real-time price fetch skipped/failed: %s", e)

    # 2. Fallback tìm trong store local
    candles = store.get_klines(symbol, timeframe, limit=500)
    if not candles:
        return None
    target = None
    for c in candles:
        ot = c["open_time"]
        if ot.tzinfo is None:
            ot = ot.replace(tzinfo=UTC)
        if ot <= valid_until:
            target = c
        else:
            break
    if target is None:
        return None
    return float(target["close"])
