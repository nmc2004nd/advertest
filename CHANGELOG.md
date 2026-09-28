# Changelog

Ghi theo group và phase. Mỗi mục ghi điều đã thêm, đã đổi, thay đổi contract, quyết định (kèm file spec đã ghi nhận), số liệu đo được và việc tồn đọng.

---

## Phase 0 — Contract và khung dự án

**Trạng thái:** ✅ hoàn thành 2026-09-28. Group 1–10 đã merge; mọi mục trong `validation.md` và Definition of Done đã đạt.

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

### Phase 1 — Group 4 (ml-metric) — 2026-09-28
#### Thêm
- `ml_core/metrics/`: `filter_classes`, `filter_ignored` (IoA ≥ 0.5); `CleanMetric` (torchmetrics, backend `pycocotools`); `build_clean_eval_result`.
#### Quyết định
- Giới hạn detection khi tính mAP là `[1, 10, max_det]` (người dùng chốt); AP tính từ tensor `precision` vì `pycocotools.summarize` viết cứng `maxDets=100` cho mAP@0.5:0.95 (người dùng chấp nhận sau review); `per_class` đủ class đích; báo lỗi khi slice không có ground truth (`requirements.md` Phase 1).
#### Số liệu đo được (fixture, CPU, dataset `5b3d46a7…`)
- YOLOv8n trên 5 ảnh: mAP@0.5 = 0.5186, mAP@0.5:0.95 = 0.3524; AP@0.5 `person` 0.832, `car` 0.724, `truck` 0.0 (1 ground truth). Golden value dự kiến cho Group 6.
- Trên fixture, `max_det` 100 hay 300 cho cùng kết quả (sau khi lọc class đích mỗi ảnh còn dưới 100 box).
#### Tồn đọng
- Group 6: so mAP của pipeline với `YOLO.val` của Ultralytics trên cùng slice để phát hiện lệch lớn.

### Phase 1 — Group 2 (ml-data) — 2026-09-28
#### Thêm
- `ml_core/data/`: parser label KITTI và `import_kitti`; lưu dataset và thư mục nguồn; preset `kitti-coco`, `apply_mapping` (`unmapped`, `difficulty`), `build_mapping`; slice theo bộ lọc tự mô tả; `SliceLoader`; lệnh `dataset import-kitti`, `mapping create`, `slice create`.
#### Quyết định
- Thư mục nguồn của ảnh ghi trong store, loader kiểm tra sha256 từng ảnh; `--root` trỏ thẳng tới thư mục có `image_2/`, `label_2/`; `categories` là 8 class KITTI cố định; lấy mẫu slice bằng `random.Random(seed)`; `labels` của loader là chỉ số class trong model; thiếu `truncated`/`occluded` thì không xét; CLI in JSON (`requirements.md` Phase 1).
#### Số liệu đo được (fixture)
- 5 ảnh, 59 annotation, 7 `DontCare`; sau mapping `kitti-coco`: `car = 14`, `truck = 1`, `person = 6`; ignore region 33 `difficulty`, 5 `unmapped`, 7 `dont_care`.
- `dataset_version_sha256` của fixture theo converter này: `5b3d46a79658bc009e50c69c3e68dedbf49fa0d2e47d913c800e06a5a79f9774` (khác `9f5b413e…` của `tests/fixtures/manifest.json` Phase 0 chỉ ở `file_name` và tên converter; annotation và ignore region giống hệt). Golden value của Group 6 dùng hash mới.
#### Tồn đọng
- Phase 3: store đang lưu đường dẫn tuyệt đối của máy local; thay bằng ảnh theo nội dung trên MinIO.
- Loader import `load_card` từ `ml_core.models.register`, kéo theo ultralytics và ART khi nạp.
- Manual check: `import-kitti` trên 7.481 ảnh KITTI (bbox vượt khung ảnh sẽ bị contract từ chối).

