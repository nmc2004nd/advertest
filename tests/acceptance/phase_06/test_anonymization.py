"""validation.md Phase 6, Làm mờ (`test_anonymization.py`)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import pytest
import yaml
from PIL import Image
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from advertest_contracts.models import FailureCaseView, RunResult
from attacks.factory import build_perturbation
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m
from ml_core.cli import app as ml_app
from ml_core.privacy.blur import blur_regions, region_mask
from ml_core.privacy.regions import Detection, rule_v1_regions
from ml_core.runner import candidates as candidates_module
from ml_core.runner.images import difference_image

from .conftest import Kitti, grid_attack, ok, post

# ---------------------------------------------------------------- vùng rule_v1


def test_rule_v1_regions() -> None:
    person = Detection((10, 30, 40, 120), "person")  # cao 90 → 1/3 trên: 30..60
    car = Detection((100, 50, 300, 150), "car", 0.9)  # cao 100 → 40% dưới: 110..150
    truck = Detection((400, 0, 500, 50), "truck", 0.3)
    weak = Detection((0, 0, 50, 50), "person", 0.2)  # score < 0.25: bỏ
    cyclist = Detection((200, 200, 260, 300), "bicycle", 0.9)  # class không thuộc quy tắc: bỏ
    regions = rule_v1_regions(
        ground_truth=[person],
        clean=[car, weak],
        attacked=[truck, cyclist],
        ignore_boxes=[(600, 600, 700, 700)],
        width=640,
        height=640,
    )
    assert sorted(regions) == sorted(
        [
            (10.0, 30.0, 40.0, 60.0),
            (100.0, 110.0, 300.0, 150.0),
            (400.0, 30.0, 500.0, 50.0),
            (600.0, 600.0, 640.0, 640.0),  # ignore region, cắt theo khung ảnh
        ]
    )


# ---------------------------------------------------------------- làm mờ trên ảnh thật


def test_blur_changes_inside_and_keeps_outside(kitti: Kitti) -> None:
    """Ảnh sạch, ảnh sau biến đổi và ảnh thứ ba (vùng khác biệt): trong vùng khác bản chưa làm mờ,
    ngoài vùng giống hệt."""
    images, targets, mask = kitti.subset([0])
    fog = build_perturbation(get_spec(load_catalog(), name="fog"), None)
    corrupted = fog.apply(images, targets, 3.0, 0, mask)
    clean, transformed = images[0], corrupted[0]
    third = difference_image(clean, transformed)
    gt = targets[0]
    _, height, width = clean.shape
    regions = rule_v1_regions(
        ground_truth=[Detection(tuple(map(float, b)), "car") for b in gt["boxes"]],
        clean=[],
        attacked=[],
        ignore_boxes=[tuple(map(float, b)) for b in gt["ignore_boxes"]],
        width=width,
        height=height,
    )
    assert regions
    inside = region_mask(regions, width, height)
    for name, image in (("sạch", clean), ("sau biến đổi", transformed), ("thứ ba", third)):
        blurred = blur_regions(image, regions)
        assert np.array_equal(blurred[:, ~inside], image[:, ~inside]), name
        changed = np.any(blurred != image, axis=0)[inside].mean()
        assert changed > 0.5, (name, changed)


# ---------------------------------------------------------------- metric không đổi


def _run(kitti: Kitti, tmp: Path, name: str) -> RunResult:
    config = {
        "model_id": kitti.ids["model"],
        "slice_id": kitti.ids["slice"],
        "mapping_id": kitti.ids["mapping"],
        "attacks": [grid_attack("fgsm", [4])],
        "device": "cpu",
        "batch_size": 5,
        "failure_cases_per_run": 3,
    }
    path = tmp / f"{name}.yaml"
    path.write_text(yaml.safe_dump(config))
    args = ["--store-dir", str(kitti.store_dir), "run", "--config", str(path), "--force"]
    result = CliRunner().invoke(ml_app, args)
    assert result.exit_code == 0, result.output
    (only,) = json.loads(result.stdout)
    return RunResult.model_validate(only)


def test_metrics_same_with_or_without_blur(
    kitti: Kitti, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blurred = _run(kitti, tmp_path, "co-lam-mo")
    monkeypatch.setattr(candidates_module, "blur_regions", lambda image, _regions: image.copy())
    plain = _run(kitti, tmp_path, "khong-lam-mo")
    assert blurred.metrics is not None and blurred.metrics == plain.metrics
    # Id case chứa run_id (mỗi lần --force là run mới): so số case.
    assert len(blurred.failure_case_ids) == len(plain.failure_case_ids) > 0


# ---------------------------------------------------------------- run thật qua API và worker


def _png(buckets: Any, key: str) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(buckets.artifacts.get(key))).convert("RGB"))


def _pixelated(pixels: np.ndarray) -> float:
    """Tỉ lệ điểm ảnh bằng điểm bên phải (vùng pixelate có khối màu đều)."""
    return float(np.all(pixels[:, 1:] == pixels[:, :-1], axis=-1).mean())


@pytest.mark.db
def test_new_cases_blurred_in_minio_and_shown(api: Any, kitti: Kitti, owner_engine: Engine) -> None:
    target = api.target()
    api.profile(target, sec=0.05, batch=3, attacks=["fgsm"])
    _, _, client = api.user("engineer")
    created = ok(post(client, "/experiments", api.body(target, [grid_attack("fgsm", [16])])))
    experiment_id = created.json()["id"]
    api.work(target, experiment_id)
    (run,) = client.get(f"/experiments/{experiment_id}/runs").json()
    assert run["status"] == "completed" and run["failure_case_ids"], run

    originals = {
        image_id: np.round(np.clip(kitti.batch.images[i], 0, 1) * 255)
        .astype(np.uint8)
        .transpose(1, 2, 0)
        for i, image_id in enumerate(kitti.batch.image_ids)
    }
    with Session(owner_engine) as session:
        cases = session.scalars(
            select(m.FailureCase).where(m.FailureCase.run_id == UUID(run["run_id"]))
        ).all()
    assert cases
    checked = 0
    for case in cases:
        assert case.anonymization is not None
        assert case.anonymization["applied"] is True and case.anonymization["method"] == "rule_v1"
        detections = case.detections
        regions = [
            region
            for region in (
                *(_region(d) for d in detections["ground_truth"]),
                *(tuple(r["bbox"]) for r in detections.get("ignore_regions", [])),
            )
            if region is not None
        ]
        original = originals[case.image_id]
        shown = {k: _png(api.buckets, case.artifacts[k])
                 for k in ("clean_png", "adversarial_png", "perturbation_png")}  # fmt: skip
        for region in regions:
            x1, y1, x2, y2 = (round(v) for v in region)
            if (x2 - x1) < 24 or (y2 - y1) < 24:
                continue  # vùng nhỏ: khối pixelate quá ít để kiểm
            crop = (slice(y1 + 2, y2 - 2), slice(x1 + 2, x2 - 2))
            # Ảnh sạch hiển thị khác ảnh gốc tái tạo từ dataset trong vùng làm mờ.
            assert not np.array_equal(shown["clean_png"][crop], original[crop])
            for key, pixels in shown.items():
                assert _pixelated(pixels[crop]) > 0.6, (case.image_id, key, region)
            checked += 1
    assert checked >= 1

    # Case mới (dataset chưa ẩn danh) hiển thị bình thường; case cũ chưa làm mờ thì ẩn.
    views = [FailureCaseView.model_validate(v)
             for v in client.get(f"/runs/{run['run_id']}/failure-cases").json()]  # fmt: skip
    assert views and all(v.display_mode == "normal" and v.anonymization for v in views)
    old_id = views[0].id
    with Session(owner_engine) as session, session.begin():
        session.execute(
            update(m.FailureCase).where(m.FailureCase.id == old_id).values(anonymization=None)
        )
    old = FailureCaseView.model_validate(client.get(f"/failure-cases/{old_id}").json())
    assert old.display_mode == "hidden_unanonymized"
    assert old.artifacts is None  # không lộ khóa MinIO (đề xuất contract 002)
    assert all(url is None for url in old.urls.model_dump().values())


def _region(detection: dict[str, Any]) -> tuple[float, ...] | None:
    """Vùng rule_v1 của một ground truth đã map (class đích: person, car, truck)."""
    x1, y1, x2, y2 = detection["bbox"]
    name = detection.get("class_name")
    height = y2 - y1
    if name == "person":
        return (x1, y1, x2, y1 + height / 3)
    if name in ("car", "truck"):
        return (x1, y2 - 0.4 * height, x2, y2)
    return None
