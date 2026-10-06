## Phase 3 — Worker và máy local

**Trạng thái:** ✅ hoàn thành 2026-09-29, **còn tồn đọng** (người dùng cho phép đóng phase). Group 0–6 đã merge.

### Replan sau Phase 3 — 2026-09-29
- Phase 4 `requirements.md`: danh sách `ErrorCode` gộp các mã đã có từ Phase 3 (`invalid_request` cho 422 nghiệp vụ; `validation_error` cho 422 do sai schema).
- Phase 5 `requirements.md`: `POST /experiments` dùng lại `experiments.submit` (inference params, `failure_cases_per_run`, action audit `experiment.submit`/`experiment.cancel`); `ErrorResponse` cần đường dẫn trường; câu hỏi mở mới về cách phục vụ ảnh cho điện thoại (presigned URL hiện ký cho `127.0.0.1:9000`).
- Phase 6 `requirements.md`: làm mờ ở `StoreCandidates` của worker; `targets` chưa có `image_id` trong `RunExecutor`; thời gian train patch báo qua `progress`; PGD phụ thuộc nhẹ batch size.
- `tech-stack.md` mục 4.4: tái lập với batch size khác nhau (±0.01).
- `roadmap.md`: "Từ Phase 3" cho Phase 9 (user MinIO riêng, GPU) và Phase 10 (`DEFAULT_STORE_DIR`, quyền 0600 của `LocalStore`).
- Rủi ro: ảnh trên điện thoại ở Phase 5; thời gian job acceptance của CI tăng; tái lập và calibration trên GPU chưa đo.

### Phase 3 — Tổng kết (phase-close) — 2026-09-29
- **Giao được:** experiment gửi qua `advertest-admin` (compute target, token, `import-local`, `submit`, `experiment list|show|cancel`); API nội bộ `/internal/worker` (lease có `lease_id`, bundle, heartbeat, start có cache toàn hệ thống, progress, artifact-url, complete, cost profile); worker `advertest-worker` (chạy trực tiếp hoặc Docker `cpu`/`gpu`) chạy `RunExecutor` theo batch, checkpoint lên MinIO qua presigned URL, chạy tiếp sau gián đoạn, calibration, giới hạn thời gian, hủy; artifact và thumbnail trong MinIO; đủ trạng thái run có lý do.
- **Contract:** schema API worker (`WorkerLease`, `WorkerJobBundle`, `RunStartRequest/Response`, `ProgressReport`, `WorkerDirective`, `ArtifactUrlRequest/Response`, `CostProfile`, `RunCompletion`), `RunResult.cached_from_run_id`, `RunMetrics.partial`, `FailureCaseRecord.id` gồm `run_id`, thumbnail, `ProtocolStatus`, `ErrorCode` (401/403/404/409/422). Người dùng chấp nhận (làm thay người duyệt theo ủy quyền).
- **Số liệu cuối:** `make check` pass trên `main` (562 test Python, 156 test nghiệm thu không cần DB, 36 Vitest); `make test-db` 124 test (41 test nghiệm thu Phase 3). KITTI 300 ảnh, CPU, worker trong Docker: `pgd_sweep` 28 phút xử lý, metric trong ±0.01 so với Phase 2 (FGSM trùng tuyệt đối); `kill -9` chạy tiếp sau 59 giây; checkpoint 27 MB cho 6 run; calibration PGD batch 2 1.229 s/ảnh, FGSM batch 2 0.158 s/ảnh.
- **`validation.md`:** Automated Tests đủ; Manual Checks 9/10; Definition of Done 5/6.
- **CI:** xanh sau khi push `main` gồm Group 6 (người dùng xác nhận, 2026-09-29).
- **Tồn đọng (cập nhật khi có kết quả):**
  - Manual check profile `gpu` và số calibration trên GPU.
  - User MinIO riêng cho API (từ Phase 0), `DEFAULT_STORE_DIR` chỉ đúng khi cài editable (từ Phase 1): chưa có task, đề xuất chuyển sang phase sau (replan).
  - Kết quả PGD phụ thuộc nhẹ vào batch size trên KITTI thật (trong sai số).
- **Lưu ý:** Group 0, 6, việc review, merge và phase-close do agent làm thay người duyệt theo ủy quyền của người dùng; review và test nghiệm thu do chính agent đã viết code thực hiện nên không độc lập.

