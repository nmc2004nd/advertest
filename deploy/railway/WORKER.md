# Chạy worker trên Ubuntu và Windows

Hướng dẫn cài một máy chạy worker cho bản triển khai trên Railway: máy mới, chuyển máy, hay thêm máy.
Vận hành hằng ngày (log, token, cập nhật, sự cố): [RUNNING.md](RUNNING.md).

Worker chỉ gọi ra ngoài qua HTTPS (`https://<frontend>/api` và bucket), không mở cổng nào, nên máy ở
mạng nào cũng chạy được (nhà, công ty, sau NAT). Mỗi máy chạy ba container:

| Container | Làm gì | Token trong `.env.pc` |
|---|---|---|
| `worker-cpu` (hoặc `worker` khi dùng GPU) | Chạy experiment | `WORKER_TOKEN` |
| `worker-tools` | Kiểm tra model, kiểm tra attack spec, thử nhanh | `WORKER_TOOLS_TOKEN` |
| `converter` | Sandbox không mạng, chuyển `.pt`/`.pth` sang safetensors | — |

## 0. Chọn cách

| | Cách A: build trên máy | Cách B: chép image đã build |
|---|---|---|
| Khi nào | Máy mới, máy GPU, hoặc sau khi sửa code | Chuyển sang máy CPU khác, không muốn build |
| Cần | Docker, git, python3 | Docker, git (chỉ để lấy file compose) |
| Thời gian | Lần đầu 10–20 phút (tải torch) | Thời gian chép file ~5 GB |

Máy GPU luôn dùng cách A: image GPU cài torch bản CUDA, khác image CPU.

**Yêu cầu máy:** 64-bit, RAM từ 8 GB (16 GB nên dùng), trống ~15 GB đĩa cho image và cache.
GPU (tùy chọn): NVIDIA, driver mới.

---

## 1. Ubuntu (22.04, 24.04)

### 1.1. Cài Docker, git, python3

```bash
sudo apt update && sudo apt install -y git python3 curl
curl -fsSL https://get.docker.com | sudo sh          # Docker Engine + plugin compose
sudo usermod -aG docker "$USER"                       # dùng docker không cần sudo
newgrp docker                                         # hoặc đăng xuất rồi đăng nhập lại
docker run --rm hello-world                           # kiểm tra
docker compose version                                # cần v2
sudo systemctl enable docker                          # Docker (và worker) tự chạy khi bật máy
```

### 1.2. GPU NVIDIA (bỏ qua nếu chạy CPU)

```bash
nvidia-smi                                            # driver đã cài và thấy card
# nvidia-container-toolkit theo https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all ubuntu nvidia-smi          # container thấy GPU
```

### 1.3. Lấy code và cấu hình

```bash
git clone https://github.com/nmc2004nd/advertest.git
cd advertest
git checkout deploy-railway                           # cùng nhánh với api trên Railway
```

Tạo `.env.pc` ở gốc repo (xem mục 3), rồi `chmod 600 .env.pc`.

### 1.4. Cách A: build và chạy

```bash
PYTHONPATH=. python3 scripts/fetch_fixtures.py        # tải fixture, kiểm sha256
deploy/railway/pc-up.sh cpu                           # hoặc: deploy/railway/pc-up.sh gpu
```

`fetch_fixtures.py` có thể báo không tải được `yolov8n.onnx` và `fcos_resnet50_fpn_coco.safetensors`
(link cũ 404). Worker không cần hai file này; image chỉ cần `yolov8n.pt` và ảnh `kitti/`, và lúc build
có kiểm sha256 nên thiếu hay sai file thì build báo lỗi ngay. Máy có `uv` thì dùng `make fixtures`
cũng được.

### 1.5. Cách B: chép image đã build

Trên máy cũ:

```bash
docker save advertest-worker:cpu | gzip > worker-cpu.tar.gz
```

Chép `worker-cpu.tar.gz` và `.env.pc` sang máy mới (scp, USB), rồi trên máy mới, trong thư mục repo:

