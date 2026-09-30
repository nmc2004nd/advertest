"""Vùng làm mờ rule_v1 (validation.md Phase 6, mục Làm mờ)."""

import pytest

from ml_core.privacy.regions import Detection, object_region, rule_v1_regions


def test_person_top_third_and_vehicle_bottom_forty_percent() -> None:
    assert object_region(Detection((10, 30, 40, 120), "person")) == (10, 30, 40, 60)
    car = object_region(Detection((0, 100, 200, 200), "car"))
    assert car == pytest.approx((0, 160, 200, 200))
    truck = object_region(Detection((5, 0, 50, 50), "truck"))
    assert truck == pytest.approx((5, 30, 50, 50))
    assert object_region(Detection((0, 0, 10, 10), "bicycle")) is None


def test_union_of_sources_score_threshold_and_ignore() -> None:
    regions = rule_v1_regions(
        ground_truth=[Detection((10, 30, 40, 120), "person")],
        clean=[
            Detection((100, 100, 200, 200), "car", 0.9),
            Detection((300, 300, 330, 390), "person", 0.2),  # dưới 0.25: bỏ
        ],
        attacked=[Detection((400, 100, 500, 150), "truck", 0.25)],  # đúng 0.25: giữ
        ignore_boxes=[(600.0, 200.0, 630.0, 260.0)],
        width=640,
        height=640,
    )
    assert regions == pytest.approx(
        [(10, 30, 40, 60), (100, 160, 200, 200), (400, 130, 500, 150), (600, 200, 630, 260)]
    )


def test_clip_drops_empty_regions() -> None:
    regions = rule_v1_regions(
        ground_truth=[Detection((-10, -30, 20, 60), "person")],
        clean=[],
        attacked=[],
        ignore_boxes=[(630.0, 630.0, 700.0, 700.0), (700.0, 700.0, 800.0, 800.0)],
        width=640,
        height=640,
    )
    # Person: 1/3 trên của box cao 90 là [-30, 0) → nằm ngoài ảnh, bị bỏ.
    assert regions == pytest.approx([(630, 630, 640, 640)])
