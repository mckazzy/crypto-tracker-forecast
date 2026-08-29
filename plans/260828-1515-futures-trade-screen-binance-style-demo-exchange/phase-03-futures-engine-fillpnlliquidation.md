---
phase: 3
title: "Futures engine fill/PnL/liquidation"
status: complete
priority: P1
effort: ""
dependencies: [2]
---

# Phase 3: Futures engine fill/PnL/liquidation

## Overview

Asyncio task `FuturesEngine` chạy trong process: nhận mark-price ticks (push qua
`on_mark_price(tick)`), evaluate limit fill / TP / SL / liquidation cho tất cả
positions + open orders, cập nhật balance. Thay thế behavior placeholder của
POST orders ở Phase 2. **Red Team & Codex Review:** engine phải là nguồn giá duy nhất (server-authoritative),
có startup reconciliation, quản lý vị thế theo **Hedge Mode**, và mọi mutation trong 1 transaction an toàn.

## Requirements

- Functional: market fill ngay tại mark; limit fill khi mark cross price (long-limit:
  mark ≤ price; short-limit: mark ≥ price); TP/SL trigger theo mark; liquidation khi
  mark chạm liq_price; balance cập nhật theo formulas Phase 1.
- Non-functional: evaluate đồng bộ trong event loop (O(orders+positions) mỗi tick, chấp nhận
  cho demo); exception trong 1 tick không kill task.
- **Red Team & Codex Review (bắt buộc):**
  - **Position Mode (ISSUE-2):** Áp dụng chuẩn **Hedge Mode** (mỗi user có thể giữ đồng thời
    1 vị thế LONG và 1 vị thế SHORT độc lập trên cùng 1 symbol).
    - Mở cùng chiều (ví dụ đang có LONG, đặt thêm LONG) → **MERGE & Netting**:
      `new_qty = old_qty + qty`,
      `avg_entry = (old_entry * old_qty + fill_price * qty) / new_qty`,
      `margin = avg_entry * new_qty / leverage`,
      tính lại `liq_price` theo công thức có buffer MMR của Phase 1.
    - Mở ngược chiều (đang có LONG, đặt SHORT) → Tạo riêng vị thế SHORT độc lập (không trừ/partial vị thế LONG).
    - Đóng vị thế: Đóng toàn bộ vị thế của chiều đó (không partial close).
  - **Startup reconciliation:** engine load ALL `status='OPEN'` orders + positions từ DB
    khi khởi động, re-evaluate theo mark hiện tại (REST `premiumIndex` hoặc relay) trước
    khi nhận tick live. Test restart: đặt limit → restart → tick cross → fill.
  - **Atomicity & Concurrency (ISSUE-3):** mỗi mutation (fill/close/liquidation/reset) = 1 transaction qua
    `store.transaction()` — position close + balance credit trong cùng BEGIN/COMMIT dưới sự bảo vệ của Store write-lock.
  - **Liveness:** engine nhận tick từ relay upstream task (KHÔNG từ client handler) —
    engine sống kể cả khi 0 client; test: không client nào connected → engine vẫn liquidate.
  - Feed tick qua 1 queue duy nhất (engine `consume` từ queue — relay upstream push),
    không feed trực tiếp trong vòng lặp client → không trùng tick.
  - Symbol whitelist: validate `symbol.upper() in settings.symbol_list` khi mở position.
  - Balance mutation = 1 SQL statement (`UPDATE ... SET balance = balance + ?`),
    không read-then-write; bảo đảm isolated margin không âm tiền (`calc_close_balance` clamp).
  - Exception trong tick: log + tiếp tục, NHƯNG balance write thất bại phải retry/log —
    không silent drop. Test: close thành công ⇒ balance delta quan sát được.
  - Mọi futures route `async def` (không để FastAPI threadpool interleave giữa
    read/write balance).

## Architecture

- `app/trading/futures_engine.py`: class `FuturesEngine(store)` với
  `async def run()` (consume asyncio.Queue) + `on_mark_price(price, symbol)` từ relay
  upstream reader + `last_mark` cache (dùng cho `GET /api/futures/mark`).
