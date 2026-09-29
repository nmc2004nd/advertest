"""Model ORM cho toàn bộ bảng của Phase 0 (requirements.md mục "DB schema").

Migration trong backend/migrations/ là nguồn sự thật của DB; test `alembic check` bảo đảm
model ở đây không lệch với migration.
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Double,
    Enum,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from advertest_contracts.enums import (
    AttackAccess,
    AttackKind,
    BillingMode,
    CaseSeverity,
    ComputeKind,
    ExperimentStatus,
    LimitKind,
    ProtocolStatus,
    ReviewDecision,
    Role,
    RunStatus,
    UserStatus,
)

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Money = Numeric(18, 6)
Sha256 = String(64)
Currency = String(3)


class LedgerKind(enum.StrEnum):
    RESERVE = "reserve"
    SETTLE = "settle"
    RELEASE = "release"


def pg_enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    """Enum Postgres lưu giá trị chuỗi của enum (không phải tên thành viên)."""
    return Enum(enum_cls, name=name, values_callable=lambda cls: [m.value for m in cls])


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    # Thời gian luôn là timestamptz (UTC); số thực là double precision.
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        float: Double(),
    }


def _uuid_pk() -> Mapped[UUID]:
    return mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))


def _created_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, unique=True)
    full_name: Mapped[str] = mapped_column(Text)
    organization: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, "user_status"), server_default=UserStatus.PENDING.value
    )
    requested_role: Mapped[Role | None] = mapped_column(pg_enum(Role, "role"))
    request_reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created_at()
    # Phase 4: lý do từ chối, thời điểm vô hiệu hóa.
    reject_reason: Mapped[str | None] = mapped_column(Text)
    disabled_at: Mapped[datetime | None]


class AuthEventKind(enum.StrEnum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"


class UserSession(Base):
    """Phiên đăng nhập phía server (Phase 4). Chỉ lưu sha256 của token trong cookie."""

    __tablename__ = "sessions"

    id: Mapped[UUID] = _uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_sha256: Mapped[str] = mapped_column(Sha256, unique=True)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(Text)


class PasswordResetToken(Base):
    """Token đặt lại mật khẩu do admin tạo (Phase 4); dùng một lần."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[UUID] = _uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_sha256: Mapped[str] = mapped_column(Sha256, unique=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class AuthEvent(Base):
    """Sự kiện đăng nhập, đăng xuất (Phase 4); chỉ thêm, tách khỏi audit_log."""

    __tablename__ = "auth_events"

    id: Mapped[UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, index=True)
    ip: Mapped[str | None] = mapped_column(Text, index=True)
    kind: Mapped[AuthEventKind] = mapped_column(pg_enum(AuthEventKind, "auth_event_kind"))
    created_at: Mapped[datetime] = mapped_column(index=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[Role] = mapped_column(pg_enum(Role, "role"), primary_key=True)


class ComputeTarget(Base):
    __tablename__ = "compute_targets"
    __table_args__ = (
        CheckConstraint(
            "billing_mode = 'none' OR (price_per_hour IS NOT NULL AND currency IS NOT NULL)",
            name="hourly_needs_price",
        ),
        CheckConstraint("default_time_limit_s <= max_time_limit_s", name="default_within_max"),
    )

    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[ComputeKind] = mapped_column(pg_enum(ComputeKind, "compute_kind"))
    gpu_model: Mapped[str | None] = mapped_column(Text)
    vram_gb: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    billing_mode: Mapped[BillingMode] = mapped_column(pg_enum(BillingMode, "billing_mode"))
    price_per_hour: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str | None] = mapped_column(Currency)
    token_hash: Mapped[str | None] = mapped_column(Text)
    # tech-stack.md mục 4.2: trần thời gian mặc định 2 giờ cho máy local.
    default_time_limit_s: Mapped[int] = mapped_column(Integer, server_default=text("7200"))
    # Phase 5: trần người dùng được chọn trong wizard (mặc định 8 giờ).
    max_time_limit_s: Mapped[int] = mapped_column(Integer, server_default=text("28800"))
    last_heartbeat_at: Mapped[datetime | None]


class Model(Base):
    __tablename__ = "models"

    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[UUID] = _uuid_pk()
    model_id: Mapped[UUID] = mapped_column(ForeignKey("models.id"))
    weights_sha256: Mapped[str] = mapped_column(Sha256, unique=True)
    weights_uri: Mapped[str] = mapped_column(Text)
    framework: Mapped[str] = mapped_column(Text)
    class_names: Mapped[list[str]] = mapped_column(ARRAY(Text))
    input_size: Mapped[int]
    supports_gradients: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = _created_at()