### Phase 3 — Group 6 (người duyệt, người dùng cho phép) — 2026-09-29
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_03/` (41 test, mọi mục Automated Tests của `validation.md`): `test_architecture.py` (AST import, env compose, OpenAPI và router), `test_worker_auth.py`, `test_leasing.py`, `test_artifacts.py`, `test_execution.py` (golden Phase 2 ±0.01), `test_resume.py` (so lần chạy liền mạch ±0.005/±0.01, gián đoạn một và hai lần), `test_limits.py`, `test_calibration.py` (CLI `advertest-worker calibrate` qua uvicorn thật), `test_audit.py`. Chạy với worker thật, YOLOv8n và 5 ảnh fixture thật, Postgres và MinIO thật; cả bộ khoảng 1.5 phút trên CPU.
- Lần chạy liền mạch và lần bị gián đoạn dùng GIT_COMMIT khác nhau (fingerprint khác, không trúng cache); yêu cầu `start` trong test có fingerprint riêng mỗi lần.
- Manifest trong Docker kiểm bằng test mô phỏng env (`GIT_COMMIT`, `DOCKER_IMAGE_DIGEST`) cộng manual check trong container (người dùng chốt).
#### Manual check (máy phát triển, CPU 16 luồng, không GPU; `make up` với project và cổng riêng, đã dọn)
- `import-local`: 300/7481 ảnh KITTI lên MinIO (đếm object; chỉ ảnh thuộc slice).
- `pgd_sweep.yaml` trên slice KITTI 300 ảnh, worker trong Docker (`docker/worker/up.sh cpu`), 28 phút xử lý: 6 run `completed`, mỗi run 20 failure case đủ file (PNG 640x640, thumbnail WebP 320x320), `candidates/` rỗng, manifest có `docker_image_digest` thật và `git_dirty = false`.
- `kill -9` worker khi run PGD L∞ eps 2 ở 132/300 ảnh; khởi động lại; worker nhận lại experiment sau 59 giây (lease hết hạn) và chạy tiếp từ checkpoint batch 65.
- Metric so với Phase 2 (CLI, batch 8): FGSM eps 4/8 trùng tuyệt đối (0.1765, 0.1631); PGD L∞ eps 2 (run bị gián đoạn) mAP@0.5 0.0129 vs 0.0123, ASR 0.761 vs 0.767; eps 4 0.0018 vs 0.0017, ASR 0.897 vs 0.903; eps 8, 16 trùng mAP, ASR lệch ≤ 0.006: trong sai số ±0.01. Lệch có cả ở run PGD không bị gián đoạn, nhiều khả năng do batch size (2 vs 8) chứ không do chạy tiếp.
- Gửi lại cùng cấu hình: 6 run `skipped` (`cached`), xong trong khoảng 20 giây.
- Giới hạn 60 giây: dừng ở 59.9 giây xử lý; run hiện tại `stopped_limit` (42/300 ảnh, `partial = true`), 5 run chưa chạy `stopped_limit` với 0 ảnh.
- Worker chạy trực tiếp (`uv run --extra cpu advertest-worker run --once`): FGSM eps 4 trên 300 ảnh, 48.5 giây, `completed`.
- Calibration trên CPU: PGD L∞ batch 2, 1.229 s/ảnh (batch 1: 1.319, batch 4: 1.321); FGSM batch 2, 0.158 s/ảnh.
- Checkpoint sau `pgd_sweep`: mỗi run 1 file (4.1–5.0 MB), tổng 27 MB cho 6 run (trước khi sửa: 691 MB cho một run).
#### Tồn đọng
- Manual check profile `gpu` (không có GPU); số calibration trên GPU.
- PGD phụ thuộc nhẹ vào batch size trên KITTI thật (≤ 0.0006 mAP, ≤ 0.006 ASR): nằm trong sai số, nên ghi vào spec về tái lập.
- Definition of Done: CI xanh sau khi push, đánh dấu `roadmap.md` (skill `phase-close`).

### Phase 3 — sửa checkpoint quá nặng (worker) — 2026-09-29
#### Thay đổi
- `advertest_worker/job.py`: xóa checkpoint k-1 sau khi `progress` của checkpoint k thành công (khi chạy tiếp, xóa checkpoint trong bundle sau batch kế tiếp); giữ checkpoint cuối cùng của run (xóa trước `complete` thì worker chết đúng lúc đó sẽ không chạy tiếp được). Xóa lỗi chỉ ghi cảnh báo; mất lease (`409`) khi xóa thì dừng experiment ngay.
- Test end-to-end: chạy tiếp sau khi worker chết còn đúng checkpoint cuối mỗi run (fail trên code cũ); xóa lỗi không làm run `failed`; mất lease khi xóa thì không xử lý thêm, không gửi `complete` (fail trên code cũ).
#### Quyết định (ghi theo review; đã ghi vào `requirements.md` Phase 3, Checkpoint và chạy tiếp; `validation.md` thêm manual check dung lượng checkpoint)
- Mỗi run chỉ giữ checkpoint mới nhất mà API đang trỏ tới; có thể thừa một file nếu worker chết giữa `progress` và lệnh xóa.
#### Review
- Review (do chính agent viết nhánh, không độc lập): 1 điểm phải sửa (nuốt `LeaseLost` khi xóa checkpoint), đã sửa kèm test.
- `make check` pass (562 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 86 test pass.
#### Tồn đọng
- Chưa đo lại dung lượng trên KITTI (ước tính còn khoảng 4.7 MB mỗi run thay vì 691 MB): manual check Group 6.

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
