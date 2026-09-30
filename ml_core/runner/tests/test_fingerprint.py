from pathlib import Path
from typing import Any

import pytest

from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import ClassMapping, LibVersions, SliceSpec
from attacks.registry import get_spec, load_catalog
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS
from ml_core.runner.fingerprint import build_fingerprint_inputs, fingerprint

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks"
SLICE = SliceSpec.model_validate_json((MOCKS / "slice_spec/kitti_fixture.json").read_text())
MAPPING = ClassMapping.model_validate_json((MOCKS / "class_mapping/kitti_coco.json").read_text())
VERSIONS = LibVersions(
    torch="2.14.0", art="1.20.1", ultralytics="8.4.163", torchmetrics="1.9.0", numpy="2.4.6"
)


def _inputs(**overrides: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "spec": get_spec(load_catalog(), name="pgd_linf"),
        "level": 8.0,
        "seed": 0,
        "params": DEFAULT_INFERENCE_PARAMS,
        "mapping": MAPPING,
        "slice_spec": SLICE,
        "weights_sha256": "a" * 64,
        "git_commit": "1" * 40,
        "git_dirty": False,
        "lib_versions": VERSIONS,
        "docker_image_digest": "none",
    }
    args.update(overrides)
    return args


def _fp(**overrides: Any) -> str:
    return fingerprint(build_fingerprint_inputs(**_inputs(**overrides)))


def test_fingerprint_is_sha_of_inputs() -> None:
    inputs = build_fingerprint_inputs(**_inputs())
    assert fingerprint(inputs) == sha256_of(inputs)
    assert inputs.params == {"eps": 8.0}
    assert _fp() == _fp()


@pytest.mark.parametrize(
    "overrides",
    [
        {"level": 4.0},
        {"seed": 1},
        {"spec": get_spec(load_catalog(), name="fgsm")},
        {"mapping": MAPPING.model_copy(update={"mapping_sha256": "c" * 64})},
        {"params": DEFAULT_INFERENCE_PARAMS.model_copy(update={"conf": 0.01})},
        {"weights_sha256": "b" * 64},
        {"git_dirty": True},
    ],
)
def test_fingerprint_changes(overrides: dict[str, Any]) -> None:
    assert _fp(**overrides) != _fp()


def test_patch_key_changes_fingerprint_only_when_set() -> None:
    """Phase 6 (plan task 18): run không dùng patch giữ nguyên fingerprint cũ."""
    assert _fp(patch_key=None) == _fp()
    assert "patch_key" not in build_fingerprint_inputs(**_inputs()).model_dump(mode="json")
    with_patch = build_fingerprint_inputs(**_inputs(patch_key="c" * 64))
    assert with_patch.model_dump(mode="json")["patch_key"] == "c" * 64
    assert fingerprint(with_patch) != _fp()
