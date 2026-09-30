# Validation: Phase 5 — Wizard tạo experiment và theo dõi tiến độ

> Test trong `tests/acceptance/phase_05/` và `frontend/e2e/phase_05/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. CI chạy worker trên CPU với fixture.

## Automated Tests

### Chung
- [x] `make check` pass, bao gồm test nghiệm thu các phase trước.
- [x] `make contracts` không tạo thay đổi; mock mới validate được.
- [x] Test bảo vệ route của Phase 4 vẫn pass với mọi endpoint mới (có `x-permission`, `401` khi chưa đăng nhập).

### Kiểm tra cấu hình — `test_experiment_validation.py`
- [x] Không có attack → `422` với đường dẫn trường `attacks`.
- [x] `spec_sha256` không khớp version hiện hành → `422`.
- [x] Level ngoài dải của spec, level trùng, hơn 12 level, hoặc tổng hơn 50 run → `422` với đường dẫn trường đúng.
- [x] `mode = search` → `422 not_supported_yet`.
- [x] Slice không thuộc dataset version của mapping, hoặc mapping không dành cho model → `422`.
- [x] Protocol `retired` → `422`.
- [x] Target `kind = rented` → `422`; `limit.kind = budget` với máy local → `422`; giới hạn vượt `max_time_limit_s` → `422`.
- [x] Experiment thứ 4 đang chờ của cùng người dùng → `409 queue_limit_reached`; experiment của người khác không bị ảnh hưởng.
- [x] Ước lượng và tạo cho cùng kết quả kiểm tra với cùng cấu hình.

### Ước lượng — `test_estimate.py`
- [x] Có đủ cost profile: `est_seconds` từng run và `total_seconds` đúng công thức.
- [x] Thiếu profile cho một attack: run đó có `est_seconds = null`, attack nằm trong `missing_profiles`, `total_seconds = null`; vẫn tạo được experiment.
- [x] Tổng ước lượng lớn hơn giới hạn → `exceeds_limit = true`; thiếu profile nhưng phần ước lượng được đã vượt giới hạn → vẫn `true`.
- [x] Hai experiment đang chờ trước → `queue.position = 3`, `ahead_seconds` bằng tổng ước lượng còn lại của chúng.
- [x] Model không hỗ trợ gradient + attack cần gradient → run có `skip_reason = incompatible`, `est_seconds = 0`.

### Quyền và vòng đời — `test_experiment_lifecycle.py`
- [x] Engineer tạo experiment → `queued`, có `audit_log` `experiment.submit`; worker chạy xong → `completed`, có `finished_at`.
- [x] Reviewer và admin gọi `POST /experiments` → `403`.
- [x] Mọi người dùng `active` xem được experiment của người khác.
- [x] Engineer hủy experiment của người khác → `403`; hủy của mình khi `running` → worker dừng, trạng thái `cancelled`, có `audit_log`.
- [x] Hủy experiment đã `completed` → `409 conflict`.
- [x] `clone` trả `ExperimentClone`: cấu hình giống experiment gốc; khi spec đã có version mới thì dùng version mới và `warnings` có mục tương ứng.
- [x] Tạo không có `name` → tên theo quy tắc `<model> · <slice> · <ngày UTC>`; experiment `cancelled` có `finished_at`.
- [x] `limit.value` bằng `max_time_limit_s` (mặc định 28800) được chấp nhận; lớn hơn 1 giây → `422`.

### Ảnh và quyền riêng tư — `test_failure_case_access.py`
- [x] Dataset `anonymized = true`: `display_mode = normal`, có URL ảnh, URL hết hạn sau 10 phút.
- [x] Dataset `anonymized = false`, không bật cờ dev: `display_mode = hidden_unanonymized`, **không** có URL ảnh sạch, ảnh sau tấn công hay thumbnail; vẫn có dữ liệu box.
- [x] Dataset `anonymized = false`, `DEV_ALLOW_UNBLURRED=true`: `display_mode = dev_unblurred`, có URL.
- [x] URL tạm thời chỉ đọc được đúng đối tượng được cấp.
- [x] URL ảnh có dạng `/artifacts/{token}`; token hết hạn hoặc bị sửa → `404`; token của khóa A không đọc được khóa B; không có phiên → `401`.

### Đọc tài nguyên — `test_catalog_read.py`
- [x] `GET /attack-specs` chỉ trả spec đang hoạt động; `GET /protocols` không trả `retired`; `GET /class-mappings` lọc đúng theo dataset version và model.
- [x] `online` đúng theo heartbeat 60 giây; `queue_length` đúng.
- [x] `GET /experiments` lọc theo `owner`, `status`, `model`; phân trang cursor.

### Email — `test_email.py`
- [x] Experiment `completed` → đúng một email trong outbox gửi chủ sở hữu, có tên, câu tóm tắt trạng thái, link chi tiết.
- [x] Experiment `cancelled` → có email; experiment chưa kết thúc → không có email.
- [x] SMTP lỗi → email được thử lại, sau 5 lần chuyển `failed` với `last_error`; trạng thái experiment không bị ảnh hưởng.
- [x] Nội dung email không chứa URL ảnh hay dữ liệu dataset.

### Frontend — unit (Vitest)
- [x] Câu tóm tắt trạng thái đúng cho các tổ hợp `run_counts` trong mock (ví dụ "18/20 hoàn thành, 1 lỗi, 1 dừng do giới hạn").
- [x] Biểu đồ đánh dấu run `partial`; bảng số liệu đi kèm có đủ giá trị.
- [x] Chip chỉnh level từ chối giá trị ngoài dải và giá trị trùng.
- [x] Hook polling ngừng gọi API khi experiment ở trạng thái cuối.
- [x] `CaseViewer` hiển thị khung giữ chỗ khi `hidden_unanonymized` và dải cảnh báo khi `dev_unblurred`.
- [x] Hook ảnh xin lại URL trước khi `urls_expire_at` đến.

### Frontend — E2E (Playwright, cả 3 viewport)

Môi trường E2E bật `DEV_ALLOW_UNBLURRED=true` (fixture KITTI có `anonymized = false`): trình xem hiển thị dải cảnh báo.

Ba viewport chạy tuần tự trên cùng DB: viewport chạy sau gửi cùng cấu hình nên run trúng cache theo fingerprint (`skipped`). Tiêu chí "khi xong" là experiment `completed`; câu tóm tắt được là "2/2 hoàn thành" hoặc "0/2 hoàn thành, 2 bỏ qua" (quyết định Group 7). `scripts/e2e.sh` tạo thêm máy local `e2e-offline` không có worker, để experiment gửi tới đó nằm chờ (kịch bản `queue_limit_reached` và `/home`).

- [x] Engineer đi hết wizard (FGSM eps 4, PGD eps 4 trên slice fixture, máy `local-dev`), thấy ước lượng ở bước 6, xác nhận → được chuyển tới trang chi tiết.
- [x] Trang chi tiết cập nhật tiến độ không cần tải lại; khi xong, trạng thái `completed`, tab Kết quả hiển thị biểu đồ và bảng.
- [x] Tab Failure case có thumbnail kèm watermark; mở một case, bật tắt được từng lớp box.
- [x] Tab Tái lập hiển thị fingerprint và tải được manifest.
- [x] Tải lại trang giữa wizard → dữ liệu đã nhập vẫn còn.
- [x] Nhập level ngoài dải → lỗi hiển thị tại bước 4, không sang bước tiếp được.
- [x] Nhân bản một experiment → wizard mở tại bước 6 với dữ liệu điền sẵn.
- [x] Reviewer không thấy mục "Tạo experiment"; truy cập trực tiếp `/experiments/new` → `/forbidden`.
- [x] Ở viewport 390px: wizard một bước một màn hình, thanh dưới hiển thị thời gian ước lượng; trình xem case dùng slider; không trang nào cuộn ngang.
- [x] Hủy experiment đang chạy qua hộp xác nhận → trạng thái chuyển `cancelled`.
- [x] Bước 6 hiển thị seed 0.
- [x] Engineer có 3 experiment đang chờ → gửi lần thứ 4 hiện thông báo `queue_limit_reached`.
- [x] `/home` của engineer có khối experiment đang chạy và nút "Tạo experiment"; tab Chi phí hiển thị thời gian đã dùng so với giới hạn.

## Manual Checks

- [ ] Trên laptop: tạo experiment PGD (eps 2, 4, 8, 16) trên slice KITTI 300 ảnh bằng wizard; ước lượng hiển thị hợp lý so với thời gian thực tế (ghi sai số vào `CHANGELOG.md`).
- [x] Theo dõi tiến độ experiment đó trên điện thoại thật đến khi xong.
- [x] Nhận email trong Mailpit khi experiment kết thúc; link mở đúng trang chi tiết.
- [x] Với KITTI (`anonymized = false`): mặc định ảnh bị ẩn; bật `DEV_ALLOW_UNBLURRED` thì hiển thị kèm dải cảnh báo.
- [x] Trên điện thoại: pinch-zoom và slider trong trình xem case mượt; vuốt chuyển case hoạt động.
- [x] Trên iPhone: thanh dưới của wizard không bị thanh home che; ô nhập không làm trang tự zoom.
- [x] Biểu đồ đọc được ở cả chế độ sáng và tối.
- Ghi chú (phase-close, 2026-09-30): người dùng xác nhận đạt 6 mục đã đánh dấu. Mục PGD 300 ảnh chưa đo (chưa có sai số ước lượng), để tồn đọng.

## Definition of Done

- [x] Toàn bộ Automated Tests pass trên CI, bao gồm E2E trên 3 viewport.
- [ ] Toàn bộ Manual Checks đã thực hiện.
- [x] Người duyệt đã chấp nhận thay đổi contract.
- [x] Câu hỏi mở đã có câu trả lời; nếu làm mờ được đưa lên sớm thì `roadmap.md` đã cập nhật.
- [x] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 5 được đánh dấu hoàn thành.
