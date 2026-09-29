# Plan: Phase 4 — Xác thực và phân quyền

> Phân chia thư mục:
> `backend/app/auth/`, `backend/app/admin/`, `backend/app/audit/`, `backend/app/api/` (gắn dependency, lỗi), `backend/migrations/`, `docker/`, `.env.example` (`TRUSTED_PROXIES`, `APP_BASE_URL`, `COOKIE_SECURE`) (agent `backend`); `frontend/src/`, `frontend/package.json` (`react-hook-form`, `zod`, `@playwright/test`), `frontend/playwright.config.ts` (agent `frontend`).
>
> Thứ tự: Group 0 → (Group 1–3 của backend song song với Group 4–6 của frontend) → Group 7.
> Frontend làm với mock (`VITE_USE_MOCKS=true`) cho đến khi backend merge, sau đó chuyển sang API thật.

## Group 0 — Constitution và contract `[người duyệt]`

1. Cập nhật `tech-stack.md` mục 4 (phiên phía server) và mục 5 (`react-hook-form`, `zod`), ghi lý do.
1a. Sửa `tech-stack.md` mục 4.1 (`require_role` → `require_permission`) và mục Phase 4 của `roadmap.md` (bỏ "JWT cookie", `require_role`); mô tả cookie trong `backend/app/api/security.py` (đã sửa luôn ở Group 0).
2. Thêm `Permission`, `ROLE_PERMISSIONS`, `ErrorCode` vào contract; sinh sang TypeScript.
3. Thêm các schema trong `requirements.md` và mock tương ứng (gồm mock `Me` cho từng tổ hợp role, danh sách `UserAdminView` đủ các trạng thái, `AuditLogEntry`).
4. Cập nhật OpenAPI: endpoint `/auth/*`, `/admin/users/*`, `/audit-log`; khai báo permission của mọi endpoint hiện có (dùng extension `x-permission`).
4a. Bỏ placeholder `GET /users` khỏi OpenAPI. Sửa `tests/acceptance/phase_00/test_api.py`: bỏ nhóm `/users`, thêm `/admin`; kiểm tra `501` bằng phiên hợp lệ, chỉ cho các nhóm còn là khung (không gồm `/auth`, `/admin`, `/audit-log`).
4b. Dựng job CI `e2e` (Postgres, API có seed admin, frontend build, Playwright 3 viewport) với một kịch bản khói, để Group 4–6 chạy thật sớm.
5. `make contracts`; ghi `CHANGELOG.md`.

## Group 1 — Backend: phiên và xác thực `[agent: backend]`

6. Migration: `sessions`, `password_reset_tokens`, `auth_events`, cột mới của `users`.
7. Băm mật khẩu argon2id; kiểm tra chính sách mật khẩu.
8. Tạo, tra cứu, thu hồi phiên (lưu sha256 token); cookie theo đúng cờ trong `requirements.md`.
9. Middleware CSRF (double-submit) cho request thay đổi dữ liệu có cookie phiên.
10. Giới hạn đăng nhập sai theo email và IP dựa trên `auth_events`; IP lấy theo `TRUSTED_PROXIES` (uvicorn `--forwarded-allow-ips`, cấu hình trong compose).
11. Endpoint `/auth/request-access`, `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/password` (sai mật khẩu hiện tại → `422 invalid_request`), `/auth/password-reset`; email chuyển về chữ thường.
12. Định dạng lỗi thống nhất theo `ErrorCode`.

## Group 2 — Backend: phân quyền `[agent: backend]`

13. Dependency `current_user` (đọc user, trạng thái, role từ DB) và `require_permission(...)` dùng `ROLE_PERMISSIONS` từ contract.
14. Gắn `require_permission` cho **mọi** router hiện có theo `x-permission` trong OpenAPI; endpoint `501` phải xác thực trước khi trả `501`.
15. Kiểm tra lúc khởi động: mọi route không công khai (trừ `/internal/worker`) có khai báo permission, thiếu thì ứng dụng không khởi động.

## Group 3 — Backend: quản trị và audit `[agent: backend]`

16. Service quản lý người dùng: duyệt, từ chối, đổi role, vô hiệu hóa, kích hoạt, tạo link đặt lại; luật admin cuối cùng và không tự vô hiệu hóa.
17. Ghi `audit_log` với `before`/`after` cho mọi thao tác trong `requirements.md` (gồm `user.password_reset`; actor theo luật trong requirements).
18. Endpoint `/admin/users/*` và `/audit-log` (lọc, phân trang theo cursor; `actor` trả dạng object).

## Group 4 — Frontend: nền tảng `[agent: frontend]`

19. API client: gửi cookie, tự thêm `X-CSRF-Token`, xử lý `401` và `403` toàn cục, ánh xạ `ErrorCode` sang thông điệp tiếng Việt. Proxy `/api` của Vite đặt `xfwd: true` (từ review Group 1: giới hạn đăng nhập sai theo IP cần IP gốc).
20. Hook `useMe()` và hàm `can(permission)` dùng ma trận quyền sinh từ contract.
21. Route guard theo permission; trang `/forbidden`.
22. Cấu hình điều hướng tập trung (đường dẫn, nhãn, icon, permission, cờ trang đã có).
23. Khung giao diện responsive: sidebar (desktop), cột icon (tablet), thanh tab dưới đáy với mục "Thêm" (điện thoại); xử lý `safe-area-inset`.
24. Component form dùng chung với `react-hook-form` + `zod`; component hộp xác nhận (dialog trên desktop, bottom sheet trên điện thoại).

## Group 5 — Frontend: trang công khai và tài khoản `[agent: frontend]`

25. Trang giới thiệu tối giản.
26. Trang đăng nhập (chuyển hướng về trang trước), yêu cầu truy cập, màn hình xác nhận đã gửi.
27. Trang `/pending` hiển thị theo `account_pending` / `account_rejected` / `account_disabled`.
28. Trang đặt lại mật khẩu.
29. Trang tài khoản: thông tin, role, đổi mật khẩu, đăng xuất.
30. Trang `/home` với các khối theo role.
30a. (Từ review Group 4) `RequirePermission`/`AppShell` hiển thị trạng thái lỗi kèm nút thử lại khi `/auth/me` lỗi khác `401` (hiện là màn hình trắng).

## Group 6 — Frontend: trang admin `[agent: frontend]`

31. Trang người dùng: tab chờ duyệt / tất cả; bảng trên desktop, thẻ trên điện thoại; hành động duyệt, từ chối, đổi role, vô hiệu hóa, kích hoạt, tạo link đặt lại (hiện link + nút copy).
32. Trang audit log: bộ lọc, danh sách phân trang; bảng trên desktop, thẻ trên điện thoại; hash và ID dài rút gọn ở giữa kèm nút copy.
33. Cấu hình Playwright với 3 viewport (390×844, 820×1180, 1440×900).

## Group 7 — Test nghiệm thu và kiểm tra cuối `[người duyệt]`

34. Siết `tests/acceptance/phase_00/test_api.py` (Group 0 tạm chấp nhận `401` hoặc `501` khi không có phiên): thành test `db` đăng nhập thật rồi đòi `501` cho endpoint còn là khung. Viết test nghiệm thu `tests/acceptance/phase_04/` (backend) và kịch bản Playwright `frontend/e2e/phase_04/` theo `validation.md`.
35. Chạy manual check trên điện thoại thật.
36. Cập nhật `roadmap.md`, `CHANGELOG.md`; merge.
