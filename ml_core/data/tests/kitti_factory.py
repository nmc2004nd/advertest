"""Tạo thư mục KITTI nhỏ trong `tmp_path` để test không cần tải fixture."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

WIDTH, HEIGHT = 124, 40


def label_line(
    category: str,
    bbox: tuple[float, float, float, float],
    truncated: float = 0.0,
    occluded: int = 0,
) -> str:
    left, top, right, bottom = bbox
    return (
        f"{category} {truncated:.2f} {occluded} -1.00 "
        f"{left:.2f} {top:.2f} {right:.2f} {bottom:.2f} 1.50 1.60 3.70 1.00 1.50 20.00 0.10"
    )


def make_kitti(
    root: Path, labels: dict[str, list[str]], size: tuple[int, int] = (WIDTH, HEIGHT)
) -> Path:
    """`labels`: image_id → các dòng label. Mỗi ảnh có màu khác nhau để sha256 khác nhau."""
    (root / "image_2").mkdir(parents=True, exist_ok=True)
    (root / "label_2").mkdir(parents=True, exist_ok=True)
    for i, (image_id, lines) in enumerate(sorted(labels.items())):
        Image.new("RGB", size, (i * 7 % 256, 100, 200)).save(root / "image_2" / f"{image_id}.png")
        (root / "label_2" / f"{image_id}.txt").write_text("\n".join(lines) + "\n")
    return root
