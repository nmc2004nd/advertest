# Tech Stack: AdverTest

> File này ghi những gì dự án dùng, **cách dùng**, và những gì không dùng. Feature spec chỉ mô tả phần mở rộng, không lặp lại nội dung ở đây. Phiên bản cụ thể của từng thư viện được pin trong Phase 0 và ghi lại vào file này.

## 1. Kiến trúc tổng thể

```text
                ┌────────────┐      ┌──────────────┐      ┌───────────┐
                │  Frontend  │ ───▶ │ Backend API  │ ───▶ │ Postgres  │
                │ (React)    │      │ (FastAPI)    │      │           │
                └────────────┘      └──────┬───────┘      └───────────┘
                                           │ đọc artifact
                                           ▼
   ┌──────────────┐  lấy job (token)  ┌──────────┐  lấy job (token)  ┌────────────────┐
   │ Worker local │ ────────────────▶ │   API    │ ◀──────────────── │ Worker máy thuê│
   └──────┬───────┘                   └──────────┘                   └───────┬────────┘
          │ upload (presigned URL)    ┌──────────┐                           │
          └─────────────────────────▶ │  MinIO   │ ◀─────────────────────────┘
                                      └──────────┘
```

Quy tắc kiến trúc:
- Frontend chỉ gọi Backend API.
- Worker **không** kết nối trực tiếp vào Postgres. Worker gọi API nội bộ bằng token riêng của compute target.
- Artifact (ảnh failure case, thumbnail, patch, report) lưu trong MinIO. Worker upload bằng presigned URL do API cấp.
- Một experiment chỉ chạy trên một compute target. Máy offline thì job chờ, không tự chuyển máy.
- Máy thuê kết nối về API qua Tailscale. Postgres và MinIO không mở ra internet.

## 2. ML core

| Thành phần | Lựa chọn | Ghi chú |
|---|---|---|
| Ngôn ngữ | Python 3.11 | Dùng chung cho ML core, attack, backend, worker |
| Deep learning | PyTorch | |
| Model chính | Ultralytics YOLOv8/v11 | Cần wrapper tự viết cho ART (xem 2.1) |
| Model dự phòng | torchvision Faster R-CNN + `PyTorchFasterRCNN` của ART | Dùng nếu wrapper YOLO không cho gradient đúng sau khoảng 2 ngày |
| Metric | `torchmetrics` `MeanAveragePrecision` | Backend `pycocotools` (Phase 1) |
| CLI | Typer | Lệnh `advertest` cho ML core |
| Xử lý và vẽ ảnh | Pillow | Đọc ảnh dataset, vẽ box cho `viz` |
| Dataset mặc định | KITTI 2D object | Tập đánh giá cố định khoảng 300 ảnh |

### 2.1. Quy ước dữ liệu (bắt buộc)

- Ảnh đưa vào model và attack: `numpy.float32`, **channels_first** (N, C, H, W), giá trị trong **[0, 1]**, letterbox về **640×640**.
- Toàn bộ pipeline tính toán trong không gian ảnh đã letterbox. Chỉ chuyển ngược về tọa độ ảnh gốc khi hiển thị.
- Box: định dạng **xyxy**, tọa độ pixel tuyệt đối trong không gian đã letterbox.
- Label của detector (theo ART): list các dict `{"boxes", "labels", "scores"}`.
- Định dạng dataset nội bộ: manifest JSON kiểu COCO. Mọi định dạng khác (YOLO, COCO, KITTI) phải đi qua converter.
- Dataset version = sha256 của manifest (manifest chứa hash từng ảnh và annotation). Sửa bất kỳ thứ gì là tạo version mới.
- Slice lưu **danh sách image ID cụ thể** kèm seed, không chỉ lưu điều kiện lọc.
- Map class dataset → class model là bước bắt buộc khi import. Class không map được bị loại khỏi metric và phải ghi trong report.

### 2.2. Wrapper model

- Wrapper phải có hai chế độ: tính loss (để ART lấy gradient) và predict (trả box sau NMS).
- Model trong registry có cờ `supports_gradients`, chỉ bật sau khi bài kiểm tra gradient tự động pass.

