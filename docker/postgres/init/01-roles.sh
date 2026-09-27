#!/usr/bin/env bash
# Chạy một lần khi Postgres khởi tạo thư mục dữ liệu (docker-entrypoint-initdb.d), bằng superuser.
# Tạo hai role của ứng dụng và database; quyền trên từng bảng do migration cấp.
#   advertest_owner: chạy migration, sở hữu bảng.
#   advertest_app:   ứng dụng dùng khi chạy; không sở hữu bảng nào.
set -euo pipefail

: "${ADVERTEST_DB:=advertest}"
: "${ADVERTEST_OWNER_PASSWORD:?Cần ADVERTEST_OWNER_PASSWORD}"
: "${ADVERTEST_APP_PASSWORD:?Cần ADVERTEST_APP_PASSWORD}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v db="$ADVERTEST_DB" \
  -v owner_pw="$ADVERTEST_OWNER_PASSWORD" \
  -v app_pw="$ADVERTEST_APP_PASSWORD" <<'SQL'
CREATE ROLE advertest_owner LOGIN PASSWORD :'owner_pw';
CREATE ROLE advertest_app LOGIN PASSWORD :'app_pw';
CREATE DATABASE :"db" OWNER advertest_owner;
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO advertest_app;
SQL
