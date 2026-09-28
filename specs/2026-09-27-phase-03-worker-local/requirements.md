# Requirements: Phase 3 — Worker và máy local

## Scope

Chuyển việc chạy attack từ CLI sang mô hình job: experiment được ghi vào hệ thống, worker trên máy local lấy job qua API nội bộ, chạy, báo tiến độ, lưu artifact vào MinIO, và chạy tiếp được sau khi bị gián đoạn. Kết quả của phase gồm:

1. **Executor chạy theo từng batch** với trạng thái lưu được, dùng chung cho CLI và worker.
2. **Compute target và token** cho worker.
3. **API nội bộ cho worker**: nhận job, lấy tài nguyên, bắt đầu run, báo tiến độ, xin URL upload, hoàn thành run, heartbeat.
4. **Worker** chạy trên máy local (trong Docker có GPU hoặc chạy trực tiếp).
5. **Artifact trong MinIO**, kèm thumbnail cho failure case.
6. **Đủ trạng thái run có lý do**, cache theo fingerprint ở cấp hệ thống.
7. **Giới hạn thời gian** cho máy local.
8. **Checkpoint theo batch** và chạy tiếp sau gián đoạn.
9. **Calibration cost profile** và hàm ước lượng thời gian.
10. **CLI quản trị phía server** (`advertest-admin`) để đăng ký tài nguyên, gửi experiment, theo dõi và hủy.

Cuối phase: gửi experiment, theo dõi tiến độ; tắt worker giữa chừng, bật lại thì experiment chạy tiếp và cho kết quả đúng.

## Out of Scope

- Xác thực người dùng và endpoint công khai cho experiment (Phase 4, 5). Trong phase này, experiment chỉ được gửi và theo dõi qua `advertest-admin` chạy phía server.
- Giao diện web (Phase 5).
- Email thông báo (Phase 5).
- Máy thuê, ngân sách, ledger, Tailscale (Phase 9).
- Hàng đợi công bằng giữa nhiều người dùng. Phase này dùng thứ tự đến trước.
- Một worker chạy nhiều experiment cùng lúc. Mỗi worker chạy một experiment tại một thời điểm.
- Attack mới (Phase 6), tự tìm ngưỡng (Phase 7).
- Protocol thật và quy trình duyệt (Phase 8).

## Data / Fields

### Thay đổi contract (cần người duyệt chấp nhận)

1. **Schema mới cho API nội bộ của worker:**

| Schema | Nội dung chính |
|---|---|
| `WorkerJobBundle` | `experiment_id`, `config` (`ExperimentConfig`), `model_card`, `slice`, `class_mapping`, `attack_specs`, URL tải (weights, manifest, ảnh của slice), `limit` (`kind`, `value`, `used`), `runs` (danh sách run đã lập, kèm checkpoint nếu đang chạy dở) |
| `RunStartRequest` | `fingerprint`, `fingerprint_inputs`, `environment` |
| `RunStartResponse` | `action` (`run` / `skip_cached`), `cached_from_run_id`, `cached_result` |
| `ProgressReport` | `images_done`, `batch_index`, `checkpoint_key`, `processing_seconds_delta` |
| `WorkerDirective` | `action` (`continue` / `cancel` / `stop_limit`), `remaining_seconds` |
| `CostProfile` | `compute_target_id`, `model_version_id`, `attack_spec_id`, `sec_per_image`, `peak_vram_mb`, `batch_size`, `measured_at`, `environment` |
| `RunCompletion` | `run_result` (`RunResult`), `failure_cases` (danh sách `FailureCaseRecord`) |

2. **`RunResult`** thêm `cached_from_run_id` (nullable) và `metrics.partial` (bool).
3. **`FailureCaseRecord.artifacts`** thêm `clean_thumb` và `adversarial_thumb`. **`FailureCaseRecord.id`** đổi thành `compute_failure_case_id(fingerprint, run_id, image_id)`.
4. **Enum mới `ProtocolStatus`**: `active`, `retired`, `dev`.
5. **OpenAPI**: nhóm `/internal/worker` gồm các endpoint trong mục Behaviour.

### Bố cục lưu trữ trong MinIO

| Bucket | Khóa |
|---|---|
| `models` | `<weights_sha256>/weights.pt`, `<weights_sha256>/card.json` |
| `datasets` | `<dataset_sha>/manifest.json`, `<dataset_sha>/images/<image_sha256>.png`, `slices/<slice_sha>.json`, `mappings/<mapping_sha>.json` |
| `artifacts` | `runs/<run_id>/manifest.json`, `runs/<run_id>/result.json`, `runs/<run_id>/checkpoints/<batch_index>.json`, `runs/<run_id>/candidates/<image_id>/...`, `runs/<run_id>/cases/<case_id>/...` |

