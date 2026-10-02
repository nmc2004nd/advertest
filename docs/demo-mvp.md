# Chạy, kiểm thử và demo MVP (Phase 0–8)

Tài liệu này hướng dẫn dựng AdverTest trên một máy (laptop, có hoặc không có GPU), chạy bộ kiểm thử tự động, rồi demo luồng chính của MVP: **reviewer chốt protocol → engineer chạy experiment → gửi duyệt → reviewer khác review và chấp nhận → report chính thức → người ngoài xác minh file**.

Chi tiết vận hành worker xem [`van-hanh-worker.md`](van-hanh-worker.md).

## 1. Chuẩn bị máy

| Cần | Ghi chú |
|---|---|
| Docker và Docker Compose v2 | Chạy Postgres, MinIO, Mailpit, API, frontend |
| `uv` | Môi trường Python (worker, CLI, test) |
| Node 22 và `pnpm` | Chỉ cần cho test frontend và E2E (frontend trong Compose tự cài) |
| `make`, `git` | |
| Mạng ở lần đầu | Tải image, gói Python/Node, fixture |

```bash
git clone https://github.com/nmc2004nd/advertest.git && cd advertest
uv sync --extra cpu              # máy có GPU NVIDIA: --extra cuda
pnpm --dir frontend install
pnpm --dir frontend exec playwright install chromium   # chỉ cần cho E2E
make fixtures                    # 5 ảnh KITTI và YOLOv8n vào tests/fixtures/, kiểm sha256
```

## 2. Kiểm thử tự động

| Lệnh | Kiểm gì | Thời gian (máy dev, CPU) |
|---|---|---|
| `make check` | Lint, type check, contract khớp bản đã commit, unit test, test nghiệm thu không cần DB | ~4 phút |
| `make test-db` | Test cần Postgres và MinIO thật (gồm test nghiệm thu Phase 5–8, worker CPU thật) | ~25 phút |
| `make test-e2e` | Playwright trên 3 viewport (điện thoại 390px, tablet, desktop), backend và worker thật | ~8 phút |
| `pnpm --dir frontend verify:build` | Build production không chứa trang dev hay dữ liệu mock | ~1 phút |

`make test-db` và `make test-e2e` tự dựng Postgres và MinIO tạm rồi xóa đi; không đụng tới dữ liệu demo.

Kết quả tham chiếu (2026-10-02, `main`): `make check` pass; `make test-db` 694 test pass; `make test-e2e` 90/90.

## 3. Khởi động hệ thống

```bash
cp .env.example .env
```

Sửa `.env`:
- thay mọi giá trị `change-me-*` (chỉ dùng chữ và số);
- đặt `ADVERTEST_ADMIN_EMAIL`, `ADVERTEST_ADMIN_PASSWORD` cho tài khoản admin đầu tiên;
- bỏ dấu `#` và đặt `ADVERTEST_DATA_DIR` = đường dẫn **tuyệt đối** tới thư mục `data/` của repo;
- giữ `DEV_ALLOW_UNBLURRED=false` khi demo.

```bash
GIT_COMMIT=$(git rev-parse HEAD) make up        # build và chờ mọi service healthy
set -a; . ./.env; set +a
docker compose -f docker/compose.yaml --env-file .env exec \
  -e ADVERTEST_ADMIN_EMAIL -e ADVERTEST_ADMIN_PASSWORD api python -m backend.admin_cli.seed
admin() { docker compose -f docker/compose.yaml --env-file .env exec api advertest-admin "$@"; }
```

`seed` nạp attack catalog, compute target `local-dev` và tài khoản admin.

| Địa chỉ | Dùng để |
|---|---|
| http://localhost:5173 | Ứng dụng web |
| http://127.0.0.1:8000/health | Trạng thái API (`status: ok` khi Postgres và MinIO đều ổn) |
| http://127.0.0.1:8025 | Mailpit: xem email hệ thống gửi (gửi duyệt, quyết định, experiment xong) |
| http://127.0.0.1:9001 | MinIO console |

## 4. Nạp dữ liệu

Container `api` chỉ đọc được ảnh nằm trong `ADVERTEST_DATA_DIR`. Vì vậy chép dữ liệu vào đó **trước khi** import.

### Cách nhanh: fixture 5 ảnh (đủ cho demo trên CPU)

