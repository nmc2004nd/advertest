"""Schema contract dùng chung. JSON Schema và TypeScript type được sinh từ file này."""

from __future__ import annotations

import math
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
    AttackSpecStatus,
    CaseSeverity,
    CaseVerdictKind,
    ChecklistCode,
    CommentTargetType,
    ComplianceCode,
    ComputeKind,
    ConclusionCode,
    CriterionKind,
    CriterionStatus,
    DisplayMode,
    ErrorCode,
    EvalScope,
    ExperimentMode,
    ExperimentStatus,
    LimitKind,
    ModelStatus,
    ModelVerdict,
    PerturbationImageKind,
    ProtocolStatus,
    QuickTryObjectStatus,
    ReportNoteCode,
    ReportStatus,
    ReviewDecision,
    Role,
    RunMode,
    RunPhase,
    RunStatus,
    SearchStage,
    SearchStatus,
    SkipReason,
    SpecCheckName,
    StopReason,
    SubmitCheckCode,
    ThresholdKind,
    ToolJobKind,
    ToolJobStatus,
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


def _omittable_not_required(schema: dict[str, Any], cls: type[BaseModel]) -> None:
    """Trường có `exclude_if` có thể vắng trong JSON trả về (Phase 6: trường mới bị bỏ khi mang
    giá trị mặc định để hash cũ không đổi), nên không được khai là bắt buộc ở chế độ serialization
    (TypeScript type sinh ra khai là tùy chọn)."""
    omitted = {name for name, field in cls.model_fields.items() if field.exclude_if is not None}
    # openapi-typescript coi trường có `default` là luôn có mặt; giá trị mặc định ghi ở description.
    for name in omitted:
        schema.get("properties", {}).get(name, {}).pop("default", None)
    required = [name for name in schema.get("required", []) if name not in omitted]
    if required:
        schema["required"] = required
    else:
        schema.pop("required", None)


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_extra=_omittable_not_required
    )


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


class TrainingParams(_Model):
    """Tham số huấn luyện của spec cần train trước khi đánh giá (patch, Phase 6)."""

    max_iter: PositiveInt = Field(
        description="Số vòng lặp; mỗi vòng đi qua toàn bộ slice huấn luyện"
    )
    learning_rate: PositiveFloat = Field(description="Trong thang ảnh [0, 1]")
    sample_size: PositiveInt = Field(description="Số biến đổi ngẫu nhiên mỗi ảnh mỗi vòng (EOT)")
    checkpoint_every: PositiveInt = Field(description="Lưu checkpoint sau mỗi số vòng lặp này")
    max_training_images: PositiveInt = Field(description="Kích thước tối đa của slice huấn luyện")
    batch_size: PositiveInt = Field(
        description="Batch size khi train và khi tính giá trị mục tiêu; cố định trong spec (không"
        " lấy từ cost profile) vì patch phụ thuộc cách chia batch (đề xuất contract 001, Phase 6)"
    )


# Tên adapter: các đoạn chữ thường ngăn bởi ".", ví dụ corruption.imagecorruptions (Phase R2).
AdapterName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")]


class AttackSpecBody(_Model):
    """Nội dung của attack spec (mọi trường trừ `id` và `spec_sha256`); là đầu vào của hash.

    Trường thêm ở Phase 6 (`requires_training`, `training`) và Phase R2 (`adapter`) bị bỏ khỏi
    JSON khi mang giá trị mặc định, nên hash của spec cũ không đổi.
    """

    schema_version: Literal[1] = 1
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: PositiveInt
    kind: AttackKind
    access: AttackAccess = Field(
        description="Corruption và occlusion dùng not_applicable; attack không dùng giá trị này"
    )
    art_class: str | None = Field(default=None, description="Null với corruption và occlusion")
    primary_param: PrimaryParam
    fixed_params: dict[str, JsonValue]
    cost_model: CostModel
    requires_gradients: bool
    requires_training: bool = Field(
        default=False,
        exclude_if=lambda v: v is False,
        description="Phase 6: phải train (patch) trên slice huấn luyện trước khi đánh giá",
    )
    training: TrainingParams | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Có khi và chỉ khi requires_training = true",
    )
    adapter: AdapterName | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Phase R2: adapter trong registry của worker (`GET /attack-adapters`); null là"
        " suy từ kind và art_class (`attacks.builders.effective_adapter`). `fixed_params` là tham"
        " số của adapter",
    )

    @model_validator(mode="after")
    def _check_art_class(self) -> AttackSpecBody:
        is_attack = self.kind == AttackKind.ATTACK
        if is_attack != (self.art_class is not None):
            raise ValueError("art_class bắt buộc với kind = attack và phải null với loại khác")
        if is_attack and self.access == AttackAccess.NOT_APPLICABLE:
            raise ValueError("attack (kind = attack) không được có access = not_applicable")
        if self.requires_training != (self.training is not None):
            raise ValueError("training có khi và chỉ khi requires_training = true")
        if self.requires_training and not (is_attack and self.requires_gradients):
            raise ValueError("requires_training chỉ dùng cho attack cần gradient")
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
    if isinstance(spec, BaseModel):
        # Chỉ các trường của phần thân: lớp con (AttackSpecAdminView) có thêm trường hiển thị.
        data = spec.model_dump(mode="json", include=set(AttackSpecBody.model_fields))
    else:
        data = dict(spec)
        data.pop("id", None)
        data.pop("spec_sha256", None)
    return sha256_of(AttackSpecBody.model_validate(data))


# ---------------------------------------------------------------- AttackConfig


class GridConfig(_Model):
    levels: list[float] = Field(min_length=1)
    early_stop: bool = Field(
        default=True,
        exclude_if=lambda v: v is True,
        description="Phase 6: bỏ level lớn hơn khi model đã sụp (mAP@0.5 <= 5% mAP sạch)",
    )


class SearchConfig(_Model):
    """Cấu hình tự tìm ngưỡng (Phase 7, requirements.md mục Behaviour).

    Kiểm tra phụ thuộc spec, slice và mapping (`lo`, `hi` trong dải của spec; `subset_size` không
    quá số ảnh slice; `absolute_drop` không quá mAP sạch; `class_filter` là class đích) ở backend.
    """

    threshold_kind: ThresholdKind
    threshold: float = Field(
        gt=0,
        le=1,
        description="relative_drop, attack_success_rate: (0, 1]; absolute_drop: (0, mAP sạch]",
    )
    lo: float
    hi: float
    tol: PositiveFloat = Field(
        description="Độ rộng khoảng khi dừng chia đôi; wizard mặc định (hi - lo) / 256. Tham số"
        " rời rạc chia đôi theo chỉ số nên không dùng tol"
    )
    coarse_n: int = Field(default=4, ge=3, le=8, description="Số level quét thô")
    subset_size: int = Field(
        default=100, ge=2, description="Số ảnh của tập con; wizard cảnh báo khi dưới 20"
    )
    class_filter: str | None = Field(
        default=None, min_length=1, description="Một class đích của mapping; null là mọi class"
    )
    bootstrap_samples: int = Field(
        default=200, ge=0, le=1000, description="Số mẫu bootstrap; 0 là không tính khoảng tin cậy"
    )

    @model_validator(mode="after")
    def _check_bracket(self) -> SearchConfig:
        if self.lo >= self.hi:
            raise ValueError("search.lo phải nhỏ hơn hi")
        if self.tol >= self.hi - self.lo:
            raise ValueError("search.tol phải nhỏ hơn hi - lo")
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
    training_slice_id: UUID | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Phase 6: bắt buộc khi spec có requires_training; không giao với slice"
        " đánh giá",
    )

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
    trigger_run_id: UUID | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Phase 6: run đã kích hoạt dừng sớm; có khi và chỉ khi code = early_stop",
    )

    @model_validator(mode="after")
    def _check_trigger(self) -> StatusReason:
        if (self.trigger_run_id is not None) != (self.code == SkipReason.EARLY_STOP):
            raise ValueError("trigger_run_id có khi và chỉ khi code = early_stop")
        return self


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
    attack_success_rate: UnitFloat | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Phase 7: ASR chỉ tính object của class này (ngưỡng có class_filter); null"
        " khi không có object nào của class được detect đúng trên ảnh sạch, hoặc run trước Phase 7",
    )


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


class _RunCommon(_Model):
    """Trường chung của `RunResult` (worker gửi) và `RunView` (người dùng xem); khác nhau ở
    `fingerprint` (đề xuất contract 001, Phase 5)."""

    schema_version: Literal[1] = 1
    run_id: UUID
    experiment_id: UUID
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
    scope: EvalScope = Field(
        default=EvalScope.FULL,
        exclude_if=lambda v: v == EvalScope.FULL,
        description="Phase 7: tập ảnh được đánh giá; subset chỉ có ở run của tìm ngưỡng",
    )
    search_order: NonNegativeInt | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Phase 7: thứ tự điểm trong lần tìm ngưỡng của attack (TrajectoryPoint.order);"
        " null với run quét lưới",
    )
    predictions_key: ObjectKey | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Phase 7: khóa file prediction theo ảnh trong runs/<run_id>/ (bootstrap);"
        " run trúng cache có bản sao file của run gốc (đề xuất contract 001); null khi chưa có"
        " metric, run trước Phase 7, hoặc run gốc không có file",
    )

    @model_validator(mode="after")
    def _check_status(self) -> _RunCommon:
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
        if self.scope == EvalScope.SUBSET and self.search_order is None:
            raise ValueError(
                "run scope = subset phải có search_order (chỉ tìm ngưỡng dùng tập con)"
            )
        if self.predictions_key is not None and not self.predictions_key.startswith(
            f"runs/{self.run_id}/"
        ):
            raise ValueError("predictions_key phải nằm trong runs/<run_id>/")
        return self


class RunResult(_RunCommon):
    fingerprint: Sha256Hex


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
    patch_key: Sha256Hex | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Phase 6: khóa patch (compute_patch_key) với run patch; bỏ khỏi JSON khi null"
        " nên fingerprint của run khác không đổi",
    )
    eval_image_ids_sha256: Sha256Hex | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Phase 7: sha256 (canonical_json) của danh sách image_id đã sắp xếp mà run"
        " đánh giá, chỉ khi đánh giá trên tập con; null với run toàn slice (bỏ khỏi JSON) để điểm"
        " toàn slice trúng cache của run quét lưới",
    )


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
    order: NonNegativeInt = Field(description="Thứ tự đánh giá, bắt đầu từ 0, liên tục")
    level: float
    scope: EvalScope
    drop: float | None = Field(
        description="Đại lượng so với ngưỡng (theo metric_kind); null khi run không có metric"
    )
    drop_ci: tuple[float, float] | None = Field(
        default=None,
        description="Phase 7: khoảng tin cậy bootstrap 95%; chỉ điểm toàn slice, null khi chưa"
        " tính hoặc bootstrap_samples = 0",
    )
    synthetic: bool = Field(
        default=False,
        description='Phase 7: level "không biến đổi" của spec (eps = 0, tỉ lệ che = 0): drop = 0'
        " theo định nghĩa, không chạy, không có run",
    )
    run_id: UUID | None = Field(description="null khi và chỉ khi synthetic")

    @model_validator(mode="after")
    def _check(self) -> TrajectoryPoint:
        if (self.run_id is None) != self.synthetic:
            raise ValueError("run_id là null khi và chỉ khi synthetic = true")
        if self.synthetic and self.drop != 0:
            raise ValueError("điểm synthetic có drop = 0")
        if self.drop_ci is not None:
            if self.scope != EvalScope.FULL:
                raise ValueError("drop_ci chỉ có ở điểm toàn slice")
            if self.drop_ci[0] > self.drop_ci[1]:
                raise ValueError("drop_ci phải có dạng [thấp, cao]")
        return self


# Đại lượng so với ngưỡng (requirements.md Phase 7 mục "Đại lượng dùng để so với ngưỡng").
SearchMetricKind = Literal["map50", "class_ap50", "asr", "class_asr"]


def search_metric_kind(threshold_kind: ThresholdKind, class_filter: str | None) -> str:
    if threshold_kind == ThresholdKind.ATTACK_SUCCESS_RATE:
        return "asr" if class_filter is None else "class_asr"
    return "map50" if class_filter is None else "class_ap50"


# Trạng thái có điểm gãy (non_monotonic vẫn báo điểm gãy đầu tiên tìm được).
_HAS_BREAKING_POINT = frozenset({SearchStatus.FOUND, SearchStatus.NON_MONOTONIC})


