#!/usr/bin/env bash
# Build và khởi động phần chạy trên PC (worker + worker công cụ + sandbox chuyển đổi), gọi API
# trên Railway. Giống docker/worker/up.sh: DOCKER_IMAGE_DIGEST là image ID thật của image vừa build.
#
# Cách dùng: deploy/railway/pc-up.sh cpu|gpu   (biến lấy từ ENV_FILE, mặc định .env.pc)
#            deploy/railway/pc-up.sh down
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
env_file="${ENV_FILE:-.env.pc}"
compose=(docker compose -f deploy/railway/compose.pc.yaml --env-file "$env_file")

profile="${1:-}"
case "$profile" in
  cpu) service=worker-cpu ;;
  gpu) service=worker ;;
  down) "${compose[@]}" --profile cpu --profile gpu down; exit 0 ;;
  *) echo "Cách dùng: $0 cpu|gpu|down" >&2; exit 2 ;;
esac

# Image không có .git: GIT_COMMIT được coi là mã sạch, nên chỉ build từ working tree sạch.
if [ -n "$(git status --porcelain --untracked-files=no -- . ':!.ai-log')" ]; then
  echo "Working tree có thay đổi chưa commit: commit trước khi build worker." >&2
  exit 1
fi
export GIT_COMMIT="$(git rev-parse HEAD)"

compose+=(--profile "$profile")
"${compose[@]}" build "$service" worker-tools
DOCKER_IMAGE_DIGEST="$(docker image inspect --format '{{.Id}}' "advertest-worker:$profile")"
export DOCKER_IMAGE_DIGEST
echo "Image advertest-worker:$profile $DOCKER_IMAGE_DIGEST (commit $GIT_COMMIT)"
"${compose[@]}" up -d --no-build "$service" worker-tools converter
