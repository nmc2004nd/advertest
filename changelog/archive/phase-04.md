## Phase 4 — Xác thực và phân quyền

**Trạng thái:** ✅ hoàn thành 2026-09-29. Group 0–7 đã merge.

### Replan sau Phase 4 — 2026-09-29
- Phase 5 `requirements.md`: bảng endpoint dùng action `experiment.submit` (trước ghi `experiment.created`, mâu thuẫn với chính spec); mục Context ghi các quy ước của Phase 4 (`**guard(p)`, thứ tự 401/403/422, phân trang keyset và `Page[T]`, `validation_error`/`invalid_request`, `ERROR_MESSAGES`, action `entity.verb`). `validation.md`: `experiment.submit`.
- Phase 5 `plan.md`: task 1a (OpenAPI khai `422` là `ErrorResponse`, cân nhắc `ErrorCode` cho `500`), 2a (endpoint khung qua `**guard(p)`, cập nhật số permission có route trong test backend), 37 (cập nhật test điều hướng của Phase 4 khi bật `/experiments`).
- Phase 6 `plan.md` task 35: mục `/admin/attacks` trong `NAV_ITEMS` (admin 5 mục → điện thoại 3 mục + "Thêm"), dùng lại mẫu bảng/thẻ của Phase 4.
- `roadmap.md` Phase 11: "(Từ Phase 4)" `/docs` công khai, `TRUSTED_PROXIES` của compose chỉ hợp cho dev, ô chọn actor tối đa 100.
- Rủi ro: thời gian job CI `e2e` tăng theo số kịch bản (chạy tuần tự); kịch bản E2E đăng nhập sai nhiều lần sẽ khóa đăng nhập của cả bộ (cùng IP).

### Phase 4 — Tổng kết (phase-close) — 2026-09-29
- **Giao được:** yêu cầu truy cập → admin duyệt/từ chối → đăng nhập bằng phiên phía server (cookie httpOnly 12 giờ, sha256 token, CSRF double-submit, giới hạn 5 lần sai/15 phút theo email và IP qua `TRUSTED_PROXIES`); đổi và đặt lại mật khẩu (link một lần do admin tạo); ma trận quyền trong contract (21 permission, sinh sang TypeScript), `require_permission` cho mọi route cần phiên và kiểm tra lúc khởi động; quản trị người dùng (luật admin cuối cùng, tự vô hiệu hóa, chuyển trạng thái), audit log đủ thao tác tài khoản và trang xem cho admin; frontend mobile-first (sidebar / cột icon / thanh tab), trang giới thiệu, đăng nhập, yêu cầu truy cập, chờ duyệt, đặt lại mật khẩu, tài khoản, `/home` theo role, quản lý người dùng, audit log.
- **Contract:** `Permission`, `ROLE_PERMISSIONS`, 7 `ErrorCode` mới, 13 schema (`AccessRequest`, `Me`, `UserAdminView`, `AuditLogEntry`, `Page`...), OpenAPI `/auth/*`, `/admin/users/*`, `/audit-log` với `x-permission`; `AuditLogEntry.action` chỉ đòi chuỗi không rỗng (review Group 3). Người dùng chấp nhận (làm thay người duyệt theo ủy quyền).
- **Số liệu cuối:** `make check` (709 test Python, 217 test nghiệm thu không cần DB, 103 Vitest), `make test-db` (251 test, gồm 70 test nghiệm thu Phase 4 cần DB), `make test-e2e` (39 test = 13 kịch bản × 3 viewport, khoảng 38 giây).
- **`validation.md`:** Automated Tests đủ; Manual Checks 6/6 (điện thoại Android và iPhone thật, đọc lại nội dung: người dùng xác nhận); Definition of Done 5/5.
- **CI:** xanh trên GitHub, gồm job `e2e` (người dùng xác nhận, 2026-09-29).
- **Chuyển tiếp (không chặn):** `/docs`, `/openapi.json` công khai; compose tin cả mạng Docker trong `TRUSTED_PROXIES` (chỉ hợp cho dev); lỗi `500` chưa có `ErrorCode`, OpenAPI khai `422` là `HTTPValidationError`; ô chọn actor trên trang audit tối đa 100 người dùng; 9 permission chưa có route chỉ được kiểm tra ở mức ma trận.
- **Lưu ý:** Group 0, 7, việc review, merge và phase-close do agent làm thay người duyệt theo ủy quyền của người dùng; review và test nghiệm thu do chính agent đã viết code thực hiện nên không độc lập.