class SearchResult(_Model):
    """Kết quả tìm ngưỡng của một attack (Phase 7).

    Worker gửi bản tạm thời sau mỗi điểm (`stage` khác `done`, `status` null) và bản cuối
    (`stage = done`) kèm bootstrap. `bracket` là khoảng hiện tại, kể cả khi dừng giữa chừng.
    """

    schema_version: Literal[1] = 1
    experiment_id: UUID
    attack_spec_id: UUID
    stage: SearchStage
    status: SearchStatus | None = Field(description="null khi và chỉ khi stage khác done")
    threshold_kind: ThresholdKind
    threshold: float = Field(gt=0, le=1)
    class_filter: str | None = Field(min_length=1)
    metric_kind: SearchMetricKind = Field(
        description="map50: mAP@0.5; class_ap50: AP@0.5 của class_filter; asr: ASR mọi object;"
        " class_asr: ASR object của class_filter. Suy từ threshold_kind và class_filter"
    )
    breaking_point: float | None = Field(
        default=None,
        description="Có khi và chỉ khi status là found hoặc non_monotonic (= bracket[1])",
    )
    bracket: tuple[float, float] = Field(description="Khoảng hiện tại, kể cả khi dừng giữa chừng")
    confidence_interval: tuple[float, float] | None = Field(
        default=None, description="Khoảng tin cậy 95% của điểm gãy; null nếu chưa tính bootstrap"
    )
    near_threshold: bool = Field(
        description="Khoảng tin cậy của d(b) có cận dưới < ngưỡng, hoặc của d(a) có cận trên"
        " >= ngưỡng; false khi chưa tính bootstrap"
    )
    max_points: PositiveInt = Field(description="Giới hạn trên số run (ml_core/search/bounds.py)")
    points_used: NonNegativeInt = Field(description="Số điểm đã đánh giá (không gồm synthetic)")
    message: str | None = Field(
        default=None, min_length=1, description="Có khi và chỉ khi status = failed"
    )
    trajectory: list[TrajectoryPoint]

    @model_validator(mode="after")
    def _check(self) -> SearchResult:
        if (self.status is None) != (self.stage != SearchStage.DONE):
            raise ValueError("status là null khi và chỉ khi stage khác done")
        if (self.status in _HAS_BREAKING_POINT) != (self.breaking_point is not None):
            raise ValueError("breaking_point có khi và chỉ khi status là found hoặc non_monotonic")
        if self.breaking_point is not None and self.breaking_point != self.bracket[1]:
            raise ValueError("breaking_point phải bằng bracket[1]")
        if (self.message is not None) != (self.status == SearchStatus.FAILED):
            raise ValueError("message có khi và chỉ khi status = failed")
        if self.bracket[0] > self.bracket[1]:
            raise ValueError("bracket phải có dạng [thấp, cao]")
        ci = self.confidence_interval
        if ci is not None and ci[0] > ci[1]:
            raise ValueError("confidence_interval phải có dạng [thấp, cao]")
        if self.metric_kind != search_metric_kind(self.threshold_kind, self.class_filter):
            raise ValueError("metric_kind phải khớp threshold_kind và class_filter")
        if [p.order for p in self.trajectory] != list(range(len(self.trajectory))):
            raise ValueError("trajectory phải theo order 0, 1, 2, ... liên tục")
        real = [p.run_id for p in self.trajectory if not p.synthetic]
        if len(set(real)) != len(real):
            raise ValueError("mỗi run chỉ là một điểm của trajectory")
        if self.points_used != len(real):
            raise ValueError("points_used phải bằng số điểm không synthetic của trajectory")
        if self.points_used > self.max_points:
            raise ValueError("points_used không được vượt max_points")
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
    framework: Literal["ultralytics", "torchvision", "onnx"] = Field(
        description="Phase R2 thêm onnx (chỉ inference, supports_gradients luôn false)"
    )
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
        if self.framework == "onnx" and self.supports_gradients:
            raise ValueError("model onnx không hỗ trợ gradient")
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
    perturbation_png: str = Field(
        min_length=1, description="Ảnh thứ ba; nội dung theo FailureCaseRecord.perturbation_kind"
    )
    clean_thumb: str | None = Field(default=None, description=_THUMB)
    adversarial_thumb: str | None = Field(default=None, description=_THUMB)


class CaseAnonymization(_Model):
    """Làm mờ mặt người và biển số trên ảnh hiển thị của failure case (Phase 6)."""

    applied: bool
    method: str = Field(pattern=r"^[a-z][a-z0-9_]*$", examples=["rule_v1"])
    version: PositiveInt = Field(description="Version cài đặt của method")
    regions_count: NonNegativeInt = Field(description="Số vùng đã làm mờ trên ảnh")


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
    perturbation_kind: PerturbationImageKind = Field(
        default=PerturbationImageKind.AMPLIFIED_NOISE,
        description="Phase 6: nhiễu khuếch đại (FGSM, PGD), vùng khác biệt (corruption,"
        " occlusion) hoặc vị trí patch",
    )
    anonymization: CaseAnonymization | None = Field(
        default=None,
        description="null với case tạo trước Phase 6 (ảnh chưa làm mờ); case mới luôn có",
    )

    @model_validator(mode="after")
    def _check(self) -> FailureCaseRecord:
        expected_id = compute_failure_case_id(self.fingerprint, self.run_id, self.image_id)
        if self.id != expected_id:
            raise ValueError(f"id phải là compute_failure_case_id (tính lại: {expected_id})")
        expected = self.lost_objects + 0.5 * self.new_false_positives
        if self.severity_score != expected:
            raise ValueError(f"severity_score phải bằng {expected}")
        return self


# ---------------------------------------------------------------- Phase 6: patch


def compute_patch_key(
    *,
    spec_sha256: str,
    weights_sha256: str,
    training_slice_sha256: str,
    area_ratio: float,
    seed: int,
) -> str:
    """Khóa patch: mỗi khóa chỉ train một lần (requirements.md Phase 6, Patch attack)."""
    return sha256_of(
        {
            "spec_sha256": spec_sha256,
            "weights_sha256": weights_sha256,
            "training_slice_sha256": training_slice_sha256,
            "area_ratio": area_ratio,
            "seed": seed,
        }
    )


def patch_prefix(key: str) -> str:
    """Thư mục của patch trong bucket artifact (patch, checkpoint)."""
    return f"patches/{key}/"


class PatchArtifact(_Model):
    """Patch đã train, lưu trong MinIO dưới `patches/<key>/`, dùng lại giữa các experiment."""

    schema_version: Literal[1] = 1
    key: Sha256Hex = Field(description="compute_patch_key của năm trường bên dưới")
    spec_sha256: Sha256Hex
    weights_sha256: Sha256Hex
    training_slice_sha256: Sha256Hex
    area_ratio: float = Field(gt=0, le=1)
    seed: NonNegativeInt
    side_px: PositiveInt = Field(description="Cạnh patch vuông, pixel trong không gian letterbox")
    patch_sha256: Sha256Hex = Field(description="sha256 của file .npy")
    png_key: ObjectKey
    npy_key: ObjectKey = Field(description="Mảng float32 (C, H, W) trong [0, 1]")
    iterations: PositiveInt = Field(description="Số vòng lặp đã train (bằng training.max_iter)")
    training_seconds: NonNegativeFloat = Field(description="Cộng dồn qua các lần chạy tiếp")
    objective_history: list[float] = Field(
        description="Giá trị mục tiêu sau mỗi vòng lặp (loss của detector trên ảnh đã dán patch;"
        " attack untargeted làm giá trị này tăng)"
    )
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _check(self) -> PatchArtifact:
        expected = compute_patch_key(
            spec_sha256=self.spec_sha256,
            weights_sha256=self.weights_sha256,
            training_slice_sha256=self.training_slice_sha256,
            area_ratio=self.area_ratio,
            seed=self.seed,
        )
        if self.key != expected:
            raise ValueError(f"key phải là compute_patch_key (tính lại: {expected})")
        prefix = patch_prefix(self.key)
        if not (self.png_key.startswith(prefix) and self.npy_key.startswith(prefix)):
            raise ValueError("png_key và npy_key phải nằm trong patches/<key>/")
        if len(self.objective_history) != self.iterations:
            raise ValueError("objective_history phải có đúng iterations phần tử")
        return self


# ---------------------------------------------------------------- Phase 3: API nội bộ của worker


class CostProfile(_Model):
    """Chi phí đo bằng calibration, riêng cho từng (compute target, model, attack)."""

    schema_version: Literal[1] = 1
    compute_target_id: UUID
    model_version_id: UUID
    attack_spec_id: UUID
    sec_per_image: PositiveFloat
    sec_per_image_iteration: PositiveFloat | None = Field(
        default=None,
        description="Phase 6: giây cho một ảnh trong một vòng lặp huấn luyện; chỉ có với spec"
        " requires_training",
    )
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
    metrics: RunMetrics | None = Field(
        default=None,
        description="Phase 6: metric của run đã có kết quả, để worker tính lại dừng sớm khi chạy"
        " tiếp sau gián đoạn",
    )
    patch_key: Sha256Hex | None = Field(
        default=None, description="Phase 6: khóa patch với run patch (có trong bundle.patches)"
    )
    scope: EvalScope = Field(
        default=EvalScope.FULL,
        exclude_if=lambda v: v == EvalScope.FULL,
        description="Phase 7: subset khi run đánh giá tập con của tìm ngưỡng",
    )
    search_order: NonNegativeInt | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Phase 7: thứ tự điểm của run tìm ngưỡng; null với run quét lưới",
    )

    @model_validator(mode="after")
    def _check(self) -> BundleRun:
        if self.images_done > self.images_total:
            raise ValueError("images_done không được lớn hơn images_total")
        if self.scope == EvalScope.SUBSET and self.search_order is None:
            raise ValueError("run scope = subset phải có search_order")
        if self.checkpoint is not None and self.status != RunStatus.RUNNING:
            raise ValueError("checkpoint chỉ có khi status = running")
        return self


class BundlePatch(_Model):
    """Patch mà một run của experiment cần (Phase 6)."""

    key: Sha256Hex
    attack_spec_id: UUID
    area_ratio: float = Field(gt=0, le=1)
    training_slice_id: UUID
    artifact: PatchArtifact | None = Field(description="null khi chưa train xong")
    checkpoint_key: ObjectKey | None = Field(
        description="Checkpoint train mới nhất trong patches/<key>/ khi đang train dở; file"
        " checkpoint tự ghi số vòng lặp đã xong"
    )

    @model_validator(mode="after")
    def _check(self) -> BundlePatch:
        if self.artifact is not None:
            if self.artifact.key != self.key or self.artifact.area_ratio != self.area_ratio:
                raise ValueError("artifact phải cùng key và area_ratio")
            if self.checkpoint_key is not None:
                raise ValueError("patch đã train xong không còn checkpoint_key")
        if self.checkpoint_key is not None and not self.checkpoint_key.startswith(
            patch_prefix(self.key)
        ):
            raise ValueError("checkpoint_key phải nằm trong patches/<key>/")
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
    runs: list[BundleRun] = Field(
        description="Theo thứ tự chạy: run quét lưới trước, rồi run tìm ngưỡng đã tạo (Phase 7)."
        " Rỗng được khi mọi attack ở chế độ tìm ngưỡng và chưa có điểm nào"
    )
    training_slices: list[SliceSpec] = Field(
        default_factory=list,
        description="Phase 6: slice huấn luyện của các attack có training_slice_id",
    )
    patches: list[BundlePatch] = Field(
        default_factory=list, description="Phase 6: patch mà các run patch cần, không trùng key"
    )
    search_results: list[SearchResult] = Field(
        default_factory=list,
        description="Phase 7: SearchResult mới nhất của từng attack tìm ngưỡng đã có điểm; worker"
        " chạy lại thuật toán theo trajectory để tiếp tục đúng giai đoạn sau gián đoạn",
    )

    @model_validator(mode="after")
    def _check(self) -> WorkerJobBundle:
        cfg = self.config
        search_ids = {a.attack_spec_id for a in cfg.attacks if a.mode == RunMode.SEARCH}
        if not self.runs and len(search_ids) != len(cfg.attacks):
            raise ValueError("runs chỉ rỗng khi mọi attack ở chế độ tìm ngưỡng")
        for run in self.runs:
            if (run.search_order is not None) != (run.attack_spec_id in search_ids):
                raise ValueError("search_order có khi và chỉ khi run thuộc attack tìm ngưỡng")
        found = [r.attack_spec_id for r in self.search_results]
        if len(set(found)) != len(found) or not set(found) <= search_ids:
            raise ValueError("search_results: mỗi attack tìm ngưỡng tối đa một kết quả")
        if any(r.experiment_id != self.experiment_id for r in self.search_results):
            raise ValueError("search_results phải thuộc experiment này")
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
        training = {s.id: s for s in self.training_slices}
        needed = {a.training_slice_id for a in cfg.attacks if a.training_slice_id is not None}
        if set(training) != needed:
            raise ValueError("training_slices phải đúng các training_slice_id trong config")
        evaluation = set(self.slice.image_ids)
        for training_slice in self.training_slices:
            if training_slice.dataset_version_sha256 != self.slice.dataset_version_sha256:
                raise ValueError("slice huấn luyện phải cùng dataset version với slice đánh giá")
            if evaluation.intersection(training_slice.image_ids):
                raise ValueError("slice huấn luyện không được giao với slice đánh giá")
        images = set(self.slice.image_ids).union(*(s.image_ids for s in self.training_slices))
        if set(self.downloads.images) != images:
            raise ValueError("downloads.images phải đúng các ảnh của slice và slice huấn luyện")
        patches = {p.key: p for p in self.patches}
        if len(patches) != len(self.patches):
            raise ValueError("patches không được trùng key")
        for patch in self.patches:
            if patch.attack_spec_id not in spec_ids or patch.training_slice_id not in training:
                raise ValueError("patch phải thuộc attack và slice huấn luyện của config")
        if {r.patch_key for r in self.runs if r.patch_key is not None} != set(patches):
            raise ValueError("patches phải đúng các patch_key của runs")
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
    """Tiến độ sau mỗi batch (đánh giá) hoặc sau mỗi vòng lặp train patch (Phase 6)."""

    lease_id: UUID
    images_done: NonNegativeInt = Field(
        description="Tổng số ảnh đã xử lý của run; 0 khi phase = training"
    )
    batch_index: NonNegativeInt = Field(description="0 khi phase = training")
    checkpoint_key: ObjectKey = Field(
        description="evaluating: trong runs/<run_id>/; training: checkpoint patch mới nhất trong"
        " patches/<patch_key>/ (worker ghi checkpoint ở vòng 0 trước khi báo)"
    )
    processing_seconds_delta: NonNegativeFloat = Field(
        description="Thời gian xử lý từ lần báo trước (gồm thời gian train); API cộng dồn"
    )
    phase: RunPhase = RunPhase.EVALUATING
    iterations_done: NonNegativeInt | None = Field(
        default=None, description="Chỉ có khi phase = training"
    )
    iterations_total: PositiveInt | None = Field(
        default=None, description="Chỉ có khi phase = training (training.max_iter)"
    )

    @model_validator(mode="after")
    def _check_phase(self) -> ProgressReport:
        training = self.phase == RunPhase.TRAINING
        if training != (self.iterations_done is not None and self.iterations_total is not None):
            raise ValueError(
                "iterations_done và iterations_total có khi và chỉ khi phase = training"
            )
        done, total = self.iterations_done, self.iterations_total
        if done is not None and total is not None and done > total:
            raise ValueError("iterations_done không được lớn hơn iterations_total")
        if training and (self.images_done != 0 or self.batch_index != 0):
            raise ValueError("phase = training có images_done = 0 và batch_index = 0")
        return self


