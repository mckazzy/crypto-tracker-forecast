import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_ws_worker() -> None:
    """Realtime kline WS worker. Implemented in Phase 3 — stub keeps lifespan importable."""
    logger.info("ws_worker stub started (Phase 3 will implement streaming)")
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("ws_worker stub cancelled")
        raise
