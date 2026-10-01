#!/usr/bin/env bash
# E2E Playwright với backend thật (Phase 4 Group 0, task 4b): migration, seed admin, uvicorn,
# rồi `pnpm --dir frontend e2e` (Playwright tự build và chạy `vite preview` có proxy /api).
# Phase 5 (plan.md task 3a): dữ liệu fixture (5 ảnh KITTI, YOLOv8n; cần `make fixtures`) đăng ký
# bằng `advertest-admin import-local`, worker CPU thật cho máy `local-dev`, và
# DEV_ALLOW_UNBLURRED=true (fixture KITTI chưa làm mờ, requirements.md Phase 5 Decisions).
# Phase 6 (plan.md task 36a): `adv_patch` nạp với `max_iter = 4` thay cho 200 (giữ `batch_size`
# của spec, đề xuất contract 001); fixture có 5 ảnh nên thêm slice đánh giá 3 ảnh và slice huấn
# luyện 2 ảnh không giao nhau (`slice create --exclude-slice`) cho kịch bản patch.
# Cần Postgres đã có role (ADVERTEST_TEST_OWNER_URL, ADVERTEST_TEST_APP_URL) và MinIO
# (ADVERTEST_TEST_MINIO_*), ví dụ qua `docker/postgres/test-db.sh scripts/e2e.sh` (make test-e2e)
# hoặc service container của CI. Tham số thêm được chuyển cho Playwright (ví dụ --project=phone).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT="${ADVERTEST_E2E_API_PORT:-58000}"
: "${ADVERTEST_TEST_OWNER_URL:?Cần ADVERTEST_TEST_OWNER_URL}"
: "${ADVERTEST_TEST_APP_URL:?Cần ADVERTEST_TEST_APP_URL}"
: "${ADVERTEST_TEST_MINIO_ENDPOINT:?Cần ADVERTEST_TEST_MINIO_ENDPOINT (MinIO cho artifact và worker)}"

export DATABASE_URL="$ADVERTEST_TEST_APP_URL"
export MINIO_ENDPOINT="$ADVERTEST_TEST_MINIO_ENDPOINT"
export MINIO_ACCESS_KEY="${ADVERTEST_TEST_MINIO_ACCESS_KEY:?Cần ADVERTEST_TEST_MINIO_ACCESS_KEY}"
export MINIO_SECRET_KEY="${ADVERTEST_TEST_MINIO_SECRET_KEY:?Cần ADVERTEST_TEST_MINIO_SECRET_KEY}"
# Tài khoản admin và khóa ký URL ảnh chỉ dùng cho DB tạm của E2E, không phải bí mật.
export ADVERTEST_ADMIN_EMAIL="${ADVERTEST_ADMIN_EMAIL:-admin@e2e.test}"
export ADVERTEST_ADMIN_PASSWORD="${ADVERTEST_ADMIN_PASSWORD:-e2e-admin-password}"
export ARTIFACT_TOKEN_SECRET="${ARTIFACT_TOKEN_SECRET:-e2e-artifact-token-secret}"
export DEV_ALLOW_UNBLURRED=true
unset SMTP_HOST  # E2E không gửi email

cd "$ROOT"
[ -f tests/fixtures/yolov8n.pt ] || { echo "Thiếu fixture: chạy make fixtures" >&2; exit 1; }
WORK="$(mktemp -d)"
PIDS=()
cleanup() {
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  rm -rf "$WORK"
}
trap cleanup EXIT

# Ultralytics lần đầu import in thông báo tạo file settings ra stdout, làm hỏng JSON của CLI
# `advertest` (máy CI luôn là lần đầu). Thư mục cấu hình riêng để mọi máy chạy như CI; import
# trước một lần để thông báo đó không lẫn vào output được đọc.
export YOLO_CONFIG_DIR="$WORK/ultralytics"
uv run --no-sync python -c "import ultralytics" >/dev/null

MIGRATION_DATABASE_URL="$ADVERTEST_TEST_OWNER_URL" uv run --no-sync alembic -c backend/alembic.ini upgrade head
uv run --no-sync python -m backend.admin_cli.seed

# adv_patch cho E2E: cùng tên và version với seed, max_iter = 4 (hash và id tính lại). DB tạm.
MIGRATION_DATABASE_URL="$ADVERTEST_TEST_OWNER_URL" uv run --no-sync python - <<'PY'
import os

from sqlalchemy import create_engine, update