class WorkerDirective(_Model):
    action: Literal["continue", "cancel", "stop_limit"]
    remaining_seconds: NonNegativeFloat | None = Field(
        description="Thời gian xử lý còn lại; null khi giới hạn là tiền"
    )


class ArtifactUrlRequest(_Model):
    lease_id: UUID
    key: ObjectKey = Field(
        description="Khóa đầy đủ, phải nằm trong runs/<run_id>/, hoặc trong patches/<patch_key>/"
        " với patch_key của run (Phase 6). Run phải đang running, trừ GET"
        " runs/<run_id>/predictions.json của run đã kết thúc thuộc experiment đang lease (Phase 7,"
        " bootstrap; đề xuất contract 001)"
    )
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


class RunSkipRequest(_Model):
    """Body của `POST /runs/{id}/skip` (Phase 6): bỏ run chưa start do dừng sớm."""

    lease_id: UUID
    code: Literal["early_stop"]
    trigger_run_id: UUID = Field(description="Run của cùng attack đã làm model sụp")
    message: str = Field(min_length=1)


class SearchRunCreate(_Model):
    """Body của `POST /internal/worker/experiments/{id}/runs` (Phase 7): tạo run cho điểm tìm
    ngưỡng kế tiếp. Trả `BundleRun` (`queued`). API trả `422` (không `409`) khi attack không ở
    chế độ tìm ngưỡng, level ngoài `[lo, hi]` hoặc vượt `max_points`."""

    lease_id: UUID
    attack_spec_id: UUID
    level: float
    scope: EvalScope
    search_order: NonNegativeInt = Field(description="Bằng TrajectoryPoint.order của điểm này")


class SearchResultReport(_Model):
    """Body của `POST /internal/worker/experiments/{id}/search-result` (Phase 7): bản tạm thời sau
    mỗi điểm, bản cuối khi xong. Bản sau thay bản trước của cùng attack."""

    lease_id: UUID
    result: SearchResult


class PatchRegistration(_Model):
    """Body của `POST /runs/{id}/patch` (Phase 6): đăng ký patch vừa train xong.

    Khóa đã có (worker khác đăng ký trước) thì API giữ bản cũ và trả bản đó; worker dùng bản trả
    về để đánh giá.
    """

    lease_id: UUID
    artifact: PatchArtifact


# ---------------------------------------------------------------- API chung


class FieldError(_Model):
    """Lỗi của một trường (Phase 5): giao diện hiển thị tại đúng bước và đúng trường."""

    path: str = Field(
        min_length=1,
        examples=["attacks.0.grid.levels"],
        description="Đường dẫn trường trong body, các đoạn ngăn bởi dấu chấm, chỉ số mảng từ 0",
    )
    message: str = Field(min_length=1)


class ComplianceItem(_Model):
    """Một mục tuân thủ protocol (Phase 8): trong ước lượng, ExperimentDetail và lỗi 422
    `not_compliant` khi tạo experiment."""

    code: ComplianceCode
    attack_spec_name: str | None = Field(
        default=None, description="Attack bắt buộc của mục này; null với mục không theo attack"
    )
    satisfied: bool
    detail: str = Field(min_length=1)


class ChecklistItem(_Model):
    """Một điều kiện trạng thái trước khi chấp nhận (Phase 8)."""

    code: ChecklistCode
    satisfied: bool
    detail: str = Field(min_length=1)


class SubmitCheckItem(_Model):
    """Một điều kiện gửi duyệt (Phase 8)."""

    code: SubmitCheckCode
    satisfied: bool
    detail: str = Field(min_length=1)


class ErrorBody(_Model):
    code: ErrorCode
    message: str = Field(min_length=1)
    fields: list[FieldError] | None = Field(
        default=None,
        description="Chỉ có ở lỗi 422 gắn được với trường cụ thể; không có thì bỏ khỏi body",
    )
    compliance: list[ComplianceItem] | None = Field(
        default=None,
        description="Phase 8: chỉ có ở lỗi 422 not_compliant (mọi mục, kể cả mục đã thỏa)",
    )
    checklist: list[ChecklistItem] | None = Field(
        default=None, description="Phase 8: chỉ có ở lỗi 409 checklist_incomplete"
    )


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


# ---------------------------------------------------------------- ProtocolBody (Phase 8)

AttackSpecName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class RequiredGrid(_Model):
    levels: list[float] = Field(
        min_length=1, description="Level tối thiểu phải chạy; experiment được thêm level khác"
    )

    @model_validator(mode="after")
    def _check(self) -> RequiredGrid:
        if len(set(self.levels)) != len(self.levels):
            raise ValueError("grid.levels không được trùng")
        return self


class RequiredSearch(_Model):
    """Cấu hình tìm ngưỡng tối thiểu: experiment phải cùng ngưỡng, dải bao phủ [lo, hi],
    `tol ≤ max_tol`, `bootstrap_samples ≥ min_bootstrap_samples` (requirements.md Phase 8)."""

    threshold_kind: ThresholdKind
    threshold: float = Field(gt=0, le=1)
    class_filter: str | None = Field(default=None, min_length=1, description="Một class đích")
    lo: float
    hi: float
    max_tol: PositiveFloat
    min_bootstrap_samples: int = Field(
        default=200,
        ge=0,
        le=1000,
        description="0 cho phép không tính khoảng tin cậy (tiêu chí khi đó không bao giờ"
        " inconclusive do khoảng tin cậy)",
    )

    @model_validator(mode="after")
    def _check(self) -> RequiredSearch:
        if self.lo >= self.hi:
            raise ValueError("search.lo phải nhỏ hơn hi")
        if self.max_tol >= self.hi - self.lo:
            raise ValueError("search.max_tol phải nhỏ hơn hi - lo")
        return self


class RequiredAttack(_Model):
    """Attack bắt buộc. Một protocol không có hai attack cùng `attack_spec_name` (Phase 5: một
    experiment không có hai attack cùng spec). Kiểm tra cần catalog (spec tồn tại, `spec_sha256`
    khớp, patch không ở chế độ tìm ngưỡng, dải trong `primary_param`) ở backend."""

    attack_spec_name: AttackSpecName
    spec_sha256: Sha256Hex = Field(description="Chốt đúng version spec")
    mode: RunMode
    grid: RequiredGrid | None = None
    search: RequiredSearch | None = None

    @model_validator(mode="after")
    def _check(self) -> RequiredAttack:
        if self.mode == RunMode.GRID and (self.grid is None or self.search is not None):
            raise ValueError("mode = grid cần grid và không có search")
        if self.mode == RunMode.SEARCH and (self.search is None or self.grid is not None):
            raise ValueError("mode = search cần search và không có grid")
        return self


class PassCriterion(_Model):
    """Tiêu chí đạt (requirements.md Phase 8, bảng Đánh giá tiêu chí).

    - `max_drop_at_level`: attack quét lưới; đại lượng `threshold_kind` (theo `class_filter`) tại
      `level` (một level bắt buộc) ≤ `threshold`.
    - `min_breaking_point`: attack tìm ngưỡng; điểm gãy của chính lần tìm ngưỡng bắt buộc (cùng
      `threshold_kind`, `threshold`, `class_filter`) ≥ `level`, với `lo < level ≤ hi`.
    """

    kind: CriterionKind
    attack_spec_name: AttackSpecName
    level: float
    threshold_kind: ThresholdKind
    threshold: float = Field(gt=0, le=1)
    class_filter: str | None = Field(
        default=None,
        min_length=1,
        description="Một class đích; cùng kiểu với SearchConfig.class_filter (Phase 7)",
    )


def _check_criterion(criterion: PassCriterion, attack: RequiredAttack | None, i: int) -> None:
    where = f"pass_criteria.{i}"
    if attack is None:
        raise ValueError(
            f"{where}: attack {criterion.attack_spec_name} không có trong required_attacks"
        )
    if criterion.kind == CriterionKind.MAX_DROP_AT_LEVEL:
        if attack.grid is None:
            raise ValueError(f"{where}: max_drop_at_level chỉ dùng với attack quét lưới")
        if criterion.level not in attack.grid.levels:
            raise ValueError(f"{where}: level phải là một level bắt buộc của attack")
        return
    if attack.search is None:
        raise ValueError(f"{where}: min_breaking_point chỉ dùng với attack tìm ngưỡng")
    search = attack.search
    if (criterion.threshold_kind, criterion.threshold, criterion.class_filter) != (
        search.threshold_kind,
        search.threshold,
        search.class_filter,
    ):
        raise ValueError(
            f"{where}: min_breaking_point phải cùng threshold_kind, threshold, class_filter với"
            " cấu hình tìm ngưỡng bắt buộc"
        )
    if not search.lo < criterion.level <= search.hi:
        raise ValueError(f"{where}: level phải thỏa lo < level ≤ hi của tìm ngưỡng")


class ProtocolBody(_Model):
    """Nội dung một version protocol; không bao giờ thay đổi sau khi tạo (Phase 8 thay bản Phase 0,
    bỏ `review_severity_threshold`). Danh sách rỗng chỉ dùng cho protocol `dev` (dev-open);
    `ProtocolCreate` bắt buộc có attack và tiêu chí."""

    schema_version: Literal[2] = 2
    description: LongText = Field(description="Mục đích của protocol")
    required_attacks: list[RequiredAttack]
    min_slice_size: PositiveInt
    pass_criteria: list[PassCriterion]
    cases_to_review_per_attack: PositiveInt = Field(
        default=5,
        description="Số failure case có severity_score cao nhất của mỗi attack bắt buộc phải có"
        " verdict",
    )
    forbid_dirty_runs: bool = Field(default=True, description="Cấm run có git_dirty = true")

    @model_validator(mode="after")
    def _check(self) -> ProtocolBody:
        names = [a.attack_spec_name for a in self.required_attacks]
        if len(set(names)) != len(names):
            raise ValueError("required_attacks không được trùng attack_spec_name")
        by_name = {a.attack_spec_name: a for a in self.required_attacks}
        for i, criterion in enumerate(self.pass_criteria):
            _check_criterion(criterion, by_name.get(criterion.attack_spec_name), i)
        return self


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


# ---------------------------------------------------------------- Experiment trên web (Phase 5)

Seconds = NonNegativeFloat
# URL ảnh tạm thời, tương đối với gốc API (frontend thêm VITE_API_BASE_URL): chỉ đọc được đúng một
# đối tượng, cần cả phiên đăng nhập có `experiment.read` lẫn token chưa hết hạn.
ArtifactUrl = Annotated[str, StringConstraints(pattern=r"^/artifacts/[A-Za-z0-9._~-]+$")]
ExperimentName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

# Trạng thái experiment chưa kết thúc (chưa có finished_at).
_UNFINISHED = frozenset({ExperimentStatus.DRAFT, ExperimentStatus.QUEUED, ExperimentStatus.RUNNING})


class ExperimentCreate(ExperimentConfig):
    """Body của `POST /experiments` và `POST /experiments/estimate`."""

    name: ExperimentName | None = Field(
        default=None, description="Bỏ trống: server đặt `<model> · <slice> · <YYYY-MM-DD UTC>`"
    )
    cloned_from: UUID | None = Field(default=None, description="Experiment gốc khi nhân bản")
    promoted_from: UUID | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Phase R2: experiment Khám phá nguồn khi nâng lên chính thức (chỉ để truy vết)",
    )


class CloneWarning(_Model):
    attack_spec_id: UUID = Field(description="ID của spec ở version hiện hành (trong config)")
    from_version: PositiveInt
    to_version: PositiveInt
    message: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> CloneWarning:
        if self.to_version <= self.from_version:
            raise ValueError("to_version phải lớn hơn from_version")
        return self


