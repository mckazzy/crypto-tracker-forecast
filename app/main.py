import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    ws_task = None
    if not getattr(app.state, "ws_worker_disabled", False):
        from app.ingest.ws_worker import run_ws_worker

        ws_task = asyncio.create_task(run_ws_worker())
    yield
    if ws_task is not None:
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Crypto Tracker Forecast", lifespan=lifespan)

from app.api.routes import router as api_router  # noqa: E402

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET"],
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
