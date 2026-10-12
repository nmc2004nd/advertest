# Vận hành hằng ngày: web trên Railway, worker trên PC

Tài liệu này dành cho người đã có bản triển khai chạy sẵn (dựng từ đầu: [README.md](README.md)).
Mọi lệnh chạy ở gốc repo, nơi có `.env.pc` (token worker, mật khẩu; đã gitignore).

```
Trình duyệt ──▶ https://<frontend>      (Railway: frontend → api → Postgres, bucket)
PC          ──▶ https://<frontend>/api  (worker hỏi job mỗi vài giây)
            ──▶ presigned URL của bucket (tải model, dataset; ghi kết quả)
```

Web luôn chạy. Experiment chỉ chạy khi worker trên PC bật; lúc PC tắt, experiment mới nằm chờ trong
hàng đợi và tự chạy khi worker online lại.

## 1. Chạy worker

| Việc | Lệnh |
|---|---|
| Bật (CPU) | `deploy/railway/pc-up.sh cpu` |
| Bật (GPU NVIDIA, cần nvidia-container-toolkit) | `deploy/railway/pc-up.sh gpu` |
| Tắt | `deploy/railway/pc-up.sh down` |
| Trạng thái | `docker compose -f deploy/railway/compose.pc.yaml --env-file .env.pc ps` |
| Log worker experiment | `docker logs -f advertest-pc-worker-cpu-1` (GPU: `advertest-pc-worker-1`) |
| Log worker công cụ | `docker logs -f advertest-pc-worker-tools-1` |

`pc-up.sh` chạy ba container:

- `worker-cpu` / `worker`: chạy experiment (token `WORKER_TOKEN`, compute target `pc`).
- `worker-tools`: kiểm tra model, kiểm tra attack spec, thử nhanh (token `WORKER_TOOLS_TOKEN`,
  compute target `pc-tools`).
- `converter`: sandbox không mạng, chuyển `.pt`/`.pth` upload qua web sang safetensors.

Container có `restart: unless-stopped`: bật máy là worker tự chạy lại (khi Docker khởi động cùng
máy), trừ khi đã tắt bằng `down`.

**Log bình thường:** `POST .../internal/worker/lease "HTTP/1.1 204 No Content"` lặp lại vài giây
một lần: worker đã kết nối và đang chờ job.

### Khi sửa code

`pc-up.sh` chỉ build từ working tree sạch, để mỗi run ghi đúng commit đã chạy. Commit trước, rồi chạy
lại `deploy/railway/pc-up.sh cpu` (build lại image, giữ cache).

Nếu thay đổi chạm vào API (`backend/`, `ml_core/`, `attacks/`, `contracts/`) thì cũng deploy lại
service `api` trên Railway (mục 3), để worker và API cùng phiên bản.

### Chạy worker trên máy khác

1. Máy cần Docker, repo (cùng nhánh) và fixture: `make fixtures`.
2. Tạo compute target riêng cho máy đó; mỗi token chỉ dùng trên một máy:
   ```bash
   deploy/railway/admin.sh advertest-admin compute-target create --name pc2 --as <email admin>
   ```
3. Trên máy mới tạo `.env.pc` chỉ với `API_URL`, `WORKER_TOKEN` (token vừa in), `WORKER_TOOLS_TOKEN`
   (chỉ cần nếu máy này cũng chạy worker công cụ), rồi `deploy/railway/pc-up.sh cpu`.

## 2. Lệnh quản trị

`admin.sh` chạy lệnh trong container `api` trên Railway qua `railway ssh` (cần Railway CLI đã đăng
nhập, `railway link` tới project, SSH key đã đăng ký: xem [README.md](README.md) mục 2).

```bash
deploy/railway/admin.sh advertest-admin compute-target list
deploy/railway/admin.sh advertest-admin compute-target rotate-token --name pc   # token cũ hết hiệu lực ngay
deploy/railway/admin.sh advertest-admin --help
```

Sau `rotate-token`: dán token mới vào `.env.pc` (`WORKER_TOKEN` hoặc `WORKER_TOOLS_TOKEN`) rồi chạy
lại `pc-up.sh`.

## 3. Cập nhật web trên Railway

Service `api` và `frontend` lấy code từ nhánh `deploy-railway` trên GitHub.

```bash
git push                                   # đẩy commit lên nhánh deploy
railway redeploy -s api                    # hoặc bấm Deploy trên dashboard
railway logs -s api                        # log khi chạy
railway logs -s api --build                # log build
curl https://<frontend-domain>/api/health  # "status": "ok", git_commit là commit vừa đẩy
```

Nếu push không tự deploy (GitHub App của Railway chưa có quyền vào repo), `railway redeploy` chạy lại
bản cũ: deploy đúng commit bằng
`railway api 'mutation { serviceInstanceDeployV2(serviceId: "<id>", environmentId: "<id>", commitSha: "<sha>") }'`
(id lấy bằng `railway status --json`).

Migration DB chạy tự động khi `api` khởi động. Dữ liệu không mất khi deploy lại: Postgres nằm trên
volume, file nằm trong bucket; `api` và `frontend` không lưu gì.

## 4. Sao lưu

```bash
# Postgres
railway ssh -s Postgres -- "pg_dump -U postgres -Fc advertest | base64 -w0" | base64 -d > backup-$(date +%F).dump

# Bucket (biến lấy từ .env.pc)
set -a; . ./.env.pc; set +a
AWS_ACCESS_KEY_ID=$MINIO_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$MINIO_SECRET_KEY \
  aws s3 sync "s3://$MINIO_BUCKET" ./bucket-backup --endpoint-url "$MINIO_ENDPOINT" --region auto
```

Railway không tự backup ở gói Hobby. Xóa service `Postgres` hay volume của nó là mất dữ liệu; bucket xóa
nhầm còn khôi phục được trong 52 giờ.

## 5. Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Experiment đứng ở trạng thái chờ | Worker chưa bật | `pc-up.sh cpu`, xem log worker |
| Log worker `401` | Token sai hoặc đã đổi | `compute-target rotate-token`, cập nhật `.env.pc`, chạy lại `pc-up.sh` |
| `pc-up.sh`: "Working tree có thay đổi chưa commit" | Còn file sửa dở | Commit hoặc bỏ thay đổi |
| Build worker lỗi thiếu fixture | Chưa có `tests/fixtures` | `make fixtures` |
| Worker lỗi `403` khi tải từ bucket | Presigned URL hết hạn (15 phút) hoặc lệch giờ máy | Đồng bộ giờ hệ thống; job sẽ được cấp lại |
| Upload model trên web lỗi CORS (console trình duyệt) | Domain frontend đổi, CORS bucket cũ | Sửa `APP_BASE_URL` trong `.env.pc`, chạy `deploy/railway/bucket-cors.sh` |
| `/api/health` có `"minio": {"ok": false}` | Credential bucket đổi | Kiểm tra biến `MINIO_*` của service `api` (tham chiếu tới `bucket`) |
| `/api/health` không trả lời | `api` crash hoặc đang deploy | `railway logs -s api`, `railway deployment list -s api` |
| Email không tới | Chưa cấu hình SMTP (email nằm trong outbox) | Điền `SMTP_*` cho service `api` |
