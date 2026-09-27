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
    attack_success_rate: UnitFloat
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
