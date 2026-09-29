#!/usr/bin/env bash
# E2E Playwright với backend thật (Phase 4 Group 0, task 4b): migration, seed admin, uvicorn,
# rồi `pnpm --dir frontend e2e` (Playwright tự build và chạy `vite preview` có proxy /api).
# Cần Postgres đã có role (ADVERTEST_TEST_OWNER_URL, ADVERTEST_TEST_APP_URL), ví dụ qua
# `docker/postgres/test-db.sh scripts/e2e.sh` (make test-e2e) hoặc service container của CI.
# Tham số thêm được chuyển cho Playwright (ví dụ --project=phone).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT="${ADVERTEST_E2E_API_PORT:-58000}"
: "${ADVERTEST_TEST_OWNER_URL:?Cần ADVERTEST_TEST_OWNER_URL}"
: "${ADVERTEST_TEST_APP_URL:?Cần ADVERTEST_TEST_APP_URL}"

export DATABASE_URL="$ADVERTEST_TEST_APP_URL"
export MINIO_ENDPOINT="${ADVERTEST_TEST_MINIO_ENDPOINT:-http://127.0.0.1:9}"
export MINIO_ACCESS_KEY="${ADVERTEST_TEST_MINIO_ACCESS_KEY:-none}"
export MINIO_SECRET_KEY="${ADVERTEST_TEST_MINIO_SECRET_KEY:-none}"
# Tài khoản admin chỉ dùng cho DB tạm của E2E, không phải bí mật.
export ADVERTEST_ADMIN_EMAIL="${ADVERTEST_ADMIN_EMAIL:-admin@e2e.test}"
export ADVERTEST_ADMIN_PASSWORD="${ADVERTEST_ADMIN_PASSWORD:-e2e-admin-password}"

cd "$ROOT"
MIGRATION_DATABASE_URL="$ADVERTEST_TEST_OWNER_URL" uv run --no-sync alembic -c backend/alembic.ini upgrade head
uv run --no-sync python -m backend.admin_cli.seed

uv run --no-sync uvicorn backend.app.main:app --host 127.0.0.1 --port "$API_PORT" &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 && break
  sleep 1
done

API_PROXY_TARGET="http://127.0.0.1:$API_PORT" pnpm --dir frontend e2e "$@"