class DraftNote(_Model):
    """Lưu ý của bản nháp không gắn với version spec (Phase R2: promote, draft từ preset)."""

    code: Literal["slice_too_small"] = Field(
        description="slice_too_small: slice nhỏ hơn min_slice_size của protocol; compliance sẽ"
        " chặn khi gửi duyệt"
    )
    message: str = Field(min_length=1)


class ExperimentClone(_Model):
    """`GET /experiments/{id}/clone`: cấu hình điền sẵn; spec cũ đã lên version hiện hành.

    Phase R2 dùng lại cho `POST /experiments/{id}/promote` và `POST /experiments/draft`: chỉ trả
    bản nháp, không tạo experiment.
    """

    config: ExperimentCreate
    warnings: list[CloneWarning]
    notes: list[DraftNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> ExperimentClone:
        ids = {attack.attack_spec_id for attack in self.config.attacks}
        if any(w.attack_spec_id not in ids for w in self.warnings):
            raise ValueError("warnings[].attack_spec_id phải có trong config.attacks")
        return self


class EstimateRun(_Model):
    attack_spec_id: UUID
    level: float
    images: PositiveInt
    sec_per_image: NonNegativeFloat | None = Field(description="null khi thiếu cost profile")
    est_seconds: Seconds | None = Field(
        description="images * sec_per_image * 1.2; null khi thiếu profile; 0 khi run sẽ bị bỏ qua"
    )
    skip_reason: Literal["incompatible"] | None = Field(
        description="Run sẽ bị `skipped`: attack cần gradient, model không hỗ trợ"
    )
    training_seconds: Seconds | None = Field(
        default=None,
        description="Phase 6: max_iter * số ảnh slice huấn luyện * sec_per_image_iteration khi"
        " patch chưa có; null khi patch đã có, spec không cần train, thiếu profile hoặc run bị bỏ"
        " qua. Không gồm trong est_seconds, nhưng cộng vào total_seconds và exceeds_limit",
    )

    @model_validator(mode="after")
    def _check(self) -> EstimateRun:
        if self.training_seconds is not None and (
            self.skip_reason is not None or self.est_seconds is None
        ):
            raise ValueError("training_seconds chỉ có khi run được ước lượng và không bị bỏ qua")
        if self.skip_reason is not None:
            if self.est_seconds != 0:
                raise ValueError("run sẽ bị bỏ qua phải có est_seconds = 0")
        elif (self.sec_per_image is None) != (self.est_seconds is None):
            raise ValueError("sec_per_image và est_seconds cùng null hoặc cùng có giá trị")
        return self


class QueueEstimate(_Model):
    position: PositiveInt = Field(description="Vị trí của experiment mới trong hàng đợi của target")
    ahead_seconds: Seconds = Field(
        description="Tổng ước lượng còn lại của các experiment đứng trước"
        " (bỏ phần không ước lượng được)"
    )


class SearchEstimate(_Model):
    """Chi phí tối đa của một attack tìm ngưỡng (Phase 7)."""

    attack_spec_id: UUID
    max_points: PositiveInt = Field(description="max_subset_points + max_full_points")
    max_subset_points: NonNegativeInt = Field(description="0 khi slice không lớn hơn subset_size")
    max_full_points: PositiveInt
    max_seconds: Seconds | None = Field(
        description="(max_subset_points * subset_size + max_full_points * số ảnh slice)"
        " * sec_per_image * 1.2; null khi thiếu profile"
    )

    @model_validator(mode="after")
    def _check(self) -> SearchEstimate:
        if self.max_points != self.max_subset_points + self.max_full_points:
            raise ValueError("max_points phải bằng max_subset_points + max_full_points")
        return self


class EstimateResponse(_Model):
    runs: list[EstimateRun] = Field(
        description="Run quét lưới; rỗng được khi mọi attack ở chế độ tìm ngưỡng (Phase 7)"
    )
    total_seconds: Seconds | None = Field(
        description="Tổng est_seconds và training_seconds; null khi có run thiếu profile"
    )
    missing_profiles: list[UUID] = Field(
        description="attack_spec_id thiếu cost profile, không trùng"
    )
    exceeds_limit: bool = Field(
        description="Tổng est_seconds và training_seconds của các run ước lượng được (cận dưới khi"
        " thiếu profile) lớn hơn giới hạn thời gian"
    )
    queue: QueueEstimate
    searches: list[SearchEstimate] = Field(
        default_factory=list, description="Phase 7: mỗi attack tìm ngưỡng một dòng"
    )
    max_total_seconds: Seconds | None = Field(
        default=None,
        description="Phase 7: total_seconds + tổng max_seconds; null khi không có attack tìm"
        " ngưỡng, hoặc có run hay search thiếu ước lượng",
    )
    max_exceeds_limit: bool = Field(
        default=False,
        description="Phase 7: tổng ước lượng được của trường hợp xấu nhất (run quét lưới và"
        " max_seconds) lớn hơn giới hạn thời gian; chỉ cảnh báo, không chặn tạo experiment",
    )
    compliance: list[ComplianceItem] = Field(
        default_factory=list,
        description="Phase 8: tuân thủ protocol, giống kết quả kiểm tra khi tạo; rỗng với protocol"
        " dev",
    )

    @model_validator(mode="after")
    def _check(self) -> EstimateResponse:
        if not self.runs and not self.searches:
            raise ValueError("cần ít nhất một run hoặc một search")
        unknown = [r for r in self.runs if r.skip_reason is None and r.est_seconds is None]
        if (self.total_seconds is None) != bool(unknown):
            raise ValueError("total_seconds là null khi và chỉ khi có run thiếu ước lượng")
        if len(set(self.missing_profiles)) != len(self.missing_profiles):
            raise ValueError("missing_profiles không được trùng")
        unknown_searches = [s for s in self.searches if s.max_seconds is None]
        missing = {r.attack_spec_id for r in unknown} | {s.attack_spec_id for s in unknown_searches}
        if set(self.missing_profiles) != missing:
            raise ValueError(
                "missing_profiles phải đúng bằng các attack của run và search thiếu ước lượng"
            )
        ids = [s.attack_spec_id for s in self.searches]
        if len(set(ids)) != len(ids):
            raise ValueError("searches không được trùng attack")
        if ids and {r.attack_spec_id for r in self.runs} & set(ids):
            raise ValueError("attack tìm ngưỡng không có run quét lưới")
        known_max = self.searches and self.total_seconds is not None and not unknown_searches
        if (self.max_total_seconds is not None) != bool(known_max):
            raise ValueError(
                "max_total_seconds có khi và chỉ khi có search và mọi run, search ước lượng được"
            )
        if not self.searches and self.max_exceeds_limit:
            raise ValueError("max_exceeds_limit chỉ true khi có attack tìm ngưỡng")
        if self.exceeds_limit and self.searches and not self.max_exceeds_limit:
            raise ValueError("exceeds_limit kéo theo max_exceeds_limit")
        return self


class UserRef(_Model):
    id: UUID
    full_name: str


class ModelRef(_Model):
    id: UUID = Field(description="ID của model version")
    name: str


class SliceRef(_Model):
    id: UUID
    name: str
    size: PositiveInt


class ComputeTargetRef(_Model):
    id: UUID
    name: str
    kind: ComputeKind


class ProtocolRef(_Model):
    id: UUID
    name: str
    status: ProtocolStatus


class RunCounts(_Model):
    """Số run theo từng `RunStatus`."""

    queued: NonNegativeInt
    running: NonNegativeInt
    completed: NonNegativeInt
    failed: NonNegativeInt
    skipped: NonNegativeInt
    stopped_limit: NonNegativeInt
    cancelled: NonNegativeInt


class ExperimentSummary(_Model):
    id: UUID
    name: ExperimentName
    owner: UserRef
    status: ExperimentStatus
    model: ModelRef
    slice: SliceRef
    compute_target: ComputeTargetRef
    run_counts: RunCounts
    progress: Progress = Field(description="Tổng số ảnh đã xử lý trên mọi run")
    created_at: UtcDatetime
    finished_at: UtcDatetime | None = Field(description="null khi draft, queued hoặc running")
    mode: ExperimentMode = Field(
        description="Phase R2: exploration khi và chỉ khi protocol có status dev"
    )

    @model_validator(mode="after")
    def _check_finished(self) -> ExperimentSummary:
        if (self.finished_at is None) != (self.status in _UNFINISHED):
            raise ValueError("finished_at là null khi và chỉ khi status là draft, queued, running")
        if self.finished_at is not None and self.finished_at < self.created_at:
            raise ValueError("finished_at không được trước created_at")
        return self


class AttackRankingEntry(_Model):
    """Một attack trong bảng xếp hạng (Phase 6, `ml_core/metrics/ranking.py`).

    Điểm của đường cong: (level / primary_param.max, relative_drop), thêm (0, 0) ở đầu; level bị
    `early_stop` lấy relative_drop của run kích hoạt. Diện tích tính đến `coverage`, không ngoại
    suy.
    """

    attack_spec_id: UUID
    name: str
    kind: AttackKind
    auc_drop: float | None = Field(
        description="Diện tích hình thang; null khi ít hơn 2 điểm (không đủ dữ liệu)"
    )
    max_relative_drop: float | None = Field(description="null khi không có level nào có metric")
    levels_evaluated: NonNegativeInt = Field(description="Số level có metric")
    levels_early_stopped: NonNegativeInt = Field(description="Số level bị bỏ qua do dừng sớm")
    coverage: UnitFloat | None = Field(
        description="level / max lớn nhất được tính (có metric hoặc early_stop); null khi không có"
    )
    partial: bool = Field(description="Có run stopped_limit hoặc metrics.partial")

    @model_validator(mode="after")
    def _check(self) -> AttackRankingEntry:
        points = self.levels_evaluated + self.levels_early_stopped
        if points < 2 and self.auc_drop is not None:
            raise ValueError("auc_drop là null khi ít hơn 2 level có kết quả")
        if (self.coverage is None) != (points == 0):
            raise ValueError("coverage là null khi và chỉ khi không có level nào có kết quả")
        if self.levels_early_stopped and not self.levels_evaluated:
            raise ValueError("level early_stop cần ít nhất một level có metric")
        if self.levels_evaluated == 0 and self.max_relative_drop is not None:
            raise ValueError("max_relative_drop là null khi không có level nào có metric")
        return self


class ExperimentDetail(ExperimentSummary):
    config: ExperimentConfig
    config_sha256: Sha256Hex
    protocol: ProtocolRef
    limit: Limit
    processing_seconds_used: Seconds
    queue_position: PositiveInt | None = Field(description="Chỉ có khi status = queued")
    cloned_from: UUID | None
    clean_metrics: MapPair | None = Field(
        description="mAP ảnh sạch; null khi chưa run nào có metric"
    )
    attack_ranking: list[AttackRankingEntry] = Field(
        default_factory=list,
        description="Phase 6: mỗi attack quét lưới của config một dòng (Phase 7: không gồm attack"
        " tìm ngưỡng), giảm dần theo auc_drop, null xếp cuối",
    )
    search_results: list[SearchResult] = Field(
        default_factory=list,
        description="Phase 7: SearchResult mới nhất của từng attack tìm ngưỡng đã có điểm (cập nhật"
        " khi đang chạy)",
    )
    compliance: list[ComplianceItem] = Field(
        default_factory=list,
        description="Phase 8: tuân thủ protocol version đã gắn; rỗng với protocol dev",
    )
    submit_check: list[SubmitCheckItem] | None = Field(
        default=None,
        description="Phase 8: điều kiện gửi duyệt; chỉ có khi status = completed (backend Phase 8"
        " luôn điền khi completed)",
    )
    runs_requiring_explanation: list[UUID] = Field(
        default_factory=list,
        description="Phase 8: run của attack bắt buộc không completed (trừ skipped do cached,"
        " early_stop) phải có lời giải trình khi gửi duyệt; chỉ có khi status = completed",
    )
    review: ReviewView | None = Field(
        default=None,
        description="Phase 8: có khi và chỉ khi experiment đã gửi duyệt (submitted_for_review,"
        " in_review, approved, changes_requested, rejected)",
    )
    report: ReportView | None = Field(
        default=None, description="Phase 8: report chính thức; chỉ có khi status = approved"
    )

    @model_validator(mode="after")
    def _check_review(self) -> ExperimentDetail:
        completed = self.status == ExperimentStatus.COMPLETED
        if self.submit_check is not None and not completed:
            raise ValueError("submit_check chỉ có khi status = completed")
        if self.runs_requiring_explanation and not completed:
            raise ValueError("runs_requiring_explanation chỉ có khi status = completed")
        if (self.review is not None) != (self.status in _REVIEW_STATUSES):
            raise ValueError("review có khi và chỉ khi experiment đã gửi duyệt")
        if self.report is not None:
            if self.status != ExperimentStatus.APPROVED:
                raise ValueError("report chỉ có khi status = approved")
            if self.report.experiment_id != self.id:
                raise ValueError("report phải thuộc experiment này")
        review = self.review
        if review is not None:
            expected = _REVIEW_DECISION_STATUS.get(review.decision)
            if expected is not None and expected != self.status:
                raise ValueError("review.decision không khớp status")
            if review.decision is None and self.status not in _OPEN_REVIEW:
                raise ValueError("experiment đã quyết định phải có review.decision")
            if (review.assignee is not None) != (self.status != _WAITING_REVIEW):
                raise ValueError(
                    "review.assignee có khi và chỉ khi status khác submitted_for_review"
                )
            if review.assignee is not None and review.assignee.id == self.owner.id:
                raise ValueError("người nhận review không được là người tạo experiment")
        return self

    @model_validator(mode="after")
    def _check_detail(self) -> ExperimentDetail:
        if (self.queue_position is not None) != (self.status == ExperimentStatus.QUEUED):
            raise ValueError("queue_position có khi và chỉ khi status = queued")
        if self.limit != self.config.limit:
            raise ValueError("limit phải bằng config.limit")
        ids = [entry.attack_spec_id for entry in self.attack_ranking]
        if len(set(ids)) != len(ids):
            raise ValueError("attack_ranking không được trùng attack")
        grid = {a.attack_spec_id for a in self.config.attacks if a.mode == RunMode.GRID}
        if not set(ids) <= grid:
            raise ValueError("attack_ranking chỉ gồm attack của config ở chế độ quét lưới")
        search = {a.attack_spec_id for a in self.config.attacks if a.mode == RunMode.SEARCH}
        found = [r.attack_spec_id for r in self.search_results]
        if len(set(found)) != len(found) or not set(found) <= search:
            raise ValueError("search_results: mỗi attack tìm ngưỡng của config tối đa một kết quả")
        if any(r.experiment_id != self.id for r in self.search_results):
            raise ValueError("search_results phải thuộc experiment này")
        scores = [entry.auc_drop for entry in self.attack_ranking]
        known = [score for score in scores if score is not None]
        if scores[: len(known)] != sorted(known, reverse=True):
            raise ValueError("attack_ranking phải giảm dần theo auc_drop, null xếp cuối")
        return self


class ExperimentPage(Page[ExperimentSummary]):
    pass


class RunAttackSpec(_Model):
    name: str
    version: PositiveInt
    param_name: str = Field(description="Tên tham số chính (primary_param.name)")
    param_unit: str = Field(description="Đơn vị tham số chính (primary_param.unit)")
    param_max: PositiveFloat = Field(
        description="primary_param.max; trục hoành chuẩn hóa level / param_max (đề xuất contract"
        " 003, Phase 6)"
    )


class IterationProgress(_Model):
    done: NonNegativeInt
    total: PositiveInt

    @model_validator(mode="after")
    def _check(self) -> IterationProgress:
        if self.done > self.total:
            raise ValueError("done không được lớn hơn total")
        return self


class RunView(_RunCommon):
    """Run hiển thị cho người dùng. `fingerprint` null khi và chỉ khi run chưa bắt đầu: worker
    tính fingerprint ở `start` (đề xuất contract 001, Phase 5)."""

    fingerprint: Sha256Hex | None = Field(
        description="null khi run chưa bắt đầu (queued, bị hủy/dừng trước khi chạy, hoặc bị bỏ qua"
        " do early_stop)"
    )
    attack_spec: RunAttackSpec
    phase: RunPhase | None = Field(
        default=None, description="Phase 6: giai đoạn khi status = running; null khi khác"
    )
    training: IterationProgress | None = Field(
        default=None, description="Phase 6: tiến độ train patch; có khi và chỉ khi phase = training"
    )

    @model_validator(mode="after")
    def _check_phase(self) -> RunView:
        if self.phase is not None and self.status != RunStatus.RUNNING:
            raise ValueError("phase chỉ có khi status = running")
        if (self.training is not None) != (self.phase == RunPhase.TRAINING):
            raise ValueError("training có khi và chỉ khi phase = training")
        return self

    @model_validator(mode="after")
    def _check_not_started(self) -> RunView:
        early_stop = self.status_reason is not None and self.status_reason.code == "early_stop"
        if self.fingerprint is None and (
            (self.status not in _NOT_STARTED and not early_stop)
            or self.progress.images_done != 0
            or self.metrics is not None
            or self.manifest_uri is not None
            or self.failure_case_ids
        ):
            raise ValueError(
                "fingerprint chỉ null khi run chưa bắt đầu (queued, cancelled, stopped_limit, hoặc"
                " skipped do early_stop; chưa xử lý ảnh nào; không có metric, manifest, failure"
                " case)"
            )
        return self


# Trạng thái của run có thể chưa từng bắt đầu (chưa có fingerprint).
_NOT_STARTED = frozenset({RunStatus.QUEUED, RunStatus.CANCELLED, RunStatus.STOPPED_LIMIT})


class FailureCaseUrls(_Model):
    """URL tạm thời của từng artifact; null khi không cấp (ảnh bị ẩn, hoặc danh sách chỉ có
    thumbnail)."""

    clean: ArtifactUrl | None
    adversarial: ArtifactUrl | None
    perturbation: ArtifactUrl | None
    clean_thumb: ArtifactUrl | None
    adversarial_thumb: ArtifactUrl | None


class FailureCaseView(FailureCaseRecord):
    # Nới kiểu của lớp cha (record của worker luôn có khóa); mypy báo gán không tương thích nên
    # cần ignore. Luật null khi và chỉ khi bị ẩn kiểm ở `_check_display`.
    artifacts: CaseArtifacts | None = Field(  # type: ignore[assignment]
        description="Khóa lưu trữ của ảnh; null khi và chỉ khi display_mode = hidden_unanonymized"
        " (không lộ khóa MinIO của ảnh bị ẩn; đề xuất contract 002, Phase 6)"
    )
    urls: FailureCaseUrls
    urls_expire_at: UtcDatetime | None = Field(
        description="null khi display_mode = hidden_unanonymized"
    )
    display_mode: DisplayMode

    @model_validator(mode="after")
    def _check_display(self) -> FailureCaseView:
        hidden = self.display_mode == DisplayMode.HIDDEN_UNANONYMIZED
        if hidden != (self.artifacts is None):
            raise ValueError("artifacts là null khi và chỉ khi display_mode = hidden_unanonymized")
        any_url = any(value is not None for value in self.urls.model_dump().values())
        if hidden and (any_url or self.urls_expire_at is not None):
            raise ValueError("hidden_unanonymized không có URL ảnh nào và không có urls_expire_at")
        if not hidden and (not any_url or self.urls_expire_at is None):
            raise ValueError("display_mode khác hidden_unanonymized phải có URL và urls_expire_at")
        return self


class ComputeTargetPublic(_Model):
    id: UUID
    name: str
    kind: ComputeKind
    gpu_model: str | None = Field(description="null với máy chỉ có CPU")
    online: bool = Field(description="Có heartbeat trong 60 giây gần nhất")
    queue_length: NonNegativeInt = Field(description="Số experiment đang queued trên target")
    default_time_limit_s: PositiveInt
    max_time_limit_s: PositiveInt

    @model_validator(mode="after")
    def _check(self) -> ComputeTargetPublic:
        if self.default_time_limit_s > self.max_time_limit_s:
            raise ValueError("default_time_limit_s không được lớn hơn max_time_limit_s")
        return self


class ModelSummary(_Model):
    id: UUID = Field(description="ID của model version")
    name: str
    framework: str = Field(description="Ví dụ ultralytics; hiển thị ở ô kiến trúc của wizard")
    weights_sha256: Sha256Hex
    class_names: list[str] = Field(min_length=1)
    input_size: PositiveInt
    supports_gradients: bool
    created_at: UtcDatetime
    status: ModelStatus = Field(
        default=ModelStatus.READY,
        description="Phase R2: chỉ model ready được dùng trong experiment và thử nhanh",
    )
    check: ModelCheckResult | None = Field(
        default=None, description="Kết quả job model_check gần nhất; null với model đăng ký qua CLI"
    )


class DatasetVersionSummary(_Model):
    id: UUID
    dataset_id: UUID
    manifest_sha256: Sha256Hex
    num_images: PositiveInt
    class_names: list[str]
    created_at: UtcDatetime


class DatasetSummary(_Model):
    id: UUID
    name: str
    anonymized: bool = Field(description="false: ảnh bị ẩn trên giao diện cho tới Phase 10")
    versions: list[DatasetVersionSummary] = Field(description="Mới nhất trước")

    @model_validator(mode="after")
    def _check(self) -> DatasetSummary:
        if any(version.dataset_id != self.id for version in self.versions):
            raise ValueError("versions[].dataset_id phải bằng id của dataset")
        return self


class SliceSummary(_Model):
    id: UUID
    name: str
    dataset_version_id: UUID
    slice_sha256: Sha256Hex | None
    size: PositiveInt
    seed: NonNegativeInt
    classes: list[str] = Field(description="Class gốc được tính (filter.classes)")


class ClassMappingSummary(_Model):
    id: UUID
    dataset_version_id: UUID
    model_version_id: UUID
    mapping_sha256: Sha256Hex
    preset: str | None
    classes: dict[str, str | None] = Field(description="Class gốc → class model; null là bỏ")


class ProtocolSummary(_Model):
    id: UUID
    name: str
    version: PositiveInt
    status: ProtocolStatus
    body_sha256: Sha256Hex


# ---------------------------------------------------------------- Attack catalog cho admin


class AttackSpecMetadata(_Model):
    """Thông tin hiển thị của spec, nằm ngoài `spec_sha256` (tech-stack.md mục 9, luật 9); sửa
    không đổi version (Phase R2)."""

    display_name: Name
    description: LongText
    realism: Literal["low", "medium", "high"] = Field(description="Mức sát thực tế")
    level_labels: dict[str, Name] = Field(
        default_factory=dict,
        description="Level (số viết dạng chuỗi, so khớp theo giá trị số) → nhãn dễ đọc",
    )

    @model_validator(mode="after")
    def _check_levels(self) -> AttackSpecMetadata:
        values: set[float] = set()
        for key in self.level_labels:
            try:
                value = float(key)
            except ValueError:
                raise ValueError(f"level_labels: khóa {key!r} không phải số") from None
            if not math.isfinite(value):
                raise ValueError(f"level_labels: khóa {key!r} không hữu hạn")
            if value in values:
                raise ValueError(f"level_labels: level {key!r} bị trùng")
            values.add(value)
        return self

    def label_for(self, level: float) -> str | None:
        """Nhãn của level (so theo giá trị số), None khi không khai báo."""
        for key, label in self.level_labels.items():
            if float(key) == level:
                return label
        return None


class SpecCheckItem(_Model):
    name: SpecCheckName
    passed: bool
    details: str | None = Field(
        default=None, description="Lý do khi fail; lý do bỏ qua khi passed mà không áp dụng"
    )

    @model_validator(mode="after")
    def _check(self) -> SpecCheckItem:
        if not self.passed and not self.details:
            raise ValueError("details bắt buộc khi passed = false")
        return self


class SpecCheckResult(_Model):
    """Kết quả job spec_check (`attacks/selfcheck.py`, requirements.md Phase R2).

    `items` theo thứ tự `SpecCheckName`; quá giờ hoặc lỗi giữa chừng thì có thể thiếu mục, khi đó
    `error` ghi lý do và `passed = false`.
    """

    spec_id: UUID
    items: list[SpecCheckItem]
    passed: bool
    error: str | None = Field(default=None, description="Quá 120 giây hoặc lỗi ngoài các mục")
    checked_at: UtcDatetime
    worker_target_id: UUID = Field(description="Compute target của worker đã chạy kiểm tra")

    @model_validator(mode="after")
    def _check(self) -> SpecCheckResult:
        names = [item.name for item in self.items]
        expected = list(SpecCheckName)[: len(names)]
        if names != expected:
            raise ValueError("items phải theo thứ tự SpecCheckName, không trùng")
        complete = len(names) == len(SpecCheckName) and self.error is None
        if self.passed != (complete and all(item.passed for item in self.items)):
            raise ValueError(
                "passed = true khi và chỉ khi đủ 7 mục, mọi mục pass và không có error"
            )
        return self


class AttackSpecView(AttackSpec):
    """`GET /attack-specs` (Phase R2): spec `active` kèm metadata."""

    metadata: AttackSpecMetadata | None = Field(
        description="null khi chưa khai (spec seed trước R2)"
    )


class AttackSpecAdminView(AttackSpec):
    """Spec trong trang `/admin/attacks`: mọi version, kể cả spec đã tắt."""

    is_active: bool = Field(description="Suy ra: status = active")
    status: AttackSpecStatus
    metadata: AttackSpecMetadata | None = Field(description="null khi chưa khai (spec seed)")
    check: SpecCheckResult | None = Field(description="Kết quả spec_check gần nhất")
    created_by: UserRef | None = Field(description="null với spec seed")
    approved_by: UserRef | None = Field(description="null khi chưa duyệt hoặc spec seed")

    @model_validator(mode="after")
    def _check_status(self) -> AttackSpecAdminView:
        if self.is_active != (self.status == AttackSpecStatus.ACTIVE):
            raise ValueError("is_active phải bằng (status == active)")
        return self


class AttackSpecAdminPage(Page[AttackSpecAdminView]):
    pass


# ---------------------------------------------------------------- Phase 8: protocol, review, report

ProtocolName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

_WAITING_REVIEW = ExperimentStatus.SUBMITTED_FOR_REVIEW
_OPEN_REVIEW = frozenset({ExperimentStatus.SUBMITTED_FOR_REVIEW, ExperimentStatus.IN_REVIEW})
_REVIEW_DECISION_STATUS: dict[ReviewDecision | None, ExperimentStatus] = {
    ReviewDecision.APPROVE: ExperimentStatus.APPROVED,
    ReviewDecision.CHANGES_REQUESTED: ExperimentStatus.CHANGES_REQUESTED,
    ReviewDecision.REJECT: ExperimentStatus.REJECTED,
}
_REVIEW_STATUSES = _OPEN_REVIEW | frozenset(_REVIEW_DECISION_STATUS.values())


def _require_content(body: ProtocolBody) -> ProtocolBody:
    if not body.required_attacks:
        raise ValueError("protocol cần ít nhất một attack bắt buộc")
    if not body.pass_criteria:
        raise ValueError("protocol cần ít nhất một tiêu chí đạt")
    return body


class ProtocolCreate(_Model):
    """`POST /protocols`: tạo protocol `active` version 1."""

    name: ProtocolName
    body: Annotated[ProtocolBody, AfterValidator(_require_content)]


class ProtocolVersionCreate(_Model):
    """`POST /protocols/{id}/versions`: version mới cùng `name`, chỉ tạo từ version mới nhất (409
    nếu không); version cũ chuyển `retired` trong cùng giao dịch (kickoff Group 0)."""

    body: Annotated[ProtocolBody, AfterValidator(_require_content)]


class ProtocolView(_Model):
    id: UUID
    name: str
    version: PositiveInt
    status: ProtocolStatus
    body: ProtocolBody
    body_sha256: Sha256Hex = Field(description="sha256_of(body)")
    created_by: UserRef | None = Field(description="null với protocol dev (dev-open)")
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _check(self) -> ProtocolView:
        if self.body_sha256 != sha256_of(self.body):
            raise ValueError("body_sha256 không khớp nội dung body")
        if (self.created_by is None) != (self.status == ProtocolStatus.DEV):
            raise ValueError("created_by là null khi và chỉ khi status = dev")
        return self


class SubmitForReview(_Model):
    """`POST /experiments/{id}/submit`. Lời giải trình chỉ gửi kèm ở đây (kickoff Phase 8)."""

    note: LongText | None = None
    run_explanations: dict[UUID, LongText] = Field(
        default_factory=dict, description="run_id → lời giải trình"
    )


class RunExplanation(_Model):
    run_id: UUID
    author: UserRef
    text: str = Field(min_length=1)
    created_at: UtcDatetime


class CaseVerdictInput(_Model):
    severity: CaseSeverity
    kind: CaseVerdictKind
    mitigation: LongText | None = Field(
        default=None, description="Bắt buộc khi kind = safety_relevant"
    )

    @model_validator(mode="after")
    def _check(self) -> CaseVerdictInput:
        if self.kind == CaseVerdictKind.SAFETY_RELEVANT and self.mitigation is None:
            raise ValueError("kind = safety_relevant bắt buộc có mitigation")
        return self


class CaseVerdictView(CaseVerdictInput):
    """Một version verdict; version lớn nhất là hiện hành, mọi version được giữ."""

    failure_case_id: UUID
    version: PositiveInt
    reviewer: UserRef
    created_at: UtcDatetime


class CriterionResult(_Model):
    """Kết quả tự động (chỉ tham khảo) của `pass_criteria[index]`."""

    index: NonNegativeInt = Field(description="Chỉ số trong body.pass_criteria của protocol")
    status: CriterionStatus
    value: float | None = Field(
        description="max_drop_at_level: đại lượng tại level; min_breaking_point: điểm gãy (cận"
        " trên bracket); null khi không có"
    )
    detail: str = Field(min_length=1)


class RequiredCase(_Model):
    """Case bắt buộc review: top `cases_to_review_per_attack` theo `severity_score` của mỗi
    attack bắt buộc (cùng điểm theo `image_id`)."""

    failure_case_id: UUID
    run_id: UUID
    attack_spec_name: str
    level: float
    image_id: str = Field(min_length=1)
    severity_score: float = Field(gt=0)
    display_mode: DisplayMode
    current_verdict: CaseVerdictView | None

    @model_validator(mode="after")
    def _check(self) -> RequiredCase:
        verdict = self.current_verdict
        if verdict is not None and verdict.failure_case_id != self.failure_case_id:
            raise ValueError("current_verdict phải thuộc failure case này")
        return self


class ReviewDecisionInput(_Model):
    """`POST /reviews/{experiment_id}/decision`. Thiếu trường nhập → 422 (kickoff Phase 8); thiếu
    `inconclusive_justification` khi có tiêu chí inconclusive cũng 422 (kiểm ở backend)."""

    decision: ReviewDecision
    model_verdict: ModelVerdict | None = Field(default=None, description="Bắt buộc khi approve")
    conclusion: LongText = Field(description="Kết luận; lý do với changes_requested và reject")
    mitigation: LongText | None = Field(default=None, description="Bắt buộc khi approve")
    inconclusive_justification: LongText | None = None

    @model_validator(mode="after")
    def _check(self) -> ReviewDecisionInput:
        if self.decision == ReviewDecision.APPROVE and (
            self.model_verdict is None or self.mitigation is None
        ):
            raise ValueError("approve bắt buộc có model_verdict và mitigation")
        return self


class ReviewCommentCreate(_Model):
    target_type: CommentTargetType
    target_id: UUID = Field(
        description="ID experiment, run hoặc failure case thuộc experiment (422 nếu không thuộc)"
    )
    body: LongText


class ReviewComment(_Model):
    id: UUID
    experiment_id: UUID
    author: UserRef
    body: str = Field(min_length=1)
    target_type: CommentTargetType
    target_id: UUID
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _check(self) -> ReviewComment:
        on_experiment = self.target_type == CommentTargetType.EXPERIMENT
        if on_experiment and self.target_id != self.experiment_id:
            raise ValueError("bình luận gắn experiment phải có target_id = experiment_id")
        return self


class ReviewView(_Model):
    """Trạng thái review của experiment (`ExperimentDetail.review`)."""

    submitted_at: UtcDatetime
    submission_note: str | None
    run_explanations: list[RunExplanation]
    assignee: UserRef | None = Field(description="Người đang nhận hoặc đã quyết định")
    claimed_at: UtcDatetime | None
    decision: ReviewDecision | None
    decided_at: UtcDatetime | None
    model_verdict: ModelVerdict | None
    conclusion: str | None
    mitigation: str | None
    inconclusive_justification: str | None
    criteria_results: list[CriterionResult] = Field(
        description="Khi chưa quyết định: tính tại thời điểm đọc; sau quyết định: bản đã lưu"
    )
    checklist: list[ChecklistItem] = Field(
        description="Điều kiện trạng thái trước khi chấp nhận; sau quyết định: bản đã lưu"
    )
    required_cases: list[RequiredCase]
    comments_count: NonNegativeInt

    @model_validator(mode="after")
    def _check(self) -> ReviewView:
        if (self.assignee is None) != (self.claimed_at is None):
            raise ValueError("assignee và claimed_at cùng null hoặc cùng có giá trị")
        decided = self.decision is not None
        if decided != (self.decided_at is not None) or decided != (self.conclusion is not None):
            raise ValueError("decision, decided_at, conclusion cùng null hoặc cùng có giá trị")
        if decided and self.assignee is None:
            raise ValueError("review đã quyết định phải có assignee")
        if not decided and (
            self.model_verdict is not None
            or self.mitigation is not None
            or self.inconclusive_justification is not None
        ):
            raise ValueError(
                "model_verdict, mitigation, inconclusive_justification chỉ có sau quyết định"
            )
        if self.decision == ReviewDecision.APPROVE and (
            self.model_verdict is None or self.mitigation is None
        ):
            raise ValueError("approve phải có model_verdict và mitigation")
        if len({r.index for r in self.criteria_results}) != len(self.criteria_results):
            raise ValueError("criteria_results không được trùng index")
        ids = [c.failure_case_id for c in self.required_cases]
        if len(set(ids)) != len(ids):
            raise ValueError("required_cases không được trùng")
        return self


class ReviewQueueItem(_Model):
    """Một dòng của hàng đợi `GET /reviews` (không gồm experiment do người gọi tạo)."""

    experiment: ExperimentSummary
    protocol: ProtocolRef
    submitted_at: UtcDatetime
    assignee: UserRef | None
    claimed_at: UtcDatetime | None
    decision: ReviewDecision | None
    decided_at: UtcDatetime | None
    max_relative_drop: float | None = Field(
        description="relative_drop lớn nhất trên run toàn slice có metric; null khi không có"
    )
    required_cases_total: NonNegativeInt
    required_cases_reviewed: NonNegativeInt

    @model_validator(mode="after")
    def _check(self) -> ReviewQueueItem:
        if self.experiment.status not in _REVIEW_STATUSES:
            raise ValueError("hàng đợi chỉ gồm experiment đã gửi duyệt")
        if self.required_cases_reviewed > self.required_cases_total:
            raise ValueError("required_cases_reviewed không được vượt required_cases_total")
        if (self.assignee is None) != (self.claimed_at is None):
            raise ValueError("assignee và claimed_at cùng null hoặc cùng có giá trị")
        if (self.decision is None) != (self.decided_at is None):
            raise ValueError("decision và decided_at cùng null hoặc cùng có giá trị")
        return self


class ReportView(_Model):
    id: UUID
    experiment_id: UUID
    experiment_name: str
    status: ReportStatus
    model_verdict: ModelVerdict
    approved_by: UserRef
    approved_at: UtcDatetime
    generated_at: UtcDatetime | None = Field(description="Có khi và chỉ khi status = ready")
    json_sha256: Sha256Hex | None = Field(description="Có khi và chỉ khi status = ready")
    pdf_sha256: Sha256Hex | None = Field(description="Có khi và chỉ khi status = ready")

    @model_validator(mode="after")
    def _check(self) -> ReportView:
        ready = self.status == ReportStatus.READY
        values = (self.generated_at, self.json_sha256, self.pdf_sha256)
        if any((v is None) == ready for v in values):
            raise ValueError("generated_at, json_sha256, pdf_sha256 có khi và chỉ khi ready")
        return self


class ReportDownload(_Model):
    """`GET /reports/{id}/download?format=`: URL tạm thời tới đúng file đã lưu."""

    format: Literal["pdf", "json"]
    url: Annotated[str, StringConstraints(pattern=r"^/reports/files/[A-Za-z0-9._~-]+$")]
    expires_at: UtcDatetime
    sha256: Sha256Hex = Field(description="json_sha256 hoặc pdf_sha256 của report")
    filename: str = Field(pattern=r"^[A-Za-z0-9._-]+\.(pdf|json)$")


class VerifyInfo(_Model):
    """`GET /verify/{report_id}` (công khai): không có tên người hay nội dung report."""

    report_id: UUID
    issued_at: UtcDatetime
    json_sha256: Sha256Hex
    pdf_sha256: Sha256Hex


# ---------------------------------------------------------------- ReportSnapshot


class ReportNote(_Model):
    code: ReportNoteCode
    text: str = Field(min_length=1)


class ReportSummary(_Model):
    """Mục 1: tóm tắt."""

    experiment_id: UUID
    experiment_name: str
    owner: UserRef
    model_verdict: ModelVerdict
    conclusion: str = Field(min_length=1)
    mitigation: str = Field(min_length=1)
    inconclusive_justification: str | None
    approved_by: UserRef
    approved_at: UtcDatetime

    @model_validator(mode="after")
    def _check(self) -> ReportSummary:
        if self.approved_by.id == self.owner.id:
            raise ValueError("người duyệt không được là người tạo experiment")
        return self


class ReportProtocol(_Model):
    id: UUID
    name: str
    version: PositiveInt
    body_sha256: Sha256Hex
    body: ProtocolBody

    @model_validator(mode="after")
    def _check(self) -> ReportProtocol:
        if self.body_sha256 != sha256_of(self.body):
            raise ValueError("body_sha256 không khớp nội dung body")
        return self


class ReportModel(_Model):
    id: UUID = Field(description="ID của model version")
    name: str
    weights_sha256: Sha256Hex


class ReportDatasetVersion(_Model):
    id: UUID
    dataset_name: str
    manifest_sha256: Sha256Hex
    anonymized: bool


class ReportSlice(_Model):
    id: UUID
    name: str
    slice_sha256: Sha256Hex | None
    size: PositiveInt


class ReportClassMapping(_Model):
    id: UUID
    mapping_sha256: Sha256Hex
    excluded_classes: list[str] = Field(description="Class gốc bị loại khỏi metric")


class ReportAttackSpec(_Model):
    id: UUID
    name: str
    version: PositiveInt
    kind: AttackKind
    spec_sha256: Sha256Hex
    param_name: str
    param_unit: str
    requires_training: bool = Field(description="Patch (Phase 6): cần note patch_fixed_position")
    required: bool = Field(description="Là attack bắt buộc của protocol")


class ReportConfiguration(_Model):
    """Mục 3: cấu hình."""

    protocol: ReportProtocol
    model: ReportModel
    dataset_version: ReportDatasetVersion
    slice: ReportSlice
    class_mapping: ReportClassMapping
    attack_specs: list[ReportAttackSpec] = Field(min_length=1)
    compute_target: ComputeTargetRef
    gpu_model: str | None = Field(description="null khi chạy trên CPU")
    config_sha256: Sha256Hex


class ReportGridPoint(_Model):
    level: float
    run_id: UUID
    status: RunStatus
    map50: UnitFloat | None = Field(description="mAP@0.5 sau tấn công; null khi không có metric")
    relative_drop: float | None
    attack_success_rate: UnitFloat | None
    early_stop_from_run_id: UUID | None = Field(
        description="Run kích hoạt dừng sớm khi level bị skipped do early_stop"
    )


class ReportGridAttack(_Model):
    attack_spec_id: UUID
    attack_spec_name: str
    points: list[ReportGridPoint] = Field(description="Theo level tăng dần; chỉ run toàn slice")


class ReportResults(_Model):
    """Mục 4: kết quả."""

    clean_metrics: MapPair | None
    grid: list[ReportGridAttack]
    attack_ranking: list[AttackRankingEntry]
    searches: list[SearchResult] = Field(description="Kết quả cuối của từng attack tìm ngưỡng")
    criteria: list[CriterionResult] = Field(
        description="Theo thứ tự configuration.protocol.body.pass_criteria"
    )


class ReportRun(_Model):
    """Mục 5: mọi run, kể cả failed, skipped, stopped_limit, cancelled và run tập con."""

    run_id: UUID
    attack_spec_id: UUID
    attack_spec_name: str
    level: float
    scope: EvalScope
    search_order: NonNegativeInt | None
    status: RunStatus
    status_reason: StatusReason | None
    metrics: RunMetrics | None
    processing_seconds: Seconds
    explanation: str | None = Field(description="Lời giải trình khi gửi duyệt")


class ReportCase(_Model):
    """Mục 6: failure case đã review (chỉ case đã làm mờ)."""

    failure_case_id: UUID
    run_id: UUID
    attack_spec_name: str
    level: float
    image_id: str = Field(min_length=1)
    severity_score: float = Field(gt=0)
    lost_objects: NonNegativeInt
    new_false_positives: NonNegativeInt
    required: bool = Field(description="Là case bắt buộc review")
    anonymization: CaseAnonymization
    thumbnail_key: ObjectKey = Field(description="Thumbnail ảnh sau tấn công đã làm mờ")
    verdict: CaseVerdictView

    @model_validator(mode="after")
    def _check(self) -> ReportCase:
        if not self.anonymization.applied:
            raise ValueError("report chỉ chứa case đã làm mờ (anonymization.applied)")
        if self.verdict.failure_case_id != self.failure_case_id:
            raise ValueError("verdict phải thuộc failure case này")
        return self


class ReportRelatedExperiment(_Model):
    id: UUID
    name: str
    status: ExperimentStatus
    owner: UserRef
    protocol: ProtocolRef
    protocol_version: PositiveInt
    dev: bool = Field(description="Gắn protocol dev (dev-open)")
    created_at: UtcDatetime


class ReportTimelineEvent(_Model):
    action: Literal["experiment.submitted", "review.claimed", "review.released", "review.decided"]
    actor: UserRef
    at: UtcDatetime


class ReportHistory(_Model):
    """Mục 7: experiment khác cùng model version và dataset version, gắn protocol này (mọi
    version) hoặc protocol dev, tạo trước thời điểm duyệt; timeline review."""

    related_experiments: list[ReportRelatedExperiment]
    timeline: list[ReportTimelineEvent] = Field(min_length=1, description="Theo thời gian")
    comments_count: NonNegativeInt


class ReportReproRun(_Model):
    """Mục 8: tái lập; các trường null khi run chưa bắt đầu (không có manifest)."""

    run_id: UUID
    fingerprint: Sha256Hex | None
    git_commit: GitCommit | None
    git_dirty: bool | None
    lib_versions: LibVersions | None
    docker_image_digest: DockerDigest | None
    cached_from_run_id: UUID | None


class ReportResources(_Model):
    """Mục 9: tài nguyên (Phase 8 chỉ ghi thời gian xử lý; tiền ở Phase 9)."""

    processing_seconds_used: Seconds
    limit: Limit


_MANDATORY_NOTES = frozenset({ReportNoteCode.TEST_ENVIRONMENT_ONLY, ReportNoteCode.INPUT_SPACE})


class ReportSnapshot(_Model):
    """Toàn bộ nội dung report; file JSON là `canonical_json` của snapshot, `json_sha256` là
    sha256 của file đó."""

    schema_version: Literal[1] = 1
    report_id: UUID
    summary: ReportSummary
    notes: list[ReportNote] = Field(description="Mục 2: phạm vi và lưu ý bắt buộc")
    configuration: ReportConfiguration
    results: ReportResults
    runs: list[ReportRun] = Field(min_length=1)
    reviewed_cases: list[ReportCase]
    history: ReportHistory
    reproducibility: list[ReportReproRun]
    resources: ReportResources

    @model_validator(mode="after")
    def _check(self) -> ReportSnapshot:
        codes = [note.code for note in self.notes]
        if len(set(codes)) != len(codes):
            raise ValueError("notes không được trùng code")
        if not set(codes) >= _MANDATORY_NOTES:
            raise ValueError("notes thiếu lưu ý bắt buộc (test_environment_only, input_space)")
        specs = self.configuration.attack_specs
        conditional = {
            ReportNoteCode.ANONYMIZATION: bool(self.reviewed_cases),
            ReportNoteCode.OCCLUSION_STRESS: any(s.kind == AttackKind.OCCLUSION for s in specs),
            ReportNoteCode.PATCH_FIXED_POSITION: any(s.requires_training for s in specs),
            ReportNoteCode.EXCLUDED_CLASSES: bool(
                self.configuration.class_mapping.excluded_classes
            ),
        }
        missing = [
            code.value for code, needed in conditional.items() if needed and code not in codes
        ]
        if missing:
            raise ValueError(f"notes thiếu lưu ý bắt buộc theo nội dung report: {missing}")
        run_ids = [r.run_id for r in self.runs]
        if len(set(run_ids)) != len(run_ids):
            raise ValueError("runs không được trùng")
        if [r.run_id for r in self.reproducibility] != run_ids:
            raise ValueError("reproducibility phải theo đúng thứ tự runs")
        if any(c.run_id not in set(run_ids) for c in self.reviewed_cases):
            raise ValueError("reviewed_cases phải thuộc runs của report")
        criteria = self.configuration.protocol.body.pass_criteria
        if [c.index for c in self.results.criteria] != list(range(len(criteria))):
            raise ValueError("results.criteria phải đủ và theo thứ tự pass_criteria")
        dirty = any(r.git_dirty for r in self.reproducibility)
        if dirty != (ReportNoteCode.GIT_DIRTY in codes):
            raise ValueError("note git_dirty có khi và chỉ khi có run git_dirty")
        if dirty and self.configuration.protocol.body.forbid_dirty_runs:
            raise ValueError("protocol forbid_dirty_runs không cho run git_dirty")
        return self


class ReportDetail(_Model):
    """`GET /reports/{id}`: xem report trong ứng dụng (không có URL tải)."""

    report: ReportView
    snapshot: ReportSnapshot | None = Field(description="Có khi và chỉ khi status = ready")

    @model_validator(mode="after")
    def _check(self) -> ReportDetail:
        if (self.snapshot is not None) != (self.report.status == ReportStatus.READY):
            raise ValueError("snapshot có khi và chỉ khi report ready")
        if self.snapshot is not None and self.snapshot.report_id != self.report.id:
            raise ValueError("snapshot.report_id phải bằng report.id")
        return self


# ---------------------------------------------------------------- Phase R2: catalog, model qua web

# Danh sách kiến trúc torchvision cho phép (requirements.md Phase R2, Decisions).
TORCHVISION_ARCHITECTURES: tuple[str, ...] = (
    "fasterrcnn_resnet50_fpn_v2",
    "retinanet_resnet50_fpn_v2",
    "fcos_resnet50_fpn",
)
# Giới hạn upload model qua web (Decisions): 500 MB.
MODEL_UPLOAD_MAX_BYTES = 500 * 1024 * 1024


class AttackSpecCreate(_Model):
    """`POST /admin/attack-specs`: name mới (version 1) hoặc name có sẵn (version lớn nhất + 1).
    Server tính `id`, `spec_sha256`; spec mới ở `draft` rồi chuyển `checking`."""

    body: AttackSpecBody
    metadata: AttackSpecMetadata


class AttackSpecReject(_Model):
    """`POST /attack-specs/{id}/reject`: `pending_approval` → `draft`."""

    reason: Reason


class AttackAdapterInfo(_Model):
    """`GET /attack-adapters`: adapter có trong registry của worker."""

    name: AdapterName
    kind: AttackKind
    params_schema: dict[str, JsonValue] = Field(
        description="JSON Schema của fixed_params (draft 2020-12)"
    )
    requires_gradients: bool


class ModelCheckResult(_Model):
    """Kết quả job model_check: nạp model, so sha256, inference trên fixture, số class, kiểm
    gradient (chỉ torchvision)."""

    passed: bool
    details: str | None = Field(default=None, description="Lý do khi passed = false")
    gradient_check: GradientCheck | None = Field(
        description="null với onnx (không hỗ trợ gradient) hoặc khi dừng trước bước này"
    )
    checked_at: UtcDatetime
    worker_target_id: UUID

    @model_validator(mode="after")
    def _check(self) -> ModelCheckResult:
        if not self.passed and not self.details:
            raise ValueError("details bắt buộc khi passed = false")
        return self


class ModelUploadCreate(_Model):
    """`POST /models/uploads`: chỉ `.onnx` hoặc `.safetensors`, tối đa 500 MB (mission.md nguyên
    tắc 10). Nội dung được kiểm tra lại khi `POST /models`."""

    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\]+\.(onnx|safetensors)$")
    size_bytes: PositiveInt = Field(le=MODEL_UPLOAD_MAX_BYTES)


