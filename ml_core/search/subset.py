"""Tập con cố định của slice cho giai đoạn tìm kiếm (requirements.md Phase 7, mục Tập con).

Tập con là `size` ảnh đầu tiên sau khi sắp theo `hash(seed, image_id)`: xác định, không phụ thuộc
thứ tự lưu trữ. Khóa hash có thêm `purpose` để thứ tự này không trùng với seed theo ảnh của attack
(`attacks/common/seed.py`).
"""

from __future__ import annotations

from collections.abc import Iterable

from advertest_contracts.hashing import sha256_of

_PURPOSE = "search_subset"


def subset_key(seed: int, image_id: str) -> str:
    """Khóa sắp xếp của một ảnh: sha256 của `canonical_json({"purpose", "seed", "image_id"})`."""
    if seed < 0:
        raise ValueError(f"seed phải không âm, nhận {seed}")
    if not image_id:
        raise ValueError("image_id không được rỗng")
    return sha256_of({"purpose": _PURPOSE, "seed": seed, "image_id": image_id})


def select_subset(image_ids: Iterable[str], seed: int, size: int) -> list[str]:
    """`size` ảnh đầu tiên của slice theo `subset_key`; slice không lớn hơn `size` thì trả cả slice
    (cùng thứ tự). Kết quả theo thứ tự khóa, không phải thứ tự đầu vào."""
    if size < 1:
        raise ValueError(f"size phải dương, nhận {size}")
    ids = list(image_ids)
    if len(set(ids)) != len(ids):
        raise ValueError("image_ids không được trùng")
    ordered = sorted(ids, key=lambda image_id: (subset_key(seed, image_id), image_id))
    return ordered[:size]


def eval_image_ids_sha256(image_ids: Iterable[str]) -> str:
    """`FingerprintInputs.eval_image_ids_sha256`: sha256 (canonical_json) của danh sách image_id
    đã sắp xếp. Chỉ dùng cho run trên tập con; run toàn slice để trường này null."""
    ids = sorted(image_ids)
    if not ids:
        raise ValueError("tập ảnh đánh giá không được rỗng")
    if len(set(ids)) != len(ids):
        raise ValueError("image_ids không được trùng")
    return sha256_of(ids)
