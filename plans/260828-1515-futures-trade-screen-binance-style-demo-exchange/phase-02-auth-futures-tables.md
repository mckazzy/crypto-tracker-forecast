---
phase: 2
title: "Auth + futures tables"
status: complete
priority: P1
effort: ""
dependencies: [1]
---

# Phase 2: Auth + futures tables

## Overview

Auth username/password (bcrypt + JWT), dependency `get_current_user`, 4 bảng mới
(users, futures_accounts, futures_orders, futures_positions) + store methods,
REST endpoints auth/account/orders/positions/trades/mark. Engine Phase 3 sẽ tiếp quản behavior
của POST orders (Phase 2 tập trung đóng contract schema, store persistence, auth guard và transaction safety).
**Red Team & Codex Review:** phase này đã đóng toàn bộ ownership + price-integrity contract —
KHÔNG ship placeholder fill theo body mark.

## Requirements

- Functional: register/login trả JWT; mỗi user mới tự có ví 10,000 USDT; reset nạp lại.
- Non-functional: password bcrypt (không plaintext); JWT secret từ settings; bearer token.
- **Red Team & Codex Review (bắt buộc):**
  - `jwt_secret` KHÔNG default — Settings validator fail-fast nếu unset hoặc < 32 chars
    (fail-closed, không fail-open như `ai_api_key: str = ""` precedent).
  - Pin `jwt.decode(..., algorithms=["HS256"])`, bắt buộc `exp`; test negative:
    "token ký bằng secret khác → 401".
  - Mọi futures route dùng `get_current_user`; user_id từ JWT `sub`, KHÔNG từ body.
  - Mọi store query/update futures có `WHERE id = ? AND user_id = ?` predicate.
  - Register: min password 8, cap length 64 (bcrypt truncate 72 bytes); login trả 401
    generic "invalid credentials" (không lộ username tồn tại).
  - Password: dùng `bcrypt` TRỰC TIẾP (`hashpw`/`checkpw`), pin version trong
    requirements.txt — KHÔNG dùng passlib (unmaintained, break với bcrypt>=4.1).
  - Mọi cột timestamp `TIMESTAMPTZ` + ghi datetime tz-aware UTC + đọc qua `_ensure_utc()`.
  - Mọi store method mới dùng `?` placeholder — f-string chỉ cho placeholder syntax,
    giá trị luôn trong params list (SQL injection guard).
  - **Codex Review (ISSUE-3 - Concurrency):** DuckDB là single-writer; `DuckDBStore` tích hợp
    `asyncio.Lock` cấp Store bao bọc toàn bộ `store.transaction()` và các thao tác ghi dữ liệu,
    tránh triệt để `duckdb.TransactionException` hoặc `Catalog Error / Write-Write Conflict`.
  - **Codex Review (ISSUE-4 - Order Lifecycle):** Ở Phase 2, `POST /api/futures/orders` lưu order
    ở trạng thái `OPEN`. Router hỗ trợ hook mock mark cho test integration; Phase 3 engine sẽ
    chính thức consume và execute market fill.
  - Test store: username chứa SQL metacharacters round-trip literal.

## Architecture

- `app/auth/` — `security.py` (bcrypt hash/verify, jwt encode/decode), `deps.py`
  (`get_current_user` FastAPI dependency).
- Bảng mới trong `DuckDBStore` (ensure-schema pattern như bảng hiện có); methods:
  `create_user`, `get_user_by_username`, `create_account`, `get_account`, `reset_account`,
  CRUD futures_orders/positions — tất cả user-scoped.
- **Concurrency contract (Red Team & Codex Review):**
  - Thêm `store.transaction()` context manager (BEGIN/COMMIT/ROLLBACK trên 1 connection duy nhất)
    được đồng bộ hóa bằng `asyncio.Lock`.
  - Reset/close là 1 transaction; balance update dùng 1 statement `UPDATE futures_accounts SET balance = balance + ?`
    (không read-then-write trong Python).
