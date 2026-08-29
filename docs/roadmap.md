# Roadmap — Upgrade Features (SP6 candidate) — 2026-08-29

> Nguồn: brainstorm 2 góc nhìn (product 12 ý + technical 10 ý), sau khi hoàn tất
> SP5 follow-up (commit `052274d`). Trạng thái test tại thời điểm viết:
> pytest 339 · vitest 63 · build PASS.

## Bối cảnh hiện tại (đã chạy được)

- SP1-SP5 đầy đủ: ingest klines spot (Binance WS + DuckDB), AI forecast
  (OpenRouter + local LightGBM, 6 timeframe), feedback loop + retrain, alerts
  (Telegram), leaderboard, **futures demo exchange** (ví ảo, market/limit,
  TP/SL, liq, positions, P&L) với relay WS có watchdog REST fallback + seed
  chart từ REST (do mạng chặn fstream push).
- UI 5 tab (Dashboard/Leaderboard/Forecast/Trading/Alerts), dark/light theme.
- Kiến trúc: FastAPI lifespan chạy ws_worker + FuturesEngine (queue tick) +
  BinanceRelay (1 upstream/symbol, fan-out, engine nhận tick độc lập client).

## Tiêu chí chọn feature

1. Tận dụng data/component/model **đã có** (không build từ zero).
2. Giải quyết nỗi đau thật (giá giả 50k, event loop đóng băng, alert chỉ trong
   terminal, chart đứng yên khi WS kline bị chặn, forecast → lệnh phải copy-paste).
3. Effort ≤ S cho "Next up" → chạy trọn vẹn trong 1 sprint.

## Next up (SP6 — 6 feature, toàn bộ effort S)

### N1. Stale-mark fail-closed (bỏ giá giả 50,000) — [Technical T2]
- **Vấn đề:** `_engine_mark()` hardcode `50000.0` (`app/api/futures_routes.py:229-236`) khi
  engine chưa nhận tick → order MARKET + close position fill tại **giá giả** (QA ghi rõ
  "stale/giả"). 
- **Thiết kế:** engine track `mark_ts` + `mark_age_ms` per symbol; setting
  `stale_mark_seconds` (~10s); mark cũ hơn ngưỡng → `GET /api/futures/mark` trả 503,
  `POST /api/futures/orders` (MARKET) + close từ chối với lỗi rõ ràng.
- **AC:** engine không tick → order MARKET nhận 503 (không tạo order); hết hardcode 50k
  (test grep); test mới cho cả 2 path.

### N2. TP/SL/Liquidation Alerts realtime — [Product 1]
- **Vấn đề:** lệnh bị đóng vì TP/SL/liq chỉ hiện trong terminal — user rời tab là mất.
- **Thiết kế:** engine `_close_position`/`_liquidate` (đã có reason SL/TP/LIQUIDATION,
  `app/trading/futures_engine.py:212,226`) → `AlertEngine.dispatch` (dedup sẵn) +
  `TelegramSender` (`app/alerts/engine.py`, `app/alerts/telegram.py`) + feed AlertsPanel.
- **AC:** đóng lệnh TP/SL/liq tạo 1 alert có lý do + giá thoát + P&L; Telegram nhận khi
  cấu hình token; alert không spam (dedup).

### N3. Backfill không block event loop — [Technical T1]
- **Vấn đề:** `/api/backfill` chạy `runner.backfill(...)` sync trong `async def`
  (`app/api/routes.py:101-127`) → đóng băng WS relay + engine futures khi backfill
  365 ngày × 6 TF.
- **Thiết kế:** `asyncio.to_thread` hoặc `BackgroundTasks` + job registry
  `running|done|error` + `GET /api/backfill/status`; chặn start trùng (409).
- **AC:** gọi backfill 1 symbol dài → `GET /health` trong lúc chạy <200ms; request thứ 2
  nhận 409 ngay.

### N4. Signal → Order (một-chạm vào lệnh theo forecast) — [Product 4]
- **Vấn đề:** forecast ra tín hiệu nhưng phải copy-paste direction/TP/SL sang OrderForm.
- **Thiết kế:** nút "Trade this signal" trên mỗi tín hiệu ở ForecastCompare — tự điền
  direction + entry + TP/SL vào OrderForm (user chỉ chọn notional/leverage); signal đã có
  `direction/take_profit/stop_loss` từ `/api/forecast/compare/{symbol}/{timeframe}`.
- **AC:** click signal → OrderForm điền đúng TP/SL/direction; submit MARKET tạo position
  tại engine mark; test UI + API.

