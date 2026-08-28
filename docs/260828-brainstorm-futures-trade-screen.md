# Brainstorm: Futures Trade Screen (Binance-style demo exchange)

Ngày: 2026-08-28 · Status: APPROVED (phương án A)

## Problem

Dựng screen Trade futures giống Binance trong web-app hiện có: giá realtime, order form
(Market/Limit, leverage, TP/SL), positions với P&L tính như thật, liquidation, và hệ thống
ví ảo (pool token) cho mỗi user — thắng thua trừ/thêm tiền ảo như một sàn trade mẫu.

## Requirements (chốt)

- **Execution**: paper trading engine nội bộ — ví ảo 10,000 USDT/account, nút Reset.
  KHÔNG gọi Binance order API; chỉ dùng Binance làm nguồn giá.
- **Auth đầy đủ**: username/password, JWT session, mỗi user 1 ví ảo riêng.
- **Layout**: Chart + order form + positions (không orderbook, không trade history tabs).
- **Realtime**: Binance WS proxy — backend relay `markPrice`/`kline` ra frontend qua 1 WS.
- **Orders**: Market + Limit, leverage slider, TP/SL, Long/Short.
- **Liquidation**: có — tính liq price theo leverage/margin, mark price chạm → tự đóng, mất margin.
- **Tách biệt SP4**: bảng + endpoints mới, không đụng positions/AI feedback pipeline hiện tại.

## Evaluated approaches

| Approach | Mô tả | Kết luận |
|---|---|---|
| A — WS tick-driven (CHỌN) | WS proxy feed mark price ticks thẳng vào engine; evaluate fill/TP/SL/liq theo từng tick | 1 nguồn data, realtime thật, tận dụng topology single-process |
| B — Background poll | Engine poll mark price 1-2s | Liquidation trễ, 2 đường data |
| C — Evaluate on-read | Chỉ evaluate khi frontend gọi API | Lệnh không fill khi không ai mở trang — loại |

## Final design (Approach A)

### Backend (FastAPI, single-process — giữ nguyên ràng buộc 1 connection DuckDB)

1. **Auth module** (`app/auth/`): register/login (bcrypt), JWT, dependency `get_current_user`.
2. **Futures engine** (`app/trading/futures_engine.py`): asyncio task nhận mark-price ticks
   từ WS relay → market fill ngay tại mark, limit fill khi giá cross, TP/SL trigger,
   liquidation check. Ghi qua `DuckDBStore` (cursor chia sẻ, set TimeZone mỗi cursor).
3. **WS relay** (`app/ws/relay.py`): server subscribe Binance `markPrice` + `kline` cho symbol
   được yêu cầu, forward ra client kèm feed vào engine. Endpoint: `ws /ws/trade/{symbol}`.
4. **Routes** (`app/api/futures_routes.py`):
   - `POST /api/auth/register` / `POST /api/auth/login` → JWT
   - `GET /api/futures/account` — balance, margin dùng, unrealized P&L
   - `POST /api/futures/account/reset` — nạp lại 10,000 USDT
   - `POST /api/futures/orders` — đặt lệnh (market/limit, leverage, TP/SL, long/short)
   - `DELETE /api/futures/orders/{id}` — hủy limit
   - `GET /api/futures/positions` / `POST /api/futures/positions/{id}/close`
   - `GET /api/futures/trades` — lịch sử

### DuckDB tables mới (tách SP4)

- `users(id, username, password_hash, created_at)`
- `futures_accounts(id, user_id, balance, created_at, reset_at)`
- `futures_orders(id, user_id, symbol, side LONG/SHORT, type MARKET/LIMIT, price, qty,
  leverage, tp, sl, status OPEN/FILLED/CANCELLED, created_at, filled_at)`
- `futures_positions(id, user_id, symbol, side, entry, qty, leverage, margin, liq_price,
  tp, sl, status OPEN/CLOSED, pnl, exit_price, closed_at, close_reason MANUAL/TP/SL/LIQUIDATION)`

### Công thức (như Binance USDT-M)

- Margin = qty × entry / leverage
- Liq price ≈ entry × (1 ∓ 1/leverage) (long: entry×(1−1/lev)±buffer, short: ngược lại)
- Unrealized P&L = (mark − entry) × qty × dir; ROI = P&L / margin
- Đóng lệnh: balance += margin + P&L; liquidation: balance += 0 (mất margin)

### Frontend (React tab Trading — thay UI hiện tại của tab này)

- Header: symbol, mark price realtime (WS), giá đổi màu theo tick.
- Trái: `CandleChart` (lightweight-charts, tái dùng) + line entry/TP/SL/liq trên chart.
- Phải: Order form — leverage slider (1-125x), Market/Limit toggle, qty (USDT hoặc coin),
  TP/SL inputs, nút Long (xanh) / Short (đỏ), hiển thị margin/liq price trước khi xác nhận.
- Dưới: tabs Positions / Open Orders / History; đóng lệnh tay; P&L realtime.
- Login/Register modal khi chưa có JWT; token lưu localStorage.

## Phases đề xuất cho plan

1. Auth + tables mới + account endpoints (+reset)
2. Engine: market/limit fill + P&L + TP/SL + liquidation (unit tests công thức trước)
3. WS relay + feed engine
4. UI terminal (order form + chart overlay + positions tabs + login modal)

## Risks

- WS relay thêm điểm hỏng: cần auto-reconnect Binance + client, fallback polling nếu WS đứt.
- Liquidation theo tick có thể miss gap lớn (1 candle nhảy qua liq) → chấp nhận, demo level.
- Giá 1 connection Binance WS共用 nhiều client: relay 1 stream duy nhất, fan-out nội bộ.
- Test canvas chart với Vitest: tái dùng pattern `isCanvasAvailable` của CandleChart hiện tại.