- app.main lifespan khởi động task; graceful cancel on shutdown + `PRAGMA checkpoint`.
- Validation mở vị thế: symbol whitelist; margin ≤ available (balance − margin dùng dở);
  leverage clamp 1-125; qty > 0 (làm tròn 6 chữ số thập phân).
- Evaluate thứ tự trong 1 tick: SL → TP → liq (dùng mark cuối; chấp nhận gap demo-level).

## Related Code Files

- Create: `app/trading/futures_engine.py`
- Modify: `app/api/futures_routes.py` (POST orders → validate + fill qua engine; close dùng engine mark)
- Modify: `app/main.py` (lifespan: start/stop engine task, startup reconciliation, shutdown checkpoint)
- Create: `tests/unit/test_futures_engine.py`
- Modify: `tests/integration/test_futures_api.py` (market order giờ fill qua engine; close dùng mark)

## Implementation Steps (TDD)

1. RED unit: `test_futures_engine.py` với fake store (in-memory), KHÔNG cần duckdb:
   - market LONG fill → position entry = mark, margin đúng, balance trừ margin.
   - limit LONG không fill khi mark > price; fill khi mark ≤ price.
   - limit SHORT không fill khi mark < price; fill khi mark ≥ price.
   - TP long: mark ≥ tp → close, pnl = (tp − entry)×qty, balance += margin + pnl.
   - SL short: mark ≥ sl → close lose.
   - liquidation long: mark ≤ liq → close LIQUIDATION, balance không hoàn margin (không âm ví).
   - margin check: order vượt available → reject.
   - **Hedge Mode & Netting:**
     - LONG mở 2 lần → 1 vị thế LONG, qty gộp, avg entry đúng.
     - LONG đang mở, mở thêm SHORT → tồn tại 2 vị thế LONG và SHORT riêng biệt.
     - Đóng vị thế → đóng toàn bộ chiều được chọn.
   - **Red Team:** exception trong tick → engine vẫn sống (tick sau vẫn evaluate).
   - **Red Team:** startup load OPEN orders/positions → tick sau vẫn evaluate đúng.
   - **Red Team:** 0 client connected → tick vẫn tới engine (queue từ upstream, không từ client).
   - **Red Team:** mutation failure → balance không đổi (transaction rollback).
2. GREEN: implement engine dùng formulas.py; tick từ queue; mọi mutation qua transaction.
3. Wire vào futures_routes (POST orders) + main lifespan (startup reconciliation + shutdown checkpoint).
4. RED→GREEN integration: market order qua API tạo position FILLED, GET account
   phản ánh margin_used; close API tính pnl bằng engine mark (bỏ qua body price);
   restart app giữa phiên → limit order vẫn fill sau restart.
5. Chạy full pytest.

## Success Criteria

- [x] `pytest tests/unit/test_futures_engine.py` pass (≥12 assertions key, gồm startup reconcile + 0-client + Hedge Mode netting).
- [x] Full pytest pass.
- [x] Engine là 1 asyncio task duy nhất, cancel sạch on shutdown, checkpoint trước khi close.
- [x] Không có mutation nào ngoài transaction; balance chỉ đổi qua `balance = balance + ?`.

## Risk Assessment

- Gap risk (1 candle nhảy qua cả TP và liq): evaluate thứ tự SL → TP → liq trong 1 tick,
  dùng mark cuối; chấp nhận sai lệch demo-level (đã ghi design doc).
- **Red Team:** sync DuckDB trong event loop block các task khác — chấp nhận cho demo
  (tick budget nhỏ), nhưng `POST /backfill` phải wrap `asyncio.to_thread` + single-writer
  lock để không đóng băng engine phút chốc; ghi chú degradation trong code.
- **Red Team:** crash giữa mutation → transaction rollback giữ ledger nhất quán;
  boot-time reconcile phát hiện trạng thái lệch.
