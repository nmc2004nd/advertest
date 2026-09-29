# Changelog

Ghi theo group và phase. Mỗi mục ghi điều đã thêm, đã đổi, thay đổi contract, quyết định (kèm file spec đã ghi nhận), số liệu đo được và việc tồn đọng.

---

## Phase 3 — Worker và máy local

**Trạng thái:** đang làm. Group 0–5 đã merge.

### Phase 3 — Group 5 (backend) — 2026-09-29
#### Thêm
- CLI `advertest-admin` (`backend/admin_cli/cli.py`, entry point trong `pyproject.toml`, người dùng cho phép): `compute-target create|rotate-token|list`, `import-local --store --as`, `submit --config --target [--time-limit] --as` (in ước lượng hoặc "chưa có ước lượng"), `experiment list|show [--watch]|cancel --as`. Lệnh ghi dữ liệu kiểm `--as` là admin `active`.
- `docker/compose.yaml`: service `worker-cpu` (profile `cpu`) và `worker` (profile `gpu`, nvidia), host network, env chỉ gồm `API_URL`, `WORKER_TOKEN`, `CACHE_DIR`, `DEVICE`, `DOCKER_IMAGE_DIGEST`; MinIO mở `127.0.0.1:9000`; `api` có `MINIO_PUBLIC_ENDPOINT` và mount `ADVERTEST_DATA_DIR` chỉ đọc.
- `docker/worker/up.sh cpu|gpu`: build từ working tree sạch, `GIT_COMMIT` là commit hiện tại, `DOCKER_IMAGE_DIGEST` là image ID thật.
- `.env.example` (`MINIO_PORT`, `MINIO_PUBLIC_ENDPOINT`, `ADVERTEST_DATA_DIR`, `API_URL`, `WORKER_TOKEN`, `WORKER_DEVICE`); `docs/van-hanh-worker.md`.
- Test: `test_admin_cli.py` (CliRunner, Postgres và MinIO thật: token chỉ in một lần, `--as` không phải admin bị từ chối, audit, submit/show/list/cancel, `--watch`), `test_compose.py` (env worker không có thông tin đăng nhập, profile, cổng).
#### Sửa (phát hiện khi chạy thật trên Docker)
- Image thiếu thư viện cho opencv: `api` (từ Group 2, qua `ml_core.models.wrapper`) và worker không import được ultralytics, tức `make up` hỏng trên `main` trước nhánh này. Dockerfile cài `libgl1`, `libglib2.0-0`, `libxcb1`; `MPLCONFIGDIR`, `YOLO_CONFIG_DIR` ở `/tmp`.
- Image thiếu `contracts/seeds/`: seed không chạy được trong container. `.dockerignore` thêm thư mục này.
#### Số liệu đo được (chạy thật trên Docker, KITTI slice 300 ảnh seed 42, YOLOv8n, CPU, worker trong container)
- FGSM eps 4/255: mAP@0.5 sạch 0.5332 → 0.1765, ASR 0.438: trùng tuyệt đối số của Phase 2 (CLI). 71.6 giây xử lý; calibration chọn batch 1, 0.244 s/ảnh. 20 failure case kèm thumbnail, `candidates/` rỗng; manifest có `docker_image_digest` thật, `git_dirty = false`.
- Checkpoint: 300 file, checkpoint cuối 4.7 MB, tổng 691 MB cho một run (mỗi batch ghi checkpoint đầy đủ, không xóa checkpoint cũ).
#### Quyết định (người dùng chốt hoặc ghi theo review; đã ghi vào `requirements.md` Phase 3, Luồng xử lý của worker, CLI quản trị; `validation.md` Manual Checks)
- `DOCKER_IMAGE_DIGEST` là image ID thật truyền lúc chạy; worker compose dùng host network, MinIO mở `127.0.0.1:9000`; entry point `advertest-admin` (người dùng chốt).
- `import-local` bắt buộc `--as`, chạy bằng uid của máy; `ADVERTEST_DATA_DIR` mount vào `api`; `local-dev` cấp token bằng `rotate-token`; seed truyền biến admin khi chạy.
#### Review
- Review (do chính agent viết nhánh, không độc lập): không có điểm chặn; ghi nhận: checkpoint quá nặng (worker), compose chạy thẳng không qua `up.sh` làm worker lỗi fingerprint, quyền 0600 của `LocalStore`, CLI chỉ bắt `ServiceError`.
- `make check` pass (562 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 84 test pass.
#### Tồn đọng
- **Checkpoint quá nặng** (Group 4, nên làm trước Group 6): worker xóa checkpoint k-1 sau khi `progress` của checkpoint k thành công.
- Worker nên kiểm `GIT_COMMIT` lúc khởi động (image build không qua `up.sh`).
- `LocalStore` ghi file quyền 0600 (ml-core): cân nhắc 0644 để `import-local` không cần `exec -u`.
- Profile `gpu` chưa chạy thử; manual check `pgd_sweep.yaml` và `kill -9` trên `make up`.
- Image thử nghiệm còn trên máy: `advertest-worker:cpu`, `advertest-g5smoke-api` (container và volume đã dọn).

### Phase 3 — Group 4 (worker) — 2026-09-29
#### Thêm
- Package `advertest_worker` (`backend/worker/advertest_worker/`): `config.py` (`API_URL`, `WORKER_TOKEN`, `CACHE_DIR`, `DEVICE`), `client.py` (API nội bộ, retry với backoff, `409` → `LeaseLost`), `cache.py` (tải theo sha256, `LocalStore` trong cache, `ShaCacheLoader`), `calibrate.py` (n = min(20, số ảnh), batch tối đa min(n, 32), dừng khi hết VRAM hoặc hết lợi trên CPU, có lượt khởi động), `job.py` (vòng lặp start → batch → checkpoint → `progress` → chỉ thị → `complete`; chạy tiếp từ checkpoint; tự dừng khi không đủ thời gian; giảm batch khi hết VRAM; heartbeat ở luồng riêng), `cli.py` (`advertest-worker run [--once]`, `calibrate --experiment <id>`).
- Test: client (MockTransport), calibration trên CPU, vòng lặp `serve`; end-to-end với API, Postgres, MinIO thật: chạy xong, trùng cache (attack không được gọi), worker chết rồi chạy tiếp (mỗi ảnh đúng một lần), giới hạn thời gian (kết quả một phần), hủy (dừng sau batch hiện tại), checkpoint hỏng.
#### Thay đổi (sửa theo review)
- Worker: lỗi khi tải hoặc dựng lại checkpoint chỉ làm run `failed`; vòng lặp `run` không thoát khi một job lỗi.
- Backend (`phase03-backend-fp`): chạy tiếp với fingerprint khác → run `failed` (commit trước khi trả `409`) thay vì kẹt ở `running`; test service, HTTP, end-to-end với worker thật.
#### Quyết định (người dùng chốt hoặc ghi theo review; đã ghi vào `requirements.md` Phase 3, Luồng xử lý của worker, Calibration)
- `calibrate --experiment <id>`, không lease (người dùng chốt).
- Worker xét chỉ thị ở đầu batch và ngay sau `progress`; run `failed`/`cancelled` xóa ứng viên; batch mặc định 8; cache `~/.cache/advertest-worker`; thời gian calibration không tính vào giới hạn; vòng lặp không thoát khi một job lỗi; fingerprint đổi khi chạy tiếp thì run `failed`.
#### Review
- Review (do chính agent viết nhánh, không độc lập): 3 điểm phải sửa, đã sửa kèm test; các test mới fail trên code cũ. Trong lúc viết test hủy cũng phát hiện và sửa: chỉ thị `cancel` trả về từ `progress` của batch cuối bị bỏ qua.
- `make check` pass (559 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 81 test pass.
#### Tồn đọng
- Nhánh giảm batch khi hết VRAM chưa có test (không có GPU): manual check trên máy GPU.
- Test end-to-end dùng YOLOv8n ngẫu nhiên (không có failure case); fixture thật để cho test nghiệm thu Group 6. Metric sau khi chạy tiếp trùng lần chạy liền mạch đã kiểm ở unit test Group 1, chưa kiểm qua worker.
- Group 5: service `worker` trong compose, `.env.example` (`MINIO_PUBLIC_ENDPOINT`), tài liệu chạy worker.

### Phase 3 — Group 3 (backend) — 2026-09-29
#### Thêm
- `backend/app/api/worker.py`: cài đặt 8 endpoint `/internal/worker` (`lease` 200/204, `bundle`, `heartbeat`, `start`, `progress`, `artifact-url`, `complete` 204, `cost-profiles` 204); `search-result` vẫn là khung (Phase 7). OpenAPI không đổi so với Group 0.
- `backend/app/api/deps.py`: session factory, storage, đồng hồ là dependency (test thay được); mỗi endpoint mở transaction riêng; bearer token → compute target (thiếu token 401 trước khi mở DB).
- `backend/app/api/errors.py`: lỗi service → HTTP (404, 403, 409, 422) với `ErrorResponse`.
- `backend/app/services/bundle.py` (dựng `WorkerJobBundle`: card, slice, manifest từ MinIO; mapping, attack spec, cost profile từ DB; presigned GET cho weights, manifest, ảnh, checkpoint); `runs.artifact_url`.
- `backend/app/presign.py`: presigned PUT/GET/DELETE 15 phút qua `MINIO_PUBLIC_ENDPOINT`.
- Test HTTP với Postgres và MinIO thật (`test_worker_api.py`): token và xoay token, bundle với URL tải thật (kiểm sha256), luồng run, URL ngoài thư mục run (403), run đã kết thúc (409), artifact thiếu (422), lease cũ (409), cost profile, URL hết hạn; `test_skeleton.py`: 8 endpoint trả 401 khi thiếu token.
#### Contract (người duyệt, người dùng cho phép)
- `ErrorCode` thêm `invalid_request` (422); sinh lại JSON Schema, OpenAPI, TypeScript.
#### Thay đổi
- Test nghiệm thu Phase 0 `test_worker_internal_endpoint_returns_501` gọi endpoint khung `search-result` thay cho `lease` (người dùng cho phép). Phase 7 phải đổi lại khi cài đặt `search-result`.
#### Quyết định (đã ghi vào `requirements.md` Phase 3, API nội bộ cho worker)
- Bảng mã lỗi của API worker; `bundle` không đòi `lease_id`; `MINIO_PUBLIC_ENDPOINT` mặc định `MINIO_ENDPOINT`; presigned URL còn hiệu lực tới khi hết hạn kể cả sau khi run kết thúc.
#### Review
- Review (do chính agent viết nhánh, không độc lập): không có điểm chặn; ghi nhận: URL còn hiệu lực sau khi run kết thúc, `KeyNotFoundError` từ MinIO trong bundle thành 500, `assert` trong endpoint `lease`, presigner dùng khóa root MinIO.
- `make check` pass (551 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 73 test pass.
#### Tồn đọng
- `MINIO_PUBLIC_ENDPOINT` trong `.env.example` và compose (Group 5); manual check chữ ký qua host công khai với `make up`.
- OpenAPI chưa khai báo 401/403/409/422 cho endpoint worker (cần thay đổi contract nếu muốn).
- Lỗi validation của FastAPI (422 `{"detail": ...}`) chưa theo `ErrorResponse` (Phase 4).

### Phase 3 — Group 2 (backend) — 2026-09-29
#### Thêm
- Migration `0002`: `protocol_status` thêm `dev`, seed `dev-open` (`created_by` null chỉ với `status = dev`); `experiments.lease_id`, `processing_seconds_used`, `inference_params`, `failure_cases_per_run`; `runs.fingerprint` nullable, `cached_from_run_id`, `checkpoint_key`, `checkpoint_batch_index`, `ordinal`; `failure_cases` theo `FailureCaseRecord` (bỏ `artifact_uri`, `thumbnail_uri`, `details`; thêm `fingerprint`, `rank`, `lost_objects`, `new_false_positives`, `detections`, `artifacts`); `slices.slice_sha256`; `cost_profiles.environment`. Upgrade/downgrade hai chiều.
- `backend/app/services/`: `compute_targets` (token `secrets`, DB lưu sha256, xoay token, xác thực), `audit` (`require_admin`, `record`), `registry` (`import_local` từ `LocalStore` vào DB và MinIO, id là `content_id`, chỉ ảnh thuộc slice, chạy lại an toàn), `experiments` (`submit`, `cancel`, `sweep_cancelled`), `leasing` (`lease` `SKIP LOCKED`, `heartbeat`, `directive`), `runs` (`start` có cache toàn hệ thống, `progress`, `complete` kiểm tra artifact trong MinIO, `record_cost_profile`), `estimate`.
- `backend/app/storage.py`: client S3 (boto3) của backend, `Buckets`, bố cục khóa MinIO.
- Test `db` (Postgres và MinIO thật): model khớp migration (trước đây chưa có test này), `dev-open`, compute target, registry, lease (kể cả hai worker đồng thời), cache, giới hạn thời gian, hủy, ước lượng, audit.
#### Quyết định (người dùng chốt hoặc ghi theo review; đã ghi vào `requirements.md` Phase 3)
- `dev-open` không có người tạo, id cố định (mục Protocol phát triển).
- Cost profile giữ lịch sử, profile mới nhất thắng (Calibration và ước lượng).
- Hủy: chờ worker báo nếu lease còn hạn; lease hết hạn thì dọn ngay hoặc ở lần `lease` kế tiếp (Trạng thái).
- Dạng `manifest_uri` và khóa artifact (Bố cục lưu trữ trong MinIO); `runs.ordinal`, `SKIP LOCKED`, thứ tự khóa (API nội bộ); `gpu_seconds` lấy từ worker, giới hạn tính theo tổng API cộng dồn (Trạng thái); kiểm tra admin ở CLI (CLI quản trị).
#### Review
- Review (do chính agent viết nhánh, không độc lập): 3 điểm phải sửa trước khi merge, đã sửa kèm test: run kẹt ở `running` khi hủy rồi worker chết; thứ tự khóa run/experiment có thể gây deadlock; khóa artifact có `..` gây lỗi 500. Test thứ tự khóa và test khóa `..` đã chạy lại trên code cũ và fail; test dọn run kẹt chưa chạy lại trên code cũ. Trong lúc viết test cũng phát hiện và sửa: `lease` khóa dòng compute target làm worker cùng target chờ nhau.
- `make check` pass (546 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 67 test pass.
#### Tồn đọng
- Group 3: dựng `WorkerJobBundle`, presigned URL, đổi lỗi service sang HTTP (404/403/409/422).
- Target `local-dev` do seed tạo không có token: dùng `rotate-token` thay vì `create` (Group 5, `validation.md` Manual Checks).
- User MinIO riêng cho API (tồn đọng Phase 0) chưa có task.
- Migration 0002 thêm cột NOT NULL vào `failure_cases`: chỉ chạy được khi bảng rỗng (đúng với mọi môi trường trước Phase 3).

### Phase 3 — Group 1 (ml-core) — 2026-09-29
#### Thêm
- `ml_core/runner/executor.py`: `RunExecutor` (`process_batch`, `finalize`, `to_checkpoint`, `from_checkpoint`), `RunContext`, `build_context`, `load_clean_predictions`, `linf_eps`. Checkpoint JSON: ảnh đã xử lý, prediction sau tấn công đã lọc class đích, `ImageAttackStats`, top-K và mọi ứng viên đã upload, thời gian xử lý; không chứa ảnh; từ chối checkpoint khác fingerprint. mAP tính lại ở `finalize` theo thứ tự slice.
- `ml_core/runner/candidates.py`: `MemoryCandidates` (CLI, bố cục Phase 2) và `StoreCandidates` (worker: PNG và thumbnail vào `runs/<run_id>/candidates/<image_id>/`, chép sang `cases/<case_id>/` khi hoàn tất).
- `ml_core/runner/images.py`: `thumbnail_webp` (320 px, WebP), mask letterbox, PNG, ảnh nhiễu khuếch đại (chuyển từ `run.py`).
- `ml_core/runner/cache_loader.py`: `ShaCacheLoader` đọc ảnh `<cache>/<sha256>` có kiểm tra hash.
- `ml_core/store/`: `MinioStore` (client S3 truyền vào, bất biến theo ETag/nội dung), `PresignedStore` (`httpx`), protocol `DeletableStore`.
- 21 unit test mới (chạy tiếp gián đoạn hai lần với batch size khác trùng tuyệt đối metric, record và nội dung ảnh; top-K; thumbnail; hai store với client S3 giả và `httpx.MockTransport`).
#### Thay đổi
- CLI `advertest run` dùng `RunExecutor`; bố cục store và đầu ra như Phase 2; 58 test nghiệm thu Phase 2 pass.
#### Quyết định (người dùng chốt; đã ghi vào `requirements.md` Phase 3)
- Run dừng do giới hạn: mọi metric, kể cả mAP sạch, tính trên ảnh đã xử lý (Decisions).
- Loader theo sha256 cho worker đặt trong `ml_core/runner` (Executor dùng chung).
- Ghi vào spec theo review: ứng viên chỉ bị xóa khi hoàn tất, hoàn tất chạy lại được; thời gian batch không gồm upload; `PresignedStore.put` ghi đè được; `MinioStore` nhận client truyền vào; checkpoint theo danh sách ảnh. `validation.md` thêm mục "không xin được URL cho run không `running`".
#### Review
- Review nhanh (do chính agent viết nhánh, không độc lập): 1 điểm phải sửa trước khi merge, đã sửa (unit test thứ tự top-K, bằng điểm, `evict`). `make check` pass (546 test Python, 153 test nghiệm thu, 36 Vitest).
#### Tồn đọng
- Chưa đo kích thước checkpoint trên KITTI 300 ảnh với model thật.
- `from_checkpoint` chưa từ chối `image_id` trùng trong `done` (checkpoint do executor ghi nên không xảy ra).

### Phase 3 — Group 0 (người duyệt) — 2026-09-29
#### Contract
- `RunResult.cached_from_run_id` (chỉ khi `skipped`/`cached`); `RunMetrics.partial` (mặc định `false`, `true` khi và chỉ khi `stopped_limit`); mock `stopped_limit_time_partial`, `skipped_cached_phase3`.
- `compute_failure_case_id(fingerprint, run_id, image_id)`; `CaseArtifacts.clean_thumb`, `adversarial_thumb` (nullable: CLI không tạo); mock `failure_case_record/worker_minio` theo bố cục MinIO.
- Enum `ProtocolStatus` (`active`, `retired`, `dev`); `ErrorCode` thêm `unauthenticated`, `forbidden`, `not_found`, `conflict`.
- Schema mới: `WorkerLease`, `WorkerJobBundle` (`BundleRun`, `BundleCheckpoint`, `BundleDownloads`, `BundleLimit`), `HeartbeatRequest`, `RunStartRequest`, `RunStartResponse`, `ProgressReport`, `WorkerDirective`, `ArtifactUrlRequest`, `ArtifactUrlResponse`, `CostProfile`, `RunCompletion`; kiểu `ObjectKey` (không có `.`/`..`, không `/` đầu), `PresignedUrl`. Mỗi schema có mock; 26 JSON Schema.
- OpenAPI `/internal/worker`: thêm `GET experiments/{id}/bundle`, `POST runs/{id}/start`, `POST cost-profiles`; body và response theo schema mới; `lease` khai `200 WorkerLease` / `204`; `complete`, `cost-profiles` trả `204`. Giữ `experiments/{id}/search-result` (Phase 7).
#### Thêm
- `httpx==0.28.1` thành dependency chính; package `advertest_worker` (`backend/worker/advertest_worker/`, mới có `__init__.py`), script `advertest-worker = advertest_worker.cli:app` (Group 4 viết `cli.py`); mypy, ruff khai package mới.
#### Thay đổi
- Test nghiệm thu Phase 0: danh sách enum (`ErrorCode`, `ProtocolStatus`) và endpoint worker theo Phase 3. Phase 2: `test_case_id_is_uuid5_of_fingerprint_run_and_image`.
- Ngoài thư mục người duyệt (người dùng cho phép): `ml_core/runner/run.py` truyền `run_id` vào `compute_failure_case_id` (1 dòng); `backend/app/tests/api/test_skeleton.py` cập nhật danh sách endpoint worker, gọi thử heartbeat và artifact-url kèm body từ `contracts/mocks` (nay có body bắt buộc), thêm `GET bundle`.
#### Review
- Review nhanh (do chính agent viết nhánh, không độc lập): 2 điểm phải sửa trước khi merge, đã sửa: `test_skeleton.py` gọi thử lại đủ heartbeat, artifact-url; `validation.md` ghi `RunCompletion` thay `RunResult`. `make check` pass (525 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 41 test pass.
#### Quyết định (người dùng chốt; đã ghi vào `requirements.md` Phase 3)
- Lease có `lease_id`; request của worker gửi kèm, `lease_id` cũ → `409` (`validation.md` thêm 1 mục).
- `artifact-url` cấp presigned `PUT`, `GET`, `DELETE`; worker tự chép ứng viên sang `cases/` và xóa phần thừa.
- Người duyệt (agent) tự chọn, ghi vào `requirements.md`: bundle có `inference_params`, `failure_cases_per_run`, `cost_profiles`; `RunCompletion` không dùng cho run `cached`; run `incompatible` hoặc lỗi khi dựng attack vẫn đi qua `start` rồi `complete`.

### Phase 3 — kickoff (spec) — 2026-09-29
#### Quyết định (người dùng chốt)
- `POST /complete` nhận `RunCompletion` (`run_result` + `failure_cases`); API kiểm tra record và khóa artifact, ghi bảng `failure_cases` (sửa bảng cho khớp `FailureCaseRecord`) (`requirements.md` Phase 3, bảng API và Decisions; `plan.md` task 2, 10, 21, 28).
- `FailureCaseRecord.id = compute_failure_case_id(fingerprint, run_id, image_id)`; đóng câu hỏi mở (`requirements.md` Phase 3). Group 0 sửa contract, mock và test nghiệm thu Phase 2 liên quan.
- Worker: `httpx==0.28.1` thành dependency chính, entry point riêng `advertest-worker run|calibrate` (`plan.md` task 4b, 29; `tech-stack.md` mục 11).
- Worker mặc định chạy trực tiếp; compose có profile `cpu` (CI) và `gpu` (tồn đọng khi chưa có máy GPU); đóng câu hỏi mở (`requirements.md`, `validation.md` Manual Checks).
- Calibration: n = min(20, số ảnh của slice), batch tối đa min(n, 32), trên CPU dừng khi `sec_per_image` không giảm (`requirements.md` mục Calibration, `validation.md`).
- Giới hạn thời gian mặc định 2 giờ theo `tech-stack.md` mục 4.2; đóng câu hỏi mở.
#### Tồn đọng
- Lỗ hổng độ phủ chưa xử lý (xem báo cáo kickoff): user MinIO riêng cho api, image CUDA; `DEFAULT_STORE_DIR`, `import-local` không có `--as`; test tự động cho "chỉ upload ảnh thuộc slice", `kind = local`/`billing_mode = none`, seed `dev-open`, `lease` trả `204`, `experiment list`/`show --watch`; cột `environment` của `cost_profiles`; task 23 và 30 không có trong requirements; trạng thái experiment khi mọi run `failed`; seed đã tạo sẵn target `local-dev` (trùng với `compute-target create --name local-dev`).

---

## Phase 2 — Attack white-box đầu tiên

**Trạng thái:** ✅ hoàn thành 2026-09-28, **còn tồn đọng** (người dùng cho phép đóng phase và cập nhật sau). Group 0–4 đã merge.

### Phase 2 — Tổng kết (phase-close) — 2026-09-28
- **Giao được:** adapter ART → `Perturbation` cho `fgsm`, `pgd_linf`, `pgd_l2` (mask vùng ảnh thật, áp lại sau `generate`); metric sau tấn công (ASR, FP mới, mức sụt, `RunMetrics`); chọn failure case kèm 3 PNG và `FailureCaseRecord`; fingerprint, manifest, cache theo fingerprint, `--force`; CLI `advertest run --config [--force]`, `advertest run show`.
- **Contract:** `Perturbation.apply(..., mask)`, `FingerprintInputs.git_dirty`, `RunMetrics.attack_success_rate` nhận `null`, schema `FailureCaseRecord`. Người duyệt đã chấp nhận (Group 0).
- **Số liệu cuối:** `make check` pass trên `main` (463 test Python, 152 test nghiệm thu gồm 58 của Phase 2, 36 test Vitest); `make test-db` 41 test pass. KITTI (CPU): mAP@0.5 sạch 0.5332 → PGD L∞ eps 2/255: 0.0123, eps 4/255: 0.0017; FGSM eps 4/255: 0.1765; PGD L2 eps 1: 0.0556. PGD 1.3 s/ảnh, FGSM 0.17 s/ảnh. Chạy lại `--force` trùng tuyệt đối.
- **`validation.md`:** Automated Tests đủ; 5/7 Manual Checks (người dùng xác nhận); Definition of Done 4/5.
- **CI:** xanh sau khi push `main` gồm phần đóng phase (người dùng xác nhận, 2026-09-29); đánh dấu Definition of Done "Automated Tests pass trên CI".
- **Tồn đọng (cập nhật khi có kết quả):**
  - 2 manual check cần GPU: thời gian mỗi ảnh và batch size lớn nhất khi tính gradient trên GPU; `--force` trên GPU nằm trong sai số.
- **Lưu ý:** các group của người duyệt (0, 4), việc review và merge do agent làm thay theo ủy quyền của người dùng; review do chính agent đã viết code thực hiện nên không phải review độc lập.

### Phase 2 — kickoff (spec) — 2026-09-28
#### Thay đổi
- `attack_success_rate` là `null` khi `|C| = 0`; chạy bằng CLI thì `compute_target_id = null`; cấu hình đọc bằng PyYAML; `git_dirty` bỏ qua `.ai-log/`; run `cached` chỉ in ra, không ghi store; ảnh nhiễu khuếch đại L2 chia theo `max|δ|`; ml-core được sửa `configs/examples/` (`requirements.md`, `plan.md`, `validation.md` Phase 2; `tech-stack.md` mục 11).
#### Quyết định
- Preset `kitti-coco` giữ nguyên, không gộp `bus` vào `truck`; đóng câu hỏi mở (`requirements.md` Phase 2, Decisions).
- Manual check cần GPU chạy trên CPU; phần GPU là tồn đọng (`validation.md` Phase 2).
#### Tồn đọng
- Lỗ hổng độ phủ chưa có mục trong `validation.md`: nhãn cho attack là ground truth, `new_false_positives` trừ số trên ảnh sạch, mAP sạch từ cache, `experiment_id`, `environment`/`gpu_seconds`/`cost`, `inference_params` đổi fingerprint, `run show`, nội dung PNG nhiễu.

### Replan sau Phase 2 — 2026-09-28
- Phase 3 `requirements.md`: `RunExecutor` giữ hành vi Phase 2 (mask áp lại sau `generate`, lọc/ghép prediction, top-K chép riêng ảnh, lỗi khi dựng attack → `failed`); checkpoint chứa prediction đã lọc class đích, không chứa ảnh; CLI giữ bố cục `runs/<fingerprint>/`, MinIO dùng `runs/<run_id>/`; image worker đặt `GIT_COMMIT`, `DOCKER_IMAGE_DIGEST`; `submit --config` dùng `LocalRunConfig`; câu hỏi mở mới về `FailureCaseRecord.id` trùng khi hai run cùng fingerprint chạy đồng thời.
- Phase 3 `plan.md` task 5 và 32; `validation.md` thêm 2 test (manifest trong Docker, checkpoint không chứa ảnh).
- `roadmap.md`: thêm mục "(Từ Phase 2)" cho Phase 3, 6 (lưới mịn ở eps nhỏ), 7 (khoảng tìm kiếm bắt đầu dưới 1/255), 8 (report ghi eps trên ảnh float letterbox, xem lại số failure case).
- Rủi ro: checkpoint nặng nếu lưu prediction thô; YOLOv8n trên ảnh float bão hòa ở mọi mức eps của catalog; thời gian và batch size trên GPU vẫn chưa đo (calibration Phase 3 là lần đo đầu tiên).

### Phase 2 — Group 4 (người duyệt) — 2026-09-28
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_02/` (58 test: Chung, Tính đúng của attack, Metric, Failure case, Fingerprint/manifest/cache, Trạng thái), chạy trên fixture thật bằng CPU; luồng dựng qua CLI trong store tạm; khoảng 1 phút 40 giây cả bộ nghiệm thu.
- Golden value `tests/fixtures/golden/phase_02.json`: mAP@0.5 sạch 0.5186; `fgsm` eps 4: mAP@0.5 0.2231, ASR 0.6; `pgd_linf` eps 4: mAP@0.5 0.0016, ASR 0.9333; sai số ±0.01.
- `validation.md`: 9 mục bổ sung độ phủ (nhãn attack là ground truth, FP mới trừ số ảnh sạch và bỏ class không đích, mAP sạch từ cache, `experiment_id`, `environment`/`gpu_seconds`/`cost`, `inference_params` đổi fingerprint, `run show`, bảng tóm tắt, ảnh nhiễu ở vùng pad) và bố cục `attempts/`.
#### Thay đổi
- `requirements.md`: ghi các quyết định của Group 1–3 (mask áp lại sau `generate`, `level` ngoài dải, lọc và ghép prediction, bố cục store, đầu ra CLI, box trong failure case, `DOCKER_IMAGE_DIGEST`, `GIT_COMMIT`); trả lời 2 câu hỏi mở.
- Sửa lỗi import vòng `ml_core.runner.run` ↔ `ml_core.cli` (vai trò ml-core, nhánh `phase02-ml-core-fix`, đã merge): phát hiện khi viết test nghiệm thu.
#### Số liệu đo được (KITTI, slice 300 ảnh seed 42, YOLOv8n, CPU 16 luồng, batch 8, seed 0)
- mAP@0.5 sạch 0.5332, mAP@0.5:0.95 sạch 0.3042 (khớp baseline Phase 1, lấy từ cache).

| Attack | eps | mAP@0.5 | Relative drop | ASR |
|---|---|---|---|---|
| `pgd_linf` | 2/255 | 0.0123 | 0.977 | 0.767 |
| `pgd_linf` | 4/255 | 0.0017 | 0.997 | 0.903 |
| `pgd_linf` | 8/255 | 0.0005 | 0.999 | 0.948 |
| `pgd_linf` | 16/255 | 0.0001 | 1.000 | 0.984 |
| `fgsm` | 4/255 | 0.1765 | 0.669 | 0.438 |
| `fgsm` | 8/255 | 0.1631 | 0.694 | 0.481 |
| `pgd_l2` | 1 | 0.0556 | 0.896 | 0.623 |
| `pgd_l2` | 2 | 0.0142 | 0.973 | 0.790 |
| `pgd_l2` | 4 | 0.0037 | 0.993 | 0.872 |
| `pgd_l2` | 8 | 0.0010 | 0.998 | 0.932 |

- Thời gian: PGD 1.3 s/ảnh (L∞ và L2), FGSM 0.17 s/ảnh; sweep `pgd_sweep.yaml` 48 phút (2 mức đầu chậm hơn vì test chạy song song), `pgd_l2` 26 phút; RAM tối đa 3.3 GB.
- Chạy lại với `--force`: 6 run trùng tuyệt đối với lần đầu (mAP, ASR, danh sách failure case), cùng fingerprint, ghi vào `reruns/`. `git_dirty = false` (chạy từ worktree sạch tại `6554445`).
- Failure case (`pgd_linf` eps 8, 5 case xem bằng mắt): box ground truth, prediction và ignore region khớp ảnh; nhiễu không nhìn thấy trên ảnh sau tấn công; ảnh nhiễu khuếch đại chỉ có nhiễu trong vùng ảnh thật (vùng pad = 128). Sau tấn công xe biến mất và xuất hiện 40–52 detection sai, phần lớn trên nền.
#### Quyết định (người dùng chốt)
- Giữ dải eps của catalog; vùng hữu ích nằm dưới `pgd_l2` eps 1 và `pgd_linf` eps 2/255 (`requirements.md`, Open Questions).
- Giữ 20 failure case mỗi run, xem lại ở Phase 8.
#### Tồn đọng
- Manual check cần GPU: thời gian mỗi ảnh và batch lớn nhất khi tính gradient, `--force` trên GPU.
- Replan (phase-close): Phase 6 cần lưới mịn ở eps nhỏ (dưới 1/255 với L∞); Phase 7 cần khoảng tìm kiếm mặc định nhỏ; YOLOv8n trên ảnh float không lượng tử hóa rất dễ bị tấn công, report nên ghi rõ.

### Phase 2 — Group 3 (ml-core) — 2026-09-28
#### Thêm
- `ml_core/runner/`: `config.py` (`LocalRunConfig`, YAML, `experiment_id`, đối chiếu spec với catalog), `env.py` (`git_state` bỏ `.ai-log/`, thiết bị, `environment`, `DOCKER_IMAGE_DIGEST`), `fingerprint.py` (`config_sha256` riêng từng run), `run.py` (quét lưới: cache theo fingerprint, `--force`, attack theo batch có mask letterbox, metric, top-k failure case, PNG, `FailureCaseRecord`, manifest, `RunResult`).
- CLI `advertest run --config <yaml> [--force]` (stdout: mảng JSON `RunResult`; stderr: tiến độ, cảnh báo, bảng tóm tắt) và `advertest run show <fingerprint>`.
- `configs/examples/pgd_sweep.yaml` (PGD L∞ 2, 4, 8, 16; FGSM 4, 8) với id KITTI trong `data/store`.
- 36 unit test (YOLOv8n ngẫu nhiên, KITTI tổng hợp; bài kiểm tra gradient được giả lập).
#### Thay đổi
- `current_git_commit`, `describe_device`, `default_device` chuyển sang `ml_core/runner/env.py`; `advertest eval` dùng chung, cảnh báo working tree bẩn nay bỏ qua `.ai-log/`.
#### Quyết định (cần ghi vào `requirements.md` Phase 2)
- Bố cục store (người dùng chốt): `runs/<fp>/` chỉ cho `completed` (`result.json` ghi sau cùng); `failed` và `skipped/incompatible` ở `runs/<fp>/attempts/<run_id>/`; `--force` khi đã có kết quả ghi vào `reruns/<run_id>/`, khi chưa có thì ghi thư mục chính.
- Run `cached` chép `metrics`, `failure_case_ids`, `progress` từ kết quả cũ; không ghi store.
- Box trong `FailureCaseRecord`: prediction đã lọc (class đích, score ≥ `operating_conf`, ngoài ignore region).
- `docker_image_digest` từ biến `DOCKER_IMAGE_DIGEST` (không có thì `"none"`); có `GIT_COMMIT` thì `git_dirty = false`.
#### Review
- Review (do chính agent viết code, không độc lập) tìm 2 lỗi nên sửa, đã sửa trước khi merge: ảnh failure case giữ view của cả batch (có thể tốn khoảng 1.5 GB RAM với 300 ảnh); lỗi khi dựng attack làm dừng cả lệnh thay vì ghi `failed`.
#### Số liệu đo được (5 ảnh fixture, YOLOv8n, CPU, `advertest run`)
- mAP@0.5 sạch 0.5186 (khớp golden Phase 1). Sau tấn công: PGD L∞ eps 4 → 0.0016 (ASR 0.933), eps 16 → 0.0 (ASR 1.0); FGSM eps 4 → 0.2231 (ASR 0.6), eps 8 → 0.2053 (ASR 0.667). Tổng 21 s; lần hai (cached) 3.7 s.
- Batch 1 và batch 5 cho kết quả trùng tuyệt đối; vùng pad trong PNG của 5 failure case giữ nguyên, ảnh nhiễu ở vùng pad bằng 0.5.
#### Tồn đọng
- Phase 3: run lỗi giữa lúc ghi artifact vào `runs/<fp>/` có thể để lại file thừa (nên ghi vào thư mục tạm rồi đổi tên).

### Phase 2 — Group 2 (ml-metric) — 2026-09-28
#### Thêm
- `ml_core/metrics/attack.py`: `match_predictions` (ghép một-một), `image_attack_stats` / `ImageAttackStats` (`correct`, `lost`, `new_false_positives`, `severity_score`), `attack_success_rate`, `compute_drops`, `build_run_metrics` (dựng `RunMetrics`), `severity_score`, `select_failure_cases`; 17 unit test.
#### Quyết định (người dùng chốt; cần ghi vào `requirements.md` Phase 2 mục Metric)
- Trước khi ghép, prediction được lọc như pipeline mAP (class đích, bỏ IoA ≥ 0.5 với ignore region), cho cả tập C và FP mới.
- Ghép một-một cho cả ảnh sạch và ảnh sau tấn công.
- Agent tự chọn: IoU ≥ 0.5 tính cả biên; ghép với ground truth có IoU lớn nhất; `absolute_drop` có thể âm; `image_id` so theo chuỗi khi xếp failure case.
#### Số liệu đo được (YOLOv8n, 3 ảnh fixture, ground truth = prediction sạch ≥ 0.5, CPU)
- ASR: FGSM eps 4 = 0.6; PGD L∞ eps 4 và 16 = 1.0. FP mới mỗi ảnh: 7–9 (FGSM), 14–38 (PGD).

### Phase 2 — Group 1 (attack) — 2026-09-28
#### Thêm
- `attacks/registry.py`: `load_catalog`, `get_spec` (theo `name` trả version cao nhất, hoặc theo `spec_sha256`), `UnknownAttack`.
- `attacks/art_adapter.py`: `ArtPerturbation` (FGSM, PGD L∞, PGD L2 qua ART), `build_perturbation(spec, estimator)`, `IncompatibleAttack`, `UnsupportedAttack`; 27 unit test với estimator giả (`PyTorchYolo` bọc model tuyến tính nhỏ).
#### Quyết định (cần ghi vào `requirements.md` Phase 2)
- ART 1.20.1 bỏ qua `mask` trong `FastGradientMethod` khi estimator là object detector (đã xác nhận: nhiễu 8/255 ở vùng pad); adapter truyền mask cho ART rồi áp lại mask sau `generate` (vùng pad lấy nguyên ảnh gốc) và cắt về `clip_values`.
- `level` ngoài `[min, max]` của spec → `ValueError`; PGD thiếu `eps_step_ratio` dùng 0.25.
#### Số liệu đo được (YOLOv8n, 2 ảnh fixture, CPU)
- FGSM eps 8: 0.16 s/ảnh; PGD L∞ eps 8: 1.3 s/ảnh; PGD L2 eps 2: 1.5 s/ảnh. Vùng pad giữ nguyên chính xác; loss tăng (PGD L∞ 2.1 → 27.3).
- PGD L∞ làm số detection ≥ 0.25 tăng mạnh (7 → 46, 10 → 67): FP mới nhiều, ASR có thể thấp hơn kỳ vọng.

### Phase 2 — Group 0 (người duyệt) — 2026-09-28
#### Contract
- `Perturbation.apply` thêm `mask: MaskBatch | None = None` (N, 1, H, W), float32; `tech-stack.md` mục 3.1 cập nhật.
- `FingerprintInputs.git_dirty: bool` (bắt buộc); mock `manifest/gpu_local.json` tính lại fingerprint (`712a8585…`).
- `RunMetrics.attack_success_rate: UnitFloat | None`; mock mới `run_result/completed_no_detections.json`.
- Schema mới `FailureCaseRecord` (`schema_version = 1`) với `CaseBox`, `CaseIgnoreRegion`, `CaseDetections`, `CaseArtifacts`, hàm `compute_failure_case_id`; mock `failure_case_record/pgd_linf_eps8.json`. Validator: `id` đúng `compute_failure_case_id(fingerprint, image_id)`, `severity_score = lost_objects + 0.5 × new_false_positives` và > 0, ground truth không có score, prediction bắt buộc có score.
- Seed `fgsm`, `pgd_linf`, `pgd_l2` khớp bảng `requirements.md`, không sửa.
- Sinh lại JSON Schema (15), `openapi.json`, `frontend/src/contracts/`.
#### Thêm
- Dependency `pyyaml==6.0.3` (đã có trong `uv.lock` qua ultralytics); mypy khai `yaml` trong `ignore_missing_imports` (`tech-stack.md` mục 7, 11).
#### Thay đổi
- Test nghiệm thu Phase 0 `test_fingerprint_changes_with_every_input`: thêm `git_dirty` vào danh sách trường phải làm đổi fingerprint (chặt hơn, người dùng cho phép).
#### Quyết định (người dùng chốt)
- `FailureCaseRecord` có thêm trường `fingerprint` để schema tự kiểm tra `id`; box ghi `class_name` (class đích), ignore region là `{bbox, source}` (`requirements.md` Phase 2, bảng `FailureCaseRecord`).
#### Số liệu đo được
- `make check` pass: 383 test Python, 94 test nghiệm thu, 36 test Vitest; `contracts-check` sạch.
#### Tồn đọng
- Phase 3: bảng DB `failure_cases` (`artifact_uri`, `thumbnail_uri`, `details`) khác schema `FailureCaseRecord`; `id` trùng giữa lần chạy gốc và `--force` (cùng fingerprint, cùng ảnh) sẽ xung đột khóa chính khi lưu DB.

## Phase 1 — Inference và metric

**Trạng thái:** ✅ hoàn thành 2026-09-28, **còn tồn đọng** (người dùng cho phép đóng phase và cập nhật sau). Group 0–6 đã merge; mục chi tiết từng group (`### Phase 1 — Group …`) nằm bên dưới, xen với mục Phase 0 theo thứ tự thời gian.

### Phase 1 — Tổng kết (phase-close) — 2026-09-28
- **Giao được:** CLI `advertest` chạy trọn `dataset import-kitti` → `model register` → `slice create` → `mapping create` → `eval` → `viz`; wrapper YOLOv8n cho ART (model luôn ở eval, bài kiểm tra gradient); converter KITTI, mapping `kitti-coco` có lọc Moderate, slice theo hash; mAP bằng torchmetrics/pycocotools theo `max_det`; cache prediction thô; kho `LocalStore` bất biến.
- **Contract:** `ModelCard`, `CleanEvalResult`, `SliceSpec`, `ClassMapping`; `IgnoreRegion.source` chấp nhận `difficulty:`. Người duyệt đã chấp nhận.
- **Số liệu cuối:** `make check` pass trên `main` (376 test Python, 94 test nghiệm thu gồm 42 của Phase 1, 36 test Vitest). Baseline KITTI (CPU): mAP@0.5 = 0.533, mAP@0.5:0.95 = 0.304; golden trên fixture 0.5186 / 0.3524.
- **`validation.md`:** 42/42 Automated Tests; 4/7 Manual Checks; Definition of Done 5/6.
- **CI:** xanh sau khi push `main` gồm phần đóng phase (người dùng xác nhận); đánh dấu Definition of Done "Automated Tests pass trên CI".
- **Tồn đọng (cập nhật khi có kết quả):**
  - 3 manual check cần GPU: `eval` trên GPU local (ghi `sec_per_image`, batch size), lần hai trên GPU (cache hit nhanh rõ rệt), theo dõi VRAM và batch size lớn nhất. Máy phát triển hiện không có GPU; baseline đang là số đo CPU.
- **Lưu ý:** các group của người duyệt (0, 6) và việc review, merge do agent làm thay theo ủy quyền của người dùng; review do chính agent đã viết code thực hiện nên không phải review độc lập.

### Replan sau Phase 1 — 2026-09-28
- Phase 2 `requirements.md`: nhãn cho attack lấy từ `SliceLoader` (chỉ số class trong model); mask dựng từ `LetterboxInfo`; mAP sau tấn công qua `CleanMetric` theo `max_det`, mAP sạch từ cache Phase 1; `config_sha256` dùng `LETTERBOX_CONFIG`; `git_commit` lấy như `advertest eval`; câu hỏi mở mới về `Truck`/`bus` trong preset `kitti-coco` (chốt trước golden Phase 2).
- Phase 2 `plan.md` task 19: chuyển `current_git_commit`, `describe_device` sang `ml_core/runner/env.py` để `eval` và `run` dùng chung.
- `roadmap.md` Phase 3: thêm mục "(Từ Phase 1)" (ảnh theo sha256 trên MinIO thay đường dẫn tuyệt đối, `DEFAULT_STORE_DIR`, `import-local` đọc bố cục `LocalStore`, chỉ admin đăng ký model).
- Rủi ro: PGD trên CPU ước khoảng 2 s/ảnh (khoảng 1 giờ cho sweep 6 mức eps trên 300 ảnh); ảnh KITTI của Ultralytics là JPEG mang đuôi `.png` (content-type trên MinIO phải theo định dạng thật).
- Câu hỏi còn mở: YOLOv8 hay YOLOv11.

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

### Phase 1 — Group 6 (người duyệt) — 2026-09-28
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_01/` (42 test: Chung, Letterbox, Dữ liệu, Model, Metric, Đánh giá và cache), chạy trên fixture thật bằng CPU; luồng dựng qua CLI trong store tạm.
- Golden value `tests/fixtures/golden/phase_01.json`: mAP@0.5 0.5186, mAP@0.5:0.95 0.3524, sai số ±0.01 (dataset `5b3d46a7…`, slice seed 42, CPU).
#### Thay đổi
- `.gitignore`: cho phép commit `tests/fixtures/golden/`.
#### Số liệu đo được (KITTI thật, CPU, máy phát triển không có GPU)
- `dataset import-kitti` trên `data/raw/kitti/training/`: 7.481 ảnh, 40.570 annotation, 11.295 `DontCare`; 10 giây; không có bbox vượt khung. `dataset_version_sha256` = `cfd54b7f9e35d30670a99fa3630ac94ff3a54318d12ba98dde6bd36bea490f25`.
- Slice 300 ảnh seed 42: `slice_sha256` = `19356539b9bd…` (id `37341deb-7761-5c9b-adf1-e84a9d3f53a8`); ground truth sau mapping: `car` 719, `person` 135, `truck` 26.
- **Baseline YOLOv8n:** mAP@0.5 = 0.5332, mAP@0.5:0.95 = 0.3042; AP@0.5 `car` 0.842, `person` 0.570, `truck` 0.188. `supports_gradients = true`.
- Thời gian (CPU 16 luồng, batch 8): 0.065 s/ảnh khi cache miss; 0.0096 s/ảnh khi cache hit.
- `viz` 8 ảnh (`000004`, `000028`, `000057`, `000062`, `000100`, `000169`, `000183`, `000216`): box ground truth và prediction khớp vị trí sau letterbox; ignore region phủ đúng xe bị cắt ở mép ảnh và xe bị che.
#### Quyết định
- Câu hỏi mở về baseline đã trả lời: mAP@0.5 = 0.533 ≥ 0.4 nên không cần fine-tune hay đổi kích thước đầu vào (`requirements.md` Phase 1, Open Questions).
#### Tồn đọng
- Manual check cần GPU (máy này không có): `eval` trên GPU local, cache hit nhanh rõ rệt, theo dõi VRAM, batch size lớn nhất.
- Bản KITTI của Ultralytics là JPEG mang đuôi `.png` (nén lại), baseline có thể lệch nhẹ so với ảnh PNG gốc.
- AP `truck` thấp vì `Truck` của KITTI gồm cả xe buýt (YOLO: `bus`): xem lại preset `kitti-coco` khi replan.
- Câu hỏi mở còn lại: chốt YOLOv8 hay YOLOv11.

### Phase 1 — Group 5 (ml-core) — 2026-09-28
#### Thêm
- `ml_core/cli/`: cache prediction thô (`cache.py`), lệnh `eval` (`evaluate.py`), lệnh `viz` (`viz.py`); `letterbox_info` trong `ml_core/preprocess/`.
#### Quyết định
- Khi cache hit, ground truth tính từ manifest không đọc ảnh; `device` là thiết bị đã tạo prediction, lưu trong file cache (sửa sau review); mặc định GPU nếu có, batch size 8; hết VRAM báo lỗi kèm gợi ý; `git_commit` từ `GIT_COMMIT` hoặc `git rev-parse HEAD`; `viz` vẽ prediction thuộc class đích có score ≥ `operating_conf` (`requirements.md` Phase 1).
#### Số liệu đo được (fixture, CPU)
- `advertest eval`: mAP@0.5 = 0.5186, mAP@0.5:0.95 = 0.3524 (khớp Group 4); cache miss 0.087 s/ảnh, cache hit 0.016 s/ảnh, metric giống hệt.
- `viz` ảnh `000902`: box ground truth và prediction khớp vị trí xe sau letterbox.
#### Tồn đọng
- AP `truck` = 0 trên fixture vì KITTI gán `Truck` cho xe buýt, YOLO nhận là `bus` (không có trong mapping). Xem lại preset `kitti-coco` khi replan, sau khi có baseline KITTI.
- Mỗi khóa cache khoảng 10 MB JSON với slice 300 ảnh.
- Trên máy phát triển luôn có cảnh báo working tree bẩn do `.ai-log/` được git theo dõi.

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
