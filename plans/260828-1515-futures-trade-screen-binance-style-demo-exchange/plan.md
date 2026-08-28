---
title: "Futures Trade Screen - Binance-style demo exchange"
description: "Auth đầy đủ + ví ảo futures engine (market/limit, leverage, TP/SL, liquidation) + Binance WS proxy + UI terminal Binance-style ở tab Trading. Tách biệt hoàn toàn với SP4 paper trading."
status: approved
priority: P1
effort: ""
tags: [futures, paper-trading, auth, websocket, frontend]
created: 2026-08-28
---

# Futures Trade Screen - Binance-style demo exchange

## Overview

Dựng screen Trade futures giống Binance trong web-app: giá realtime qua Binance WS proxy,
order form (Market/Limit, leverage 1-125x, TP/SL, Long/Short), positions với P&L tính như
Binance USDT-M thật, liquidation, và ví ảo 10,000 USDT cho mỗi user (auth đầy đủ).
Engine nội bộ: thắng thua cộng/trừ balance ảo như sàn trade mẫu. KHÔNG gọi Binance order
API — Binance chỉ là nguồn giá. Tách bảng + endpoints riêng, không đụng SP4 pipeline.

Design doc (approved): `docs/260828-brainstorm-futures-trade-screen.md` — phương án A
(WS tick-driven engine, 1 nguồn data, single-process topology giữ nguyên).

## Goals

| # | Goal | Priority |
|---|------|----------|
| 1 | Auth register/login (bcrypt + JWT), mỗi user 1 ví ảo riêng | P1 |
| 2 | Futures engine: fill market/limit, TP/SL, liquidation theo mark-price tick | P1 |
| 3 | Công thức Binance USDT-M chính xác: margin, liq price (có MMR buffer), unrealized/realized P&L, ROI | P1 |
| 4 | Binance WS proxy: relay markPrice + kline ra frontend, feed engine cùng stream | P1 |
| 5 | UI terminal Binance-style ở tab Trading: chart + order form + positions tabs | P1 |

## Non-Goals

- Orderbook depth, trade history tabs (Binance full terminal) — làm sau nếu cần.
- Funding rate 8h.
- Real Binance order API / testnet.
- Migrate SP4 positions pipeline.
- Rate limiting trên auth endpoints (chấp nhận cho demo loopback — đã note trong Red Team Review).

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Phase 1: Formulas core (TDD)](./phase-01-start.md) | ✅ Complete |
| 2 | [Phase 2: Auth + futures tables](./phase-02-auth-futures-tables.md) | ✅ Complete |
| 3 | [Phase 3: Futures engine fill/PnL/liquidation](./phase-03-futures-engine-fillpnlliquidation.md) | ✅ Complete |
| 4 | [Phase 4: WS relay + frontend terminal](./phase-04-ws-relay-frontend-terminal.md) | ✅ Complete |

## Contracts (chốt, các phase phải tuân theo)

### DuckDB tables mới

```sql
users(id INTEGER PK, username TEXT UNIQUE, password_hash TEXT, created_at TIMESTAMPTZ)
futures_accounts(id INTEGER PK, user_id INTEGER UNIQUE FK, balance DOUBLE,
                 created_at TIMESTAMPTZ, reset_at TIMESTAMPTZ)
futures_orders(id INTEGER PK, user_id INTEGER FK, symbol TEXT, side TEXT,        -- LONG/SHORT
               type TEXT,                                                        -- MARKET/LIMIT
               price DOUBLE NULL, qty DOUBLE, leverage INTEGER,
               tp DOUBLE NULL, sl DOUBLE NULL,
               status TEXT,                                                      -- OPEN/FILLED/CANCELLED
               created_at TIMESTAMPTZ, filled_at TIMESTAMPTZ NULL)
futures_positions(id INTEGER PK, user_id INTEGER FK, symbol TEXT, side TEXT,
                  entry DOUBLE, qty DOUBLE, leverage INTEGER, margin DOUBLE,
                  liq_price DOUBLE, tp DOUBLE NULL, sl DOUBLE NULL,
                  status TEXT,                                                   -- OPEN/CLOSED
                  pnl DOUBLE NULL, exit_price DOUBLE NULL, closed_at TIMESTAMPTZ NULL,
                  close_reason TEXT NULL)                                        -- MANUAL/TP/SL/LIQUIDATION
```

