# Plan: Phase 8 — Protocol, review và report

> Phân chia thư mục:
> `backend/app/protocols/`, `backend/app/reviews/` (agent `backend-review`); `backend/app/reports/` (agent `backend-report`);
> `frontend/src/features/protocols/`, `frontend/src/features/reviews/` (agent `frontend-review`); `frontend/src/features/reports/`, `frontend/src/features/verify/`, phần gửi duyệt trong `frontend/src/features/experiments/` (agent `frontend-report`).
>
> Thứ tự: Group 0 → Group 1 → (Group 2, 3 song song; frontend Group 4–6 bắt đầu với mock) → Group 7.

## Group 0 — Contract, constitution `[người duyệt]`

1. Định nghĩa lại `ProtocolBody`; thêm enum và schema trong `requirements.md`; thêm `compliance`, `review`, `report` vào `ExperimentDetail`.
2. Thêm permission `review.comment` vào ma trận; cập nhật bảng trong test nghiệm thu Phase 4 và trong `mission.md` mục 3 nếu cần.
3. Thêm matplotlib, Jinja2 vào `tech-stack.md` (nếu giữ lựa chọn mặc định).
4. Cập nhật OpenAPI với mọi endpoint mới kèm `x-permission`.
5. Viết mock: protocol có attack quét lưới và tìm ngưỡng; experiment ở mọi trạng thái review; `criteria_results` đủ ba trạng thái; `checklist` thiếu và đủ; `ReportSnapshot` đầy đủ; `VerifyInfo`.
6. `make contracts`; ghi `CHANGELOG.md`.

## Group 1 — Backend: dữ liệu và protocol `[agent: backend-review]`

7. Migration: thay đổi bảng trong `requirements.md`; cập nhật `dev-open`; quyền DB và trigger mới.
8. Service protocol: tạo, tạo version, ngừng dùng; kiểm tra hợp lệ.
9. Hàm tuân thủ protocol dùng chung cho ước lượng, tạo experiment và gửi duyệt; tích hợp vào kiểm tra của Phase 5.
10. Endpoint `/protocols*`.

## Group 2 — Backend: gửi duyệt và review `[agent: backend-review]`

11. Gửi duyệt: điều kiện, giải trình run, khóa experiment (chặn mọi endpoint thay đổi bằng một kiểm tra chung), email cho reviewer.
12. Nhận / trả lại review; hàng đợi loại experiment của chính người gọi.
13. Chọn case bắt buộc review theo attack.
14. Verdict có version.
15. Đánh giá tiêu chí tự động theo bảng trong `requirements.md` (dùng dữ liệu Phase 6–7).
16. Danh sách kiểm tra trước khi chấp nhận; endpoint quyết định; email cho engineer.
17. Bình luận chỉ thêm.
18. Ghi `audit_log` cho mọi action trong `requirements.md`.

## Group 3 — Backend: report `[agent: backend-report]`

19. Dựng `ReportSnapshot` từ DB và MinIO (gồm lịch sử experiment liên quan, mọi run, case đã review).
20. Mẫu HTML Jinja2 cho 9 mục; biểu đồ matplotlib thành PNG; chân trang.
21. Render PDF bằng WeasyPrint; tính hash; lưu vào bucket `reports`.
22. Tác vụ nền sinh report sau khi chấp nhận, thử lại 3 lần; endpoint sinh lại khi `failed`.
23. Endpoint `/reports*` với phân quyền tải; `/verify/{report_id}` công khai trả `VerifyInfo`.

## Group 4 — Frontend: engineer `[agent: frontend-report]`

24. Wizard bước 1: chọn protocol → điền sẵn và khóa attack bắt buộc, ngưỡng; lọc slice theo `min_slice_size`; bảng tuân thủ trực tiếp.
25. Nút và hộp "Gửi duyệt" (ghi chú, giải trình từng run, điều kiện).
26. Dải "Đã khóa"; tab Review (trạng thái, người nhận, bình luận, quyết định); nút "Nhân bản để sửa".

## Group 5 — Frontend: reviewer `[agent: frontend-review]`

27. Trang `/reviews` với ba nhóm và cách sắp xếp.
28. Trang `/reviews/:id`: nhận/trả lại, tuân thủ, tiêu chí, danh sách kiểm tra, run kèm giải trình, biểu đồ, case bắt buộc với tiến độ, bình luận, khung quyết định.
29. Trang `/reviews/:id/cases/:caseId`: mở rộng `CaseViewer` với form verdict, lịch sử verdict, phím tắt, bảng phím tắt, bottom sheet và vuốt trên điện thoại.
30. Trang `/protocols` với form xây dựng protocol.
31. Khối reviewer trên trang chủ; bật mục điều hướng.

## Group 6 — Frontend: report và xác minh `[agent: frontend-report]`

32. Trang `/reports`, `/reports/:id` (hiển thị snapshot), nút tải cho reviewer.
33. Trang công khai `/verify/:id` tính SHA-256 trong trình duyệt bằng Web Crypto.

## Group 7 — Test nghiệm thu và kiểm tra cuối `[người duyệt]`

34. Viết test nghiệm thu `tests/acceptance/phase_08/` và kịch bản Playwright `frontend/e2e/phase_08/` theo `validation.md`.
35. Chạy trọn luồng trên KITTI; đọc kỹ toàn bộ PDF.
36. Thử các cách gian lận ở mục Manual Checks.
37. Trả lời câu hỏi mở; cập nhật `CHANGELOG.md`, `roadmap.md`; merge.
