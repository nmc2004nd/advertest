"""Sandbox chuyển `.pt` sang safetensors (Phase R3, đề xuất contract 003; mission.md nguyên tắc 10).

- Checkpoint Ultralytics thật (`yolov8n.pt`) → safetensors có kiến trúc, class, kích thước.
- State dict torchvision → safetensors; đoán kiến trúc và số class từ tên khóa.
- Nhánh torchvision dùng `weights_only=True`: pickle chạy lệnh bị từ chối, lệnh không chạy.
- Giao thức spool: worker ghi yêu cầu, sandbox trả `status.json`, worker đọc kết quả và dọn thư mục;
  metadata đọc từ header JSON, không unpickle.
"""

from __future__ import annotations

import json
import os
import pickle
import threading
from pathlib import Path

import pytest
import torch

from advertest_worker.converter import (
    REQUEST,
    STATUS,
    ConversionError,
    SpoolClient,
    metadata_report,
    run_one,
    safe_name,
    safetensors_metadata,
    serve_once,
)

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def _request(work: Path, data: bytes, framework: str, stem: str, suffix: str) -> None:
    work.mkdir(parents=True)
    (work / f"input{suffix}").write_bytes(data)
    (work / REQUEST).write_text(
        json.dumps({"framework": framework, "suffix": suffix, "stem": stem})
    )


def test_ultralytics_checkpoint(tmp_path: Path) -> None:
    work = tmp_path / "job"
    _request(work, (FIXTURES / "yolov8n.pt").read_bytes(), "ultralytics", "yolov8n", ".pt")
    status = run_one(work)
    assert status == {"ok": True}, status
    assert not (work / "input.pt").exists()  # file pickle bị xóa ngay sau khi chuyển
    meta = metadata_report(
        safetensors_metadata((work / "output.safetensors").read_bytes()), "ultralytics"
    )
    assert meta["architecture"] == "yolov8n" and meta["input_size"] == 640
    assert meta["class_names"] is not None and len(meta["class_names"]) == 80


def test_torchvision_state_dict(tmp_path: Path) -> None:
    state = {
        "rpn.head.conv.0.0.weight": torch.zeros(4, 4, 3, 3),
        "roi_heads.box_predictor.cls_score.weight": torch.zeros(5, 8, dtype=torch.float16),
        "roi_heads.box_predictor.cls_score.bias": torch.zeros(5),
    }
    source = tmp_path / "frcnn.pth"
    torch.save({"model": state}, source)
    work = tmp_path / "job"
    _request(work, source.read_bytes(), "torchvision", "frcnn", ".pth")
    assert run_one(work) == {"ok": True}
    meta = metadata_report(
        safetensors_metadata((work / "output.safetensors").read_bytes()), "torchvision"
    )
    assert meta["architecture"] == "fasterrcnn_resnet50_fpn_v2"
    assert meta["num_classes"] == 5 and meta["class_names"] is None


class _Evil:
    def __init__(self, marker: Path) -> None:
        self.marker = marker

    def __reduce__(self) -> tuple[object, tuple[str]]:
        return (os.system, (f"touch {self.marker}",))


def test_torchvision_rejects_code_in_pickle(tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    work = tmp_path / "job"
    _request(work, pickle.dumps({"w": _Evil(marker)}), "torchvision", "evil", ".pt")
    status = run_one(work)
    assert status["ok"] is False and "Không chuyển được" in status["error"]
    assert not marker.exists()


def test_timeout_and_bad_request(tmp_path: Path) -> None:
    work = tmp_path / "slow"
    _request(work, (FIXTURES / "yolov8n.pt").read_bytes(), "ultralytics", "yolov8n", ".pt")
    status = run_one(work, timeout_s=0.01)
    assert status["ok"] is False and "quá" in status["error"]
    bad = tmp_path / "bad"
    _request(bad, b"x", "onnx", "m", ".pt")
    assert run_one(bad)["ok"] is False


def test_safe_name() -> None:
    assert safe_name("../../YOLO 11n.PT") == ("YOLO_11n", ".pt")
    with pytest.raises(ConversionError):
        safe_name("m.onnx")


def test_spool_round_trip(tmp_path: Path) -> None:
    """Worker gửi file, "sandbox" (serve_once ở luồng khác) trả kết quả; thư mục được dọn."""
    stop = threading.Event()

    def sandbox() -> None:
        while not stop.is_set():
            if not serve_once(tmp_path):
                stop.wait(0.05)

    thread = threading.Thread(target=sandbox, daemon=True)
    thread.start()
    try:
        client = SpoolClient(tmp_path, timeout_s=120)
        data = client.convert("job-1", (FIXTURES / "yolov8n.pt").read_bytes(), "yolov8n.pt",
                              "ultralytics")  # fmt: skip
        assert safetensors_metadata(data)["framework"] == "ultralytics"
        assert not (tmp_path / "job-1").exists()
        with pytest.raises(ConversionError, match="Không chuyển được"):
            client.convert("job-2", b"rac", "x.pt", "torchvision")
    finally:
        stop.set()
        thread.join(timeout=5)


def test_spool_timeout_without_sandbox(tmp_path: Path) -> None:
    with pytest.raises(ConversionError, match="không trả lời"):
        SpoolClient(tmp_path, timeout_s=0.2).convert("job", b"x", "m.pt", "ultralytics")
    assert not (tmp_path / "job").exists()
    assert not list(tmp_path.glob(f"*/{STATUS}"))


def test_header_metadata_rejects_non_safetensors() -> None:
    with pytest.raises(ConversionError):
        safetensors_metadata(pickle.dumps({"a": 1}))
