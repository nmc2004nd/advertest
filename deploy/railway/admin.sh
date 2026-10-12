#!/usr/bin/env bash
# Chạy lệnh quản trị trên PC, trỏ vào Postgres và bucket của Railway (biến lấy từ .env.pc).
#   deploy/railway/admin.sh python -m backend.admin_cli.seed
#   deploy/railway/admin.sh advertest-admin compute-target create --name pc --as <email admin>
#   deploy/railway/admin.sh advertest-admin import-local --store <thư mục LocalStore> --as <email admin>
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
env_file="${ENV_FILE:-$root/.env.pc}"
set -a; . "$env_file"; set +a
cd "$root"
# --extra cpu: thiếu cờ này uv đổi torch sang bản CUDA.
exec uv run --extra cpu "$@"
