# Plan: Phase 5 — Wizard tạo experiment và theo dõi tiến độ

> Phân chia thư mục:
> `backend/app/services/` (mở rộng `experiments.py`, `estimate.py`; thêm `catalog.py`, `notifications.py`, `artifacts.py`), route trong `backend/app/api/`, `backend/migrations/` (agent `backend`);
> `frontend/src/features/experiments/`, `frontend/src/features/wizard/`, `frontend/src/components/case-viewer/`, `frontend/src/components/charts/` (agent `frontend`, có thể chia cho hai agent: một làm wizard, một làm chi tiết và trình xem).
>
> Thứ tự: Group 0 → (Group 1–3 backend song song với Group 4–6 frontend dùng mock) → Group 7.

## Group 0 — Contract `[người duyệt]`

1. Thêm các schema trong `requirements.md` và mã lỗi mới.
1a. (Từ Phase 4) Khi thêm `error.fields`: OpenAPI khai `422` là `ErrorResponse` (hiện vẫn là `HTTPValidationError`); cân nhắc thêm `ErrorCode` cho lỗi `500` (hiện chưa trả `ErrorResponse`).
1b. (Kickoff) `EstimateResponse.runs[].skip_reason`, `ExperimentClone`, `ErrorBody.fields`, `GET /artifacts/{token}`.
2. Cập nhật OpenAPI với các endpoint đọc tài nguyên và endpoint experiment, kèm `x-permission`.
2a. (Từ Phase 4) OpenAPI sinh từ app: endpoint khung thêm vào `backend/app/api/public.py` bằng `**guard(p)`. Cập nhật con số `len(REPRESENTATIVES)` trong `backend/app/tests/db/test_route_protection_db.py` khi có permission mới có route.
3. Viết mock: experiment ở mọi trạng thái; experiment `completed` có run đủ các trạng thái (kể cả `metrics.partial`); `EstimateResponse` đủ, thiếu profile, vượt giới hạn; `FailureCaseView` với cả 3 `display_mode`.
3a. (Kickoff) `scripts/e2e.sh`: khởi động worker CPU (target `local-dev`) và đặt `DEV_ALLOW_UNBLURRED=true`.
4. `make contracts`; ghi `CHANGELOG.md`.

## Group 1 — Backend: đọc tài nguyên `[agent: backend]`

5. Migration: `compute_targets.max_time_limit_s` (mặc định 28800); `experiments.name` (NOT NULL, điền tên cho experiment cũ), `cloned_from`, `finished_at`; bảng `email_outbox`.
6. Endpoint đọc model, dataset, dataset version, slice, class mapping, attack spec, protocol, compute target (tính `online` và `queue_length`).

## Group 2 — Backend: experiment `[agent: backend]`

7. Hàm kiểm tra cấu hình dùng chung cho ước lượng và tạo, trả lỗi có đường dẫn trường.
8. Mở rộng hàm ước lượng Phase 3: theo run, `missing_profiles`, `exceeds_limit`, vị trí và thời gian chờ trong hàng đợi.
9. `POST /experiments/estimate`, `POST /experiments` (giới hạn 3 experiment đang chờ; ghi `audit_log`).
10. `GET /experiments` (lọc, phân trang), `GET /experiments/{id}`, `GET /experiments/{id}/runs`, `GET /runs/{id}/manifest`.
11. `POST /experiments/{id}/cancel` (chỉ chủ sở hữu; tái sử dụng logic hủy Phase 3), `GET /experiments/{id}/clone` (trả `ExperimentClone`).
12. `GET /runs/{id}/failure-cases`, `GET /failure-cases/{id}`: cấp URL tạm thời 10 phút qua `/api/artifacts/{token}` (token HMAC gắn một khóa, API stream từ MinIO); áp dụng `display_mode` theo cờ `anonymized` của dataset và `DEV_ALLOW_UNBLURRED`.
13. Đặt `finished_at` khi experiment vào trạng thái cuối.

