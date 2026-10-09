# CLAUDE.md — AdverTest

Dự án phát triển theo spec-driven development. Spec là nguồn sự thật; code là kết quả của spec; test nghiệm thu là bằng chứng.

## Nguồn sự thật

1. `specs/mission.md` — mục đích và **nguyên tắc không được vi phạm** (mục 4)
2. `specs/tech-stack.md` — công nghệ, quy ước dữ liệu, cấu trúc repo, luật cho agent
3. `specs/design.md` — **bắt buộc với mọi việc liên quan giao diện**: vùng phong cách, màu, chữ, lớp overlay, câu chữ
4. `specs/roadmap.md` — phase nào đang làm, phụ thuộc
5. Spec của phase được giao: `specs/YYYY-MM-DD-phase-NN-*/` (`requirements.md`, `plan.md`, `validation.md`)

### Đọc gì (đọc đúng mục cần, không đọc nguyên file)

Spec dài và tiếng Việt tốn token; đọc nguyên file ở mỗi phiên là nguồn tốn token lớn. In một mục bằng `bash .claude/scripts/md_section.sh <file> '<regex tiêu đề>' [--all]` (dòng đầu output là `file:dòng`).

| Nguồn | Phần cần đọc |
|---|---|
| `CLAUDE.md` | Không đọc lại (đã tự nạp) |
| `mission.md` | `'^## 4\.'` (nguyên tắc); mục khác khi việc liên quan trực tiếp |
| `tech-stack.md` | Theo agent: ml-* `'^## 2\.'`, attack `'^## 3\.'`, backend/worker `'^## 4\.'`, frontend `'^## 5\.'`; mọi agent `'^## 9\.'` |
| `design.md` | Cả file, chỉ khi việc có giao diện |
| `roadmap.md` | `'^## Tổng quan'` + `'^## Phase NN '` |
| `plan.md` | 8 dòng đầu + `'^## Group G '` |
| `requirements.md` | `'^## Scope'`, `'^## Out of Scope'`, `'^## Decisions'`, `'^### Chốt ở Group'` (`--all`), các mục `Behaviour` mà task nhắc tới |
| `validation.md` | Mục `###` thuộc group + `'^## Definition of Done'` khi đóng phase |
| `CHANGELOG.md` | Mục `'^### Phase NN — Tổng kết'` của phase trước; phase cũ hơn ở `changelog/archive/phase-NN.md` |
| `contracts/python/advertest_contracts/models.py` (120 KB) | Không Read cả file: `grep -n 'class Tên'` rồi `sed -n 'a,bp'` |

Chỉ mở rộng phạm vi đọc khi mục đã đọc tham chiếu sang mục khác hoặc khi đang tìm câu trả lời cho một chỗ mơ hồ.

## Phiên làm việc

- **Mỗi lần gọi skill (`phase-*`, `contract-proposal`) là một phiên riêng.** Gõ `/clear` trước khi chạy skill tiếp theo. Chạy cả phase trong một phiên làm context phình gần 1M token, và mỗi lượt đều phải đọc lại toàn bộ context đó.
- **Luồng một phase:** (`phase-kickoff` nếu spec còn chỗ chưa chốt) → `phase-implement` từng group → `phase-review` **một lần cho cả phase** → `phase-close` **một lần**. Group rủi ro (đổi contract, migration DB, hành vi/golden của worker, quyền endpoint) được review riêng ngay sau khi làm.
- Bàn giao giữa các phiên qua `.claude/handoff/phaseNN-gG-<skill>.md` (review cả phase: `phaseNN-review.md`; không commit), không dựa vào lịch sử chat.
- **Test theo tầng:** sau mỗi task `make check-fast P='<đường dẫn>'`; cuối group `make check` (+ `make test-db` nếu đụng DB/worker); review chạy lại `make check` trước merge.
- Không in log dài vào context: `make check > <scratchpad>/check.log 2>&1; echo exit=$?; tail -n 40 <scratchpad>/check.log`, fail thì `grep -nE 'FAILED|ERROR|Error|error:' <scratchpad>/check.log | head -40` (`<scratchpad>` là thư mục scratchpad của phiên, không có thì dùng `/tmp`). pytest chạy riêng: `-q --tb=short` trên đúng file hoặc test liên quan.
- `git diff`: xem `--stat` trước, rồi diff từng file cần đọc; bỏ file sinh tự động (`contracts/schemas`, `contracts/openapi.json`, `contracts/mocks`, `frontend/src/contracts`) và lockfile.
- Screenshot chỉ chụp viewport đang kiểm tra. Gom các lệnh đọc độc lập vào cùng một lượt.

## Quyền sở hữu thư mục

| Agent | Được sửa |
|---|---|
| `ml-core` và các agent con (`ml-data`, `ml-model`, `ml-metric`, `ml-search`, `ml-privacy`) | `ml_core/` (đúng thư mục con ghi trong `plan.md` của phase) |
| `attack` và các agent con (`attack-transform`, `attack-patch`) | `attacks/` |
| `backend` và các agent con | `backend/app/`, `backend/admin_cli/`, `backend/migrations/`, `backend/alembic.ini`, `docker/`; `pyproject.toml` và `uv.lock` chỉ khi thêm dependency đã được duyệt |
| `worker` | `backend/worker/` |
| `frontend` và các agent con | `frontend/` |
| `frontend-landing` | `frontend/src/features/landing/`, `frontend/src/design/`, `frontend/src/copy/` (thu hẹp thêm theo `plan.md` Phase 11a) |
| Người duyệt (con người) | `specs/`, `contracts/`, `tests/acceptance/`, `CLAUDE.md` |

`plan.md` của mỗi phase có thể thu hẹp thêm phạm vi; khi đó `plan.md` được ưu tiên.

