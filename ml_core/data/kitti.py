"""Converter KITTI 2D object → manifest nội bộ (`DatasetManifest`).

Thư mục `root` chứa `image_2/*.png` và `label_2/*.txt` (định dạng label gốc của KITTI).
Manifest lưu tọa độ ảnh gốc; `DontCare` thành ignore region `dont_care`. Ignore region
`unmapped:<class>` và `difficulty:<class>` chỉ sinh ra khi áp mapping (`ml_core.data.mapping`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    ConverterInfo,
    DatasetManifest,
    IgnoreRegion,
    ManifestAnnotation,
    ManifestImage,
    ManifestSource,
)
from ml_core.fixtures import sha256_file

KITTI_CLASSES = ("Car", "Van", "Truck", "Pedestrian", "Person_sitting", "Cyclist", "Tram", "Misc")
DONT_CARE = "DontCare"
CONVERTER = ConverterInfo(name="advertest-import-kitti", version="1")


class KittiLabelError(ValueError):
    """Dòng label KITTI không hợp lệ."""


@dataclass(frozen=True)
class KittiObject:
    category: str
    truncated: float
    occluded: int
    bbox: tuple[float, float, float, float]  # left, top, right, bottom (xyxy, pixel ảnh gốc)


def parse_label_line(line: str) -> KittiObject:
    """Một dòng label KITTI.

    Các trường: `type truncated occluded alpha left top right bottom h w l x y z ry`.
    """
    fields = line.split()
    if len(fields) < 8:
        raise KittiLabelError(f"Dòng label thiếu trường: {line!r}")
    category = fields[0]
    if category not in KITTI_CLASSES and category != DONT_CARE:
        raise KittiLabelError(f"Class KITTI không biết: {category!r}")
    try:
        truncated = float(fields[1])
        occluded = int(fields[2])
        left, top, right, bottom = (float(v) for v in fields[4:8])
    except ValueError as exc:
        raise KittiLabelError(f"Dòng label sai định dạng số: {line!r}") from exc
    return KittiObject(category, truncated, occluded, (left, top, right, bottom))


def parse_label_file(path: Path) -> list[KittiObject]:
    return [parse_label_line(line) for line in path.read_text().splitlines() if line.strip()]


def import_kitti(root: Path, split: str = "training") -> DatasetManifest:
    """Tạo manifest từ `root/image_2` và `root/label_2`. Ảnh nào cũng phải có file label."""
    image_dir, label_dir = root / "image_2", root / "label_2"
    paths = sorted(image_dir.glob("*.png"))
    if not paths:
        raise FileNotFoundError(f"Không có ảnh PNG trong {image_dir}")

    images: list[ManifestImage] = []
    annotations: list[ManifestAnnotation] = []
    ignore_regions: list[IgnoreRegion] = []
    for path in paths:
        image_id = path.stem
        label_path = label_dir / f"{image_id}.txt"
        if not label_path.is_file():
            raise FileNotFoundError(f"Thiếu file label {label_path}")
        with Image.open(path) as img:
            width, height = img.size
        images.append(
            ManifestImage(
                image_id=image_id,
                file_name=path.relative_to(root).as_posix(),
                sha256=sha256_file(path),
                width=width,
                height=height,
            )
        )
        for obj in parse_label_file(label_path):
            if obj.category == DONT_CARE:
                ignore_regions.append(
                    IgnoreRegion(image_id=image_id, bbox=obj.bbox, source="dont_care")
                )
            else:
                annotations.append(
                    ManifestAnnotation(
                        image_id=image_id,
                        bbox=obj.bbox,
                        category=obj.category,
                        attributes={"truncated": obj.truncated, "occluded": obj.occluded},
                    )
                )

    return DatasetManifest(
        images=images,
        annotations=annotations,
        ignore_regions=ignore_regions,
        categories=list(KITTI_CLASSES),
        source=ManifestSource(format="kitti", split=split, converter=CONVERTER),
    )


def dataset_version_sha256(manifest: DatasetManifest) -> str:
    return sha256_of(manifest)
