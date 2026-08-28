import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    ws_task = None
    engine_task = None
    relay = None
    if not getattr(app.state, "ws_worker_disabled", False):
        from app.forecast.registry import register_defaults

        register_defaults()

        from app.ingest.ws_worker import run_ws_worker

        ws_task = asyncio.create_task(run_ws_worker())

    # Futures demo exchange (SP5): engine consume tick queue (Phase 4 relay push).
    # Gate futures_disabled để test không mở engine/DB thật.
    if not getattr(app.state, "futures_disabled", False):
        from app.api.routes import get_store

        store = get_store()
        from app.trading.futures_engine import FuturesEngine

        engine = FuturesEngine(store, symbol_list=settings.symbol_list)
        engine.set_queue(_futures_queue)
        app.state.futures_engine = engine
        store._engine = engine
        engine_task = asyncio.create_task(engine.run())

        # Binance futures WS relay (gate riêng cho test, mirror ws_worker_disabled)
        if not getattr(app.state, "relay_disabled", False):
            from app.ws.relay import BinanceRelay

            relay = BinanceRelay(engine=engine, symbol_list=settings.symbol_list)
            app.state.futures_relay = relay
    yield
    if relay is not None:
        try:
            await relay.shutdown()
        except Exception as e:
            print(f"relay shutdown error: {e}")
    if engine_task is not None:
        engine_task.cancel()
        try:
            await engine_task
        except asyncio.CancelledError:
            pass
        try:
            _futures_store_conn_checkpoint()
        except Exception as e:
            print(f"checkpoint failed: {e}")
    if ws_task is not None:
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass


_futures_queue: asyncio.Queue = asyncio.Queue()
_futures_store_ref = {}


def _futures_store_conn_checkpoint() -> None:
    """PRAGMA checkpoint trên connection store trước khi shutdown (flush WAL)."""
    from app.api.routes import get_store

    store = get_store()
    try:
        store.cursor().execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass


app = FastAPI(title="Crypto Tracker Forecast", lifespan=lifespan)

from app.api.routes import router as api_router  # noqa: E402

app.include_router(api_router)

from app.api.trading_routes import router as trading_router  # noqa: E402

app.include_router(trading_router)

from app.api.alert_routes import router as alert_router  # noqa: E402

app.include_router(alert_router)

from app.api.outcome_routes import router as outcome_router  # noqa: E402

app.include_router(outcome_router)

from app.api.ai_routes import router as ai_router  # noqa: E402

app.include_router(ai_router)

from app.forecast.routes import leaderboard_router, router as forecast_router  # noqa: E402

app.include_router(forecast_router)
app.include_router(leaderboard_router)

from app.api.futures_routes import router as futures_router  # noqa: E402

app.include_router(futures_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "PUT", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    from app.api.routes import get_store

    body: dict = {"status": "ok"}
    try:
        store = get_store()
        counts = {
            sym: {tf: store.count(sym, tf) for tf in settings.timeframe_list}
            for sym in settings.symbol_list
        }
        total = sum(sum(tfs.values()) for tfs in counts.values())
        body["db"] = {"total_klines": total, "symbols": counts}
    except Exception as e:
        body["db"] = {"error": str(e)}
    return body


@app.websocket("/ws/trade/{symbol}")
async def ws_trade(websocket: WebSocket, symbol: str):
    """Relay Binance futures markPrice + kline frames cho 1 symbol.

    Market data public — không cần auth. Symbol validate theo settings.symbol_list
    (regex ^[A-Z0-9]{4,20}$) trước get_or_create. WS chỉ phát market data,
    KHÔNG có P&L cá nhân. Engine nhận tick từ relay upstream (độc lập client).
    """
    import re

    sym = symbol.upper()
    if not re.match(r"^[A-Z0-9]{4,20}$", sym) or sym not in settings.symbol_list:
        await websocket.close(code=4404, reason="invalid symbol")
        return

    relay = getattr(app.state, "futures_relay", None)
    if relay is None:
        await websocket.close(code=4403, reason="relay disabled")
        return

    await websocket.accept()
    try:
        q = await relay.subscribe(sym)
    except ValueError:
        await websocket.close(code=4404, reason="invalid symbol")
        return
    except RuntimeError:
        await websocket.close(code=4429, reason="too many connections")
        return

    try:
        while True:
            frame = await q.get()
            await websocket.send_json(frame)
    except WebSocketDisconnect:
        pass
    finally:
        await relay.release(sym, q)