### Phase 4 — Group 7 (người duyệt, người dùng giao) — 2026-09-29
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_04/` (134 test: 64 ô ma trận quyền không cần DB, 70 test `db`): người dùng tạo qua API thật (yêu cầu truy cập, admin duyệt), mỗi client một IP gốc qua proxy tin cậy, đồng hồ giả. Đủ mọi mục Automated Tests backend của `validation.md` (bảo vệ route, xác thực, CSRF, hiệu lực tức thời, quản trị, audit). Luật "admin active cuối cùng" kiểm tra qua HTTP bằng cách tạm vô hiệu các admin khác rồi khôi phục (người dùng chốt).
- E2E `frontend/e2e/phase_04/` (13 kịch bản × 3 viewport = 39): yêu cầu truy cập → chờ duyệt; admin duyệt qua giao diện → điều hướng chỉ mục được phép; từ chối có lý do; engineer → `/forbidden`; hết phiên → `/login?next=` rồi quay lại; bàn phím cho form đăng nhập và yêu cầu truy cập; bố cục theo viewport (tab/cột icon/sidebar, bảng/thẻ, bottom sheet, không cuộn ngang); số chờ duyệt trên `/home`; hai trình duyệt; cờ cookie và localStorage. Hai lần chạy liên tiếp đều 39/39.
- Playwright `workers: 1` (người dùng chốt: các kịch bản dùng chung DB).
#### Thay đổi
- Test nghiệm thu Phase 0 (`test_api.py`, task 34): bỏ nhánh chuyển tiếp; không phiên → đúng `401 unauthenticated`; phiên thật đủ 3 role → đúng `501` cho nhóm còn là khung.
#### Manual check (máy phát triển, không có điện thoại thật)
- `make up` (project `advertest-p4check`, cổng riêng, env tạm, đã dọn): 4 service healthy; uvicorn chạy `--no-proxy-headers`; seed admin trong container; đăng nhập bằng email chữ hoa → `200`, cookie `advertest_session` (`HttpOnly; Max-Age=43200; Path=/; SameSite=lax`) và `csrf_token` (không `HttpOnly`); `/auth/me` đúng; đăng nhập qua proxy `/api` của frontend `200`; đăng xuất thiếu CSRF → `403`.
- **Phát hiện:** trong compose, với `TRUSTED_PROXIES=127.0.0.1` mặc định, đăng nhập qua proxy của frontend ghi IP của container frontend (`172.19.0.5`): mọi người dùng chung một IP, giới hạn đăng nhập sai theo IP khóa chung. Đã sửa (người dùng chốt): compose mặc định `TRUSTED_PROXIES=127.0.0.1,172.16.0.0/12`, ghi chú trong `.env.example` rằng bản triển khai chỉ đặt IP reverse proxy thật. Chạy lại `make up`: không header → ghi `172.19.0.1` (gateway, mọi người dùng trên máy này vốn chung IP vì cổng chỉ gắn 127.0.0.1); có reverse proxy gửi `X-Forwarded-For: 198.51.100.23` → ghi đúng `198.51.100.23`.
- Chưa làm (cần người dùng): điện thoại Android và iPhone thật (luồng đầy đủ, không tự zoom, thanh tab không bị thanh home che, copy link đặt lại); đọc lại toàn bộ nội dung tiếng Việt.
#### Số liệu
- `make check`: 709 test Python, 217 test nghiệm thu không cần DB, 103 Vitest. `make test-db`: 251 test. `make test-e2e`: 39 test trong khoảng 38 giây.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn. Ghi vào spec: E2E tuần tự (`tech-stack.md` mục 7), `TRUSTED_PROXIES` của compose (`requirements.md`), cách kiểm tra luật admin cuối cùng (`validation.md`). Ghi nhận: tin cả mạng Docker chỉ hợp cho dev (xem lại ở Phase 11).

### Phase 4 — Group 6 (frontend) — 2026-09-29
#### Thêm
- `/admin/users`: tab Chờ duyệt / Tất cả, "Tải thêm"; bảng TanStack Table v9 (≥ 1280px), thẻ (< 1280px); duyệt (role được yêu cầu chọn sẵn), từ chối (bắt buộc lý do), đổi role (bỏ admin có cảnh báo), vô hiệu hóa (xác nhận), kích hoạt, link đặt lại (ô chỉ đọc + copy, dự phòng chọn sẵn khi không có clipboard); lỗi 409/422 trong dialog; làm mới danh sách, số chờ duyệt, audit, `me`.
- `/admin/audit`: lọc người thực hiện (ô chọn hoặc nhấn tên), hành động, loại đối tượng, khoảng ngày; thay đổi dạng `status: a → b`; ID rút gọn ở giữa kèm copy; bảng/thẻ; "Tải thêm".
- Điều hướng bật 2 trang admin; dependency `@tanstack/react-table` 9.2.4. Vitest 91 → 103.
#### Kiểm tra
- Luồng admin thật (spec tạm, không commit) trên 3 viewport: duyệt, từ chối, đổi role, tạo và copy link, vô hiệu hóa, lọc audit, người bị từ chối thấy `/pending?code=account_rejected`; dialog là bottom sheet ở 390px; không cuộn ngang.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md`, `tech-stack.md`)
- Lọc actor bằng ô chọn (tối đa 100) và nhấn tên; "Tải thêm"; ngày theo giờ máy, trọn ngày kết thúc; ẩn nút tự vô hiệu hóa; bảng từ 1280px.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn. Ghi nhận: ô chọn actor thiếu người khi hơn 100 người dùng.