from advertest_contracts.ids import content_id
from advertest_contracts.models import AttackSpec, compute_spec_sha256
from backend.admin_cli.seed import load_attack_specs
from backend.app.db import models as m

E2E_MAX_ITER = 4
base = next(s for s in load_attack_specs() if s.name == "adv_patch")
assert base.training is not None
body = base.model_dump(mode="json", exclude={"id", "spec_sha256"})
body["training"]["max_iter"] = E2E_MAX_ITER
body["training"]["checkpoint_every"] = 2
sha = compute_spec_sha256(body)
spec = AttackSpec.model_validate({**body, "id": str(content_id(sha)), "spec_sha256": sha})
engine = create_engine(os.environ["MIGRATION_DATABASE_URL"])
with engine.begin() as conn:
    done = conn.execute(
        update(m.AttackSpecRow)
        .where(m.AttackSpecRow.id == base.id)
        .values(id=spec.id, spec=spec.model_dump(mode="json"), spec_sha256=spec.spec_sha256)
    )
    assert done.rowcount == 1, "Không tìm thấy adv_patch của seed"
print(f"adv_patch E2E: max_iter = {E2E_MAX_ITER}, spec_sha256 = {spec.spec_sha256}")
PY

# Bucket MinIO (như minio-init của compose).
uv run --no-sync python - <<'PY'
from typing import Any

from backend.app.storage import BUCKET_ARTIFACTS, BUCKET_DATASETS, BUCKET_MODELS, make_s3_client

client: Any = make_s3_client()
existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
for name in (BUCKET_MODELS, BUCKET_DATASETS, BUCKET_ARTIFACTS):
    if name not in existing:
        client.create_bucket(Bucket=name)
PY

# Dữ liệu fixture: dataset, model, slice 5 ảnh, mapping kitti-coco (như test nghiệm thu Phase 3, 5).
STORE="$WORK/store"
field() { uv run --no-sync python -c "import json,sys; print(json.load(sys.stdin)['$1'])"; }
DATASET="$(uv run --no-sync advertest --store-dir "$STORE" dataset import-kitti --root tests/fixtures/kitti | field dataset_version_sha256)"
MODEL="$(uv run --no-sync advertest --store-dir "$STORE" model register --weights tests/fixtures/yolov8n.pt --name yolov8n-coco | field id)"
uv run --no-sync advertest --store-dir "$STORE" slice create --dataset "$DATASET" --size 5 --seed 42 >/dev/null
# Phase 6: slice đánh giá 3 ảnh và slice huấn luyện 2 ảnh còn lại (không giao) cho patch.
EVAL3="$(uv run --no-sync advertest --store-dir "$STORE" slice create --dataset "$DATASET" --size 3 --seed 6 | field id)"
uv run --no-sync advertest --store-dir "$STORE" slice create --dataset "$DATASET" --size 2 --seed 6 --exclude-slice "$EVAL3" >/dev/null
uv run --no-sync advertest --store-dir "$STORE" mapping create --dataset "$DATASET" --model "$MODEL" >/dev/null
uv run --no-sync advertest-admin import-local --store "$STORE" --as "$ADVERTEST_ADMIN_EMAIL"
TOKEN="$(uv run --no-sync advertest-admin compute-target rotate-token local-dev --as "$ADVERTEST_ADMIN_EMAIL" | tail -n 1)"
# Máy local không có worker: experiment gửi tới đây nằm chờ (E2E giới hạn 3 experiment đang chờ).
uv run --no-sync advertest-admin compute-target create --name e2e-offline --as "$ADVERTEST_ADMIN_EMAIL" >/dev/null

uv run --no-sync uvicorn backend.app.main:app --host 127.0.0.1 --port "$API_PORT" --no-access-log &
PIDS+=("$!")
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 && break
  sleep 1
done

# Worker CPU thật cho local-dev (lease mỗi 5 giây khi rảnh).
API_URL="http://127.0.0.1:$API_PORT" WORKER_TOKEN="$TOKEN" CACHE_DIR="$WORK/worker-cache" DEVICE=cpu \
  uv run --no-sync advertest-worker run >"$WORK/worker.log" 2>&1 &
PIDS+=("$!")

status=0
API_PROXY_TARGET="http://127.0.0.1:$API_PORT" pnpm --dir frontend e2e "$@" || status=$?
if [ "$status" -ne 0 ]; then
  echo "---- 50 dòng cuối log worker ----" >&2
  tail -n 50 "$WORK/worker.log" >&2 || true
fi
exit "$status"
