# Requirements: Phase 5 — Wizard tạo experiment và theo dõi tiến độ

## Scope

Phase đầu tiên nối ML core, worker, backend và frontend thành một luồng người dùng hoàn chỉnh: engineer tạo experiment trên web, theo dõi tiến độ (kể cả trên điện thoại), xem kết quả và failure case. Kết quả của phase gồm:

1. **API đọc tài nguyên** cho wizard: model, dataset, slice, class mapping, attack catalog, protocol, compute target.
2. **API experiment**: ước lượng, tạo, liệt kê, xem chi tiết, hủy, nhân bản.
3. **Wizard tạo experiment** 6 bước, chế độ quét lưới.
4. **Trang danh sách và chi tiết experiment** với các tab Tổng quan, Kết quả, Failure case, Chi phí, Tái lập.
5. **Trình xem failure case** (chỉ xem, có watermark), là nền cho màn hình review ở Phase 8.
6. **Email** khi experiment kết thúc.
7. **Khối "việc của tôi"** cho engineer trên trang chủ.

Cuối phase: engineer tạo experiment trên web, theo dõi tiến độ trên điện thoại, xem đường cong metric và failure case khi xong.

## Out of Scope

- Chế độ tự tìm ngưỡng (Phase 7). Wizard chỉ hiển thị chế độ này ở trạng thái "Sắp có".
- Attack mới: patch, corruption, occlusion (Phase 6).
- Protocol thật, gửi duyệt, review, report (Phase 8). Wizard chỉ có protocol `dev-open`.
- Máy thuê, ngân sách, chi phí tiền (Phase 9). Tab Chi phí chỉ hiển thị thời gian.
- Upload dataset, tạo slice và class mapping trên web (Phase 10). Các tài nguyên này vẫn đăng ký qua `advertest-admin import-local`.
- Làm mờ mặt và biển số (Phase 10). Xem cách xử lý tạm thời trong Behaviour.
- So sánh nhiều experiment (Phase 11).
- Thông báo trong ứng dụng; lưu nháp wizard phía server.

## Data / Fields

### Thay đổi contract (cần người duyệt chấp nhận)

| Schema | Nội dung chính |
|---|---|
| `ExperimentCreate` | Giống `ExperimentConfig`; tùy chọn `name`, `cloned_from` |
| `EstimateResponse` | `runs` (mỗi run: `attack_spec_id`, `level`, `images`, `sec_per_image`, `est_seconds`, null nếu thiếu profile), `total_seconds` (null nếu thiếu profile), `missing_profiles`, `exceeds_limit`, `queue` (`position`, `ahead_seconds`) |
| `ExperimentSummary` | `id`, `name`, `owner`, `status`, `model`, `slice`, `compute_target`, `run_counts` (theo `RunStatus`), `progress` (`images_done`, `images_total`), `created_at`, `finished_at` |
| `ExperimentDetail` | `ExperimentSummary` + `config`, `config_sha256`, `protocol` (`id`, `name`, `status`), `limit`, `processing_seconds_used`, `queue_position`, `cloned_from`, `clean_metrics` |
| `RunView` | `RunResult` + `attack_spec` (tên, đơn vị tham số chính) |
| `FailureCaseView` | `FailureCaseRecord` + URL tạm thời cho từng artifact, `urls_expire_at`, `display_mode` (`normal` / `hidden_unanonymized` / `dev_unblurred`) |
| `ComputeTargetPublic` | `id`, `name`, `kind`, `gpu_model`, `online`, `queue_length`, `default_time_limit_s`, `max_time_limit_s` |
| `ModelSummary`, `DatasetSummary`, `SliceSummary`, `ClassMappingSummary`, `ProtocolSummary` | Trường cần cho wizard (tên, hash, số ảnh, class, trạng thái) |
| `ErrorCode` (bổ sung) | `not_supported_yet`, `queue_limit_reached` |

### Thay đổi DB

| Bảng | Thay đổi |
|---|---|
| `compute_targets` | Thêm `max_time_limit_s` |
| `experiments` | Thêm `name`, `cloned_from`, `finished_at` |
| `email_outbox` | Bảng mới: `id`, `to`, `subject`, `body_html`, `body_text`, `status` (`pending` / `sent` / `failed`), `attempts`, `last_error`, `created_at`, `sent_at` |