class ModelUpload(_Model):
    upload_id: UUID
    url: PresignedUrl = Field(description="Presigned PUT")
    expires_at: UtcDatetime


class ModelRegister(_Model):
    """`POST /models`: tạo model version `checking`, id = content_id(weights_sha256); trùng sha →
    409; xếp job model_check."""

    name: Name
    framework: Literal["torchvision", "onnx"]
    architecture: str = Field(
        min_length=1,
        max_length=200,
        description="torchvision: một trong TORCHVISION_ARCHITECTURES; onnx: mô tả tự do",
    )
    upload_id: UUID
    class_names: list[str] = Field(min_length=1, description="Theo thứ tự index của model")
    input_size: PositiveInt

    @model_validator(mode="after")
    def _check(self) -> ModelRegister:
        if self.framework == "torchvision" and self.architecture not in TORCHVISION_ARCHITECTURES:
            raise ValueError(
                "architecture torchvision phải là một trong " + ", ".join(TORCHVISION_ARCHITECTURES)
            )
        if len(set(self.class_names)) != len(self.class_names):
            raise ValueError("class_names không được trùng")
        if any(not name for name in self.class_names):
            raise ValueError("class_names không được rỗng")
        return self


# ---------------------------------------------------------------- Phase R2: insight

# Ngưỡng cố định (requirements.md Phase R2, Decisions), không phải tham số của người dùng.
WEAKNESS_DROP = 0.3
WEAKNESS_VISIBLE_DROP = 0.1
MAX_WEAKNESSES = 5
# Dải level_ratio của ma trận độ bền: (0, .25], (.25, .5], (.5, .75], (.75, 1].
ROBUSTNESS_BANDS: tuple[tuple[float, float], ...] = (
    (0.0, 0.25),
    (0.25, 0.5),
    (0.5, 0.75),
    (0.75, 1.0),
)


