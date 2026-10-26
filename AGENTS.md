# AGENTS.md — luật phối hợp nhiều coding agent (repo này)

Repo chạy nhiều agent song song. Mỗi agent làm trong **worktree riêng** do Orca tạo
(`C:\Users\Admin\orca\workspaces\crypto-tracker-forecast\<tên>`, branch `chauleminh3011/<tên>`).

## Phân vai (chốt 2026-10-24)

| Agent (Orca id) | Vai | Được sửa | Không được |
|---|---|---|---|
| `command-code` | **Implement code** (feature, fix, script) | `app/`, `web/src/`, `scripts/` | sửa `tests/` của người khác, merge/push |
| `codex` | **Kiến trúc + test**: quyết định thiết kế, viết/bổ sung test, review cấu trúc | `tests/`, `docs/` | implement feature lớn (tốn token) |
| `antigravity` (`agy`) | **Review độc lập**: logic, bảo mật, đối chiếu AC — hoặc **implement vừa + viết test** khi được coordinator giao Task | `docs/qa/`; khi nhận Task implement: `app/`, `web/src/`, test mới trong worktree riêng của mình | sửa file của agent khác; vừa viết code vừa tự review diff của chính mình |
| `claude` | **Refactor** đa file, tách module, doc kỹ thuật — *tạm dừng vì chưa có account* | `app/`, `web/src/`, `docs/` | thêm feature mới |

Lý do đổi (2026-10-24): Codex tốn token khi code nhiều → chỉ giữ kiến trúc + test;
việc implement chuyển sang `command-code`.

## Hạn mức (quota) — kiểm tra trước khi dispatch

Chạy `orca account list` xem `rateLimits` trước khi giao việc. Số đo 2026-10-25 trên máy này:
`codex` đã dùng **99%** cửa sổ 5h (reset trong ngày), `antigravity` mới **2%**.

- `codex`: chỉ nhận task **design ngắn (≤1 lượt)**. Cửa sổ 5h dễ cạn giữa DAG — cạn thì chuyển
  bước design cho `antigravity`, **không chờ reset**.
- `antigravity`: quota dồi dào nhất → nhận thêm **implement vừa + viết test** khi `command-code`
  đang bận, hoặc khi cần tiết kiệm token trả phí.
- `command-code`: trả theo token (~$0,05 cho feature nhỏ), không giới hạn cứng → workhorse cho
  phần code lớn.
- Không xếp `codex` thành mắt xích bắt buộc: pipeline phải chạy được cả khi codex cạn quota.

## Luật chung

1. Chỉ làm trong worktree của mình. Không sửa file trong worktree agent khác.
2. Không `git push`, không `git merge`, không sửa `.env`, không cài package mới khi chưa được yêu cầu.
3. Server bind `127.0.0.1`; test bằng `.venv\Scripts\python.exe -m pytest` (baseline: 339 passed).
4. Trước khi báo xong: chạy `git status --short` + test liên quan, ghi rõ đã chạy gì.
5. Báo cáo đúng 3 dòng: `DONE|BLOCKED` · tóm tắt 1 câu · danh sách file đổi (+ test đã chạy).
6. Không tự mở rộng scope. Task mơ hồ → `BLOCKED` kèm câu hỏi, không đoán.

## Chuỗi phối hợp 1 feature

```
(design) codex — task ngắn; codex cạn quota thì dùng agy
   ↓
command-code (implement theo plan, chạy pytest)   ← việc vừa thì có thể giao agy
   ↓
review: agent KHÔNG viết đoạn code đó (agy hoặc codex) → ghi docs/qa/
   ↓
Hermes/orchestrator: đọc báo cáo → quyết merge
```

Feature đã có spec chi tiết sẵn (vd `docs/roadmap.md` mục N1) thì **bỏ bước design**,
đưa thẳng cho `command-code`. Việc nhỏ (1–2 file) thì bỏ luôn cả design lẫn Run/Task,
mở thẳng một agent trong worktree rồi coordinator review diff.