- Router `app/api/futures_routes.py` include vào `app/main.py`.
- **Red Team:** thêm `app.state.futures_disabled` gate (mirror `ws_worker_disabled`),
  lifespan resolve `get_store()` tại startup (không import-time), share 1 instance
  engine/routes/relay. Conftest set flag để test không mở real DB / Binance socket.
- **Red Team:** `reset_account` = close ALL positions (tại mark hiện tại) + cancel ALL
  orders + set balance 10,000 — TRONG 1 TRANSACTION, không để margin locked rơi vãi.
- Thêm `GET /api/futures/mark/{symbol}` trả engine last mark (WS fallback).

## Related Code Files

- Create: `app/auth/__init__.py`, `app/auth/security.py`, `app/auth/deps.py`
- Create: `app/api/futures_routes.py`
- Modify: `app/storage/duckdb_store.py` (thêm schema + methods + `transaction()` + `_write_lock`) — dùng `TIMESTAMPTZ`
- Modify: `app/main.py` (include router + futures_disabled gate + get_store startup)
- Modify: `app/config.py` (jwt_secret validator fail-fast, token expiry)
- Modify: `requirements.txt` (pyjwt==, bcrypt== — pin version, theo convention `==` hiện có)
- Modify: `tests/conftest.py` (`futures_disabled = True` trong client fixture)
- Create: `tests/unit/test_duckdb_store_futures.py`, `tests/integration/test_auth.py`, `tests/integration/test_futures_api.py`

## Implementation Steps (TDD)

1. RED unit: `test_duckdb_store_futures.py` — create_user (unique username), get_user_by_username,
   account default 10,000, reset_account (với OPEN position → đóng + balance đúng, margin_used=0),
   order CRUD user-scoped (query bằng user_id khác → empty), position insert/close với pnl + close_reason.
2. GREEN: thêm schema + methods vào DuckDBStore (mỗi cursor set TimeZone — pattern hiện có;
   timestamp TIMESTAMPTZ + tz-aware; `_write_lock` + transaction() context manager).
3. RED integration: `test_auth.py` — register → token, login sai password → 401 generic,
   duplicate username → 400 generic (không lộ), decode JWT roundtrip + algorithms/exp enforced,
   token secret khác → 401, min password 8.
4. GREEN: `app/auth/security.py` + `deps.py`.
5. RED integration: `test_futures_api.py` — auth-guard 401 khi không token;
   GET account trả balance 10,000; reset; POST orders persist market/limit dưới dạng OPEN
   (hoặc mock filled khi có test mark — KHÔNG nhận mark từ body);
   GET positions/trades user-scoped (user A token → 404 trên id của user B);
   close position cập nhật balance 1 transaction; close bỏ qua body exit_price.
6. GREEN: `futures_routes.py` + wire main.py; thêm deps pin pyjwt + bcrypt.
7. Chạy full pytest để chắc không vỡ pipeline cũ.

## Success Criteria

- [x] `pytest tests/unit/test_duckdb_store_futures.py tests/integration/test_auth.py tests/integration/test_futures_api.py` pass.
- [x] Full pytest pass (không regression SP1-SP4).
- [x] Không có bảng/index nào của SP4 bị sửa.
- [x] Test chứng minh: IDOR blocked, client-supplied price bị bỏ qua, JWT fail-closed,
      reset với OPEN position không double-credit, Store write-lock ngăn ngừa xung đột transaction.

## Risk Assessment

- DuckDB file bị 2 process mở — giữ nguyên topology single-process (1 connection chia sẻ);
  thêm `futures_disabled` gate cho test; document `--reload` có thể gây lỗi mở DB lần 2.
- JWT secret: validator fail-fast, không có default — fail-closed.
- `transaction()` trên DuckDB: test rõ rollback khi exception giữa chừng và write-lock an toàn.
