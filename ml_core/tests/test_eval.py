"""Luồng `eval` trên dữ liệu tổng hợp: YOLOv8n khởi tạo ngẫu nhiên (tên class COCO) và thư mục
KITTI nhỏ. Không cần mạng hay fixture; mAP trên fixture thật do test nghiệm thu kiểm tra."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from PIL import Image
from typer.testing import CliRunner
from ultralytics.models import YOLO
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    ClassMapping,
    ClassMappingBody,
    CleanEvalResult,
    ModelCard,
    SliceSpec,
    compute_mapping_sha256,
)
from ml_core.cli import app
from ml_core.cli import evaluate as evaluate_module
from ml_core.cli.cache import prediction_cache_key, save_predictions
from ml_core.cli.evaluate import (
    OutOfMemoryError,
    current_git_commit,
    describe_device,
    ground_truth,
    predict_slice,
    run_eval,
)
from ml_core.cli.viz import GT_COLOR, IGNORE_COLOR, PRED_COLOR, render
from ml_core.data.dataset import save_dataset
from ml_core.data.kitti import import_kitti
from ml_core.data.loader import SliceLoader
from ml_core.data.mapping import build_mapping, save_mapping
from ml_core.data.slice import create_slice, save_slice
from ml_core.data.tests.kitti_factory import label_line, make_kitti
from ml_core.models.register import register_model
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS
from ml_core.preprocess import letterbox
from ml_core.store import LocalStore

COMMIT = "1" * 40


@dataclass
class Env:
    store: LocalStore
    card: ModelCard
    slice_spec: SliceSpec
    mapping: ClassMapping


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> Env:
    tmp = tmp_path_factory.mktemp("eval")
    torch.manual_seed(0)
    yolo = YOLO("yolov8n.yaml")
    model = yolo.model
    assert isinstance(model, DetectionModel)
    # Tên class như COCO ở các vị trí preset kitti-coco dùng: person 0, car 2, truck 7.
    model.names = {i: {0: "person", 2: "car", 7: "truck"}.get(i, f"class{i}") for i in range(80)}
    weights = tmp / "yolov8n-random.pt"
    yolo.save(weights)

    root = make_kitti(
        tmp / "kitti",
        {
            "000001": [
                label_line("Car", (10, 2, 40, 38)),
                label_line("Cyclist", (40, 0, 60, 35)),
                label_line("DontCare", (60, 0, 70, 10)),
            ],
            "000002": [label_line("Pedestrian", (5, 2, 15, 39))],
            "000003": [label_line("Truck", (50, 0, 120, 39)), label_line("Car", (0, 0, 9, 20))],
        },
    )
    store = LocalStore(tmp / "store")
    manifest = import_kitti(root)
    save_dataset(store, manifest, root)
    check_images = np.stack([letterbox(Image.open(root / "image_2" / "000001.png"))[0]])
    card = register_model(store, weights, "yolov8n-random", check_images)
    slice_spec = create_slice(manifest, size=3, seed=0)
    save_slice(store, slice_spec)
    mapping = build_mapping(sha256_of(manifest), card, "kitti-coco")
    save_mapping(store, mapping)
    return Env(store, card, slice_spec, mapping)


@pytest.fixture(autouse=True)
def git_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_COMMIT", COMMIT)


def _no_model(*args: object, **kwargs: object) -> None:
    raise AssertionError("model không được nạp khi cache hit")


def _other_mapping(env: Env) -> ClassMapping:
    """Cùng model, cùng dataset, không lọc độ khó: nhiều ground truth hơn mapping preset."""
    body = ClassMappingBody(
        dataset_version_sha256=env.mapping.dataset_version_sha256,
        model_id=env.card.id,
        preset=None,
        classes=env.mapping.classes,
        difficulty=None,
    )
    sha = compute_mapping_sha256(body)
    mapping = ClassMapping(**body.model_dump(), id=content_id(sha), mapping_sha256=sha)
    save_mapping(env.store, mapping)
    return mapping


def test_eval_result_valid_and_cache(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    first = run_eval(env.store, env.card.id, env.slice_spec.id, env.mapping.id, "cpu").result
    CleanEvalResult.model_validate_json(first.model_dump_json())
    assert first.inference_params == DEFAULT_INFERENCE_PARAMS
    assert (first.inference_params.conf, first.inference_params.iou) == (0.001, 0.7)
    assert (first.inference_params.max_det, first.inference_params.operating_conf) == (300, 0.25)
    assert first.num_images == 3 and first.git_commit == COMMIT and first.device == "cpu"
    assert set(first.metrics.per_class) == {"car", "person", "truck"}

    # Lần hai cùng tham số: cache hit, model không được nạp.
    monkeypatch.setattr(evaluate_module, "load_detection_model", _no_model)
    second = run_eval(env.store, env.card.id, env.slice_spec.id, env.mapping.id, "cpu").result
    assert second.cache.hit and second.cache.key == first.cache.key
    assert second.metrics == first.metrics


def test_changing_conf_misses_cache(env: Env) -> None:
    base = run_eval(env.store, env.card.id, env.slice_spec.id, env.mapping.id, "cpu").result
    params = DEFAULT_INFERENCE_PARAMS.model_copy(update={"conf": 0.01})
    other = run_eval(
        env.store, env.card.id, env.slice_spec.id, env.mapping.id, "cpu", params=params
    ).result
    assert not other.cache.hit and other.cache.key != base.cache.key
    assert other.inference_params.conf == 0.01


def test_changing_mapping_hits_cache_and_recomputes(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = run_eval(env.store, env.card.id, env.slice_spec.id, env.mapping.id, "cpu").result
    other_mapping = _other_mapping(env)
    monkeypatch.setattr(evaluate_module, "load_detection_model", _no_model)
    other = run_eval(env.store, env.card.id, env.slice_spec.id, other_mapping.id, "cpu").result
    assert other.cache.hit and other.cache.key == base.cache.key
    assert other.class_mapping.id == other_mapping.id
    # Không lọc độ khó: Car cao 20 px trở thành ground truth.
    assert other.metrics.per_class["car"].num_gt == base.metrics.per_class["car"].num_gt + 1


def test_ground_truth_matches_loader(env: Env) -> None:
    loader = SliceLoader.from_ids(env.store, env.slice_spec.id, env.mapping.id)
    targets, ignores = ground_truth(loader)
    for batch in loader.batches(batch_size=2):
        for image_id, target, ignore in zip(
            batch.image_ids, batch.targets, batch.ignore, strict=True
        ):
            np.testing.assert_array_equal(targets[image_id]["boxes"], target["boxes"])
            np.testing.assert_array_equal(targets[image_id]["labels"], target["labels"])
            np.testing.assert_array_equal(ignores[image_id], ignore["boxes"])


def test_mapping_of_other_model_rejected(env: Env) -> None:
    with pytest.raises(ValueError, match="thuộc model"):
        run_eval(env.store, content_id("f" * 64), env.slice_spec.id, env.mapping.id, "cpu")


def test_out_of_memory_suggests_smaller_batch(env: Env) -> None:
    class Oom:
        def predict(self, x: Any, batch_size: int) -> Any:
            raise torch.cuda.OutOfMemoryError("CUDA out of memory")

    loader = SliceLoader.from_ids(env.store, env.slice_spec.id, env.mapping.id)
    with pytest.raises(OutOfMemoryError, match="--batch-size 4"):
        predict_slice(loader, Oom(), batch_size=8)


def test_cli_eval_writes_result(env: Env, tmp_path: Path) -> None:
    out = tmp_path / "result.json"
    args = ["--store-dir", str(env.store.root), "eval", "--model", str(env.card.id)]
    args += ["--slice", str(env.slice_spec.id), "--mapping", str(env.mapping.id)]
    args += ["--out", str(out), "--device", "cpu", "--batch-size", "2"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    parsed = CleanEvalResult.model_validate(json.loads(out.read_text()))
    assert parsed.slice.id == env.slice_spec.id
    assert "mAP@0.5" in result.stdout


def test_git_commit_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert current_git_commit() == (COMMIT, [])
    monkeypatch.setenv("GIT_COMMIT", "abc")
    with pytest.raises(ValueError, match="GIT_COMMIT"):
        current_git_commit()


def test_git_commit_from_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIT_COMMIT")
    commit, _ = current_git_commit()
    assert len(commit) == 40


def test_describe_cpu() -> None:
    assert describe_device("cpu") == "cpu"


def test_render_colors() -> None:
    image = np.zeros((3, 640, 640), dtype=np.float32)
    canvas = render(
        image,
        gt_boxes=np.array([[10, 10, 100, 100]]),
        ignore_boxes=np.array([[200, 200, 300, 300]]),
        pred_boxes=np.array([[400, 400, 500, 500]]),
        pred_texts=["car 0.90"],
    )
    pixels = np.asarray(canvas)
    assert canvas.size == (640, 640)
    assert tuple(pixels[50, 10]) == GT_COLOR
    assert tuple(pixels[250, 200]) == IGNORE_COLOR
    assert tuple(pixels[450, 400]) == PRED_COLOR


def test_cli_viz_writes_png(env: Env, tmp_path: Path) -> None:
    out = tmp_path / "viz"
    args = ["--store-dir", str(env.store.root), "viz", "--model", str(env.card.id)]
    args += ["--slice", str(env.slice_spec.id), "--mapping", str(env.mapping.id)]
    args += ["--out", str(out), "--n", "2", "--device", "cpu"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    files = sorted(out.glob("*.png"))
    assert [f.stem for f in files] == env.slice_spec.image_ids[:2]
    assert Image.open(files[0]).size == (640, 640)
    # Ảnh 000001 có Car (ground truth) và DontCare, Cyclist (ignore region).
    pixels = np.asarray(Image.open(out / "000001.png"))
    assert (pixels == GT_COLOR).all(axis=2).any()
    assert (pixels == IGNORE_COLOR).all(axis=2).any()


def test_cache_hit_reports_device_that_made_predictions(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prediction tạo trên GPU (giả lập) được dùng lại khi chạy trên CPU: kết quả ghi GPU."""
    params = DEFAULT_INFERENCE_PARAMS.model_copy(update={"conf": 0.002})
    key = prediction_cache_key(env.card.weights_sha256, env.slice_spec, params)
    empty = {"boxes": np.zeros((0, 4)), "labels": np.zeros(0), "scores": np.zeros(0)}
    save_predictions(
        env.store, key, {i: empty for i in env.slice_spec.image_ids}, "cuda:0 (NVIDIA Test)"
    )
    monkeypatch.setattr(evaluate_module, "load_detection_model", _no_model)
    result = run_eval(
        env.store, env.card.id, env.slice_spec.id, env.mapping.id, "cpu", params=params
    ).result
    assert result.cache.hit
    assert result.device == "cuda:0 (NVIDIA Test)"


def test_cache_miss_reports_current_device(env: Env) -> None:
    params = DEFAULT_INFERENCE_PARAMS.model_copy(update={"conf": 0.003})
    result = run_eval(
        env.store, env.card.id, env.slice_spec.id, env.mapping.id, "cpu", params=params
    ).result
    assert not result.cache.hit and result.device == "cpu"
