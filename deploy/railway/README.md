# Triển khai: web trên Railway, worker trên PC

Web (đăng nhập, experiment, review, report) luôn chạy trên Railway. Experiment chỉ chạy khi PC bật
worker; lúc PC tắt, experiment mới nằm chờ trong hàng đợi và chạy khi worker online lại.

```
Railway:  frontend (Caddy, có domain)  ──/api──▶  api (không domain)  ──▶  Postgres
                                                     │
                                                     └──▶ minio (có domain, volume /data)
PC:       worker + worker-tools + converter  ── HTTPS ──▶ https://<frontend>/api  và  https://<minio>
```

| File | Dùng để |
|---|---|
| `api.toml`, `frontend.toml`, `minio.toml` | Config-as-code cho từng service trên Railway |
| `railway.env.example` | Biến môi trường của từng service trên Railway |
| `pc.env.example` | Biến môi trường trên PC (chép thành `.env.pc` ở gốc repo) |
| `init-db.sh` | Tạo role và database trên Postgres của Railway (một lần) |
| `create-buckets.sh` | Tạo 4 bucket trên MinIO của Railway (một lần) |
| `admin.sh` | Chạy lệnh quản trị trên PC, trỏ vào Railway |
| `compose.pc.yaml`, `pc-up.sh` | Chạy worker trên PC |

Chi phí ước tính: gói Hobby 5 USD/tháng (đã gồm 5 USD tiền dùng); image `api` có torch dùng khoảng
1 GB RAM nên tổng thường 5–10 USD/tháng.

## Chuẩn bị

- Tài khoản Railway (gói Hobby), repo đã đẩy lên GitHub.
- PC có Docker, `uv`, và fixture (`make fixtures`; image worker cần chúng).
- Sinh các mật khẩu (chỉ chữ và số): `openssl rand -hex 24`, mỗi lần cho một biến:
  `ADVERTEST_OWNER_PASSWORD`, `ADVERTEST_APP_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`,
  `ARTIFACT_TOKEN_SECRET`.

## 1. Tạo project trên Railway

1. **New Project → Deploy from GitHub repo**, chọn repo. Railway tạo một service; tạo thêm hai service
   cũng từ repo đó (**+ New → GitHub Repo**). Đặt tên ba service đúng là `api`, `frontend`, `minio`
   (biến tham chiếu trong `railway.env.example` dùng các tên này).
2. Ở mỗi service: **Settings → Config-as-code**, điền đường dẫn file tương ứng
   (`/deploy/railway/api.toml`, `/deploy/railway/frontend.toml`, `/deploy/railway/minio.toml`).
   Chọn nhánh deploy ở **Settings → Source**.
3. **+ New → Database → PostgreSQL**. Giữ tên `Postgres`. Ở **Settings → Networking** bật
   **TCP Proxy** (để chạy `init-db.sh` và lệnh quản trị từ PC).
4. Service `minio`: **+ Volume** gắn vào `/data`; **Settings → Networking → Generate Domain**, cổng `9000`.
5. Service `frontend`: **Generate Domain**, cổng `8080`. Đây là địa chỉ người dùng mở.
6. Service `api`: **không** tạo domain công khai (`TRUSTED_PROXIES=*` chỉ an toàn khi api chỉ nhận
   kết nối từ `frontend` trong mạng riêng).
7. Dán biến môi trường theo `railway.env.example`: phần Shared Variables ở Project Settings, phần
   còn lại vào tab **Variables → Raw Editor** của từng service.

Lần deploy đầu, `api` sẽ fail vì chưa có database `advertest`; làm tiếp bước 2 rồi redeploy.

## 2. Khởi tạo database và bucket (từ PC, một lần)

```bash
cp deploy/railway/pc.env.example .env.pc   # điền PGHOST/PGPORT/PGPASSWORD (TCP proxy), mật khẩu, MINIO_*
deploy/railway/init-db.sh                  # tạo advertest_owner, advertest_app, database advertest
deploy/railway/create-buckets.sh           # tạo artifacts, reports, datasets, models
```

Redeploy service `api` (migration chạy trong entrypoint). Kiểm tra:
`curl https://<frontend-domain>/api/health` trả `"status": "ok"`.

## 3. Admin, compute target, dữ liệu (từ PC)

```bash
deploy/railway/admin.sh python -m backend.admin_cli.seed      # admin đầu tiên (ADVERTEST_ADMIN_*)
deploy/railway/admin.sh advertest-admin compute-target create --name pc --as <email admin>
deploy/railway/admin.sh advertest-admin compute-target create --name pc-tools --as <email admin>
deploy/railway/admin.sh advertest-admin import-local --store <thư mục LocalStore> --as <email admin>
```

Token in ra (một lần) điền vào `WORKER_TOKEN` và `WORKER_TOOLS_TOKEN` trong `.env.pc`.

## 4. Chạy worker trên PC

```bash
deploy/railway/pc-up.sh cpu     # hoặc gpu; dừng: deploy/railway/pc-up.sh down
```

Worker chỉ build từ working tree sạch (commit trước), giống `docker/worker/up.sh`.

## Kiểm tra sau khi deploy

- Mở `https://<frontend-domain>` trên điện thoại, đăng nhập; tải lại ở một trang con (SPA fallback).
- Tắt worker (`pc-up.sh down`), tạo experiment: nó ở trạng thái chờ. Bật lại: experiment chạy,
  ảnh failure case hiện trên web (presigned URL tới MinIO hoạt động).
- Thử đăng nhập sai vài lần, rồi xem audit log: IP ghi lại phải là IP thật của bạn, không phải IP
  nội bộ. Nếu sai, proxy của Railway không gửi `X-Real-IP` như giả định trong `docker/frontend/Caddyfile`.

## Vận hành

- **Backup Postgres:** `pg_dump` qua TCP proxy, ví dụ
  `docker run --rm -e PGPASSWORD postgres:17-alpine pg_dump -h $PGHOST -p $PGPORT -U postgres -Fc advertest > backup.dump`.
  Volume MinIO: `mc mirror` từ domain công khai về PC.
- **Email:** `SMTP_HOST` trống thì email nằm chờ trong outbox; điền SMTP (Resend, Brevo...) để gửi thật.
- **Đổi khóa:** đổi biến trên Railway rồi redeploy; token worker đổi bằng `compute-target rotate-token`.
- `make up` (môi trường dev) không bị ảnh hưởng bởi các file ở đây.
