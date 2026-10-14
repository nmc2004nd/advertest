# Triển khai: web trên Railway, worker trên PC

Web (đăng nhập, experiment, review, report) luôn chạy trên Railway. Experiment chỉ chạy khi PC bật
worker; lúc PC tắt, experiment mới nằm chờ trong hàng đợi và chạy khi worker online lại.

```
Railway:  frontend (Caddy, có domain)  ──/api──▶  api (không domain)  ──▶  Postgres
                                                     │
                                                     └──▶ bucket (Storage Bucket, API S3 công khai)
PC:       worker + worker-tools + converter  ── HTTPS ──▶ https://<frontend>/api  và  presigned URL của bucket
```

Railway chỉ cấp **một** bucket với tên có hậu tố ngẫu nhiên và credential riêng, nên API chạy ở chế
độ một bucket (`MINIO_BUCKET`): bốn bucket logic `models`, `datasets`, `artifacts`, `reports` thành
tiền tố khóa (`artifacts/runs/<run_id>/...`). URI trong DB vẫn là `s3://artifacts/...`; môi trường
dev (`make up`, MinIO) không đổi.

| File | Dùng để |
|---|---|
| `WORKER.md` | Cài máy chạy worker trên Ubuntu và Windows |
| `RUNNING.md` | Vận hành hằng ngày: chạy worker, cập nhật, sao lưu, xử lý sự cố |
| `railway.env.example` | Biến môi trường của từng service trên Railway |
| `pc.env.example` | Biến môi trường trên PC (chép thành `.env.pc` ở gốc repo) |
| `init-db.sh` | Tạo role và database trên Postgres của Railway (một lần, qua `railway ssh`) |
| `bucket-cors.sh` | Cho phép trình duyệt (domain frontend) PUT lên bucket (một lần) |
| `admin.sh` | Chạy lệnh quản trị trong container `api` (qua `railway ssh`) |
| `compose.pc.yaml`, `pc-up.sh` | Chạy worker trên PC |

Chi phí ước tính: gói Hobby 5 USD/tháng (đã gồm 5 USD tiền dùng); image `api` có torch dùng khoảng
1 GB RAM nên tổng thường 5–10 USD/tháng. Bucket: 0,015 USD/GB-tháng, không tính phí request và egress.

## Chuẩn bị

- Tài khoản Railway (gói Hobby), Railway CLI đã đăng nhập (`railway login`), nhánh deploy đã đẩy lên GitHub.
- PC có Docker, `uv`, và fixture (`make fixtures`; image worker cần chúng).
- Sinh các mật khẩu (chỉ chữ và số): `openssl rand -hex 24`, mỗi lần cho một biến:
  `ADVERTEST_OWNER_PASSWORD`, `ADVERTEST_APP_PASSWORD`, `ARTIFACT_TOKEN_SECRET`.

## 1. Tạo project trên Railway

Railway đã bỏ config-as-code (`railway.toml`) cho project mới, nên thiết lập của từng service đặt
trong **Settings** (hoặc qua `railway api`, mutation `serviceInstanceUpdate`).

1. `railway init --name advertest` (hoặc **New Project** trên web), rồi `railway link` ở gốc repo.
2. Thêm service `api` và `frontend` từ GitHub repo (**+ New → GitHub Repo**, đặt đúng tên này: biến
   tham chiếu trong `railway.env.example` dùng chúng). Ở **Settings → Source** chọn nhánh deploy;
   kiểm tra lại, vì `railway add --branch` không đổi nhánh (service vẫn theo `main`).
3. **Settings** của từng service:

   | | `api` | `frontend` |
   |---|---|---|
   | Dockerfile path | `docker/api/Dockerfile` | `docker/frontend/Dockerfile` |
   | Healthcheck path | `/health`, timeout 300 s | `/` |
   | Restart policy | On failure, 5 lần | On failure, 5 lần |
   | Watch paths | `backend/**`, `ml_core/**`, `attacks/**`, `contracts/python/**`, `contracts/seeds/**`, `pyproject.toml`, `uv.lock`, `docker/api/**` | `frontend/**`, `docker/frontend/**` |
   | Domain công khai | **không** (`TRUSTED_PROXIES=*` chỉ an toàn khi api chỉ nhận kết nối từ `frontend`) | **Generate Domain**, cổng `8080` |

4. `railway add --database postgres` (giữ tên `Postgres`). Không cần TCP proxy.
5. `railway bucket create bucket --region sin` (đặt tên `bucket`). `railway bucket credentials
   --bucket bucket` cho endpoint, tên bucket, khóa và kiểu địa chỉ (`urlStyle`).
