# Crypto Tracker & Forecast

Single-process FastAPI app: WebSocket ingest worker chạy như asyncio task trong cùng process, dùng chung 1 DuckDB instance. SP1 (data foundation) + SP2 (forecast core) + SP3 (model zoo) + SP4 (alerts + paper trading + feedback).

## Architecture spike (Phase 1)

`scripts/spike_single_process_duckdb.py` — 2 kết luận quan trọng:

1. **Không thể mở cùng file DuckDB với config trộn lẫn** (read-write + `read_only=True`) ngay cả trong cùng process → app dùng đúng **1 connection read-write duy nhất**, chia sẻ qua nhiều cursor (thread-safe cho đọc song song).
2. **`SET TimeZone='UTC'` không propagate xuống cursor** (host UTC+7 mặc định Asia/Saigon) → phải set TimeZone trên **mỗi cursor** khi tạo. Store layer áp dụng điều này ở Phase 2/4.

Kết luận: topology single-process khả thi, không cần fallback Parquet. Red-team #1 tránh bằng cách không bao giờ mở DB từ process thứ hai.

Chạy spike: `.venv\Scripts\python.exe scripts\spike_single_process_duckdb.py`

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

## Run

```
start.bat
REM hoặc:
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Server bind **127.0.0.1 duy nhất** (không bao giờ 0.0.0.0)
- CORS allowlist: `http://localhost:5173`, `http://127.0.0.1:5173`
- Health: http://127.0.0.1:8000/health

## Test

```
.venv\Scripts\python.exe -m pytest
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

- `POST /api/alerts` — dispatch alert (telegram nếu cấu hình, fallback webhook)
- `GET /api/alerts` — lịch sử alerts
- `POST /api/outcomes` — user nhập win/lose (guard: cần ≥ FEEDBACK_MIN_SIGNALS track record)
- `POST /api/outcomes/auto-resolve` — auto-resolve từ klines (TP→win, SL→lose)
- `GET/POST /api/positions` + `POST /api/positions/{id}/close` + `GET /api/positions/pnl` — paper trading

## Test

```
.venv\Scripts\python.exe -m pytest
cd web && npm run test && npm run build
```

Xem thêm: plans tại vault `2nd-brain-monkeys/Plans/2608*-*-*-crypto-tracker-forecast/` (SP1 data foundation, SP2 forecast core, SP3 model zoo, SP4 alerts + paper trading + feedback).
