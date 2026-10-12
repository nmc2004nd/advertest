#!/usr/bin/env bash
# Chạy lệnh quản trị bên trong container `api` trên Railway qua `railway ssh` (mạng riêng, đã có
# DATABASE_URL và biến của bucket). Cần `railway link` tới project và SSH key đã đăng ký.
#   deploy/railway/admin.sh python -m backend.admin_cli.seed       (ADVERTEST_ADMIN_* lấy từ .env.pc)
#   deploy/railway/admin.sh advertest-admin compute-target create --name pc --as <email admin>
# `import-local` đọc thư mục trên PC nên không chạy được theo cách này.
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
env_file="${ENV_FILE:-$root/.env.pc}"
set -a; . "$env_file"; set +a

args="$(printf '%q ' "$@")"
railway ssh -s "${API_SERVICE:-api}" -- "cd /app && \
  ADVERTEST_ADMIN_EMAIL=$(printf '%q' "${ADVERTEST_ADMIN_EMAIL:-}") \
  ADVERTEST_ADMIN_PASSWORD=$(printf '%q' "${ADVERTEST_ADMIN_PASSWORD:-}") $args"