File trong `scripts/` và file ở gốc repo (`Makefile`, `pyproject.toml`, `.env.example`) chỉ được sửa khi `plan.md` giao task đó hoặc người duyệt cho phép rõ ràng.

## Không bao giờ

- Sửa `specs/`, `contracts/`, `tests/acceptance/` (trừ khi người dùng giao đúng việc đó và nói rõ).
- Làm yếu test: `skip`, `xfail`, `.only`, nới sai số, xóa assertion, nuốt ngoại lệ.
- Thêm dependency không có trong `tech-stack.md`.
- Mở rộng phạm vi ngoài `requirements.md` của phase.
- Commit bí mật (mật khẩu, token, khóa).

## Dừng lại và hỏi khi

- Spec không nói rõ và lựa chọn ảnh hưởng tới thiết kế, dữ liệu hoặc hành vi người dùng thấy.
- Cần thay đổi contract → dùng skill `contract-proposal`.
- Test nghiệm thu fail vì lý do ngoài phạm vi được giao.
- Sửa cùng một lỗi 3 lần chưa được → viết báo cáo chẩn đoán thay vì thử tiếp.

## Cách hỏi người dùng

Khi cần người dùng quyết định, dùng công cụ **`AskUserQuestion`** thay vì hỏi bằng văn bản tự do.

- **Chỉ hỏi khi thật sự bị chặn** bởi một quyết định thuộc về người dùng: điều mà spec, code và các giá trị mặc định hợp lý trong `tech-stack.md` không trả lời được. Đừng hỏi những gì spec đã nói.
- **Giới hạn của công cụ:** mỗi lần gọi 1–4 câu hỏi; mỗi câu 2–4 lựa chọn; `header` tối đa 12 ký tự. Có nhiều hơn 4 câu thì hỏi câu quan trọng nhất trước, hỏi tiếp ở lượt sau.
- **Câu hỏi** nêu ngắn gọn nguồn gốc vấn đề (file và mục), để người dùng biết đang quyết định điều gì.
- **Lựa chọn** loại trừ lẫn nhau (trừ khi dùng `multiSelect`); mô tả của mỗi lựa chọn nói rõ hệ quả. Nếu bạn có khuyến nghị, đặt nó **đầu tiên** và thêm " (Khuyến nghị)" vào cuối nhãn. Không cần tạo lựa chọn "Khác": người dùng luôn gõ được câu trả lời tự do.
- **Nội dung dài** (kế hoạch, báo cáo, diff) trình bày bằng văn bản trước, rồi mới gọi `AskUserQuestion` để hỏi quyết định.
- **Sau khi có câu trả lời:** nếu đó là quyết định thiết kế, đề xuất ghi vào spec (dạng diff). Quyết định không được chỉ nằm trong lịch sử chat.
- **Phương án dự phòng:** nếu công cụ không khả dụng (ví dụ đang chạy trong subagent) hoặc trả về câu trả lời rỗng, **không được tự giả định câu trả lời**. Hỏi lại bằng văn bản: đánh số câu hỏi, liệt kê lựa chọn A/B/C, rồi dừng chờ.

## Lệnh

| Lệnh | Dùng khi |
|---|---|
| `make check-fast P='<đường dẫn>'` | Vòng lặp nhanh sau mỗi task: ruff, mypy, pytest không cần DB trên `P`; `frontend/` thì lint, typecheck, test |
| `make check` | Bắt buộc trước khi báo xong (lint, type check, kiểm tra contract, unit test, test nghiệm thu); ghi output ra file log rồi `tail` (xem "Phiên làm việc") |
| `make test-db` | Test cần Postgres thật (marker `db`); tự dựng container Postgres tạm |
| `make test-acceptance` | Chạy riêng test nghiệm thu |
| `make contracts` | Sinh lại JSON Schema, OpenAPI, TypeScript type từ contract |
| `make contracts-check` | Sinh lại và báo lỗi nếu file sinh ra lệch với bản đã commit |
| `pnpm --dir frontend verify:build` | Build production và kiểm tra không chứa trang dev hay mock |
| `make up` / `make down` | Khởi động / dừng môi trường Docker; biến lấy từ `ENV_FILE` (mặc định `.env`, mẫu ở `.env.example`) |
| `make fixtures` | Tải fixture test, kiểm tra sha256 |

## Git

- Mỗi agent làm trên nhánh `phaseNN-<agent>` (thường trong một git worktree riêng).
- Commit sau mỗi task hoàn chỉnh: `phaseNN(<agent>): <mô tả ngắn>`.
- Không tự merge vào `main`.

## Skill của dự án (`.claude/skills/`)

| Skill | Dùng khi |
|---|---|
| `phase-kickoff` | Bắt đầu một phase khi spec còn chỗ chưa chốt: đọc spec, tìm chỗ mơ hồ, kiểm tra độ phủ |
| `phase-implement` | Làm một group với vai trò một agent |
| `phase-review` | Review nhánh so với spec trước khi merge, một lần cho cả phase hoặc riêng group rủi ro (chạy trong subagent riêng, chỉ báo cáo quay về) |
| `phase-close` | Đóng cả phase một lần: changelog, đánh dấu tiến độ, replan |
| `contract-proposal` | Cần đổi contract |

## Quy ước dữ liệu hay bị quên

Ảnh `float32`, `channels_first`, giá trị `[0, 1]`, letterbox 640×640; box `xyxy` pixel trong không gian letterbox; thời gian UTC; ID là UUID (uuid5 từ hash nội dung khi có thể, qua `advertest_contracts.ids.content_id`); hash là sha256 trên `canonical_json` (RFC 8785); tiền là `Decimal`, trong JSON là chuỗi. Migration mới phải tự `GRANT` quyền cho `advertest_app` trên bảng nó tạo.
