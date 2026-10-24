# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo shape

- `app/` = FastAPI backend, single-process by design.
- `web/` = React + Vite frontend.
- `tests/` = pytest suite split into `unit/` and `integration/`.
- `docs/` = product notes, design spec, roadmap, QA artifacts.
- `plans/` = implementation plans and phase notes.

## Big-picture architecture

- Backend entry is `app/main.py`. It wires CORS, routers, `/health`, and `/ws/trade/{symbol}`.
- App runs `ws_worker` and `FuturesEngine` in FastAPI lifespan. Keep that in-process model unless a change explicitly needs separate services.
- Market data lives in one DuckDB file through `DuckDBStore` (`app/storage/duckdb_store.py`). `app/api/routes.py` owns cached store creation and `/api/klines`, `/api/symbols`, `/api/backfill`.
- Ingest path is Binance WS + REST fallback: `app/ingest/ws_worker.py`, `app/ingest/backfill.py`, `app/ingest/gapfill.py`, `app/connectors/binance_rest.py`.
- Forecast stack sits under `app/forecast/` and `app/models/`: feature prep, baselines, metrics, walk-forward eval, registry, train/eval/retrain, AI provider.
- Futures demo exchange lives in `app/trading/`, `app/api/futures_routes.py`, and `app/ws/relay.py`. It is server-authoritative, mark-price driven, and shares state with the backend process.
- Alerts/auth live in `app/alerts/`, `app/api/alert_routes.py`, `app/auth/`, and `app/api/trading_routes.py`.
- Frontend is a tabbed trading terminal in `web/src/App.tsx` with chart, forecast compare, leaderboard, alerts, and futures terminal. API wrappers are in `web/src/lib/api.ts`.
- `web/vite.config.ts` proxies `/api` and `/ws` to `127.0.0.1:9900`.

## Common commands

### Backend

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9900
```

```powershell
.venv\Scripts\python.exe -m pytest
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_validate_kline.py
```

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_futures_api.py -k mark
```

### Frontend

```powershell
cd web && npm run dev
```

```powershell
cd web && npm run lint
```

```powershell
cd web && npm run test
```

```powershell
cd web && npm run test -- src/__tests__/App.test.tsx
```

```powershell
cd web && npm run build
```

```powershell
cd web && npm run preview
```

### Full app

```powershell
start.bat
```

## Config and runtime notes

- Copy `.env.example` to `.env` before running backend.
- `JWT_SECRET` must be set and at least 32 chars.
- Server binds loopback only. Do not change to `0.0.0.0`.
- Main UI runs on Vite `5173`; backend default is `9900`.
- `pytest.ini` already points test discovery at `tests/` and sets `asyncio_mode=auto`.
- Frontend tests use Vitest + jsdom with `web/src/test-setup.ts`.

## Docs worth reading first

- `README.md` for setup, run, and test commands.
- `docs/design-specs.md` for UI direction.
- `docs/roadmap.md` for current SP6 direction and backlog.
- `docs/260828-brainstorm-futures-trade-screen.md` and `plans/260828-1515-futures-trade-screen-binance-style-demo-exchange/` for SP5 context.
