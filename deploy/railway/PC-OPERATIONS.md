# Bật, tắt, cập nhật và build worker trên PC

Runbook này dành cho máy đã cài worker và có `.env.pc`. Hướng dẫn cài mới: [WORKER.md](WORKER.md).
Mọi lệnh Bash chạy ở gốc repo trong Ubuntu/WSL (`~/advertest`). Các lệnh PowerShell có thể chạy ở
bất kỳ thư mục nào vì dùng tên container cố định.

Worker trên PC gồm ba container:

- `advertest-pc-worker-1`: chạy experiment bằng GPU (profile `gpu`).
- `advertest-pc-worker-tools-1`: kiểm tra model/spec và quick try bằng CPU.
- `advertest-pc-converter-1`: sandbox chuyển đổi model.

## 1. Kiểm tra trước khi bật

Trên Windows, mở PowerShell:

```powershell
$docker = (Get-Command docker.exe -ErrorAction SilentlyContinue).Source
if (-not $docker) {
  $docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
}

& $docker desktop status
& $docker info
```

Docker đã sẵn sàng khi `desktop status` có `Status running` và `docker info` trả về phần `Server`.
Nếu chưa chạy:

```powershell
& $docker desktop start
```

Chờ Docker chuyển sang `running` rồi mới bật worker.

## 2. Bật và tắt tạm thời

### Tắt tạm để sleep hoặc không nhận job

Trước khi tắt:

1. Trên web, target phải có `0 job đang chờ`. Con số này chỉ tính experiment `queued`, không tính
   experiment đang chạy.
2. Kiểm tra log gần nhất:

   ```powershell
   & $docker logs --since 30s advertest-pc-worker-1 2>&1
   & $docker logs --since 30s advertest-pc-worker-tools-1 2>&1
   ```

3. Worker rảnh khi log có `/lease "HTTP/1.1 204 No Content"`; worker-tools rảnh khi có
   `/tool-lease "HTTP/1.1 204 No Content"`. Không sleep khi log có `Nhận experiment` và job chưa
   kết thúc.

Dừng cả ba container nhưng giữ nguyên container, image, volume và cache:

```powershell
& $docker stop `
  advertest-pc-worker-1 `
  advertest-pc-worker-tools-1 `
  advertest-pc-converter-1
```

Sau khi lệnh in đủ ba tên container, có thể cho máy sleep. Target chuyển sang `offline` sau tối đa
60 giây.

### Bật lại sau khi wake

Đợi Docker Desktop sẵn sàng theo mục 1, sau đó:

```powershell
& $docker start `
  advertest-pc-converter-1 `
  advertest-pc-worker-tools-1 `
  advertest-pc-worker-1

& $docker ps --filter 'name=advertest-pc-'
& $docker logs --since 30s advertest-pc-worker-1 2>&1
```

Đúng khi cả ba container có trạng thái `Up` và worker lại nhận `204 No Content`.

Nếu `docker start` báo `No such container`, deployment đã bị hạ bằng `pc-up.sh down`; dùng mục 3 để
tạo lại container.

## 3. `stop` khác `pc-up.sh down`

| Lệnh | Container | Image | Volume/cache | Cách bật lại |
|---|---|---|---|---|
| `docker stop ...` | Giữ lại | Giữ lại | Giữ lại | `docker start ...` |
| `deploy/railway/pc-up.sh down` | Xóa | Giữ lại | Giữ lại | `deploy/railway/pc-up.sh gpu` |
| Compose `down -v` | Xóa | Giữ lại | **Xóa** | Build/up và tải lại cache |

Dùng `docker stop/start` cho việc tắt tạm. Dùng `pc-up.sh down` trước khi cập nhật code, chuyển máy
hoặc hạ deployment. Không thêm `-v` nếu chỉ muốn dừng worker.

Script `.sh` chỉ chạy trong Ubuntu/WSL và cần Docker Desktop bật WSL integration cho distro đó:

```bash
cd ~/advertest
deploy/railway/pc-up.sh down
```

## 4. Cập nhật code và chạy lại

Chỉ cập nhật khi worker đang rảnh theo mục 2.

```bash
cd ~/advertest
git status --short
deploy/railway/pc-up.sh down
git pull --ff-only
deploy/railway/pc-up.sh gpu
```

`pc-up.sh gpu` thực hiện lần lượt:

1. Từ chối build nếu working tree có thay đổi chưa commit (trừ `.ai-log`).
2. Gắn `GIT_COMMIT` hiện tại vào image.
3. Build image GPU cho experiment và image CPU cho worker-tools/converter.
4. Lấy image ID thật làm `DOCKER_IMAGE_DIGEST`.
5. Tạo và bật lại ba container mà không xóa volume cache.

Sau cập nhật:

```bash
docker compose -f deploy/railway/compose.pc.yaml --env-file .env.pc --profile gpu ps
docker logs --since 30s advertest-pc-worker-1
docker logs --since 30s advertest-pc-worker-tools-1
```

Worker nên chạy cùng commit với service `api` trên Railway. Nếu thay đổi chạm vào `backend/`,
`ml_core/`, `attacks/` hoặc `contracts/`, kiểm tra và deploy lại API tương ứng.

## 5. Khi nào cần build lại worker?

| Thay đổi | Build worker PC? | Ghi chú |
|---|---:|---|
| Chỉ frontend | Không | Chỉ deploy frontend trên Railway. |
| Chỉ cấu hình/metadata compute target trong DB | Không | Refresh web là đủ. |
| `backend/worker`, `ml_core`, `attacks` hoặc contract worker dùng | Có | Chạy `pc-up.sh gpu`. |
| `pyproject.toml`, `uv.lock`, Dockerfile | Có, lâu hơn | Layer dependency phải cài lại. |
| Phiên bản PyTorch/CUDA | Có, rất lâu | Tải và unpack nhiều GB. |

Build đầu tiên hoặc đổi CUDA có thể mất hàng chục phút. Khi chỉ đổi source Python, Docker tái sử dụng
layer dependency nên thường nhanh hơn nhiều. Không chạy `docker builder prune` hoặc
`docker system prune` nếu muốn giữ cache build.

### Chỉ build, chưa bật container

```bash
cd ~/advertest
export GIT_COMMIT="$(git rev-parse HEAD)"
docker compose -f deploy/railway/compose.pc.yaml --env-file .env.pc \
  --profile gpu build worker worker-tools
```

Thông thường nên dùng `pc-up.sh gpu` để script tự gắn đúng image digest và bật đủ service.

### Build lại hoàn toàn, không dùng cache

Chỉ dùng khi nghi cache hỏng hoặc đang kiểm chứng dependency:

```bash
export GIT_COMMIT="$(git rev-parse HEAD)"
docker compose -f deploy/railway/compose.pc.yaml --env-file .env.pc \
  --profile gpu build --no-cache worker worker-tools
```

Lệnh này rất lâu với image CUDA. Nó không xóa volume dữ liệu, nhưng tạo thêm dữ liệu build trong
Docker image store.

## 6. Windows chưa bật WSL integration

Nếu Ubuntu báo `docker: command not found`, có hai lựa chọn:

1. Khuyến nghị: Docker Desktop → **Settings → Resources → WSL integration** → bật `Ubuntu`, rồi chạy
   `wsl --shutdown` trong PowerShell và mở lại Docker Desktop.
2. Tắt/bật tạm bằng các lệnh PowerShell ở mục 2. Để update/build bằng `pc-up.sh`, vẫn cần bật WSL
   integration; không chạy script Bash trực tiếp trong PowerShell.

## 7. Các lệnh kiểm tra nhanh

```powershell
# Trạng thái container
& $docker ps --filter 'name=advertest-pc-'

# Log GPU worker
& $docker logs -f --tail 30 advertest-pc-worker-1

# Log worker công cụ
& $docker logs -f --tail 30 advertest-pc-worker-tools-1

# GPU nhìn thấy trong container
& $docker exec advertest-pc-worker-1 nvidia-smi
```

Các dấu hiệu cần xử lý:

- `401`: token sai hoặc đã rotate; cập nhật `.env.pc` rồi tạo lại container.
- `ConnectError`: kiểm tra Internet và `API_URL`.
- Worker liên tục restart: xem `docker logs` trước khi build lại.
- `no space left on device`: kiểm tra Docker disk image và dung lượng ổ đĩa; không prune khi chưa xác
  định dữ liệu sẽ bị xóa.

