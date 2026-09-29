"""API experiment với Postgres và MinIO thật (validation.md Phase 5: kiểm tra cấu hình, ước lượng,
quyền và vòng đời, ảnh và quyền riêng tư; phần lọc/phân trang của `GET /experiments`)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    AttackAccess,
    AttackKind,
    BillingMode,
    ComputeKind,
    ExperimentStatus,
    ProtocolStatus,
    Role,
    RunStatus,
)
from advertest_contracts.models import (
    AttackSpec,
    ErrorResponse,
    EstimateResponse,
    ExperimentClone,
    ExperimentCreate,
    ExperimentDetail,
    ExperimentPage,
    FailureCaseView,
    Manifest,
    RunView,
    compute_spec_sha256,
)
from backend.app.api.deps import get_artifact_reader
from backend.app.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from backend.app.db import models as m
from backend.app.services import artifacts, compute_targets, experiments, leasing, runs
from backend.app.storage import Buckets

from .conftest import make_user
from .test_auth_api import Env, _login, _user, env
from .test_worker_services import (
    T0,
    FakeClock,
    World,
    _attack,
    _completion,
    _start_request,
    world,
)

pytestmark = pytest.mark.db
__all__ = ["env", "world"]
MOCKS = Path(__file__).resolve().parents[4] / "contracts" / "mocks"
DEV_OPEN = "2edcdef5-0d3a-5d5f-98ac-b02637fa6718"


def _sha() -> str:
    return uuid.uuid4().hex * 2


# ---------------------------------------------------------------- dữ liệu


@dataclass(frozen=True)
class Fx:
    """Tài nguyên dùng chung của module (ngoài `world` của Phase 3)."""

    world: World
    model: uuid.UUID
    slice: uuid.UUID
    mapping: uuid.UUID
    dataset: uuid.UUID
    target: uuid.UUID
    rented: uuid.UUID
    retired_protocol: uuid.UUID
    other_slice: uuid.UUID  # dataset version khác
    nograd_model: uuid.UUID
    nograd_mapping: uuid.UUID
    extra_specs: tuple[AttackSpec, ...]  # 3 bản sao fgsm để thử trần 50 run


def _copy_spec(session: Session, base: str, name: str, version: int = 1) -> AttackSpec:
    body = next(
        s for s in json.loads((MOCKS.parent / "seeds" / "attack_specs.json").read_text())
        if s["name"] == base
    )  # fmt: skip
    body = {k: v for k, v in body.items() if k not in ("id", "spec_sha256")}
    body.update(name=name, version=version)
    sha = compute_spec_sha256(body)
    row = m.AttackSpecRow(
        name=name, version=version, kind=AttackKind.ATTACK, access=AttackAccess.WHITE_BOX,
        spec=body, spec_sha256=sha,
    )  # fmt: skip
    session.add(row)
    session.flush()
    return AttackSpec.model_validate({**body, "id": str(row.id), "spec_sha256": sha})


@pytest.fixture(scope="module")
def fx(world: World, app_engine: Engine, owner_engine: Engine) -> Fx:
    tag = uuid.uuid4().hex[:8]
    with Session(owner_engine) as s, s.begin():
        model_id = world.local.card.id
        slice_row = s.get(m.Slice, world.local.slice.id)
        mapping = s.get(m.ClassMapping, world.local.mapping.id)
        assert slice_row is not None and mapping is not None
        dv = s.get(m.DatasetVersion, slice_row.dataset_version_id)
        assert dv is not None
        admin = make_user(s)
        target = compute_targets.create(s, actor=admin, name=f"g2-{tag}").target
        rented = m.ComputeTarget(
            name=f"thue-{tag}", kind=ComputeKind.RENTED, billing_mode=BillingMode.HOURLY,
            price_per_hour=Decimal("1.5"), currency="USD",
        )  # fmt: skip
        protocol = m.Protocol(
            name=f"cu-{tag}", version=1, body={}, body_sha256=_sha(),
            status=ProtocolStatus.RETIRED, created_by=admin.id,
        )  # fmt: skip
        other_dv = m.DatasetVersion(
            dataset_id=dv.dataset_id, manifest_sha256=_sha(), manifest_uri="s3://d",
            num_images=3, class_names=["Car"],
        )  # fmt: skip
        other_model = m.Model(name=f"khong-grad-{tag}", created_by=admin.id)
        s.add_all([rented, protocol, other_dv, other_model])
        s.flush()
        other_slice = m.Slice(
            dataset_version_id=other_dv.id, name=f"khac-{tag}", filter={}, seed=0,
            image_ids=["1"], image_ids_sha256=_sha(),
        )  # fmt: skip
        nograd = m.ModelVersion(
            model_id=other_model.id, weights_sha256=_sha(), weights_uri="s3://m",
            framework="torchvision", class_names=["car"], input_size=640,
            supports_gradients=False,
        )  # fmt: skip
        s.add_all([other_slice, nograd])
        s.flush()
        nograd_mapping = m.ClassMapping(
            dataset_version_id=dv.id, model_version_id=nograd.id, mapping={},
            mapping_sha256=_sha(),
        )  # fmt: skip
        s.add(nograd_mapping)
        extra = tuple(_copy_spec(s, "fgsm", f"fgsm_{tag}_{i}") for i in range(3))
        return Fx(
            world=world, model=model_id, slice=slice_row.id, mapping=mapping.id,
            dataset=dv.dataset_id, target=target.id, rented=rented.id,
            retired_protocol=protocol.id, other_slice=other_slice.id, nograd_model=nograd.id,
            nograd_mapping=nograd_mapping.id, extra_specs=extra,
        )  # fmt: skip


def _body(fx: Fx, attacks: list[dict[str, Any]] | None = None, **changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": 1,
        "protocol_id": DEV_OPEN,
        "model_version_id": str(fx.model),
        "slice_id": str(fx.slice),
        "class_mapping_id": str(fx.mapping),
        "compute_target_id": str(fx.target),
        "attacks": attacks
        if attacks is not None
        else [_attack("fgsm", [4]), _attack("pgd_linf", [4])],
        "limit": {"kind": "time", "value": "7200"},
    }
    body.update(changes)
    return body


def _spec_attack(spec: AttackSpec, levels: list[float]) -> dict[str, Any]:
    return {
        "attack_spec_id": str(spec.id), "spec_sha256": spec.spec_sha256, "mode": "grid",
        "grid": {"levels": levels}, "seed": 0,
    }  # fmt: skip


@dataclass
class Api:
    env: Env
    buckets: Buckets

    def client(self, *roles: Role) -> tuple[uuid.UUID, TestClient]:
        user_id, email = _user(self.env.engine, roles=roles or (Role.ENGINEER,))
        client = self.env.client()
        app: Any = client.app
        app.dependency_overrides[get_artifact_reader] = lambda: self.buckets.artifacts.get
        assert _login(client, email).status_code == 200
        return user_id, client


@pytest.fixture
def api(env: Env, buckets: Buckets) -> Api:
    env.clock.now = T0
    return Api(env, buckets)


def _post(client: TestClient, path: str, body: Any = None) -> httpx.Response:
    csrf = {CSRF_HEADER: client.cookies.get(CSRF_COOKIE) or ""}
    response: httpx.Response = client.post(path, json=body, headers=csrf)
    return response


def _error(response: httpx.Response) -> tuple[int, str, list[str]]:
    error = ErrorResponse.model_validate(response.json()).error
    return response.status_code, error.code, [f.path for f in error.fields or []]


def _create(client: TestClient, body: dict[str, Any]) -> ExperimentDetail:
    response = _post(client, "/experiments", body)
    assert response.status_code == 201, response.text
    return ExperimentDetail.model_validate(response.json())


# ---------------------------------------------------------------- kiểm tra cấu hình


@pytest.mark.parametrize("path", ["/experiments", "/experiments/estimate"])
def test_no_attack_is_422_at_attacks(api: Api, fx: Fx, path: str) -> None:
    _, client = api.client()
    assert _error(_post(client, path, _body(fx, attacks=[]))) == (
        422, "validation_error", ["attacks"],
    )  # fmt: skip


def test_spec_hash_mismatch(api: Api, fx: Fx) -> None:
    _, client = api.client()
    attack = {**_attack("fgsm", [4]), "spec_sha256": "0" * 64}
    assert _error(_post(client, "/experiments", _body(fx, [attack]))) == (
        422, "invalid_request", ["attacks.0.spec_sha256"],
    )  # fmt: skip


@pytest.mark.parametrize(
    "levels",
    [[4, 40], [4, 4], [float(i) for i in range(1, 14)]],
    ids=["ngoai-dai", "trung", "hon-12"],
)
def test_level_errors(api: Api, fx: Fx, levels: list[float]) -> None:
    _, client = api.client()
    status, code, paths = _error(
        _post(
            client, "/experiments", _body(fx, [_attack("pgd_linf", [2]), _attack("fgsm", levels)])
        )
    )
    assert (status, code, paths) == (422, "invalid_request", ["attacks.1.grid.levels"])


def test_more_than_50_runs(api: Api, fx: Fx) -> None:
    _, client = api.client()
    levels = [float(i) for i in range(1, 12)]  # 11 level, 5 attack: 55 run
    attacks = [_attack("fgsm", levels), _attack("pgd_linf", levels)]
    attacks += [_spec_attack(spec, levels) for spec in fx.extra_specs]
    assert _error(_post(client, "/experiments", _body(fx, attacks))) == (
        422, "invalid_request", ["attacks"],
    )  # fmt: skip


def test_search_mode_is_not_supported_yet(api: Api, fx: Fx) -> None:
    _, client = api.client()
    search = {
        "threshold_kind": "relative_drop", "threshold": 0.2, "lo": 0, "hi": 16, "tol": 0.5,
        "coarse_n": 4, "subset_size": 100,
    }  # fmt: skip
    attack = {**_attack("fgsm", [4]), "mode": "search", "grid": None, "search": search}
    assert _error(_post(client, "/experiments", _body(fx, [attack]))) == (
        422, "not_supported_yet", ["attacks.0.mode"],
    )  # fmt: skip


def test_slice_mapping_model_mismatch(api: Api, fx: Fx) -> None:
    _, client = api.client()
    wrong_slice = _body(fx, slice_id=str(fx.other_slice))
    assert _error(_post(client, "/experiments", wrong_slice))[2] == ["slice_id"]
    wrong_model = _body(fx, class_mapping_id=str(fx.nograd_mapping))
    assert _error(_post(client, "/experiments", wrong_model))[2] == ["class_mapping_id"]


def test_protocol_target_and_limit_rules(api: Api, fx: Fx) -> None:
    _, client = api.client()
    cases = {
        "protocol_id": _body(fx, protocol_id=str(fx.retired_protocol)),
        "compute_target_id": _body(fx, compute_target_id=str(fx.rented)),
        "limit.kind": _body(fx, limit={"kind": "budget", "value": "10"}),
        "limit.value": _body(fx, limit={"kind": "time", "value": "28801"}),
    }
    for path, body in cases.items():
        assert _error(_post(client, "/experiments", body)) == (422, "invalid_request", [path])
    assert (
        _post(
            client, "/experiments/estimate", _body(fx, limit={"kind": "time", "value": "28800"})
        ).status_code
        == 200
    )


def test_unknown_cloned_from(api: Api, fx: Fx) -> None:
    _, client = api.client()
    body = _body(fx, cloned_from=str(uuid.uuid4()))
    assert _error(_post(client, "/experiments", body))[2] == ["cloned_from"]


def test_estimate_and_create_share_validation(api: Api, fx: Fx) -> None:
    _, client = api.client()
    body = _body(
        fx,
        [_attack("fgsm", [99]), {**_attack("pgd_linf", [4]), "spec_sha256": "1" * 64}],
        protocol_id=str(fx.retired_protocol),
    )
    estimate, create = (_post(client, p, body) for p in ("/experiments/estimate", "/experiments"))
    assert _error(estimate) == _error(create)
    assert _error(create)[2] == ["attacks.0.grid.levels", "attacks.1.spec_sha256", "protocol_id"]


def test_fourth_queued_experiment_is_rejected_per_user(api: Api, fx: Fx) -> None:
    _, client = api.client()
    for _ in range(3):
        _create(client, _body(fx))
    assert _error(_post(client, "/experiments", _body(fx)))[:2] == (409, "queue_limit_reached")
    _, other = api.client()
    _create(other, _body(fx))


# ---------------------------------------------------------------- ước lượng


def _profiles(owner_engine: Engine, fx: Fx, target: uuid.UUID, spp: dict[str, float]) -> None:
    ids = {
        s["name"]: s["id"]
        for s in json.loads((MOCKS.parent / "seeds" / "attack_specs.json").read_text())
    }
    with Session(owner_engine) as s, s.begin():
        for name, value in spp.items():
            s.add(
                m.CostProfile(
                    compute_target_id=target, model_version_id=fx.model,
                    attack_spec_id=uuid.UUID(ids[name]), sec_per_image=value, peak_vram_mb=100,
                    batch_size=2, measured_at=T0,
                )
            )  # fmt: skip


def _new_target(owner_engine: Engine) -> uuid.UUID:
    with Session(owner_engine) as s, s.begin():
        admin = make_user(s)
        return compute_targets.create(s, actor=admin, name=f"est-{uuid.uuid4().hex[:8]}").target.id


def _estimate(client: TestClient, body: dict[str, Any]) -> EstimateResponse:
    response = _post(client, "/experiments/estimate", body)
    assert response.status_code == 200, response.text
    return EstimateResponse.model_validate(response.json())


def test_estimate_with_profiles(api: Api, fx: Fx, owner_engine: Engine) -> None:
    target = _new_target(owner_engine)
    _profiles(owner_engine, fx, target, {"fgsm": 0.5, "pgd_linf": 2.0})
    _, client = api.client()
    body = _body(
        fx, [_attack("fgsm", [2, 4]), _attack("pgd_linf", [4])], compute_target_id=str(target)
    )
    result = _estimate(client, body)
    images = len(fx.world.local.slice.image_ids)
    expected = [(0.5, images * 0.5 * 1.2), (0.5, images * 0.5 * 1.2), (2.0, images * 2.0 * 1.2)]
    assert [r.images for r in result.runs] == [images] * 3
    assert [r.sec_per_image for r in result.runs] == [spp for spp, _ in expected]
    assert [r.est_seconds for r in result.runs] == pytest.approx([est for _, est in expected])
    assert result.total_seconds == pytest.approx(images * (0.5 + 0.5 + 2.0) * 1.2)
    assert result.missing_profiles == [] and result.exceeds_limit is False
    assert (result.queue.position, result.queue.ahead_seconds) == (1, 0)


def test_missing_profile_still_creates(api: Api, fx: Fx, owner_engine: Engine) -> None:
    target = _new_target(owner_engine)
    _profiles(owner_engine, fx, target, {"fgsm": 0.5})
    _, client = api.client()
    body = _body(
        fx, [_attack("fgsm", [4]), _attack("pgd_l2", [1, 2])], compute_target_id=str(target)
    )
    result = _estimate(client, body)
    assert [r.est_seconds is None for r in result.runs] == [False, True, True]
    pgd_l2 = next(
        s["id"]
        for s in json.loads((MOCKS.parent / "seeds" / "attack_specs.json").read_text())
        if s["name"] == "pgd_l2"
    )
    assert [str(i) for i in result.missing_profiles] == [pgd_l2]
    assert result.total_seconds is None
    _create(client, body)


def test_exceeds_limit(api: Api, fx: Fx, owner_engine: Engine) -> None:
    target = _new_target(owner_engine)
    _profiles(owner_engine, fx, target, {"pgd_linf": 100.0})
    _, client = api.client()
    body = _body(
        fx,
        [_attack("pgd_linf", [4]), _attack("pgd_l2", [1])],
        compute_target_id=str(target),
        limit={"kind": "time", "value": "10"},
    )
    result = _estimate(client, body)
    # Thiếu profile pgd_l2 nhưng phần ước lượng được (240 s) đã vượt 10 s.
    assert result.total_seconds is None and result.exceeds_limit is True


def test_queue_position_and_ahead_seconds(api: Api, fx: Fx, owner_engine: Engine) -> None:
    target = _new_target(owner_engine)
    _profiles(owner_engine, fx, target, {"fgsm": 1.0})
    body = _body(fx, [_attack("fgsm", [2, 4])], compute_target_id=str(target))
    for _ in range(2):  # hai experiment đang chờ của người khác, tạo trước
        _, other = api.client()
        _create(other, body)
        api.env.clock.advance(1)
    _, client = api.client()
    result = _estimate(client, body)
    per_experiment = 2 * len(fx.world.local.slice.image_ids) * 1.0 * 1.2
    assert result.queue.position == 3
    assert result.queue.ahead_seconds == pytest.approx(2 * per_experiment)
    created = _create(client, body)
    assert created.queue_position == 3


def test_incompatible_runs_are_marked(api: Api, fx: Fx) -> None:
    _, client = api.client()
    body = _body(fx, [_attack("fgsm", [4])], model_version_id=str(fx.nograd_model),
                 class_mapping_id=str(fx.nograd_mapping))  # fmt: skip
    result = _estimate(client, body)
    assert [(r.skip_reason, r.est_seconds) for r in result.runs] == [("incompatible", 0)]
    assert result.missing_profiles == [] and result.total_seconds == 0


# ---------------------------------------------------------------- quyền và vòng đời


def _audit(engine: Engine, experiment: uuid.UUID, action: str) -> int:
    with Session(engine) as s:
        return (
            s.scalar(
                select(func.count())
                .select_from(m.AuditLog)
                .where(m.AuditLog.entity_id == experiment, m.AuditLog.action == action)
            )
            or 0
        )


def test_create_and_read_by_everyone(api: Api, fx: Fx, app_engine: Engine) -> None:
    owner_id, client = api.client()
    created = _create(client, _body(fx, name="  Thử FGSM  "))
    assert created.status == ExperimentStatus.QUEUED and created.name == "Thử FGSM"
    assert created.owner.id == owner_id and created.finished_at is None
    assert created.created_at == T0 and created.run_counts.queued == 2
    assert _audit(app_engine, created.id, "experiment.submit") == 1
    runs_ = [
        RunView.model_validate(r) for r in client.get(f"/experiments/{created.id}/runs").json()
    ]
    assert [(r.status, r.fingerprint, r.attack_spec.name) for r in runs_] == [
        (RunStatus.QUEUED, None, "fgsm"), (RunStatus.QUEUED, None, "pgd_linf"),
    ]  # fmt: skip
    for role in (Role.REVIEWER, Role.ADMIN):
        _, other = api.client(role)
        assert other.get(f"/experiments/{created.id}").status_code == 200
        assert _error(_post(other, "/experiments", _body(fx)))[:2] == (403, "forbidden")


def test_default_name_from_model_slice_and_date(api: Api, fx: Fx) -> None:
    _, client = api.client()
    created = _create(client, _body(fx))
    assert created.name.startswith(f"{created.model.name} · {created.slice.name} · ")


def test_list_filters_and_pagination(api: Api, fx: Fx) -> None:
    me, client = api.client()
    mine = []
    for _ in range(3):
        mine.append(_create(client, _body(fx)).id)
        api.env.clock.advance(1)  # created_at khác nhau: thứ tự xác định
    _, other = api.client()
    theirs = _create(other, _body(fx)).id
    params: dict[str, Any] = {"owner": "me", "limit": 2}
    page = ExperimentPage.model_validate(client.get("/experiments", params=params).json())
    assert [e.id for e in page.items] == [mine[2], mine[1]]  # mới nhất trước
    assert page.next_cursor is not None
    params["cursor"] = page.next_cursor
    rest = ExperimentPage.model_validate(client.get("/experiments", params=params).json())
    assert [e.id for e in rest.items] == [mine[0]] and rest.next_cursor is None
    everyone = client.get(
        "/experiments", params={"model": str(fx.model), "status": "queued", "limit": 100}
    )
    ids = {e.id for e in ExperimentPage.model_validate(everyone.json()).items}
    assert theirs in ids and set(mine) <= ids
    assert all(e.owner.id == me for e in page.items)
    none = client.get("/experiments", params={"owner": "me", "status": "completed"}).json()
    assert none["items"] == []


def test_cancel_rules(api: Api, fx: Fx, app_engine: Engine) -> None:
    _, owner = api.client()
    created = _create(owner, _body(fx))
    _, other = api.client()
    assert _error(_post(other, f"/experiments/{created.id}/cancel"))[:2] == (403, "forbidden")
    api.env.clock.advance(30)
    cancelled = ExperimentDetail.model_validate(
        _post(owner, f"/experiments/{created.id}/cancel").json()
    )
    assert cancelled.status == ExperimentStatus.CANCELLED
    assert cancelled.finished_at == T0 + timedelta(seconds=30)
    assert cancelled.run_counts.cancelled == 2
    assert _audit(app_engine, created.id, "experiment.cancel") == 1
    assert _error(_post(owner, f"/experiments/{created.id}/cancel"))[:2] == (409, "conflict")
    assert _error(_post(owner, f"/experiments/{uuid.uuid4()}/cancel"))[:2] == (404, "not_found")


# ---------------------------------------------------------------- chạy xong, run, manifest, ảnh


@dataclass(frozen=True)
class Done:
    owner_email: str
    experiment: uuid.UUID
    run: uuid.UUID
    case: uuid.UUID
    case_key: str


@pytest.fixture(scope="module")
def done(fx: Fx, app_engine: Engine, owner_engine: Engine, buckets: Buckets) -> Done:
    """Experiment một run chạy xong qua service của worker (lease → start → complete)."""
    clock = FakeClock()
    owner_id, owner_email = _user(owner_engine, roles=(Role.ENGINEER,))
    with Session(owner_engine) as s, s.begin():
        admin = make_user(s)
        target_id = compute_targets.create(
            s, actor=admin, name=f"done-{uuid.uuid4().hex[:8]}"
        ).target.id
    with Session(app_engine) as s, s.begin():
        actor = s.get(m.User, owner_id)
        assert actor is not None
        body = ExperimentCreate.model_validate(
            _body(fx, [_attack("fgsm", [4])], compute_target_id=str(target_id))
        )
        experiment = experiments.create_from_body(s, actor=actor, body=body, clock=clock)
        target_row = s.get(m.ComputeTarget, target_id)
        assert target_row is not None
        assert leasing.lease(s, target_row, clock) is experiment
        (run,) = experiments.runs_of(s, experiment.id)
        assert experiment.lease_id is not None
        runs.start(s, target_row, run.id, _start_request(experiment.lease_id), clock)
        clock.advance(120)
        completion = _completion(run, experiment.lease_id, buckets)
        runs.complete(s, target_row, run.id, completion, buckets.artifacts.exists, clock)
        manifest = json.loads((MOCKS / "manifest" / "gpu_local.json").read_text())
        # `_completion` đã đặt manifest rỗng; ghi đè bằng manifest hợp lệ (put của store cấm đè).
        raw: Any = buckets.artifacts.client
        raw.put_object(
            Bucket=buckets.artifacts.bucket,
            Key=f"runs/{run.id}/manifest.json",
            Body=json.dumps(manifest).encode(),
        )
        case = completion.failure_cases[0]
        return Done(owner_email, experiment.id, run.id, case.id, case.artifacts.clean_png)


def test_completed_experiment_detail_runs_and_manifest(api: Api, done: Done) -> None:
    _, client = api.client()
    detail = ExperimentDetail.model_validate(client.get(f"/experiments/{done.experiment}").json())
    assert detail.status == ExperimentStatus.COMPLETED
    assert detail.finished_at == T0 + timedelta(seconds=120)
    assert detail.clean_metrics is not None and detail.queue_position is None
    (run,) = [
        RunView.model_validate(r) for r in client.get(f"/experiments/{done.experiment}/runs").json()
    ]
    assert run.fingerprint is not None and run.status == RunStatus.COMPLETED
    assert RunView.model_validate(client.get(f"/runs/{done.run}").json()) == run
    manifest = client.get(f"/runs/{done.run}/manifest")
    assert manifest.status_code == 200
    Manifest.model_validate(manifest.json())
    assert client.get(f"/runs/{uuid.uuid4()}/manifest").status_code == 404


def test_cancel_completed_is_conflict(api: Api, done: Done) -> None:
    client = api.env.client()
    assert _login(client, done.owner_email).status_code == 200
    assert _error(_post(client, f"/experiments/{done.experiment}/cancel"))[:2] == (409, "conflict")


@pytest.fixture
def anonymized(owner_engine: Engine, fx: Fx) -> Iterator[None]:
    with Session(owner_engine) as s, s.begin():
        s.execute(update(m.Dataset).where(m.Dataset.id == fx.dataset).values(anonymized=True))
    yield
    with Session(owner_engine) as s, s.begin():
        s.execute(update(m.Dataset).where(m.Dataset.id == fx.dataset).values(anonymized=False))


def test_unanonymized_dataset_hides_images(
    api: Api, done: Done, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEV_ALLOW_UNBLURRED", raising=False)
    _, client = api.client()
    (listed,) = [
        FailureCaseView.model_validate(c)
        for c in client.get(f"/runs/{done.run}/failure-cases").json()
    ]
    full = FailureCaseView.model_validate(client.get(f"/failure-cases/{done.case}").json())
    for case in (listed, full):
        assert case.display_mode == "hidden_unanonymized"
        assert all(v is None for v in case.urls.model_dump().values())
        assert case.urls_expire_at is None
        assert case.detections.ground_truth  # vẫn có dữ liệu box


def test_dev_flag_serves_images_with_warning_mode(
    api: Api, done: Done, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEV_ALLOW_UNBLURRED", "true")
    _, client = api.client()
    case = FailureCaseView.model_validate(client.get(f"/failure-cases/{done.case}").json())
    assert case.display_mode == "dev_unblurred"
    assert case.urls.clean is not None
    image = client.get(case.urls.clean)
    assert image.status_code == 200 and image.content == done.case_key.encode()
    assert image.headers["content-type"] == "image/png"


def test_anonymized_dataset_urls_expire_after_10_minutes(
    api: Api, done: Done, anonymized: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEV_ALLOW_UNBLURRED", raising=False)
    _, client = api.client()
    (listed,) = [
        FailureCaseView.model_validate(c)
        for c in client.get(f"/runs/{done.run}/failure-cases").json()
    ]
    assert listed.display_mode == "normal"
    assert listed.urls.clean is None and listed.urls.clean_thumb is not None  # danh sách: thumbnail
    case = FailureCaseView.model_validate(client.get(f"/failure-cases/{done.case}").json())
    assert case.urls_expire_at == T0 + timedelta(minutes=10)
    assert case.urls.clean is not None and case.urls.perturbation is not None
    assert client.get(case.urls.clean).status_code == 200
    api.env.clock.advance(600)
    assert _error(client.get(case.urls.clean))[:2] == (404, "not_found")


def test_token_reads_only_its_object(api: Api, done: Done, anonymized: None) -> None:
    _, client = api.client()
    case = FailureCaseView.model_validate(client.get(f"/failure-cases/{done.case}").json())
    assert case.urls.clean is not None and case.urls.adversarial is not None
    token_clean = case.urls.clean.removeprefix("/artifacts/")
    payload, signature = token_clean.split(".")
    other_payload = case.urls.adversarial.removeprefix("/artifacts/").split(".")[0]
    # Ghép phần khóa của ảnh khác với chữ ký của ảnh này: không đọc được.
    assert client.get(f"/artifacts/{other_payload}.{signature}").status_code == 404
    assert client.get(f"/artifacts/{payload}.{signature[:-2]}AA").status_code == 404
    assert client.get("/artifacts/khong-phai-token").status_code == 404
    # Token tự ký cho khóa ngoài runs/ bị từ chối ngay khi cấp.
    with pytest.raises(ValueError):
        artifacts.issue("datasets/x.png", T0)
    # Không có phiên: 401 dù token đúng.
    assert TestClient(client.app).get(case.urls.clean).status_code == 401


# ---------------------------------------------------------------- nhân bản


def test_clone_uses_current_spec_version(api: Api, fx: Fx, owner_engine: Engine) -> None:
    tag = uuid.uuid4().hex[:8]
    with Session(owner_engine) as s, s.begin():
        v1 = _copy_spec(s, "fgsm", f"fgsm_clone_{tag}")
    _, client = api.client()
    original = _create(client, _body(fx, [_spec_attack(v1, [2, 4]), _attack("pgd_linf", [4])]))
    same = ExperimentClone.model_validate(client.get(f"/experiments/{original.id}/clone").json())
    assert same.warnings == []
    assert same.config.attacks == original.config.attacks
    assert same.config.cloned_from == original.id and same.config.name is None

    with Session(owner_engine) as s, s.begin():
        v2 = _copy_spec(s, "fgsm", f"fgsm_clone_{tag}", version=2)
        s.execute(
            update(m.AttackSpecRow).where(m.AttackSpecRow.id == v1.id).values(is_active=False)
        )
    updated = ExperimentClone.model_validate(client.get(f"/experiments/{original.id}/clone").json())
    assert updated.config.attacks[0].attack_spec_id == v2.id
    assert updated.config.attacks[0].grid == original.config.attacks[0].grid
    assert [(w.attack_spec_id, w.from_version, w.to_version) for w in updated.warnings] == [
        (v2.id, 1, 2)
    ]
    # Cấu hình nhân bản tạo được ngay.
    _create(client, json.loads(updated.config.model_dump_json()))
    assert client.get(f"/experiments/{uuid.uuid4()}/clone").status_code == 404
