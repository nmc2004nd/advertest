#!/bin/sh
# 1. Chạy migration bằng role advertest_owner (MIGRATION_DATABASE_URL).
# 2. Chạy API bằng role advertest_app (DATABASE_URL); xóa URL của owner khỏi môi trường của app.
#    X-Forwarded-For do app xử lý theo TRUSTED_PROXIES (backend/app/main.py), không do uvicorn.
set -eu

: "${MIGRATION_DATABASE_URL:?Cần MIGRATION_DATABASE_URL (role advertest_owner)}"
: "${DATABASE_URL:?Cần DATABASE_URL (role advertest_app)}"

alembic -c backend/alembic.ini upgrade head

exec env -u MIGRATION_DATABASE_URL \
  uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers
