# Handoff — SP5 follow-up (QA fixes) — 2026-08-29

> Phiên này bị treo giữa chừng (model hang khi gọi tool) TRƯỚC KHI viết bất kỳ dòng code nào.
> Chưa có file nào bị sửa. Toàn bộ giá trị của phiên = nghiên cứu + thiết kế đã chốt bên dưới.

## Trạng thái repo

- Branch: `master` @ `8694961` (SP5 futures demo exchange), working tree sạch trừ `docs/qa/` (chưa commit).
- Chưa có thay đổi code nào trong phiên này — mọi fix bên dưới là **việc cần làm**, không phải đã làm.

## Nguồn yêu cầu (đọc để hiểu full context)

1. `docs/qa/test-report-2026-08-29-sp5.md` — báo cáo QA phiên trước: 332 pytest + 63 vitest + build pass; UI test 6/8; blocker + 4 minor issues + recommendations P0/P1/P2.
2. Tóm tắt phiên trước (trong conversation, không có file): danh sách việc tiếp theo ưu tiên.

## Việc cần làm (theo thứ tự ưu tiên)

### 1. [P0] Watchdog fallback nguồn giá — `app/ws/relay.py` + `app/config.py`

**Vấn đề:** `fstream.binance.com` bị mạng drop push frames (markPrice, kline_*, aggTrade im lặng hoàn toàn;
bookTicker/trade thì OK; spot WS OK). Engine không nhận tick → REST mark trả 50,000 mặc định,
Market Buy khóa vĩnh viễn, chart futures trống.

**Thiết kế đã chốt (chưa code):**
- `config.py` thêm 2 settings:
  - `binance_futures_ws_silence_timeout: float = 5.0`
  - `binance_futures_rest_poll_interval: float = 3.0`
- `relay.py`:
  - Mỗi `_Upstream` track `_last_frame_mono` (dùng `time.monotonic()`), update khi nhận **frame thật từ WS** (không tính frame tự inject).
  - Thêm watchdog coroutine per-upstream (chạy song song `_run_upstream`): mỗi giây check silence;
    nếu im lặng > `silence_timeout` → poll REST `GET {settings.binance_rest_base}/fapi/v1/premiumIndex?symbol=X`
    → fanout frame `markPrice` + push engine tick `{"symbol", "mark"}`; trong khi vẫn im lặng, poll lại mỗi
    `rest_poll_interval` giây. Frame WS thật đến → reset.
  - Refactor `_inject_catchup` thành 2 hàm dùng chung: `_fetch_rest_mark(symbol) -> float | None` (httpx, timeout 10s,
    try/except trả None) và `_emit_mark(up, mark)` (fanout + engine queue). Watchdog tái dùng cả hai.
  - Cancel watchdog task trong `_run_upstream` khi bị cancel + trong `shutdown()`.
- **Lưu ý về fapi vs spot:** hiện `binance_rest_base = https://api.binance.com` (SPOT) nhưng
  `_inject_catchup` đang gọi `/fapi/v1/premiumIndex` trên base đó — có thể sai base. Cân nhắc thêm setting
  `binance_futures_rest_base: str = "https://fapi.binance.com"` và dùng nó cho cả catch-up lẫn watchdog.
  (QA ghi nhận fapi REST không bị chặn — chỉ WS streams bị drop.)

**Test cần thêm** (`tests/integration/test_ws_relay.py`, dùng pattern `fake_connect` + `FakeUpstream` sẵn có):
- Silence > timeout → watchdog inject mark (monkeypatch `_fetch_rest_mark`), client queue nhận frame, engine queue nhận tick.
- Frame WS đến liên tục → KHÔNG poll REST.
- `_last_frame_mono` reset khi frame WS đến.

### 2. [P1] Seed kline đầu tiên của FuturesChart từ REST

**Vấn đề:** chart chỉ render khi nhận kline WS; kline WS bị chặn → chart trống mãi.
**Lưu ý:** `/api/klines` hiện có ĐỌC TỪ LOCAL DuckDB và **không có timeframe 1m** trong
`settings.timeframes` (5m,15m,1h,4h,1d,1w) → không dùng được cho futures chart.

**Thiết kế đã chốt (chưa code):**
- Server (`app/api/futures_routes.py`): thêm endpoint **public market data** (không auth, mirror contract WS):
  `GET /api/futures/klines/{symbol}?timeframe=1m&limit=200` — validate symbol như `_validate_symbol` nhưng không Depends auth;
  httpx gọi `GET {fapi_base}/fapi/v1/klines` (primary), fallback `GET {spot_base}/api/v3/klines` nếu fapi lỗi/geo-block;
  map raw array Binance `[open_time, open, high, low, close, volume, close_time, ...]` →
  `{open_time, close_time, open, high, low, close, volume, is_closed}` với `is_closed = close_time < now_ms`.
- Client (`web/src/lib/futures.ts`): `fetchFuturesKlines(symbol, timeframe='1m', limit=200) -> KlineFrame[]`.
- `FuturesTerminal.tsx`: effect on `[symbol]` — nếu `candleRef.current.length === 0` → fetch seed
  → `candleRef.current = frames.slice(-MAX_CHART_CANDLES)` + `setCandles(...)`. WS kline frame thật đến sẽ
  overwrite/update candle cuối như logic hiện tại (onKline đã xử lý update-vs-append).
- Chỉ seed 1 lần mỗi symbol; KHÔNG seed đè data WS đã có.

### 3. [P2] Minor fixes

