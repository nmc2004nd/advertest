# Requirements: Phase 4 — Xác thực và phân quyền

## Scope

Ba role hoạt động đúng quyền, từ lúc người dùng yêu cầu truy cập đến lúc được admin duyệt và dùng hệ thống. Kết quả của phase gồm:

1. **Yêu cầu truy cập, đăng nhập, đăng xuất, đổi mật khẩu**, và đặt lại mật khẩu bằng link do admin tạo.
2. **Phiên đăng nhập phía server** trong cookie httpOnly, có chống CSRF và giới hạn đăng nhập sai.
3. **Ma trận quyền** là một phần của contract, dùng chung cho backend và frontend.
4. **Bảo vệ mọi endpoint** không công khai.
5. **Quản lý người dùng** cho admin: duyệt, từ chối, đổi role, vô hiệu hóa, tạo link đặt lại mật khẩu.
6. **Audit log** cho các thao tác tài khoản, và trang xem audit log cho admin.
7. **Frontend**: khung điều hướng theo role (mobile-first), trang giới thiệu tối giản, yêu cầu truy cập, đăng nhập, chờ duyệt, tài khoản, quản lý người dùng, audit log.

Phase này chỉ phụ thuộc Phase 0 và chạy song song được với Phase 2–3.

## Out of Scope

- Gửi email (Phase 5). Link đặt lại mật khẩu do admin tạo và tự chuyển cho người dùng.
- Xác minh email. Việc admin duyệt tài khoản đóng vai trò xác minh.
- Đăng nhập bằng bên thứ ba (Google, SSO), xác thực hai lớp.
- Trang của engineer, reviewer (Phase 5, 8). Mục điều hướng của chúng chỉ xuất hiện khi trang tương ứng đã có.
- Luật "không tự review" ở tầng service (Phase 8). Trigger DB đã có từ Phase 0.
- Trang giới thiệu hoàn chỉnh (Phase 11).

## Data / Fields

### Thay đổi constitution (cần người duyệt chấp nhận)

- **`tech-stack.md` mục 4:** đổi "JWT trong cookie httpOnly" thành **phiên phía server**: cookie chứa token ngẫu nhiên, DB lưu sha256 của token. *Lý do:* hệ thống yêu cầu vô hiệu hóa tài khoản và đổi role có hiệu lực ngay, và đăng xuất phải hủy được phiên. Với JWT, muốn làm vậy vẫn phải tra DB mỗi request, nên phiên phía server đơn giản và rõ ràng hơn.
- **`tech-stack.md` mục 5:** thêm `react-hook-form` và `zod` cho form. *Lý do:* các form của phase này và các phase sau (wizard, review) cần validation nhất quán.

### Thay đổi contract

**Ma trận quyền** (`contracts/python/advertest_contracts/permissions.py`, sinh sang TypeScript):

| Permission | engineer | reviewer | admin |
|---|:-:|:-:|:-:|
| `experiment.read` | ✓ | ✓ | ✓ |
| `experiment.create` | ✓ | | |
| `experiment.cancel_own` | ✓ | | |
| `experiment.submit_review` | ✓ | | |
| `dataset.read` | ✓ | ✓ | ✓ |
| `dataset.upload` | ✓ | | |
| `slice.create` | ✓ | | |
| `model.read` | ✓ | ✓ | ✓ |
| `model.manage` | | | ✓ |
| `attack_catalog.read` | ✓ | ✓ | ✓ |
| `attack_catalog.manage` | | | ✓ |
| `protocol.read` | ✓ | ✓ | ✓ |
| `protocol.manage` | | ✓ | |
| `review.decide` | | ✓ | |
| `report.export` | | ✓ | |
| `report.read` | ✓ | ✓ | ✓ |
| `user.manage` | | | ✓ |
| `compute_target.read` | ✓ | | ✓ |
| `compute_target.manage` | | | ✓ |
| `budget.manage` | | | ✓ |
| `audit.read` | | | ✓ |