> **Red Team & Review:** mọi cột thời gian dùng `TIMESTAMPTZ` + luôn ghi datetime tz-aware UTC, đọc qua `_ensure_utc()` — không dùng `TIMESTAMP` (host UTC+7 sẽ lệch 7h so với klines).

### Ownership, price integrity & Concurrency (Red Team & Review bắt buộc)

- Mọi query/update futures lấy `user_id` từ JWT `sub`, KHÔNG từ body; SQL predicate luôn `WHERE id = ? AND user_id = ?`. Đây là contract, không phải detail.
- **Server-authoritative price**: mọi fill/close dùng mark price từ engine cache — KHÔNG BAO GIỜ nhận `mark`/`exit_price` từ client body (reject hoặc bỏ qua). Không có Phase-2 placeholder fill theo body.
- **Concurrency & Transaction Safety**: `DuckDBStore` áp dụng `_write_lock` (`asyncio.Lock`) bao bọc toàn bộ `store.transaction()` cho mọi thao tác ghi dữ liệu (orders, positions, accounts).
- **Position Mode**: Áp dụng chuẩn **Hedge Mode** (tối đa 1 LONG và 1 SHORT riêng biệt cho mỗi cặp `user_id, symbol`). Lệnh cùng chiều sẽ được merge & netting theo weighted average entry; lệnh ngược chiều mở vị thế độc lập.
- Symbol validate `symbol.upper() in settings.symbol_list` ở order route + WS route (regex `^[A-Z0-9]{4,20}$`).
- JWT: `jwt_secret` KHÔNG có default, startup fail nếu unset/`<32 chars`; `jwt.decode(..., algorithms=["HS256"])`; bắt buộc `exp`.

### REST endpoints

- `POST /api/auth/register` `{username, password}` → `{token}` — min password 8, cap length 64
- `POST /api/auth/login` `{username, password}` → `{token}`
- `GET /api/futures/account` → `{balance, margin_used, unrealized_pnl}` (auth, user-scoped)
- `POST /api/futures/account/reset` → close all + cancel all + balance = 10,000 (auth) — atomic, 1 transaction
- `POST /api/futures/orders` (auth, user-scoped) → market: fill ngay tại engine mark; limit: lưu OPEN
- `DELETE /api/futures/orders/{id}` (auth, `WHERE id=? AND user_id=?`)
- `GET /api/futures/positions?status=` / `POST /api/futures/positions/{id}/close` (auth, user-scoped)
- `GET /api/futures/trades` — positions CLOSED, user-scoped (auth)
- `GET /api/futures/mark/{symbol}` → `{symbol, mark, ts}` — engine last mark, dùng cho WS fallback (auth)
- WS `/ws/trade/{symbol}` → `{type: 'markPrice'|'kline', ...}` frames — public market data,
  symbol validate theo `settings.symbol_list`; WS chỉ phát market data, KHÔNG có P&L cá nhân

### Công thức (pure module `app/trading/formulas.py`)

- `margin = qty * entry / leverage`
- **Liq Price có MMR Buffer 0.5% (ISSUE-1):**
  - `liq_price = entry * (1 - 1/leverage + 0.005)` (LONG)
  - `liq_price = entry * (1 + 1/leverage - 0.005)` (SHORT)
- `unrealized_pnl = (mark - entry) * qty` (LONG) · `(entry - mark) * qty` (SHORT)
- `roi = pnl / margin`
- Close: `balance = max(0.0, balance + margin + pnl)` · Liquidation: `balance = max(0.0, balance)` (mất margin, không âm ví)
- Notional conversion: `qty = round(notional_usdt / mark, 6)`

