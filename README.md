# Crypto Tracker & Forecast — SP1 Data Foundation

Single-process FastAPI app: WebSocket ingest worker chạy như asyncio task trong cùng process, dùng chung 1 DuckDB instance.

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

Xem thêm: plan SP1 tại vault `2nd-brain-monkeys/Plans/260825-1638-sp1-data-foundation-crypto-tracker-forecast/`.