Người dùng có nhiều role có hợp các permission. Các luật phụ thuộc đối tượng (chỉ hủy experiment của mình, không review experiment của mình) được kiểm tra ở tầng service, không nằm trong ma trận.

**Enum `ErrorCode`**: đã có từ Phase 3: `not_implemented`, `unauthenticated`, `forbidden`, `not_found`, `conflict`, `invalid_request` (422 nghiệp vụ); Phase 4 thêm `invalid_credentials`, `account_pending`, `account_rejected`, `account_disabled`, `rate_limited`, `csrf_failed`, `validation_error` (422 do body không đúng schema, thay body mặc định `{"detail": ...}` của FastAPI).

**Schema mới:**

| Schema | Nội dung chính |
|---|---|
| `AccessRequest` | `full_name`, `email`, `organization`, `requested_role`, `reason`, `password` |
| `LoginRequest` | `email`, `password` |
| `Me` | `id`, `full_name`, `email`, `roles`, `permissions`, `status` |
| `UserAdminView` | `id`, `full_name`, `email`, `organization`, `status`, `roles`, `requested_role`, `request_reason`, `reject_reason`, `created_at`, `approved_at`, `approved_by` |
| `ApproveRequest` | `roles` (ít nhất 1) |
| `RejectRequest` | `reason` |
| `RolesUpdate` | `roles` (ít nhất 1; muốn chặn truy cập thì vô hiệu hóa) |
| `PasswordChange` | `current_password`, `new_password` |
| `PasswordResetLink` | `url`, `expires_at` |
| `PasswordResetConsume` | `token`, `new_password` |
| `AuditLogEntry` | `id`, `actor` (`{id, full_name, email}`, hoặc `null` với hành động của hệ thống), `action`, `entity_type`, `entity_id`, `before`, `after`, `created_at` |
| `Page[T]` | `items`, `next_cursor` |

### Thay đổi DB

| Bảng | Cột chính |
|---|---|
| `sessions` | `id`, `user_id`, `token_sha256`, `created_at`, `expires_at`, `last_seen_at`, `revoked_at`, `user_agent`, `ip` |
| `password_reset_tokens` | `id`, `user_id`, `token_sha256`, `created_by`, `expires_at`, `used_at` |
| `auth_events` | `id`, `email`, `ip`, `kind` (`login_success`, `login_failed`, `logout`), `created_at` |
| `users` (bổ sung) | `reject_reason`, `disabled_at` |

## Behaviour

### Endpoint

| Endpoint | Quyền | Hành vi |
|---|---|---|
| `POST /auth/request-access` | Công khai | Tạo user `pending`. Email được chuyển về chữ thường trước khi lưu và so sánh (cả khi đăng nhập). Email đã tồn tại (không phân biệt hoa thường) → vẫn trả `202` cùng nội dung, không tạo thêm |
| `POST /auth/login` | Công khai | Thành công → tạo phiên, đặt cookie. Sai → `401 invalid_credentials` (cùng thông điệp cho email không tồn tại). Đúng mật khẩu nhưng tài khoản chưa `active` → `403` với `account_pending` / `account_rejected` / `account_disabled`, không tạo phiên |
| `POST /auth/logout` | Đã đăng nhập | Thu hồi phiên hiện tại, xóa cookie |
| `GET /auth/me` | Đã đăng nhập | Trả `Me` |
| `POST /auth/password` | Đã đăng nhập | Đổi mật khẩu; thu hồi mọi phiên khác của người dùng. Sai `current_password` → `422 invalid_request` (không dùng `401` để frontend không chuyển về `/login`) |
| `POST /auth/password-reset` | Công khai | Dùng token một lần; đặt mật khẩu mới; thu hồi mọi phiên |
| `GET /admin/users?status=` | `user.manage` | Danh sách phân trang |
| `POST /admin/users/{id}/approve` | `user.manage` | `pending` → `active`, gán role |
| `POST /admin/users/{id}/reject` | `user.manage` | `pending` → `rejected`, lưu lý do |
| `PUT /admin/users/{id}/roles` | `user.manage` | Đổi role; có hiệu lực ngay từ request tiếp theo |
| `POST /admin/users/{id}/disable` | `user.manage` | `active` → `disabled`; thu hồi mọi phiên |
| `POST /admin/users/{id}/enable` | `user.manage` | `disabled` → `active` |
| `POST /admin/users/{id}/reset-link` | `user.manage` | Tạo link đặt lại mật khẩu `{APP_BASE_URL}/reset-password/{token}`, hết hạn sau 24 giờ |
| `GET /audit-log` | `audit.read` | Lọc theo actor, action, entity, khoảng thời gian; phân trang |