### Dùng lại từ Phase 3 (replan)
- `POST /experiments` dùng lại service `experiments.submit` của Phase 3: `inference_params` mặc định (`DEFAULT_INFERENCE_PARAMS`) và `failure_cases_per_run = 20` lưu ở bảng `experiments` (không nằm trong `ExperimentConfig`); audit dùng action đã có `experiment.submit` / `experiment.cancel` (không phải `experiment.created`).
- Lỗi 422 có đường dẫn trường: `ErrorResponse` hiện không có trường cho đường dẫn → Group 0 của Phase 5 cần thêm (ví dụ `error.fields`).

## Behaviour

### API đọc tài nguyên

| Endpoint | Permission |
|---|---|
| `GET /models`, `GET /models/{id}` | `model.read` |
| `GET /datasets`, `GET /dataset-versions/{id}` | `dataset.read` |
| `GET /slices?dataset_version=` | `dataset.read` |
| `GET /class-mappings?dataset_version=&model=` | `dataset.read` |
| `GET /attack-specs` (chỉ spec đang hoạt động) | `attack_catalog.read` |
| `GET /protocols` (trạng thái `active` và `dev`) | `protocol.read` |
| `GET /compute-targets` | `compute_target.read` |

Worker được coi là `online` nếu có heartbeat trong 60 giây gần nhất.

### API experiment

| Endpoint | Permission | Hành vi |
|---|---|---|
| `POST /experiments/estimate` | `experiment.create` | Kiểm tra cấu hình như khi tạo, trả `EstimateResponse`, không tạo gì |
| `POST /experiments` | `experiment.create` | Tạo experiment `queued`, lập danh sách run, ghi `audit_log` (`experiment.submit`) |
| `GET /experiments?owner=me\|all&status=&model=` | `experiment.read` | Phân trang theo cursor |
| `GET /experiments/{id}` | `experiment.read` | `ExperimentDetail` |
| `GET /experiments/{id}/runs` | `experiment.read` | Danh sách `RunView` |
| `GET /runs/{id}/manifest` | `experiment.read` | Nội dung `Manifest` |
| `GET /runs/{id}/failure-cases` | `experiment.read` | Danh sách `FailureCaseView` (chỉ thumbnail URL) |
| `GET /failure-cases/{id}` | `experiment.read` | `FailureCaseView` đầy đủ URL |
| `POST /experiments/{id}/cancel` | `experiment.cancel_own` | Chỉ chủ sở hữu; trạng thái `queued` hoặc `running`; ghi `audit_log` |
| `GET /experiments/{id}/clone` | `experiment.create` | Trả `ExperimentCreate` điền sẵn từ experiment cũ (spec đã cũ được cập nhật lên version hiện hành, kèm cảnh báo) |

### Kiểm tra khi tạo và ước lượng (lỗi `422` có đường dẫn trường)
- Ít nhất một attack; spec đang hoạt động và `spec_sha256` khớp version hiện hành.
- `mode = search` → `422 not_supported_yet`.
- Mỗi attack: các level nằm trong dải của spec, không trùng, tối đa 12 level; tổng số run của experiment tối đa 50.
- Slice thuộc dataset version của class mapping; mapping dành cho đúng model.
- Protocol có trạng thái `active` hoặc `dev`.
- Compute target tồn tại; phase này chỉ chấp nhận `kind = local`. Target offline vẫn tạo được (experiment chờ trong hàng đợi).
- `limit.kind = time` với máy local; `0 < limit.value ≤ max_time_limit_s`.
- Mỗi người dùng tối đa 3 experiment đang `queued` → vượt thì `409 queue_limit_reached`.
- Model không hỗ trợ gradient mà chọn attack cần gradient → cho phép tạo nhưng ước lượng đánh dấu run đó sẽ `skipped` (`incompatible`).

### Ước lượng
- `est_seconds` mỗi run = `images × sec_per_image × 1.2`, với `sec_per_image` lấy từ cost profile của (target, model, attack).
- Thiếu profile → giá trị null, liệt kê trong `missing_profiles`; vẫn tạo được (worker tự calibration).
- `exceeds_limit = true` khi tổng ước lượng lớn hơn giới hạn thời gian.
- `queue.ahead_seconds` = tổng ước lượng còn lại của các experiment đứng trước trong hàng đợi của target (bỏ qua phần không ước lượng được).

