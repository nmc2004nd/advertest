"""PatchArtifact hợp lệ theo contract (validation.md Phase 6, mục Patch)."""

from datetime import UTC, datetime

import numpy as np
import pytest

from advertest_contracts.models import PatchArtifact
from attacks.patch.artifact import build_artifact, load_patch, patch_files
from attacks.patch.training import TrainingState
from attacks.tests.transform_helpers import spec

NOW = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)


def _state(iterations: int = 200) -> TrainingState:
    patch = np.random.default_rng(0).random((3, 12, 12)).astype(np.float32)
    return TrainingState(
        patch=patch,
        iterations_done=iterations,
        objective_history=[float(i) for i in range(iterations)],
        seconds=12.5,
    )


def _build(state: TrainingState) -> tuple[PatchArtifact, bytes]:
    artifact, files = build_artifact(
        spec("adv_patch"),
        state,
        weights_sha256="a" * 64,
        training_slice_sha256="b" * 64,
        area_ratio=0.1,
        seed=0,
        created_at=NOW,
    )
    return artifact, files.npy


def test_artifact_valid_and_patch_round_trip() -> None:
    state = _state()
    artifact, npy = _build(state)
    PatchArtifact.model_validate(artifact.model_dump(mode="json"))
    assert artifact.side_px == 12 and artifact.iterations == 200
    prefix = f"patches/{artifact.key}/"
    assert artifact.npy_key == f"{prefix}{artifact.patch_sha256}.npy"
    assert artifact.png_key == f"{prefix}{artifact.patch_sha256}.png"
    np.testing.assert_array_equal(load_patch(npy, artifact), state.patch)


def test_same_patch_same_sha_and_png_decodes() -> None:
    a = patch_files(_state().patch)
    b = patch_files(_state().patch)
    assert a.sha256 == b.sha256 and a.png.startswith(b"\x89PNG")


def test_incomplete_training_cannot_register() -> None:
    with pytest.raises(ValueError, match="chưa đăng ký"):
        _build(_state(iterations=150))


def test_load_patch_checks_sha_and_shape() -> None:
    artifact, npy = _build(_state())
    with pytest.raises(ValueError, match="sha256"):
        load_patch(npy + b"x", artifact)
    other = patch_files(np.zeros((3, 5, 5), dtype=np.float32))
    wrong = artifact.model_copy(update={"patch_sha256": other.sha256})
    with pytest.raises(ValueError, match="side_px"):
        load_patch(other.npy, wrong)