Chi tiết phản hồi (chốt ở review Group 0): `POST /auth/login` thành công trả `Me`; `request-access` trả `202` không có body; `logout`, `password`, `password-reset` trả `204`; các endpoint `/admin/users/{id}/*` trả `UserAdminView` sau thay đổi, `reset-link` trả `PasswordResetLink`. Phân trang theo cursor: `limit` mặc định 50, tối đa 100; `next_cursor = null` khi hết. `/audit-log` lọc bằng `actor_id`, `action`, `entity_type`, `entity_id`, `since` (gồm mốc), `until` (không gồm mốc). Chốt ở review Group 3: danh sách sắp theo `(created_at, id)` giảm dần; cursor là chuỗi mờ, cursor sai → `422 invalid_request`; `since`/`until` không có múi giờ → `422 invalid_request`. Audit `user.reset_link_created` có `before` bằng `after` (trạng thái không đổi). `APP_BASE_URL` mặc định `http://localhost:5173`. `AuditLogEntry.action` chỉ đòi chuỗi không rỗng để dòng cũ lệch quy ước vẫn đọc được; code ghi audit theo quy ước `entity.verb` (có test).

### Phiên và bảo mật
- Cookie phiên: `httpOnly`, `SameSite=Lax`, `Secure` khi `COOKIE_SECURE=true`, hết hạn tuyệt đối sau 12 giờ; không có "ghi nhớ đăng nhập".
- Mỗi request đã xác thực đọc user, trạng thái và role **từ DB**. User không còn `active` → phiên bị từ chối (`401`).
- CSRF: server đặt cookie `csrf_token` (không httpOnly); mọi request thay đổi dữ liệu (`POST`, `PUT`, `PATCH`, `DELETE`) có cookie phiên phải gửi header `X-CSRF-Token` khớp → sai thì `403 csrf_failed`. Endpoint `/internal/worker` (bearer token) không áp dụng.
- Mật khẩu: argon2id; tối thiểu 10 ký tự, không trùng email. Áp dụng cho yêu cầu truy cập, đổi mật khẩu và đặt lại mật khẩu.
- Giới hạn đăng nhập sai: quá 5 lần trong 15 phút cho cùng email hoặc cùng IP → `429 rate_limited`.
- IP của client: chỉ lấy từ `X-Forwarded-For` khi kết nối đến từ proxy khai báo trong biến `TRUSTED_PROXIES` (uvicorn `--forwarded-allow-ips`); nếu không thì dùng địa chỉ kết nối. *Lý do:* API đứng sau proxy `/api`; tin mọi header thì bị giả mạo, không tin header nào thì mọi người dùng chung một IP.
- Cookie `csrf_token` (không httpOnly) được đặt khi đăng nhập thành công và xóa khi đăng xuất.
- Chi tiết cài đặt (chốt ở review Group 1): `X-Forwarded-For` xử lý trong app bằng `ProxyHeadersMiddleware` của uvicorn theo `TRUSTED_PROXIES`, uvicorn chạy với `--no-proxy-headers`. Chỉ sai email hoặc mật khẩu mới ghi `login_failed` và tính vào giới hạn; lần bị chặn `429` và lần đúng mật khẩu nhưng tài khoản chưa `active` không ghi `auth_events`. Link đặt lại không tồn tại, đã dùng hoặc hết hạn → `422 invalid_request`. Lỗi HTTP của framework trả `ErrorResponse` với mã theo status (`404` → `not_found`, `405` và mã 4xx khác → `invalid_request`).
- Mọi lỗi trả body `{"error": {"code": ErrorCode, "message": ...}}`.

