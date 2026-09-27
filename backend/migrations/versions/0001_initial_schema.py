"""Schema đầu tiên: toàn bộ bảng, enum, phân quyền advertest_app, trigger chặn tự review.

Revision ID: 0001
Revises:
Create Date: 2026-09-27 21:25:05.148350
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Bảng chỉ được thêm, không sửa, không xóa (mission.md nguyên tắc 3).
APPEND_ONLY = ["audit_log", "case_verdicts", "reviews", "reports", "ledger_entries"]
# Run không bị xóa, chỉ đặt archived = true.
NO_DELETE = ["runs"]
FULL_ACCESS = [
    "users",
    "user_roles",
    "compute_targets",
    "cost_profiles",
    "models",
    "model_versions",
    "datasets",
    "dataset_versions",
    "class_mappings",
    "slices",
    "attack_specs",
    "protocols",
    "experiments",
    "search_results",
    "failure_cases",
    "budgets",
    "quotas",
]
ENUM_TYPES = [
    "attack_kind",
    "attack_access",
    "compute_kind",
    "billing_mode",
    "user_status",
    "role",
    "protocol_status",
    "experiment_status",
    "limit_kind",
    "ledger_kind",
    "review_decision",
    "run_status",
    "case_severity",
]

FORBID_SELF_REVIEW = """
CREATE FUNCTION forbid_self_review() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.reviewer_id = (SELECT created_by FROM experiments WHERE id = NEW.experiment_id) THEN
        RAISE EXCEPTION 'Người tạo experiment không được review experiment của mình'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$
