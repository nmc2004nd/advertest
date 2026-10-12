#!/usr/bin/env bash
# Tạo 4 bucket trên MinIO của Railway (giống service minio-init của docker/compose.yaml); chạy lại
# không lỗi. Biến lấy từ ENV_FILE (mặc định .env.pc): MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY.
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
env_file="${ENV_FILE:-$root/.env.pc}"
set -a; . "$env_file"; set +a

: "${MINIO_ENDPOINT:?Cần MINIO_ENDPOINT (https://<domain của minio>)}"
: "${MINIO_ACCESS_KEY:?Cần MINIO_ACCESS_KEY}"
: "${MINIO_SECRET_KEY:?Cần MINIO_SECRET_KEY}"
scheme="${MINIO_ENDPOINT%%://*}"
host="${MINIO_ENDPOINT#*://}"
# Khóa nằm trong biến môi trường, không nằm trên dòng lệnh.
export MC_HOST_railway="$scheme://$MINIO_ACCESS_KEY:$MINIO_SECRET_KEY@$host"

docker run --rm -e MC_HOST_railway \
  cgr.dev/chainguard/minio-client@sha256:b2bd7824d23d3e3b15bedd7e87fbc3be29d2e213307b4f901e4a1d92356dc20f \
  mb --ignore-existing railway/artifacts railway/reports railway/datasets railway/models