class Weakness(_Model):
    """Một điểm yếu (requirements.md Phase R2, Behaviour Insight)."""

    attack_spec_id: UUID
    attack_name: str = Field(min_length=1)
    kind: Literal["grid", "search"]
    level: float
    level_ratio: UnitFloat = Field(description="level / primary_param.max")
    level_label: str | None = Field(description="Nhãn từ metadata của spec; null khi không có")
    relative_drop: float | None = Field(description="grid: mức sụt mAP@0.5 tương đối tại level")
    breaking_point: float | None = Field(description="search: điểm gãy found")
    class_name: str | None = Field(
        description="Class sụt AP50 tương đối nhiều nhất tại level; null khi không xác định"
    )
    class_relative_drop: float | None = Field(
        description="Mức sụt AP50 tương đối của class_name; null khi class_name null"
    )

    @model_validator(mode="after")
    def _check(self) -> Weakness:
        if self.kind == "grid" and (self.relative_drop is None or self.breaking_point is not None):
            raise ValueError("grid cần relative_drop và không có breaking_point")
        if self.kind == "search" and self.breaking_point is None:
            raise ValueError("search cần breaking_point")
        if (self.class_name is None) != (self.class_relative_drop is None):
            raise ValueError("class_relative_drop có khi và chỉ khi có class_name")
        return self


