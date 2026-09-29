"""Schema contract dùng chung. JSON Schema và TypeScript type được sinh từ file này."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar
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
    Role,
    RunMode,
    RunStatus,
    SearchStatus,
    SkipReason,
    StopReason,
    ThresholdKind,
    UserStatus,
)
from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.permissions import Permission, permissions_for

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
GitCommit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
# Digest image Docker, hoặc "none" khi chạy ngoài Docker (Phase 2).
DockerDigest = Annotated[str, StringConstraints(pattern=r"^(none|sha256:[0-9a-f]{64})$")]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]
PresignedUrl = Annotated[str, StringConstraints(pattern=r"^https?://\S+$")]
# Khóa đối tượng trong bucket: các đoạn ngăn bởi "/", không rỗng, không bắt đầu bằng "."
# (nên không có "." hay ".."), không có "/" ở đầu hay cuối.
_KEY_SEGMENT = r"[A-Za-z0-9_-][A-Za-z0-9._-]*"
ObjectKey = Annotated[str, StringConstraints(pattern=rf"^{_KEY_SEGMENT}(/{_KEY_SEGMENT})*$")]


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
    partial: bool = Field(
        default=False, description="true khi metric chỉ tính trên phần ảnh đã xử lý (stopped_limit)"
    )


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
    cached_from_run_id: UUID | None = Field(
        default=None, description="Run gốc khi status = skipped với code = cached (Phase 3)"
    )

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
        cached = self.status == RunStatus.SKIPPED and reason is not None and reason.code == "cached"
        if self.cached_from_run_id is not None and not cached:
            raise ValueError("cached_from_run_id chỉ dùng khi status = skipped với code = cached")
        if self.metrics is not None:
            stopped = self.status == RunStatus.STOPPED_LIMIT
            if self.metrics.partial != stopped:
                raise ValueError("metrics.partial = true khi và chỉ khi status = stopped_limit")
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


_THUMB = "Thumbnail WebP rộng 320 px (Phase 3); null khi chạy bằng CLI, bắt buộc qua worker"


class CaseArtifacts(_Model):
    """Khóa lưu trữ (LocalStore ở Phase 2, MinIO từ Phase 3) của ảnh PNG letterbox."""

    clean_png: str = Field(min_length=1)
    adversarial_png: str = Field(min_length=1)
    perturbation_png: str = Field(min_length=1, description="Ảnh nhiễu khuếch đại")
    clean_thumb: str | None = Field(default=None, description=_THUMB)
    adversarial_thumb: str | None = Field(default=None, description=_THUMB)


def compute_failure_case_id(fingerprint: str, run_id: UUID, image_id: str) -> UUID:
    """id của failure case: content_id của sha256 {"fingerprint", "run_id", "image_id"}.

    Có `run_id` vì cùng fingerprint có thể có nhiều run tạo case (Phase 3).
    """
    return content_id(
        sha256_of({"fingerprint": fingerprint, "run_id": str(run_id), "image_id": image_id})
    )


class FailureCaseRecord(_Model):
    """Một ảnh bị attack làm hỏng nặng trong một run (Phase 2)."""

    schema_version: Literal[1] = 1
    id: UUID = Field(description="compute_failure_case_id(fingerprint, run_id, image_id)")
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
        expected_id = compute_failure_case_id(self.fingerprint, self.run_id, self.image_id)
        if self.id != expected_id:
            raise ValueError(f"id phải là compute_failure_case_id (tính lại: {expected_id})")
        expected = self.lost_objects + 0.5 * self.new_false_positives
        if self.severity_score != expected:
            raise ValueError(f"severity_score phải bằng {expected}")
        return self


# ---------------------------------------------------------------- Phase 3: API nội bộ của worker


class CostProfile(_Model):
    """Chi phí đo bằng calibration, riêng cho từng (compute target, model, attack)."""

    schema_version: Literal[1] = 1
    compute_target_id: UUID
    model_version_id: UUID
    attack_spec_id: UUID
    sec_per_image: PositiveFloat
    peak_vram_mb: NonNegativeInt = Field(description="0 khi chạy trên CPU")
    batch_size: PositiveInt
    measured_at: UtcDatetime
    environment: Environment

    @model_validator(mode="after")
    def _check(self) -> CostProfile:
        if self.environment.compute_target_id != self.compute_target_id:
            raise ValueError("environment.compute_target_id phải bằng compute_target_id")
        return self


class WorkerLease(_Model):
    """Trả về từ `POST /lease` (không có job thì `204`)."""

    schema_version: Literal[1] = 1
    experiment_id: UUID
    lease_id: UUID = Field(description="Đổi mỗi lần lease; gửi kèm mọi request sau đó")
    lease_expires_at: UtcDatetime


class BundleDownloads(_Model):
    """Presigned GET URL cho tài nguyên của job."""

    weights: PresignedUrl
    dataset_manifest: PresignedUrl
    images: dict[str, PresignedUrl] = Field(
        min_length=1, description="image_id → URL, đúng các ảnh của slice"
    )
    expires_at: UtcDatetime


class BundleCheckpoint(_Model):
    batch_index: NonNegativeInt = Field(description="Batch cuối cùng đã xử lý xong")
    key: ObjectKey
    url: PresignedUrl


class BundleRun(_Model):
    run_id: UUID
    attack_spec_id: UUID
    level: float
    seed: NonNegativeInt
    status: RunStatus
    images_done: NonNegativeInt
    images_total: PositiveInt
    checkpoint: BundleCheckpoint | None = Field(description="Checkpoint mới nhất khi đang chạy dở")

    @model_validator(mode="after")
    def _check(self) -> BundleRun:
        if self.images_done > self.images_total:
            raise ValueError("images_done không được lớn hơn images_total")
        if self.checkpoint is not None and self.status != RunStatus.RUNNING:
            raise ValueError("checkpoint chỉ có khi status = running")
        return self


class BundleLimit(_Model):
    kind: LimitKind
    value: Decimal = Field(gt=0, description="Tiền (budget) hoặc giây (time)")
    used: Decimal = Field(ge=0, description="Đã dùng: giây xử lý cộng dồn hoặc tiền")


class WorkerJobBundle(_Model):
    """Mọi thứ worker cần để chạy một experiment (`GET /experiments/{id}/bundle`)."""

    schema_version: Literal[1] = 1
    experiment_id: UUID
    config: ExperimentConfig
    model_card: ModelCard
    slice: SliceSpec
    class_mapping: ClassMapping
    attack_specs: list[AttackSpec] = Field(min_length=1)
    inference_params: InferenceParams = Field(description="Thuộc fingerprint (config_sha256)")
    failure_cases_per_run: NonNegativeInt
    cost_profiles: list[CostProfile] = Field(
        description="Profile đã có của (target, model, attack); thiếu thì worker calibrate trước"
    )
    downloads: BundleDownloads
    limit: BundleLimit
    runs: list[BundleRun] = Field(min_length=1, description="Theo thứ tự chạy")

    @model_validator(mode="after")
    def _check(self) -> WorkerJobBundle:
        cfg = self.config
        if cfg.model_version_id != self.model_card.id:
            raise ValueError("config.model_version_id phải bằng model_card.id")
        if cfg.slice_id != self.slice.id:
            raise ValueError("config.slice_id phải bằng slice.id")
        if cfg.class_mapping_id != self.class_mapping.id:
            raise ValueError("config.class_mapping_id phải bằng class_mapping.id")
        if self.class_mapping.model_id != self.model_card.id:
            raise ValueError("class_mapping.model_id phải bằng model_card.id")
        if self.class_mapping.dataset_version_sha256 != self.slice.dataset_version_sha256:
            raise ValueError("class_mapping và slice phải cùng dataset version")
        spec_ids = {a.attack_spec_id for a in cfg.attacks}
        if {s.id for s in self.attack_specs} != spec_ids:
            raise ValueError("attack_specs phải đúng các attack trong config")
        if any(r.attack_spec_id not in spec_ids for r in self.runs):
            raise ValueError("run có attack_spec_id không nằm trong config")
        if len({r.run_id for r in self.runs}) != len(self.runs):
            raise ValueError("run_id không được trùng")
        if set(self.downloads.images) != set(self.slice.image_ids):
            raise ValueError("downloads.images phải đúng các ảnh của slice")
        if (self.limit.kind, self.limit.value) != (cfg.limit.kind, cfg.limit.value):
            raise ValueError("limit phải khớp config.limit")
        for profile in self.cost_profiles:
            if (
                profile.compute_target_id != cfg.compute_target_id
                or profile.model_version_id != self.model_card.id
                or profile.attack_spec_id not in spec_ids
            ):
                raise ValueError("cost_profiles chỉ gồm profile của target, model, attack này")
        return self


class HeartbeatRequest(_Model):
    lease_id: UUID
    experiment_id: UUID


class RunStartRequest(_Model):
    lease_id: UUID
    fingerprint: Sha256Hex
    fingerprint_inputs: FingerprintInputs
    environment: Environment

    @model_validator(mode="after")
    def _check(self) -> RunStartRequest:
        expected = sha256_of(self.fingerprint_inputs)
        if self.fingerprint != expected:
            raise ValueError(f"fingerprint không khớp fingerprint_inputs (tính lại: {expected})")
        return self


class RunStartResponse(_Model):
    action: Literal["run", "skip_cached"]
    cached_from_run_id: UUID | None = Field(default=None, description="Chỉ có khi skip_cached")
    cached_result: RunResult | None = Field(
        default=None, description="Kết quả của run gốc (completed); chỉ có khi skip_cached"
    )

    @model_validator(mode="after")
    def _check(self) -> RunStartResponse:
        skip = self.action == "skip_cached"
        has_id, has_result = self.cached_from_run_id is not None, self.cached_result is not None
        if has_id != skip or has_result != skip:
            raise ValueError("cached_from_run_id và cached_result có khi và chỉ khi skip_cached")
        result = self.cached_result
        if result is not None and (
            result.run_id != self.cached_from_run_id or result.status != RunStatus.COMPLETED
        ):
            raise ValueError("cached_result phải là kết quả completed của cached_from_run_id")
        return self


class ProgressReport(_Model):
    lease_id: UUID
    images_done: NonNegativeInt = Field(description="Tổng số ảnh đã xử lý của run")
    batch_index: NonNegativeInt
    checkpoint_key: ObjectKey
    processing_seconds_delta: NonNegativeFloat = Field(
        description="Thời gian xử lý từ lần báo trước; API cộng dồn"
    )


class WorkerDirective(_Model):
    action: Literal["continue", "cancel", "stop_limit"]
    remaining_seconds: NonNegativeFloat | None = Field(
        description="Thời gian xử lý còn lại; null khi giới hạn là tiền"
    )


class ArtifactUrlRequest(_Model):
    lease_id: UUID
    key: ObjectKey = Field(description="Khóa đầy đủ, phải nằm trong runs/<run_id>/")
    method: Literal["PUT", "GET", "DELETE"]


class ArtifactUrlResponse(_Model):
    key: ObjectKey
    method: Literal["PUT", "GET", "DELETE"]
    url: PresignedUrl
    expires_at: UtcDatetime


class RunCompletion(_Model):
    """Body của `POST /runs/{id}/complete`."""

    schema_version: Literal[1] = 1
    lease_id: UUID
    run_result: RunResult
    failure_cases: list[FailureCaseRecord]

    @model_validator(mode="after")
    def _check(self) -> RunCompletion:
        result = self.run_result
        if result.cached_from_run_id is not None:
            raise ValueError("run cached do API ghi ở start, không gửi qua complete")
        if [case.id for case in self.failure_cases] != result.failure_case_ids:
            raise ValueError("failure_case_ids phải đúng id của failure_cases, cùng thứ tự")
        for case in self.failure_cases:
            if case.run_id != result.run_id or case.fingerprint != result.fingerprint:
                raise ValueError("failure case phải cùng run_id và fingerprint với run_result")
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


# ---------------------------------------------------------------- Xác thực và quản trị (Phase 4)

# Email luôn ở dạng chữ thường (so sánh không phân biệt hoa thường). Chỉ kiểm tra hình dạng tối
# thiểu; việc admin duyệt tài khoản đóng vai trò xác minh.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    ),
]
# Mật khẩu mới: tối thiểu 10 ký tự; giới hạn trên để băm argon2 không bị lạm dụng.
NewPassword = Annotated[str, StringConstraints(min_length=10, max_length=256)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=256)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


def _unique_roles(roles: list[Role]) -> list[Role]:
    if len(set(roles)) != len(roles):
        raise ValueError("roles không được trùng")
    return roles


# Ít nhất một role, không trùng.
RoleList = Annotated[list[Role], Field(min_length=1), AfterValidator(_unique_roles)]


class AccessRequest(_Model):
    full_name: Name
    email: Email
    organization: Name | None = None
    requested_role: Role
    reason: Reason
    password: NewPassword

    @model_validator(mode="after")
    def _password_differs_from_email(self) -> AccessRequest:
        if self.password.strip().lower() == self.email:
            raise ValueError("Mật khẩu không được trùng email")
        return self


class LoginRequest(_Model):
    email: Email
    password: Password


class Me(_Model):
    id: UUID
    full_name: str
    email: Email
    roles: list[Role]
    permissions: list[Permission] = Field(description="Hợp các permission của mọi role")
    status: UserStatus

    @model_validator(mode="after")
    def _permissions_match_roles(self) -> Me:
        if set(self.permissions) != permissions_for(self.roles):
            raise ValueError("permissions phải bằng hợp ROLE_PERMISSIONS của roles")
        return self


class UserAdminView(_Model):
    id: UUID
    full_name: str
    email: Email
    organization: str | None
    status: UserStatus
    roles: list[Role]
    requested_role: Role | None
    request_reason: str | None
    reject_reason: str | None = Field(description="Chỉ có khi status = rejected")
    created_at: UtcDatetime
    approved_at: UtcDatetime | None
    approved_by: UUID | None


class ApproveRequest(_Model):
    roles: RoleList


class RejectRequest(_Model):
    reason: Reason


class RolesUpdate(_Model):
    roles: RoleList = Field(description="Ít nhất 1 role; muốn chặn truy cập thì vô hiệu hóa")


class PasswordChange(_Model):
    current_password: Password
    new_password: NewPassword


class PasswordResetLink(_Model):
    url: str = Field(pattern=r"^https?://\S+/reset-password/\S+$")
    expires_at: UtcDatetime


class PasswordResetConsume(_Model):
    token: Password
    new_password: NewPassword


class AuditActor(_Model):
    id: UUID
    full_name: str
    email: Email


class AuditLogEntry(_Model):
    id: UUID
    actor: AuditActor | None = Field(description="null với hành động của hệ thống")
    # Không ép mẫu khi đọc: audit log chỉ thêm, một dòng cũ lệch quy ước không được làm hỏng cả
    # trang. Quy ước `entity.verb` áp cho code ghi (review Phase 4 Group 3).
    action: str = Field(
        min_length=1,
        examples=["user.approved"],
        description="Theo quy ước `entity.verb` (ví dụ user.approved)",
    )
    entity_type: str = Field(min_length=1)
    entity_id: UUID | None
    before: dict[str, JsonValue] | None
    after: dict[str, JsonValue] | None
    created_at: UtcDatetime


ItemT = TypeVar("ItemT", bound=BaseModel)


class Page(_Model, Generic[ItemT]):
    """Một trang kết quả; `next_cursor = null` khi đã hết."""

    items: list[ItemT]
    next_cursor: str | None


class UserAdminPage(Page[UserAdminView]):
    pass


class AuditLogPage(Page[AuditLogEntry]):
    pass