```bash
# Máy có GPU: thay --extra cpu bằng --extra cuda trong các lệnh dưới (uv run đồng bộ theo extra).
# Ultralytics in thông báo ra stdout ở lần import đầu, làm hỏng JSON của CLI: import trước một lần.
uv run --extra cpu python -c "import ultralytics" >/dev/null
cp -r tests/fixtures/kitti "$ADVERTEST_DATA_DIR/kitti-fixture"
STORE="$ADVERTEST_DATA_DIR/store"
field() { uv run --extra cpu python -c "import json,sys; print(json.load(sys.stdin)['$1'])"; }
DATASET=$(uv run --extra cpu advertest --store-dir "$STORE" dataset import-kitti --root "$ADVERTEST_DATA_DIR/kitti-fixture" | field dataset_version_sha256)
MODEL=$(uv run --extra cpu advertest --store-dir "$STORE" model register --weights tests/fixtures/yolov8n.pt --name yolov8n-coco | field id)
uv run --extra cpu advertest --store-dir "$STORE" slice create --dataset "$DATASET" --size 5 --seed 42
uv run --extra cpu advertest --store-dir "$STORE" mapping create --dataset "$DATASET" --model "$MODEL"
docker compose -f docker/compose.yaml --env-file .env exec -u "$(id -u):$(id -g)" api \
  advertest-admin import-local --store "$STORE" --as "$ADVERTEST_ADMIN_EMAIL"
```

### Dữ liệu KITTI thật (tùy chọn)

KITTI cần đăng nhập để tải nên không có script tự tải. Đặt bộ `training/` (gồm `image_2/`, `label_2/`) vào `"$ADVERTEST_DATA_DIR/kitti"`, rồi chạy các lệnh trên với `--root "$ADVERTEST_DATA_DIR/kitti"`. Tạo slice lớn hơn, ví dụ `--size 300`.

Trên CPU, slice 300 ảnh với PGD mất nhiều giờ; nên chạy worker trên máy có GPU.

## 5. Chạy worker

```bash
TOKEN=$(admin compute-target rotate-token local-dev --as "$ADVERTEST_ADMIN_EMAIL" | tail -n 1)
export API_URL=http://127.0.0.1:8000 WORKER_TOKEN="$TOKEN"
export GIT_COMMIT=$(git rev-parse HEAD)   # không đặt thì run bị gắn "code chưa commit" khi working tree có thay đổi
uv run --extra cpu advertest-worker run   # máy có GPU: --extra cuda
```

Token chỉ hiện một lần. Để worker chạy ở một terminal riêng suốt buổi demo; lần chạy đầu worker tự đo chi phí (calibration).

## 6. Tạo tài khoản demo

Cần **ba tài khoản khác nhau**, vì người chạy test không được tự duyệt test của mình:

| Tài khoản | Role | Việc trong demo |
|---|---|---|
| Admin (đã seed) | admin | Duyệt tài khoản mới |
| Reviewer | reviewer | Tạo protocol; review, ra quyết định; tải report |
| Engineer | engineer | Tạo và chạy experiment, gửi duyệt |

1. Mở http://localhost:5173 → **Yêu cầu truy cập**, tạo yêu cầu cho reviewer và engineer, mỗi người một email.
2. Đăng nhập admin → **Người dùng** → tab **Chờ duyệt** → **Duyệt**, chọn đúng role cho từng người.

Nên mở mỗi tài khoản trong một cửa sổ trình duyệt riêng (hoặc một cửa sổ ẩn danh), để chuyển vai nhanh khi demo.

## 7. Kịch bản demo MVP

### Bước 1: reviewer chốt protocol (tiêu chí có trước khi chạy)

Reviewer → **Protocol** → **Tạo protocol**:
- tên `kitti-demo`, mục đích bất kỳ, kích thước slice tối thiểu `5` (fixture) hoặc `300` (KITTI thật), số case review mỗi attack `2`;
- giữ ô **Không chấp nhận run chạy từ code chưa commit**;
- attack bắt buộc: `fgsm`, chế độ **Quét lưới**, level `2, 4`;
- tiêu chí: **Mức sụt tối đa tại một level**, attack `fgsm`, level `4`, mức sụt tối đa `60` (%).

Điểm cần nói: protocol không sửa được sau khi tạo; muốn đổi phải tạo version mới, và version cũ tự ngừng dùng.

### Bước 2: engineer chạy experiment theo protocol

Engineer → **Tạo experiment**:
1. Chọn `kitti-demo`.
2. Chọn model `yolov8n-coco`, dataset và slice.
3. Bước Tấn công: `fgsm` đã được thêm sẵn, **khóa "Theo protocol"**, không bỏ chọn được. Bảng tuân thủ ✓/✗ cập nhật trực tiếp.
4. **Chạy** → xác nhận.

Trang chi tiết tự cập nhật tiến độ tới **completed**; xem các tab Kết quả, Failure case.

Điểm cần nói: thử bỏ bớt attack hay bớt level đều không tạo được (lỗi tuân thủ).