### Phase 1 — Group 3 (ml-model) — 2026-09-28
#### Thêm
- `ml_core/models/`: `UltralyticsDetector` (predict có NMS theo `conf/iou/max_det`, loss `v8DetectionLoss`, model luôn ở eval), `build_estimator` (`PyTorchYolo`), bài kiểm tra gradient, `register_model` và lệnh `advertest model register`.
#### Thay đổi
- `pyproject.toml`: mypy bỏ qua thiếu type stub của `art` (`tech-stack.md` mục 7), người dùng cho phép.
#### Quyết định
- Wrapper tự viết thay cho `is_ultralytics=True` của ART; target của bài kiểm tra gradient là prediction của chính model (score ≥ 0.25); weights chép vào store; đăng ký lại trả card cũ; lỗi khi kiểm tra không ghi card (`requirements.md` Phase 1).
#### Số liệu đo được (fixture, CPU)
- Wrapper khớp `YOLO.predict` trên 5 ảnh: cùng số box (245–293), IoU nhỏ nhất 0.99998, score lệch tối đa 1.4e-6.
- Bài kiểm tra gradient trên YOLOv8n: loss 9.63 → 25.43 sau bước 2/255; state_dict và 114 tensor BatchNorm không đổi; `supports_gradients = true`.
- YOLOv8n khởi tạo ngẫu nhiên không đạt điều kiện "loss tăng" (loss gần như phẳng theo ảnh): unit test chỉ khẳng định gradient hợp lệ và model không đổi; điều kiện này cần có trong test nghiệm thu trên fixture (Group 6).

### Phase 1 — Group 1 (ml-core) — 2026-09-28
#### Thêm
- `ml_core/store/`: `ArtifactStore`, `LocalStore` (key bất biến, ghi nguyên tử), chỉ mục id → sha `index/<kind>/<id>`.
- `ml_core/preprocess/letterbox.py`: letterbox 640×640 (Pillow `BILINEAR`, pad 114/255, căn giữa), `LETTERBOX_CONFIG`, chuyển box hai chiều.
- CLI `advertest` (Typer): nhóm lệnh `model`, `dataset`, `slice`, `mapping`; `eval`, `viz` dạng khung (báo chưa có đến Group 5); tùy chọn chung `--store-dir`.
- Dependency `typer==0.27.2`, `pillow==12.3.0`, `pycocotools==2.0.11`; entry point `advertest` (`tech-stack.md` mục 11).
#### Thay đổi
- `.gitignore`: `data/` → `/data/` (dòng cũ bỏ qua cả `ml_core/data/`), người dùng cho phép.
#### Quyết định
- 3 Typer trong `ml_core/data/cli.py`; chỉ mục id do Group 1 làm; `--store-dir`; key bất biến và không bắt đầu bằng `.`; `LETTERBOX_CONFIG` cho khóa cache và fingerprint (`requirements.md`, `plan.md` Phase 1).

### Phase 1 — Group 0 (người duyệt) — 2026-09-28
#### Contract
- Schema mới, `schema_version = 1`: `ModelCard` (kèm `GradientCheck`), `ClassMapping` (thân `ClassMappingBody`, `compute_mapping_sha256`), `SliceSpec` (`SliceFilter`, `compute_slice_sha256`), `CleanEvalResult` (`InferenceParams`, `EvalMetrics`, `ClassEvalMetrics`, ...); kiểu dùng chung `DifficultyFilter`, `InferenceParams`.
- `IgnoreRegion.source` chấp nhận thêm `difficulty:<class>`; hash manifest fixture không đổi (`9f5b413e...`).
- Validator: mọi `id` phải là `content_id` của hash tương ứng; `ModelCard.supports_gradients == gradient_check.passed`, `details` bắt buộc khi fail; `SliceSpec.image_ids` sắp xếp, không trùng, đúng `size` phần tử; `ap50`/`ap50_95` là null khi và chỉ khi `num_gt = 0`.
- Mock: `model_card` (2), `class_mapping` (1), `slice_spec` (1), `clean_eval_result` (2). Sinh lại JSON Schema, `openapi.json`, `frontend/src/contracts/`.
#### Quyết định
- `len(image_ids) == size`: `slice create` báo lỗi khi không đủ ảnh đạt bộ lọc; AP của class không có GT là `null` (người dùng chốt, 2026-09-28).
- `ModelCard.framework` chỉ nhận `ultralytics` hoặc `torchvision` (phương án dự phòng Faster R-CNN).
- `slice_sha256` hash đúng 5 trường theo `requirements.md` (không gồm `schema_version`); `mapping_sha256` hash mọi trường trừ `id` và chính nó (gồm `schema_version`, cùng cách với `AttackSpec`).
#### Thay đổi
- Test contract `test_dataset_manifest_rejects_inconsistent`: case `difficulty:Car` (trước đây bị từ chối) đổi thành `foo:Car`, vì contract nay chấp nhận `difficulty:`.
#### Sau review
- Các quyết định trên đã ghi vào `requirements.md` Phase 1; `DifficultyFilter` ghi rõ ngưỡng tính cả biên (giữ khi cao ≥ 25, `occluded` ≤ 1, `truncated` ≤ 0.30).

