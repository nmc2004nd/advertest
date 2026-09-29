# Validation: Phase 4 — Xác thực và phân quyền

> Test trong `tests/acceptance/phase_04/` và `frontend/e2e/phase_04/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng.

## Automated Tests

### Chung
- [x] `make check` pass, bao gồm test nghiệm thu các phase trước.
- [x] `make contracts` không tạo thay đổi; mock của mọi schema mới validate được.
- [x] `ROLE_PERMISSIONS` trong contract trùng khớp **từng ô** với bảng trong `requirements.md` (test so sánh với bảng được mã hóa trong test).

### Bảo vệ endpoint — `test_route_protection.py`
- [x] Duyệt toàn bộ route trong OpenAPI: mọi route không nằm trong danh sách công khai và không thuộc `/internal/worker` trả `401` khi không có phiên (kể cả route đang trả `501`).
- [x] Mọi route không công khai có khai báo `x-permission` (một `Permission` hoặc `authenticated`).
- [x] Ứng dụng từ chối khởi động nếu có route không công khai thiếu khai báo permission (test bằng một route giả).
- [x] Với từng role đơn lẻ: gọi một route đại diện cho mỗi permission; được phép ↔ ✓ trong ma trận, không được phép → `403 forbidden`.
- [x] Người dùng nhiều role có hợp các permission; `GET /auth/me` trả `permissions` bằng đúng hợp các ô trong ma trận.

### Yêu cầu truy cập và đăng nhập — `test_auth.py`
- [x] Yêu cầu truy cập tạo user `pending`; mật khẩu lưu dạng argon2id, không có bản gốc trong DB.
- [x] Yêu cầu truy cập với email đã tồn tại → `202`, cùng nội dung phản hồi, không tạo user mới.
- [x] Mật khẩu ngắn hơn 10 ký tự hoặc trùng email → `422 validation_error`.
- [x] Chính sách mật khẩu áp dụng cho `/auth/password` và `/auth/password-reset` (`422 validation_error`).
- [x] Email chữ hoa/thường: yêu cầu truy cập `A@x.com` rồi `a@x.com` → không tạo user thứ hai; đăng nhập bằng email khác hoa thường thành công.
- [x] Đăng nhập user `pending` / `rejected` / `disabled` với đúng mật khẩu → `403` với đúng mã lỗi, **không** có cookie phiên.
- [x] Sai mật khẩu và email không tồn tại → cùng `401 invalid_credentials`, cùng thông điệp.
- [x] Sai 5 lần trong 15 phút → lần thứ 6 trả `429 rate_limited` kể cả khi mật khẩu đúng.
- [x] `X-Forwarded-For` từ nguồn ngoài `TRUSTED_PROXIES` bị bỏ qua; từ proxy tin cậy thì giới hạn theo IP gốc (hai IP gốc khác nhau không khóa lẫn nhau).
- [x] Đăng nhập thành công: cookie phiên có `HttpOnly`, `SameSite=Lax`; có `Secure` khi `COOKIE_SECURE=true`; DB chỉ lưu sha256 của token; có cookie `csrf_token` không `HttpOnly`; đăng xuất xóa cả hai cookie.
- [x] Phiên quá 12 giờ → `401`.
- [x] Đăng xuất rồi dùng lại cookie cũ → `401`.

### CSRF — `test_csrf.py`
- [x] `POST` có cookie phiên nhưng thiếu `X-CSRF-Token` → `403 csrf_failed`.
- [x] `X-CSRF-Token` không khớp cookie → `403 csrf_failed`.
- [x] `GET` không yêu cầu CSRF token.
- [x] Endpoint `/internal/worker` với bearer token không yêu cầu CSRF token.

### Hiệu lực tức thời — `test_immediate_effect.py`
- [x] Admin bỏ role `engineer` của người dùng đang đăng nhập → request tiếp theo của người đó với permission `experiment.create` bị `403` (cùng phiên).
- [x] Admin vô hiệu hóa người dùng đang đăng nhập → request tiếp theo `401`; mọi phiên của người đó bị thu hồi.
- [x] Đổi mật khẩu → các phiên khác của người dùng bị thu hồi, phiên hiện tại vẫn dùng được.
- [x] Đổi mật khẩu với `current_password` sai → `422 invalid_request`; phiên hiện tại vẫn dùng được.

### Quản trị — `test_admin.py`
- [x] Duyệt không kèm role → `422`; đổi role thành danh sách rỗng → `422 validation_error`.
- [x] Duyệt → user `active` với đúng role; đăng nhập được.
- [x] Từ chối không kèm lý do → `422`; có lý do → `rejected`, lý do được lưu.
- [x] Admin tự vô hiệu hóa chính mình → `409 conflict`.
- [x] Bỏ role admin hoặc vô hiệu hóa admin `active` cuối cùng → `409 conflict`. (Qua HTTP: test tạm vô hiệu các admin khác của DB dùng chung rồi khôi phục; vô hiệu hóa admin cuối cùng chỉ xảy ra khi tự vô hiệu hóa.)
- [x] Link đặt lại: dùng được một lần; lần hai → lỗi; hết hạn sau 24 giờ; sau khi dùng mọi phiên cũ bị thu hồi.
- [x] Người không có `user.manage` gọi `/admin/users/*` → `403`.
- [x] Chuyển trạng thái không hợp lệ (approve user `active`, enable user `active`, disable user `disabled`) → `409 conflict`.
- [x] `GET /admin/users?status=pending` chỉ trả user `pending`; phân trang không trùng, không sót.
- [x] Link đặt lại bắt đầu bằng `APP_BASE_URL` + `/reset-password/`.
- [x] Đổi role hoặc tạo link đặt lại cho user `pending`/`rejected` → `409 conflict`.
- [x] Tạo link đặt lại mới → link cũ chưa dùng không dùng được nữa.

### Audit — `test_audit_phase04.py`
- [x] Mỗi thao tác `user.approved`, `user.rejected`, `user.roles_changed`, `user.disabled`, `user.enabled`, `user.reset_link_created`, `user.password_changed`, `user.password_reset`, `user.access_requested` tạo đúng một dòng `audit_log` với actor, entity, `before`, `after` đúng; actor của `access_requested`, `password_changed`, `password_reset` là chính người dùng đó.
- [x] `/audit-log` trả `actor` dạng `{id, full_name, email}`, hoặc `null` với hành động hệ thống.
- [x] Không dòng `audit_log` nào chứa mật khẩu, hash mật khẩu hoặc token.
- [x] Đăng nhập, đăng nhập sai, đăng xuất ghi vào `auth_events`, không ghi vào `audit_log`.
- [x] `/audit-log` lọc đúng theo actor, action, khoảng thời gian; phân trang không trùng, không sót.
- [x] Người không có `audit.read` gọi `/audit-log` → `403`.
- [x] `/audit-log` không lọc vẫn trả `200` khi DB có dòng audit lệch quy ước `entity.verb`.

### Frontend — unit (Vitest)
- [x] `can(permission)` trả đúng theo ma trận cho mọi tổ hợp role trong mock `Me`.
- [x] Cấu hình điều hướng: mục chưa có trang không hiển thị; mục thiếu quyền không hiển thị.
- [x] Mọi `ErrorCode` có thông điệp tiếng Việt.
- [x] Schema `zod` của form yêu cầu truy cập từ chối mật khẩu dưới 10 ký tự.

### Frontend — E2E (Playwright, cả 3 viewport)
- [x] Người dùng mới yêu cầu truy cập → đăng nhập thấy màn hình "đang chờ duyệt".
- [x] Admin đăng nhập, vào "Người dùng", duyệt với role `engineer` → người dùng đăng nhập lại vào được `/home`, điều hướng chỉ hiện mục được phép.
- [x] Admin từ chối một yêu cầu kèm lý do → người đó đăng nhập thấy màn hình "bị từ chối".
- [x] Engineer truy cập trực tiếp `/admin/users` → chuyển tới `/forbidden`.
- [x] Hết phiên (xóa cookie) → thao tác tiếp theo đưa về `/login`; đăng nhập xong quay lại đúng trang trước.
- [x] Ở viewport 390px: thanh tab dưới đáy hiển thị; không có trang nào cuộn ngang; hộp xác nhận hiện dạng bottom sheet.
- [x] Ở viewport 820px: điều hướng dạng cột icon.
- [x] Admin đăng nhập thấy khối "tài khoản chờ duyệt" trên `/home` với đúng số lượng.
- [x] Ở viewport 1440px: sidebar hiển thị; trang người dùng và audit log hiển thị dạng bảng.
- [x] Điều hướng toàn bộ form đăng nhập và yêu cầu truy cập bằng bàn phím được.

## Manual Checks

- [x] Toàn bộ luồng yêu cầu truy cập → duyệt → đăng nhập trên điện thoại Android và iPhone thật.
- [x] Trên iPhone: chạm vào ô nhập không làm trang tự zoom; thanh tab không bị thanh home che.
- [x] Mở hai trình duyệt: vô hiệu hóa người dùng ở trình duyệt admin, người dùng ở trình duyệt kia bị đăng xuất ở thao tác kế tiếp.
- [x] Tạo link đặt lại, copy trên điện thoại, dùng thành công.
- [x] Kiểm tra cookie trong DevTools: đúng cờ, không có dữ liệu nhạy cảm trong cookie hay localStorage.
- [x] Đọc lại nội dung giao diện: tiếng Việt thống nhất, không còn chữ giữ chỗ.
- Ghi chú (Group 7, 2026-09-29): hai mục đã đánh dấu được tự động hóa trong `frontend/e2e/phase_04/security.spec.ts` (3 viewport) và kiểm tra thêm bằng `curl` trên `make up` (cờ `HttpOnly`, `SameSite=Lax`, `Max-Age=43200`). Các mục còn lại (điện thoại Android và iPhone thật, đọc lại nội dung) người dùng tự làm và xác nhận đạt (2026-09-29).

## Definition of Done

- [x] Toàn bộ Automated Tests pass trên CI, bao gồm E2E trên 3 viewport.
- [x] Toàn bộ Manual Checks đã thực hiện.
- [x] Người duyệt đã chấp nhận thay đổi `tech-stack.md` và contract (đặc biệt là ma trận quyền).
- [x] Câu hỏi mở đã có câu trả lời.
- [x] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 4 được đánh dấu hoàn thành.
