# Test Report — 2026-08-29 — SP5 Futures Trade Screen (full regression + UI)

## Test Results Overview
- **Backend (pytest)**: 332 passed / 0 failed / 0 skipped — 34.65s
- **Frontend (vitest)**: 63 passed / 0 failed (10 files) — 7.64s
- **Web build (tsc + vite)**: PASS (1826 modules, ~600ms, bundle 417KB / gzip 122KB)
- **UI browser (agent-browser, headless Chromium)**: 6/8 scenarios pass

## Coverage Metrics
| Suite | Result | Threshold | Status |
|-------|--------|-----------|--------|
| pytest (unit + integration) | 332/332 | 100% pass | PASS |
| vitest (web) | 63/63 | 100% pass | PASS |
| Build | OK | no errors | PASS |

(Coverage % không đo trong lần chạy này — không có flag --cov trong pytest.ini.)

## UI Test Results (local: uvicorn :8000 + vite :5173, Chrome headless)
- **Pages tested**: 5 (Dashboard, Leaderboard, Forecast, Trading, Alerts)
- **Screenshots**: `docs/qa/*.png`
- **Console errors**: none (chỉ vite HMR debug)
- **a11y (axe-core 4.12)**: 1 violation `color-contrast [serious]` — node `.inline-flex` (badge LIVE trên Dashboard), 19 passes
- **Responsive**: skipped (mặc định desktop viewport)
- **Auth flow**: register `qa_tester_01` → JWT → ví 10,000 USDT hiển thị đúng (Balance/Margin/Available) ✅
- **Trading gate**: chưa đăng nhập → order form disabled + Sign-in modal ✅
- **Limit order form**: nhập price → Margin + Liq. Price pre-check tính đúng theo công thức MMR buffer (100 USDT @10x → margin 10.00, liq ≈ 54,300 tại entry 60,000 — đúng `entry*(1-1/lev+0.005)`) ✅
- **Leaderboard / Forecast / Alerts**: render đủ dữ liệu, không lỗi console ✅

## Critical Issue (blocker 1)
### Binance futures WS không nhận push frame trong môi trường mạng hiện tại
- **Symptom**: `/ws/trade/BTCUSDT` mở OK nhưng 0 frame; frontend `mark = null` → nút Market Buy disabled vĩnh viễn; FuturesChart trống (không có kline đầu tiên — chart chỉ render khi nhận kline WS, không seed từ REST).
- **Root cause (đã phân lập)**:
  - `wss://fstream.binance.com` TCP+TLS handshake **OK** nhưng push bị drop trung gian (có thể là ISP/GFW-style filtering chọn theo nội dung stream): `bookTicker`, `trade` **đẩy được**, còn `markPrice`, `kline_*`, `aggTrade`, `!ticker@arr`, `!markPrice@arr` **im lặng hoàn toàn** (đã test cả 2 client websockets 15.0.1 và .NET ClientWebSocket, raw + combined stream, kline 1m chờ tới 70s).
  - Spot WS `stream.binance.com:9443` và `data-stream.binance.vision` đẩy bình thường mọi stream (aggTrade, kline_1m đều có frame < 1s).
- **Impact**: tính năng cốt lõi SP5 (mark realtime, engine tick-driven fill/TP/SL/liq) không chạy khi đứng sau mạng lọc fstream. Server fallback poll `/api/futures/mark` cũng vô dụng vì engine không nhận tick nào → `last_mark` rỗng → REST trả mark mặc định 50,000 (stale/giả).
- **Fix đề xuất (priority CRITICAL)**:
  1. Thêm fallback stream source cho relay: nếu fstream không có frame trong N giây (watchdog), chuyển sang `data-stream.binance.vision` (spot mark ~ giá futures) hoặc polling REST `premiumIndex` định kỳ (đã có sẵn `_inject_catchup` chỉ chạy 1 lần lúc connect).
  2. Seed chart kline đầu tiên từ REST `GET /fapi/v1/klines` thay vì chờ WS kline (chart trống mãi khi WS kline bị chặn).
  3. Cho phép cấu hình `binance_futures_ws_base` qua `.env` (hiện đã đọc settings — chỉ cần document) + thêm base dự phòng.

## Minor Issues
1. **Fallback polling mark chỉ chạy khi WS close** (`connectTradeWs.onclose` → `poll()`): nếu WS mở nhưng không có frame (đúng scenario hiện tại), client không poll → nên thêm watchdog "không nhận frame trong Xs → poll".
2. **vitest warning act()**: `OrderForm.test.tsx`, `App.test.tsx`, `ForecastCompare.test.tsx` có update state ngoài act() — không fail nhưng nên bọc act để sạch output.
3. **a11y color-contrast** trên badge LIVE (`.inline-flex`) — xem xét tăng độ tương phản.
4. **Klines polling dồn dập**: `GET /api/klines` gọi lặp liên tục (~40 lần/30s trên Dashboard) — nghi là polling loop không có interval đủ dài hoặc duplicate effect; nên throttle/caching.

