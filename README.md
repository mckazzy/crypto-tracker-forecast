# Crypto Tracker & Forecast

Single-process FastAPI app: WebSocket ingest worker chạy như asyncio task trong cùng process, dùng chung 1 DuckDB instance.

**SP1** data foundation · **SP2** forecast core (AI OpenRouter + local LightGBM) · **SP3** model zoo + walk-forward eval · **SP4** alerts (Telegram) + paper trading + feedback loop · **SP5** futures demo exchange (Binance-style trade screen).

## Tính năng

- **Real-time klines** — Binance spot WS ingest vào DuckDB (6 timeframe: 5m → 1w), `/api/klines` đọc local DB.
- **AI Forecast** — OpenRouter (deepseek/gpt/qwen…) vs local LightGBM (`intraday_lgbm`/`meta_lgbm`/`elasticnet`), 6 timeframe, walk-forward eval, feedback loop (win/lose + auto-resolve từ klines) + retrain pipeline.
- **Alerts** — dispatch Telegram (nếu cấu hình) + webhook fallback, feed trong UI.
- **Leaderboard** — so sánh AI vs local theo accuracy + token cost.
- **Futures Demo Exchange (SP5)** — ví ảo 10,000 USDT, market/limit order, TP/SL, liquidation, positions + P&L realtime, chart kline + mark price qua WS relay. **Fallback tự động khi mạng chặn fstream push**: watchdog poll REST `premiumIndex` mỗi 3s khi WS im lặng >5s, seed chart từ `GET /api/futures/klines/{symbol}` (fapi primary, spot fallback).

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env            # bắt buộc: JWT_SECRET >= 32 chars
cd web && npm install && cd ..
```

## Run

```
start.bat
REM hoặc:
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9900
cd web && npm run dev             # vite dev server :5173 (proxy /api + /ws)
```

- Server bind **127.0.0.1 duy nhất** (không bao giờ 0.0.0.0)
- CORS allowlist: `http://localhost:5173`, `http://127.0.0.1:5173`
- Health: http://127.0.0.1:9900/health

## Test

```
.venv\Scripts\python.exe -m pytest          # 339 passed
cd web && npm run test && npm run build     # 63 passed + build OK
```

## Backfill historical data

```
.venv\Scripts\python.exe -m app.ingest backfill --symbol BTCUSDT --timeframes 5m,15m,1h,4h,1d,1w --days 365
```

## Forecast & Models

```
# Train model (SP3 model zoo: intraday_lgbm / meta_lgbm / elasticnet)
.venv\Scripts\python.exe -m app.models train --symbol BTCUSDT --timeframes 1h,4h --model intraday_lgbm

# Eval walk-forward vs baseline
.venv\Scripts\python.exe -m app.models eval --symbol BTCUSDT --timeframes 1h,4h

# Retrain từ feedback outcomes (SP4)
.venv\Scripts\python.exe -m app.models retrain --symbol BTCUSDT --timeframes 1h,4h
```

## Alerts (SP4)

Cấu hình `.env`:
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
FEEDBACK_MIN_SIGNALS=10
```

## AI Provider (OpenRouter)

Cấu hình `.env`:
```
AI_ENABLED=true
AI_BASE_URL=https://openrouter.ai/api/v1
AI_API_KEY=sk-or-...          # key từ https://openrouter.ai/keys
AI_MODEL=deepseek/deepseek-v4-flash-0731
```

## Futures Demo Exchange (SP5)

- `POST /api/futures/auth/register|login` → JWT (fail-closed, secret ≥ 32 chars)
- `POST /api/futures/orders` — MARKET fill tại engine mark (server-authoritative, client price bị bỏ qua) / LIMIT chờ fill; TP/SL tùy chọn
- `GET /api/futures/positions|orders|trades` + `POST /api/futures/positions/{id}/close` + `POST /api/futures/account/reset`
- `GET /api/futures/mark/{symbol}` — mark price hiện tại (engine cache)
- `GET /api/futures/klines/{symbol}?timeframe=1m&limit=200` — public market data, fapi primary + spot fallback
- WS `ws://127.0.0.1:9900/ws/trade/{symbol}` — frame markPrice + kline (server-normalized, không cần auth)
- Engine nhận tick độc lập client (0 client vẫn sống); relay watchdog poll REST khi WS im lặng >5s (mạng lọc fstream)

## Roadmap

Xem `docs/roadmap.md` — SP6 candidate (stale-mark fail-closed, TP/SL/liq alerts, backfill async, signal→order, position overlay, bounded engine queue) + backlog 19 ý.