### Phase 4 — Group 5 (frontend) — 2026-09-29
#### Thêm
- Trang `/` (giới thiệu, ba role), `/login` (quay lại `next`; `account_*` → `/pending?code=`), `/request-access` và `/request-access/sent`, `/pending`, `/reset-password/:token`, `/account` (thông tin, đổi mật khẩu với lỗi `422` dưới ô mật khẩu hiện tại, đăng xuất), `/home` (khối theo role, số chờ duyệt cho admin).
- `RequirePermission` hiện lỗi và nút "Thử lại" khi `/auth/me` lỗi khác `401` (task 30a); điều hướng bật "Trang chủ", "Tài khoản".
- Schema zod (`src/auth/schemas.ts`) cùng luật với contract; `SelectField`, `TextareaField`, `FormAlert`, `LoadError`; `src/test-utils.tsx`. Vitest 70 → 91.
#### Sửa trong lúc làm
- Bản build của E2E không đặt `VITE_API_BASE_URL=/api` nên gọi API không qua proxy (kịch bản khói chỉ gọi `/api/health` nên không lộ): đặt trong `playwright.config.ts`.
#### Kiểm tra
- Chạy thử luồng thật (spec tạm, không commit) trên 3 viewport với backend thật: yêu cầu truy cập → chờ duyệt → admin duyệt (qua API) → `/account` chuyển về `/login?next=` rồi quay lại → đổi mật khẩu (sai rồi đúng) → đăng xuất; không cuộn ngang.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md`, `tech-stack.md`, `plan.md`)
- `/pending?code=`; `/request-access/sent`; khối admin đếm tối đa 100 ("100+"); bản build E2E dùng `/api`; Group 6 làm mới số chờ duyệt sau khi duyệt/từ chối.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn.

### Phase 4 — Group 4 (frontend) — 2026-09-29
#### Thêm
- API client: `apiSend` gửi cookie và `X-CSRF-Token` (từ cookie `csrf_token`); `401 unauthenticated` → `/login?next=...`, `403 forbidden` → `/forbidden` qua `QueryCache`/`MutationCache`; `ERROR_MESSAGES` tiếng Việt cho mọi `ErrorCode`; proxy Vite `xfwd: true`.
- `useMe()`, `can()`, `<RequirePermission>`, trang `/forbidden`; cấu hình điều hướng `src/nav/config.ts` (quyền, cờ `implemented`; mọi mục còn `false`).
- `AppShell`: sidebar ≥ 1280px, cột icon 768–1279px, thanh tab < 768px (3 mục + "Thêm"), `safe-area-inset`, `viewport-fit=cover`; `Dialog` đáp ứng (bottom sheet trên điện thoại), `ConfirmDialog`, `Button` (≥ 44px), `TextField`, `useZodForm` (resolver tự viết).
- Dependency: `react-hook-form` 7.89.0, `zod` 4.6.5. Vitest 36 → 70.
#### Sửa trong lúc làm
- Bản build production chứa chunk mock khi kiểm tra chế độ mock qua hàm gọi từ hai chỗ: viết thẳng biểu thức `import.meta.env` tại chỗ gọi.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md`, `tech-stack.md`)
- Thanh tab 3 mục + "Thêm"; chỉ `401 unauthenticated`/`403 forbidden` chuyển trang toàn cục; `next` chỉ đường dẫn nội bộ; `VITE_MOCK_ME`; resolver zod tự viết.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn. Chuyển cho Group 5 (`plan.md` task 30a): trạng thái lỗi khi `/auth/me` lỗi khác `401`.

