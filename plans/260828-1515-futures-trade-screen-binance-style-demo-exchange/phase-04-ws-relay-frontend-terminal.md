---
phase: 4
title: "WS relay + frontend terminal"
status: complete
priority: P1
effort: ""
dependencies: [3]
---

# Phase 4: WS relay + frontend terminal

## Overview

Backend: FastAPI WS endpoint `/ws/trade/{symbol}` relay Binance `markPrice` + `kline`
(mỗi symbol 1 upstream connection duy nhất, fan-out nội bộ), đồng thời feed engine.
Frontend: thay UI tab Trading bằng terminal Binance-style — chart + order form +
positions tabs, login modal, mark price realtime. **Red Team & Codex Review:** tick source phải độc lập
client, WS host đúng futures, Vite proxy /ws, chart v5 migration, test churn đầy đủ,
và tính toán liq price đồng bộ buffer MMR với backend.

## Requirements

- Functional: client nhận markPrice + kline frames; engine nhận cùng tick từ relay
  upstream reader (KHÔNG từ client handler); frontend đặt lệnh market/limit kèm leverage/TP/SL;
  positions P&L update realtime; đăng nhập/đăng ký; reset ví; đóng lệnh tay.
- **Validation S1 & Codex Review:**
  - **Chart futures RIÊNG** cho terminal (`FuturesChart.tsx` mới, realtime qua kline WS + price lines
    entry/TP/SL/liq). Dashboard GIỮ NGUYÊN chart hiện tại (`CandleChart.tsx` polling 30s) — không đụng.
  - **Tab Alerts riêng** trong nav — chuyển SP4 Alerts Feed ra tab riêng, giữ nguyên tính năng.
  - **Order form nhập notional USDT** → payload `notional_usdt`; server đổi ra coin qty theo
    mark (`qty = round(notional / mark, 6)`).
  - **Công thức tính liq price trên Frontend mirror chuẩn backend (ISSUE-1):**
    - LONG: `entry * (1 - 1/leverage + 0.005)`
    - SHORT: `entry * (1 + 1/leverage - 0.005)`
- Non-functional: reconnect tự động (Binance upstream + browser client) + single-flight
  `get_or_create` + jitter; fallback polling REST (`GET /api/futures/mark/{symbol}`) khi WS đứt;
  Vitest không render canvas (pattern `isCanvasAvailable` hiện có).
- **Red Team (bắt buộc):**
  - Tick feed engine từ upstream reader task (engine sống với 0 client) — test bắt buộc.
  - Upstream lifetime KHÔNG refcount về 0: engine giữ reference vĩnh viễn cho mọi symbol
    có OPEN position/order; evict chỉ khi không còn client VÀ không còn position/order.
  - Symbol validate `^[A-Z0-9]{4,20}$` + `in settings.symbol_list` TRƯỚC `get_or_create`;
    cap upstream connections.
  - Thêm setting `binance_futures_ws_base: str = "wss://fstream.binance.com"` RIÊNG —
    KHÔNG dùng chung `binance_ws_base` (đang là SPOT stream dùng cho kline worker).
  - Vite proxy: thêm `'/ws': { target: 'ws://127.0.0.1:8000', ws: true }` — không có thì
    browser WS không reachable trong dev.
  - Reconnect catch-up: sau khi reconnect, inject 1 tick từ REST mark (premiumIndex) để
    không miss liquidation window.
  - Relay normalize payload server-side về đúng frame contract `{type: 'markPrice'|'kline', ...}`
    (1 normalizer module + fixture tests) — frontend không parse raw Binance envelope.
  - `relay_disabled` app.state gate cho test (mirror ws_worker_disabled).

## Architecture

Backend:
- `app/ws/relay.py`: `BinanceRelay` quản lý 1 websockets connection tới
  `<binance_futures_ws_base>/stream?streams=<sym>@markPrice@1s/<sym>@kline_<tf>`;
  fan-out qua set of asyncio.Queues; upstream reader task push vào engine queue
  (độc lập client); `get_or_create(symbol)` single-flight + refcount + symbol validate;
  auto-reconnect backoff + catch-up tick.
- `/ws/trade/{symbol}`: accept → validate symbol → register queue → forward normalized
  frames JSON; unregister on disconnect. KHÔNG feed engine ở đây.
- Thêm `GET /api/futures/mark/{symbol}` đã có từ Phase 2 làm fallback polling.

Frontend (tab Trading, thay thế `Trading.tsx` hiện tại — xóa hẳn, không giữ tham khảo):
- `web/src/lib/futures.ts` — API client (auth token header, orders/positions/account/mark) +
  WS hook `useMarkPrice` (reconnect + fallback polling mark REST). **Red Team:** là owner duy nhất
  của frame parsing (server-normalized) + pre-check math (bao gồm MMR 0.5% buffer).
- `web/src/components/futures/TradeHeader.tsx` — symbol + mark price đổi màu theo tick.
- `web/src/components/futures/OrderForm.tsx` — leverage slider 1-125x, Market/Limit toggle,
  nhập NOTIONAL USDT (→ server đổi qty theo mark với precision 6 số thập phân), TP/SL, Long/Short buttons,
  hiển thị margin + liq price pre-check.