6. Đặt biến theo `railway.env.example` (tab **Variables → Raw Editor**, hoặc `railway variable set
   -s <service> --skip-deploys ...`).

Lần deploy đầu, `api` sẽ fail vì chưa có database `advertest`; làm tiếp bước 2 rồi redeploy.

## 2. Khởi tạo database và CORS của bucket (từ PC, một lần)

`init-db.sh` và `admin.sh` chạy lệnh bên trong container trên Railway qua `railway ssh`, không mở
Postgres ra Internet. Cần một SSH key đã đăng ký: `ssh-keygen -t ed25519`, `railway ssh keys add`, và
host key của `ssh.railway.com` trong `~/.ssh/known_hosts` (`ssh-keyscan ssh.railway.com`).

```bash
cp deploy/railway/pc.env.example .env.pc   # điền mật khẩu, MINIO_* (credential của bucket), APP_BASE_URL
deploy/railway/init-db.sh                  # tạo advertest_owner, advertest_app, database advertest
deploy/railway/bucket-cors.sh              # cho phép https://<frontend> PUT lên bucket (upload model)
```

Không cần tạo bucket con: tiền tố khóa tự xuất hiện khi ghi.

Redeploy service `api` (migration chạy trong entrypoint). Kiểm tra:
`curl https://<frontend-domain>/api/health` trả `"status": "ok"`.

## 3. Admin và compute target (từ PC)

```bash
deploy/railway/admin.sh python -m backend.admin_cli.seed      # admin đầu tiên (ADVERTEST_ADMIN_* trong .env.pc)
deploy/railway/admin.sh advertest-admin compute-target create --name pc --as <email admin>
deploy/railway/admin.sh advertest-admin compute-target create --name pc-tools --as <email admin>
```

Token in ra (một lần) điền vào `WORKER_TOKEN` và `WORKER_TOOLS_TOKEN` trong `.env.pc`.
Đưa model, dataset, slice từ LocalStore lên (ví dụ KITTI): [RUNNING.md](RUNNING.md) mục 3b.

## 4. Chạy worker trên PC

```bash
deploy/railway/pc-up.sh cpu     # hoặc gpu; dừng: deploy/railway/pc-up.sh down
```

Worker chỉ build từ working tree sạch (commit trước), giống `docker/worker/up.sh`.
Hướng dẫn copy/paste để bật/tắt tạm, sleep, cập nhật code và quản lý build cache:
[PC-OPERATIONS.md](PC-OPERATIONS.md).

## Kiểm tra sau khi deploy

- Mở `https://<frontend-domain>` trên điện thoại, đăng nhập; tải lại ở một trang con (SPA fallback).
- Tắt worker (`pc-up.sh down`), tạo experiment: nó ở trạng thái chờ. Bật lại: experiment chạy,
  ảnh failure case hiện trên web (presigned URL tới bucket hoạt động).
- Đăng ký model bằng cách upload file weights trên web: thanh tiến độ chạy hết. Lỗi CORS trong
  console trình duyệt nghĩa là chưa chạy `bucket-cors.sh` hoặc `APP_BASE_URL` sai domain.
- Thử đăng nhập sai vài lần, rồi xem audit log: IP ghi lại phải là IP thật của bạn, không phải IP
  nội bộ. Nếu sai, proxy của Railway không gửi `X-Real-IP` như giả định trong `docker/frontend/Caddyfile`.

## Vận hành

- **Worker trên PC:** xem runbook [PC-OPERATIONS.md](PC-OPERATIONS.md) trước khi sleep, cập nhật hoặc
  build lại image.
- **Backup Postgres:** `pg_dump` trong container qua `railway ssh` (base64 để dữ liệu nhị phân đi
  nguyên vẹn): `railway ssh -s Postgres -- "pg_dump -U postgres -Fc advertest | base64 -w0" | base64 -d > backup.dump`.
  Bucket không có backup tự động; sao về PC bằng công cụ S3 bất kỳ, ví dụ
  `aws s3 sync s3://$MINIO_BUCKET ./bucket-backup --endpoint-url $MINIO_ENDPOINT`.
  Bucket xóa nhầm còn khôi phục được trong 52 giờ.
- **Email:** `SMTP_HOST` trống thì email nằm chờ trong outbox; điền SMTP (Resend, Brevo...) để gửi thật.
- **Đổi khóa:** đổi biến trên Railway rồi redeploy; token worker đổi bằng `compute-target rotate-token`.
- `make up` (môi trường dev) không bị ảnh hưởng bởi các file ở đây.