### Phase 4 — Group 3 (backend) — 2026-09-29
#### Thêm
- `backend/app/admin/users.py`: duyệt, từ chối, đổi role, vô hiệu hóa (thu hồi mọi phiên), kích hoạt, tạo link đặt lại (24 giờ, sha256, vô hiệu link cũ); khóa dòng và advisory lock cho luật admin active cuối cùng; audit `before`/`after` = `{status, roles}` trong cùng transaction.
- `backend/app/audit/query.py`, `backend/app/api/pagination.py`: `/audit-log` lọc, `actor` dạng object; phân trang keyset theo `(created_at, id)`.
- Endpoint `/admin/users/*`, `/audit-log` (OpenAPI không đổi); `APP_BASE_URL` trong compose và `.env.example`.
- Test: `tests/db/test_admin_api.py` (19): duyệt/từ chối, `409` các loại, admin cuối cùng (service, trong transaction rollback), link đặt lại, hiệu lực tức thời, `403`, phân trang, audit không chứa bí mật, `/audit-log` không lọc đọc được dòng lệch quy ước.
#### Contract (người duyệt, người dùng chốt ở review)
- `AuditLogEntry.action`: bỏ mẫu `entity.verb`, chỉ đòi chuỗi không rỗng. Lý do: audit log chỉ thêm, dòng lệch quy ước (test Phase 0 chèn `'x'`) làm cả trang `/audit-log` trả `500`. Quy ước `entity.verb` giữ cho code ghi, có test.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md`, `validation.md` Phase 4)
- Đổi role và tạo link chỉ cho user `active`/`disabled`; link mới vô hiệu link cũ; `reset_link_created` có `before` = `after`; thứ tự `(created_at, id)` giảm dần, cursor mờ, cursor sai hoặc thời gian thiếu múi giờ → `422`; `APP_BASE_URL` mặc định.
#### Review
- Review do chính agent viết nhánh (không độc lập). Phát hiện nên sửa (#3, `/audit-log` trả `500` với dòng lệch mẫu) đã xử lý trước khi merge bằng thay đổi contract ở trên và test backend.

### Phase 4 — Group 2 (backend) — 2026-09-29
#### Thêm
- `backend/app/auth/permissions.py`: `require_permission(p)` theo `ROLE_PERMISSIONS` (`403 forbidden`), `guard(p)` (dependency và `x-permission` từ một nguồn), `check_route_permissions` chạy trong `create_app()` và `lifespan`.
- Mọi route cần phiên trong `public.py` dùng `**guard(...)`: `401`/`403` trước `501`. OpenAPI không đổi.
- `current_user` đọc cookie bằng dependency riêng `session_token`: thiếu cookie → `401` không mở DB.
- Test: ma trận quyền (63 trường hợp), route giả thiếu hoặc lệch khai báo, `401` cho mọi route cần phiên, phiên thật theo từng role (12 permission có route), hợp role, bỏ role có hiệu lực ngay.
#### Phát hiện khi làm
- FastAPI 0.141 giữ router con dưới dạng `_IncludedRouter` (không chép route vào `app.routes`): kiểm tra phải duyệt bằng `fastapi.routing.iter_route_contexts` như khi sinh OpenAPI; có test bảo đảm route qua router con bị phát hiện.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md` Phase 4)
- `**guard(p)`; kiểm tra khởi động đòi đúng một `require_permission` khớp `x-permission`; thứ tự `401` → `403` → `422` → route; thiếu cookie không mở DB.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn. Ghi nhận: 9 permission chưa có route chỉ được kiểm tra ở mức ma trận; `/docs`, `/openapi.json` vẫn công khai (xét ở Phase 11).
- `make check` (717 test Python, 153 nghiệm thu, 36 Vitest) và `make test-db` (161) pass.