class RobustnessCell(_Model):
    band: int = Field(ge=0, lt=len(ROBUSTNESS_BANDS), description="Chỉ số trong bands")
    max_relative_drop: float | None = Field(description="null khi dải không có run có metric")
    runs: NonNegativeInt

    @model_validator(mode="after")
    def _check(self) -> RobustnessCell:
        if (self.max_relative_drop is None) != (self.runs == 0):
            raise ValueError("max_relative_drop là null khi và chỉ khi runs = 0")
        return self


class RobustnessRow(_Model):
    attack_spec_id: UUID
    attack_name: str = Field(min_length=1)
    cells: list[RobustnessCell]

    @model_validator(mode="after")
    def _check(self) -> RobustnessRow:
        if [c.band for c in self.cells] != list(range(len(ROBUSTNESS_BANDS))):
            raise ValueError("cells phải đủ 4 dải theo thứ tự")
        return self


class Conclusion(_Model):
    """Câu kết luận sinh theo luật (`backend/app/insight/phrases.py`)."""

    code: ConclusionCode
    params: dict[str, JsonValue] = Field(description="Số liệu dùng dựng câu")
    text: str = Field(min_length=1, description="Tiếng Việt; cùng đầu vào cho cùng câu")


class ExperimentInsight(_Model):
    """`GET /experiments/{id}/insight`."""

    experiment_id: UUID
    mode: ExperimentMode
    weaknesses: list[Weakness] = Field(max_length=MAX_WEAKNESSES)
    matrix: list[RobustnessRow] = Field(description="Mỗi attack quét lưới một hàng")
    bands: list[tuple[float, float]] = Field(description="(lo, hi], theo ROBUSTNESS_BANDS")
    conclusion: Conclusion
    partial: bool = Field(description="Có run stopped_limit hoặc experiment chưa kết thúc")

    @model_validator(mode="after")
    def _check(self) -> ExperimentInsight:
        if tuple(self.bands) != ROBUSTNESS_BANDS:
            raise ValueError("bands phải bằng ROBUSTNESS_BANDS")
        if (self.conclusion.code == ConclusionCode.ROBUST) != (
            not self.weaknesses and self.conclusion.code != ConclusionCode.NO_DATA
        ):
            raise ValueError("code robust khi và chỉ khi có dữ liệu mà không có điểm yếu")
        if self.conclusion.code in (ConclusionCode.WEAK, ConclusionCode.WEAK_CLASS) and (
            not self.weaknesses
        ):
            raise ValueError("code weak, weak_class cần ít nhất một điểm yếu")
        return self