### 2.3. Định nghĩa metric

- **Metric chính:** mAP@0.5. Metric phụ: mAP@0.5:0.95.
- **Mức sụt tương đối** (mặc định cho ngưỡng): `(mAP_sạch − mAP_tấn_công) / mAP_sạch`.
- **Tỷ lệ tấn công thành công:** trong số object được detect đúng trên ảnh sạch (IoU ≥ 0.5, đúng class), tỷ lệ bị mất hoặc sai class sau tấn công.
- Khoảng tin cậy: bootstrap trên prediction đã lưu, không tốn thêm GPU. AP@0.5 của mẫu bootstrap tính bằng cài đặt riêng (`ml_core/metrics/bootstrap.py`, ghép COCO ở IoU 0.5 theo ảnh, trọng số theo ảnh) và phải khớp `CleanMetric`, kể cả dãy 101 ngưỡng recall float32 mà torchmetrics truyền cho pycocotools (ghi cứng theo torch 2.14; test so với `torch.linspace` báo khi nâng torch làm đổi dãy) (Phase 7).
- Prediction trên ảnh sạch được cache theo (model version, slice).

## 3. Attack

| Thành phần | Lựa chọn |
|---|---|
| Thư viện attack | Adversarial Robustness Toolbox (ART) |
| White-box | `FastGradientMethod` (FGSM), `ProjectedGradientDescent` (L∞, L2), `AdversarialPatchPyTorch` hoặc `RobustDPatch` |
| Corruption | Bản vá nội bộ của `imagecorruptions` 1.1.2 trong `attacks/corruptions/` (giữ LICENSE và tham số gốc; bản gốc cần `pkg_resources` và dùng `np.float_`, Phase 6) |
| Occlusion | Tự viết, che theo tỷ lệ diện tích bounding box |

### 3.1. Interface chung (bắt buộc)

Mọi phép biến đổi, dù là attack ART hay corruption, đều cài đặt cùng một interface:

```python
class Perturbation(Protocol):
    spec: AttackSpec                      # định nghĩa trong contracts/
    def apply(self, images: np.ndarray,   # (N, C, H, W), float32, [0, 1]
              targets: list[dict],
              level: float,               # giá trị tham số chính đang quét
              seed: int,
              mask: np.ndarray | None = None  # (N, 1, H, W), float32: 1 vùng ảnh thật, 0 vùng pad
              ) -> np.ndarray: ...
```

Điểm ảnh có `mask = 0` phải giữ nguyên (so sánh chính xác); `mask = None` là biến đổi toàn ảnh (Phase 2).

Tầng sweep, metric, backend và frontend không được phụ thuộc vào việc bên dưới là ART hay thư viện khác.

### 3.2. Quy ước attack

- Mỗi attack có **một tham số chính** để quét. Các tham số còn lại cố định trong spec.
- PGD: bước nhảy **tỷ lệ theo eps** (mặc định eps/4), 10 bước.
- Patch attack được train một lần, lưu vào MinIO, tái sử dụng. Không train patch theo từng job.
- Mặc định tấn công **untargeted** (làm object biến mất).
- Attack spec có trường `access: white_box | black_box` (hiện chỉ dùng `white_box`).
- Attack white-box trên model không có `supports_gradients` → run bị `skipped` kèm lý do.

### 3.3. Tự tìm ngưỡng

- Thuật toán: quét thô vài điểm để khoanh vùng → chia đôi đến độ chính xác yêu cầu → xác nhận hai đầu khoảng trên toàn slice.
- Giai đoạn tìm kiếm chạy trên tập con cố định của slice (khoảng 100 ảnh).
- Số điểm tối đa được tính trước để hiển thị chi phí tối đa.
- Trạng thái kết quả: `found`, `not_reached`, `below_min`, `stopped_limit`, `non_monotonic`, `failed` (Phase 7: mAP sạch bằng 0, không còn object cho ASR, lỗi không phục hồi).