### Hiển thị ảnh và quyền riêng tư (tạm thời đến Phase 10)
- Ảnh được phục vụ bằng URL tạm thời (hết hạn 10 phút) do API cấp sau khi kiểm tra `experiment.read`. Presigned URL của Phase 3 ký cho `MINIO_PUBLIC_ENDPOINT` (`127.0.0.1:9000`), nên trình duyệt ở máy khác (điện thoại qua LAN) không tải được; Phase 5 phải chọn cách phục vụ ảnh (xem Open Questions).
- Dataset có `anonymized = false`:
  - mặc định: `display_mode = hidden_unanonymized`, không cấp URL ảnh; giao diện hiển thị khung giữ chỗ "Ảnh bị ẩn: dataset chưa được làm mờ" và vẫn vẽ box trên nền trống;
  - khi server bật `DEV_ALLOW_UNBLURRED=true`: `display_mode = dev_unblurred`, cấp URL và giao diện hiển thị dải cảnh báo "Chưa làm mờ – chỉ dùng cho phát triển".
- Không bật `DEV_ALLOW_UNBLURRED` ở môi trường demo hoặc bảo vệ.

### Email
- Khi experiment chuyển sang `completed` hoặc `cancelled`: thêm một email vào `email_outbox` gửi cho chủ sở hữu, gồm tên experiment, trạng thái tổng hợp (ví dụ "18/20 hoàn thành, 1 lỗi, 1 dừng do giới hạn"), link tới trang chi tiết.
- Tác vụ nền trong API gửi email từ outbox, thử lại tối đa 5 lần với backoff; lỗi cuối cùng ghi vào `last_error`.
- Môi trường phát triển dùng Mailpit trong Docker Compose.
- Email không chứa ảnh hay dữ liệu dataset.

### Frontend: wizard (`/experiments/new`)

| Bước | Nội dung |
|---|---|
| 1. Protocol | Danh sách protocol; `dev-open` có nhãn "Dev – không gửi duyệt được" |
| 2. Model | Thẻ model: tên, kiến trúc, số class, nhãn "Không hỗ trợ gradient" nếu có |
| 3. Dataset và slice | Chọn dataset version, slice (số ảnh, seed); class mapping tự chọn nếu chỉ có một, báo lỗi rõ ràng nếu không có |
| 4. Attack | Catalog nhóm theo loại; chọn attack → chỉnh các level bằng chip, có preset (ví dụ eps 2, 4, 8, 16); chế độ "Tự tìm ngưỡng" hiển thị "Sắp có" |
| 5. Máy chạy và giới hạn | Thẻ compute target: tên, GPU, trạng thái online, số job đang chờ, thời gian ước lượng, nhãn "Miễn phí – máy local"; ô giới hạn thời gian (mặc định theo target) |
| 6. Xác nhận | Tóm tắt toàn bộ cấu hình, ước lượng từng run và tổng, vị trí hàng đợi, cảnh báo `exceeds_limit` và `missing_profiles`; nút "Chạy experiment" mở hộp xác nhận |

- Ước lượng được gọi lại (debounce 500 ms) mỗi khi cấu hình thay đổi từ bước 4 trở đi.
- Điện thoại: mỗi bước một màn hình; thanh dưới cố định hiển thị thời gian ước lượng và nút "Tiếp". Desktop: cột tóm tắt bên phải luôn hiển thị.
- Trạng thái wizard giữ qua lần tải lại trang (sessionStorage), xóa sau khi tạo thành công.
- "Nhân bản" từ trang chi tiết mở wizard đã điền sẵn tới bước 6.
- Lỗi `422` từ server hiển thị tại đúng bước và đúng trường.

### Frontend: danh sách và chi tiết
- `/experiments`: bộ lọc (của tôi / tất cả, trạng thái, model); bảng trên desktop, thẻ trên điện thoại (tên, `StatusBadge`, thanh tiến độ, thời gian).
- `/experiments/:id` gồm các tab:
  - **Tổng quan:** trạng thái tổng hợp dạng câu, thanh tiến độ, vị trí hàng đợi khi `queued`, bảng run (attack, level, trạng thái, lý do, tiến độ, thời gian), nút Hủy (chỉ chủ sở hữu, khi `queued`/`running`) và Nhân bản.
  - **Kết quả:** biểu đồ mAP@0.5 theo level cho từng attack, có đường ngang mAP sạch; biểu đồ tỷ lệ tấn công thành công; bảng số liệu tương ứng (thay thế cho biểu đồ về khả năng tiếp cận). Run có `metrics.partial` được đánh dấu. Trên điện thoại hiển thị từng biểu đồ một, chuyển bằng tab.
  - **Failure case:** lưới thumbnail theo run, sắp theo `severity_score`, có watermark "BẢN NHÁP – CHƯA DUYỆT".
  - **Chi phí:** thời gian xử lý đã dùng so với giới hạn, thời gian từng run.
  - **Tái lập:** với mỗi run: fingerprint (rút gọn giữa, có nút copy), git commit, cảnh báo nếu `git_dirty`, phiên bản thư viện, Docker image, môi trường; nút tải `manifest.json`.