# ---------------------------------------------------------------- Phase R2: template và preset


class TemplateGrid(_Model):
    level_ratios: list[UnitFloat] = Field(
        min_length=1, description="Tỷ lệ trên [min, max] của primary_param; level bắt buộc"
    )


class TemplateSearch(_Model):
    threshold_kind: ThresholdKind
    threshold: float = Field(gt=0, le=1)
    lo_ratio: UnitFloat
    hi_ratio: UnitFloat
    max_tol_ratio: float = Field(gt=0, le=1, description="max_tol = max_tol_ratio · (hi - lo)")

    @model_validator(mode="after")
    def _check(self) -> TemplateSearch:
        if self.lo_ratio >= self.hi_ratio:
            raise ValueError("lo_ratio phải nhỏ hơn hi_ratio")
        return self


class TemplateAttack(_Model):
    attack_spec_name: AttackSpecName
    mode: RunMode
    grid: TemplateGrid | None = None
    search: TemplateSearch | None = None

    @model_validator(mode="after")
    def _check(self) -> TemplateAttack:
        if self.mode == RunMode.GRID and (self.grid is None or self.search is not None):
            raise ValueError("mode = grid cần grid và không có search")
        if self.mode == RunMode.SEARCH and (self.search is None or self.grid is not None):
            raise ValueError("mode = search cần search và không có grid")
        return self


# Ngưỡng max_drop_at_level gợi ý theo strictness (requirements.md Phase R2).
STRICTNESS_MAX_DROP: dict[str, float] = {"lenient": 0.5, "standard": 0.3, "strict": 0.15}


class ProtocolTemplate(_Model):
    """Một template trong `contracts/seeds/protocol_templates.json`; không bao giờ tự tạo
    protocol (`GET /protocol-templates/{key}/draft` trả `ProtocolCreate`)."""

    key: Literal["quick", "front_camera", "weather", "full"]
    title: Name
    description: LongText
    attacks: list[TemplateAttack] = Field(min_length=1)
    strictness: Literal["lenient", "standard", "strict"]
    min_slice_size: PositiveInt

    @model_validator(mode="after")
    def _check(self) -> ProtocolTemplate:
        names = [a.attack_spec_name for a in self.attacks]
        if len(set(names)) != len(names):
            raise ValueError("attacks không được trùng attack_spec_name")
        return self


class PresetSearch(_Model):
    """Tìm ngưỡng mà preset thêm vào (deep); dải [lo, hi] là [min, max] của spec, tol theo wizard
    (hi - lo) / 256."""

    threshold_kind: ThresholdKind
    threshold: float = Field(gt=0, le=1)
    subset_size: int = Field(ge=2)


class ExperimentPreset(_Model):
    """Một preset trong `contracts/seeds/experiment_presets.json`."""

    key: Literal["fast", "standard", "deep"]
    title: Name
    description: LongText
    level_ratios: list[UnitFloat] = Field(min_length=1, description="Tỷ lệ trên [min, max]")
    use_search: bool = Field(description="Thêm tìm ngưỡng với attack hỗ trợ (không áp cho patch)")
    search: PresetSearch | None = Field(default=None, description="Có khi và chỉ khi use_search")

    @model_validator(mode="after")
    def _check(self) -> ExperimentPreset:
        if self.use_search != (self.search is not None):
            raise ValueError("search có khi và chỉ khi use_search = true")
        if len(set(self.level_ratios)) != len(self.level_ratios):
            raise ValueError("level_ratios không được trùng")
        return self


PresetKey = Literal["fast", "standard", "deep"]


class ExperimentDraftRequest(_Model):
    """`POST /experiments/draft`: dựng `ExperimentCreate` từ protocol và preset, trả
    `ExperimentClone`; không tạo experiment."""

    protocol_id: UUID
    preset: PresetKey
    model_version_id: UUID
    slice_id: UUID
    class_mapping_id: UUID
    compute_target_id: UUID
    limit: Limit
    attack_spec_ids: list[UUID] | None = Field(
        default=None,
        description="Chỉ với protocol dev; null là toàn bộ catalog active",
    )


class PromoteRequest(_Model):
    """`POST /experiments/{id}/promote`: trả `ExperimentClone`, không tạo experiment."""

    protocol_id: UUID


# ---------------------------------------------------------------- Phase R2: thử nhanh

QUICK_TRY_MAX_IMAGE_BYTES = 10 * 1024 * 1024
QUICK_TRY_MAX_SIDE = 4096


class QuickTryCreate(_Model):
    """Các field form của `POST /quick-tries` (multipart, cộng file `image` là ảnh JPEG/PNG
    ≤ 10 MB, cạnh dài ≤ 4096 px)."""

    model_version_id: UUID
    attack_spec_id: UUID
    preset: PresetKey = "standard"


class QuickTryObject(_Model):
    """Một object, ghép theo IoU ≥ 0.5 cùng class giữa ảnh sạch và ảnh bị tấn công."""

    bbox: PixelBBox = Field(description="xyxy letterbox; object new lấy box trên ảnh bị tấn công")
    class_name: str = Field(min_length=1)
    clean_score: UnitFloat | None = Field(description="null khi status = new")
    attacked_score: UnitFloat | None = Field(description="null khi status = lost")
    status: QuickTryObjectStatus

    @model_validator(mode="after")
    def _check(self) -> QuickTryObject:
        if (self.clean_score is None) != (self.status == QuickTryObjectStatus.NEW):
            raise ValueError("clean_score là null khi và chỉ khi status = new")
        if (self.attacked_score is None) != (self.status == QuickTryObjectStatus.LOST):
            raise ValueError("attacked_score là null khi và chỉ khi status = lost")
        return self


class QuickTryLevel(_Model):
    level: float
    label: str | None = Field(description="Nhãn từ metadata của spec")
    image_url: ArtifactUrl = Field(description="Ảnh bị tấn công, đã làm mờ (như ảnh failure case)")
    objects: list[QuickTryObject]


class QuickTryView(_Model):
    """`POST /quick-tries` (202) và `GET /quick-tries/{id}`; hết hạn thì `GET` trả 410."""

    id: UUID
    status: ToolJobStatus
    not_a_test_result: Literal[True] = Field(
        default=True, description="Luôn true: không phải kết quả kiểm thử"
    )
    model_version_id: UUID
    attack_spec_id: UUID
    preset: PresetKey
    clean_image_url: ArtifactUrl | None = Field(
        description="Ảnh sạch đã letterbox và làm mờ; có khi và chỉ khi completed. Ảnh gốc chưa"
        " làm mờ không bao giờ được phục vụ qua API"
    )
    levels: list[QuickTryLevel] = Field(description="Rỗng khi chưa completed")
    created_at: UtcDatetime
    expires_at: UtcDatetime
    error: str | None = Field(description="Có khi và chỉ khi failed")

    @model_validator(mode="after")
    def _check(self) -> QuickTryView:
        done = self.status == ToolJobStatus.COMPLETED
        if (self.clean_image_url is not None) != done:
            raise ValueError("clean_image_url có khi và chỉ khi completed")
        if done != bool(self.levels):
            raise ValueError("levels không rỗng khi và chỉ khi completed")
        if (self.error is not None) != (self.status == ToolJobStatus.FAILED):
            raise ValueError("error có khi và chỉ khi failed")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at phải sau created_at")
        return self


# ---------------------------------------------------------------- Phase R2: job công cụ (worker)


class ToolLease(_Model):
    """Trả về từ `POST /internal/worker/tool-lease` (không có job thì `204`)."""

    schema_version: Literal[1] = 1
    kind: ToolJobKind
    job_id: UUID
    lease_id: UUID = Field(description="Đổi mỗi lần lease; gửi kèm mọi request sau đó")
    lease_expires_at: UtcDatetime


class ToolModel(_Model):
    """Model cần nạp cho job công cụ (presigned GET cho weights)."""

    model_version_id: UUID
    framework: Literal["ultralytics", "torchvision", "onnx"]
    architecture: str = Field(min_length=1)
    weights_sha256: Sha256Hex
    class_names: list[str] = Field(min_length=1)
    input_size: PositiveInt
    weights_url: PresignedUrl


class SpecCheckPayload(_Model):
    kind: Literal[ToolJobKind.SPEC_CHECK] = ToolJobKind.SPEC_CHECK
    spec: AttackSpec


class ModelCheckPayload(_Model):
    kind: Literal[ToolJobKind.MODEL_CHECK] = ToolJobKind.MODEL_CHECK
    model: ToolModel


class QuickTryPayload(_Model):
    kind: Literal[ToolJobKind.QUICK_TRY] = ToolJobKind.QUICK_TRY
    quick_try_id: UUID
    model: ToolModel
    spec: AttackSpec
    levels: list[float] = Field(min_length=1)
    image_url: PresignedUrl = Field(description="Ảnh gốc (chưa làm mờ)")
    clean_upload_url: PresignedUrl = Field(description="PUT ảnh sạch đã letterbox và làm mờ")
    level_upload_urls: list[PresignedUrl] = Field(
        description="PUT ảnh bị tấn công đã làm mờ, cùng thứ tự levels"
    )

    @model_validator(mode="after")
    def _check(self) -> QuickTryPayload:
        if len(self.level_upload_urls) != len(self.levels):
            raise ValueError("level_upload_urls phải cùng độ dài levels")
        return self


ToolPayload = Annotated[
    SpecCheckPayload | ModelCheckPayload | QuickTryPayload, Field(discriminator="kind")
]


class ToolJobBundle(_Model):
    """`GET /internal/worker/tool-jobs/{id}`; presigned URL hết hạn sau 15 phút."""

    schema_version: Literal[1] = 1
    job_id: UUID
    payload: ToolPayload
    expires_at: UtcDatetime


class ToolHeartbeat(_Model):
    lease_id: UUID


class QuickTryLevelReport(_Model):
    level: float
    objects: list[QuickTryObject]


class SpecCheckReport(_Model):
    kind: Literal[ToolJobKind.SPEC_CHECK] = ToolJobKind.SPEC_CHECK
    result: SpecCheckResult


class ModelCheckReport(_Model):
    kind: Literal[ToolJobKind.MODEL_CHECK] = ToolJobKind.MODEL_CHECK
    result: ModelCheckResult


class QuickTryReport(_Model):
    """Ảnh đã PUT lên các URL trong payload trước khi gửi report."""

    kind: Literal[ToolJobKind.QUICK_TRY] = ToolJobKind.QUICK_TRY
    levels: list[QuickTryLevelReport] = Field(min_length=1)


ToolReport = Annotated[
    SpecCheckReport | ModelCheckReport | QuickTryReport, Field(discriminator="kind")
]


class ToolJobResult(_Model):
    """`POST /internal/worker/tool-jobs/{id}/result`: đúng một trong `report` hoặc `error`.

    `error` là lỗi hạ tầng (không nạp được tài nguyên, ngoại lệ); kiểm tra fail vẫn gửi `report`
    với `passed = false`.
    """

    lease_id: UUID
    report: ToolReport | None = None
    error: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _check(self) -> ToolJobResult:
        if (self.report is None) == (self.error is None):
            raise ValueError("cần đúng một trong report hoặc error")
        return self


ExperimentDetail.model_rebuild()
ModelSummary.model_rebuild()