## 4. Backend và worker

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Web framework | FastAPI | Cùng ngôn ngữ với ML core, có sẵn OpenAPI |
| Validation | Pydantic v2 | Dùng chung schema với contract |
| Database | PostgreSQL 17 | Nhiều người dùng, ghi đồng thời, phân quyền ở cấp DB cho audit log |
| Driver Postgres | psycopg 3 | Một driver cho cả sync (Alembic, script) và async (API) |
| ORM / migration | SQLAlchemy 2 + Alembic | Migration có version, review được |
| Object storage | MinIO (API tương thích S3), image `cgr.dev/chainguard/minio` pin theo digest | Worker ở nhiều máy cùng ghi được. Image chính thức `minio/minio` đã ngừng phát hành công khai |
| Server ASGI | uvicorn | Chạy API trong container |
| Client S3 | boto3 | Kiểm tra MinIO ở `/health`; presigned URL ở Phase 3 |
| Mật khẩu | argon2 (`argon2-cffi`) | |
| Phiên đăng nhập | Phiên phía server: cookie httpOnly chứa token ngẫu nhiên, DB lưu sha256 của token (Phase 4) | Vô hiệu hóa tài khoản, đổi role và đăng xuất phải có hiệu lực ngay; với JWT vẫn phải tra DB mỗi request |
| Report PDF | WeasyPrint (render HTML → PDF ở server) | |
| Mẫu report | Jinja2 (Phase 8) | Render HTML của report trước khi chuyển PDF |
| Biểu đồ report | matplotlib (Phase 8), PNG nhúng vào PDF | Frontend vẫn dùng Recharts; ảnh trong PDF phải sinh ở server. Image cần thư viện hệ thống của WeasyPrint (pango) và font có dấu tiếng Việt (DejaVu); phiên bản ở mục 11 |
| Email | SMTP | Thông báo run xong, chờ duyệt, ngân sách |
| Hàng đợi | Bảng job trong Postgres, worker lấy qua API | Không dùng Celery/Redis: quy mô nhỏ, ít hạ tầng |

### 4.1. Quy ước backend