### Bảo vệ endpoint
- Endpoint công khai: `/health`, `/auth/request-access`, `/auth/login`, `/auth/password-reset`, `/verify/{report_id}`.
- Mọi endpoint khác (trừ `/internal/worker`) yêu cầu phiên hợp lệ và khai báo permission bằng dependency `require_permission(...)`. Thiếu phiên → `401`; thiếu permission → `403`. Kiểm tra này chạy **trước** khi endpoint trả `501`.
- Endpoint chỉ cần đăng nhập (`/auth/logout`, `/auth/me`, `/auth/password`) khai `x-permission: authenticated` (mọi user `active`), không thêm permission vào ma trận.
- Placeholder `GET /users` của Phase 0 bị bỏ; quản lý người dùng nằm ở `/admin/users`.
- Chi tiết cài đặt (chốt ở review Group 2): route khai quyền bằng `**guard(p)`, một nguồn cho cả dependency `require_permission` và `x-permission`; kiểm tra lúc tạo app và lúc khởi động đòi mỗi route không công khai (trừ `/internal/worker`) có đúng một `require_permission` khớp `x-permission`. Thứ tự kiểm tra: `401` (phiên) → `403` (permission) → `422` (tham số, body) → route. Thiếu cookie phiên trả `401` mà không mở DB.

### Luật quản trị
- Duyệt phải gán ít nhất một role.
- Admin không vô hiệu hóa được chính mình.
- Không thể bỏ role admin hoặc vô hiệu hóa admin `active` cuối cùng.
- Chuyển trạng thái không hợp lệ (approve/reject user không `pending`, disable user không `active`, enable user không `disabled`) → `409 conflict`.
- Đổi role và tạo link đặt lại chỉ cho user `active` hoặc `disabled`; trạng thái khác → `409 conflict` (chốt ở Group 3).
- Tạo link đặt lại mới vô hiệu mọi link cũ chưa dùng của user đó (chốt ở Group 3).
- Mỗi thao tác quản trị ghi `audit_log` với `before` và `after` (trạng thái, role): `user.approved`, `user.rejected`, `user.roles_changed`, `user.disabled`, `user.enabled`, `user.reset_link_created`. Người dùng tự đổi mật khẩu ghi `user.password_changed`; dùng link đặt lại ghi `user.password_reset` (không ghi mật khẩu hay token; `before`/`after` là `null`).
- Yêu cầu truy cập ghi `user.access_requested`. Actor của `user.access_requested`, `user.password_changed`, `user.password_reset` là chính người dùng đó.
- Đăng nhập thành công/thất bại và đăng xuất ghi vào `auth_events`, không ghi vào `audit_log`.

### Frontend

**Điều hướng:**
- Cấu hình điều hướng tập trung: mỗi mục có đường dẫn, nhãn, icon, permission yêu cầu, và cờ trang đã có hay chưa. Chỉ hiện mục người dùng có quyền **và** trang đã có.
- Desktop (≥ 1280px): sidebar; tablet (768–1279px): cột icon; điện thoại (< 768px): thanh tab dưới đáy, tối đa 4 mục, các mục còn lại trong mục "Thêm".
- `/home` hiển thị các khối "việc của tôi" theo từng role người dùng có. Trong phase này: khối admin hiển thị số tài khoản chờ duyệt; khối engineer và reviewer hiển thị "Sắp có".

**Trang:**