### N5. Position Levels Overlay trên chart — [Product 3]
- **Vấn đề:** phải chuyển tab giữa PositionsPanel và chart để ước khoảng cách entry/TP/SL/liq.
- **Thiết kế:** FuturesChart (pure SVG, `web/src/components/futures/FuturesChart.tsx`) nhận
  prop `levels` — vẽ đường ngang entry/TP/SL/liq + nhãn giá màu theo side; data từ OPEN
  position (entry/tp/sl/liq_price đã có).
- **AC:** position OPEN → chart vẽ 4 đường đúng giá; position đóng → overlay biến mất;
  test render FuturesChart với levels.

### N6. Engine queue bounded + tick coalescing — [Technical T3]
- **Vấn đề:** `_futures_queue: asyncio.Queue()` không giới hạn (`app/main.py:68`);
  `_emit_mark` `await q.put` kẹt khi engine chậm; tick cũ chồng chất.
- **Thiết kế:** `maxsize` + drop-oldest (như `_fanout` client queue) hoặc per-symbol giữ
  tick mới nhất; watchdog dùng `put_nowait` + đếm drop.
- **AC:** bơm 10k tick nhanh hơn engine consume → queue bounded, không leak; watchdog
  không block quá 1 tick interval; tick cuối luôn là giá mới nhất.

## Backlog (còn lại từ brainstorm)

### Product
| # | Feature | Effort | Ghi chú |
|---|---|---|---|
| P2 | Export lịch sử giao dịch CSV + stats (win rate/profit factor) | S | tái dùng `GET /api/futures/trades` + pattern `export_forecasts.csv` |
| P5 | Custom Price Alerts ("BTC > 70,000") | M | bảng `price_alerts` + CRUD trong `app/api/alert_routes.py`; engine đánh giá trên từng tick |
| P6 | Multi-TF Confluence Gauge (6 timeframe đồng thuận) | S | aggregate các model intraday đã train; 0 tốn token AI |
| P7 | Equity Curve + drawdown theo thời gian | M | bảng `balance_snapshots` + `/api/futures/equity`; chart pattern CandleChart |
| P8 | Multi-Symbol Futures Dashboard (lưới 5 symbol) | M | `engine.last_mark` + positions/account user-scoped đã có |
| P9 | Leaderboard 2.0 risk-adjusted (win rate, avg score, cost-per-win, filter) | S-M | aggregation + UI sort trong Leaderboard.tsx |
| P10 | Backtest Lab (chiến lược theo tín hiệu model vs random_walk) | M | `app/forecast/backtest.py` + `app/models/eval.py` đã có |
| P11 | Telegram Trading Bot (`/balance`, `/positions`, `/close`) | M | long-poll getUpdates task trong lifespan; tái dùng store + engine |
| P12 | News & Sentiment Digest per symbol (RSS + AI tóm tắt) | M-L | `AIProvider` + `ai_daily_token_budget` đã có |

### Technical
| # | Feature | Effort | Ghi chú |
|---|---|---|---|
| T4 | Shared httpx connection pool (reuse REST client) | M | `_fetch_rest_mark` tạo AsyncClient mỗi 3s/symbol (`app/ws/relay.py:211-225`); dùng chung relay/klines/gapfill/LLM |
| T5 | Periodic WAL checkpoint (durability) | S | checkpoint chỉ lúc shutdown (`app/main.py:72-80`); crash → xóa WAL mất data (`app/api/routes.py:26-31`) |
| T6 | Structured logging + request correlation | M | middleware `request_id` + `X-Request-ID`; event INFO fill/close/liq/watchdog |
| T7 | Rate limiting auth + `/api/backfill` + `/api/ai/*` | S | in-memory per-IP sliding window; 429 + Retry-After; config qua env |
| T8 | CI pipeline + coverage threshold (≥75%) + audit | M | GitHub Actions 3 job; pytest `--cov-fail-under`; pip/npm audit |
| T9 | Futures kline freshness fallback (WS kline bị chặn) | M | watchdog poll `GET /fapi/v1/klines` ~15-30s → `_emit_kline` `source:"rest"`; không reset `last_frame_mono` |
| T10 | DB schema versioning (migrations có trật tự) | M | bảng `schema_version` + migration idempotent có thứ tự (`app/storage/duckdb_store.py:225-245`) |

## Ghi chú triển khai
- Thứ tự khuyến nghị trong Next up: N1 → N3 → N6 (hạ tầng, không đụng UI) → N2 → N4 → N5 (product).
- Mỗi feature kèm test; chạy lại full suite trước khi commit (chuẩn hiện tại: pytest 339 + vitest 63 + build).
- Môi trường dev: pytest cần fixture `tmp_path` override trong `tests/conftest.py` (sandbox khóa dir mode=0o700); vitest/build cần full-access sandbox (esbuild spawn).
