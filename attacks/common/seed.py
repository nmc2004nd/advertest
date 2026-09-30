"""Seed theo từng ảnh (requirements.md Phase 6, mục Seed theo từng ảnh).

`seed_i = hash(seed, image_id)`: phép biến đổi ngẫu nhiên của một ảnh chỉ phụ thuộc seed của run và
`image_id`, không phụ thuộc batch size hay thứ tự ảnh trong batch.
"""

from __future__ import annotations

import numpy as np

from advertest_contracts.hashing import sha256_of

# np.random.default_rng nhận mọi số nguyên không âm; giữ 64 bit để ít trùng.
_SEED_HEX_DIGITS = 16


def per_image_seed(seed: int, image_id: str) -> int:
    """Seed của một ảnh: 64 bit đầu của sha256(canonical_json({"seed", "image_id"}))."""
    if seed < 0:
        raise ValueError(f"seed phải không âm, nhận {seed}")
    if not image_id:
        raise ValueError("image_id không được rỗng")
    return int(sha256_of({"seed": seed, "image_id": image_id})[:_SEED_HEX_DIGITS], 16)


def image_rng(seed: int, image_id: str) -> np.random.Generator:
    """Bộ sinh số ngẫu nhiên riêng của một ảnh (không dùng trạng thái chung của numpy)."""
    return np.random.default_rng(per_image_seed(seed, image_id))


def target_image_id(target: dict[str, object], index: int) -> str:
    """`image_id` của một phần tử `targets` (bắt buộc từ Phase 6, interface `Perturbation`)."""
    image_id = target.get("image_id")
    if not isinstance(image_id, str) or not image_id:
        raise ValueError(f"targets[{index}] thiếu image_id (bắt buộc với phép biến đổi ngẫu nhiên)")
    return image_id
