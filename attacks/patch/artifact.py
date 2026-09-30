"""File và `PatchArtifact` của patch đã train (requirements.md Phase 6, mục Patch attack; task 12).

- `patch.npy`: mảng float32 (3, side, side) trong [0, 1], `np.save` không pickle; `patch_sha256`
  là sha256 của đúng các byte này.
- `patch.png`: ảnh RGB 8 bit để người xem (làm tròn), không dùng để đánh giá.
- Khóa MinIO: `patches/<key>/<patch_sha256>.npy` và `.png` (đặt tên theo nội dung, người dùng
  chốt ở Group 3): hai worker cùng train một khóa không ghi đè file của nhau, nên file của bản đã
  đăng ký luôn khớp `patch_sha256`.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from PIL import Image

from advertest_contracts.models import AttackSpec, PatchArtifact, patch_prefix
from attacks.patch.geometry import patch_key
from attacks.patch.training import PatchArray, TrainingState, training_params


@dataclass(frozen=True)
class PatchFiles:
    npy: bytes
    png: bytes
    sha256: str


def patch_files(patch: PatchArray) -> PatchFiles:
    if patch.ndim != 3 or patch.shape[0] != 3 or patch.shape[1] != patch.shape[2]:
        raise ValueError(f"patch phải có shape (3, side, side), nhận {patch.shape}")
    array = np.ascontiguousarray(patch, dtype=np.float32)
    npy = io.BytesIO()
    np.save(npy, array, allow_pickle=False)
    png = io.BytesIO()
    rgb = np.round(np.clip(array, 0.0, 1.0) * 255.0).astype(np.uint8).transpose(1, 2, 0)
    Image.fromarray(rgb).save(png, format="PNG")
    data = npy.getvalue()
    return PatchFiles(npy=data, png=png.getvalue(), sha256=hashlib.sha256(data).hexdigest())


def build_artifact(
    spec: AttackSpec,
    state: TrainingState,
    *,
    weights_sha256: str,
    training_slice_sha256: str,
    area_ratio: float,
    seed: int,
    created_at: datetime,
) -> tuple[PatchArtifact, PatchFiles]:
    """`PatchArtifact` và file cần upload cho patch đã train đủ `training.max_iter` vòng."""
    params = training_params(spec)
    if state.iterations_done != params.max_iter:
        raise ValueError(
            f"Patch mới train {state.iterations_done}/{params.max_iter} vòng, chưa đăng ký được"
        )
    files = patch_files(state.patch)
    key = patch_key(
        spec,
        weights_sha256=weights_sha256,
        training_slice_sha256=training_slice_sha256,
        area_ratio=area_ratio,
        seed=seed,
    )
    prefix = patch_prefix(key)
    artifact = PatchArtifact(
        key=key,
        spec_sha256=spec.spec_sha256,
        weights_sha256=weights_sha256,
        training_slice_sha256=training_slice_sha256,
        area_ratio=area_ratio,
        seed=seed,
        side_px=int(state.patch.shape[1]),
        patch_sha256=files.sha256,
        png_key=f"{prefix}{files.sha256}.png",
        npy_key=f"{prefix}{files.sha256}.npy",
        iterations=state.iterations_done,
        training_seconds=state.seconds,
        objective_history=state.objective_history,
        created_at=created_at,
    )
    return artifact, files


def load_patch(npy: bytes, artifact: PatchArtifact) -> PatchArray:
    """Mảng patch từ `patch.npy`, kiểm tra sha256 và kích thước khớp `artifact`."""
    digest = hashlib.sha256(npy).hexdigest()
    if digest != artifact.patch_sha256:
        raise ValueError(f"patch.npy có sha256 {digest}, cần {artifact.patch_sha256}")
    patch = np.load(io.BytesIO(npy), allow_pickle=False)
    if patch.dtype != np.float32 or patch.shape != (3, artifact.side_px, artifact.side_px):
        raise ValueError(f"patch.npy có {patch.dtype} {patch.shape}, không khớp side_px")
    result: PatchArray = patch
    return result
