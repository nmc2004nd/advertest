#!/usr/bin/env bash
# Đặt CORS cho bucket Railway: trình duyệt PUT file model thẳng lên presigned URL (Đăng ký model →
# upload weights), nên bucket phải cho phép origin của frontend. Chạy lại không lỗi.
# Biến lấy từ ENV_FILE (mặc định .env.pc): MINIO_ENDPOINT, MINIO_BUCKET, MINIO_REGION,
# MINIO_ACCESS_KEY, MINIO_SECRET_KEY, APP_BASE_URL (https://<domain của frontend>).
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
env_file="${ENV_FILE:-$root/.env.pc}"
set -a; . "$env_file"; set +a

: "${MINIO_BUCKET:?Cần MINIO_BUCKET (biến BUCKET của bucket trên Railway)}"
: "${APP_BASE_URL:?Cần APP_BASE_URL (https://<domain của frontend>)}"
cd "$root"
# --extra cpu: thiếu cờ này uv đổi torch sang bản CUDA.
exec uv run --extra cpu python - <<'PY'
import os

from backend.app.storage import make_s3_client

client = make_s3_client()
bucket = os.environ["MINIO_BUCKET"]
client.put_bucket_cors(  # type: ignore[attr-defined]
    Bucket=bucket,
    CORSConfiguration={
        "CORSRules": [
            {
                "AllowedOrigins": [os.environ["APP_BASE_URL"].rstrip("/")],
                "AllowedMethods": ["GET", "PUT"],
                "AllowedHeaders": ["*"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3000,
            }
        ]
    },
)
print(client.get_bucket_cors(Bucket=bucket)["CORSRules"])  # type: ignore[attr-defined]
PY
