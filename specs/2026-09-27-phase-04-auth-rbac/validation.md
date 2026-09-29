# Validation: Phase 4 — Xác thực và phân quyền

> Test trong `tests/acceptance/phase_04/` và `frontend/e2e/phase_04/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng.

## Automated Tests

### Chung
- [ ] `make check` pass, bao gồm test nghiệm thu các phase trước.
- [ ] `make contracts` không tạo thay đổi; mock của mọi schema mới validate được.
- [ ] `ROLE_PERMISSIONS` trong contract trùng khớp **từng ô** với bảng trong `requirements.md` (test so sánh với bảng được mã hóa trong test).

### Bảo vệ endpoint — `test_route_protection.py`
- [ ] Duyệt toàn bộ route trong OpenAPI: mọi route không nằm trong danh sách công khai và không thuộc `/internal/worker` trả `401` khi không có phiên (kể cả route đang trả `501`).
- [ ] Mọi route không công khai có khai báo `x-permission` (một `Permission` hoặc `authenticated`).
- [ ] Ứng dụng từ chối khởi động nếu có route không công khai thiếu khai báo permission (test bằng một route giả).
- [ ] Với từng role đơn lẻ: gọi một route đại diện cho mỗi permission; được phép ↔ ✓ trong ma trận, không được phép → `403 forbidden`.
- [ ] Người dùng nhiều role có hợp các permission; `GET /auth/me` trả `permissions` bằng đúng hợp các ô trong ma trận.

### Yêu cầu truy cập và đăng nhập — `test_auth.py`
- [ ] Yêu cầu truy cập tạo user `pending`; mật khẩu lưu dạng argon2id, không có bản gốc trong DB.
- [ ] Yêu cầu truy cập với email đã tồn tại → `202`, cùng nội dung phản hồi, không tạo user mới.
- [ ] Mật khẩu ngắn hơn 10 ký tự hoặc trùng email → `422 validation_error`.
- [ ] Chính sách mật khẩu áp dụng cho `/auth/password` và `/auth/password-reset` (`422 validation_error`).
- [ ] Email chữ hoa/thường: yêu cầu truy cập `A@x.com` rồi `a@x.com` → không tạo user thứ hai; đăng nhập bằng email khác hoa thường thành công.
- [ ] Đăng nhập user `pending` / `rejected` / `disabled` với đúng mật khẩu → `403` với đúng mã lỗi, **không** có cookie phiên.
- [ ] Sai mật khẩu và email không tồn tại → cùng `401 invalid_credentials`, cùng thông điệp.
- [ ] Sai 5 lần trong 15 phút → lần thứ 6 trả `429 rate_limited` kể cả khi mật khẩu đúng.
- [ ] `X-Forwarded-For` từ nguồn ngoài `TRUSTED_PROXIES` bị bỏ qua; từ proxy tin cậy thì giới hạn theo IP gốc (hai IP gốc khác nhau không khóa lẫn nhau).
- [ ] Đăng nhập thành công: cookie phiên có `HttpOnly`, `SameSite=Lax`; có `Secure` khi `COOKIE_SECURE=true`; DB chỉ lưu sha256 của token; có cookie `csrf_token` không `HttpOnly`; đăng xuất xóa cả hai cookie.
- [ ] Phiên quá 12 giờ → `401`.
- [ ] Đăng xuất rồi dùng lại cookie cũ → `401`.

### CSRF — `test_csrf.py`
- [ ] `POST` có cookie phiên nhưng thiếu `X-CSRF-Token` → `403 csrf_failed`.
- [ ] `X-CSRF-Token` không khớp cookie → `403 csrf_failed`.
- [ ] `GET` không yêu cầu CSRF token.
- [ ] Endpoint `/internal/worker` với bearer token không yêu cầu CSRF token.

### Hiệu lực tức thời — `test_immediate_effect.py`
- [ ] Admin bỏ role `engineer` của người dùng đang đăng nhập → request tiếp theo của người đó với permission `experiment.create` bị `403` (cùng phiên).
- [ ] Admin vô hiệu hóa người dùng đang đăng nhập → request tiếp theo `401`; mọi phiên của người đó bị thu hồi.
- [ ] Đổi mật khẩu → các phiên khác của người dùng bị thu hồi, phiên hiện tại vẫn dùng được.
- [ ] Đổi mật khẩu với `current_password` sai → `422 invalid_request`; phiên hiện tại vẫn dùng được.

### Quản trị — `test_admin.py`
- [ ] Duyệt không kèm role → `422`; đổi role thành danh sách rỗng → `422 validation_error`.
- [ ] Duyệt → user `active` với đúng role; đăng nhập được.
- [ ] Từ chối không kèm lý do → `422`; có lý do → `rejected`, lý do được lưu.
- [ ] Admin tự vô hiệu hóa chính mình → `409 conflict`.
- [ ] Bỏ role admin hoặc vô hiệu hóa admin `active` cuối cùng → `409 conflict`.
- [ ] Link đặt lại: dùng được một lần; lần hai → lỗi; hết hạn sau 24 giờ; sau khi dùng mọi phiên cũ bị thu hồi.
- [ ] Người không có `user.manage` gọi `/admin/users/*` → `403`.
- [ ] Chuyển trạng thái không hợp lệ (approve user `active`, enable user `active`, disable user `disabled`) → `409 conflict`.
- [ ] `GET /admin/users?status=pending` chỉ trả user `pending`; phân trang không trùng, không sót.
- [ ] Link đặt lại bắt đầu bằng `APP_BASE_URL` + `/reset-password/`.

### Audit — `test_audit_phase04.py`
- [ ] Mỗi thao tác `user.approved`, `user.rejected`, `user.roles_changed`, `user.disabled`, `user.enabled`, `user.reset_link_created`, `user.password_changed`, `user.password_reset`, `user.access_requested` tạo đúng một dòng `audit_log` với actor, entity, `before`, `after` đúng; actor của `access_requested`, `password_changed`, `password_reset` là chính người dùng đó.
- [ ] `/audit-log` trả `actor` dạng `{id, full_name, email}`, hoặc `null` với hành động hệ thống.
- [ ] Không dòng `audit_log` nào chứa mật khẩu, hash mật khẩu hoặc token.
- [ ] Đăng nhập, đăng nhập sai, đăng xuất ghi vào `auth_events`, không ghi vào `audit_log`.
- [ ] `/audit-log` lọc đúng theo actor, action, khoảng thời gian; phân trang không trùng, không sót.
- [ ] Người không có `audit.read` gọi `/audit-log` → `403`.

### Frontend — unit (Vitest)
- [ ] `can(permission)` trả đúng theo ma trận cho mọi tổ hợp role trong mock `Me`.
- [ ] Cấu hình điều hướng: mục chưa có trang không hiển thị; mục thiếu quyền không hiển thị.
- [ ] Mọi `ErrorCode` có thông điệp tiếng Việt.
- [ ] Schema `zod` của form yêu cầu truy cập từ chối mật khẩu dưới 10 ký tự.

### Frontend — E2E (Playwright, cả 3 viewport)
- [ ] Người dùng mới yêu cầu truy cập → đăng nhập thấy màn hình "đang chờ duyệt".
- [ ] Admin đăng nhập, vào "Người dùng", duyệt với role `engineer` → người dùng đăng nhập lại vào được `/home`, điều hướng chỉ hiện mục được phép.
- [ ] Admin từ chối một yêu cầu kèm lý do → người đó đăng nhập thấy màn hình "bị từ chối".
- [ ] Engineer truy cập trực tiếp `/admin/users` → chuyển tới `/forbidden`.
- [ ] Hết phiên (xóa cookie) → thao tác tiếp theo đưa về `/login`; đăng nhập xong quay lại đúng trang trước.
- [ ] Ở viewport 390px: thanh tab dưới đáy hiển thị; không có trang nào cuộn ngang; hộp xác nhận hiện dạng bottom sheet.
- [ ] Ở viewport 820px: điều hướng dạng cột icon.
- [ ] Admin đăng nhập thấy khối "tài khoản chờ duyệt" trên `/home` với đúng số lượng.
- [ ] Ở viewport 1440px: sidebar hiển thị; trang người dùng và audit log hiển thị dạng bảng.
- [ ] Điều hướng toàn bộ form đăng nhập và yêu cầu truy cập bằng bàn phím được.

## Manual Checks

- [ ] Toàn bộ luồng yêu cầu truy cập → duyệt → đăng nhập trên điện thoại Android và iPhone thật.
- [ ] Trên iPhone: chạm vào ô nhập không làm trang tự zoom; thanh tab không bị thanh home che.
- [ ] Mở hai trình duyệt: vô hiệu hóa người dùng ở trình duyệt admin, người dùng ở trình duyệt kia bị đăng xuất ở thao tác kế tiếp.
- [ ] Tạo link đặt lại, copy trên điện thoại, dùng thành công.
- [ ] Kiểm tra cookie trong DevTools: đúng cờ, không có dữ liệu nhạy cảm trong cookie hay localStorage.
- [ ] Đọc lại nội dung giao diện: tiếng Việt thống nhất, không còn chữ giữ chỗ.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass trên CI, bao gồm E2E trên 3 viewport.
- [ ] Toàn bộ Manual Checks đã thực hiện.
- [ ] Người duyệt đã chấp nhận thay đổi `tech-stack.md` và contract (đặc biệt là ma trận quyền).
- [ ] Câu hỏi mở đã có câu trả lời.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 4 được đánh dấu hoàn thành.