## Behaviour

### Executor dùng chung
- Tách logic chạy run của Phase 2 thành `RunExecutor` với các bước: khởi tạo → xử lý từng batch → hoàn tất. Trạng thái sau mỗi batch tuần tự hóa được thành JSON (prediction theo ảnh, số liệu trung gian cho ASR và false positive, danh sách ứng viên failure case).
- `RunExecutor` giữ nguyên các hành vi đã chốt ở Phase 2: áp lại mask sau `generate` (FGSM của ART bỏ qua mask), lọc prediction như pipeline mAP rồi ghép một-một, top-K ứng viên chép riêng ảnh (không giữ view của batch), lỗi khi dựng attack → run `failed`. Test nghiệm thu Phase 2 là thước đo.
- Checkpoint chứa prediction sau tấn công **đã lọc class đích** (không chứa ảnh), thống kê từng ảnh (`ImageAttackStats`) và khóa ứng viên, để `finalize` tính lại mAP mà không chạy lại model.
- CLI `advertest run` của Phase 2 dùng lại `RunExecutor` và cho kết quả như trước.
- CLI giữ bố cục `LocalStore` của Phase 2 (`runs/<fingerprint>/`, `reruns/`, `attempts/`); MinIO dùng `runs/<run_id>/` vì quyết định cache nằm ở DB.
- `ArtifactStore` có thêm cài đặt `MinioStore`; worker chỉ ghi qua presigned URL.

### Compute target và token
- `advertest-admin compute-target create --name local-dev --kind local --gpu-model ... --time-limit 7200` tạo target và in token **một lần duy nhất**; DB chỉ lưu sha256 của token.
- `advertest-admin compute-target rotate-token <name>` tạo token mới, token cũ mất hiệu lực ngay.
- Phase này chỉ chấp nhận `kind = local`, `billing_mode = none`.

### API nội bộ cho worker (`/internal/worker`, bearer token)
| Endpoint | Hành vi |
|---|---|
| `POST /lease` | Trả experiment `queued` cũ nhất dành cho target của token (hoặc experiment `running` có lease đã hết hạn), đặt lease 60 giây; không có thì `204` |
| `GET /experiments/{id}/bundle` | Trả `WorkerJobBundle` với presigned URL tải (hết hạn sau 15 phút) |
| `POST /heartbeat` | Gia hạn lease 60 giây; trả `WorkerDirective` |
| `POST /runs/{id}/start` | Nhận `RunStartRequest`; nếu đã có run `completed` cùng fingerprint ở bất kỳ experiment nào thì trả `skip_cached` kèm kết quả; ngược lại chuyển run sang `running` và trả `run` |
| `POST /runs/{id}/progress` | Nhận `ProgressReport`; cộng dồn thời gian xử lý; trả `WorkerDirective` |
| `POST /runs/{id}/artifact-url` | Trả presigned PUT URL cho một khóa **nằm trong** `runs/<run_id>/`, hết hạn sau 15 phút |
| `POST /runs/{id}/complete` | Nhận `RunCompletion`; kiểm tra hợp lệ theo contract, `failure_case_ids` khớp `failure_cases`, mọi khóa artifact nằm trong `runs/<run_id>/` và tồn tại trong MinIO; ghi run và `failure_cases` vào DB |
| `POST /cost-profiles` | Nhận `CostProfile` cho target của token |

- Token của target A gọi bất kỳ endpoint nào cho experiment thuộc target B → `403`.
- Mọi thay đổi trạng thái do API thực hiện; worker không có thông tin đăng nhập DB hay MinIO.

### Luồng xử lý của worker
- Worker là package `advertest_worker`, lệnh `advertest-worker run|calibrate`; client HTTP dùng `httpx`.
- Cách chạy mặc định trên máy phát triển: chạy trực tiếp (`uv run advertest-worker run`). Compose có profile `cpu` (CI, test manifest trong Docker) và profile `gpu` (nvidia runtime, kiểm khi có máy GPU).
- Fingerprint: image Docker của worker đặt biến `GIT_COMMIT` và `DOCKER_IMAGE_DIGEST` (Phase 2); chạy ngoài Docker thì lấy như CLI (`git rev-parse`, `git_dirty` bỏ qua `.ai-log/`).

1. Gọi `lease` theo chu kỳ (mặc định 5 giây khi rảnh).
2. Nhận bundle; tải model và ảnh của slice về cache local theo sha256 (chỉ tải ảnh chưa có).
3. Nếu chưa có cost profile cho (target, model, attack), chạy calibration trước.
4. Với từng run theo thứ tự: tính fingerprint → `start` → nếu `skip_cached` thì chuyển sang run kế → nếu `run` thì xử lý từng batch, sau mỗi batch lưu checkpoint lên MinIO và gọi `progress`.
5. Làm theo `WorkerDirective`: `cancel` hoặc `stop_limit` thì dừng ngay sau batch hiện tại.
6. Heartbeat chạy ở luồng riêng mỗi 15 giây.
7. Hoàn tất run: chọn failure case cuối từ ứng viên, tạo thumbnail, upload, gọi `complete`, xóa ứng viên không được chọn.

### Failure case trong chế độ batch
- Sau mỗi batch, worker giữ danh sách top-K ứng viên theo `severity_score` (quy tắc xác định như Phase 2). Ảnh của ứng viên mới được upload vào `candidates/`; danh sách ứng viên nằm trong checkpoint.
- Khi hoàn tất: ứng viên được chọn chép sang `cases/<case_id>/`, ứng viên còn lại bị xóa (chúng chưa phải kết quả).
- Thumbnail: rộng 320 px, định dạng WebP, cho ảnh sạch và ảnh sau tấn công.

### Checkpoint và chạy tiếp
- Checkpoint sau batch k chứa đủ trạng thái để xử lý từ batch k+1.
- Lease hết hạn (worker chết, máy treo) → experiment được lease lại; bundle chứa checkpoint mới nhất; worker tiếp tục từ batch kế tiếp.
- Mỗi ảnh được tính vào metric **đúng một lần**, kể cả khi bị gián đoạn nhiều lần.

### Trạng thái
| Tình huống | Run hiện tại | Run chưa chạy | Experiment |
|---|---|---|---|
| Mọi run xong | `completed` | — | `completed` |
| Trùng fingerprint | `skipped` (`cached`), có `cached_from_run_id`, metric sao chép từ run gốc | — | — |
| Model không hỗ trợ gradient | `skipped` (`incompatible`) | — | — |
| Ngoại lệ trong run | `failed` kèm thông điệp | Tiếp tục chạy | — |
| Chạm giới hạn thời gian | `stopped_limit` (`time`), metric trên phần ảnh đã xử lý, `metrics.partial = true` | `stopped_limit` (`time`), `images_done = 0` | `completed` |
| Hủy | `cancelled` | `cancelled` | `cancelled` |

- Experiment chuyển `queued → running` khi được lease lần đầu.

### Giới hạn thời gian
- Thời gian tính = tổng thời gian xử lý các batch (không tính thời gian chờ trong hàng đợi hay thời gian worker bị gián đoạn).
- API giữ số liệu cộng dồn và trả `remaining_seconds` trong mỗi `WorkerDirective`.
- Worker dừng khi thời gian còn lại không đủ cho batch tiếp theo theo cost profile.
- Giá trị mặc định lấy từ `default_time_limit_s` của compute target.

### Calibration và ước lượng
- `advertest-worker calibrate` (hoặc tự động trước job): chạy trên n = min(20, số ảnh của slice) ảnh đầu; tăng dần batch size (1, 2, 4, ...) tối đa min(n, 32); dừng khi hết VRAM (lùi một bậc) hoặc, trên CPU, khi `sec_per_image` không giảm so với bậc trước (giữ bậc trước); đo `sec_per_image` và `peak_vram_mb` ở batch size được chọn; gửi `CostProfile`.
- Worker dùng batch size trong cost profile khi chạy.
- Hàm ước lượng ở backend: `thời_gian ≈ Σ_run (số ảnh × sec_per_image) × 1.2`. `advertest-admin submit` in ước lượng này; thiếu cost profile thì báo "chưa có ước lượng".

### CLI quản trị (`advertest-admin`, chạy trong container `api`)
- `import-local --store data/store`: đăng ký model, dataset version, slice, mapping từ `LocalStore` vào DB và MinIO. Chỉ upload ảnh thuộc các slice được đăng ký.
- `submit --config <yaml> --target <name> [--time-limit s] --as <email>`: tạo experiment `queued` gắn protocol `dev-open`, lập danh sách run. `<yaml>` theo `LocalRunConfig` của Phase 2 (id là `content_id` nên trùng giữa `LocalStore` và DB sau `import-local`); `device`, `batch_size` bị bỏ qua (worker dùng cost profile).
- `experiment list`, `experiment show <id> [--watch]`: trạng thái experiment, từng run, tiến độ, thời gian đã dùng.
- `experiment cancel <id> --as <email>`.
- Mỗi lệnh ghi thao tác vào `audit_log` với actor là người dùng trong `--as` (phải là admin `active`).

