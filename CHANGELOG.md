# Changelog

Ghi theo group và phase. Mỗi mục ghi điều đã thêm, đã đổi, thay đổi contract, quyết định (kèm file spec đã ghi nhận), số liệu đo được và việc tồn đọng.

---

## Phase 0 — Contract và khung dự án

**Trạng thái:** đang làm. Group 1, 2, 3, 4, 5, 7, 8 đã merge; Group 9 đang chờ review; Group 6 xong một phần; Group 10 chưa làm.

Ghi chú chung: các group của người duyệt (1, 2, 8, 9) do agent soạn thay theo cho phép của người dùng; mọi nhánh được review trước khi merge, nhưng review do chính agent đã viết code thực hiện nên không phải review độc lập.

### Phase 0 — Group 1 (người duyệt) — 2026-09-27
#### Thêm
- Cấu trúc thư mục theo `tech-stack.md` mục 8; `.gitignore`.
- Python workspace bằng uv: một `pyproject.toml` gốc, 4 package `advertest_contracts`, `ml_core`, `attacks`, `backend`; `uv.lock`.
- Cấu hình ruff và mypy (strict cho `contracts/` và `backend/`), pytest.
- Frontend khung: Vite, React, TypeScript strict, Tailwind, shadcn/ui, TanStack Query, React Router, ESLint, Prettier.
- `Makefile` với các lệnh chung.
#### Thay đổi
- Bỏ theo dõi `.env` trong git (file đã từng được commit và push lên `origin`).
#### Quyết định
- torch chọn biến thể bằng extra `cpu`/`cuda` của uv trong cùng một lockfile (`tech-stack.md` mục 11).
- Target `make` của phần chưa có báo "Chưa có (Group N)" và thoát lỗi; `make check` coi "chưa có test" là pass (ghi trong `Makefile`).
#### Tồn đọng
- Khóa `AI_LOG_API_KEY` vẫn còn trong lịch sử git: cần đổi khóa.

### Phase 0 — Group 2 (người duyệt) — 2026-09-27
#### Thêm
- 16 enum, 7 schema Pydantic (`AttackSpec`, `AttackConfig`, `ExperimentConfig`, `RunResult`, `Manifest`, `SearchResult`, `ProtocolBody`), interface `Perturbation`.
- `canonical_json` theo RFC 8785, `sha256_of`, `compute_fingerprint`, `content_id` (uuid5, namespace cố định trong `advertest_contracts.ids`).
- Mock cho mọi schema (đủ mọi `RunStatus`, `SearchStatus`); seed catalog `fgsm`, `pgd_linf`, `pgd_l2`.
- `scripts/gen_contracts.py`: JSON Schema, TypeScript type (openapi-typescript); `make contracts-check`.
#### Contract
- Schema mới, mọi schema bắt đầu ở `schema_version = 1`. `status_reason.code` có thêm `cancelled`.
#### Quyết định
- `canonical_json` theo RFC 8785; seed chỉ gồm attack của Phase 2; `openapi-typescript`; mã `cancelled` (`requirements.md`, `plan.md` Phase 0, `tech-stack.md`).
- Sau review: `Environment` được phép null; tiền là `Decimal` (chuỗi trong JSON); các ràng buộc schema bổ sung; Phase 1 dùng `content_id` của contract (`requirements.md` Phase 0, `tech-stack.md` mục 4.1, `plan.md` Phase 1).
#### Số liệu đo được
- `canonical_json` khớp `JSON.stringify` của Node trên 60.014 số.

### Phase 1 — kickoff (spec) — 2026-09-27
#### Thay đổi
- Fixture là 5 ảnh KITTI kèm label; ID của slice/mapping sinh từ hash toàn bộ nội dung (`slice_sha256`); CLI dùng Typer, lệnh đặt theo thư mục của từng agent; ground truth dưới mức Moderate của KITTI thành ignore region (`requirements.md`, `plan.md`, `validation.md` Phase 1; `tech-stack.md`).

### Phase 0 — Group 3 (backend) — 2026-09-27
#### Thêm
- SQLAlchemy 2, Alembic, model ORM và migration `0001` cho 23 bảng; enum Postgres khớp contract.
- Role `advertest_owner`/`advertest_app` tạo bằng `docker/postgres/init/01-roles.sh`; migration cấp quyền (bảng chỉ-thêm chỉ có `SELECT`, `INSERT`; `runs` không có `DELETE`).
- Trigger chặn tự review; unique `(experiment_id, fingerprint)`; CHECK trạng thái bất thường phải có lý do.
- Script seed (`backend/admin_cli/seed.py`); `make test-db`.
#### Quyết định
- psycopg 3, argon2-cffi, Postgres 17; Alembic đọc `MIGRATION_DATABASE_URL`, ứng dụng đọc `DATABASE_URL`; mỗi migration tự `GRANT` (`tech-stack.md` mục 4, 4.1, 11; `requirements.md` Phase 0; `CLAUDE.md`).
#### Tồn đọng
- Phase 3: luật "chỉ worker ghi kết quả" phải chặn ở API (DB vẫn cho `advertest_app` sửa `runs`).
- Phase 4: chuyển email về chữ thường khi đăng ký.

