"""Interface chung cho mọi phép biến đổi ảnh (tech-stack.md mục 3.1).

Tầng sweep, metric, backend và frontend chỉ phụ thuộc vào interface này, không phụ thuộc
vào việc bên dưới là ART hay thư viện khác.
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from advertest_contracts.models import AttackSpec

# (N, C, H, W), float32, giá trị trong [0, 1], letterbox 640x640.
ImageBatch = npt.NDArray[np.float32]
# (N, 1, H, W), float32: 1 ở vùng ảnh thật, 0 ở vùng pad của letterbox.
MaskBatch = npt.NDArray[np.float32]


class Perturbation(Protocol):
    spec: AttackSpec

    def apply(
        self,
        images: ImageBatch,
        targets: list[dict[str, Any]],
        level: float,
        seed: int,
        mask: MaskBatch | None = None,
    ) -> ImageBatch:
        """Trả batch ảnh đã biến đổi, cùng shape và dtype với `images`.

        `targets` theo quy ước detector của ART: mỗi phần tử là dict `boxes`, `labels`,
        `scores`. `level` là giá trị tham số chính đang quét. `mask` giới hạn vùng được
        biến đổi: điểm ảnh có mask bằng 0 giữ nguyên; `None` là toàn ảnh.
        """
        ...