"""


def upgrade() -> None:
    op.create_table(
        "attack_specs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "kind", sa.Enum("attack", "corruption", "occlusion", name="attack_kind"), nullable=False
        ),
        sa.Column(
            "access", sa.Enum("white_box", "black_box", name="attack_access"), nullable=False
        ),
        sa.Column("spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("spec_sha256", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attack_specs")),
        sa.UniqueConstraint("name", "version", name=op.f("uq_attack_specs_name")),
        sa.UniqueConstraint("spec_sha256", name=op.f("uq_attack_specs_spec_sha256")),
    )
    op.create_table(
        "compute_targets",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Enum("local", "rented", name="compute_kind"), nullable=False),
        sa.Column("gpu_model", sa.Text(), nullable=True),
        sa.Column("vram_gb", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("billing_mode", sa.Enum("none", "hourly", name="billing_mode"), nullable=False),
        sa.Column("price_per_hour", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("token_hash", sa.Text(), nullable=True),
        sa.Column(
            "default_time_limit_s", sa.Integer(), server_default=sa.text("7200"), nullable=False
        ),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "billing_mode = 'none' OR (price_per_hour IS NOT NULL AND currency IS NOT NULL)",
            name=op.f("ck_compute_targets_hourly_needs_price"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_compute_targets")),
        sa.UniqueConstraint("name", name=op.f("uq_compute_targets_name")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("organization", sa.Text(), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "active", "rejected", "disabled", name="user_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "requested_role", sa.Enum("engineer", "reviewer", "admin", name="role"), nullable=True
        ),
        sa.Column("request_reason", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], name=op.f("fk_users_approved_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True, comment="null với hành động của hệ thống"),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_audit_log_actor_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_table(
        "budgets",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_budgets_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budgets")),
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("anonymized", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_datasets_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
    )
    op.create_table(
        "models",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_models_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_models")),
        sa.UniqueConstraint("name", name=op.f("uq_models_name")),
    )
    op.create_table(
        "protocols",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "retired", name="protocol_status"),
            server_default="active",
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_protocols_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_protocols")),
        sa.UniqueConstraint("name", "version", name=op.f("uq_protocols_name")),
    )
    op.create_table(
        "quotas",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("budget_amount", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("gpu_hours", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_quotas_user_id_users")),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_quotas")),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Enum("engineer", "reviewer", "admin", name="role"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_roles_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", "role", name=op.f("pk_user_roles")),
    )
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_uri", sa.Text(), nullable=False),
        sa.Column("num_images", sa.Integer(), nullable=False),
        sa.Column("class_names", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_dataset_versions_dataset_id_datasets")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_versions")),
        sa.UniqueConstraint("manifest_sha256", name=op.f("uq_dataset_versions_manifest_sha256")),
    )
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("weights_sha256", sa.String(length=64), nullable=False),
        sa.Column("weights_uri", sa.Text(), nullable=False),
        sa.Column("framework", sa.Text(), nullable=False),
        sa.Column("class_names", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("input_size", sa.Integer(), nullable=False),
        sa.Column(
            "supports_gradients", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["models.id"], name=op.f("fk_model_versions_model_id_models")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_versions")),
        sa.UniqueConstraint("weights_sha256", name=op.f("uq_model_versions_weights_sha256")),
    )
    op.create_table(
        "class_mappings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mapping_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_class_mappings_dataset_version_id_dataset_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            name=op.f("fk_class_mappings_model_version_id_model_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_class_mappings")),
        sa.UniqueConstraint("mapping_sha256", name=op.f("uq_class_mappings_mapping_sha256")),
    )
    op.create_table(
        "cost_profiles",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("compute_target_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("attack_spec_id", sa.Uuid(), nullable=False),
        sa.Column("sec_per_image", sa.Double(), nullable=False),
        sa.Column("peak_vram_mb", sa.Integer(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attack_spec_id"],
            ["attack_specs.id"],
            name=op.f("fk_cost_profiles_attack_spec_id_attack_specs"),
        ),
        sa.ForeignKeyConstraint(
            ["compute_target_id"],
            ["compute_targets.id"],
            name=op.f("fk_cost_profiles_compute_target_id_compute_targets"),
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            name=op.f("fk_cost_profiles_model_version_id_model_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cost_profiles")),
    )
    op.create_table(
        "slices",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("filter", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("image_ids", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("image_ids_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_slices_dataset_version_id_dataset_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_slices")),
    )
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("protocol_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("slice_id", sa.Uuid(), nullable=False),
        sa.Column("class_mapping_id", sa.Uuid(), nullable=False),
        sa.Column("compute_target_id", sa.Uuid(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "queued",
                "running",
                "completed",
                "submitted_for_review",
                "in_review",
                "approved",
                "changes_requested",
                "rejected",
                "cancelled",
                name="experiment_status",
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("limit_kind", sa.Enum("budget", "time", name="limit_kind"), nullable=False),
        sa.Column("limit_value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checkpoint", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["class_mapping_id"],
            ["class_mappings.id"],
            name=op.f("fk_experiments_class_mapping_id_class_mappings"),
        ),
        sa.ForeignKeyConstraint(
            ["compute_target_id"],
            ["compute_targets.id"],
            name=op.f("fk_experiments_compute_target_id_compute_targets"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_experiments_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            name=op.f("fk_experiments_model_version_id_model_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["protocol_id"], ["protocols.id"], name=op.f("fk_experiments_protocol_id_protocols")
        ),
        sa.ForeignKeyConstraint(
            ["slice_id"], ["slices.id"], name=op.f("fk_experiments_slice_id_slices")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiments")),
    )
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind", sa.Enum("reserve", "settle", "release", name="ledger_kind"), nullable=False
        ),
        sa.Column("amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_ledger_entries_experiment_id_experiments"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_ledger_entries_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_entries")),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("exported_by", sa.Uuid(), nullable=False),
        sa.Column("pdf_uri", sa.Text(), nullable=False),
        sa.Column("json_uri", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiments.id"], name=op.f("fk_reports_experiment_id_experiments")
        ),
        sa.ForeignKeyConstraint(
            ["exported_by"], ["users.id"], name=op.f("fk_reports_exported_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
        sa.UniqueConstraint("sha256", name=op.f("uq_reports_sha256")),
    )
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "decision",
            sa.Enum("approve", "changes_requested", "reject", name="review_decision"),
            nullable=False,
        ),
        sa.Column("conclusion", sa.Text(), nullable=False),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiments.id"], name=op.f("fk_reviews_experiment_id_experiments")
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"], ["users.id"], name=op.f("fk_reviews_reviewer_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
        sa.UniqueConstraint("experiment_id", "version", name=op.f("uq_reviews_experiment_id")),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("attack_spec_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.Double(), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "completed",
                "failed",
                "skipped",
                "stopped_limit",
                "cancelled",
                name="run_status",
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("status_reason", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("images_done", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("images_total", sa.Integer(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("gpu_seconds", sa.Double(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_amount", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("manifest_uri", sa.Text(), nullable=True),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status NOT IN ('failed', 'skipped', 'stopped_limit', 'cancelled')"
            " OR status_reason IS NOT NULL",
            name=op.f("ck_runs_abnormal_status_has_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["attack_spec_id"],
            ["attack_specs.id"],
            name=op.f("fk_runs_attack_spec_id_attack_specs"),
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiments.id"], name=op.f("fk_runs_experiment_id_experiments")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
        sa.UniqueConstraint("experiment_id", "fingerprint", name=op.f("uq_runs_experiment_id")),
    )
    op.create_table(
        "search_results",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("attack_spec_id", sa.Uuid(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["attack_spec_id"],
            ["attack_specs.id"],
            name=op.f("fk_search_results_attack_spec_id_attack_specs"),
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_search_results_experiment_id_experiments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_results")),
    )
    op.create_table(
        "failure_cases",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("image_id", sa.Text(), nullable=False),
        sa.Column("severity_score", sa.Double(), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("thumbnail_uri", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name=op.f("fk_failure_cases_run_id_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_failure_cases")),
    )
    op.create_table(
        "case_verdicts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("failure_case_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "severity",
            sa.Enum("critical", "major", "minor", "acceptable", name="case_severity"),
            nullable=False,
        ),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["failure_case_id"],
            ["failure_cases.id"],
            name=op.f("fk_case_verdicts_failure_case_id_failure_cases"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"], ["users.id"], name=op.f("fk_case_verdicts_reviewer_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_verdicts")),
        sa.UniqueConstraint(
            "failure_case_id", "version", name=op.f("uq_case_verdicts_failure_case_id")
        ),
    )

    op.execute(FORBID_SELF_REVIEW)
    op.execute(
        "CREATE TRIGGER reviews_forbid_self_review BEFORE INSERT OR UPDATE ON reviews"
        " FOR EACH ROW EXECUTE FUNCTION forbid_self_review()"
    )

    # advertest_app được tạo bởi docker/postgres/init/01-roles.sh; migration chỉ cấp quyền.
    for table in FULL_ACCESS:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO advertest_app")
    for table in NO_DELETE:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO advertest_app")
    for table in APPEND_ONLY:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO advertest_app")


def downgrade() -> None:
    op.drop_table("case_verdicts")
    op.drop_table("failure_cases")
    op.drop_table("search_results")
    op.drop_table("runs")
    op.drop_table("reviews")
    op.drop_table("reports")
    op.drop_table("ledger_entries")
    op.drop_table("experiments")
    op.drop_table("slices")
    op.drop_table("cost_profiles")
    op.drop_table("class_mappings")
    op.drop_table("model_versions")
    op.drop_table("dataset_versions")
    op.drop_table("user_roles")
    op.drop_table("quotas")
    op.drop_table("protocols")
    op.drop_table("models")
    op.drop_table("datasets")
    op.drop_table("budgets")
    op.drop_table("audit_log")
    op.drop_table("users")
    op.drop_table("compute_targets")
    op.drop_table("attack_specs")
    op.execute("DROP FUNCTION forbid_self_review()")
    for enum_type in ENUM_TYPES:
        op.execute(f"DROP TYPE {enum_type}")
