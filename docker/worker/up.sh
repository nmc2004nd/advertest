#!/usr/bin/env bash
# Build và khởi động worker trong Docker với DOCKER_IMAGE_DIGEST là image ID thật của image vừa
# build (image không tự biết digest của nó lúc build). Mặc định nên chạy worker trực tiếp trên
# máy (docs/van-hanh-worker.md); script này dành cho profile cpu (CI) và gpu.
#
# Cách dùng: docker/worker/up.sh cpu|gpu   (biến lấy từ ENV_FILE, mặc định .env ở gốc repo)
set -euo pipefail

profile="${1:-}"
case "$profile" in
  cpu) service=worker-cpu ;;
  gpu) service=worker ;;
  *) echo "Cách dùng: $0 cpu|gpu" >&2; exit 2 ;;
esac

root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
env_file="${ENV_FILE:-.env}"

# Image không có .git: GIT_COMMIT được coi là mã sạch (git_dirty = false), nên chỉ build từ
# working tree sạch (bỏ qua .ai-log/, giống quy tắc fingerprint).
if [ -n "$(git status --porcelain --untracked-files=no -- . ':!.ai-log')" ]; then
  echo "Working tree có thay đổi chưa commit: commit trước khi build worker." >&2
  exit 1
fi
export GIT_COMMIT="$(git rev-parse HEAD)"

compose=(docker compose -f docker/compose.yaml --env-file "$env_file" --profile "$profile")
"${compose[@]}" build "$service"
DOCKER_IMAGE_DIGEST="$(docker image inspect --format '{{.Id}}' "advertest-worker:$profile")"
export DOCKER_IMAGE_DIGEST
echo "Image advertest-worker:$profile $DOCKER_IMAGE_DIGEST (commit $GIT_COMMIT)"
"${compose[@]}" up -d --no-build "$service"
