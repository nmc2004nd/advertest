"""validation.md Phase 8, Tiêu chí (`test_criteria.py`).

Đầu cuối: experiment chạy bằng worker thật, kết quả đọc ở `ExperimentDetail.review.criteria_results`
sau khi gửi duyệt. Các trạng thái tìm ngưỡng khó tạo thật trên slice 5 ảnh (`near_threshold`,
`stopped_limit`, `failed`, level trong bracket, khoảng tin cậy chứa level) kiểm bằng hàm đánh giá
với `SearchResult` của contract (như Phase 6 kiểm xếp hạng bằng `RankingRun`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from advertest_contracts.models import PassCriterion, SearchResult
from attacks.registry import get_spec, load_catalog
from backend.app.reviews.criteria import min_breaking_point

from .conftest import (
    LEVELS,
    P5,
    Flow,
    max_drop,
    ok,
    post,
    protocol_body,
    required_grid,
    runs_of,
    unique,
)

pytestmark = pytest.mark.db
MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "search_result"


def _results(flow: Flow, experiment_id: str) -> list[dict[str, Any]]:
    ok(flow.submit(experiment_id))
    review = flow.owner.get(f"/experiments/{experiment_id}").json()["review"]
    results: list[dict[str, Any]] = review["criteria_results"]
    return results


def _protocol(flow: Flow, **changes: Any) -> str:
    created = ok(
        post(flow.reviewer, "/protocols", {"name": unique("p"), "body": protocol_body(**changes)})
    ).json()
    protocol_id: str = created["id"]
    return protocol_id


def _drop(flow: Flow, experiment_id: str, level: float, cls: str | None = None) -> float:
    run = next(
        r
        for r in runs_of(flow.owner, experiment_id)
        if r["level"] == level and r["status"] == "completed"
    )
    metrics = run["metrics"]
    if cls is None:
        drop: float = metrics["relative_drop"]
        return drop
    per = metrics["per_class"][cls]
    return float((per["clean_ap50"] - per["attacked_ap50"]) / per["clean_ap50"])


# ---------------------------------------------------------------- max_drop_at_level


def test_max_drop_pass_fail_and_class_filter(flow: Flow) -> None:
    protocol_id = _protocol(
        flow,
        pass_criteria=[
            max_drop("fgsm", 4.0, threshold=0.9),
            max_drop("fgsm", 2.0, threshold=0.05),
            max_drop("fgsm", 4.0, threshold=1.0, class_filter="car"),
        ],
    )
    experiment_id = flow.experiment(protocol_id=protocol_id)
    results = _results(flow, experiment_id)
    assert [r["status"] for r in results] == ["pass", "fail", "pass"], results
    assert results[0]["value"] == pytest.approx(_drop(flow, experiment_id, 4.0))
    assert results[1]["value"] == pytest.approx(_drop(flow, experiment_id, 2.0))
    # class_filter: đại lượng là mức sụt AP50 của riêng class car, không phải mAP.
    assert results[2]["value"] == pytest.approx(_drop(flow, experiment_id, 4.0, "car"))


def test_max_drop_inconclusive_without_completed_run(
    flow: Flow, fail_first_build: list[str]
) -> None:
    protocol_id = _protocol(flow, pass_criteria=[max_drop("fgsm", 2.0), max_drop("fgsm", 4.0)])
    experiment_id = flow.experiment(protocol_id=protocol_id)
    runs = {r["level"]: r for r in runs_of(flow.owner, experiment_id)}
    failed = [level for level, r in runs.items() if r["status"] == "failed"]
    assert len(failed) == 1
    reason = {runs[failed[0]]["run_id"]: "Hết bộ nhớ"}
    ok(flow.submit(experiment_id, run_explanations=reason))
    review = flow.owner.get(f"/experiments/{experiment_id}").json()["review"]
    by_level = {LEVELS[i]: r for i, r in enumerate(review["criteria_results"])}
    assert by_level[failed[0]]["status"] == "inconclusive"
    other = next(level for level in LEVELS if level != failed[0])
    assert by_level[other]["status"] == "pass"


def test_max_drop_uses_trigger_run_for_early_stop(flow: Flow) -> None:
    """PGD L∞ sụp ở eps 2; eps 4 bị bỏ qua do dừng sớm → dùng đại lượng của run kích hoạt."""
    levels = [2.0, 4.0, 8.0, 16.0, 32.0]
    flow.api.profile(flow.target, sec=0.05, batch=5, attacks=["pgd_linf"])
    protocol_id = _protocol(
        flow,
        required_attacks=[required_grid("pgd_linf", levels)],
        pass_criteria=[max_drop("pgd_linf", 4.0, threshold=1.0)],
    )
    experiment_id = flow.experiment(
        attacks=[P5.attack("pgd_linf", levels)], protocol_id=protocol_id
    )
    runs = {r["level"]: r for r in runs_of(flow.owner, experiment_id)}
    assert runs[4.0]["status"] == "skipped" and runs[4.0]["status_reason"]["code"] == "early_stop"
    (result,) = _results(flow, experiment_id)
    assert result["status"] == "pass"
    assert "dừng sớm" in result["detail"]


# ---------------------------------------------------------------- min_breaking_point


def _search_protocol(flow: Flow, *, threshold: float, lo: float, levels: list[float]) -> str:
    spec = get_spec(load_catalog(), name="fgsm")
    required = {
        "attack_spec_name": "fgsm",
        "spec_sha256": spec.spec_sha256,
        "mode": "search",
        "search": {
            "threshold_kind": "relative_drop",
            "threshold": threshold,
            "class_filter": None,
            "lo": lo,
            "hi": 16.0,
            "max_tol": 2.0,
            "min_bootstrap_samples": 50,
        },
    }
    criteria = [
        {
            "kind": "min_breaking_point",
            "attack_spec_name": "fgsm",
            "level": level,
            "threshold_kind": "relative_drop",
            "threshold": threshold,
            "class_filter": None,
        }
        for level in levels
    ]
    return _protocol(flow, required_attacks=[required], pass_criteria=criteria)


def _search_experiment(flow: Flow, protocol_id: str, *, threshold: float, lo: float) -> str:
    spec = get_spec(load_catalog(), name="fgsm")
    attack = {
        "attack_spec_id": str(spec.id),
        "spec_sha256": spec.spec_sha256,
        "mode": "search",
        "search": {
            "threshold_kind": "relative_drop",
            "threshold": threshold,
            "class_filter": None,
            "lo": lo,
            "hi": 16.0,
            "tol": 2.0,
            "coarse_n": 3,
            "subset_size": 3,
            "bootstrap_samples": 50,
        },
        "seed": 0,
    }
    return flow.experiment(attacks=[attack], protocol_id=protocol_id)


def test_breaking_point_found(flow: Flow) -> None:
    """FGSM sụp 50% giữa eps 2 (0.34) và eps 4 (0.57): kết quả trên trang review đúng luật áp lên
    `SearchResult` thật (slice 5 ảnh: khoảng tin cậy rộng nên thường `near_threshold`); với level
    0.5 và 16 thì không bao giờ `pass` ở level lớn hay `fail` ở level nhỏ."""
    protocol_id = _search_protocol(flow, threshold=0.5, lo=0.0, levels=[0.5, 16.0])
    experiment_id = _search_experiment(flow, protocol_id, threshold=0.5, lo=0.0)
    results = _results(flow, experiment_id)
    (search,) = flow.owner.get(f"/experiments/{experiment_id}").json()["search_results"]
    result = SearchResult.model_validate(search)
    assert result.status in {"found", "non_monotonic"}, result
    assert 2.0 <= result.bracket[1] <= 4.0
    for index, level in enumerate([0.5, 16.0]):
        expected = min_breaking_point(index, _criterion(level, result), result)
        assert results[index] == expected.model_dump(mode="json")
    assert results[0]["status"] != "fail" and results[1]["status"] != "pass"


def test_breaking_point_not_reached_passes(flow: Flow) -> None:
    """FGSM không làm mAP sụp 90% trong dải 0-16 (tối đa khoảng 0.64)."""
    protocol_id = _search_protocol(flow, threshold=0.9, lo=0.0, levels=[8.0])
    experiment_id = _search_experiment(flow, protocol_id, threshold=0.9, lo=0.0)
    (result,) = _results(flow, experiment_id)
    assert result["status"] == "pass" and "Không chạm ngưỡng" in result["detail"], result


def test_breaking_point_below_min_fails(flow: Flow) -> None:
    """Ngưỡng 0.2 đã vượt ngay ở eps 1 (khoảng 0.26)."""
    protocol_id = _search_protocol(flow, threshold=0.2, lo=1.0, levels=[4.0])
    experiment_id = _search_experiment(flow, protocol_id, threshold=0.2, lo=1.0)
    (result,) = _results(flow, experiment_id)
    assert result["status"] == "fail" and "cận dưới" in result["detail"], result


def _mock(name: str, **changes: Any) -> SearchResult:
    data = json.loads((MOCKS / f"{name}.json").read_text())
    data.update(changes)
    return SearchResult.model_validate(data)


def _criterion(level: float, mock: SearchResult, name: str = "fgsm") -> PassCriterion:
    return PassCriterion.model_validate(
        {
            "kind": "min_breaking_point",
            "attack_spec_name": name,
            "level": level,
            "threshold_kind": mock.threshold_kind,
            "threshold": mock.threshold,
            "class_filter": mock.class_filter,
        }
    )


@pytest.mark.parametrize(
    ("mock", "changes", "level", "expected"),
    [
        ("found", {"confidence_interval": None}, 0.3, "pass"),  # a = 0.375 ≥ 0.3
        ("found", {"confidence_interval": None}, 0.6, "fail"),  # b = 0.5 < 0.6
        ("found", {"confidence_interval": None}, 0.4, "inconclusive"),  # trong (0.375, 0.5]
        ("found", {"confidence_interval": [0.2, 0.5]}, 0.3, "inconclusive"),  # KTC chứa level
        ("found", {"near_threshold": True, "confidence_interval": None}, 0.3, "inconclusive"),
        ("non_monotonic", {"near_threshold": False, "confidence_interval": None}, 1.0, "pass"),
        ("not_reached", {}, 0.5, "pass"),
        ("below_min", {}, 1.0, "fail"),
        ("stopped_limit", {}, 0.5, "inconclusive"),
        ("failed", {}, 0.5, "inconclusive"),
    ],
)
def test_breaking_point_rules(
    mock: str, changes: dict[str, Any], level: float, expected: str
) -> None:
    result = _mock(mock, **changes)
    assert min_breaking_point(0, _criterion(level, result), result).status == expected
