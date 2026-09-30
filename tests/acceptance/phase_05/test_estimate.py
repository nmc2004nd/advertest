"""validation.md Phase 5, Ước lượng (`test_estimate.py`)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from advertest_contracts.models import EstimateResponse

from .conftest import Api, attack, ok, post, spec_id

pytestmark = pytest.mark.db
IMAGES = 5  # slice fixture


def _estimate(api: Api, client: TestClient, body: dict[str, object]) -> EstimateResponse:
    response = ok(post(client, "/experiments/estimate", body))
    return EstimateResponse.model_validate(response.json())


def test_with_profiles_follows_formula(api: Api) -> None:
    target = api.target()
    api.profile(target, sec=0.5, batch=2, attacks=["fgsm"])
    api.profile(target, sec=2.0, batch=2, attacks=["pgd_linf"])
    _, _, client = api.user("engineer")
    result = _estimate(
        api, client, api.body(target, [attack("fgsm", [2, 4]), attack("pgd_linf", [8])])
    )
    assert [r.est_seconds for r in result.runs] == pytest.approx(
        [IMAGES * 0.5 * 1.2, IMAGES * 0.5 * 1.2, IMAGES * 2.0 * 1.2]
    )
    assert result.total_seconds == pytest.approx(IMAGES * (0.5 + 0.5 + 2.0) * 1.2)
    assert result.missing_profiles == []


def test_missing_profile_is_null_and_still_creatable(api: Api) -> None:
    target = api.target()
    api.profile(target, sec=0.5, batch=2, attacks=["fgsm"])
    _, _, client = api.user("engineer")
    body = api.body(target, [attack("fgsm", [4]), attack("pgd_l2", [1])])
    result = _estimate(api, client, body)
    assert [r.est_seconds for r in result.runs] == [pytest.approx(3.0), None]
    assert [str(i) for i in result.missing_profiles] == [spec_id("pgd_l2")]
    assert result.total_seconds is None
    assert post(client, "/experiments", body).status_code == 201


def test_exceeds_limit(api: Api) -> None:
    target = api.target()
    api.profile(target, sec=10.0, batch=2, attacks=["pgd_linf"])
    _, _, client = api.user("engineer")
    body = api.body(target, [attack("pgd_linf", [4])], limit={"kind": "time", "value": "30"})
    assert _estimate(api, client, body).exceeds_limit is True  # 60 s > 30 s


def test_queue_position_and_ahead_seconds(api: Api) -> None:
    target = api.target()
    api.profile(target, sec=1.0, batch=2, attacks=["fgsm"])
    body = api.body(target, [attack("fgsm", [2, 4])])
    for _ in range(2):
        _, _, other = api.user("engineer")
        ok(post(other, "/experiments", body))
        api.clock.advance(1)
    _, _, client = api.user("engineer")
    result = _estimate(api, client, body)
    assert result.queue.position == 3
    assert result.queue.ahead_seconds == pytest.approx(2 * 2 * IMAGES * 1.0 * 1.2)


def test_incompatible_runs_are_marked(api: Api) -> None:
    _, _, client = api.user("engineer")
    body = api.body(api.target(), [attack("fgsm", [4])], gradient=False)
    result = _estimate(api, client, body)
    assert [(r.skip_reason, r.est_seconds) for r in result.runs] == [("incompatible", 0)]
