# Requirements: Phase 0 — Contract và khung dự án

## Scope

Tạo nền tảng chung để các agent (ml-core, attack, backend, frontend) làm song song từ Phase 1 trở đi mà không phải đoán định dạng dữ liệu của nhau. Kết quả của phase gồm:

1. Repo monorepo với cấu trúc thư mục, công cụ và lệnh chạy thống nhất.
2. **Contract** là nguồn sự thật duy nhất cho dữ liệu trao đổi giữa các phần: enum, schema, OpenAPI.
3. DB schema đầu tiên (migration) cho toàn bộ thực thể đã thiết kế, kể cả phân quyền cấp DB cho `audit_log`.
4. Backend API khung: đủ endpoint và schema trong OpenAPI, phần xử lý trả `501`.
5. Frontend khung: build được, dùng type sinh tự động từ contract, đọc được mock data.
6. Fixture test chạy trên CPU (ảnh nhỏ + model nhỏ).
7. Docker Compose, CI và file hướng dẫn agent.

Phase này do người duyệt viết hoặc duyệt từng dòng. Agent có thể hỗ trợ soạn, nhưng mọi file trong `contracts/` và migration phải được người duyệt chấp nhận trước khi merge.

## Out of Scope

- Logic nghiệp vụ thật của bất kỳ endpoint nào (chỉ trả `501 Not Implemented`).
- Wrapper model cho ART, attack, metric (Phase 1–2).
- Worker thật (Phase 3). Phase 0 chỉ định nghĩa API nội bộ của worker trong OpenAPI.
- Xác thực thật (Phase 4). Phase 0 chỉ định nghĩa schema và endpoint.
- Giao diện thật. Frontend chỉ có trang khung hiển thị mock để chứng minh type và mock hoạt động.
- Converter dataset, upload dataset.
- Tailscale, máy thuê.

## Data / Contracts

### Enum dùng chung

| Enum | Giá trị |
|---|---|
| `Role` | `engineer`, `reviewer`, `admin` |
| `UserStatus` | `pending`, `active`, `rejected`, `disabled` |
| `RunStatus` | `queued`, `running`, `completed`, `failed`, `skipped`, `stopped_limit`, `cancelled` |
| `ExperimentStatus` | `draft`, `queued`, `running`, `completed`, `submitted_for_review`, `in_review`, `approved`, `changes_requested`, `rejected`, `cancelled` |
| `SearchStatus` | `found`, `not_reached`, `below_min`, `stopped_limit`, `non_monotonic` |
| `StopReason` | `budget`, `time` |
| `SkipReason` | `cached`, `incompatible` |
| `ComputeKind` | `local`, `rented` |
| `BillingMode` | `none`, `hourly` |
| `LimitKind` | `budget`, `time` |
| `AttackKind` | `attack`, `corruption`, `occlusion` |
| `AttackAccess` | `white_box`, `black_box` |
| `RunMode` | `grid`, `search` |
| `ThresholdKind` | `relative_drop`, `absolute_drop`, `attack_success_rate` |
| `ReviewDecision` | `approve`, `changes_requested`, `reject` |
| `CaseSeverity` | `critical`, `major`, `minor`, `acceptable` |

### Schema contract

Mỗi schema có trường `schema_version` (bắt đầu từ `1`). Mô tả dưới đây là bắt buộc; kiểu chi tiết do file Pydantic quyết định.

**`AttackSpec`** — định nghĩa một attack trong catalog.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | uuid | ✓ | uuid5 của `spec_sha256` (namespace trong `advertest_contracts.ids`) |
| `name` | string | ✓ | Ví dụ `pgd_linf` |
| `version` | int | ✓ | Tăng khi đổi bất kỳ trường nào |
| `kind` | `AttackKind` | ✓ | |
| `access` | `AttackAccess` | ✓ | Hiện chỉ `white_box` |
| `art_class` | string | | Null với corruption/occlusion |
| `primary_param` | object | ✓ | `name`, `type` (`continuous`/`discrete`), `min`, `max`, `values` (nếu rời rạc), `unit` |
| `fixed_params` | object | ✓ | Ví dụ `{"max_iter": 10, "eps_step_ratio": 0.25}` |
| `cost_model` | object | ✓ | `passes_per_image` (số lần forward+backward) hoặc `cpu_only: true` |
| `requires_gradients` | bool | ✓ | |
| `spec_sha256` | string | ✓ | Hash của toàn bộ trường trừ `id` và chính nó |

**`AttackConfig`** — một attack trong experiment.

