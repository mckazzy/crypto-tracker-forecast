---
phase: 1
title: "Formulas core (TDD)"
status: complete
priority: P1
effort: ""
dependencies: []
---

# Phase 1: Formulas core (TDD)

## Overview

Pure-function module `app/trading/formulas.py` chứa toàn bộ công thức Binance USDT-M
(margin, liq price, P&L, ROI). Viết TEST TRƯỚC — đây là phần dễ sai nhất của toàn plan,
phải khóa hành vi bằng test trước khi engine Phase 3 dùng nó.

## Requirements

- Functional: hàm thuần `(args) -> number`, không IO, không side-effect.
- Non-functional: Decimal hoặc float nhất quán (dùng float, app demo); timezone-agnostic.
- **Red Team & Review:** thêm `calc_margin_available(balance, margin_used)` (guard margin_used > balance) để reset/liquidation không tạo balance âm.
- **Validation S1 & Codex Review (ISSUE-1):** `calc_liq_price` áp dụng maintenance margin buffer (MMR) 0.5% chuẩn Binance:
  - LONG: `entry * (1 - 1/leverage + 0.005)` (giá thanh lý phải cao hơn bankruptcy price để không bị âm tiền)
  - SHORT: `entry * (1 + 1/leverage - 0.005)` (giá thanh lý phải thấp hơn bankruptcy price)
  - Test cả 2 case buffer và edge cases leverage=1.
- **Codex Review (ISSUE-5):** cơ chế bảo vệ số dư âm (isolated margin balance protection) trong `calc_close_balance` và `calc_liq_balance`.

## Architecture

Module thuần, được import bởi engine (Phase 3) và frontend-precompute (Phase 4 không dùng —
frontend tự tính hiển thị pre-check bằng cùng công thức, đã chốt trong design doc).
**Red Team & Codex Review:** giới hạn API surface — 8 hàm thuần túy, có docstring rõ ràng:
1. `calc_margin(qty, entry, leverage)`
2. `calc_liq_price(entry, leverage, side, mmr=0.005)`
3. `calc_pnl(entry, mark, qty, side)`
4. `calc_roi(pnl, margin)`
5. `calc_close_balance(balance, margin, pnl)`
6. `calc_liq_balance(balance)`
7. `calc_margin_available(balance, margin_used)`
8. `calc_qty_from_notional(notional_usdt, mark, precision=6)`

## Related Code Files

- Create: `app/trading/formulas.py`
- Create: `tests/unit/test_formulas.py`

## Implementation Steps (TDD)

1. RED: viết `tests/unit/test_formulas.py` trước, bao gồm:
   - `calc_margin(qty, entry, leverage)` — case thường, leverage=1, qty=0.
   - `calc_liq_price(entry, leverage, side, mmr=0.005)`:
     - LONG: entry=100, lev=10, mmr=0.005 → `100 * (1 - 0.1 + 0.005) = 90.5` (cao hơn điểm cháy 90.0).
     - SHORT: entry=100, lev=10, mmr=0.005 → `100 * (1 + 0.1 - 0.005) = 109.5` (thấp hơn điểm cháy 110.0).
     - LONG: entry=100, lev=1, mmr=0.005 → `100 * (1 - 1 + 0.005) = 0.5`.
     - SHORT: entry=100, lev=1, mmr=0.005 → `100 * (1 + 1 - 0.005) = 199.5`.
   - `calc_pnl(entry, mark, qty, side)` — long/short, mark < entry, mark = entry → 0.
   - `calc_roi(pnl, margin)` — margin=0 → trả 0 (guard chia 0).
   - `calc_close_balance(balance, margin, pnl)` — win/lose; bảo vệ balance không âm: `max(0.0, balance + margin + pnl)`.
   - `calc_liq_balance(balance)` → trả nguyên `balance` hiện tại (tiền margin coi như bị trừ đứt).
   - `calc_margin_available(balance, margin_used)` — clamp ≥ 0 (`max(0.0, balance - margin_used)`).
   - `calc_qty_from_notional(notional_usdt, mark, precision=6)` — làm tròn 6 chữ số thập phân (`round(notional / mark, precision)`).
2. GREEN: implement `app/trading/formulas.py` tối giản cho pass.
3. REFACTOR: đặt docstring công thức chuẩn Binance Isolated Margin, không thêm gì ngoài 8 hàm trên (YAGNI).

## Success Criteria

- [x] `pytest tests/unit/test_formulas.py` pass 100%.
- [x] Không import duckdb/fastapi trong formulas.py.
- [x] Công thức liq price long/short đúng hướng buffer MMR.

## Risk Assessment

Công thức Binance Isolated Margin có phí giao dịch (taker fee ~0.05%) — chấp nhận bỏ qua phí fee cho bản demo; ghi chú rõ ràng trong docstring.
