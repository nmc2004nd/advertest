"""Train patch bằng RobustDPatch (validation.md Phase 6, mục Patch) trên estimator giả."""

import random

import numpy as np
import pytest

from advertest_contracts.models import AttackSpec
from attacks.art_adapter import UnsupportedAttack
from attacks.patch.training import PatchTrainer, TrainingState, paste
from attacks.tests import fake_detector as fd
from attacks.tests.transform_helpers import spec


def _spec(checkpoint_every: int = 2) -> AttackSpec:
    base = spec("adv_patch")
    assert base.training is not None
    training = base.training.model_copy(update={"checkpoint_every": checkpoint_every})
    return base.model_copy(update={"training": training})


def _trainer(seed: int = 0, checkpoint_every: int = 2) -> PatchTrainer:
    return PatchTrainer(
        _spec(checkpoint_every), fd.estimator(), area_ratio=0.1, seed=seed, batch_size=2
    )


def test_geometry_inside_real_region() -> None:
    geometry = _trainer().geometry(fd.images(3), fd.mask(3))
    assert geometry.side == 14  # round(sqrt(0.1 * 64 * 32))
    assert geometry.top >= fd.PAD and geometry.top + geometry.side <= fd.SIZE - fd.PAD


def test_objective_improves_and_patch_stays_valid() -> None:
    state = _trainer().train(fd.images(3), fd.mask(3), max_iter=6)
    assert state.iterations_done == 6 and len(state.objective_history) == 6
    assert state.objective_history[-1] > state.objective_history[0]
    assert state.patch.dtype == np.float32 and state.patch.shape == (3, 14, 14)
    assert state.patch.min() >= 0.0 and state.patch.max() <= 1.0
    assert state.seconds > 0


def test_resume_from_checkpoint_matches_uninterrupted_run() -> None:
    images, mask = fd.images(3), fd.mask(3)
    straight = _trainer().train(images, mask, max_iter=5)

    saved: list[bytes] = []
    first = _trainer().train(
        images,
        mask,
        max_iter=5,
        on_checkpoint=lambda s: saved.append(s.to_bytes()),
        on_progress=lambda s: s.iterations_done < 3,  # worker bị ngắt sau vòng 3
    )
    assert first.iterations_done == 3
    restored = TrainingState.from_bytes(saved[-1])
    assert restored.iterations_done == 2  # checkpoint gần nhất (checkpoint_every = 2)
    resumed = _trainer().train(images, mask, state=restored, max_iter=5)
    assert resumed.iterations_done == 5
    np.testing.assert_array_equal(resumed.patch, straight.patch)
    assert resumed.objective_history == straight.objective_history


def test_checkpoints_at_zero_and_every_n() -> None:
    seen: list[int] = []
    _trainer(checkpoint_every=2).train(
        fd.images(2), fd.mask(2), max_iter=5, on_checkpoint=lambda s: seen.append(s.iterations_done)
    )
    assert seen == [0, 2, 4]


def test_seed_changes_patch_and_global_random_restored() -> None:
    random.seed(123)
    before = random.getstate()
    a = _trainer(seed=0).train(fd.images(2), fd.mask(2), max_iter=2)
    assert random.getstate() == before
    b = _trainer(seed=1).train(fd.images(2), fd.mask(2), max_iter=2)
    assert not np.array_equal(a.patch, b.patch)


def test_state_round_trip_and_version() -> None:
    state = _trainer().train(fd.images(2), fd.mask(2), max_iter=2)
    again = TrainingState.from_bytes(state.to_bytes())
    np.testing.assert_array_equal(again.patch, state.patch)
    assert again.iterations_done == 2 and again.objective_history == state.objective_history
    assert again.random_state == state.random_state and again.seconds == state.seconds


def test_checkpoint_shape_must_match() -> None:
    state = TrainingState(patch=np.zeros((3, 5, 5), dtype=np.float32), iterations_done=1)
    with pytest.raises(ValueError, match="shape"):
        _trainer().train(fd.images(2), fd.mask(2), state=state, max_iter=2)


def test_rejects_non_patch_spec_and_bad_ratio() -> None:
    with pytest.raises(UnsupportedAttack):
        PatchTrainer(spec("fgsm"), fd.estimator(), area_ratio=0.1, seed=0, batch_size=1)
    with pytest.raises(ValueError, match="ngoài dải"):
        PatchTrainer(spec("adv_patch"), fd.estimator(), area_ratio=0.5, seed=0, batch_size=1)


def test_paste() -> None:
    images = np.zeros((2, 3, 8, 8), dtype=np.float32)
    out = paste(images, np.ones((3, 2, 2), dtype=np.float32), [1, 5], [2, 0])
    assert out[0, :, 1:3, 2:4].min() == 1 and out[1, :, 5:7, 0:2].min() == 1
    assert out.sum() == 2 * 3 * 4 and images.sum() == 0