a. **Client WS watchdog** (`web/src/lib/futures.ts` `connectTradeWs`): hiện `poll()` chỉ chạy trong `onclose`.
   Thêm: track `lastFrameTs = Date.now()` trong `onmessage`; `setInterval(5s)` check nếu WS đang OPEN nhưng
   `Date.now() - lastFrameTs > 10_000` → `poll()`. Clear interval trong cleanup.

b. **act() warnings** (không fail, chỉ warning): `web/src/__tests__/OrderForm.test.tsx`, `App.test.tsx`,
   `ForecastCompare.test.tsx` — bọc các update state async (fire-and-forget promise `.then(setState)`) trong `await act(async () => {...})`.

c. **Contrast badge LIVE** (`web/src/App.tsx` dòng ~142): axe violation `color-contrast [serious]`.
   Sửa class span: `text-emerald-600` → `text-emerald-700` (giữ `dark:text-emerald-400`).

d. **Throttle `/api/klines` dồn dập** (~40 req/30s trên Dashboard):
   - `web/src/lib/api.ts` `fetchKlines`: thêm throttle/dedupe — cache in-flight promise theo key `symbol|timeframe|limit`;
     min-interval 10s mỗi key (cache response, trả cached nếu gọi lại trong 10s). Manual refresh (nút Refresh trong App)
     cần bypass → thêm optional param `opts?: { force?: boolean }`.
   - App.tsx hiện có 2 đường fetch (effect 30s + `load` callback) — có thể gộp 1 path nếu muốn.
   - Nghi ngờ nguyên nhân gốc: main.tsx dùng StrictMode (dev double-invoke effects) + nhiều component poll
     (App 30s, ForecastCompare 15s/60s, Leaderboard/Alerts 30s). Throttle ở `fetchKlines` xử lý mọi trường hợp.

### 4. Chạy lại test

```bash
# backend (venv sẵn có: .venv\Scripts\python.exe)
.venv\Scripts\python.exe -m pytest tests/ -q          # baseline: 332 pass
cd web && npm run test && npm run build               # baseline: 63 pass + build ok
```

### 5. UI smoke qua trình duyệt (tùy chọn nhưng nên làm)

- uvicorn app.main:app --port 8000 + vite (5173), tab Trading: chart CÓ candles (seed REST), mark price hiện
  (watchdog inject), Market Buy enabled. Console không error mới. Compare với screenshots cũ trong docs/qa/*.png.

### 6. Commit (một commit hoặc tách 2: docs + fixes)

- `docs/qa/` (báo cáo + screenshots) — bằng chứng phiên QA.
- Code fixes + tests mới.
- Gợi ý message: `fix: SP5 fallback mark-price watchdog + seed kline REST + QA minor fixes`

### 7. Dọn checkbox plan SP5 (dọn xong scanner sẽ hết báo 23%)

Plan `plans/260828-1515-futures-trade-screen-binance-style-demo-exchange/`: cả 4 phase file có
`status: complete` trong frontmatter + plan.md ghi ✅ Complete, nhưng **17 checkbox `- [ ]` chưa tick**
(scanner đo 5/22 = 23%). Cả 17 đều là acceptance criteria ĐÃ đạt (332+63 test pass):
- phase-01: 3 ô (pytest formulas pass, không import duckdb/fastapi, liq MMR đúng hướng)
- phase-02: 4 ô (pytest store/auth/api pass, full pytest, SP4 không đổi, IDOR/price/JWT checks)
- phase-03: 4 ô (engine tests, full pytest, single task shutdown, mutation trong transaction)
- phase-04: 6 ô (WS relay tests, engine 0-client, UI market+limit, close+reset, chart realtime, web test+build)
→ Tick tất cả thành `- [x]` sau khi chạy lại suite pass để đảm bảo không giả mạo kết quả.

## File đã đọc trong phiên này (context tiết kiệm cho phiên sau)

- `docs/qa/test-report-2026-08-29-sp5.md` (67 dòng)
- `app/ws/relay.py` (232) — BinanceRelay, _run_upstream, _inject_catchup, _fanout, shutdown
- `app/api/futures_routes.py` (244) — auth/orders/positions/mark endpoints, _engine_mark default 50000
- `app/api/routes.py` (80 đầu) — /api/klines đọc local DuckDB, không có 1m
- `app/connectors/binance_rest.py` (151) — BinanceRestClient (spot /api/v3), _normalize klines
- `app/config.py` (80) — settings, chưa có silence/poll settings, binance_futures_ws_base có sẵn
- `app/main.py` (178) — lifespan wiring engine + relay, /ws/trade/{symbol}
- `app/trading/futures_engine.py` — chỉ grep: engine nhận tick qua `_queue` dạng `{"symbol", "mark"}`
- `web/src/components/futures/FuturesTerminal.tsx` (208) — candles state + candleRef, onMark/onKline
- `web/src/components/futures/FuturesChart.tsx` (143) — pure render, nhận candles prop
- `web/src/lib/futures.ts` (293) — connectTradeWs (poll chỉ onclose), fetchMark, calc* helpers
- `web/src/lib/api.ts` (39) — fetchKlines chưa throttle
- `web/src/App.tsx` (497) — LIVE badge dòng ~142, fetchKlines effect 30s + load callback
- `web/src/main.tsx` — StrictMode ON
- `tests/integration/test_ws_relay.py` (193) — fake_connect + FakeUpstream pattern cho test watchdog
- `plans/.../plan.md` + grep checkbox 4 phase files

## Trạng thái watzup scan (2026-08-29)

- master @ 8694961, dirty: `?? docs/qa/` — commit trước khi switch context.
- Plan SP5: 5/22 todos · 23% (do checkbox chưa tick — xem mục 7).
- Không có roadmap/milestone file nào trong docs/.