## Test Commands

```bash
.venv\Scripts\python.exe -m pytest tests/unit/test_formulas.py tests/unit/test_duckdb_store_futures.py tests/unit/test_futures_engine.py tests/integration/test_futures_api.py tests/integration/test_auth.py tests/integration/test_ws_relay.py
cd web && npm run test && npm run build
```

## Success Criteria

- [x] Register/login lấy JWT; mỗi user có ví ảo 10,000 USDT riêng, reset được.
- [x] Market order fill ngay tại mark price; limit order fill khi giá cross.
- [x] TP/SL/liquidation trigger tự động theo tick; balance cập nhật đúng công thức có MMR buffer.
- [x] Frontend: mark price realtime, order form nhập notional USDT, positions P&L live, đóng lệnh tay.
- [x] Full suite pass: pytest (332) + web test (63) + web build.

## Implementation Log — 2026-08-28 (`/ak:cook` code mode)

- Phase 1: `app/trading/formulas.py` — 8 hàm thuần, 23 tests.
- Phase 2: `app/auth/{security,deps}.py`, 4 bảng futures + `transaction()`/`_write_lock` trong DuckDBStore, `futures_routes.py`, jwt fail-fast; 62 tests mới.
- Phase 3: `app/trading/futures_engine.py` — hedge mode netting, TP/SL/liq, startup reconcile; wire routes + lifespan; 20 unit + integration tests.
- Phase 4: `app/ws/relay.py` + `/ws/trade/{symbol}`; frontend terminal (`lib/futures.ts`, 6 components), tab Alerts riêng, xóa Trading.tsx; 10 relay tests + 30 web tests mới.
- Code review: APPROVE. Fix H-1 (double-charge margin khi merge cùng chiều — trả lại margin cũ), thêm `unrealized_pnl` vào account contract (M-1), wire price lines entry/TP/SL/liq vào FuturesChart (L-2).
- Test: pytest 332 pass, web 63 pass, web build pass.

## Validation Log

### Session 1 — 2026-08-28
**Trigger:** `/ak:plan validate` sau red-team — chốt các decision point chưa được brainstorm/red-team phủ.
**Questions asked:** 6

#### Questions & Answers

1. **[Architecture]** Mở 2 lệnh LONG BTC cùng lúc — Binance gộp thành 1 vị thế (average entry). Engine xử lý thế nào?
   - Options: Netting theo symbol | 1 row / 1 order
   - **Answer:** Netting theo symbol (Recommended) — Hedge Mode (1 LONG và 1 SHORT độc lập per symbol).
   - **Rationale:** giống Binance thật, engine đơn giản khi close; merge khi cùng chiều.

2. **[Scope]** Tab Trading hiện tại chứa 'Alerts Feed' của SP4 — khi thay bằng terminal futures, alerts đi đâu?
   - Options: Tab Alerts riêng | Bỏ khỏi UI | Nhúng vào terminal
   - **Answer:** Tab Alerts riêng (Recommended)
   - **Rationale:** giữ tính năng SP4, không phá pipeline feedback/retrain; thêm nav item 'Alerts'.

3. **[Assumptions]** Order form nhập khối lượng theo đơn vị nào?
   - Options: Notional USDT | Coin qty | Toggle cả hai
   - **Answer:** Notional USDT (Recommended)
   - **Rationale:** nhập 100 USDT → server đổi ra coin qty theo mark với round 6 chữ số thập phân.

4. **[Risks]** Red-team ghi nhận liq price thiếu maintenance margin buffer. Có thêm buffer không?
   - Options: Thêm buffer 0.5% | Giữ thuần 1/leverage
   - **Answer:** Thêm buffer 0.5% (Recommended)
   - **Rationale:** gần Binance thật hơn; Phase 1 thêm test; frontend mirror cùng công thức buffer.

