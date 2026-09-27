# Đề xuất contract 002: DatasetManifest

- Người đề xuất: agent ml-core, Phase 00, Group 6
- Trạng thái: chờ duyệt

## Vấn đề

- `plan.md` Phase 0 task 31 yêu cầu viết `tests/fixtures/manifest.json` "theo định dạng manifest nội bộ", và `validation.md` Phase 0 yêu cầu file này "validate được theo định dạng manifest nội bộ". Hiện `contracts/` không có schema nào cho định dạng đó, nên không có gì để validate.
- Định dạng mới chỉ được mô tả bằng một bảng trong `requirements.md` Phase 1 (mục "Manifest dataset nội bộ"). Định dạng này được dùng chung bởi nhiều agent: converter KITTI (Phase 1, ml-data), backend lưu `dataset_versions.manifest_sha256` và `manifest_uri` (Phase 3), converter YOLO/COCO (Phase 10). Dataset version là sha256 của manifest, nên chỉ cần lệch một trường là hash lệch.
- `tech-stack.md` mục 2.1: "Định dạng dataset nội bộ: manifest JSON kiểu COCO. Mọi định dạng khác phải đi qua converter."

## Thay đổi đề xuất

`contracts/python/advertest_contracts/models.py`: thêm, theo đúng bảng của `requirements.md` Phase 1.

```python
BBox = tuple[float, float, float, float]  # xyxy, pixel của ảnh gốc


def _check_bbox(bbox: BBox) -> BBox:
    x1, y1, x2, y2 = bbox
    if not (0 <= x1 <= x2 and 0 <= y1 <= y2):
        raise ValueError("bbox phải là xyxy với 0 <= x1 <= x2 và 0 <= y1 <= y2")
    return bbox


PixelBBox = Annotated[BBox, AfterValidator(_check_bbox)]


class ManifestImage(_Model):
    image_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    sha256: Sha256Hex
    width: PositiveInt
    height: PositiveInt
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class ManifestAnnotation(_Model):
    image_id: str
    bbox: PixelBBox
    category: str = Field(description="Class gốc của dataset, phải có trong categories")
    attributes: dict[str, JsonValue] = Field(
        default_factory=dict, description="KITTI: truncated (0-1), occluded (0-3)"
    )


class IgnoreRegion(_Model):
    image_id: str
    bbox: PixelBBox
    source: str = Field(pattern=r"^(dont_care|unmapped:.+)$")


class ConverterInfo(_Model):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class ManifestSource(_Model):
    format: Literal["kitti", "yolo", "coco"]
    split: str = Field(min_length=1)
    converter: ConverterInfo


class DatasetManifest(_Model):
    """Manifest dataset nội bộ. Dataset version = sha256_of(manifest)."""

    schema_version: Literal[1] = 1
    images: list[ManifestImage] = Field(min_length=1)
    annotations: list[ManifestAnnotation]
    ignore_regions: list[IgnoreRegion]
    categories: list[str] = Field(min_length=1)
    source: ManifestSource

    @model_validator(mode="after")
    def _check_consistency(self) -> DatasetManifest:
        # 1. image_id duy nhất, images sắp theo image_id (để hash không phụ thuộc thứ tự đọc file).
        # 2. annotations và ignore_regions sắp theo image_id (không giảm), image_id phải có trong images.
        # 3. category của annotation có trong categories; categories không trùng.
        # 4. bbox nằm trong khung ảnh (x2 <= width, y2 <= height).
        ...
```

`contracts/python/advertest_contracts/registry.py`: thêm `"dataset_manifest": DatasetManifest`.

`contracts/mocks/dataset_manifest/kitti_small.json`: một manifest nhỏ (2 ảnh, có annotation và ignore region `dont_care`).

`requirements.md` Phase 1, mục "Manifest dataset nội bộ": thêm câu "Schema: `DatasetManifest` trong `advertest_contracts.models`." Ignore region dạng `unmapped:<class>` và `difficulty:<class>` sinh ra **khi áp mapping** (Phase 1); manifest do converter tạo chỉ chứa `dont_care`.

## Ảnh hưởng

| Agent / thư mục | Cần thay đổi gì |
|---|---|
| Người duyệt, `contracts/` | Thêm 7 model, registry, 1 mock; chạy `make contracts` |
| ml-core, `tests/fixtures/manifest.json` (Phase 0 Group 6) | Viết manifest cho 5 ảnh fixture theo schema (task 31) |
| Người duyệt, `tests/acceptance/phase_00/` | Test `manifest.json` validate bằng `DatasetManifest` |
| ml-data, `ml_core/data/` (Phase 1 Group 2) | Converter `import-kitti` xuất `DatasetManifest` |
| backend (Phase 3) | Đọc/validate manifest khi lưu `dataset_versions` |

- `schema_version`: không schema nào đang có phải tăng; `DatasetManifest` bắt đầu ở `1`.
- Mock cần cập nhật: thêm `dataset_manifest/kitti_small.json`.
- Test nghiệm thu cần cập nhật: thêm test `manifest.json` vào `test_fixtures.py`; `test_contracts.py` tự bao gồm mock mới.

## Phương án thay thế (không đổi contract)

1. **Test nghiệm thu kiểm cấu trúc theo bảng của Phase 1.** Nhanh, không cần duyệt contract. Nhược điểm: không có một định nghĩa chung; converter Phase 1, backend Phase 3 và Phase 10 mỗi nơi tự hiểu định dạng, hash dataset version dễ lệch; frontend không có type.
2. **Để converter Phase 1 định nghĩa schema trong `ml_core/data/`.** Nhược điểm: backend phải import `ml_core` (sai ranh giới kiến trúc), hoặc định nghĩa lại lần nữa.

## Khuyến nghị

Chấp nhận đề xuất. Định dạng đã được chốt trong `requirements.md` Phase 1, được dùng bởi ít nhất ba agent, và dataset version phụ thuộc trực tiếp vào nó; đưa vào contract là cách duy nhất bảo đảm mọi nơi tính cùng một hash.
