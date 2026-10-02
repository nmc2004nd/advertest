#!/usr/bin/env bash
# Quét diff giữa hai ref để tìm manh mối cho review.
# Cách dùng: scan_diff.sh <base> <branch> "<thư mục được sửa, cách nhau bởi dấu cách>"
# Ví dụ:    scan_diff.sh main phase01-model "ml_core/models"
# Kết quả chỉ là manh mối; reviewer phải đọc lại diff trước khi kết luận.

set -uo pipefail

BASE="${1:-main}"
BRANCH="${2:-HEAD}"
ALLOWED="${3:-}"

FORBIDDEN_PREFIXES=("specs/" "contracts/" "tests/acceptance/")
DEP_FILES=("pyproject.toml" "uv.lock" "requirements.txt" "frontend/package.json" "frontend/pnpm-lock.yaml" "package.json" "pnpm-lock.yaml")

if ! git rev-parse --verify --quiet "$BASE" >/dev/null || ! git rev-parse --verify --quiet "$BRANCH" >/dev/null; then
  echo "Lỗi: không tìm thấy ref '$BASE' hoặc '$BRANCH'." >&2
  exit 2
fi

RANGE="$BASE...$BRANCH"
CHANGED=$(git diff --name-only "$RANGE")
ADDED=$(git diff -U0 "$RANGE" | grep -E '^\+[^+]' || true)
REMOVED=$(git diff -U0 "$RANGE" | grep -E '^-[^-]' || true)

section() { printf '\n== %s ==\n' "$1"; }
found_any=0

section "File đã thay đổi"
if [ -z "$CHANGED" ]; then echo "(không có)"; else echo "$CHANGED"; fi

section "File nằm trong vùng cấm (specs/, contracts/, tests/acceptance/)"
hits=""
while IFS= read -r f; do
  [ -z "$f" ] && continue
  for p in "${FORBIDDEN_PREFIXES[@]}"; do
    case "$f" in "$p"*) hits+="$f"$'\n' ;; esac
  done
done <<< "$CHANGED"
if [ -n "$hits" ]; then printf '%s' "$hits"; found_any=1; else echo "(không có)"; fi

section "File ngoài thư mục được sửa"
if [ -z "$ALLOWED" ]; then
  echo "(bỏ qua: không truyền danh sách thư mục được sửa)"
else
  outside=""
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    ok=0
    for d in $ALLOWED; do
      d="${d%/}/"
      case "$f" in "$d"*) ok=1 ;; esac
    done
    [ "$ok" -eq 0 ] && outside+="$f"$'\n'
  done <<< "$CHANGED"
  if [ -n "$outside" ]; then printf '%s' "$outside"; found_any=1; else echo "(không có)"; fi
fi

section "Dấu hiệu làm yếu test hoặc vượt kiểm tra (dòng được thêm)"
weak=$(printf '%s\n' "$ADDED" | grep -nE 'pytest\.mark\.(skip|xfail)|pytest\.skip\(|@unittest\.skip|\b(it|test|describe)\.(skip|only)\(|\bxit\(|\bfit\(|type: ?ignore|# ?noqa|eslint-disable|@ts-ignore|@ts-expect-error|except[^:]*:\s*pass|rel=|abs=|atol=|rtol=|tolerance' || true)
if [ -n "$weak" ]; then printf '%s\n' "$weak"; found_any=1; else echo "(không có)"; fi

section "Số dòng assert/expect bị xóa"
removed_asserts=$(printf '%s\n' "$REMOVED" | grep -cE '\bassert\b|expect\(' || true)
echo "${removed_asserts:-0}"
[ "${removed_asserts:-0}" -gt 0 ] && found_any=1

section "Thay đổi file dependency"
dep_hits=""
for d in "${DEP_FILES[@]}"; do
  if printf '%s\n' "$CHANGED" | grep -qxF "$d"; then dep_hits+="$d"$'\n'; fi
done
if [ -n "$dep_hits" ]; then printf '%s' "$dep_hits"; found_any=1; else echo "(không có)"; fi

section "Dấu hiệu lộ bí mật (dòng được thêm)"
secrets=$(printf '%s\n' "$ADDED" | grep -nEi '(password|passwd|secret|api[_-]?key|token|access[_-]?key)\s*[:=]\s*["'"'"'][^"'"'"']{6,}' || true)
if [ -n "$secrets" ]; then printf '%s\n' "$secrets"; found_any=1; else echo "(không có)"; fi

section "Tóm tắt"
if [ "$found_any" -eq 1 ]; then
  echo "Có manh mối cần xem kỹ. Đọc lại từng dòng trong diff trước khi kết luận."
else
  echo "Không phát hiện manh mối tự động. Vẫn phải review thủ công 7 mục."
fi
exit 0