5. **[Scope]** Plan có relay kline WS cho chart; chart v5 vốn setData toàn bộ 30s/lần — thêm kline WS đáng công không?
   - **Answer:** Chart futures RIÊNG + realtime nhất (`FuturesChart.tsx` cho terminal; dashboard giữ polling 30s không đổi).

6. **[Architecture]** Đóng vị thế — có cần partial close như Binance không?
   - Options: Chỉ Close toàn bộ | Thêm Close %
   - **Answer:** Chỉ Close toàn bộ (Recommended)
   - **Rationale:** đúng yêu cầu tối giản; không thêm partial-close logic.

#### Confirmed Decisions
- **Netting & Hedge Mode:** gộp position cùng symbol+hướng (average entry); cho phép 1 LONG và 1 SHORT riêng biệt.
- **Alerts:** chuyển thành tab 'Alerts' riêng trong nav (giữ SP4 UI + pipeline nguyên vẹn).
- **Qty input:** order form nhập notional USDT; server đổi ra coin qty theo mark (`round(..., 6)`).
- **Liq buffer:** thêm 0.5% MMR buffer vào liq price: Long = `entry * (1 - 1/lev + 0.005)`, Short = `entry * (1 + 1/lev - 0.005)`.
- **Chart futures:** component `FuturesChart.tsx` riêng cho terminal, realtime qua kline WS; dashboard giữ nguyên polling 30s.
- **Close:** chỉ đóng toàn bộ position (không partial close).

---

## Codex Plan Review Log (Session 2026-08-28)

**Review Verdict:** `APPROVE` (Sau khi đã áp dụng toàn bộ 6 issues từ Codex Review)

| # | Finding / Issue | Severity | Category | Resolution Applied |
|---|-----------------|----------|----------|-------------------|
| 1 | Sai dấu buffer MMR trong công thức Liq Price (`* 0.995` làm giá thanh lý trễ sau điểm cháy) | Critical | Correctness | Đã sửa thành `entry * (1 - 1/lev + 0.005)` (Long) và `entry * (1 + 1/lev - 0.005)` (Short) ở Phase 1 & 4. |
| 2 | Chưa chỉ định rõ Hedge Mode hay One-way Mode khi Netting | High | Architecture | Đã xác định chuẩn **Hedge Mode** (1 LONG và 1 SHORT độc lập per symbol) ở Phase 3. |
| 3 | Phạm vi Lock của DuckDB Store chưa bao quát toàn bộ Write Operations | High | Architecture | Đã tích hợp `_write_lock` cấp Store bao bọc toàn bộ `store.transaction()` ở Phase 2 & 3. |
| 4 | Mâu thuẫn vòng đời Phase 2 Order Creation khi chưa có FuturesEngine | Medium | Sequencing | Đã phân tách rõ Phase 2 lưu OPEN (kèm mock test) và Phase 3 engine execute fill. |
| 5 | Thiếu cơ chế chặn số dư âm (Negative Balance Floor) khi nến gap | Medium | Risk | Đã thêm clamp `max(0.0, balance + margin + pnl)` bảo vệ tài khoản ví ảo. |
| 6 | Chưa chuẩn hóa độ chính xác quy đổi Notional USDT $\rightarrow$ Qty | Low | Scope | Đã thống nhất làm tròn 6 chữ số thập phân (`round(notional/mark, 6)`). |

---

### Whole-Plan Consistency Sweep
- Files reread: `plan.md`, `phase-01-start.md`, `phase-02-auth-futures-tables.md`, `phase-03-futures-engine-fillpnlliquidation.md`, `phase-04-ws-relay-frontend-terminal.md`
- Consistency Status: **100% Aligned & Approved**
- Ready for Implementation: Yes (Khi user yêu cầu bắt đầu code).

<!-- slug: futures-trade-screen-binance-style-demo-exchange -->