- Mọi endpoint không công khai (trừ `/internal/worker`) khai báo quyền bằng dependency `require_permission(...)` theo ma trận `ROLE_PERMISSIONS` trong contract, và khai `x-permission` trong OpenAPI (giá trị `authenticated` cho endpoint chỉ cần đăng nhập). Role và trạng thái user đọc từ DB mỗi request. Luật phụ thuộc đối tượng (chỉ hủy experiment của mình, "không tự review") kiểm tra ở tầng service.
- Chỉ tài khoản hệ thống của worker được ghi metric và kết quả. API của người dùng không có endpoint ghi metric.
- User ứng dụng trong Postgres bị thu hồi quyền `UPDATE` và `DELETE` trên bảng `audit_log`.
- Role `advertest_owner` và `advertest_app` được tạo bằng script init của Postgres (`docker/postgres/init/`), không tạo trong migration. Mỗi migration tự `GRANT` quyền cho `advertest_app` trên bảng nó tạo; test `test_every_table_is_granted_to_app` sẽ fail nếu quên.
- Alembic đọc `MIGRATION_DATABASE_URL` (role owner); ứng dụng và script đọc `DATABASE_URL` (role app).
- Biến môi trường khác của API: `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `GIT_COMMIT` (image Docker không có `.git`). Cookie phiên tên `advertest_session`.
- Endpoint công khai (`/health`, `/verify`) không trả chi tiết lỗi nội bộ (host, user, stack trace); chi tiết chỉ ghi vào log server.
- Verdict review có version, không ghi đè.
- ID dùng UUID (uuid5 của hash nội dung khi có thể, qua `advertest_contracts.ids.content_id`). Thời gian lưu UTC; schema từ chối múi giờ khác.
- Số tiền dùng số thập phân (`Decimal`), trong JSON là chuỗi, để tránh sai số float khi cộng dồn ledger. Chuẩn hóa số chữ số thập phân trước khi hash.
- Hash dùng sha256 trên JSON chuẩn hóa theo RFC 8785 (JCS): key sắp xếp, không khoảng trắng thừa, số viết theo quy tắc ECMAScript (`advertest_contracts.hashing.canonical_json`).

### 4.2. Compute target và giới hạn

- Bảng `compute_targets`: tên, loại (`local` | `rented`), model GPU, VRAM, `billing_mode` (`none` | `hourly`), giá mỗi giờ, token, heartbeat.
- `billing_mode = hourly`: ledger giữ chỗ khi submit, quyết toán khi xong, trần ngân sách bắt buộc, theo dõi uptime và thời gian chạy không.
- `billing_mode = none`: không ghi ledger, dùng trần thời gian (mặc định 2 giờ, admin chỉnh được).
- Cost profile (giây/ảnh, VRAM tối đa) đo bằng calibration **riêng cho từng compute target**. Batch size lấy từ cost profile, không đặt cứng.
- Worker kiểm tra giới hạn sau mỗi batch; chạm giới hạn thì dừng với `stopped_limit` và `reason` (`budget` | `time`).
- Worker lưu tiến độ sau mỗi batch và chạy tiếp được sau khi bị gián đoạn.

### 4.3. Trạng thái (enum dùng chung)

| Đối tượng | Giá trị |
|---|---|
| User | `pending`, `active`, `rejected`, `disabled` |
| Run | `queued`, `running`, `completed`, `failed`, `skipped`, `stopped_limit`, `cancelled` |
| Experiment | `draft`, `queued`, `running`, `completed`, `submitted_for_review`, `in_review`, `approved`, `changes_requested`, `rejected`, `cancelled` |
| Kết quả tìm ngưỡng | `found`, `not_reached`, `below_min`, `stopped_limit`, `non_monotonic`, `failed` |

Mọi trạng thái bất thường (`failed`, `skipped`, `stopped_limit`, `cancelled`) phải có trường lý do.

### 4.4. Tái lập

- **Fingerprint của run** = hash của: config chuẩn hóa, hash weights, dataset version, slice ID, attack spec version, tham số, seed, git commit, phiên bản torch/ART/ultralytics, digest Docker image.
- Fingerprint **không** gồm compute target và model GPU (để dùng lại kết quả giữa các máy). Hai thông tin này ghi trong manifest.
- Mỗi run có `manifest.json` trong MinIO.
- Fingerprint trùng với run đã hoàn thành → `skipped` với lý do `cached`.
- Kết quả có thể phụ thuộc nhẹ vào batch size (đo ở Phase 3: PGD trên KITTI, batch 2 so với 8, lệch ≤ 0.0006 mAP@0.5, ≤ 0.006 ASR); sai số tái lập ±0.01 bao được mức này. Batch size không thuộc fingerprint.
- Chỉ lưu ảnh của failure case (kèm thumbnail). Ảnh khác tái tạo được từ manifest và seed.

## 5. Frontend

| Thành phần | Lựa chọn |
|---|---|
| Build | Vite |
| Framework | React + TypeScript (strict) |
| UI | shadcn/ui + Tailwind CSS |
| Dữ liệu từ server | TanStack Query (polling 2 giây, tắt khi tab ẩn) |
| Bảng | TanStack Table |
| Biểu đồ | Recharts |
| Routing | React Router |
| Zoom ảnh | `react-zoom-pan-pinch` |
| Font | Be Vietnam Pro, tự host qua `@fontsource/be-vietnam-pro` |
| Sinh type từ contract/OpenAPI | `openapi-typescript` (devDependency) |
| Form | `react-hook-form` + `zod` (Phase 4): validation nhất quán cho form của mọi phase |
| E2E | `@playwright/test` (devDependency, Phase 4), 3 viewport 390×844, 820×1180, 1440×900 |

### 5.1. Quy ước frontend

- Mọi quyết định thị giác (màu, font, khoảng cách, lớp overlay, câu chữ) theo `specs/design.md`.
- Mobile-first. Breakpoint: điện thoại < 768px, tablet 768–1279px, desktop ≥ 1280px.
- Box vẽ phía client trên canvas từ JSON, scale theo `devicePixelRatio`.
- Trạng thái luôn hiển thị bằng màu + icon + chữ, dùng một component badge chung.
  Nhãn tiếng Việt, icon và tông màu định nghĩa một nơi duy nhất: `frontend/src/components/status/status-config.ts`. Bảng cấu hình khai kiểu `Record<Enum, …>` theo enum của contract, nên thiếu giá trị thì `tsc` báo lỗi; test so với mảng giá trị enum sinh từ contract.
- Type cho response của API lấy từ `frontend/src/contracts/api.ts` (sinh từ `contracts/openapi.json`); mảng giá trị enum lấy từ `frontend/src/contracts/schemas.ts`. Cả hai là file sinh ra, không sửa tay.
- Biến môi trường: `VITE_USE_MOCKS=true` đọc dữ liệu từ `contracts/mocks/` thay cho API (chỉ đọc; request ghi báo lỗi); `VITE_MOCK_ME` chọn người dùng của chế độ mock (`contracts/mocks/me/<tên>.json`, mặc định `admin`); `VITE_API_BASE_URL` (mặc định rỗng, tức gọi cùng origin). Kiểm tra chế độ mock viết thẳng `import.meta.env.VITE_USE_MOCKS === 'true'` tại chỗ gọi để bản build loại bỏ nhánh mock.
- Trang chỉ dành cho dev (ví dụ `/dev/contracts`) chỉ đăng ký khi `import.meta.env.DEV`; `pnpm --dir frontend verify:build` kiểm tra bản build production không chứa chúng.
- Hành động không đảo ngược (gửi duyệt, approve) có hộp xác nhận kèm tóm tắt.
- Bản xem trước chưa duyệt có watermark "BẢN NHÁP – CHƯA DUYỆT".
- Giao diện chỉ ẩn nút theo role cho gọn; không được coi là lớp bảo mật.
- Vùng chạm tối thiểu 44×44px, font input tối thiểu 16px, xử lý `safe-area-inset`.
- Ảnh dạng danh sách dùng thumbnail; ảnh gốc chỉ tải khi zoom.

## 6. Hạ tầng

- Docker Compose (`docker/compose.yaml`) gồm: `api`, `worker` (từ Phase 3), `postgres`, `minio`, `minio-init` (tạo bucket rồi thoát), `frontend`. Biến lấy từ `ENV_FILE` (mặc định `.env`, mẫu ở `.env.example`); mật khẩu và khóa chỉ gồm chữ và số vì được ghép vào URL.
- Một image dùng chung cho `api` và `worker`, chọn biến thể torch bằng build arg `TORCH`. Phase 0 dùng `python:3.11-slim` với `TORCH=cpu`; khi có worker (Phase 3) chuyển sang image CUDA với `TORCH=cuda`.
- `api` chạy migration bằng role owner rồi chạy uvicorn bằng role app; URL của owner bị xóa khỏi môi trường của app.
- Postgres không mở cổng ra máy chủ; các cổng khác chỉ gắn vào `127.0.0.1`.
- Frontend gọi API cùng origin qua proxy `/api` của Vite (`VITE_API_BASE_URL=/api`); bản triển khai dùng reverse proxy tương tự.
- Máy thuê chạy riêng container `worker`, kết nối qua Tailscale, cấu hình bằng token của compute target.
- CI (GitHub Actions, `.github/workflows/ci.yml`), chạy trên CPU, gồm 4 job: `python` (ruff, mypy, pytest trừ test `db`), `frontend` (ESLint, Prettier, tsc, Vitest, `verify:build`), `contracts` (`make contracts-check`, validate mock và seed), `acceptance` (Postgres service container, chạy script init role từ runner, test `db` và test nghiệm thu). Cache uv, pnpm và `tests/fixtures/`.

## 7. Kiểm thử

| Lớp | Công cụ | Chạy ở đâu |
|---|---|---|
| Lint / format | ruff (Python), ESLint + Prettier (TS) | CI |
| Type check | mypy (Python), `tsc --noEmit` (TS) | CI |
| Unit test | pytest, Vitest | CI |
| Test nghiệm thu | pytest trong `tests/acceptance/` | CI |
| E2E giao diện | Playwright, 3 viewport, chạy tuần tự (`workers: 1`, các kịch bản dùng chung DB); bản build gọi API qua `/api` (`VITE_API_BASE_URL=/api`) | CI hoặc local (`make test-e2e`) |
| Truy cập | `@axe-core/playwright` | CI |
| Hiệu năng trang công khai | Lighthouse CI (`@lhci/cli`) | CI hoặc local |
| Smoke test GPU | Script chạy tay | Máy có GPU |

Quy ước:
- Fixture nhỏ chạy trên CPU: khoảng 5 ảnh + một model rất nhỏ, mỗi test chạy trong vài giây.
- So metric với golden value **có sai số**, không so bằng tuyệt đối.
- Test Vitest chạy trong môi trường node; render component bằng `react-dom/server`. Chưa dùng thư viện test DOM (Testing Library, jsdom) khi chưa được duyệt.
- Thư viện không kèm type stub (hiện là `boto3`, `botocore`, `art`, `yaml`) được khai `ignore_missing_imports` trong cấu hình mypy, không dùng `# type: ignore` trong code.
- Mỗi nguyên tắc trong `mission.md` mục 4 có ít nhất một test nghiệm thu.

