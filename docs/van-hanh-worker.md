# Vận hành worker trên máy local (Phase 3)

Worker nhận job qua API nội bộ `/internal/worker` bằng token của compute target, chạy attack theo từng batch, lưu checkpoint và artifact lên MinIO qua presigned URL, và chạy tiếp được sau khi bị gián đoạn. Worker **không** có thông tin đăng nhập Postgres hay MinIO.

Cách chạy mặc định trên máy phát triển là **chạy trực tiếp** (`uv run --extra cuda advertest-worker run`, hoặc `--extra cpu` trên máy không có GPU). Worker trong Docker có hai profile: `cpu` (CI) và `gpu` (cần nvidia-container-toolkit).

## 1. Khởi động hệ thống

```bash
cp .env.example .env          # thay mọi giá trị change-me; đặt ADVERTEST_DATA_DIR (đường dẫn tuyệt đối tới data/)
GIT_COMMIT=$(git rev-parse HEAD) make up
docker compose -f docker/compose.yaml --env-file .env exec api python -m backend.admin_cli.seed
```

`seed` nạp attack catalog, compute target `local-dev` (chưa có token) và tài khoản admin trong `ADVERTEST_ADMIN_EMAIL`.

Các lệnh quản trị bên dưới chạy trong container `api`; viết tắt:

```bash
admin() { docker compose -f docker/compose.yaml --env-file .env exec api advertest-admin "$@"; }
```

Lệnh ghi dữ liệu cần `--as <email>` của một admin `active`; thao tác được ghi vào `audit_log`.

## 2. Compute target và token

`local-dev` do seed tạo chưa có token, nên cấp token bằng `rotate-token`:

```bash
admin compute-target rotate-token local-dev --as admin@example.com
# hoặc tạo target mới:
admin compute-target create --name laptop --gpu-model "RTX 3050" --time-limit 7200 --as admin@example.com
admin compute-target list
```

Token chỉ hiện **một lần**; DB chỉ lưu sha256. Đặt token vào `WORKER_TOKEN` của worker. `rotate-token` làm token cũ mất hiệu lực ngay.

## 3. Đăng ký dữ liệu và gửi experiment

```bash
admin import-local --store "$ADVERTEST_DATA_DIR/store" --as admin@example.com
admin submit --config configs/examples/pgd_sweep.yaml --target local-dev --as admin@example.com
```

- `import-local` đăng ký model, dataset, slice, mapping (id giữ nguyên như trong `LocalStore`) và chỉ upload ảnh thuộc slice.
- File cấu hình phải có trong container `api`. Chép vào thư mục đã mount (`$ADVERTEST_DATA_DIR`) hoặc dùng `docker compose cp`.
- `submit` in id experiment, số run và ước lượng thời gian. Chưa có cost profile thì in "chưa có ước lượng"; lần chạy đầu worker sẽ tự calibration.

## 4. Chạy worker

### Trực tiếp trên máy (mặc định)

```bash
export API_URL=http://127.0.0.1:8000 WORKER_TOKEN=<token>
uv run --extra cuda advertest-worker run     # máy có GPU; máy không GPU dùng --extra cpu
```

- Cache ở `~/.cache/advertest-worker` (đổi bằng `CACHE_DIR`). Ảnh chỉ tải một lần theo sha256.
- Fingerprint lấy commit từ `git rev-parse HEAD`; working tree bẩn (ngoài `.ai-log/`) thì `git_dirty = true`.
- `--once`: xử lý tối đa một experiment rồi thoát.
- Đo lại cost profile (ví dụ sau khi đổi GPU): `uv run --extra cuda advertest-worker calibrate --experiment <id>` (hoặc `--extra cpu`). Experiment phải đang `running` trên target này.

### Trong Docker

```bash
docker/worker/up.sh cpu     # hoặc gpu
```

Script chỉ build từ working tree sạch, và truyền `GIT_COMMIT` là commit hiện tại. Sau khi build, nó đặt `DOCKER_IMAGE_DIGEST` bằng image ID thật, để manifest ghi đúng image đã chạy. Container dùng host network, nên gọi API và MinIO qua `127.0.0.1` giống worker chạy trực tiếp; cách này chỉ dùng được trên Linux.

## 5. Theo dõi, hủy, giới hạn

```bash
admin experiment list
admin experiment show <id> --watch     # làm mới mỗi 2 giây tới khi experiment kết thúc
admin experiment cancel <id> --as admin@example.com
```

- Giới hạn thời gian mặc định lấy từ target (2 giờ), đổi bằng `submit --time-limit <giây>`.
- Chỉ thời gian xử lý các batch được tính vào giới hạn. Chạm giới hạn thì run hiện tại dừng với kết quả một phần (`stopped_limit`, `metrics.partial = true`), và các run chưa chạy chuyển `stopped_limit`.
- Hủy thì worker dừng sau batch hiện tại; run hiện tại và các run chưa chạy chuyển `cancelled`.
- Gửi lại cùng cấu hình thì các run đã có kết quả được bỏ qua (`skipped`, `cached`).

## 6. Gián đoạn và chạy tiếp

Kịch bản kiểm tra (Manual Checks trong `validation.md`):

1. Trong lúc PGD đang chạy, `kill -9` tiến trình worker.
2. Khởi động lại worker. Sau khoảng một phút (lease 60 giây hết hạn), experiment được lease lại, và worker chạy tiếp từ batch kế tiếp của checkpoint mới nhất.
3. Kết quả cuối phải khớp lần chạy không bị gián đoạn trong sai số. Mỗi ảnh được tính đúng một lần.

**Không sửa code giữa lúc experiment đang chạy dở.** Fingerprint đổi (commit khác hoặc working tree bẩn) thì run đang chạy dở chuyển `failed` ("Môi trường worker đổi giữa chừng"). Các run còn lại vẫn chạy tiếp; muốn chạy lại run đó thì gửi lại experiment.

## 7. Sự cố thường gặp

| Triệu chứng | Nguyên nhân và cách xử lý |
|---|---|
| Worker báo 401 | Token sai hoặc đã bị xoay: `rotate-token` rồi cập nhật `WORKER_TOKEN`. |
| Tải ảnh hoặc upload báo 403 `SignatureDoesNotMatch` | Worker gọi MinIO qua host khác với `MINIO_PUBLIC_ENDPOINT`. Giữ mặc định `http://127.0.0.1:9000`. |
| `import-local` không tìm thấy ảnh | `ADVERTEST_DATA_DIR` chưa đặt, hoặc không trùng đường dẫn tuyệt đối lúc import vào `LocalStore`. |
| Worker trong Docker báo `GIT_COMMIT không phải commit hash` | Build không qua `docker/worker/up.sh`: image giữ `GIT_COMMIT=unknown`. |
| Hết VRAM | Worker tự giảm batch size một bậc và gửi cost profile mới; lỗi vẫn còn ở batch 1 thì run `failed`. |
