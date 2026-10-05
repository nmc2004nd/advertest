#!/usr/bin/env bash
# Dừng AdverTest. Thêm --xoa để xóa luôn dữ liệu (database, ảnh trong MinIO, cache worker).
set -euo pipefail
cd "$(dirname "$0")/.."
DC=(docker compose -f docker/compose.yaml -f deploy/compose.local.yaml --env-file .env --profile worker)
if [ "${1:-}" = "--xoa" ]; then
  "${DC[@]}" down -v
  echo "Đã dừng và xóa dữ liệu. Chạy lại: bash deploy/start.sh"
else
  "${DC[@]}" down
  echo "Đã dừng; dữ liệu vẫn còn. Chạy lại: bash deploy/start.sh"
fi