```bash
gunzip -c worker-cpu.tar.gz | docker load
export DOCKER_IMAGE_DIGEST=$(docker image inspect --format '{{.Id}}' advertest-worker:cpu)
docker compose -f deploy/railway/compose.pc.yaml --env-file .env.pc --profile cpu \
  up -d --no-build worker-cpu worker-tools converter
```

Commit và fixture đã nằm trong image, nên không cần tải fixture. `pc-up.sh` luôn build nên không dùng
ở cách này.

---

## 2. Windows 10 / 11

Script của dự án viết cho bash, nên chạy trong **WSL2 (Ubuntu)**; Docker Desktop cung cấp Docker
cho WSL2. Cách A làm hoàn toàn trong WSL2. Cách B làm được cả từ PowerShell.

### 2.1. Cài WSL2 và Docker Desktop

1. PowerShell **Run as Administrator**:
   ```powershell
   wsl --install -d Ubuntu
   ```
   Khởi động lại máy, mở **Ubuntu** từ Start, tạo user Linux.
2. Cài [Docker Desktop](https://www.docker.com/products/docker-desktop/). Trong **Settings**:
   - **General**: bật *Use the WSL 2 based engine* và *Start Docker Desktop when you sign in*
     (để worker tự chạy khi đăng nhập Windows).
   - **Resources → WSL integration**: bật cho distro *Ubuntu*.
3. Trong cửa sổ Ubuntu (WSL):
   ```bash
   docker run --rm hello-world
   docker compose version
   sudo apt update && sudo apt install -y git python3
   ```

**RAM cho WSL2:** mặc định WSL2 dùng tối đa 50% RAM của máy. Máy 16 GB trở xuống nên đặt rõ trong
`C:\Users\<tên>\.wslconfig`:

```ini
[wsl2]
memory=12GB
```

rồi chạy `wsl --shutdown` trong PowerShell và mở lại Docker Desktop.

### 2.2. GPU NVIDIA (bỏ qua nếu chạy CPU)

Chỉ cần driver NVIDIA mới **trên Windows**: không cài driver hay nvidia-container-toolkit trong WSL.
Docker Desktop tự chuyển GPU vào container. Kiểm tra trong WSL:

```bash
nvidia-smi
docker run --rm --gpus all ubuntu nvidia-smi
```

### 2.3. Lấy code: clone trong WSL, không clone ở ổ C:

```bash
cd ~                                                  # thư mục home của Linux, không phải /mnt/c/...
git clone https://github.com/nmc2004nd/advertest.git
cd advertest
git checkout deploy-railway
```

Clone bằng Git for Windows (ở `C:\...`) sẽ đổi xuống dòng thành CRLF, làm hỏng các script `.sh`; build
từ `/mnt/c` cũng chậm hơn nhiều. Mở thư mục từ Explorer: gõ `\\wsl$\Ubuntu\home\<user>\advertest`.

Tạo `.env.pc` ở gốc repo (mục 3), `chmod 600 .env.pc`. Chép file từ Windows vào WSL:
`cp /mnt/c/Users/<tên>/Downloads/.env.pc ~/advertest/`.

### 2.4. Cách A: build và chạy (trong WSL)

Giống Ubuntu:

```bash
PYTHONPATH=. python3 scripts/fetch_fixtures.py
deploy/railway/pc-up.sh cpu                           # hoặc gpu
```

### 2.5. Cách B: chép image đã build

Trong WSL làm giống mục 1.5. Hoặc từ **PowerShell**, trong thư mục repo đã clone:

```powershell
docker load -i worker-cpu.tar.gz
$env:DOCKER_IMAGE_DIGEST = docker image inspect --format '{{.Id}}' advertest-worker:cpu
docker compose -f deploy/railway/compose.pc.yaml --env-file .env.pc --profile cpu `
  up -d --no-build worker-cpu worker-tools converter
```

### 2.6. Lưu ý riêng cho Windows

- **Ngủ/ngủ đông:** máy ngủ thì worker dừng và run đang chạy mất lease (worker khác hoặc lần
  bật sau nhận lại; mất lease nhiều lần thì run báo lỗi).
  Khi chạy experiment dài: *Settings → System → Power* đặt *Sleep* = *Never* (khi cắm sạc).
- **Tự chạy:** container có `restart: unless-stopped`, chạy lại khi Docker Desktop khởi động, tức là
  sau khi đăng nhập Windows (không chạy ở màn hình khóa trước lần đăng nhập đầu).
- Lệnh `docker ...` dùng được cả trong PowerShell lẫn WSL; lệnh `deploy/railway/*.sh` chỉ chạy trong WSL.

---

## 3. File `.env.pc`

Đặt ở gốc repo, đã gitignore. Worker chỉ cần ba dòng:

```bash
API_URL=https://<domain frontend>/api
WORKER_TOKEN=<token compute target của máy này>
WORKER_TOOLS_TOKEN=<token compute target công cụ>
# WORKER_DEVICE=        # trống: GPU nếu có, không thì CPU
```

Các biến khác trong [pc.env.example](pc.env.example) (mật khẩu DB, credential bucket) chỉ dùng cho
lệnh quản trị và script khởi tạo; máy chỉ chạy worker không nên giữ chúng.

**Token:** mỗi token gắn với một compute target.

- **Chuyển máy:** chép `.env.pc` từ máy cũ và **tắt worker máy cũ trước** (`deploy/railway/pc-up.sh down`).
- **Thêm máy chạy song song:** tạo compute target mới (từ máy có Railway CLI, xem RUNNING.md mục 2):
  ```bash
  deploy/railway/admin.sh advertest-admin compute-target create --name pc2 --as <email admin>
  deploy/railway/admin.sh advertest-admin compute-target create --name pc2-tools --as <email admin>
  ```
  Token chỉ in một lần; dán vào `.env.pc` của máy mới.
- Chép `.env.pc` qua kênh riêng (USB, scp), không gửi qua chat hay đẩy lên git. Lộ token thì cấp lại
  bằng `compute-target rotate-token`.

## 4. Kiểm tra máy đã chạy

```bash
docker compose -f deploy/railway/compose.pc.yaml --env-file .env.pc ps     # 3 container "running"
docker logs --tail 5 advertest-pc-worker-cpu-1                             # GPU: advertest-pc-worker-1
docker logs --tail 5 advertest-pc-worker-tools-1
```

Đúng khi log lặp lại `POST .../internal/worker/lease "HTTP/1.1 204 No Content"` (worker công cụ:
`tool-lease`): đã kết nối và đang chờ job. Sau đó tạo một experiment nhỏ trên web: worker nhận job,
experiment chạy xong và có ảnh failure case.

| Log | Nghĩa | Xử lý |
|---|---|---|
| `401` | Token sai hoặc đã bị cấp lại | Sửa `.env.pc`, chạy lại `pc-up.sh` (hoặc lệnh `up` của cách B) |
| `ConnectError`, `Name or service not known` | Không ra được Internet, sai `API_URL` | Kiểm tra mạng, `curl <API_URL>/health` |
| `403` khi tải từ bucket | Presigned URL hết hạn, đồng hồ máy lệch | Bật đồng bộ giờ (Windows: *Set time automatically*; Ubuntu: `timedatectl`) |
| Container `worker` thoát ngay, lỗi GPU | Docker không thấy GPU | Làm lại mục 1.2 / 2.2, hoặc chạy `cpu` |
| `pc-up.sh`: "Working tree có thay đổi chưa commit" | Có file sửa dở trong repo | `git status`, commit hoặc `git checkout -- <file>` |

## 5. Dừng, cập nhật, gỡ

```bash
deploy/railway/pc-up.sh down                          # dừng (giữ image và cache)
git pull && deploy/railway/pc-up.sh cpu               # cập nhật lên commit mới của nhánh deploy
docker compose -f deploy/railway/compose.pc.yaml --env-file .env.pc --profile cpu --profile gpu down -v
                                                      # gỡ hẳn: xóa cả cache (model, dataset tải về)
docker image rm advertest-worker:cpu                  # xóa image
```

Cache chỉ là bản sao từ bucket: xóa đi thì lần chạy sau tải lại, không mất dữ liệu trên Railway.
Worker nên chạy cùng commit với service `api` trên Railway; sau khi cập nhật api, cập nhật worker theo.
