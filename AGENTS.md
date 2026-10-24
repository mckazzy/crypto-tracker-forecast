# AGENTS.md — luật phối hợp nhiều coding agent (repo này)

Repo chạy nhiều agent song song. Mỗi agent làm trong **worktree riêng** do Orca tạo
(`C:\Users\Admin\orca\workspaces\crypto-tracker-forecast\<tên>`, branch `chauleminh3011/<tên>`).

## Phân vai (chốt 2026-10-24)

| Agent (Orca id) | Vai | Được sửa | Không được |
|---|---|---|---|
| `command-code` | **Implement code** (feature, fix, script) | `app/`, `web/src/`, `scripts/` | sửa `tests/` của người khác, merge/push |
| `codex` | **Kiến trúc + test**: quyết định thiết kế, viết/bổ sung test, review cấu trúc | `tests/`, `docs/` | implement feature lớn (tốn token) |
| `antigravity` (`agy`) | **Review độc lập**: logic, bảo mật, đối chiếu AC | chỉ ghi `docs/qa/` | sửa `app/`, `web/src/` |
| `claude` | **Refactor** đa file, tách module, doc kỹ thuật — *tạm dừng vì chưa có account* | `app/`, `web/src/`, `docs/` | thêm feature mới |

Lý do đổi (2026-10-24): Codex tốn token khi code nhiều → chỉ giữ kiến trúc + test;
việc implement chuyển sang `command-code`.

## Luật chung

1. Chỉ làm trong worktree của mình. Không sửa file trong worktree agent khác.
2. Không `git push`, không `git merge`, không sửa `.env`, không cài package mới khi chưa được yêu cầu.
3. Server bind `127.0.0.1`; test bằng `.venv\Scripts\python.exe -m pytest` (baseline: 339 passed).
4. Trước khi báo xong: chạy `git status --short` + test liên quan, ghi rõ đã chạy gì.
5. Báo cáo đúng 3 dòng: `DONE|BLOCKED` · tóm tắt 1 câu · danh sách file đổi (+ test đã chạy).
6. Không tự mở rộng scope. Task mơ hồ → `BLOCKED` kèm câu hỏi, không đoán.

## Chuỗi phối hợp 1 feature

```
codex (kiến trúc + test plan, ngắn)
   ↓
command-code (implement theo plan, chạy pytest)
   ↓
agy (review diff + đối chiếu AC, ghi docs/qa/)
   ↓
Hermes/orchestrator: đọc 3 báo cáo → quyết merge
```

Feature đã có spec chi tiết sẵn (vd `docs/roadmap.md` mục N1) thì **bỏ bước codex**,
đưa thẳng cho `command-code`.
