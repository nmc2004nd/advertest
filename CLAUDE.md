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
