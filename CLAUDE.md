# CLAUDE.md — AdverTest

Dự án phát triển theo spec-driven development. Spec là nguồn sự thật; code là kết quả của spec; test nghiệm thu là bằng chứng.

## Đọc trước khi làm bất cứ việc gì

1. `specs/mission.md` — mục đích và **nguyên tắc không được vi phạm** (mục 4)
2. `specs/tech-stack.md` — công nghệ, quy ước dữ liệu, cấu trúc repo, luật cho agent
3. `specs/roadmap.md` — phase nào đang làm, phụ thuộc
4. Spec của phase được giao: `specs/YYYY-MM-DD-phase-NN-*/` (`requirements.md`, `plan.md`, `validation.md`)

## Quyền sở hữu thư mục

| Agent | Được sửa |
|---|---|
| `ml-core` và các agent con (`ml-data`, `ml-model`, `ml-metric`, `ml-search`, `ml-privacy`) | `ml_core/` (đúng thư mục con ghi trong `plan.md` của phase) |
| `attack` và các agent con (`attack-transform`, `attack-patch`) | `attacks/` |
| `backend` và các agent con | `backend/app/`, `backend/admin_cli/`, `docker/` |
| `worker` | `backend/worker/` |
| `frontend` và các agent con | `frontend/` |
| Người duyệt (con người) | `specs/`, `contracts/`, `tests/acceptance/`, `CLAUDE.md` |

`plan.md` của mỗi phase có thể thu hẹp thêm phạm vi; khi đó `plan.md` được ưu tiên.

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

## Lệnh

| Lệnh | Dùng khi |
|---|---|
| `make check` | Bắt buộc trước khi báo xong (lint, type check, unit test, test nghiệm thu) |
| `make test-acceptance` | Chạy riêng test nghiệm thu |
| `make contracts` | Sinh lại JSON Schema, OpenAPI, TypeScript type từ contract |
| `make up` / `make down` | Khởi động / dừng môi trường Docker |
| `make fixtures` | Tải fixture test |

## Git

- Mỗi agent làm trên nhánh `phaseNN-<agent>` (thường trong một git worktree riêng).
- Commit sau mỗi task hoàn chỉnh: `phaseNN(<agent>): <mô tả ngắn>`.
- Không tự merge vào `main`.

## Skill của dự án (`.claude/skills/`)

| Skill | Dùng khi |
|---|---|
| `phase-kickoff` | Bắt đầu một phase: đọc spec, tìm chỗ mơ hồ, kiểm tra độ phủ |
| `phase-implement` | Làm một group với vai trò một agent |
| `phase-review` | Review một nhánh so với spec trước khi merge |
| `phase-close` | Cập nhật changelog, đánh dấu tiến độ, replan |
| `contract-proposal` | Cần đổi contract |

## Quy ước dữ liệu hay bị quên

Ảnh `float32`, `channels_first`, giá trị `[0, 1]`, letterbox 640×640; box `xyxy` pixel trong không gian letterbox; thời gian UTC; ID là UUID (uuid5 từ hash nội dung khi có thể); hash là sha256 trên `canonical_json`.
