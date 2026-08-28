import asyncio
import json
import logging
from datetime import UTC, datetime

import websockets

from app.config import settings
from app.connectors.binance_rest import MS_PER_UNIT
from app.storage.duckdb_store import DuckDBStore

logger = logging.getLogger(__name__)

TF_TO_STREAM = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w"}


class KlineStreamNormalizer:
    """Stateless normalizer from Binance kline WS events to store dicts."""

    def normalize(self, event: dict) -> dict:
        k = event["k"]
        return {
            "open_time": datetime.fromtimestamp(k["t"] / 1000, tz=UTC),
            "close_time": datetime.fromtimestamp(k["T"] / 1000, tz=UTC),
            "symbol": event["s"],
            "timeframe": k["i"],
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "close_volume": float(k.get("V", 0.0)),
            "trades": int(k.get("n", 0)),
            "taker_buy_base": float(k.get("V", 0.0)),
            "is_closed": bool(k["x"]),
        }


def handle_ws_message(raw: str, normalizer: KlineStreamNormalizer) -> list[dict]:
    """Parse one raw WS frame → list of normalized klines (possibly empty)."""
    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("dropping non-JSON ws frame")
        return []
    if isinstance(msg, dict) and "data" in msg:  # combined-stream envelope
        msg = msg["data"]
    if not isinstance(msg, dict) or msg.get("e") != "kline":
        return []
    return [normalizer.normalize(msg)]


def detect_gap(last_stored: int | None, incoming: int, step: int) -> list[int]:
    """Return open_times (ms) missing between last stored and incoming candle."""
    if last_stored is None or incoming <= last_stored + step:
        return []
    return list(range(last_stored + step, incoming, step))


def build_stream_url(symbols: list[str], timeframes: list[str]) -> str:
    streams = "/".join(
        f"{s.lower()}@kline_{tf}" for s in symbols for tf in timeframes
    )
    base = settings.binance_ws_base.rstrip("/")
    return f"{base}/stream?streams={streams}"


async def run_ws_worker(store: DuckDBStore | None = None) -> None:
    """Subscribe to kline streams for all configured symbols/timeframes.

    Closed candles are upserted into the store; open candles update an
    in-memory latest-price cache only. Reconnects with exponential backoff.
    """
    from app.api.routes import get_store

    if store is None:
        store = get_store()

    url = build_stream_url(settings.symbol_list, settings.timeframe_list)
    normalizer = KlineStreamNormalizer()
    backoff = 1.0
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                logger.info("ws connected: %s", url)
                backoff = 1.0
                async for raw in ws:
                    for kline in handle_ws_message(raw, normalizer):
                        if kline["is_closed"]:
                            await _store_with_gapfill(store, kline)
                        # open-candle handling (latest price cache) lands with Phase 5 UI
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("ws disconnected (%s), retrying in %.1fs", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


async def _store_with_gapfill(store: DuckDBStore, kline: dict) -> None:
    """Upsert closed candle; REST-fill any gap between DB tail and this candle."""
    step = MS_PER_UNIT.get(kline["timeframe"])
    if step is None:
        return
    last = store.max_open_time(kline["symbol"], kline["timeframe"])
    last_ms = int(last.timestamp() * 1000) if last else None
    incoming_ms = int(kline["open_time"].timestamp() * 1000)

    from app.ingest.gapfill import fetch_missing

    missing = detect_gap(last_ms, incoming_ms, step)
    if missing:
        logger.info(
            "gap detected %s %s: %d candles — fetching via REST",
            kline["symbol"],
            kline["timeframe"],
            len(missing),
        )
        filled = await asyncio.to_thread(fetch_missing, store, kline["symbol"], kline["timeframe"], last_ms or incoming_ms, incoming_ms)
        logger.info("gap-filled %d candles", filled)
    store.upsert_klines([kline])