- Polling 2 giây khi experiment `queued` hoặc `running`; dừng khi trạng thái cuối; tạm dừng khi tab bị ẩn.

### Frontend: trình xem failure case (`/failure-cases/:id`)
- Desktop: hai ảnh cạnh nhau với zoom đồng bộ. Điện thoại: slider kéo giữa ảnh sạch và ảnh sau tấn công, pinch-zoom, vuốt để chuyển case.
- Bật tắt từng lớp: ground truth, dự đoán trên ảnh sạch, dự đoán sau tấn công, ignore region. Object bị mất tô đỏ.
- Hiển thị ảnh nhiễu khuếch đại.
- Box vẽ trên canvas, scale theo `devicePixelRatio`; nhãn box ẩn trên màn hình nhỏ, chạm vào box để hiện.
- Watermark "BẢN NHÁP – CHƯA DUYỆT" luôn hiển thị trong phase này.
- Component được thiết kế để Phase 8 thêm form verdict và phím tắt mà không viết lại.

### Trang chủ
- Khối engineer: experiment đang chạy của tôi (thanh tiến độ), 5 experiment kết thúc gần nhất, nút "Tạo experiment".

## Decisions

- **Giữ bước chọn protocol dù chỉ có `dev-open`.** *Lý do:* Phase 8 chỉ cần thêm protocol thật, không phải đổi cấu trúc wizard.
- **Giới hạn 3 experiment đang chờ cho mỗi người dùng.** *Lý do:* cách đơn giản nhất để tránh một người chiếm hàng đợi của GPU dùng chung, khi chưa có hàng đợi công bằng.
- **Ẩn ảnh của dataset chưa làm mờ theo mặc định.** *Lý do:* `mission.md` nguyên tắc 9; tính năng làm mờ ở Phase 10, nên cho đến lúc đó cách an toàn là không hiển thị, và chỉ cho xem trong môi trường phát triển có cảnh báo rõ.
- **Email qua outbox.** *Lý do:* experiment kết thúc không phụ thuộc vào việc SMTP có hoạt động lúc đó; email được thử lại và lỗi được ghi lại.
- **Trình xem failure case là component dùng chung với Phase 8.** *Lý do:* đây là màn hình khó nhất của sản phẩm; làm một lần, mở rộng sau.
- **Bảng số liệu đi kèm mỗi biểu đồ.** *Lý do:* khả năng tiếp cận và để kỹ sư đọc được giá trị chính xác.

## Context

- `mission.md` nguyên tắc 5 (chi phí biết trước), 6 (trạng thái rõ), 9 (quyền riêng tư).
- `tech-stack.md` mục 4.2 (giới hạn), 5, 5.1 (frontend, responsive).
- Phase 3: service experiment, ước lượng, hàng đợi, trạng thái, artifact trong MinIO.
- Phase 4: phiên, permission, khung điều hướng, form, hộp xác nhận. Cụ thể (replan sau Phase 4):
  - Route mới khai quyền bằng `**guard(p)`; app từ chối khởi động nếu route cần phiên thiếu khai báo. Thứ tự kiểm tra: `401` → `403` → `422` → route.
  - Phân trang dùng `backend/app/api/pagination.py` (keyset `(created_at, id)`, cursor mờ) và schema `Page[T]` có tên cụ thể (ví dụ `ExperimentPage`); giao diện dùng "Tải thêm".
  - `422` do body sai schema là `validation_error`, `422` nghiệp vụ là `invalid_request`; mã mới (`not_supported_yet`, `queue_limit_reached`) cần thông điệp trong `ERROR_MESSAGES` của frontend (`tsc` báo nếu thiếu).
  - Audit action theo quy ước `entity.verb`.

## Open Questions

- [ ] Ảnh failure case cho điện thoại: API proxy ảnh qua `/api`, hay presigned URL với `MINIO_PUBLIC_ENDPOINT` là địa chỉ LAN?

- [ ] Có nên đưa tính năng làm mờ lên sớm (trước Phase 8) để report không bị thiếu ảnh không.
- [ ] Giới hạn 3 experiment đang chờ mỗi người có phù hợp không.
