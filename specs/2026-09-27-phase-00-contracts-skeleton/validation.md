# Validation: Phase 0 — Contract và khung dự án

> Test trong `tests/acceptance/phase_00/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng.

## Automated Tests

### Công cụ và build
- [x] `make lint` pass (ruff, eslint).
- [x] `make typecheck` pass (mypy, `tsc --noEmit`).
- [x] `make test` pass (pytest, vitest).
- [x] `pnpm --dir frontend build` thành công và bản build không chứa route `/dev/contracts`.

### Contract — `tests/acceptance/phase_00/test_contracts.py`
- [x] Mỗi enum trong `advertest_contracts.enums` có đúng tập giá trị như bảng trong `requirements.md` (so sánh tập, không thừa, không thiếu).
- [x] Mọi file trong `contracts/mocks/` validate được bằng model Pydantic tương ứng.
- [x] Mock `RunResult` phủ đủ mọi giá trị `RunStatus`; mock `SearchResult` phủ đủ mọi giá trị `SearchStatus`.
- [x] `RunResult` có trạng thái `failed`, `skipped`, `stopped_limit`, `cancelled` mà thiếu `status_reason` → validation lỗi.
- [x] `AttackConfig` với `mode = grid` mà thiếu `grid` (hoặc `search` mà thiếu `search`) → validation lỗi.
- [x] `canonical_json()` cho cùng kết quả với hai dict có thứ tự key khác nhau.
- [x] `compute_fingerprint()` **không đổi** khi chỉ thay đổi `environment` của manifest, và **đổi** khi thay bất kỳ trường nào trong `fingerprint_inputs`.
- [x] Mọi spec trong `contracts/seeds/attack_specs.json` validate được và `spec_sha256` khớp với giá trị tính lại.
- [x] `make contracts` chạy lại không tạo ra thay đổi nào so với bản đã commit (`git diff --exit-code`).

### Database — `tests/acceptance/phase_00/test_database.py`
(Chạy với Postgres thật trong CI.)
- [x] `alembic upgrade head` rồi `alembic downgrade base` rồi `upgrade head` lại chạy không lỗi.
- [x] Toàn bộ bảng trong `requirements.md` tồn tại sau migration.
- [x] Kết nối bằng `advertest_app`: `INSERT` vào `audit_log` thành công.
- [x] Kết nối bằng `advertest_app`: `UPDATE`, `DELETE`, `TRUNCATE` trên `audit_log` bị từ chối.
- [x] Kết nối bằng `advertest_app`: `UPDATE` hoặc `DELETE` trên `case_verdicts`, `reviews`, `reports`, `ledger_entries` bị từ chối.
- [x] Kết nối bằng `advertest_app`: `DELETE` trên `runs` bị từ chối; `UPDATE runs SET archived = true` thành công.
- [x] Chèn hai run cùng `(experiment_id, fingerprint)` → vi phạm unique constraint.
- [x] Chèn `reviews` có `reviewer_id` trùng `experiments.created_by` → trigger từ chối.
- [x] Seed tạo đúng số attack spec, compute target `local-dev` có `billing_mode = none`, và một admin ở trạng thái `active`.

### API — `tests/acceptance/phase_00/test_api.py`
- [x] `GET /health` trả `200`, có trường phiên bản, git commit, trạng thái Postgres và MinIO đều ok.
- [x] Một endpoint mẫu trong mỗi nhóm trả `501` với body lỗi đúng định dạng thống nhất.
- [x] `contracts/openapi.json` chứa đủ các nhóm endpoint công khai và 6 endpoint nội bộ của worker trong `requirements.md`.
- [x] Nhóm `/internal/worker` khai báo security scheme bearer; các nhóm còn lại khai báo cookie.

### Frontend
- [x] Test `StatusBadge`: mọi giá trị của `RunStatus`, `ExperimentStatus`, `SearchStatus` có nhãn, màu và icon riêng; không giá trị nào rơi vào nhánh mặc định.
- [x] Type trong `frontend/src/contracts/` được sinh ra, không có chỉnh sửa tay (kiểm tra qua `git diff --exit-code` sau `make contracts`).

### Fixture
- [x] `make fixtures` tải đủ file và mọi sha256 khớp với `tests/fixtures/checksums.json`.
- [x] `tests/fixtures/manifest.json` validate được theo định dạng manifest nội bộ.
- [x] Smoke test: YOLOv8n chạy trên 5 ảnh bằng CPU trong dưới 60 giây; box trả về đúng định dạng xyxy, nằm trong khung 640×640.

## Manual Checks

- [x] `make up` trên máy phát triển: cả 4 service healthy.
- [x] Mở MinIO console, thấy đủ 4 bucket `artifacts`, `reports`, `datasets`, `models`.
- [x] Mở `/docs` của API, duyệt qua các nhóm endpoint và schema; tên trường nhất quán với `requirements.md`.
- [x] Chạy frontend với `VITE_USE_MOCKS=true`, mở `/dev/contracts`, thấy danh sách run với badge trạng thái đúng.
- [ ] Mở `/dev/contracts` ở viewport 375px: không có thanh cuộn ngang.
- [x] CI trên GitHub chạy xanh cho cả 4 job.
- [ ] Đọc lại toàn bộ `contracts/` một lượt, đối chiếu với `mission.md` mục 4 và `tech-stack.md` mục 4.3, 4.4.

## Definition of Done

- [x] Toàn bộ mục Automated Tests pass trên CI.
- [ ] Toàn bộ Manual Checks đã thực hiện.
- [ ] Người duyệt đã chấp nhận từng file trong `contracts/` và migration.
- [x] `CLAUDE.md` đã có và đã được thử với ít nhất một agent (agent đọc được và làm theo quy tắc thư mục).
- [x] `tech-stack.md` đã ghi phiên bản thư viện được pin.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 0 được đánh dấu hoàn thành.