### Phase 4 — Group 1 (backend) — 2026-09-29
#### Thêm
- Migration `0003`: `sessions` (sha256 token, `UPDATE` không `DELETE`), `password_reset_tokens` (`UPDATE` không `DELETE`), `auth_events` (chỉ thêm), `users.reject_reason`, `users.disabled_at`.
- `backend/app/auth/`: argon2id và chính sách mật khẩu (`passwords.py`); phiên phía server 12 giờ, cookie `advertest_session` (HttpOnly, SameSite=Lax, Secure theo `COOKIE_SECURE`) và `csrf_token` (`sessions.py`); `current_user` đọc phiên, user, trạng thái, role từ DB (`deps.py`); middleware CSRF double-submit (`csrf.py`); giới hạn 5 lần sai trong 15 phút theo email và IP (`rate_limit.py`); nghiệp vụ (`service.py`).
- Endpoint `/auth/request-access`, `login`, `logout`, `me`, `password`, `password-reset` (OpenAPI không đổi).
- Lỗi thống nhất: body sai schema → `422 validation_error` (không lặp lại giá trị gửi lên); lỗi HTTP của framework → `ErrorResponse`.
- `TRUSTED_PROXIES`, `COOKIE_SECURE` trong compose và `.env.example`; entrypoint `--no-proxy-headers`.
- Test: `tests/db/test_auth_api.py` (24), `test_auth_sessions.py`, `tests/auth/test_csrf.py`, `test_passwords.py`, `tests/api/test_errors.py`.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md` Phase 4)
- Đúng mật khẩu nhưng tài khoản chưa `active`, và lần bị chặn `429`: không ghi `auth_events`, không tính vào giới hạn.
- `ProxyHeadersMiddleware` trong app thay cờ uvicorn (test được); audit đổi/đặt lại mật khẩu có `before`/`after` null; `405` → `invalid_request`; link đặt lại sai/đã dùng/hết hạn → `422 invalid_request`.
- `current_user` làm ở Group 1; Group 2 còn `require_permission`, gắn cho mọi route và kiểm tra lúc khởi động.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn. Chuyển cho Group 4: `xfwd: true` cho proxy Vite (`plan.md` task 19). Còn mở (contract): lỗi `500` chưa có `ErrorCode`; OpenAPI khai `422` là `HTTPValidationError`.
- `make check` (645 test Python, 153 nghiệm thu, 36 Vitest) và `make test-db` (155) pass.
#### Manual check còn lại
- `make up`: đăng nhập admin seed, xem cờ cookie trong DevTools (entrypoint mới chưa chạy trong Docker).

### Phase 4 — Group 0 (người duyệt, người dùng giao) — 2026-09-29
#### Contract
- `advertest_contracts.permissions`: enum `Permission` (21 giá trị), `ROLE_PERMISSIONS` (đúng từng ô bảng trong `requirements.md`), `permissions_for(roles)` (hợp), `AUTHENTICATED`; sinh `frontend/src/contracts/permissions.ts`.
- `ErrorCode` thêm `invalid_credentials`, `account_pending`, `account_rejected`, `account_disabled`, `rate_limited`, `csrf_failed`, `validation_error`.
- Schema mới: `AccessRequest`, `LoginRequest`, `Me` (`permissions` phải bằng hợp của `roles`), `UserAdminView`, `ApproveRequest`, `RejectRequest`, `RolesUpdate` (cả hai: ít nhất 1 role, không trùng), `PasswordChange`, `PasswordResetLink`, `PasswordResetConsume`, `AuditActor`, `AuditLogEntry`, `Page[T]` (`UserAdminPage`, `AuditLogPage`); kiểu `Email` (tự chuyển chữ thường), `NewPassword` (10–256 ký tự). Mock: `Me` cho từng role và engineer+reviewer, `UserAdminView` đủ 4 trạng thái, `AuditLogEntry` có actor `null`. 39 JSON Schema.
- OpenAPI: `/auth/request-access|login|password-reset` công khai (không cookie); `/auth/logout|me|password`, `/admin/users/*` (7 endpoint), `/audit-log` (lọc, cursor) là khung `501`. Mọi route cần phiên khai `x-permission` và `401`/`403` `ErrorResponse`. Bỏ `GET /users` (Phase 0).
#### Thêm
- `@playwright/test` 1.63.0, `frontend/playwright.config.ts` (3 viewport, `vite preview` có proxy `/api`), `frontend/e2e/smoke.spec.ts`; `scripts/e2e.sh` (migration, seed admin, uvicorn, Playwright); `make test-e2e`; job CI `e2e`.
#### Thay đổi
- `tech-stack.md` mục 4, 4.1, 5, 11 (phiên phía server, `require_permission`/`x-permission`, `react-hook-form`/`zod`, Playwright); `roadmap.md` Phase 4.
- Test nghiệm thu Phase 0 (`test_api.py`, `test_contracts.py`): nhóm `/admin` thay `/users`; endpoint công khai của `/auth`; kiểm tra `501` chỉ cho nhóm còn là khung và tạm chấp nhận `401 unauthenticated` khi không có phiên (Group 7 siết lại, `plan.md` task 34).
- Ngoài thư mục người duyệt (người dùng cho phép): `backend/app/api/public.py`, `errors.py`, `security.py` (mô tả cookie), `main.py`; `backend/app/tests/api/test_skeleton.py` (danh sách route, thêm kiểm tra `x-permission`); `scripts/gen_contracts.py`; `Makefile`; `.github/workflows/ci.yml`; `frontend/` (Playwright, tsconfig, ignore).
#### Quyết định (người dùng chốt, đã ghi vào spec Phase 4)
- Kickoff: sửa test Phase 0; IP qua `TRUSTED_PROXIES`; sai mật khẩu hiện tại → `422 invalid_request`; action `user.password_reset`, actor là chính người dùng, `AuditLogEntry.actor` dạng object; phiên 12 giờ không ghi nhớ; bổ sung độ phủ (email chữ thường, `409` cho chuyển trạng thái sai, `APP_BASE_URL`, test hợp quyền...).
- Group 0: `x-permission: authenticated` cho route chỉ cần đăng nhập; `RolesUpdate` ít nhất 1 role; test Phase 0 chuyển tiếp `401|501`.
- Người duyệt (agent) tự chọn: ánh xạ `x-permission` của endpoint khung (`/reviews` → `review.decide`, `/budget` → `budget.manage`, `/slices` → `dataset.read`, `/failure-cases` → `experiment.read`); `Email` tự kiểm tra hình dạng thay vì `EmailStr` (tránh dependency `email-validator`).
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn; ghi vào `requirements.md` chi tiết phản hồi của endpoint (login trả `Me`, `202`/`204`, `limit` 50/100, `since`/`until`), sửa câu task 1a trong `plan.md`. Còn theo dõi: job CI `e2e` chưa chạy trên GitHub; Group 7 siết lại test Phase 0.
#### Số liệu
- `make test-e2e`: 6 test (2 kịch bản × 3 viewport) pass trong 3.7 giây.