### Phase 1 — kickoff lần 2 (spec) — 2026-09-28
#### Thay đổi
- Group 0 thêm 4 schema `ModelCard`, `CleanEvalResult`, `SliceSpec`, `ClassMapping` (mỗi schema `schema_version = 1`, không có version chung của gói); `ModelCard.lib_versions` dùng `LibVersions`; pattern `IgnoreRegion.source` chấp nhận `difficulty:.+` (`requirements.md`, `plan.md`, `validation.md` Phase 1).
- Bộ lọc slice tự mô tả (`classes`, `difficulty`, `min_objects`, mặc định từ preset `kitti-coco`); `slice create` không cần model hay mapping (`requirements.md`, `plan.md`, `validation.md` Phase 1).
- Cấu trúc file `ClassMapping` được định nghĩa (`requirements.md` Phase 1).
#### Quyết định
- Backend của `MeanAveragePrecision` là `pycocotools`; Group 1 thêm vào `pyproject.toml` (`tech-stack.md` mục 2, `plan.md` task 8).
#### Tồn đọng
- Group 0 chưa merge: Group 2–4 bị chặn.
- Lỗ hổng độ phủ chưa có test trong `validation.md`: `LocalStore` và chỉ mục id → sha, đầu ra dataset loader, letterbox căn giữa, `mapping_sha256` đổi khi đổi ngưỡng, các thành phần khác của khóa cache, thông báo hết VRAM, `mapping create --model`.

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

### Phase 0 — Group 6 (ml-core) — 2026-09-27/28
#### Thêm
- `ml_core/fixtures.py`, `scripts/fetch_fixtures.py` (`make fixtures`): tải, kiểm tra sha256, chỉ đặt file khi khớp.
- `tests/fixtures/checksums.json`: weights YOLOv8n, 5 ảnh và 5 label gốc KITTI; `tests/fixtures/LICENSE.md`.
- `tests/fixtures/manifest.json` (schema `DatasetManifest`): 5 ảnh, 59 annotation, 7 ignore region `dont_care`.
- Test nghiệm thu: smoke test YOLOv8n trên CPU, manifest đối chiếu với ảnh và label gốc, fixture phủ đủ trường hợp.
#### Contract
- Đề xuất 002 (đã duyệt): `DatasetManifest` và các model con; `schema_version = 1`.
#### Quyết định
- Nơi lưu fixture: GitHub Release `fixtures-v1` của repo (repo chuyển sang public); tên file đính kèm phẳng, mỗi mục khai `url` riêng.
- Nguồn KITTI: ảnh từ bản Ultralytics, label gốc từ KITTI (label YOLO mất `DontCare`, `truncated`, `occluded`) (`requirements.md` Phase 0, Phase 1).
- 5 ảnh `000902`, `002571`, `004499`, `004965`, `005866` chọn tự động theo độ phủ lớp và số object.
#### Số liệu đo được
- Smoke test YOLOv8n trên 5 ảnh letterbox 640×640, CPU: khoảng 1,5 giây.
- Trong 5 ảnh: 38/59 object dưới mức Moderate (sẽ thành ignore region khi áp mapping ở Phase 1).
- `dataset_version_sha256` của fixture: `9f5b413eb8a78a6a4b216011c2cf26e5b877728f7a160bbb80964a917d976069`.
#### Tồn đọng
- Tải 5 file `kitti_label_2_*.txt` lên release `fixtures-v1` (trước khi push, nếu không CI fail ở `make fixtures`).

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
#### Sửa lỗi (2026-09-28)
- Lần chạy CI đầu tiên (run 36336331689): job `python`, `contracts`, `acceptance` fail ở "Set up job" vì `astral-sh/setup-uv` không có tag major `v10`; đổi sang `@v10.2.0`.
#### Tồn đọng
- Manual check: CI xanh trên GitHub sau khi push. Phase 11: pin action theo SHA.