## 8. Cấu trúc repo và quyền sở hữu

```text
advertest/
├── specs/                  # constitution + feature specs (chỉ người duyệt sửa)
├── contracts/              # schema dùng chung, OpenAPI, enum (chỉ người duyệt sửa)
├── ml_core/                # agent: ml-core
├── attacks/                # agent: attack
├── backend/                # agent: backend (gồm API, service, worker, migration)
├── frontend/               # agent: frontend
├── tests/
│   ├── acceptance/         # test nghiệm thu (agent chỉ đọc)
│   └── fixtures/           # dữ liệu nhỏ cho test
├── docker/
├── CLAUDE.md               # hướng dẫn cho agent
└── CHANGELOG.md
```

## 9. Luật dành cho agent code

1. Đọc `mission.md`, `tech-stack.md`, `roadmap.md` và feature spec của phase trước khi code.
2. Chỉ sửa file trong thư mục được giao. Không sửa `specs/`, `contracts/`, `tests/acceptance/`.
3. Không mở rộng phạm vi ngoài `requirements.md` của phase.
4. Gặp yêu cầu mơ hồ hoặc cần đổi contract: **dừng lại và hỏi**, không tự quyết trong code.
5. Không sửa hoặc nới test để test pass.
6. Trước khi báo xong: chạy toàn bộ lệnh trong `validation.md` của phase và báo kết quả.
7. Không thêm dependency ngoài file này khi chưa được duyệt.
8. Golden tái lập: refactor lớp chạy (runner, worker, attack, model adapter) phải giữ `FingerprintInputs` và fingerprint giống từng byte khi ghim provenance (`git_commit`, `git_dirty`, `lib_versions`, `docker_image_digest`); metric trong sai số đã định; danh sách failure case giống hệt.
9. Metadata hiển thị của attack (tên dễ đọc, mô tả, mức sát thực tế, chi phí, nhãn level) nằm ngoài `spec_sha256`; sửa metadata không tạo version mới nhưng phải ghi audit log.

