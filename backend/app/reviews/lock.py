"""Khóa experiment khi gửi duyệt: một kiểm tra chung cho mọi đường ghi (plan task 11). Trigger
DB (`0009`) chặn thêm một lớp nữa."""

from __future__ import annotations

from backend.app.db import models as m
from backend.app.services.errors import ExperimentLocked


def ensure_unlocked(experiment: m.Experiment) -> None:
    if experiment.locked_at is not None:
        raise ExperimentLocked(
            f"Experiment {experiment.name} đã gửi duyệt nên bị khóa; chỉ còn bình luận được"
        )
