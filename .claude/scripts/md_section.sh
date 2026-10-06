#!/usr/bin/env bash
# In một mục markdown: từ dòng tiêu đề khớp regex tới trước tiêu đề cùng cấp hoặc cấp cao hơn kế tiếp.
# Cách dùng: md_section.sh <file> <regex tiêu đề> [--all]
# Ví dụ:    md_section.sh specs/tech-stack.md '^## 4\.'
#           md_section.sh specs/<phase>/plan.md '^## Group 3'
#           md_section.sh specs/<phase>/requirements.md '^### Chốt ở Group' --all
# Mặc định chỉ in mục khớp đầu tiên; --all in mọi mục khớp. Dòng trong khối ``` không được coi là tiêu đề.
# Thoát 1 nếu không mục nào khớp.

set -uo pipefail

if [ $# -lt 2 ]; then
  echo "Cách dùng: md_section.sh <file> <regex tiêu đề> [--all]" >&2
  exit 2
fi
FILE="$1"; PATTERN="$2"; ALL=0
[ "${3:-}" = "--all" ] && ALL=1
[ -f "$FILE" ] || { echo "Lỗi: không có file '$FILE'." >&2; exit 2; }

awk -v pat="$PATTERN" -v all="$ALL" '
  /^```/ { fence = !fence }
  {
    is_head = 0; lvl = 0
    if (!fence || /^```/) {
      if (match($0, /^#+ /)) { is_head = 1; lvl = RLENGTH - 1 }
    }
    if (printing && is_head && lvl <= cur) { printing = 0; if (!all) exit }
    if (!printing && is_head && $0 ~ pat) { printing = 1; cur = lvl; found = 1; printf "%s:%d\n", FILENAME, NR }
    if (printing) print
  }
  END { exit found ? 0 : 1 }
' "$FILE"