## 10. Khoảng trống cần quyết định

- [x] Pin phiên bản cụ thể của PyTorch, ART, Ultralytics, torchmetrics (Phase 0). Xem mục 11.
- [ ] Chọn YOLOv8 hay YOLOv11 sau khi thử wrapper.
- [ ] Nhà cung cấp GPU thuê.
- [ ] Dịch vụ SMTP.
- [ ] Nơi triển khai API, Postgres, MinIO.
- [x] Dependency mới cho Phase R2: `onnxruntime` (adapter ONNX, chỉ inference), `safetensors` (weights upload qua web), `python-multipart` (upload ảnh thử nhanh). Đã pin ở Group 0 (mục 11).

## 11. Phiên bản đã pin (Phase 0)

Nguồn sự thật là `pyproject.toml` + `uv.lock` (Python) và `frontend/package.json` + `frontend/pnpm-lock.yaml` (frontend). Bảng dưới chỉ ghi các thư viện chính; đổi phiên bản phải cập nhật cả lockfile lẫn bảng này.

| Thư viện | Phiên bản |
|---|---|
| Python | 3.11 |
| torch / torchvision | 2.14.0 / 0.29.0 |
| adversarial-robustness-toolbox | 1.20.1 |
| ultralytics | 8.4.163 |
| torchmetrics | 1.9.0 |
| pycocotools | 2.0.11 (backend của `MeanAveragePrecision`, Phase 1) |
| typer / pillow | 0.27.2 / 12.3.0 (Phase 1) |
| pyyaml | 6.0.3 (Phase 2, đọc cấu hình `advertest run`) |
| numpy | 2.4.6 |
| fastapi | 0.141.1 |
| pydantic | 2.13.5 |
| sqlalchemy | 2.1.1 |
| alembic | 1.20.0 |
| psycopg / argon2-cffi | 3.3.6 / 25.1.0 |
| boto3 / httpx | 1.43.103 / 0.28.1 (httpx là dependency chính từ Phase 3: client của worker) |
| uvicorn | 0.54.0 |
| weasyprint / jinja2 / matplotlib | 70.0 / 3.1.6 / 3.11.2 (Phase 8, report; image cài thêm `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz-subset0`, `fonts-dejavu-core`) |
| pypdf | 6.19.0 (Phase 8, chỉ nhóm dev: đọc chữ trong PDF ở test) |
| onnxruntime / safetensors / python-multipart | 1.30.0 / 0.8.0 / 0.0.32 (Phase R2: adapter model onnx chỉ inference; weights torchvision dạng safetensors; multipart cho `POST /quick-tries`). `onnx` chỉ dùng một lần để sinh fixture (`uv run --with onnx`), không vào lock |
| Image | `python:3.11-slim`, `postgres:17-alpine`, `node:22-alpine`, `cgr.dev/chainguard/minio@sha256:6a1d0b45c8669726bba580ced0bfa4cb9fdeed1ed636dfabd81d1577beb6937b`, `cgr.dev/chainguard/minio-client@sha256:b2bd7824d23d3e3b15bedd7e87fbc3be29d2e213307b4f901e4a1d92356dc20f` |
| Postgres (image) | `postgres:17-alpine` |
| ruff / mypy / pytest | 0.16.9 / 2.3.1 / 9.1.1 |

