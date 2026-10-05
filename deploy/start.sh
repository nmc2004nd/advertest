#!/usr/bin/env bash
# Dựng toàn bộ AdverTest bằng Docker trên một máy: Postgres, MinIO, Mailpit, API, frontend, worker
# CPU; nạp tài khoản admin, attack catalog, 5 ảnh KITTI mẫu và model YOLOv8n.
#
# Cách dùng (từ thư mục gốc repo):  bash deploy/start.sh
# Windows: chạy trong Git Bash hoặc WSL, Docker Desktop đang bật.
# Chạy lại bao nhiêu lần cũng được; dữ liệu giữ nguyên giữa các lần (xóa sạch: bash deploy/stop.sh --xoa).
set -euo pipefail

cd "$(dirname "$0")/.."
# Git Bash trên Windows tự đổi "/data/store" thành "C:/Program Files/Git/data/store"; tắt việc đó
# vì các đường dẫn này nằm trong container, không phải trên máy.
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*"
ENV_FILE=.env
DC=(docker compose -f docker/compose.yaml -f deploy/compose.local.yaml --env-file "$ENV_FILE")

say() { printf '\n\033[1;35m▸ %s\033[0m\n' "$*"; }
rnd() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${1:-24}"; }

command -v docker >/dev/null || { echo "Chưa có Docker. Cài Docker Desktop rồi chạy lại." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker chưa chạy. Mở Docker Desktop rồi chạy lại." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Cần Docker Compose v2 (lệnh 'docker compose')." >&2; exit 1; }

# 1. File .env với mật khẩu ngẫu nhiên (chỉ tạo một lần, không ghi đè).
if [ ! -f "$ENV_FILE" ]; then
  say "Tạo .env với mật khẩu ngẫu nhiên"
  cat >"$ENV_FILE" <<ENV
POSTGRES_PASSWORD=$(rnd)
ADVERTEST_OWNER_PASSWORD=$(rnd)
ADVERTEST_APP_PASSWORD=$(rnd)
MINIO_ACCESS_KEY=advertest
MINIO_SECRET_KEY=$(rnd 32)
MINIO_PUBLIC_ENDPOINT=http://minio:9000
ARTIFACT_TOKEN_SECRET=$(rnd 40)
DEV_ALLOW_UNBLURRED=false
COOKIE_SECURE=false
APP_BASE_URL=http://localhost:5173
SMTP_FROM="AdverTest <no-reply@advertest.local>"
ADVERTEST_ADMIN_EMAIL=admin@example.com
ADVERTEST_ADMIN_PASSWORD=Admin$(rnd 12)
WORKER_DEVICE=cpu
WORKER_TOKEN=
ENV
  chmod 600 "$ENV_FILE" 2>/dev/null || true
fi
set -a; . "./$ENV_FILE"; set +a

# 2. Commit của code (worker ghi vào mỗi run; cần mã 40 ký tự hex).
if git rev-parse HEAD >/dev/null 2>&1; then
  GIT_COMMIT=$(git rev-parse HEAD)
else
  GIT_COMMIT=$(git hash-object -t blob --stdin <<<"advertest-local" 2>/dev/null || printf '%040d' 0)
fi
export GIT_COMMIT

# 3. Dữ liệu mẫu: container api đọc data/ ở /data (chỉ đọc).
say "Chuẩn bị dữ liệu mẫu trong data/"
for f in data/store/datasets/*/sources/*.json; do
  [ -f "$f" ] && sed -i.bak 's#"root": *"[^"]*"#"root": "/data/kitti-fixture"#' "$f" && rm -f "$f.bak"
done
chmod -R a+rX data 2>/dev/null || true

# 4. Build và khởi động (lần đầu mất 5–15 phút: tải image, PyTorch CPU, gói Node).
say "Build và khởi động Postgres, MinIO, Mailpit, API, frontend"
"${DC[@]}" up -d --build --wait

say "Nạp attack catalog, máy chạy local-dev và tài khoản admin"
"${DC[@]}" exec -T -e ADVERTEST_ADMIN_EMAIL -e ADVERTEST_ADMIN_PASSWORD api python -m backend.admin_cli.seed

say "Nạp model YOLOv8n, dataset và slice 5 ảnh"
"${DC[@]}" exec -T api advertest-admin import-local --store /data/store --as "$ADVERTEST_ADMIN_EMAIL"

# 5. Worker: token mới mỗi lần chạy (token cũ hết hiệu lực), lưu vào .env.
say "Khởi động worker CPU"
WORKER_TOKEN=$("${DC[@]}" exec -T api advertest-admin compute-target rotate-token local-dev --as "$ADVERTEST_ADMIN_EMAIL" | tail -n 1 | tr -d '\r')
export WORKER_TOKEN
if grep -q '^WORKER_TOKEN=' "$ENV_FILE"; then
  sed -i.bak "s#^WORKER_TOKEN=.*#WORKER_TOKEN=$WORKER_TOKEN#" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
else
  echo "WORKER_TOKEN=$WORKER_TOKEN" >>"$ENV_FILE"
fi
"${DC[@]}" --profile worker up -d --build worker-local

cat <<DONE

$(printf '\033[1;32m')AdverTest đã chạy.$(printf '\033[0m')

  Ứng dụng web   http://localhost:5173
  Đăng nhập      $ADVERTEST_ADMIN_EMAIL  /  $ADVERTEST_ADMIN_PASSWORD
  Hộp thư (email hệ thống gửi)   http://127.0.0.1:8025
  Trạng thái API                 http://127.0.0.1:8000/health

Tiếp theo: mở web → "Yêu cầu truy cập" tạo 1 tài khoản kỹ sư và 1 reviewer, rồi đăng nhập admin
→ Người dùng → Chờ duyệt → Duyệt (chọn role). Kịch bản demo: docs/demo-mvp.md mục 7.

Xem log worker:   docker compose -f docker/compose.yaml -f deploy/compose.local.yaml --env-file .env logs -f worker-local
Dừng:             bash deploy/stop.sh
DONE
