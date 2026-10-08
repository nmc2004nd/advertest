#!/usr/bin/env bash
# Dựng Postgres tạm (cùng script init role như môi trường thật) và MinIO tạm (cùng image với
# docker/compose.yaml), chạy test đánh dấu `db`, rồi dọn.
# Cách dùng: docker/postgres/test-db.sh <lệnh pytest...>
set -uo pipefail

PG_NAME="advertest-pg-test-$$"
MINIO_NAME="advertest-minio-test-$$"
PG_PORT="${ADVERTEST_TEST_PG_PORT:-55433}"
MINIO_PORT="${ADVERTEST_TEST_MINIO_PORT:-59000}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# Cùng digest với service minio trong docker/compose.yaml.
MINIO_IMAGE="$(sed -n 's/^x-minio-image: &minio-image //p' "$HERE/../compose.yaml")"
MINIO_KEY="advertest"
MINIO_SECRET="minio-test-secret"

cleanup() { docker rm -f "$PG_NAME" "$MINIO_NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$PG_NAME" -p "127.0.0.1:$PG_PORT:5432" \
  -e POSTGRES_PASSWORD=pg-test \
  -e ADVERTEST_OWNER_PASSWORD=owner-test \
  -e ADVERTEST_APP_PASSWORD=app-test \
  -v "$HERE/init:/docker-entrypoint-initdb.d:ro" \
  postgres:17-alpine >/dev/null || exit 1

docker run -d --name "$MINIO_NAME" -p "127.0.0.1:$MINIO_PORT:9000" \
  -e MINIO_ROOT_USER="$MINIO_KEY" \
  -e MINIO_ROOT_PASSWORD="$MINIO_SECRET" \
  -e MC_HOST_local="http://$MINIO_KEY:$MINIO_SECRET@127.0.0.1:9000" \
  "$MINIO_IMAGE" server /data >/dev/null || exit 1

# Script init tạo role sau khi server tạm khởi động; chờ đến khi role app kết nối được vào DB.
for _ in $(seq 1 60); do
  if docker exec -e PGPASSWORD=app-test "$PG_NAME" \
       psql -h 127.0.0.1 -U advertest_app -d advertest -tAc "select 1" >/dev/null 2>&1 \
     && docker exec "$MINIO_NAME" mc ready local >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

export ADVERTEST_TEST_OWNER_URL="postgresql+psycopg://advertest_owner:owner-test@127.0.0.1:$PG_PORT/advertest"
export ADVERTEST_TEST_APP_URL="postgresql+psycopg://advertest_app:app-test@127.0.0.1:$PG_PORT/advertest"
export ADVERTEST_TEST_MINIO_ENDPOINT="http://127.0.0.1:$MINIO_PORT"
export ADVERTEST_TEST_MINIO_ACCESS_KEY="$MINIO_KEY"
export ADVERTEST_TEST_MINIO_SECRET_KEY="$MINIO_SECRET"

# CPU lai (Intel P-core/E-core): oneDNN chia khối theo loại lõi chạy phép tính torch đầu tiên của
# process và giữ cả process, nên PGD 1 luồng vẫn cho failure case khác nhau giữa P-core và E-core
# (golden R1 lệch 36↔37). Golden ghi trên P-core: ghim test vào P-core từ đầu process.
# Ghim làm torch tự giảm số luồng mặc định; test không ghim luồng (Phase 8, dừng sớm) cần số luồng
# như khi không ghim (số lõi vật lý), nên giữ bằng OMP_NUM_THREADS (trừ khi đã đặt sẵn).
# ADVERTEST_TEST_NO_PIN=1 để tắt.
P_CORES="/sys/devices/cpu_core/cpus"
if [ -z "${ADVERTEST_TEST_NO_PIN:-}" ] && [ -r "$P_CORES" ] && command -v taskset >/dev/null; then
  export OMP_NUM_THREADS="${OMP_NUM_THREADS:-$(lscpu -p=CORE,SOCKET | grep -v '^#' | sort -u | wc -l)}"
  echo ">> CPU lai: ghim test vào P-core $(cat "$P_CORES"), OMP_NUM_THREADS=$OMP_NUM_THREADS" >&2
  taskset -c "$(cat "$P_CORES")" "$@"
else
  "$@"
fi
