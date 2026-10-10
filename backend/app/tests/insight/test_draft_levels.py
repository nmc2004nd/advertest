"""Công thức level của template và preset (Phase R2, Chốt ở Group 0), không cần DB."""

from __future__ import annotations

import pytest

from advertest_contracts.models import PrimaryParam
from backend.app.services.drafts import experiment_presets, level_at, levels_at, protocol_templates

CONTINUOUS = PrimaryParam(name="eps", type="continuous", min=0.0, max=16.0, unit="/255")
DISCRETE = PrimaryParam(
    name="severity", type="discrete", min=1.0, max=5.0, values=[1.0, 2.0, 3.0, 4.0, 5.0], unit="mức"
)


@pytest.mark.parametrize(
    ("param", "ratio", "level"),
    [
        (CONTINUOUS, 0.0625, 1.0),
        (CONTINUOUS, 1 / 3, 5.333333),  # làm tròn 6 chữ số
        (DISCRETE, 0.25, 2.0),
        (DISCRETE, 0.125, 1.0),  # 1.5 cách đều 1 và 2: lấy giá trị nhỏ hơn
        (DISCRETE, 0.0625, 1.0),
        (DISCRETE, 1.0, 5.0),
    ],
)
def test_level_at(param: PrimaryParam, ratio: float, level: float) -> None:
    assert level_at(param, ratio) == level


def test_levels_at_sorts_and_drops_duplicates() -> None:
    assert levels_at(DISCRETE, [0.5, 0.0625, 0.125, 0.25]) == [1.0, 2.0, 3.0]


def test_seeds_load() -> None:
    assert [t.key for t in protocol_templates()] == ["quick", "front_camera", "weather", "full"]
    assert [p.key for p in experiment_presets()] == ["fast", "standard", "deep"]