### Protocol phát triển
- Migration seed một protocol `dev-open` có `status = dev`, không ràng buộc attack.
- Experiment gắn protocol `status = dev` không bao giờ được gửi duyệt (luật này được kiểm tra ở Phase 8; phase này chỉ tạo trạng thái).

## Decisions

- **Gửi experiment qua CLI quản trị, không mở endpoint HTTP khi chưa có xác thực.** *Lý do:* tránh tạo cơ chế xác thực tạm thời, thứ rất dễ bị quên và thành lỗ hổng. Endpoint công khai cho experiment ra đời ở Phase 5, sau khi Phase 4 có xác thực.
- **Fingerprint do worker tính, API quyết định dùng cache.** *Lý do:* fingerprint gồm git commit, phiên bản thư viện, Docker image, chỉ worker mới biết; còn quyết định bỏ qua phải dựa trên dữ liệu toàn hệ thống, chỉ API có.
- **Worker không có thông tin đăng nhập DB và MinIO.** *Lý do:* chuẩn bị cho máy thuê ở Phase 9: máy nằm ngoài tầm kiểm soát thì chỉ nên có token hẹp và URL tạm thời.
- **Presigned URL giới hạn trong thư mục của run.** *Lý do:* worker không thể ghi đè artifact của run khác.
- **Lease 60 giây, heartbeat 15 giây.** *Lý do:* phát hiện worker chết trong khoảng một phút mà không tạo quá nhiều request.
- **Checkpoint theo batch, lưu cả ứng viên failure case.** *Lý do:* máy local đôi khi bị treo; chạy lại từ đầu với PGD trên 300 ảnh là lãng phí và kết quả không được tính trùng.
- **Chỉ upload ảnh thuộc slice được đăng ký.** *Lý do:* tránh nhân đôi toàn bộ KITTI (vài GB) trên cùng một máy.
- **Giới hạn thời gian tính theo thời gian xử lý, không theo thời gian thực.** *Lý do:* thời gian máy bị treo hoặc chờ hàng đợi không phải do experiment tiêu tốn.
- **Run bị cache sao chép metric từ run gốc.** *Lý do:* đường cong của experiment hiển thị đầy đủ mà không phải truy vấn chéo; `cached_from_run_id` giữ nguồn gốc.
- **Failure case gửi kèm `complete`, không để API đọc từ MinIO.** *Lý do:* kiểm tra hợp lệ tập trung ở API; API không phải tin file do worker tự ghi.
- **`FailureCaseRecord.id` gồm `run_id`.** *Lý do:* cùng fingerprint có thể có nhiều run tạo case (hai worker chạy đồng thời, chạy lại sau `stopped_limit` hoặc `failed`); run bị cache dùng lại `failure_case_ids` của run gốc.

## Context

- `mission.md` nguyên tắc 3 (chỉ worker ghi kết quả, kết quả bất biến), 5 (giới hạn), 6 (trạng thái rõ).
- `tech-stack.md` mục 1 (kiến trúc), 4.1, 4.2 (compute target, giới hạn), 4.3 (enum), 4.4 (tái lập).
- Phase 0: DB schema, OpenAPI khung, docker compose, bucket MinIO.
- Phase 1–2: `LocalStore`, loader, estimator, attack, metric, fingerprint, manifest, CLI `advertest run`.
- Máy local là laptop GPU VRAM thấp, đôi khi bị treo: calibration và chạy tiếp sau gián đoạn là bắt buộc, không phải tùy chọn.

## Open Questions

- [x] Worker chạy trong Docker (cần nvidia-container-toolkit) hay trực tiếp trên máy: chạy trực tiếp là mặc định; Docker profile `cpu` cho CI; profile `gpu` là tồn đọng khi có máy GPU (mục Luồng xử lý của worker).
- [x] Giới hạn thời gian mặc định cho máy local: 2 giờ, theo `tech-stack.md` mục 4.2 (DB mặc định 7200).
- [x] `FailureCaseRecord.id = content_id(fingerprint, image_id)` (Phase 2): hai run cùng fingerprint chạy đồng thời (hai worker, trước khi run đầu `completed`) sẽ tạo case trùng `id` trong bảng `failure_cases`. Chặn ở `start` (fingerprint đang `running` → chờ) hay cho `id` gồm `run_id`? → `id` gồm `run_id` (Decisions).
