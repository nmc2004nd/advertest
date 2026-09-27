#!/usr/bin/env bash
# Dựng Postgres tạm (cùng script init role như môi trường thật), chạy test đánh dấu `db`, rồi dọn.
# Cách dùng: docker/postgres/test-db.sh <lệnh pytest...>
set -uo pipefail

NAME="advertest-pg-test-$$"
PORT="${ADVERTEST_TEST_PG_PORT:-55433}"
IMAGE="postgres:17-alpine"
HERE="$(cd "$(dirname "$0")" && pwd)"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" -p "127.0.0.1:$PORT:5432" \
  -e POSTGRES_PASSWORD=pg-test \
  -e ADVERTEST_OWNER_PASSWORD=owner-test \
  -e ADVERTEST_APP_PASSWORD=app-test \
  -v "$HERE/init:/docker-entrypoint-initdb.d:ro" \
  "$IMAGE" >/dev/null || exit 1

# Script init tạo role sau khi server tạm khởi động; chờ đến khi role app kết nối được vào DB.
for _ in $(seq 1 60); do
  if docker exec -e PGPASSWORD=app-test "$NAME" \
       psql -h 127.0.0.1 -U advertest_app -d advertest -tAc "select 1" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

export ADVERTEST_TEST_OWNER_URL="postgresql+psycopg://advertest_owner:owner-test@127.0.0.1:$PORT/advertest"
export ADVERTEST_TEST_APP_URL="postgresql+psycopg://advertest_app:app-test@127.0.0.1:$PORT/advertest"
"$@"