class CostProfile(Base):
    __tablename__ = "cost_profiles"

    id: Mapped[UUID] = _uuid_pk()
    compute_target_id: Mapped[UUID] = mapped_column(ForeignKey("compute_targets.id"))
    model_version_id: Mapped[UUID] = mapped_column(ForeignKey("model_versions.id"))
    attack_spec_id: Mapped[UUID] = mapped_column(ForeignKey("attack_specs.id"))
    sec_per_image: Mapped[float]
    peak_vram_mb: Mapped[int]
    batch_size: Mapped[int]
    measured_at: Mapped[datetime]
    environment: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    anonymized: Mapped[bool] = mapped_column(server_default=text("false"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[UUID] = _uuid_pk()
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id"))
    manifest_sha256: Mapped[str] = mapped_column(Sha256, unique=True)
    manifest_uri: Mapped[str] = mapped_column(Text)
    num_images: Mapped[int]
    class_names: Mapped[list[str]] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = _created_at()


class ClassMapping(Base):
    __tablename__ = "class_mappings"

    id: Mapped[UUID] = _uuid_pk()
    dataset_version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_versions.id"))
    model_version_id: Mapped[UUID] = mapped_column(ForeignKey("model_versions.id"))
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB)
    mapping_sha256: Mapped[str] = mapped_column(Sha256, unique=True)


class Slice(Base):
    __tablename__ = "slices"

    id: Mapped[UUID] = _uuid_pk()
    dataset_version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_versions.id"))
    name: Mapped[str] = mapped_column(Text)
    filter: Mapped[dict[str, Any]] = mapped_column(JSONB)
    seed: Mapped[int]
    image_ids: Mapped[list[str]] = mapped_column(ARRAY(Text))
    image_ids_sha256: Mapped[str] = mapped_column(Sha256)
    slice_sha256: Mapped[str | None] = mapped_column(Sha256)


class AttackSpecRow(Base):
    __tablename__ = "attack_specs"
    __table_args__ = (UniqueConstraint("name", "version"),)

    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[int]
    kind: Mapped[AttackKind] = mapped_column(pg_enum(AttackKind, "attack_kind"))
    access: Mapped[AttackAccess] = mapped_column(pg_enum(AttackAccess, "attack_access"))
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    spec_sha256: Mapped[str] = mapped_column(Sha256, unique=True)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class Protocol(Base):
    __tablename__ = "protocols"
    __table_args__ = (
        UniqueConstraint("name", "version"),
        # Phase 3: protocol phát triển (dev-open) không có người tạo.
        CheckConstraint("created_by IS NOT NULL OR status = 'dev'", name="creator_unless_dev"),
    )

    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[int]
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    body_sha256: Mapped[str] = mapped_column(Sha256)
    status: Mapped[ProtocolStatus] = mapped_column(
        pg_enum(ProtocolStatus, "protocol_status"), server_default=ProtocolStatus.ACTIVE.value
    )
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))


class Experiment(Base):
    __tablename__ = "experiments"
    # Phân trang keyset theo (created_at, id) (Phase 5).
    __table_args__ = (Index("ix_experiments_created_at_id", "created_at", "id"),)

    id: Mapped[UUID] = _uuid_pk()
    # Bỏ trống thì trigger `experiments_default_name` đặt `<model> · <slice> · <ngày UTC>`.
    name: Mapped[str] = mapped_column(Text, server_default=FetchedValue())
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    protocol_id: Mapped[UUID] = mapped_column(ForeignKey("protocols.id"))
    model_version_id: Mapped[UUID] = mapped_column(ForeignKey("model_versions.id"))
    slice_id: Mapped[UUID] = mapped_column(ForeignKey("slices.id"))
    class_mapping_id: Mapped[UUID] = mapped_column(ForeignKey("class_mappings.id"))
    compute_target_id: Mapped[UUID] = mapped_column(ForeignKey("compute_targets.id"))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    config_sha256: Mapped[str] = mapped_column(Sha256)
    status: Mapped[ExperimentStatus] = mapped_column(
        pg_enum(ExperimentStatus, "experiment_status"),
        server_default=ExperimentStatus.DRAFT.value,
    )
    limit_kind: Mapped[LimitKind] = mapped_column(pg_enum(LimitKind, "limit_kind"))
    limit_value: Mapped[Decimal] = mapped_column(Money)
    locked_at: Mapped[datetime | None]
    submitted_at: Mapped[datetime | None]
    lease_expires_at: Mapped[datetime | None]
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    lease_id: Mapped[UUID | None]
    # Tổng thời gian xử lý các batch (giây), so với limit_value khi limit_kind = time.
    processing_seconds_used: Mapped[Decimal] = mapped_column(Money, server_default=text("0"))
    inference_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    failure_cases_per_run: Mapped[int | None]
    # Phase 5.
    created_at: Mapped[datetime] = _created_at()
    cloned_from: Mapped[UUID | None] = mapped_column(ForeignKey("experiments.id"))
    finished_at: Mapped[datetime | None]


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("experiment_id", "fingerprint"),
        # tech-stack.md mục 4.3: mọi trạng thái bất thường phải có lý do.
        CheckConstraint(
            "status NOT IN ('failed', 'skipped', 'stopped_limit', 'cancelled')"
            " OR status_reason IS NOT NULL",
            name="abnormal_status_has_reason",
        ),
    )

    id: Mapped[UUID] = _uuid_pk()
    experiment_id: Mapped[UUID] = mapped_column(ForeignKey("experiments.id"))
    attack_spec_id: Mapped[UUID] = mapped_column(ForeignKey("attack_specs.id"))
    level: Mapped[float]
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    seed: Mapped[int]
    # Do worker tính và gửi ở `start` (null trước đó).
    fingerprint: Mapped[str | None] = mapped_column(Sha256, index=True)
    status: Mapped[RunStatus] = mapped_column(
        pg_enum(RunStatus, "run_status"), server_default=RunStatus.QUEUED.value
    )
    status_reason: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    images_done: Mapped[int] = mapped_column(server_default=text("0"))
    images_total: Mapped[int]
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    gpu_seconds: Mapped[float] = mapped_column(server_default=text("0"))
    cost_amount: Mapped[Decimal | None] = mapped_column(Money)
    manifest_uri: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(server_default=text("false"))
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    cached_from_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("runs.id"))
    checkpoint_key: Mapped[str | None] = mapped_column(Text)
    checkpoint_batch_index: Mapped[int | None]
    ordinal: Mapped[int] = mapped_column(server_default=text("0"))


