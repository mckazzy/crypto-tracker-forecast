import logging

from app.connectors.binance_rest import BinanceRestClient
from app.config import settings
from app.storage.duckdb_store import DuckDBStore

logger = logging.getLogger(__name__)


def fetch_missing(
    store: DuckDBStore,
    symbol: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
) -> int:
    """Fetch and upsert candles in (start_ms, end_ms) via REST. Returns count."""
    client = BinanceRestClient(base_url=settings.binance_rest_base)
    try:
        batch = client.fetch_klines(symbol, timeframe, start_ms=start_ms, end_ms=end_ms)
        if not batch:
            return 0
        return store.upsert_klines(batch)
    except RuntimeError as e:
        logger.error("gap-fill fetch failed for %s %s: %s", symbol, timeframe, e)
        return 0