- `web/src/components/futures/PositionsPanel.tsx` — tabs Positions / Open Orders / History,
  P&L realtime, nút Close (toàn bộ) / Cancel.
- `web/src/components/futures/AuthModal.tsx` — login/register, JWT vào localStorage (tự động mở modal khi nhận 401).
- `web/src/components/futures/FuturesChart.tsx` — chart RIÊNG cho terminal
  (lightweight-charts v5, kline từ WS relay, price lines entry/TP/SL/liq). `CandleChart.tsx`
  của dashboard GIỮ NGUYÊN (không migrate, không đụng).

## Related Code Files

- Create: `app/ws/__init__.py`, `app/ws/relay.py`
- Modify: `app/config.py` (thêm `binance_futures_ws_base`), `app/main.py` (WS route + relay lifecycle + relay_disabled)
- Create: `tests/integration/test_ws_relay.py` (fake upstream, no-network marker)
- Create: `web/src/lib/futures.ts`, `web/src/components/futures/{TradeHeader,OrderForm,PositionsPanel,AuthModal,FuturesChart}.tsx`
- Create: `web/src/__tests__/{OrderForm,PositionsPanel,AuthModal,futures-lib,FuturesChart}.test.tsx`
- Modify: `web/src/App.tsx` (tab Trading render terminal mới, thêm tab Alerts), `web/vite.config.ts` (proxy /ws)
- Delete: `web/src/components/Trading.tsx`, `web/src/__tests__/Trading.test.tsx` (7 tests — thay bằng futures tests)
- Modify: `web/src/__tests__/App.test.tsx` — cập nhật assertions tab Trading
  (bỏ 'Alerts Feed', assert terminal mới) + thêm test tab 'Alerts' riêng (SP4 alerts giữ nguyên)

## Implementation Steps (TDD)

1. RED integration: `test_ws_relay.py` (fake upstream server, no-network):
   - client connect nhận markPrice frame (đã normalize).
   - 2 clients cùng symbol share 1 upstream (single-flight).
   - engine (spy) nhận tick kể cả khi 0 client connected.
   - symbol invalid → 400/close (whitelist + regex).
   - upstream reconnect → catch-up tick injected.
   - disconnect sạch, evict upstream khi không client + không position.
   GREEN: implement relay + route + `binance_futures_ws_base`.
2. RED frontend unit: `futures-lib` — order payload builder (notional_usdt), pre-check
   margin/liq calc (mirror formulas + buffer 0.5% đúng hướng), auth token header, WS url builder,
   frame parsing từ normalized contract. GREEN: `lib/futures.ts`.
3. RED: `OrderForm.test.tsx` — leverage slider, toggle Market/Limit, nhập notional USDT,
   submit gọi đúng payload `{notional_usdt, ...}`; `AuthModal.test.tsx` — register/login flow,
   token lưu. GREEN: implement components.
4. RED: `PositionsPanel.test.tsx` — render positions, pnl màu, Close gọi API, tabs switch.
   GREEN: implement.
5. RED: `FuturesChart` v5 — test API shape (series created, update incremental từ kline WS,
   price lines nhận entry/TP/SL/liq). GREEN: `FuturesChart.tsx` (mới) — KHÔNG đụng CandleChart.
6. Wire `App.tsx`: tab Trading → terminal; thêm tab 'Alerts' riêng (chuyển SP4 alerts feed);
   mark price từ WS hook; xóa `Trading.tsx` + `Trading.test.tsx`; cập nhật `App.test.tsx`;
   thêm proxy `/ws` trong vite.config.ts.
7. `npm run test` + `npm run build`; chạy full pytest lần cuối.

## Success Criteria

- [x] WS relay: 1 upstream/symbol, single-flight, fan-out, reconnect + catch-up (fake upstream test).
- [x] Engine nhận tick với 0 client connected (test).
- [x] UI: đặt market + limit order thành công từ form (nhập notional USDT), thấy position
      mới với P&L chạy theo tick.
- [x] Đóng lệnh tay + reset ví hoạt động end-to-end qua UI.
- [x] FuturesChart render kline WS realtime + price lines; dashboard chart
      (CandleChart) không đổi, vẫn polling 30s; tab 'Alerts' riêng hiển thị SP4 alerts.
- [x] `cd web && npm run test && npm run build` pass; full pytest pass.

## Risk Assessment

- Binance WS geo-block/rate-limit: `binance_futures_ws_base` riêng, reconnect exponential
  backoff + jitter + single-flight, catch-up tick sau reconnect, UI hiển thị disconnect + fallback
  polling `/api/futures/mark`.
- **Red Team:** lightweight-charts v5 — migrate trước, test API shape, không `catch{}` nuốt lỗi.
- **Red Team:** scope lớn — ưu tiên: order flow → positions → chart polish (price lines);
  nếu trôi, tách price lines thành follow-up sau khi order flow hoàn chỉnh.
