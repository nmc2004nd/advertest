"""Schema contract dùng chung. JSON Schema và TypeScript type được sinh từ file này."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    StringConstraints,
    model_validator,
)

from advertest_contracts.enums import (
    AttackAccess,
    AttackKind,
    CaseSeverity,
    ErrorCode,
    LimitKind,
    RunMode,
    RunStatus,
    SearchStatus,
    SkipReason,
    StopReason,
    ThresholdKind,
)
from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
GitCommit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
# Digest image Docker, hoặc "none" khi chạy ngoài Docker (Phase 2).
DockerDigest = Annotated[str, StringConstraints(pattern=r"^(none|sha256:[0-9a-f]{64})$")]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]


def _require_utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("Thời gian phải ở múi giờ UTC")
    return value


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_require_utc)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- AttackSpec


class PrimaryParam(_Model):
    name: str = Field(min_length=1)
    type: Literal["continuous", "discrete"]
    min: float
    max: float
    values: list[float] | None = Field(default=None, description="Chỉ dùng khi type = discrete")
    unit: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_range(self) -> PrimaryParam:
        if self.min >= self.max:
            raise ValueError("primary_param.min phải nhỏ hơn max")
        if self.type == "continuous" and self.values is not None:
            raise ValueError("primary_param.values chỉ dùng khi type = discrete")
        if self.type == "discrete":
            if not self.values:
                raise ValueError("primary_param.values bắt buộc khi type = discrete")
            if any(not self.min <= v <= self.max for v in self.values):
                raise ValueError("primary_param.values phải nằm trong [min, max]")
        return self


class CostModel(_Model):
    passes_per_image: PositiveInt | None = Field(
        default=None, description="Số lần forward + backward cho mỗi ảnh"
    )
    cpu_only: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> CostModel:
        if (self.passes_per_image is None) == (not self.cpu_only):
            raise ValueError("cost_model cần đúng một trong passes_per_image hoặc cpu_only = true")
        return self


class AttackSpecBody(_Model):
    """Nội dung của attack spec (mọi trường trừ `id` và `spec_sha256`); là đầu vào của hash."""

    schema_version: Literal[1] = 1
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: PositiveInt
    kind: AttackKind
    access: AttackAccess
    art_class: str | None = Field(default=None, description="Null với corruption và occlusion")
    primary_param: PrimaryParam
    fixed_params: dict[str, JsonValue]
    cost_model: CostModel
    requires_gradients: bool

    @model_validator(mode="after")
    def _check_art_class(self) -> AttackSpecBody:
        if (self.kind == AttackKind.ATTACK) != (self.art_class is not None):
            raise ValueError("art_class bắt buộc với kind = attack và phải null với loại khác")
        return self


class AttackSpec(AttackSpecBody):
    """Một attack trong catalog. Đổi bất kỳ trường nào phải tăng `version`."""

    id: UUID
    spec_sha256: Sha256Hex = Field(description="Hash của mọi trường trừ id và chính nó")

    @model_validator(mode="after")
    def _check_hash(self) -> AttackSpec:
        expected = compute_spec_sha256(self)
        if self.spec_sha256 != expected:
            raise ValueError(f"spec_sha256 không khớp nội dung (tính lại: {expected})")
        return self


def compute_spec_sha256(spec: AttackSpecBody | Mapping[str, Any]) -> str:
    """sha256 của phần thân attack spec (đã điền giá trị mặc định), bỏ qua `id` và `spec_sha256`."""
    data = spec.model_dump(mode="json") if isinstance(spec, BaseModel) else dict(spec)
    data.pop("id", None)
    data.pop("spec_sha256", None)
    return sha256_of(AttackSpecBody.model_validate(data))


# ---------------------------------------------------------------- AttackConfig


class GridConfig(_Model):
    levels: list[float] = Field(min_length=1)


class SearchConfig(_Model):
    threshold_kind: ThresholdKind
    threshold: float
    lo: float
    hi: float
    tol: PositiveFloat
    coarse_n: PositiveInt
    subset_size: PositiveInt
    class_filter: list[str] | None = None

    @model_validator(mode="after")
    def _check_bracket(self) -> SearchConfig:
        if self.lo >= self.hi:
            raise ValueError("search.lo phải nhỏ hơn hi")
        return self


def _check_mode(mode: RunMode, grid: GridConfig | None, search: SearchConfig | None) -> None:
    if mode == RunMode.GRID and (grid is None or search is not None):
        raise ValueError("mode = grid cần grid và không có search")
    if mode == RunMode.SEARCH and (search is None or grid is not None):
        raise ValueError("mode = search cần search và không có grid")


class AttackConfig(_Model):
    """Một attack trong experiment."""

    schema_version: Literal[1] = 1
    attack_spec_id: UUID
    spec_sha256: Sha256Hex = Field(description="Chốt đúng version spec")
    mode: RunMode
    grid: GridConfig | None = None
    search: SearchConfig | None = None
    seed: NonNegativeInt

    @model_validator(mode="after")
    def _check(self) -> AttackConfig:
        _check_mode(self.mode, self.grid, self.search)
        return self


# ---------------------------------------------------------------- ExperimentConfig


class Limit(_Model):
    kind: LimitKind
    value: Decimal = Field(gt=0, description="Tiền (budget) hoặc giây (time)")


class ExperimentConfig(_Model):
    schema_version: Literal[1] = 1
    protocol_id: UUID
    model_version_id: UUID
    slice_id: UUID
    class_mapping_id: UUID
    compute_target_id: UUID
    attacks: list[AttackConfig] = Field(min_length=1)
    limit: Limit


# ---------------------------------------------------------------- RunResult

# Trạng thái bất thường và các code lý do tương ứng (tech-stack.md mục 4.3).
_REASON_CODES: dict[RunStatus, frozenset[str]] = {
    RunStatus.STOPPED_LIMIT: frozenset(StopReason),
    RunStatus.SKIPPED: frozenset(SkipReason),
    RunStatus.FAILED: frozenset({"error"}),
    RunStatus.CANCELLED: frozenset({"cancelled"}),
}
_ABNORMAL = frozenset(_REASON_CODES)


class StatusReason(_Model):
    code: StopReason | SkipReason | Literal["error", "cancelled"]
    message: str = Field(min_length=1)


class Progress(_Model):
    images_done: NonNegativeInt
    images_total: NonNegativeInt

    @model_validator(mode="after")
    def _check(self) -> Progress:
        if self.images_done > self.images_total:
            raise ValueError("images_done không được lớn hơn images_total")
        return self


class MapPair(_Model):
    map50: UnitFloat
    map50_95: UnitFloat


class ClassRunMetrics(_Model):
    clean_ap50: UnitFloat | None
    attacked_ap50: UnitFloat | None


class RunMetrics(_Model):
    clean: MapPair
    attacked: MapPair
    relative_drop: float | None = Field(description="null khi mAP@0.5 sạch bằng 0")
    absolute_drop: float
    attack_success_rate: UnitFloat | None = Field(
        description="null khi không có object nào được detect đúng trên ảnh sạch (|C| = 0)"
    )
    per_class: dict[str, ClassRunMetrics] | None = None


class Cost(_Model):
    amount: Decimal = Field(ge=0)
    currency: CurrencyCode


class RunResult(_Model):
    schema_version: Literal[1] = 1
    run_id: UUID
    experiment_id: UUID
    fingerprint: Sha256Hex
    attack_spec_id: UUID
    level: float
    status: RunStatus
    status_reason: StatusReason | None = None
    progress: Progress
    metrics: RunMetrics | None = None
    gpu_seconds: NonNegativeFloat
    cost: Cost | None = Field(default=None, description="null với máy local")
    failure_case_ids: list[UUID]
    manifest_uri: str | None = None

    @model_validator(mode="after")
    def _check_status(self) -> RunResult:
        reason = self.status_reason
        if self.status in _ABNORMAL and reason is None:
            raise ValueError(f"status = {self.status} bắt buộc có status_reason")
        if self.status not in _ABNORMAL and reason is not None:
            raise ValueError(f"status = {self.status} không có status_reason")
        if reason is not None and reason.code not in _REASON_CODES[self.status]:
            raise ValueError(f"status = {self.status} không nhận code = {reason.code}")
        if self.status == RunStatus.COMPLETED and (
            self.metrics is None or self.manifest_uri is None
        ):
            raise ValueError("status = completed bắt buộc có metrics và manifest_uri")
        return self


# ---------------------------------------------------------------- Manifest


class LibVersions(_Model):
    torch: str
    art: str
    ultralytics: str
    torchmetrics: str
    numpy: str


class FingerprintInputs(_Model):
    config_sha256: Sha256Hex
    weights_sha256: Sha256Hex
    dataset_version_sha256: Sha256Hex
    slice_id: UUID
    slice_sha256: Sha256Hex
    attack_spec_sha256: Sha256Hex
    params: dict[str, JsonValue]
    seed: NonNegativeInt
    git_commit: GitCommit
    git_dirty: bool = Field(description="Working tree có thay đổi chưa commit lúc chạy")
    lib_versions: LibVersions
    docker_image_digest: DockerDigest


class Environment(_Model):
    """Máy đã chạy run. Không thuộc fingerprint."""

    compute_target_id: UUID | None = Field(description="null khi chạy bằng CLI")
    gpu_model: str | None = Field(description="null khi chạy trên CPU")
    cuda_version: str | None
    driver_version: str | None


class Manifest(_Model):
    schema_version: Literal[1] = 1
    run_id: UUID
    fingerprint: Sha256Hex = Field(description="sha256 của fingerprint_inputs đã chuẩn hóa")
    fingerprint_inputs: FingerprintInputs
    environment: Environment
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _check_fingerprint(self) -> Manifest:
        expected = sha256_of(self.fingerprint_inputs)
        if self.fingerprint != expected:
            raise ValueError(f"fingerprint không khớp fingerprint_inputs (tính lại: {expected})")
        return self


# ---------------------------------------------------------------- SearchResult


class TrajectoryPoint(_Model):
    order: NonNegativeInt
    level: float
    scope: Literal["subset", "full"]
    drop: float | None
    run_id: UUID


class SearchResult(_Model):
    schema_version: Literal[1] = 1
    experiment_id: UUID
    attack_spec_id: UUID
    status: SearchStatus
    threshold_kind: ThresholdKind
    threshold: float
    breaking_point: float | None = None
    bracket: tuple[float, float] = Field(description="Khoảng hiện tại, kể cả khi dừng giữa chừng")
    confidence_interval: tuple[float, float] | None = Field(
        default=None, description="null nếu chưa tính bootstrap"
    )
    near_threshold: bool = Field(description="Khoảng tin cậy bao trùm ngưỡng")
    trajectory: list[TrajectoryPoint]

    @model_validator(mode="after")
    def _check(self) -> SearchResult:
        if (self.status == SearchStatus.FOUND) != (self.breaking_point is not None):
            raise ValueError("breaking_point có khi và chỉ khi status = found")
        if self.bracket[0] > self.bracket[1]:
            raise ValueError("bracket phải có dạng [thấp, cao]")
        ci = self.confidence_interval
        if ci is not None and ci[0] > ci[1]:
            raise ValueError("confidence_interval phải có dạng [thấp, cao]")
        return self


# ---------------------------------------------------------------- DatasetManifest (đề xuất 002)

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
    source: str = Field(
        pattern=r"^(dont_care|unmapped:.+|difficulty:.+)$",
        description="Converter chỉ sinh dont_care; unmapped và difficulty sinh ra khi áp mapping",
    )


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
        ids = [img.image_id for img in self.images]
        if len(set(ids)) != len(ids):
            raise ValueError("image_id phải duy nhất")
        # Thứ tự cố định để hash không phụ thuộc thứ tự đọc file của converter.
        if ids != sorted(ids):
            raise ValueError("images phải sắp theo image_id")
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("categories không được trùng")
        size = {img.image_id: (img.width, img.height) for img in self.images}
        categories = set(self.categories)
        for kind, items in (
            ("annotations", self.annotations),
            ("ignore_regions", self.ignore_regions),
        ):
            order = [item.image_id for item in items]
            if order != sorted(order):
                raise ValueError(f"{kind} phải sắp theo image_id")
            for item in items:
                if item.image_id not in size:
                    raise ValueError(f"{kind}: image_id {item.image_id} không có trong images")
                width, height = size[item.image_id]
                if item.bbox[2] > width or item.bbox[3] > height:
                    raise ValueError(f"{kind}: bbox vượt khung ảnh {item.image_id}")
        for ann in self.annotations:
            if ann.category not in categories:
                raise ValueError(f"category {ann.category} không có trong categories")
        return self


# ---------------------------------------------------------------- Phase 1: model, slice, eval


def _check_content_id(kind: str, id_: UUID, sha256_hex: str) -> None:
    expected = content_id(sha256_hex)
    if id_ != expected:
        raise ValueError(f"{kind}: id phải là content_id của hash (tính lại: {expected})")


class GradientCheck(_Model):
    passed: bool
    checked_at: UtcDatetime
    details: str | None = Field(default=None, description="Lý do khi passed = false")

    @model_validator(mode="after")
    def _check(self) -> GradientCheck:
        if not self.passed and not self.details:
            raise ValueError("gradient_check.details bắt buộc khi passed = false")
        return self


class ModelCard(_Model):
    """Model đã đăng ký. id = content_id(weights_sha256)."""

    schema_version: Literal[1] = 1
    id: UUID
    name: str = Field(min_length=1)
    framework: Literal["ultralytics", "torchvision"]
    architecture: str = Field(min_length=1)
    weights_sha256: Sha256Hex
    class_names: list[str] = Field(min_length=1, description="Theo thứ tự index của model")
    input_size: PositiveInt
    supports_gradients: bool = Field(description="Chỉ true khi bài kiểm tra gradient pass")
    gradient_check: GradientCheck
    lib_versions: LibVersions

    @model_validator(mode="after")
    def _check(self) -> ModelCard:
        _check_content_id("model", self.id, self.weights_sha256)
        if len(set(self.class_names)) != len(self.class_names):
            raise ValueError("class_names không được trùng")
        if self.supports_gradients != self.gradient_check.passed:
            raise ValueError("supports_gradients phải bằng gradient_check.passed")
        return self


class DifficultyFilter(_Model):
    """Ngưỡng độ khó (mức Moderate của KITTI: 25, 1, 0.30). Ngưỡng tính cả biên: GT được giữ khi
    đạt cả ba điều kiện, không đạt thì thành ignore region `difficulty:<class>`."""

    min_height_px: NonNegativeFloat = Field(
        description="Giữ khi chiều cao bbox (y2 - y1, pixel ảnh gốc) >= min_height_px"
    )
    max_occluded: NonNegativeInt = Field(description="Giữ khi occluded <= max_occluded")
    max_truncated: UnitFloat = Field(description="Giữ khi truncated <= max_truncated")


class ClassMappingBody(_Model):
    """Nội dung class mapping (mọi trường trừ `id` và `mapping_sha256`); là đầu vào của hash."""

    schema_version: Literal[1] = 1
    dataset_version_sha256: Sha256Hex
    model_id: UUID
    preset: str | None = Field(description="Ví dụ kitti-coco; null khi tự tạo")
    classes: dict[str, str | None] = Field(
        min_length=1,
        description="Class gốc → class model; null thành ignore region unmapped:<class>",
    )
    difficulty: DifficultyFilter | None = Field(description="null là không lọc theo độ khó")


class ClassMapping(ClassMappingBody):
    id: UUID
    mapping_sha256: Sha256Hex = Field(description="Hash của mọi trường trừ id và chính nó")

    @model_validator(mode="after")
    def _check(self) -> ClassMapping:
        expected = compute_mapping_sha256(self)
        if self.mapping_sha256 != expected:
            raise ValueError(f"mapping_sha256 không khớp nội dung (tính lại: {expected})")
        _check_content_id("class_mapping", self.id, self.mapping_sha256)
        return self


def compute_mapping_sha256(mapping: ClassMappingBody | Mapping[str, Any]) -> str:
    """sha256 của phần thân class mapping, bỏ qua `id` và `mapping_sha256`."""
    data = mapping.model_dump(mode="json") if isinstance(mapping, BaseModel) else dict(mapping)
    data.pop("id", None)
    data.pop("mapping_sha256", None)
    return sha256_of(ClassMappingBody.model_validate(data))


class SliceFilter(_Model):
    """Bộ lọc tự mô tả, không phụ thuộc model hay mapping."""

    classes: list[str] = Field(
        min_length=1, description="Class gốc được tính, sắp xếp, không trùng"
    )
    difficulty: DifficultyFilter | None
    min_objects: PositiveInt = 1

    @model_validator(mode="after")
    def _check(self) -> SliceFilter:
        if self.classes != sorted(set(self.classes)):
            raise ValueError("filter.classes phải sắp xếp và không trùng")
        return self


class SliceSpec(_Model):
    schema_version: Literal[1] = 1
    id: UUID
    slice_sha256: Sha256Hex = Field(
        description="sha256 của dataset_version_sha256, filter, seed, size, image_ids"
    )
    dataset_version_sha256: Sha256Hex
    filter: SliceFilter
    seed: NonNegativeInt
    size: PositiveInt
    image_ids: list[str] = Field(
        min_length=1, description="Sắp xếp, không trùng, đúng size phần tử"
    )
    image_ids_sha256: Sha256Hex = Field(description="sha256_of(image_ids)")

    @model_validator(mode="after")
    def _check(self) -> SliceSpec:
        if self.image_ids != sorted(set(self.image_ids)):
            raise ValueError("image_ids phải sắp xếp và không trùng")
        if len(self.image_ids) != self.size:
            raise ValueError("số phần tử của image_ids phải bằng size")
        if self.image_ids_sha256 != sha256_of(self.image_ids):
            raise ValueError("image_ids_sha256 không khớp image_ids")
        expected = compute_slice_sha256(self)
        if self.slice_sha256 != expected:
            raise ValueError(f"slice_sha256 không khớp nội dung (tính lại: {expected})")
        _check_content_id("slice", self.id, self.slice_sha256)
        return self


def compute_slice_sha256(slice_: SliceSpec | Mapping[str, Any]) -> str:
    """sha256 của dataset_version_sha256, filter, seed, size, image_ids."""
    data = slice_.model_dump(mode="json") if isinstance(slice_, BaseModel) else dict(slice_)
    body = {
        "dataset_version_sha256": data["dataset_version_sha256"],
        "filter": SliceFilter.model_validate(data["filter"]).model_dump(mode="json"),
        "seed": data["seed"],
        "size": data["size"],
        "image_ids": data["image_ids"],
    }
    return sha256_of(body)


class InferenceParams(_Model):
    conf: UnitFloat
    iou: UnitFloat
    max_det: PositiveInt
    operating_conf: UnitFloat = Field(description="Ngưỡng dùng cho tỷ lệ tấn công thành công")
    input_size: PositiveInt


class EvalModelRef(_Model):
    id: UUID
    weights_sha256: Sha256Hex


class EvalSliceRef(_Model):
    id: UUID
    slice_sha256: Sha256Hex
    image_ids_sha256: Sha256Hex
    dataset_version_sha256: Sha256Hex


class EvalMappingRef(_Model):
    id: UUID
    mapping_sha256: Sha256Hex


class ClassEvalMetrics(_Model):
    ap50: UnitFloat | None = Field(description="null khi và chỉ khi num_gt = 0")
    ap50_95: UnitFloat | None = Field(description="null khi và chỉ khi num_gt = 0")
    num_gt: NonNegativeInt

    @model_validator(mode="after")
    def _check(self) -> ClassEvalMetrics:
        no_gt = self.num_gt == 0
        if (self.ap50 is None) != no_gt or (self.ap50_95 is None) != no_gt:
            raise ValueError("ap50 và ap50_95 là null khi và chỉ khi num_gt = 0")
        return self


class EvalMetrics(_Model):
    map50: UnitFloat
    map50_95: UnitFloat
    per_class: dict[str, ClassEvalMetrics] = Field(min_length=1, description="Theo class đích")


class CacheInfo(_Model):
    key: Sha256Hex
    hit: bool


class Timing(_Model):
    total_s: NonNegativeFloat
    sec_per_image: NonNegativeFloat


class CleanEvalResult(_Model):
    """Kết quả `advertest eval` trên ảnh sạch."""

    schema_version: Literal[1] = 1
    model: EvalModelRef
    slice: EvalSliceRef
    class_mapping: EvalMappingRef
    inference_params: InferenceParams
    metrics: EvalMetrics
    num_images: PositiveInt
    cache: CacheInfo
    timing: Timing
    device: str = Field(min_length=1, description="Ví dụ cuda:0 (NVIDIA ...) hoặc cpu")
    lib_versions: LibVersions
    git_commit: GitCommit

    @model_validator(mode="after")
    def _check(self) -> CleanEvalResult:
        _check_content_id("model", self.model.id, self.model.weights_sha256)
        _check_content_id("slice", self.slice.id, self.slice.slice_sha256)
        _check_content_id("class_mapping", self.class_mapping.id, self.class_mapping.mapping_sha256)
        return self


# ---------------------------------------------------------------- Phase 2: failure case


class CaseBox(_Model):
    """Box trong failure case: xyxy pixel trong không gian letterbox."""

    bbox: PixelBBox
    class_name: str = Field(min_length=1, description="Class đích của mapping")
    score: UnitFloat | None = Field(description="null với ground truth, bắt buộc với prediction")


class CaseIgnoreRegion(_Model):
    bbox: PixelBBox = Field(description="xyxy pixel trong không gian letterbox")
    source: str = Field(pattern=r"^(dont_care|unmapped:.+|difficulty:.+)$")


class CaseDetections(_Model):
    ground_truth: list[CaseBox]
    clean: list[CaseBox]
    attacked: list[CaseBox]
    ignore_regions: list[CaseIgnoreRegion]

    @model_validator(mode="after")
    def _check_scores(self) -> CaseDetections:
        if any(box.score is not None for box in self.ground_truth):
            raise ValueError("ground_truth không có score")
        if any(box.score is None for box in (*self.clean, *self.attacked)):
            raise ValueError("prediction (clean, attacked) bắt buộc có score")
        return self


class CaseArtifacts(_Model):
    """Khóa lưu trữ (LocalStore ở Phase 2, MinIO từ Phase 3) của ảnh PNG letterbox."""

    clean_png: str = Field(min_length=1)
    adversarial_png: str = Field(min_length=1)
    perturbation_png: str = Field(min_length=1, description="Ảnh nhiễu khuếch đại")


def compute_failure_case_id(fingerprint: str, image_id: str) -> UUID:
    """id của failure case: content_id của sha256 {"fingerprint", "image_id"}."""
    return content_id(sha256_of({"fingerprint": fingerprint, "image_id": image_id}))


class FailureCaseRecord(_Model):
    """Một ảnh bị attack làm hỏng nặng trong một run (Phase 2)."""

    schema_version: Literal[1] = 1
    id: UUID = Field(description="compute_failure_case_id(fingerprint, image_id)")
    run_id: UUID
    fingerprint: Sha256Hex = Field(description="Fingerprint của run")
    image_id: str = Field(min_length=1)
    lost_objects: NonNegativeInt = Field(description="Số object bị mất sau tấn công")
    new_false_positives: NonNegativeInt = Field(description="Số detection sai mới xuất hiện")
    severity_score: float = Field(
        gt=0, description="lost_objects + 0.5 * new_false_positives; chỉ lưu case > 0"
    )
    detections: CaseDetections
    artifacts: CaseArtifacts

    @model_validator(mode="after")
    def _check(self) -> FailureCaseRecord:
        expected_id = compute_failure_case_id(self.fingerprint, self.image_id)
        if self.id != expected_id:
            raise ValueError(f"id phải là compute_failure_case_id (tính lại: {expected_id})")
        expected = self.lost_objects + 0.5 * self.new_false_positives
        if self.severity_score != expected:
            raise ValueError(f"severity_score phải bằng {expected}")
        return self


# ---------------------------------------------------------------- API chung


class ErrorBody(_Model):
    code: ErrorCode
    message: str = Field(min_length=1)


class ErrorResponse(_Model):
    """Body lỗi thống nhất của mọi endpoint: {"error": {"code", "message"}}."""

    schema_version: Literal[1] = 1
    error: ErrorBody


class DependencyStatus(_Model):
    ok: bool
    detail: str | None = Field(default=None, description="Lý do khi ok = false")


class HealthResponse(_Model):
    schema_version: Literal[1] = 1
    status: Literal["ok", "degraded"] = Field(description="degraded khi có dependency không ok")
    version: str = Field(min_length=1)
    git_commit: str = Field(pattern=r"^([0-9a-f]{40}|unknown)$")
    postgres: DependencyStatus
    minio: DependencyStatus

    @model_validator(mode="after")
    def _status_matches_dependencies(self) -> HealthResponse:
        all_ok = self.postgres.ok and self.minio.ok
        if (self.status == "ok") != all_ok:
            raise ValueError("status = ok khi và chỉ khi mọi dependency ok")
        return self


# ---------------------------------------------------------------- ProtocolBody


class RequiredAttack(_Model):
    attack_spec_id: UUID
    spec_sha256: Sha256Hex
    mode: RunMode
    grid: GridConfig | None = Field(default=None, description="Các level tối thiểu phải chạy")
    search: SearchConfig | None = Field(default=None, description="Cấu hình tìm kiếm tối thiểu")

    @model_validator(mode="after")
    def _check(self) -> RequiredAttack:
        _check_mode(self.mode, self.grid, self.search)
        return self


class PassCriterion(_Model):
    threshold_kind: ThresholdKind
    threshold: float
    class_filter: list[str] | None = None


class ProtocolBody(_Model):
    schema_version: Literal[1] = 1
    required_attacks: list[RequiredAttack] = Field(min_length=1)
    min_slice_size: PositiveInt
    pass_criteria: list[PassCriterion] = Field(min_length=1)
    review_severity_threshold: CaseSeverity = Field(
        description="Case từ mức này trở lên bắt buộc có verdict"
    )