class SearchResultRow(Base):
    __tablename__ = "search_results"

    id: Mapped[UUID] = _uuid_pk()
    experiment_id: Mapped[UUID] = mapped_column(ForeignKey("experiments.id"))
    attack_spec_id: Mapped[UUID] = mapped_column(ForeignKey("attack_specs.id"))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)


class FailureCase(Base):
    """Một `FailureCaseRecord` (contract); `rank` là vị trí trong `RunResult.failure_case_ids`."""

    __tablename__ = "failure_cases"
    __table_args__ = (UniqueConstraint("run_id", "rank"),)

    id: Mapped[UUID] = _uuid_pk()
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"))
    image_id: Mapped[str] = mapped_column(Text)
    severity_score: Mapped[float]
    fingerprint: Mapped[str] = mapped_column(Sha256)
    rank: Mapped[int]
    lost_objects: Mapped[int]
    new_false_positives: Mapped[int]
    detections: Mapped[dict[str, Any]] = mapped_column(JSONB)
    artifacts: Mapped[dict[str, Any]] = mapped_column(JSONB)


class CaseVerdict(Base):
    __tablename__ = "case_verdicts"
    __table_args__ = (UniqueConstraint("failure_case_id", "version"),)

    id: Mapped[UUID] = _uuid_pk()
    failure_case_id: Mapped[UUID] = mapped_column(ForeignKey("failure_cases.id"))
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int]
    severity: Mapped[CaseSeverity] = mapped_column(pg_enum(CaseSeverity, "case_severity"))
    verdict: Mapped[str] = mapped_column(Text)
    mitigation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("experiment_id", "version"),)

    id: Mapped[UUID] = _uuid_pk()
    experiment_id: Mapped[UUID] = mapped_column(ForeignKey("experiments.id"))
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int]
    decision: Mapped[ReviewDecision] = mapped_column(pg_enum(ReviewDecision, "review_decision"))
    conclusion: Mapped[str] = mapped_column(Text)
    mitigation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[UUID] = _uuid_pk()
    experiment_id: Mapped[UUID] = mapped_column(ForeignKey("experiments.id"))
    exported_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    pdf_uri: Mapped[str] = mapped_column(Text)
    json_uri: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Sha256, unique=True)
    created_at: Mapped[datetime] = _created_at()


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[UUID] = _uuid_pk()
    total_amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(Currency)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Quota(Base):
    __tablename__ = "quotas"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    budget_amount: Mapped[Decimal | None] = mapped_column(Money)
    gpu_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[UUID] = _uuid_pk()
    experiment_id: Mapped[UUID] = mapped_column(ForeignKey("experiments.id"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[LedgerKind] = mapped_column(pg_enum(LedgerKind, "ledger_kind"))
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(Currency)
    created_at: Mapped[datetime] = _created_at()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = _uuid_pk()
    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), comment="null với hành động của hệ thống"
    )
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[UUID | None]
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class EmailStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class EmailOutbox(Base):
    """Email chờ gửi (Phase 5): thêm trong cùng transaction với việc đổi trạng thái experiment,
    tác vụ nền gửi và đánh dấu bằng UPDATE, không xóa."""

    __tablename__ = "email_outbox"
    __table_args__ = (Index("ix_email_outbox_status_next_attempt_at", "status", "next_attempt_at"),)

    id: Mapped[UUID] = _uuid_pk()
    to: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text)
    status: Mapped[EmailStatus] = mapped_column(
        pg_enum(EmailStatus, "email_status"), server_default=EmailStatus.PENDING.value
    )
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    next_attempt_at: Mapped[datetime] = mapped_column(server_default=func.now())
    sent_at: Mapped[datetime | None]