| Field | Type | Required | Notes |
|---|---|---|---|
| `attack_spec_id` | uuid | ✓ | |
| `spec_sha256` | string | ✓ | Chốt đúng version spec |
| `mode` | `RunMode` | ✓ | |
| `grid` | object | nếu `grid` | `levels: number[]` |
| `search` | object | nếu `search` | `threshold_kind`, `threshold`, `lo`, `hi`, `tol`, `coarse_n`, `subset_size`, `class_filter` (tùy chọn) |
| `seed` | int | ✓ | |

**`ExperimentConfig`**

| Field | Type | Required | Notes |
|---|---|---|---|
| `protocol_id` | uuid | ✓ | |
| `model_version_id` | uuid | ✓ | |
| `slice_id` | uuid | ✓ | |
| `class_mapping_id` | uuid | ✓ | |
| `compute_target_id` | uuid | ✓ | |
| `attacks` | `AttackConfig[]` | ✓ | Ít nhất 1 |
| `limit` | object | ✓ | `kind: LimitKind`, `value` (tiền hoặc giây; số thập phân, trong JSON là chuỗi) |

**`RunResult`**

| Field | Type | Required | Notes |
|---|---|---|---|
| `run_id`, `experiment_id` | uuid | ✓ | |
| `fingerprint` | string | ✓ | |
| `attack_spec_id` | uuid | ✓ | |
| `level` | number | ✓ | Giá trị tham số chính |
| `status` | `RunStatus` | ✓ | |
| `status_reason` | object | nếu trạng thái bất thường | `code` (`StopReason` với `stopped_limit`, `SkipReason` với `skipped`, `error` với `failed`, `cancelled` với `cancelled`), `message` |
| `progress` | object | ✓ | `images_done`, `images_total` |
| `metrics` | object | nếu có dữ liệu; bắt buộc khi `completed` | `clean` và `attacked` (mỗi cái gồm `map50`, `map50_95`), `relative_drop`, `absolute_drop`, `attack_success_rate`, `per_class` (tùy chọn) |
| `gpu_seconds` | number | ✓ | |
| `cost` | object | | `amount` (số thập phân, trong JSON là chuỗi), `currency` (mã ISO 4217); null với máy local |
| `failure_case_ids` | uuid[] | ✓ | Có thể rỗng |
| `manifest_uri` | string | nếu đã chạy; bắt buộc khi `completed` | |

**`Manifest`** — ghi kèm mỗi run trong MinIO.

| Field | Type | Required | Notes |
|---|---|---|---|
| `run_id` | uuid | ✓ | |
| `fingerprint` | string | ✓ | sha256 của `fingerprint_inputs` chuẩn hóa |
| `fingerprint_inputs` | object | ✓ | `config_sha256`, `weights_sha256`, `dataset_version_sha256`, `slice_id`, `slice_sha256`, `attack_spec_sha256`, `params`, `seed`, `git_commit`, `lib_versions` (`torch`, `art`, `ultralytics`, `torchmetrics`, `numpy`), `docker_image_digest` |
| `environment` | object | ✓ | `compute_target_id`, `gpu_model`, `cuda_version`, `driver_version`: luôn có mặt, được phép null (chạy bằng CLI, chạy trên CPU). **Không** thuộc fingerprint |
| `created_at` | datetime (UTC) | ✓ | Múi giờ khác UTC bị từ chối. Schema tự kiểm tra `fingerprint` = sha256 của `fingerprint_inputs` |

**`SearchResult`**

| Field | Type | Required | Notes |
|---|---|---|---|
| `experiment_id`, `attack_spec_id` | uuid | ✓ | |
| `status` | `SearchStatus` | ✓ | |
| `threshold_kind`, `threshold` | | ✓ | Chép từ config |
| `breaking_point` | number | nếu `found` | |
| `bracket` | `[number, number]` | ✓ | Khoảng hiện tại, kể cả khi dừng giữa chừng |
| `confidence_interval` | `[number, number]` | | Null nếu chưa tính bootstrap |
| `near_threshold` | bool | ✓ | Khoảng tin cậy bao trùm ngưỡng |
| `trajectory` | list | ✓ | Mỗi phần tử: `order`, `level`, `scope` (`subset`/`full`), `drop`, `run_id` |

**`ProtocolBody`**

