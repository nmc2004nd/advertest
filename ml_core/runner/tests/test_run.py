"""Luồng `advertest run` trên dữ liệu tổng hợp: YOLOv8n khởi tạo ngẫu nhiên và KITTI nhỏ (3 ảnh).

Model ngẫu nhiên không đạt bài kiểm tra gradient, nên test ghi card với kết quả kiểm tra giả
(`supports_gradients` theo từng test). Kết quả trên fixture thật do test nghiệm thu kiểm tra.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
import torch
import yaml
from PIL import Image
from typer.testing import CliRunner
from ultralytics.models import YOLO
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.enums import RunStatus
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    GradientCheck,
    Manifest,
    ModelCard,
    RunResult,
    compute_failure_case_id,
)
from attacks.art_adapter import ArtPerturbation, build_perturbation
from attacks.registry import get_spec, load_catalog
from ml_core.cli import app
from ml_core.cli.evaluate import predict_slice
from ml_core.data.dataset import save_dataset
from ml_core.data.kitti import import_kitti
from ml_core.data.mapping import build_mapping, save_mapping
from ml_core.data.slice import create_slice, save_slice
from ml_core.data.tests.kitti_factory import label_line, make_kitti
from ml_core.metrics.attack import ImageAttackStats
from ml_core.metrics.filters import Prediction
from ml_core.models import register as register_module
from ml_core.models.register import register_model
from ml_core.preprocess import PAD_VALUE, letterbox
from ml_core.runner import run as run_module
from ml_core.runner.candidates import MemoryCandidates
from ml_core.runner.config import LocalRunConfig, experiment_id
from ml_core.runner.env import GitState
from ml_core.runner.executor import RunExecutor, build_context
from ml_core.runner.run import (
    RunReport,
    amplified_perturbation,
    letterbox_mask,
    run_config,
    run_prefix,
)
from ml_core.store import LocalStore

COMMIT = "1" * 40


@dataclass
class Base:
    root: Path
    card: ModelCard
    slice_id: str
    mapping_id: str


def _build(tmp: Path, supports_gradients: bool) -> Base:
    torch.manual_seed(0)
    yolo = YOLO("yolov8n.yaml")
    model = yolo.model
    assert isinstance(model, DetectionModel)
    model.names = {i: {0: "person", 2: "car", 7: "truck"}.get(i, f"class{i}") for i in range(80)}
    weights = tmp / "yolov8n-random.pt"
    yolo.save(weights)
    kitti = make_kitti(
        tmp / "kitti",
        {
            "000001": [label_line("Car", (10, 2, 40, 38)), label_line("DontCare", (60, 0, 70, 10))],
            "000002": [label_line("Pedestrian", (5, 2, 15, 39))],
            "000003": [label_line("Truck", (50, 0, 120, 39)), label_line("Car", (0, 0, 9, 20))],
        },
    )
    store = LocalStore(tmp / "store")
    manifest = import_kitti(kitti)
    save_dataset(store, manifest, kitti)
    check = GradientCheck(
        passed=supports_gradients,
        checked_at=datetime(2026, 9, 28, tzinfo=UTC),
        details=None if supports_gradients else "loss không tăng (giả lập trong test)",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(register_module, "run_gradient_check", lambda *a, **k: check)
        card = register_model(
            store, weights, "yolov8n-random", np.zeros((1, 3, 640, 640), np.float32)
        )
    slice_spec = create_slice(manifest, size=3, seed=0)
    save_slice(store, slice_spec)
    mapping = build_mapping(sha256_of(manifest), card, "kitti-coco")
    save_mapping(store, mapping)
    return Base(tmp / "store", card, str(slice_spec.id), str(mapping.id))


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Base:
    return _build(tmp_path_factory.mktemp("run"), supports_gradients=True)


@pytest.fixture
def store(base: Base, tmp_path: Path) -> LocalStore:
    """Bản sao riêng của store cho từng test (store là bất biến)."""
    shutil.copytree(base.root, tmp_path / "store")
    return LocalStore(tmp_path / "store")


@pytest.fixture(autouse=True)
def git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_COMMIT", COMMIT)
    monkeypatch.delenv("DOCKER_IMAGE_DIGEST", raising=False)


def _attack(name: str, levels: list[float], seed: int = 0) -> dict[str, Any]:
    spec = get_spec(load_catalog(), name=name)
    return {
        "attack_spec_id": str(spec.id),
        "spec_sha256": spec.spec_sha256,
        "mode": "grid",
        "grid": {"levels": levels},
        "seed": seed,
    }


def _config(base: Base, attacks: list[dict[str, Any]], **overrides: Any) -> LocalRunConfig:
    return LocalRunConfig.model_validate(
        {
            "model_id": str(base.card.id),
            "slice_id": base.slice_id,
            "mapping_id": base.mapping_id,
            "attacks": attacks,
            "device": "cpu",
            "batch_size": 2,
            "failure_cases_per_run": 2,
            **overrides,
        }
    )


class Spy:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, spec: Any, estimator: Any) -> ArtPerturbation:
        self.calls += 1
        return build_perturbation(spec, estimator)


def _hash(store: LocalStore, key: str) -> str:
    return hashlib.sha256(store.get(key)).hexdigest()


def _manifest(store: LocalStore, result: RunResult) -> Manifest:
    assert result.manifest_uri is not None
    return Manifest.model_validate_json(store.get(result.manifest_uri))


def test_run_completes_with_valid_outputs(base: Base, store: LocalStore) -> None:
    config = _config(base, [_attack("fgsm", [0, 4]), _attack("pgd_l2", [1])])
    report = run_config(store, config)
    assert [o.result.status for o in report.outcomes] == [RunStatus.COMPLETED] * 3
    for outcome in report.outcomes:
        result = RunResult.model_validate_json(outcome.result.model_dump_json())
        assert result.experiment_id == experiment_id(config)
        assert result.cost is None and result.gpu_seconds > 0
        assert result.progress.images_done == result.progress.images_total == 3
        prefix = run_prefix(result.fingerprint)
        assert outcome.prefix == prefix
        assert RunResult.model_validate_json(store.get(f"{prefix}/result.json")) == result
        manifest = _manifest(store, result)
        assert manifest.fingerprint == result.fingerprint == sha256_of(manifest.fingerprint_inputs)
        assert manifest.fingerprint_inputs.git_commit == COMMIT
        assert not manifest.fingerprint_inputs.git_dirty
        assert manifest.fingerprint_inputs.docker_image_digest == "none"
        assert manifest.environment.compute_target_id is None
        assert manifest.environment.gpu_model is None
        assert result.metrics is not None
        assert result.metrics.clean.map50 == report.clean.map50
    # level = 0: ảnh sau tấn công trùng ảnh gốc nên metric trùng metric sạch.
    level0 = report.outcomes[0].result.metrics
    assert level0 is not None
    assert level0.attacked == level0.clean and level0.absolute_drop == 0
    assert level0.attack_success_rate in (0.0, None)
    assert len({o.result.fingerprint for o in report.outcomes}) == 3


def test_second_run_is_cached_without_attacking(base: Base, store: LocalStore) -> None:
    config = _config(base, [_attack("fgsm", [2, 4])])
    first = run_config(store, config)
    keys = store.list()
    spy = Spy()
    second = run_config(store, config, perturbation_factory=spy)
    assert spy.calls == 0
    assert store.list() == keys, "run cached không ghi gì vào store"
    for before, after in zip(first.outcomes, second.outcomes, strict=True):
        result = after.result
        assert result.status == RunStatus.SKIPPED
        assert result.status_reason is not None and result.status_reason.code == "cached"
        assert result.fingerprint == before.result.fingerprint
        assert result.manifest_uri == before.result.manifest_uri
        assert result.run_id != before.result.run_id
        assert after.prefix is None


def test_force_writes_rerun_without_touching_original(base: Base, store: LocalStore) -> None:
    config = _config(base, [_attack("fgsm", [4])])
    first = run_config(store, config).outcomes[0].result
    original = f"{run_prefix(first.fingerprint)}/result.json"
    digest = _hash(store, original)
    rerun = run_config(store, config, force=True).outcomes[0]
    assert rerun.result.status == RunStatus.COMPLETED
    assert rerun.prefix == f"{run_prefix(first.fingerprint)}/reruns/{rerun.result.run_id}"
    assert store.exists(f"{rerun.prefix}/result.json")
    assert _hash(store, original) == digest
    assert rerun.result.fingerprint == first.fingerprint
    assert first.metrics is not None and rerun.result.metrics is not None
    assert rerun.result.metrics.attacked.map50 == pytest.approx(
        first.metrics.attacked.map50, abs=0.005
    )


def test_batch_size_does_not_change_fingerprint_or_result(base: Base, store: LocalStore) -> None:
    one = run_config(store, _config(base, [_attack("pgd_linf", [8])], batch_size=1))
    three = run_config(store, _config(base, [_attack("pgd_linf", [8])], batch_size=3), force=True)
    a, b = one.outcomes[0].result, three.outcomes[0].result
    assert a.fingerprint == b.fingerprint
    assert a.metrics is not None and b.metrics is not None
    assert b.metrics.attacked.map50 == pytest.approx(a.metrics.attacked.map50, abs=0.005)
    if a.metrics.attack_success_rate is not None:
        assert b.metrics.attack_success_rate == pytest.approx(
            a.metrics.attack_success_rate, abs=0.01
        )


def test_fingerprint_changes_with_level_seed_and_spec(base: Base, store: LocalStore) -> None:
    report = run_config(
        store,
        _config(
            base, [_attack("fgsm", [2, 4]), _attack("fgsm", [4], seed=1), _attack("pgd_linf", [4])]
        ),
    )
    assert len({o.result.fingerprint for o in report.outcomes}) == 4


class _FakeProvenance:
    def __init__(self, commit: str, dirty: bool) -> None:
        self.state = GitState(commit=commit, dirty=dirty)

    def git(self) -> GitState:
        return self.state

    def lib_versions(self) -> Any:
        return register_module.lib_versions()

    def docker_image_digest(self) -> str:
        return "sha256:" + "c" * 64


def test_git_dirty_goes_into_manifest(base: Base, store: LocalStore) -> None:
    report = run_config(
        store, _config(base, [_attack("fgsm", [4])]), provenance=_FakeProvenance(COMMIT, True)
    )
    assert report.git_dirty
    assert _manifest(store, report.outcomes[0].result).fingerprint_inputs.git_dirty


def test_provenance_seam_goes_into_fingerprint_and_manifest(base: Base, store: LocalStore) -> None:
    commit = "2" * 40
    report = run_config(
        store,
        _config(base, [_attack("fgsm", [4])]),
        provenance=_FakeProvenance(commit, dirty=True),
    )
    assert report.git_dirty
    inputs = _manifest(store, report.outcomes[0].result).fingerprint_inputs
    assert (inputs.git_commit, inputs.git_dirty) == (commit, True)
    assert inputs.docker_image_digest == "sha256:" + "c" * 64
    default = run_config(store, _config(base, [_attack("fgsm", [4])]))
    assert default.outcomes[0].result.fingerprint != report.outcomes[0].result.fingerprint


def test_clean_predictor_seam_is_used_only_without_cache(base: Base, store: LocalStore) -> None:
    calls: list[int] = []

    def predictor(loader: Any, estimator: Any, batch_size: int) -> dict[str, Prediction]:
        calls.append(batch_size)
        return predict_slice(loader, estimator, batch_size)

    config = _config(base, [_attack("fgsm", [4])])
    run_config(store, config, clean_predictor=predictor)
    assert calls == [config.batch_size]
    run_config(store, config, force=True, clean_predictor=predictor)
    assert calls == [config.batch_size]


class _Boom:
    """Perturbation lỗi ở level 4, chạy bình thường ở level khác."""

    def __init__(self, inner: ArtPerturbation) -> None:
        self.inner = inner
        self.spec = inner.spec

    def eps(self, level: float) -> float:
        return self.inner.eps(level)

    def apply(self, images: Any, targets: Any, level: float, seed: int, mask: Any = None) -> Any:
        if level == 4:
            raise RuntimeError("lỗi giả lập")
        return self.inner.apply(images, targets, level, seed, mask)


def _boom_factory(spec: Any, estimator: Any) -> ArtPerturbation:
    return cast(ArtPerturbation, _Boom(build_perturbation(spec, estimator)))


def test_failed_run_does_not_stop_others(base: Base, store: LocalStore) -> None:
    config = _config(base, [_attack("fgsm", [2, 4, 8])])
    report = run_config(store, config, perturbation_factory=_boom_factory)
    statuses = [o.result.status for o in report.outcomes]
    assert statuses == [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.COMPLETED]
    failed = report.outcomes[1]
    assert failed.result.status_reason is not None
    assert "lỗi giả lập" in failed.result.status_reason.message
    assert (
        failed.prefix == f"{run_prefix(failed.result.fingerprint)}/attempts/{failed.result.run_id}"
    )
    assert RunResult.model_validate_json(store.get(f"{failed.prefix}/result.json")) == failed.result
    assert not store.exists(f"{run_prefix(failed.result.fingerprint)}/result.json")
    # Chạy lại: run lỗi được chạy bình thường vào thư mục chính.
    again = run_config(store, config).outcomes[1]
    assert again.result.status == RunStatus.COMPLETED
    assert again.prefix == run_prefix(failed.result.fingerprint)


def test_incompatible_model_is_skipped(tmp_path: Path) -> None:
    base = _build(tmp_path, supports_gradients=False)
    store = LocalStore(base.root)
    spy = Spy()
    report = run_config(store, _config(base, [_attack("fgsm", [4])]), perturbation_factory=spy)
    result = report.outcomes[0].result
    assert spy.calls == 0
    assert result.status == RunStatus.SKIPPED
    assert result.status_reason is not None and result.status_reason.code == "incompatible"
    assert store.exists(f"{report.outcomes[0].prefix}/result.json")
    assert _manifest(store, result).fingerprint == result.fingerprint


def test_letterbox_mask_matches_letterbox() -> None:
    image = Image.new("RGB", (124, 40), (255, 255, 255))
    array, info = letterbox(image)
    mask = letterbox_mask([info])[0, 0]
    real = np.all(array == 1.0, axis=0)
    assert np.array_equal(mask == 1, real)
    assert np.all(array[:, mask == 0] == np.float32(PAD_VALUE))


def test_amplified_perturbation() -> None:
    clean = np.full((3, 2, 2), 0.5, np.float32)
    adv = clean.copy()
    adv[0, 0, 0] += 4 / 255
    adv[0, 0, 1] -= 8 / 255
    linf = amplified_perturbation(clean, adv, 8 / 255)
    assert linf[0, 0, 0] == pytest.approx(0.75, abs=1e-6)
    assert linf[0, 0, 1] == pytest.approx(0.0, abs=1e-6)
    assert linf[1, 1, 1] == 0.5
    l2 = amplified_perturbation(clean, adv, None)
    assert l2[0, 0, 1] == pytest.approx(0.0, abs=1e-6) and l2[0, 0, 0] == pytest.approx(
        0.75, abs=1e-6
    )
    assert np.all(amplified_perturbation(clean, clean, None) == 0.5)


def test_failure_case_record_and_pngs(base: Base, store: LocalStore) -> None:
    config = _config(base, [_attack("fgsm", [4])])
    runner = run_module.Runner(store, config)
    loader_batch = next(runner.loader.batches(1))
    target = loader_batch.targets[0]
    image = loader_batch.images[0]
    adversarial = np.clip(image + 4 / 255, 0, 1).astype(np.float32)
    empty: Prediction = {
        "boxes": np.zeros((0, 4), np.float32),
        "labels": np.zeros(0, np.int64),
        "scores": np.zeros(0, np.float32),
    }
    fp_pred: Prediction = {
        "boxes": np.asarray([[300, 300, 340, 340], [0, 0, 5, 5]], np.float32),
        "labels": np.asarray([2, 14], np.int64),
        "scores": np.asarray([0.9, 0.9], np.float32),
    }
    stats = ImageAttackStats(correct=len(target["labels"]), lost=1, clean_fp=0, attacked_fp=1)
    image_id = loader_batch.image_ids[0]
    context = build_context(
        runner.loader, {i: empty for i in runner.slice.image_ids}, runner.params, 2
    )
    candidates = MemoryCandidates(store, "runs/x", 4 / 255)
    executor = RunExecutor(
        fingerprint="e" * 64,
        level=4,
        seed=0,
        perturbation=cast(ArtPerturbation, None),
        estimator=None,
        context=context,
        candidates=candidates,
    )
    # Trạng thái như sau khi process_batch đưa ảnh vào top-K.
    executor.predictions[image_id] = fp_pred
    executor.stats[image_id] = stats
    executor.top = [image_id]
    executor.case_inputs[image_id] = {
        "gt_boxes": target["boxes"].tolist(),
        "gt_labels": target["labels"].tolist(),
        "ignore_boxes": loader_batch.ignore[0]["boxes"].tolist(),
        "ignore_sources": loader_batch.ignore[0]["sources"],
    }
    candidates.add(image_id, image, adversarial, [])
    run_id = runner.experiment_id
    record = executor._record(run_id, image_id, stats)
    assert record.id == compute_failure_case_id("e" * 64, run_id, image_id)
    assert record.severity_score == 1.5
    assert [b.class_name for b in record.detections.attacked] == ["car"]  # class 14 bị lọc
    assert all(b.score is None for b in record.detections.ground_truth)
    assert len(record.detections.ground_truth) == len(target["labels"])
    assert len(record.detections.ignore_regions) == len(loader_batch.ignore[0]["boxes"])
    for key in (
        record.artifacts.clean_png,
        record.artifacts.adversarial_png,
        record.artifacts.perturbation_png,
    ):
        png = Image.open(io.BytesIO(store.get(key)))
        assert png.size == (640, 640) and png.mode == "RGB"


def test_report_type(base: Base, store: LocalStore) -> None:
    report = run_config(store, _config(base, [_attack("fgsm", [0])]))
    assert isinstance(report, RunReport) and not report.git_dirty


def _write_config(path: Path, config: LocalRunConfig) -> Path:
    path.write_text(yaml.safe_dump(config.model_dump(mode="json")))
    return path


def test_cli_run_and_show(base: Base, store: LocalStore, tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "run.yaml", _config(base, [_attack("fgsm", [0, 4])]))
    runner = CliRunner()
    args = ["--store-dir", str(store.root), "run", "--config", str(config_path)]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    results = [RunResult.model_validate(r) for r in json.loads(first.stdout)]
    assert [r.status for r in results] == [RunStatus.COMPLETED] * 2
    for column in ("attack", "mAP sạch", "mAP tấn công", "relative drop", "ASR", "trạng thái"):
        assert column in first.stderr
    assert "completed" in first.stderr

    second = runner.invoke(app, args)
    assert second.exit_code == 0, second.output
    assert all(r["status"] == "skipped" for r in json.loads(second.stdout))
    assert "skipped (cached)" in second.stderr

    forced = runner.invoke(app, [*args, "--force"])
    assert forced.exit_code == 0, forced.output

    fp = results[1].fingerprint
    shown = runner.invoke(app, ["--store-dir", str(store.root), "run", "show", fp])
    assert shown.exit_code == 0, shown.output
    assert RunResult.model_validate_json(shown.stdout) == results[1]
    assert "manifest.json" in shown.stderr and "reruns" in shown.stderr

    missing = runner.invoke(app, ["--store-dir", str(store.root), "run", "show", "0" * 64])
    assert missing.exit_code == 1 and "Không có run" in missing.stderr


def test_cli_run_errors(base: Base, store: LocalStore, tmp_path: Path) -> None:
    runner = CliRunner()
    no_config = runner.invoke(app, ["--store-dir", str(store.root), "run"])
    assert no_config.exit_code == 2
    bad = tmp_path / "bad.yaml"
    bad.write_text("model_id: 1\n")
    result = runner.invoke(app, ["--store-dir", str(store.root), "run", "--config", str(bad)])
    assert result.exit_code == 1 and "Lỗi" in result.stderr


def test_error_while_building_attack_fails_only_that_run(base: Base, store: LocalStore) -> None:
    def factory(spec: Any, estimator: Any) -> ArtPerturbation:
        if spec.name == "fgsm":
            raise RuntimeError("không dựng được attack (giả lập)")
        return build_perturbation(spec, estimator)

    config = _config(base, [_attack("fgsm", [4]), _attack("pgd_l2", [1])])
    report = run_config(store, config, perturbation_factory=factory)
    failed, other = report.outcomes
    assert failed.result.status == RunStatus.FAILED
    assert failed.result.status_reason is not None
    assert "không dựng được" in failed.result.status_reason.message
    assert failed.prefix is not None and "/attempts/" in failed.prefix
    assert store.exists(f"{failed.prefix}/result.json")
    assert other.result.status == RunStatus.COMPLETED


def test_memory_candidates_keep_own_copies(tmp_path: Path) -> None:
    batch = np.zeros((4, 3, 8, 8), np.float32)
    candidates = MemoryCandidates(LocalStore(tmp_path), "runs/x", None)
    for i in range(4):
        candidates.add(f"{i:06d}", batch[i], batch[i], [])
    candidates.evict("000000")
    assert list(candidates._items) == ["000001", "000002", "000003"]
    for shown in candidates._items.values():
        assert all(image.base is None for image in shown.values())


# ---------------------------------------------------------------- Phase 6


def test_cli_runs_corruption_and_occlusion(base: Base, store: LocalStore) -> None:
    """Runner dựng perturbation bằng `attacks/factory.py` (plan task 17, phần ml-core)."""
    config = _config(base, [_attack("fog", [1]), _attack("bbox_occlusion", [0.5])])
    report = run_module.Runner(store, config).run()
    assert [o.spec_name for o in report.outcomes] == ["fog", "bbox_occlusion"]
    assert all(o.result.status == RunStatus.COMPLETED for o in report.outcomes)


def test_cli_rejects_patch(base: Base, store: LocalStore) -> None:
    with pytest.raises(ValueError, match="chỉ chạy qua worker"):
        run_module.Runner(store, _config(base, [_attack("adv_patch", [0.1])]))
