"""validation.md Phase 5, Ảnh và quyền riêng tư (`test_failure_case_access.py`). Worker thật."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from advertest_contracts.models import FailureCaseView
from backend.app.db import models as m

from .conftest import Api, attack, error, ok, post

pytestmark = pytest.mark.db


def _run_with_cases(api: Api) -> tuple[TestClient, str, list[FailureCaseView]]:
    """Experiment FGSM eps 16 chạy xong (đủ mạnh để có failure case); trả client, run, case."""
    target = api.target()
    api.profile(target, sec=0.05, batch=5, attacks=["fgsm"])
    _, _, client = api.user("engineer")
    created = ok(post(client, "/experiments", api.body(target, [attack("fgsm", [16])]))).json()
    api.work(target, created["id"])
    (run,) = client.get(f"/experiments/{created['id']}/runs").json()
    assert run["status"] == "completed" and run["failure_case_ids"], run
    cases = [
        FailureCaseView.model_validate(c)
        for c in client.get(f"/runs/{run['run_id']}/failure-cases").json()
    ]
    return client, run["run_id"], cases


@pytest.fixture
def anonymized(app_engine: Engine, api: Api) -> Iterator[None]:
    def set_flag(value: bool) -> None:
        with Session(app_engine) as session, session.begin():
            session.execute(
                update(m.Dataset)
                .where(m.Dataset.id == api.world.dataset_id)
                .values(anonymized=value)
            )

    set_flag(True)
    yield
    set_flag(False)


def test_anonymized_dataset_normal_with_urls_expiring_in_10_minutes(
    api: Api, anonymized: None
) -> None:
    client, _, cases = _run_with_cases(api)
    case = FailureCaseView.model_validate(client.get(f"/failure-cases/{cases[0].id}").json())
    assert case.display_mode == "normal"
    assert case.urls.clean and case.urls.adversarial and case.urls.clean_thumb
    assert case.urls_expire_at == api.clock.now.replace(microsecond=0) + timedelta(minutes=10)
    image = client.get(case.urls.clean)
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    api.clock.advance(600)
    assert error(client.get(case.urls.clean))[:2] == (404, "not_found")


def test_unanonymized_dataset_hides_every_image_but_keeps_boxes(api: Api) -> None:
    client, run_id, cases = _run_with_cases(api)
    listed = cases[0]
    full = FailureCaseView.model_validate(client.get(f"/failure-cases/{listed.id}").json())
    for case in (listed, full):
        assert case.display_mode == "hidden_unanonymized"
        assert all(url is None for url in case.urls.model_dump().values())
        assert case.urls_expire_at is None
        assert case.detections.ground_truth
    assert "/artifacts/" not in client.get(f"/runs/{run_id}/failure-cases").text


def test_dev_flag_serves_unblurred_with_mode(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, cases = _run_with_cases(api)
    monkeypatch.setenv("DEV_ALLOW_UNBLURRED", "true")
    case = FailureCaseView.model_validate(client.get(f"/failure-cases/{cases[0].id}").json())
    assert case.display_mode == "dev_unblurred"
    assert case.urls.clean is not None
    assert client.get(case.urls.clean).status_code == 200


def test_temporary_url_reads_only_its_object(api: Api, anonymized: None) -> None:
    client, _, cases = _run_with_cases(api)
    case = FailureCaseView.model_validate(client.get(f"/failure-cases/{cases[0].id}").json())
    assert case.urls.clean and case.urls.adversarial
    clean_payload, clean_sig = case.urls.clean.removeprefix("/artifacts/").split(".")
    adv_payload, _ = case.urls.adversarial.removeprefix("/artifacts/").split(".")
    assert client.get(f"/artifacts/{adv_payload}.{clean_sig}").status_code == 404  # ghép khóa khác
    assert client.get(f"/artifacts/{clean_payload}.{clean_sig[:-2]}AA").status_code == 404
    clean = client.get(case.urls.clean).content
    adversarial = client.get(case.urls.adversarial).content
    assert clean != adversarial  # mỗi URL trả đúng đối tượng của nó
    anonymous = TestClient(api.app())
    assert error(anonymous.get(case.urls.clean))[:2] == (401, "unauthenticated")
