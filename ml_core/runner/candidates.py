"""Ứng viên failure case trong lúc chạy theo batch (requirements.md Phase 3, mục Failure case).

`RunExecutor` giữ top-K ảnh theo `select_failure_cases`; khi một ảnh vào top-K, ảnh của nó được
giao cho `CandidateSink`. Khi hoàn tất, ứng viên được chọn thành failure case (`promote`), phần
còn lại bị bỏ (`discard`).

- `MemoryCandidates` (CLI, Phase 2): giữ bản sao ảnh trong RAM, bỏ ngay khi bị đẩy khỏi top-K;
  `promote` ghi PNG vào `<prefix>/cases/<image_id>/` (bố cục `LocalStore` của Phase 2).
- `StoreCandidates` (worker): ghi ngay PNG và thumbnail vào `<prefix>/candidates/<image_id>/`,
  để chạy tiếp sau gián đoạn không cần giữ ảnh. Ảnh bị đẩy khỏi top-K chỉ bị xóa khi hoàn tất:
  xóa sớm thì checkpoint trước đó (còn trỏ vào ảnh) sẽ hỏng nếu worker chết trước checkpoint kế.
  `promote` chép sang `<prefix>/cases/<case_id>/` rồi xóa bản ứng viên.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from advertest_contracts.models import CaseArtifacts
from ml_core.runner.images import amplified_perturbation, png_bytes, thumbnail_webp
from ml_core.store import ArtifactStore, DeletableStore


class CandidateSink(Protocol):
    def add(
        self, image_id: str, clean: NDArray[np.float32], adversarial: NDArray[np.float32]
    ) -> None:
        """Ảnh vừa vào top-K. `clean`, `adversarial` là (C, H, W) float32 [0, 1]."""
        ...

    def evict(self, image_id: str) -> None:
        """Ảnh bị đẩy khỏi top-K trong lúc chạy."""
        ...

    def promote(self, image_id: str, case_id: UUID) -> CaseArtifacts:
        """Ứng viên được chọn: lưu thành artifact của failure case."""
        ...

    def discard(self, image_id: str) -> None:
        """Ứng viên không được chọn (gọi khi hoàn tất)."""
        ...


def _images(
    clean: NDArray[np.float32], adversarial: NDArray[np.float32], linf_eps: float | None
) -> dict[str, bytes]:
    return {
        "clean.png": png_bytes(clean),
        "adversarial.png": png_bytes(adversarial),
        "perturbation.png": png_bytes(amplified_perturbation(clean, adversarial, linf_eps)),
    }


class MemoryCandidates:
    def __init__(self, store: ArtifactStore, prefix: str, linf_eps: float | None) -> None:
        self.store = store
        self.prefix = prefix
        self.linf_eps = linf_eps
        self._items: dict[str, tuple[NDArray[np.float32], NDArray[np.float32]]] = {}

    def add(
        self, image_id: str, clean: NDArray[np.float32], adversarial: NDArray[np.float32]
    ) -> None:
        # Ảnh thường là view của mảng cả batch: chép riêng để không giữ cả batch trong bộ nhớ.
        self._items[image_id] = (clean.copy(), adversarial.copy())

    def evict(self, image_id: str) -> None:
        self._items.pop(image_id, None)

    def promote(self, image_id: str, case_id: UUID) -> CaseArtifacts:
        if image_id not in self._items:
            raise KeyError(f"Không có ảnh ứng viên {image_id} trong bộ nhớ")
        clean, adversarial = self._items.pop(image_id)
        base = f"{self.prefix}/cases/{image_id}"
        for name, data in _images(clean, adversarial, self.linf_eps).items():
            self.store.put(f"{base}/{name}", data)
        return CaseArtifacts(
            clean_png=f"{base}/clean.png",
            adversarial_png=f"{base}/adversarial.png",
            perturbation_png=f"{base}/perturbation.png",
        )

    def discard(self, image_id: str) -> None:
        self._items.pop(image_id, None)


CANDIDATE_FILES = (
    "clean.png",
    "adversarial.png",
    "perturbation.png",
    "clean_thumb.webp",
    "adversarial_thumb.webp",
)


class StoreCandidates:
    def __init__(self, store: DeletableStore, prefix: str, linf_eps: float | None) -> None:
        self.store = store
        self.prefix = prefix
        self.linf_eps = linf_eps

    def candidate_prefix(self, image_id: str) -> str:
        return f"{self.prefix}/candidates/{image_id}"

    def add(
        self, image_id: str, clean: NDArray[np.float32], adversarial: NDArray[np.float32]
    ) -> None:
        files = {
            **_images(clean, adversarial, self.linf_eps),
            "clean_thumb.webp": thumbnail_webp(clean),
            "adversarial_thumb.webp": thumbnail_webp(adversarial),
        }
        base = self.candidate_prefix(image_id)
        for name in CANDIDATE_FILES:
            self.store.put(f"{base}/{name}", files[name])

    def evict(self, image_id: str) -> None:
        """Không xóa ngay (xem docstring của module)."""

    def promote(self, image_id: str, case_id: UUID) -> CaseArtifacts:
        source = self.candidate_prefix(image_id)
        base = f"{self.prefix}/cases/{case_id}"
        for name in CANDIDATE_FILES:
            # Gọi lại được: worker có thể chết giữa lúc hoàn tất rồi chạy lại `finalize`.
            if not self.store.exists(f"{base}/{name}"):
                self.store.put(f"{base}/{name}", self.store.get(f"{source}/{name}"))
        self.discard(image_id)
        return CaseArtifacts(
            clean_png=f"{base}/clean.png",
            adversarial_png=f"{base}/adversarial.png",
            perturbation_png=f"{base}/perturbation.png",
            clean_thumb=f"{base}/clean_thumb.webp",
            adversarial_thumb=f"{base}/adversarial_thumb.webp",
        )

    def discard(self, image_id: str) -> None:
        base = self.candidate_prefix(image_id)
        for name in CANDIDATE_FILES:
            self.store.delete(f"{base}/{name}")
