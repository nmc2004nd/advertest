#!/usr/bin/env bash
# Chạy MỘT lần sau khi thêm Postgres trên Railway: tạo role advertest_owner, advertest_app và
# database advertest bằng đúng script init của môi trường dev (docker/postgres/init/01-roles.sh).
# Kết nối qua TCP proxy công khai của Railway; biến lấy từ ENV_FILE (mặc định .env.pc).
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
env_file="${ENV_FILE:-$root/.env.pc}"
set -a; . "$env_file"; set +a

: "${PGHOST:?Cần PGHOST (TCP proxy của Postgres trên Railway)}"
: "${PGPORT:?Cần PGPORT}"
: "${PGPASSWORD:?Cần PGPASSWORD (superuser của Postgres trên Railway)}"
: "${ADVERTEST_OWNER_PASSWORD:?Cần ADVERTEST_OWNER_PASSWORD}"
: "${ADVERTEST_APP_PASSWORD:?Cần ADVERTEST_APP_PASSWORD}"
export PGHOST PGPORT PGPASSWORD ADVERTEST_OWNER_PASSWORD ADVERTEST_APP_PASSWORD

docker run --rm \
  -e PGHOST -e PGPORT -e PGPASSWORD -e ADVERTEST_OWNER_PASSWORD -e ADVERTEST_APP_PASSWORD \
  -e POSTGRES_USER="${POSTGRES_USER:-postgres}" -e POSTGRES_DB="${POSTGRES_DB:-railway}" \
  -v "$root/docker/postgres/init:/init:ro" \
  postgres:17-alpine bash /init/01-roles.sh
echo "Đã tạo role và database advertest. Deploy lại service api để chạy migration."
