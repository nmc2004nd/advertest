"""Migration 0004 (Phase 5): điền dữ liệu cho experiment có từ Phase 3, trigger đặt tên mặc định,
trần thời gian của compute target, bảng email_outbox."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

pytestmark = pytest.mark.db

SHA = "b" * 64
SUBMITTED = datetime(2026, 9, 28, 23, 30, tzinfo=UTC)
RUN_FINISHED = datetime(2026, 9, 29, 0, 45, tzinfo=UTC)


def _sha() -> str:
    return uuid.uuid4().hex * 2


def _insert_chain(conn: Connection, tag: str) -> dict[str, uuid.UUID]:
    """Dữ liệu tối thiểu theo schema 0003 (SQL thuần: ORM đã ở schema mới)."""

    def one(sql: str, **params: object) -> uuid.UUID:
        value: uuid.UUID = conn.execute(text(sql + " RETURNING id"), params).scalar_one()
        return value

    user = one(
        "INSERT INTO users (email, full_name, password_hash) VALUES (:e, 'E', 'x')",
        e=f"m4-{tag}@x.test",
    )
    target = one(
        "INSERT INTO compute_targets (name, kind, billing_mode) VALUES (:n, 'local', 'none')",
        n=f"m4-{tag}",
    )
    model = one("INSERT INTO models (name, created_by) VALUES (:n, :u)", n=f"yolo-{tag}", u=user)
    mv = one(
        "INSERT INTO model_versions (model_id, weights_sha256, weights_uri, framework,"
        " class_names, input_size) VALUES (:m, :s, 'x', 'ultralytics', ARRAY['car'], 640)",
        m=model,
        s=_sha(),
    )
    dataset = one("INSERT INTO datasets (name, created_by) VALUES ('kitti', :u)", u=user)
    dv = one(
        "INSERT INTO dataset_versions (dataset_id, manifest_sha256, manifest_uri, num_images,"
        " class_names) VALUES (:d, :s, 'x', 5, ARRAY['Car'])",
        d=dataset,
        s=_sha(),
    )
    mapping = one(
        "INSERT INTO class_mappings (dataset_version_id, model_version_id, mapping,"
        " mapping_sha256) VALUES (:dv, :mv, '{}'::jsonb, :s)",
        dv=dv,
        mv=mv,
        s=_sha(),
    )
    slice_id = one(
        "INSERT INTO slices (dataset_version_id, name, filter, seed, image_ids,"
        " image_ids_sha256) VALUES (:dv, :n, '{}'::jsonb, 42, ARRAY['000001'], :s)",
        dv=dv,
        n=f"slice-{tag}",
        s=SHA,
    )
    return {
        "user": user, "target": target, "mv": mv, "mapping": mapping, "slice": slice_id,
    }  # fmt: skip


def _insert_experiment(
    conn: Connection, chain: dict[str, uuid.UUID], status: str, *, name: str | None = None
) -> uuid.UUID:
    columns = "" if name is None else ", name"
    values = "" if name is None else ", :name"
    experiment: uuid.UUID = conn.execute(
        text(
            "INSERT INTO experiments (created_by, protocol_id, model_version_id, slice_id,"
            " class_mapping_id, compute_target_id, config, config_sha256, status, limit_kind,"
            f" limit_value, submitted_at{columns}) VALUES (:u,"
            " '2edcdef5-0d3a-5d5f-98ac-b02637fa6718', :mv, :sl, :map, :t, '{}'::jsonb, :sha,"
            f" :st, 'time', 7200, :sub{values}) RETURNING id"
        ),
        {
            "u": chain["user"],
            "mv": chain["mv"],
            "sl": chain["slice"],
            "map": chain["mapping"],
            "t": chain["target"],
            "sha": SHA,
            "st": status,
            "sub": SUBMITTED,
            "name": name,
        },
    ).scalar_one()
    return experiment


@pytest.fixture(scope="module")
def upgraded(alembic_config: Config, owner_engine: Engine) -> Iterator[dict[str, object]]:
    """Tạo dữ liệu kiểu Phase 3 ở revision 0003 rồi nâng lên head."""
    tag = uuid.uuid4().hex[:8]
    command.downgrade(alembic_config, "0003")
    with owner_engine.begin() as conn:
        chain = _insert_chain(conn, tag)
        completed = _insert_experiment(conn, chain, "completed")
        spec: uuid.UUID = conn.execute(
            text(
                "INSERT INTO attack_specs (name, version, kind, access, spec, spec_sha256)"
                " VALUES (:n, 1, 'attack', 'white_box', '{}'::jsonb, :s) RETURNING id"
            ),
            {"n": f"m4-{tag}", "s": _sha()},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO runs (experiment_id, attack_spec_id, level, params, seed,"
                " images_total, status, finished_at)"
                " VALUES (:e, :a, 4, '{}'::jsonb, 0, 5, 'completed', :f)"
            ),
            {"e": completed, "a": spec, "f": RUN_FINISHED},
        )
        cancelled_no_runs = _insert_experiment(conn, chain, "cancelled")
        queued = _insert_experiment(conn, chain, "queued")
    command.upgrade(alembic_config, "head")
    yield {
        "tag": tag, "chain": chain, "completed": completed,
        "cancelled": cancelled_no_runs, "queued": queued,
    }  # fmt: skip


def _row(engine: Engine, experiment: object) -> tuple[str, datetime, datetime | None]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name, created_at, finished_at FROM experiments WHERE id = :e"),
            {"e": experiment},
        ).one()
    return row[0], row[1], row[2]


def test_existing_experiments_get_created_at_and_name(
    upgraded: dict[str, object], owner_engine: Engine
) -> None:
    tag = upgraded["tag"]
    name, created_at, _ = _row(owner_engine, upgraded["completed"])
    assert created_at == SUBMITTED
    # Ngày theo UTC (23:30 UTC ngày 28, dù giờ máy có thể đã sang ngày 29).
    assert name == f"yolo-{tag} · slice-{tag} · 2026-09-28"


def test_finished_at_backfilled_only_for_finished_experiments(
    upgraded: dict[str, object], owner_engine: Engine
) -> None:
    assert _row(owner_engine, upgraded["completed"])[2] == RUN_FINISHED
    assert _row(owner_engine, upgraded["cancelled"])[2] == SUBMITTED  # không có run
    assert _row(owner_engine, upgraded["queued"])[2] is None


def test_trigger_names_new_experiment_unless_given(
    upgraded: dict[str, object], app_engine: Engine
) -> None:
    chain = upgraded["chain"]
    assert isinstance(chain, dict)
    with app_engine.connect() as conn, conn.begin() as trans:
        default = _insert_experiment(conn, chain, "queued")
        given = _insert_experiment(conn, chain, "queued", name="Tên tự đặt")
        names: dict[uuid.UUID, str] = dict(
            conn.execute(
                text("SELECT id, name FROM experiments WHERE id IN (:a, :b)"),
                {"a": default, "b": given},
            ).all()
        )
        trans.rollback()
    tag = upgraded["tag"]
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    assert names[default] == f"yolo-{tag} · slice-{tag} · {today}"
    assert names[given] == "Tên tự đặt"


def test_compute_target_default_limit_cannot_exceed_max(
    upgraded: dict[str, object], owner_engine: Engine
) -> None:
    chain = upgraded["chain"]
    assert isinstance(chain, dict)
    with owner_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT default_time_limit_s, max_time_limit_s FROM compute_targets WHERE id = :t"
            ),
            {"t": chain["target"]},
        ).one()
        assert tuple(row) == (7200, 28800)
        with pytest.raises(IntegrityError, match="default_within_max"):
            conn.execute(
                text("UPDATE compute_targets SET default_time_limit_s = 30000 WHERE id = :t"),
                {"t": chain["target"]},
            )


def test_app_can_queue_and_mark_email_but_not_delete(app_engine: Engine) -> None:
    with app_engine.connect() as conn, conn.begin() as trans:
        email = conn.execute(
            text(
                'INSERT INTO email_outbox ("to", subject, body_html, body_text)'
                " VALUES ('a@x.test', 's', '<p>b</p>', 'b')"
                " RETURNING id, status::text, attempts, next_attempt_at IS NOT NULL"
            )
        ).one()
        assert tuple(email)[1:] == ("pending", 0, True)
        conn.execute(
            text("UPDATE email_outbox SET status = 'sent', attempts = 1 WHERE id = :i"),
            {"i": email[0]},
        )
        savepoint = conn.begin_nested()
        with pytest.raises(ProgrammingError, match="permission denied"):
            conn.execute(text("DELETE FROM email_outbox WHERE id = :i"), {"i": email[0]})
        savepoint.rollback()
        trans.rollback()
