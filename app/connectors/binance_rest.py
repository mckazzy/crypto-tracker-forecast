import logging
import time
from typing import Callable

import httpx

logger = logging.getLogger(__name__)

KLINES_PAGE_LIMIT = 1000
MS_PER_UNIT = {
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
}


class BinanceRestClient:
    def __init__(self, transport: httpx.BaseTransport | None = None, base_url: str | None = None):
        self._client = httpx.Client(
            base_url=base_url or "https://api.binance.com",
            transport=transport,
            timeout=30.0,
        )

    def ping(self) -> bool:
        try:
            resp = self._client.get("/api/v3/ping")
        except httpx.HTTPError as e:
            raise RuntimeError(f"Binance connectivity check failed: {e}") from e
        if resp.status_code in (451, 403):
            raise RuntimeError(
                f"Binance returned {resp.status_code} (geo-block?) — "
                "consider fallback data source data.binance.vision"
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Binance ping failed: HTTP {resp.status_code}")
        return True

    def server_time_ms(self) -> int:
        resp = self._client.get("/api/v3/time")
        resp.raise_for_status()
        return int(resp.json()["serverTime"])

    def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        start_ms: int,
        end_ms: int | None = None,
        used_weight_log: dict | None = None,
    ) -> list[dict]:
        """Fetch all closed klines in [start_ms, end_ms), paginating automatically.

        Drops the still-open last candle. Returns tz-aware UTC normalized dicts.
        """
        step = MS_PER_UNIT[timeframe]
        out: list[dict] = []
        seen_open_times: set[int] = set()
        cursor = start_ms
        while True:
            params = {
                "symbol": symbol,
                "interval": timeframe,
                "startTime": cursor,
                "limit": KLINES_PAGE_LIMIT,
            }
            if end_ms is not None:
                params["endTime"] = end_ms - 1
            resp = self._client.get("/api/v3/klines", params=params)
            weight = resp.headers.get("X-MBX-USED-WEIGHT-1M")
            if weight is not None and used_weight_log is not None:
                used_weight_log["1m"] = int(weight)
            if resp.status_code == 451:
                raise RuntimeError(
                    "Binance geo-block (HTTP 451) — fallback data.binance.vision required"
                )
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                break
            for raw in rows:
                k = _normalize(symbol, timeframe, raw)
                ot_ms = int(k["open_time"].timestamp() * 1000)
                if ot_ms in seen_open_times:
                    continue
                seen_open_times.add(ot_ms)
                if not k["is_closed"]:
                    continue  # drop unclosed seam candle
                out.append(k)
            last_open_ms = int(rows[-1][0])
            next_cursor = last_open_ms + step
            if len(rows) < KLINES_PAGE_LIMIT or next_cursor <= cursor:
                break
            cursor = next_cursor
        return out

    def get_ticker_price(self, symbol: str) -> float | None:
        """Lấy giá realtime hiện tại của symbol từ Binance."""
        try:
            resp = self._client.get("/api/v3/ticker/price", params={"symbol": symbol.upper()})
            if resp.status_code == 200:
                return float(resp.json()["price"])
        except Exception as e:
            logger.warning("failed to fetch realtime ticker for %s: %s", symbol, e)
        return None

    def fetch_recent_klines(
        self,
        symbol: str,
        timeframe: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Lấy danh sách nến gần nhất (kể cả nến đang mở) từ Binance."""
        params: dict = {"symbol": symbol.upper(), "interval": timeframe, "limit": limit}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        try:
            resp = self._client.get("/api/v3/klines", params=params)
            if resp.status_code == 200:
                rows = resp.json()
                return [_normalize(symbol.upper(), timeframe, raw) for raw in rows]
        except Exception as e:
            logger.warning("failed to fetch recent klines from Binance: %s", e)
        return []


def _normalize(symbol: str, timeframe: str, raw: list) -> dict:
    from datetime import UTC, datetime

    return {
        "open_time": datetime.fromtimestamp(raw[0] / 1000, tz=UTC),
        "close_time": datetime.fromtimestamp(raw[6] / 1000, tz=UTC),
        "symbol": symbol,
        "timeframe": timeframe,
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
        "close_volume": float(raw[7]),
        "trades": int(raw[8]),
        "taker_buy_base": float(raw[9]),
        "is_closed": str(raw[11]) not in ("1", "True", "true"),
    }