## Đã verify OK (không cần sửa)
- REST auth register/login/JWT; ví ảo 10,000; pre-check margin/liq mirror công thức backend.
- Backend engine logic: 332 test pass bao gồm fill/netting/TP/SL/liquidation (đã test logic bằng unit test; không thể E2E live-fill do upstream bị chặn — xem Critical Issue).
- Web test 63 + build pass; 5 tab render không lỗi; không có page error.

## Build Status
- **Build**: PASS — `npm run build` (tsc -b && vite build)
- **Warnings**: chỉ React act() warnings trong vitest (không ảnh hưởng build)
- **Dependencies**: all resolved

## Critical Issues
1. [BLOCKER] fstream.binance.com bị drop push frames (markPrice/kline) trên mạng hiện tại → terminal futures không có giá realtime, Market Buy bị khóa, chart trống. Cần fallback nguồn giá (REST polling watchdog / vision domain) — đề xuất ở trên.

## Recommendations
1. [P0] Thêm watchdog + fallback nguồn mark price trong `app/ws/relay.py` (REST premiumIndex poll mỗi ~3-5s khi upstream im lặng > 5s) — engine sẽ sống ở mọi mạng.
2. [P1] Seed kline chart từ REST khi WS kline chưa có frame đầu tiên.
3. [P2] Bọc act() trong 3 test file web; fix contrast badge LIVE.
4. [P2] Throttle polling `/api/klines`.

## Unresolved Questions
- Môi trường mạng hiện tại có chính sách chặn fstream chủ đích không (ISP/firewall)? Nếu chỉ mất tạm thời, fallback vẫn nên làm vì chi phí thấp.

---

## Post-fix Verification — 2026-08-29 follow-up session

Toàn bộ blocker + 4 minor issues đã được fix và verify (commit `052274d`).

### Trạng thái các issue

| Issue | Status | Bằng chứng |
|---|---|---|
| [BLOCKER] fstream drop push frames | ✅ RESOLVED | Watchdog relay: WS im lặng >5s → poll REST `premiumIndex` mỗi 3s (base fapi riêng). Smoke live: markPrice inject tại [1.0s] (catch-up connect), [6.5s] (watchdog sau 5s im lặng), rồi mỗi ~3.5s — giá sống 77634.2 → 77644.8 dù fstream hoàn toàn im lặng |
| Minor 1: client WS watchdog (mở nhưng im lặng) | ✅ RESOLVED | `connectTradeWs`: WS OPEN nhưng không có frame >10s → `poll()` (check mỗi 5s) |
| Minor 2: act() warnings 3 test file | ✅ RESOLVED | vitest: 63 pass, **0 act warnings** |
| Minor 3: a11y contrast badge LIVE | ✅ RESOLVED (code) | `text-emerald-600` → `text-emerald-700` (giữ `dark:text-emerald-400`); browser axe re-check chưa chạy lại |
| Minor 4: `/api/klines` dồn dập (~40 req/30s) | ✅ RESOLVED | `fetchKlines`: dedupe in-flight + cache 10s/key; `force` cho manual refresh |

### Test counts (sau fix)
- **pytest: 339 passed** (332 baseline + 3 watchdog relay + 4 klines endpoint) — 0 fail
- **vitest: 63 passed** — 0 fail, 0 act warnings
- **Build: PASS** — 418.30 kB / gzip 122.22 kB (khớp baseline ~417/122)

### Tính năng mới trong đợt fix
- `GET /api/futures/klines/{symbol}` — public market data (không auth), fapi primary → spot fallback, mirror WS frame contract (`is_closed = close_time < now`). Smoke live: trả 5 nến 1m thật, nến đang mở `is_closed=false`.
- Seed effect trong `FuturesTerminal` — chỉ seed khi chart rỗng, không đè data WS.
- Settings mới: `binance_futures_rest_base` (fix luôn lỗi gọi `/fapi/v1/*` trên base spot), `binance_futures_ws_silence_timeout`, `binance_futures_rest_poll_interval`.

### Ghi chú môi trường dev (quan trọng cho phiên sau)
- DSH sandbox dịch `os.mkdir(mode=0o700)` (pytest tmp_path mặc định) thành ACL owner-only không truy cập được → mọi test dùng `tmp_path` fail (kể cả cleanup sessionfinish). Đã override fixture `tmp_path` trong `tests/conftest.py` (mode mặc định 0o777). Không cần `--basetemp` nữa.
- vitest/build cần full-access sandbox (esbuild spawn subprocess bị chặn EPERM).
- `.pytest_cache` bị khóa ACL từ phiên cũ → warning cacheprovider vô hại (đã gitignore).

### Còn lại chưa verify
- Browser UI smoke (axe re-check badge LIVE) — chưa chạy; Trading terminal giờ sẽ có mark price + chart ngay khi mở (watchdog + seed đã verify qua WS/REST live).
- Coverage % vẫn chưa đo (không có flag `--cov` trong pytest.ini).
