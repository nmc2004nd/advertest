"""Tải fixture test và kiểm tra sha256 theo tests/fixtures/checksums.json (`make fixtures`)."""

from __future__ import annotations

import sys

from ml_core.fixtures import FixtureError, fetch_all, load_checksums


def main() -> int:
    try:
        downloaded = fetch_all()
    except FixtureError as exc:
        print(exc, file=sys.stderr)
        return 1
    total = len(load_checksums())
    print(f"Fixture đủ {total} file, mọi sha256 khớp (vừa tải {len(downloaded)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