### Phase 0 — Group 4 (backend) — 2026-09-27
#### Thêm
- App FastAPI: 16 nhóm endpoint công khai (mỗi nhóm một endpoint đại diện), 6 endpoint worker, `/health`; security scheme cookie `advertest_session` và bearer cho worker.
- Body lỗi thống nhất `ErrorResponse` cho `501`; `contracts/openapi.json` sinh bằng `make contracts`.
#### Contract
- Đề xuất 001 (đã duyệt): enum `ErrorCode` (`not_implemented`), `ErrorResponse`, `HealthResponse`.
#### Quyết định
- Khung API tối thiểu thay cho "request/response model đầy đủ"; `/health` luôn trả `200`, không lộ chi tiết lỗi nội bộ; boto3, httpx (dev); biến môi trường của API (`requirements.md` Phase 0, `tech-stack.md` mục 4, 4.1, 7, 11).
#### Tồn đọng
- Phase 3: `lease` trả `204` hoặc `WorkerJobBundle`. Phase 4: mô tả cookie (phiên phía server) và mọi lỗi dùng `ErrorResponse`.
- Starlette cảnh báo `httpx` với `TestClient` đã lỗi thời, khuyên dùng `httpx2`: chưa quyết.

### Phase 0 — Group 5 (frontend) — 2026-09-27
#### Thêm
- `frontend/src/contracts/api.ts` sinh từ `contracts/openapi.json`; mảng giá trị enum trong `schemas.ts`.
- Lớp gọi API (TanStack Query), chế độ mock `VITE_USE_MOCKS`; `StatusBadge` dùng chung cho 3 enum trạng thái; trang `/dev/contracts` chỉ có ở dev; `verify:build`; Vitest.
#### Quyết định
- Cấu hình `StatusBadge` ở một nơi; nguồn type của frontend; biến `VITE_*`; quy ước test Vitest (`tech-stack.md` mục 5.1, 7).
#### Tồn đọng
- Manual check: `/dev/contracts` ở viewport 375px không có thanh cuộn ngang.
- Phase 5: `useRun` dừng polling khi run kết thúc.

### Phase 0 — Group 6 (ml-core) — 2026-09-27 — xong một phần
#### Thêm
- `ml_core/fixtures.py`, `scripts/fetch_fixtures.py` (`make fixtures`): tải, kiểm tra sha256, chỉ đặt file khi khớp.
- `tests/fixtures/checksums.json` có weights YOLOv8n (release v8.3.0 của Ultralytics).
#### Quyết định
- Nơi lưu fixture: GitHub Release `fixtures-v1` của repo; tên file đính kèm phẳng, mỗi mục khai `url` riêng (`plan.md`, `requirements.md` Phase 0).
#### Tồn đọng
- Tạo release `fixtures-v1` với 5 ảnh KITTI và label; task 31 (`manifest.json`) và 32 (smoke test).
- Cần quyết: vị trí smoke test; validate manifest bằng gì (có thể cần đề xuất contract `DatasetManifest`).

### Phase 0 — Group 7 (backend) — 2026-09-27
#### Thêm
- `docker/compose.yaml`: `postgres`, `minio`, `minio-init` (tạo 4 bucket), `api`, `frontend`, có healthcheck; `docker/api/Dockerfile`; `.env.example`.
- `api` chạy migration bằng role owner rồi chạy uvicorn bằng role app; frontend gọi API qua proxy `/api` của Vite.
#### Quyết định
- MinIO bản Chainguard pin theo digest (image chính thức ngừng phát hành); uvicorn; image api python-slim + torch CPU ở Phase 0 (`tech-stack.md` mục 4, 6, 11).
#### Số liệu đo được
- `make up` lần đầu (gồm build image api): khoảng 3 phút 10 giây trên máy phát triển.
#### Tồn đọng
- Phase 3: user MinIO riêng thay cho root; image CUDA dùng chung với worker. Phase 11: pin image nền theo digest.

### Phase 0 — Group 8 (người duyệt) — 2026-09-27
#### Thêm
- `.github/workflows/ci.yml`: job `python`, `frontend`, `contracts`, `acceptance` (Postgres service container); cache uv, pnpm, fixture.
#### Quyết định
- Cấu trúc CI (`tech-stack.md` mục 6).
#### Tồn đọng
- Manual check: CI xanh trên GitHub sau khi push. Phase 11: pin action theo SHA.

### Phase 0 — Group 9 (người duyệt) — 2026-09-27
#### Thay đổi
- `CLAUDE.md`: thêm lệnh `make test-db`, `make contracts-check`, `verify:build`, `ENV_FILE`; quy tắc sửa `scripts/` và file gốc; quy ước `canonical_json`, tiền, `GRANT`.
#### Thêm
- `CHANGELOG.md` (file này).

### Số liệu chung của Phase 0 đến thời điểm này
- `make check`: 176 test Python (trừ test `db`) và 36 test Vitest pass.
- `make test-db`: 28 test pass trên Postgres 17.