Biến thể torch chọn bằng extra của uv, cùng một `uv.lock`:
- `cpu` (index `download.pytorch.org/whl/cpu`): máy phát triển và CI. `make` dùng mặc định (`TORCH=cpu`).
- `cuda` (index `download.pytorch.org/whl/cu126`): image Docker cho `api` và `worker`. CUDA 12.6 được chọn vì tương thích với nhiều phiên bản driver nhất trong các bản torch 2.14 phát hành (cu126, cu130, cu132).

Frontend: Vite 8, React 19, TypeScript 6 (strict), Tailwind CSS 4, shadcn/ui (style `radix-nova`, icon Lucide), TanStack Query 5, React Router 8, ESLint 10, Prettier 3, `react-hook-form` 7.89.0 và `zod` 4.6.5, `@tanstack/react-table` 9.2.4 (v9: `useTable`, `tableFeatures`, `table.FlexRender`) (Phase 4; resolver zod tự viết trong `src/components/form/`), `@playwright/test` 1.63.0 (pin chính xác vì phiên bản trình duyệt đi theo; E2E chạy bằng `make test-e2e` hoặc job CI `e2e`), `recharts` 3.10.1 cùng peer `react-is` 19.2.8 và `react-zoom-pan-pinch` 4.2.0 (Phase 5, pin chính xác). Phiên bản chính xác nằm trong `frontend/pnpm-lock.yaml`.
