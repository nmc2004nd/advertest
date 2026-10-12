#!/usr/bin/env bash
# Chạy MỘT lần sau khi thêm Postgres trên Railway: tạo role advertest_owner, advertest_app và
# database advertest bằng đúng script init của môi trường dev (docker/postgres/init/01-roles.sh).
# Chạy bên trong container Postgres qua `railway ssh` (cần `railway link` tới project và SSH key đã
# đăng ký: `railway ssh keys add`), không cần mở Postgres ra Internet. Mật khẩu lấy từ ENV_FILE
# (mặc định .env.pc).
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
env_file="${ENV_FILE:-$root/.env.pc}"
set -a; . "$env_file"; set +a

: "${ADVERTEST_OWNER_PASSWORD:?Cần ADVERTEST_OWNER_PASSWORD}"
: "${ADVERTEST_APP_PASSWORD:?Cần ADVERTEST_APP_PASSWORD}"
script="$(base64 -w0 "$root/docker/postgres/init/01-roles.sh")"

railway ssh -s "${POSTGRES_SERVICE:-Postgres}" -- "echo $script | base64 -d > /tmp/roles.sh \
  && ADVERTEST_OWNER_PASSWORD=$ADVERTEST_OWNER_PASSWORD ADVERTEST_APP_PASSWORD=$ADVERTEST_APP_PASSWORD \
  POSTGRES_USER=\${POSTGRES_USER:-postgres} POSTGRES_DB=\${POSTGRES_DB:-railway} bash /tmp/roles.sh; \
  rc=\$?; rm -f /tmp/roles.sh; exit \$rc"
echo "Đã tạo role và database advertest. Deploy lại service api để chạy migration."