## Group 3 — Backend: email `[agent: backend]`

14. Thêm email vào outbox khi experiment `completed` hoặc `cancelled` (trong cùng transaction với việc đổi trạng thái).
15. Tác vụ nền gửi email qua SMTP, thử lại tối đa 5 lần với backoff, ghi `last_error`.
16. Mẫu email tiếng Việt (HTML và văn bản thuần).
17. Thêm Mailpit vào `docker/compose.yaml`; cập nhật `.env.example`.

## Group 4 — Frontend: component dùng chung `[agent: frontend]`

18. Hook dữ liệu với TanStack Query: polling 2 giây khi `queued`/`running`, dừng ở trạng thái cuối, tạm dừng khi tab ẩn.
19. Component tóm tắt trạng thái experiment thành câu từ `run_counts`.
20. Biểu đồ đường cong metric (Recharts): đường ngang mAP sạch, đánh dấu run `partial`, bảng số liệu đi kèm; chế độ từng biểu đồ trên điện thoại.
21. `CaseViewer`: cạnh nhau (desktop) / slider (điện thoại), zoom đồng bộ, pinch-zoom, vuốt chuyển case, lớp box bật tắt, canvas theo `devicePixelRatio`, ảnh nhiễu, watermark, khung giữ chỗ cho `hidden_unanonymized`, dải cảnh báo cho `dev_unblurred`.
22. Tự xin lại URL khi URL ảnh sắp hết hạn.

## Group 5 — Frontend: wizard `[agent: frontend]`

23. Khung wizard 6 bước: thanh bước, điều hướng tới/lui, lưu sessionStorage, bố cục điện thoại (một bước một màn hình, thanh dưới cố định) và desktop (cột tóm tắt).
24. Các bước 1–5 theo `requirements.md`; chip chỉnh level có kiểm tra dải; preset level; seed cố định 0; tự chọn class mapping khi chỉ có một, báo lỗi khi không có.
25. Gọi ước lượng có debounce; hiển thị cảnh báo.
26. Bước 6: tóm tắt, hộp xác nhận, gửi, chuyển tới trang chi tiết; hiển thị lỗi `422` tại đúng bước và trường; xử lý `409 queue_limit_reached`.
27. Mở wizard từ "Nhân bản" với dữ liệu điền sẵn và cảnh báo spec đã cập nhật.

## Group 6 — Frontend: danh sách, chi tiết, trang chủ `[agent: frontend]`

28. Trang `/experiments` với bộ lọc; bảng / thẻ theo viewport.
29. Trang `/experiments/:id` với 5 tab; nút Hủy (hộp xác nhận) và Nhân bản.
30. Trang `/failure-cases/:id` dùng `CaseViewer`.
31. Khối engineer trên `/home`.
32. Bật các mục điều hướng "Experiment" và "Tạo experiment" (cờ trang đã có).

## Group 7 — Test nghiệm thu và kiểm tra cuối `[người duyệt]`

33. Viết test nghiệm thu `tests/acceptance/phase_05/` và kịch bản Playwright `frontend/e2e/phase_05/` theo `validation.md` (worker CPU với fixture chạy trong CI).
34. Chạy manual check trên laptop và điện thoại thật.
35. Trả lời câu hỏi mở; cập nhật `roadmap.md` nếu quyết định đưa làm mờ lên sớm.
36. Cập nhật `CHANGELOG.md`, `roadmap.md`; merge.
37. (Từ Phase 4) Kịch bản E2E `frontend/e2e/phase_04/onboarding.spec.ts` đang đòi engineer thấy đúng 2 mục điều hướng; khi bật `/experiments` cập nhật thành số mục mới (người duyệt). Test Vitest điều hướng trong `frontend/src/pages/app-pages.test.tsx` cũng cần đổi (agent frontend, Group 6).