| Field | Type | Required | Notes |
|---|---|---|---|
| `required_attacks` | list | ✓ | Mỗi phần tử: `attack_spec_id`, `spec_sha256`, `mode`, dải hoặc cấu hình tìm kiếm tối thiểu |
| `min_slice_size` | int | ✓ | |
| `pass_criteria` | list | ✓ | Mỗi phần tử: `threshold_kind`, `threshold`, `class_filter` (tùy chọn) |
| `review_severity_threshold` | `CaseSeverity` | ✓ | Case từ mức này trở lên bắt buộc có verdict |

### DB schema (bảng và cột chính)

| Bảng | Cột chính |
|---|---|
| `users` | `id`, `email` (unique), `full_name`, `organization`, `password_hash`, `status`, `requested_role`, `request_reason`, `approved_by`, `approved_at`, `created_at` |
| `user_roles` | `user_id`, `role` (khóa chính kép) |
| `compute_targets` | `id`, `name`, `kind`, `gpu_model`, `vram_gb`, `billing_mode`, `price_per_hour`, `currency`, `token_hash`, `default_time_limit_s`, `last_heartbeat_at` |
| `cost_profiles` | `id`, `compute_target_id`, `model_version_id`, `attack_spec_id`, `sec_per_image`, `peak_vram_mb`, `batch_size`, `measured_at` |
| `models` | `id`, `name`, `created_by` |
| `model_versions` | `id`, `model_id`, `weights_sha256` (unique), `weights_uri`, `framework`, `class_names`, `input_size`, `supports_gradients`, `created_at` |
| `datasets` | `id`, `name`, `anonymized`, `created_by` |
| `dataset_versions` | `id`, `dataset_id`, `manifest_sha256` (unique), `manifest_uri`, `num_images`, `class_names`, `created_at` |
| `class_mappings` | `id`, `dataset_version_id`, `model_version_id`, `mapping`, `mapping_sha256` |
| `slices` | `id`, `dataset_version_id`, `name`, `filter`, `seed`, `image_ids`, `image_ids_sha256` |
| `attack_specs` | `id`, `name`, `version`, `kind`, `access`, `spec`, `spec_sha256` (unique), `is_active` |
| `protocols` | `id`, `name`, `version`, `body`, `body_sha256`, `status` (`active`/`retired`), `created_by` |
| `experiments` | `id`, `created_by`, `protocol_id`, `model_version_id`, `slice_id`, `class_mapping_id`, `compute_target_id`, `config`, `config_sha256`, `status`, `limit_kind`, `limit_value`, `locked_at`, `submitted_at`, `lease_expires_at`, `checkpoint` |
| `runs` | `id`, `experiment_id`, `attack_spec_id`, `level`, `params`, `seed`, `fingerprint`, `status`, `status_reason`, `images_done`, `images_total`, `metrics`, `gpu_seconds`, `cost_amount`, `manifest_uri`, `archived`, `started_at`, `finished_at` |
| `search_results` | `id`, `experiment_id`, `attack_spec_id`, `result` (theo schema `SearchResult`) |
| `failure_cases` | `id`, `run_id`, `image_id`, `severity_score`, `artifact_uri`, `thumbnail_uri`, `details` |
| `case_verdicts` | `id`, `failure_case_id`, `reviewer_id`, `version`, `severity`, `verdict`, `mitigation`, `created_at` |
| `reviews` | `id`, `experiment_id`, `reviewer_id`, `version`, `decision`, `conclusion`, `mitigation`, `created_at` |
| `reports` | `id`, `experiment_id`, `exported_by`, `pdf_uri`, `json_uri`, `sha256` (unique), `created_at` |
| `budgets` | `id`, `total_amount`, `currency`, `updated_by`, `updated_at` |
| `quotas` | `user_id`, `budget_amount`, `gpu_hours` |
| `ledger_entries` | `id`, `experiment_id`, `user_id`, `kind` (`reserve`/`settle`/`release`), `amount`, `currency`, `created_at` |
| `audit_log` | `id`, `actor_id`, `action`, `entity_type`, `entity_id`, `before`, `after`, `created_at` |

Ràng buộc bắt buộc ở cấp DB:
- Hai DB role: `advertest_owner` (chạy migration, sở hữu bảng) và `advertest_app` (ứng dụng dùng khi chạy).
- `advertest_app` **không có** quyền `UPDATE`, `DELETE`, `TRUNCATE` trên `audit_log`, `case_verdicts`, `reviews`, `reports`, `ledger_entries`.
- `runs` không có quyền `DELETE` với `advertest_app` (chỉ đặt `archived = true`).
- Unique `(experiment_id, fingerprint)` trên `runs`.
- Không cho phép có dòng trong `reviews` mà `reviewer_id` trùng `experiments.created_by` (kiểm tra bằng trigger).