| Trang | Đường dẫn | Nội dung |
|---|---|---|
| Giới thiệu | `/` | Mô tả ngắn, ba role, nút "Yêu cầu truy cập" và "Đăng nhập" |
| Đăng nhập | `/login` | Email, mật khẩu; chuyển về trang định vào trước đó sau khi đăng nhập |
| Yêu cầu truy cập | `/request-access` | Form `AccessRequest`; sau khi gửi chuyển đến màn hình xác nhận |
| Chờ duyệt | `/pending` | Hiển thị theo mã lỗi đăng nhập: đang chờ, bị từ chối, bị vô hiệu hóa |
| Đặt lại mật khẩu | `/reset-password/:token` | Mật khẩu mới, xác nhận |
| Tài khoản | `/account` | Thông tin, role, đổi mật khẩu, đăng xuất |
| Người dùng | `/admin/users` | Tab "Chờ duyệt" / "Tất cả"; duyệt (chọn role, mặc định chọn sẵn role được yêu cầu), từ chối (bắt buộc lý do), đổi role, vô hiệu hóa/kích hoạt, tạo link đặt lại (hiện link kèm nút copy) |
| Audit log | `/admin/audit` | Bộ lọc, danh sách; bảng trên desktop, thẻ trên điện thoại |
| Không có quyền | `/forbidden` | Thông báo và nút về trang chủ |

**Hành vi chung:**
- `401` từ API → chuyển về `/login` kèm đường dẫn hiện tại; `403` → `/forbidden`.
- Client tự gửi `X-CSRF-Token` từ cookie cho mọi request thay đổi dữ liệu.
- Hộp xác nhận cho: từ chối, vô hiệu hóa, bỏ role admin.
- Form dùng `react-hook-form` + `zod`; lỗi hiển thị cạnh ô nhập.
- Nội dung giao diện bằng tiếng Việt.
- Responsive theo `tech-stack.md` mục 5.1: không cuộn ngang ở 375px, vùng chạm ≥ 44px, font ô nhập ≥ 16px; dialog thành bottom sheet trên điện thoại.
- Có nhãn cho mọi ô nhập, điều hướng được bằng bàn phím.

## Decisions

- **Phiên phía server thay cho JWT.** *Lý do:* xem mục thay đổi constitution.
- **Role và trạng thái đọc từ DB mỗi request, không nằm trong cookie.** *Lý do:* vô hiệu hóa và đổi role phải có hiệu lực ngay (`mission.md` nguyên tắc 1).
- **Ma trận quyền nằm trong contract.** *Lý do:* backend và frontend dùng chung một nguồn; frontend ẩn đúng những gì backend chặn, không lệch nhau.
- **Mọi người dùng `active` đọc được mọi experiment; chỉ chủ sở hữu được sửa hoặc hủy.** *Lý do:* tổ chức nhỏ, minh bạch có lợi cho kiểm toán, và reviewer cần đọc mọi experiment.
- **Không tiết lộ email đã tồn tại.** *Lý do:* tránh dò danh sách tài khoản.
- **Link đặt lại mật khẩu do admin tạo.** *Lý do:* chưa có email ở phase này; admin đã là người duyệt tài khoản nên việc xác minh danh tính khi cấp lại mật khẩu cũng thuộc về admin.
- **Phiên 12 giờ tuyệt đối, không có "ghi nhớ đăng nhập".** *Lý do:* công cụ nội bộ, ưu tiên đơn giản và an toàn; có thể xem lại ở Phase 11.
- **Sự kiện đăng nhập tách khỏi `audit_log`.** *Lý do:* số lượng lớn và khác mục đích; `audit_log` dành cho thao tác thay đổi quyền và dữ liệu.

## Context

- `mission.md` mục 3 (role), nguyên tắc 1 (tách quyền), 3 (audit log bất biến).
- `tech-stack.md` mục 4 (backend), 5 (frontend), 5.1 (responsive).
- Phase 0: bảng `users`, `user_roles`, `audit_log` và quyền DB; OpenAPI khung; `StatusBadge`; mock mode của frontend.
- Phase 3: `advertest-admin --as` yêu cầu admin `active`, không đổi.

## Open Questions

- [x] Thời hạn phiên 12 giờ có phù hợp không, hay cần "ghi nhớ đăng nhập" dài hơn. → Giữ 12 giờ, không ghi nhớ (2026-09-29).