### Bước 3: gửi duyệt và khóa

Engineer → **Gửi duyệt** → xác nhận. Trang hiện dải **"Đã khóa – đang chờ duyệt"**; không hủy hay sửa được nữa, vẫn bình luận được. Mailpit có email gửi cho reviewer.

### Bước 4: reviewer review

Reviewer → **Duyệt** → tab **Chờ nhận** → mở experiment → **Nhận review**.
- Xem tuân thủ, kết quả tiêu chí (tham khảo), danh sách kiểm tra trước khi chấp nhận.
- Nút **Chấp nhận** đang khóa, có lý do bên dưới: chưa review đủ case bắt buộc.
- Mở một **case bắt buộc**:
  - **Desktop:** phím `?` hiện bảng phím tắt; `3` = mức Nhỏ, `A` = Chấp nhận được, `Ctrl+Enter` lưu, `J` sang case sau.
  - **Điện thoại:** vuốt ngang để chuyển case; nút **Ghi verdict** mở form ở bottom sheet.

### Bước 5: quyết định

Quay lại trang review: tiến độ đủ (ví dụ "2/2 đã review"). Điền **Kết luận**, **Biện pháp khắc phục**, chọn **Kết luận về model** → **Chấp nhận** → xác nhận.

Điểm cần nói: chấp nhận là chấp nhận *bài test*. Kết luận về model có thể là "không đạt tiêu chí".

Lựa chọn khác:
- **Yêu cầu sửa:** engineer thấy quyết định và nút **Nhân bản để sửa**; wizard mở với cấu hình cũ.

### Bước 6: report chính thức và xác minh

1. Reviewer → **Report** → mở report vừa sinh (vài giây sau khi chấp nhận). Trang hiện dải **BẢN CHÍNH THỨC**, mã report, đủ 9 mục.
2. **Tải PDF**. Mỗi trang PDF có chân trang ghi mã report và link xác minh. Engineer xem được report nhưng không có nút tải.
3. Mở `/verify/<mã report>` ở cửa sổ **chưa đăng nhập** → chọn file PDF vừa tải → **Khớp**.
4. Sửa 1 byte của file (hoặc chọn một PDF khác) → **Không khớp**.

Điểm cần nói: hash tính ngay trong trình duyệt, file không gửi lên server.

`/verify` cần HTTPS hoặc `localhost`; mở bằng IP trong mạng LAN qua HTTP thì trang báo cần HTTPS.

### Bước 7 (tùy chọn): tách quyền và chống gian lận

- Tạo người dùng có cả hai role engineer và reviewer: experiment của chính họ không xuất hiện trong hàng đợi, và vào thẳng trang review thì không có nút nhận.
- Report liệt kê mọi experiment khác cùng model và dataset (kể cả lần chạy không gửi duyệt hay đã hủy), nên không giấu được các lần chạy xấu.
- **Audit log** (admin) ghi mọi bước: gửi duyệt, nhận, verdict, quyết định, sinh và tải report.

## 8. Sự cố thường gặp

| Triệu chứng | Cách xử lý |
|---|---|
| `make up` không healthy | `docker compose -f docker/compose.yaml --env-file .env logs api`; kiểm tra mật khẩu trong `.env` chỉ có chữ và số |
| Lệnh `advertest` báo lỗi JSON (`field`) | Chạy `uv run --extra cpu python -c "import ultralytics"` một lần rồi chạy lại lệnh |
| `import-local` báo không đọc được ảnh | Ảnh phải nằm trong `ADVERTEST_DATA_DIR` (đường dẫn tuyệt đối, cùng đường dẫn lúc `import-kitti`); chạy với `-u "$(id -u):$(id -g)"` |
| Experiment nằm mãi ở hàng đợi | Worker chưa chạy hoặc sai token; xem log worker, `admin compute-target list` |
| Gửi duyệt báo "code chưa commit" | Worker chạy khi working tree có thay đổi; đặt `GIT_COMMIT` (mục 5) hoặc commit trước khi chạy |
| Không có nút **Gửi duyệt** | Experiment chưa `completed`, hoặc đang gắn protocol `dev-open` (protocol phát triển, không gửi duyệt được) |
| Report ở "Sinh lỗi" | Reviewer bấm **Sinh lại** trên trang report; xem log `api` |
| Ảnh case bị ẩn | Case cũ chưa làm mờ (trước Phase 6); chạy lại experiment để worker làm mờ |

## 9. Dọn dẹp

```bash
make down                                          # dừng, giữ dữ liệu
docker compose -f docker/compose.yaml --env-file .env down -v   # dừng và xóa toàn bộ DB, MinIO
```