### Phase 0 — Group 9 (người duyệt) — 2026-09-27
#### Thay đổi
- `CLAUDE.md`: thêm lệnh `make test-db`, `make contracts-check`, `verify:build`, `ENV_FILE`; quy tắc sửa `scripts/` và file gốc; quy ước `canonical_json`, tiền, `GRANT`.
#### Thêm
- `CHANGELOG.md` (file này).

### Phase 0 — Group 10 (người duyệt) — 2026-09-27
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_00/`: `test_contracts.py`, `test_database.py` (marker `db`), `test_api.py`, `test_fixtures.py`.
- `make test-db` dựng thêm MinIO (cùng digest với compose) để test `/health` với Postgres và MinIO thật; job `acceptance` của CI chạy MinIO bằng `docker run` và chạy test nghiệm thu `db`.
#### Thay đổi spec
- `tech-stack.md` mục 4.1: hash ghi rõ theo RFC 8785.
#### Thay đổi
- `make test-acceptance` chạy `make fixtures` trước và bỏ qua test `db` (test `db` chạy trong `make test-db`).
#### Quyết định
- Test manifest.json và smoke test YOLOv8n viết cùng phần còn lại của Group 6; test `/health` dùng MinIO thật (người dùng chốt, 2026-09-27).
#### Số liệu đo được
- Test nghiệm thu: 49 test không cần DB pass; 13 test `db` pass (cùng 28 test DB của backend: 41 pass).
- Thử lỗi giả: cấp thêm `UPDATE` cho bảng chỉ-thêm làm 10 test fail; MinIO sai cổng làm test `/health` fail.
- Rà `contracts/`: tên trường của 9 schema khớp bảng trong `requirements.md`; `FingerprintInputs` đủ 11 đầu vào.
#### Manual check đã chạy (trên máy phát triển, 2026-09-27)
- `make up`: 4 service healthy; MinIO có đủ 4 bucket; MinIO console và `/docs` trả `200`; OpenAPI có đủ các nhóm endpoint; `/dev/contracts` phục vụ được ở chế độ mock.
#### Tồn đọng
- Manual check người duyệt tự làm: `/dev/contracts` ở viewport 375px; CI xanh trên GitHub; đọc lại `contracts/` đối chiếu `mission.md` mục 4.
- Group 6: 5 ảnh KITTI, `manifest.json`, smoke test và hai test nghiệm thu tương ứng.
- Phase 0 chưa đánh dấu hoàn thành trong `roadmap.md` (còn mục fixture và CI).

### Phase 0 — kiểm tra Definition of Done (phase-close) — 2026-09-27
- `validation.md`: đánh dấu 30 mục Automated Tests có bằng chứng (`make check`, `make test-db`, `verify:build`, test nghiệm thu) và 2 mục DoD (`CLAUDE.md` đã dùng thật; `tech-stack.md` mục 11 đã ghi phiên bản pin).
- Manual check `make up`, MinIO 4 bucket, `/docs`: agent đã chạy ở Group 10; người dùng chấp nhận là đạt.
- **Phase 0 chưa đóng.** Còn thiếu: 3 test fixture (Group 6: ảnh KITTI, `manifest.json`, smoke test); manual check `/dev/contracts` (badge, viewport 375px), CI xanh trên GitHub, đọc lại `contracts/`; DoD "Automated Tests pass trên CI", "người duyệt chấp nhận `contracts/` và migration". Người dùng chọn để sau.

### Phase 0 — kiểm tra Definition of Done lần 2 (phase-close) — 2026-09-28
- Đánh dấu thêm: `make fixtures` tải đủ 11 file (job acceptance của CI và tải thử từ thư mục trống); người dùng xác nhận `/dev/contracts` hiển thị badge đúng và CI xanh cả 4 job (run 36336874119, commit `7471b62`), kéo theo DoD "Automated Tests pass trên CI".
- **Phase 0 vẫn chưa đóng.** Còn thiếu: `/dev/contracts` ở viewport 375px; đọc lại `contracts/` đối chiếu `mission.md` mục 4 và `tech-stack.md` mục 4.3, 4.4; người duyệt chấp nhận `contracts/` và migration `0001` (kéo theo DoD "Toàn bộ Manual Checks").

### Phase 0 — Tổng kết (phase-close) — 2026-09-28
- **Đóng phase.** Người dùng xác nhận 2 manual check cuối (`/dev/contracts` ở viewport 375px; đã đọc lại `contracts/`). `validation.md` đủ 44/44 mục; `roadmap.md` đánh dấu Phase 0 hoàn thành.
- **Giao được:** monorepo với uv và pnpm; contract Pydantic (16 enum + `ErrorCode`, 10 schema, sinh JSON Schema, OpenAPI, TypeScript); DB 23 bảng với phân quyền chống sửa kết quả và trigger chặn tự review; API khung FastAPI; frontend khung; Docker Compose (Postgres, MinIO, API, frontend); CI 4 job; fixture KITTI 5 ảnh kèm manifest; 52 test nghiệm thu (13 cần DB).
- **Contract:** đề xuất 001 (`ErrorResponse`, `HealthResponse`) và 002 (`DatasetManifest`) đã duyệt và áp dụng.
- **Số liệu cuối:** `make check` pass; `make test-db` 41 test pass; CI run 36336874119 xanh cả 4 job.
- **Lưu ý:** các group của người duyệt do agent soạn thay theo cho phép của người dùng; review do chính agent thực hiện nên không phải review độc lập.
- **Tồn đọng chuyển sang phase sau:** xem `roadmap.md` (mục "Từ Phase 0" ở Phase 3, 4, 5, 11); câu hỏi mở về đơn vị tiền tệ mặc định.

### Phase 0 — kiểm tra Definition of Done lần 3 (phase-close) — 2026-09-28
- Người duyệt chấp nhận `contracts/` và migration `0001`.
- **Phase 0 vẫn chưa đóng.** Còn thiếu: `/dev/contracts` ở viewport 375px; đọc lại `contracts/` đối chiếu `mission.md` mục 4 và `tech-stack.md` mục 4.3, 4.4 (kéo theo DoD "Toàn bộ Manual Checks").

### Replan sau Phase 0 (lần 2) — 2026-09-28
- Fixture sau mapping `kitti-coco` và lọc Moderate còn `car = 14`, `truck = 1`, `person = 6` ground truth; ghi vào `validation.md` Phase 1. AP từng lớp trên fixture nhiễu (đặc biệt `truck`), golden value chỉ nên so mAP tổng.

### Replan sau Phase 0 — 2026-09-27
- Phase 1: Group 2–5 phụ thuộc Phase 0 Group 6 (fixture KITTI); Group 1 thêm `typer`, `pillow` và entry point `advertest` vào `pyproject.toml`; contract Phase 1 dùng lại `Sha256Hex`, `GitCommit`, `LibVersions`, `UtcDatetime` (`plan.md`, `requirements.md` Phase 1).
- Phase 2: ID ghép và `experiment_id` tính bằng `content_id(sha256_of(...))`; seed Phase 0 đã khớp bảng catalog (`requirements.md`, `plan.md` Phase 2).
- Tồn đọng của Phase 0 đưa vào `roadmap.md` ở Phase 3, 4, 5, 11.
- Câu hỏi còn mở: đơn vị tiền tệ mặc định (VND hay USD).

### Số liệu chung của Phase 0 đến thời điểm này
- `make check`: 176 test Python (trừ test `db`), 49 test nghiệm thu và 36 test Vitest pass.
- `make test-db`: 41 test pass trên Postgres 17 và MinIO.
