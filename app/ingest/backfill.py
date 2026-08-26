import logging
from datetime import UTC, datetime, timedelta

from app.connectors.binance_rest import BinanceRestClient, MS_PER_UNIT
from app.storage.duckdb_store import DuckDBStore

logger = logging.getLogger(__name__)

DAY_MS = 86_400_000


class BackfillRunner:
    def __init__(self, store: DuckDBStore, client: BinanceRestClient):
        self.store = store
        self.client = client

    def backfill(
        self,
        symbol: str,
        timeframes: list[str],
        days: int,
        resume: bool = False,
        end_ms: int | None = None,
    ) -> int:
        """Backfill closed candles for each timeframe. Returns total inserted rows."""
        if end_ms is None:
            end_ms = self.client.server_time_ms() if hasattr(self.client, "server_time_ms") else None
        total = 0
        used_weight: dict = {}
        for tf in timeframes:
            step = MS_PER_UNIT[tf]
            tf_end = end_ms
            if tf_end is None:
                # fall back to now-UTC aligned to grid
                tf_end = int((datetime.now(UTC).timestamp()) * 1000)

            if resume:
                # cursor already points to the next page's start (last_open + step)
                cursor = self.store.get_backfill_cursor(symbol, tf)
                start_ms = int(cursor.timestamp() * 1000) if cursor else tf_end - days * DAY_MS
            else:
                start_ms = tf_end - days * DAY_MS

            inserted_tf = 0
            page_start = start_ms
            while page_start < tf_end:
                batch = self.client.fetch_klines(
                    symbol, tf, start_ms=page_start, end_ms=tf_end, used_weight_log=used_weight
                )
                if not batch:
                    break
                n = self.store.upsert_klines(batch)
                inserted_tf += n
                total += n
                last_open = batch[-1]["open_time"]
                last_open_ms = int(last_open.timestamp() * 1000)
                next_page = last_open_ms + step
                if next_page <= page_start:
                    break
                page_start = next_page
                self.store.set_backfill_cursor(symbol, tf, datetime.fromtimestamp(page_start / 1000, tz=UTC))
            logger.info("backfill %s %s: %d candles (weight %s)", symbol, tf, inserted_tf, used_weight.get("1m"))
        return total