### API (OpenAPI)

Nhóm endpoint công khai cho người dùng: `/auth`, `/users`, `/models`, `/datasets`, `/slices`, `/attack-specs`, `/protocols`, `/experiments`, `/runs`, `/failure-cases`, `/reviews`, `/reports`, `/compute-targets`, `/budget`, `/audit-log`, `/verify/{report_id}`, `/health`.

Nhóm endpoint nội bộ cho worker (tiền tố `/internal/worker`, xác thực bằng token của compute target):
- `POST /lease`: nhận experiment kế tiếp dành cho máy này.
- `POST /heartbeat`
- `POST /runs/{id}/progress`: cập nhật tiến độ và checkpoint.
- `POST /runs/{id}/artifact-url`: xin presigned URL để upload.
- `POST /runs/{id}/complete`: gửi `RunResult` cuối cùng.
- `POST /experiments/{id}/search-result`: gửi `SearchResult`.

Mọi endpoint (trừ `/health`) trả `501` trong Phase 0, nhưng request và response model phải đầy đủ trong OpenAPI.

## Behaviour

- `GET /health` trả `200` kèm phiên bản API, git commit và trạng thái kết nối Postgres, MinIO.
- `make up` khởi động Postgres, MinIO, API; migration chạy tự động bằng role `advertest_owner`.
- `make check` chạy toàn bộ lint, type check, test và kiểm tra contract.
- Sinh lại artifact từ contract (`make contracts`) không làm thay đổi file đã commit nếu contract không đổi.

## Decisions

- **Nguồn sự thật của contract là Pydantic** trong `contracts/python/`. JSON Schema và TypeScript type được **sinh ra** từ đó, không viết tay. *Lý do:* một nơi định nghĩa, ba nơi sử dụng (Python, JSON, TS) mà không lệch nhau.
- **CI kiểm tra file sinh ra luôn khớp với nguồn.** *Lý do:* chặn trường hợp sửa tay file sinh ra hoặc quên sinh lại.
- **Endpoint trả `501` nhưng OpenAPI đầy đủ.** *Lý do:* frontend sinh type và làm việc với mock ngay; backend điền logic dần ở các phase sau mà không đổi hình dạng API.
- **Ràng buộc chống gian lận đặt ở DB ngay từ Phase 0.** *Lý do:* nguyên tắc 3 trong `mission.md`; đặt ở DB thì kể cả code có bug cũng không vi phạm được.
- **Quản lý package:** `uv` cho Python (có lockfile, nhanh), `pnpm` cho frontend. *Lý do:* lockfile bắt buộc để tái lập môi trường.
- **Monorepo, một Makefile ở gốc.** *Lý do:* agent và CI dùng chung một bộ lệnh.
- **Fixture không commit vào repo**, được tải bằng script có kiểm tra sha256 và cache trong CI. Gồm 5 ảnh KITTI (split training) kèm file label gốc, cùng weights YOLOv8n. Tổng các ảnh phải có đủ `Car`, `Van`, `Truck`, `Pedestrian`, `Cyclist`, `DontCare`, và ít nhất một object dưới mức Moderate. Giấy phép CC BY-NC-SA 3.0, ghi nguồn trong `tests/fixtures/LICENSE.md`. *Lý do:* tránh phình repo và vấn đề giấy phép dữ liệu; checksum đảm bảo mọi nơi dùng đúng cùng một fixture.
- **Mock data nằm trong `contracts/mocks/`** và được validate theo schema trong CI. *Lý do:* mock sai schema sẽ khiến frontend làm theo dữ liệu không tồn tại.

## Context

- `mission.md` mục 4: nguyên tắc 1, 3, 4 phải có dấu vết ngay trong schema và DB của phase này.
- `tech-stack.md`: mục 2.1 (quy ước dữ liệu), 3.1 (interface `Perturbation`), 4 (backend), 4.3 (enum), 4.4 (fingerprint), 8 (cấu trúc repo), 9 (luật cho agent).
- Phase này là nền của mọi phase sau; thay đổi contract ở phase sau phải đi qua cập nhật spec và `schema_version`.

## Open Questions

- [x] Nguồn 5 ảnh fixture: KITTI training + label gốc, CC BY-NC-SA 3.0 (chốt ở kickoff Phase 1).
- [ ] Đơn vị tiền tệ mặc định cho ngân sách (VND hay USD).
