"""Sandbox chuyển đổi `.pt`/`.pth` sang `.safetensors` (Phase R3, đề xuất contract 003; mission.md
nguyên tắc 10).

Hai phía, nối bằng thư mục spool dùng chung (volume Docker), không qua mạng:

- **Sandbox** (`python -m advertest_worker.converter serve --spool /app/convert`, service
  `converter`): container `network_mode: none`, rootfs chỉ đọc, không capability, không biến môi
  trường bí mật, giới hạn RAM, CPU, số process. Mỗi file chạy trong một tiến trình con riêng
  (`convert`) với môi trường tối thiểu, rlimit CPU và kích thước file, cắt cứng khi quá giờ. Đây
  là nơi duy nhất mở pickle từ web.
- **Worker công cụ** (`SpoolClient`): ghi file vào `<spool>/<job>/`, chờ `status.json`, đọc kết quả.
  Worker không bao giờ mở pickle: metadata đọc từ header JSON của safetensors.

Giao thức trong `<spool>/<job>/`: worker ghi `input<.pt|.pth>` rồi `request.json` (đổi tên nguyên
tử, ghi sau cùng); sandbox ghi `output.safetensors` rồi `status.json` (`{"ok": true}` hoặc
`{"ok": false, "error": "..."}`), xóa file input. Worker xóa cả thư mục sau khi đọc.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONVERT_TIMEOUT_S = 120  # một file, trong sandbox
WAIT_TIMEOUT_S = 300  # phía worker: gồm thời gian chờ lượt và nạp thư viện
CPU_LIMIT_S = 180
FILE_LIMIT_BYTES = 1024**3  # kết quả float32 của checkpoint 500 MB vẫn dưới 1 GB
POLL_S = 0.5
MAX_ERROR_CHARS = 2000
REQUEST = "request.json"
STATUS = "status.json"
OUTPUT = "output.safetensors"
FRAMEWORKS = ("ultralytics", "torchvision")


class ConversionError(Exception):
    """Sandbox không chuyển được file (file hỏng, kiến trúc không hỗ trợ, quá giờ)."""


# ---------------------------------------------------------------------------- đọc kết quả (worker)


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(filename: str) -> tuple[str, str]:
    """(tên không đuôi, đuôi) an toàn để đặt file trong spool; Ultralytics đoán kiến trúc từ tên
    file (ví dụ `yolo11n.pt`) khi checkpoint không ghi."""
    path = Path(filename)
    suffix = path.suffix.lower()
    if suffix not in (".pt", ".pth"):
        raise ConversionError(f"Đuôi file {suffix or '(không có)'} không chuyển đổi được")
    stem = _UNSAFE.sub("_", path.stem).strip("._")[:100] or "model"
    return stem, suffix


def safetensors_metadata(data: bytes) -> dict[str, str]:
    """`__metadata__` trong header JSON của safetensors; không nạp tensor, không unpickle."""
    if len(data) < 9:
        raise ConversionError("Kết quả không phải safetensors (quá ngắn)")
    length = int.from_bytes(data[:8], "little")
    if not 0 < length <= min(len(data) - 8, 100 * 1024 * 1024) or data[8:9] != b"{":
        raise ConversionError("Kết quả không phải safetensors (header sai)")
    header = json.loads(data[8 : 8 + length])
    meta = header.get("__metadata__") or {}
    if not isinstance(meta, dict):
        raise ConversionError("Header safetensors có __metadata__ sai kiểu")
    return {str(k): str(v) for k, v in meta.items()}


def metadata_report(meta: dict[str, str], framework: str) -> dict[str, Any]:
    """Metadata của safetensors → dict theo `ModelConvertMetadata`."""
    if meta.get("framework") != framework:
        raise ConversionError(f"Kết quả có framework {meta.get('framework')!r}, cần {framework}")
    names = json.loads(meta["names"]) if "names" in meta else None
    return {
        "framework": framework,
        "architecture": meta.get("architecture") or None,
        "class_names": names or None,
        "input_size": int(meta["imgsz"]) if meta.get("imgsz") else None,
        "num_classes": int(meta["num_classes"]) if meta.get("num_classes") else None,
    }


class SpoolClient:
    """Phía worker công cụ: gửi file vào spool, chờ sandbox trả kết quả."""

    def __init__(self, spool: Path, timeout_s: float = WAIT_TIMEOUT_S) -> None:
        self.spool = spool
        self.timeout_s = timeout_s

    def convert(self, job_id: str, data: bytes, filename: str, framework: str) -> bytes:
        stem, suffix = safe_name(filename)
        work = self.spool / job_id
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        try:
            (work / f"input{suffix}").write_bytes(data)
            request = work / f".{REQUEST}.tmp"
            request.write_text(json.dumps({"framework": framework, "suffix": suffix, "stem": stem}))
            request.rename(work / REQUEST)
            deadline = time.monotonic() + self.timeout_s
            while not (work / STATUS).exists():
                if time.monotonic() > deadline:
                    raise ConversionError(
                        f"Sandbox chuyển đổi không trả lời sau {self.timeout_s:.0f} giây"
                        " (service converter có đang chạy không?)"
                    )
                time.sleep(POLL_S)
            status = json.loads((work / STATUS).read_text())
            if not status.get("ok"):
                raise ConversionError(
                    str(status.get("error") or "Sandbox báo lỗi")[:MAX_ERROR_CHARS]
                )
            return (work / OUTPUT).read_bytes()
        finally:
            shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------- chuyển đổi (sandbox)


def _torchvision_architecture(keys: set[str]) -> str | None:
    if any(k.startswith("roi_heads.box_predictor.") for k in keys):
        return "fasterrcnn_resnet50_fpn_v2" if "rpn.head.conv.0.0.weight" in keys else None
    if any(k.startswith("head.regression_head.bbox_ctrness") for k in keys):
        return "fcos_resnet50_fpn"
    if any(k.startswith("head.classification_head.") for k in keys):
        return "retinanet_resnet50_fpn_v2"
    return None


def _torchvision_classes(state: dict[str, Any], architecture: str | None) -> int | None:
    if "roi_heads.box_predictor.cls_score.weight" in state:
        return int(state["roi_heads.box_predictor.cls_score.weight"].shape[0])
    logits = state.get("head.classification_head.cls_logits.weight")
    if logits is None:
        return None
    count = int(logits.shape[0])
    if architecture == "retinanet_resnet50_fpn_v2":
        return count // 9 if count % 9 == 0 else None  # 9 anchor mỗi vị trí
    return count


def convert_torchvision(source: Path, output: Path) -> None:
    """State dict torchvision: `torch.load(weights_only=True)` chỉ nhận tensor và kiểu cơ bản."""
    import torch
    from safetensors.torch import save_file

    loaded = torch.load(source, map_location="cpu", weights_only=True)
    if isinstance(loaded, dict):
        for key in ("model", "state_dict", "model_state_dict"):
            if isinstance(loaded.get(key), dict):
                loaded = loaded[key]
                break
    if not isinstance(loaded, dict) or not loaded:
        raise ConversionError("File torchvision phải là state dict (dict tên → tensor)")
    state = {
        str(k): (v.float() if v.is_floating_point() else v).detach().contiguous()
        for k, v in loaded.items()
        if isinstance(v, torch.Tensor)
    }
    if len(state) != len(loaded):
        raise ConversionError("State dict có phần tử không phải tensor")
    architecture = _torchvision_architecture(set(state))
    metadata = {"framework": "torchvision"}
    if architecture:
        metadata["architecture"] = architecture
    classes = _torchvision_classes(state, architecture)
    if classes:
        metadata["num_classes"] = str(classes)
    save_file(state, str(output), metadata=metadata)


def convert_ultralytics(source: Path, output: Path) -> None:
    """Checkpoint Ultralytics là pickle đầy đủ: chỉ nạp được trong sandbox."""
    from ml_core.models.ultralytics_safetensors import export_safetensors

    try:
        export_safetensors(source, output)
    except ValueError as exc:
        if "--architecture" in str(exc):
            raise ConversionError(
                "Không nhận ra kiến trúc YOLO trong checkpoint; đổi tên file theo kiến trúc"
                " (ví dụ yolo11n.pt) rồi tải lên lại"
            ) from exc
        raise


def convert(source: Path, output: Path, framework: str) -> None:
    if framework == "torchvision":
        convert_torchvision(source, output)
    elif framework == "ultralytics":
        convert_ultralytics(source, output)
    else:
        raise ConversionError(f"Framework {framework!r} không chuyển đổi được")


def _limits() -> None:  # pragma: no cover - chạy trong tiến trình con
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_S, CPU_LIMIT_S))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_LIMIT_BYTES, FILE_LIMIT_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _sandbox_env(tmp: Path) -> dict[str, str]:
    """Môi trường tối thiểu: không mang biến của container sang tiến trình mở pickle."""
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp),
        "YOLO_CONFIG_DIR": str(tmp),
        "MPLCONFIGDIR": str(tmp),
        "OMP_NUM_THREADS": "2",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_one(work: Path, timeout_s: float = CONVERT_TIMEOUT_S) -> dict[str, Any]:
    """Chuyển file trong `work` bằng tiến trình con; trả nội dung `status.json`."""
    try:
        request = json.loads((work / REQUEST).read_text())
        framework, suffix = request["framework"], request["suffix"]
        stem, _ = safe_name(f"{request.get('stem') or 'model'}{suffix}")
        if framework not in FRAMEWORKS:
            return {"ok": False, "error": "Yêu cầu chuyển đổi không hợp lệ"}
        tmp = work / "tmp"
        tmp.mkdir(exist_ok=True)
        source = tmp / f"{stem}{suffix}"
        (work / f"input{suffix}").rename(source)
        try:
            done = subprocess.run(
                [sys.executable, "-m", "advertest_worker.converter", "convert",
                 str(source), str(work / OUTPUT), framework],
                env=_sandbox_env(tmp),
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                preexec_fn=_limits if os.name == "posix" else None,
                check=False,
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Chuyển đổi quá {timeout_s:.0f} giây"}
        finally:
            source.unlink(missing_ok=True)
            shutil.rmtree(tmp, ignore_errors=True)
        if done.returncode != 0 or not (work / OUTPUT).is_file():
            lines = [line for line in done.stderr.strip().splitlines() if line.strip()]
            reason = lines[-1] if lines else f"mã thoát {done.returncode}"
            return {"ok": False, "error": f"Không chuyển được file: {reason}"[:MAX_ERROR_CHARS]}
        return {"ok": True}
    except Exception as exc:  # file yêu cầu hỏng: vẫn trả status để worker không chờ mãi
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]}


def _write_status(work: Path, status: dict[str, Any]) -> None:
    tmp = work / f".{STATUS}.tmp"
    tmp.write_text(json.dumps(status, ensure_ascii=False))
    tmp.rename(work / STATUS)


def serve_once(spool: Path, timeout_s: float = CONVERT_TIMEOUT_S) -> bool:
    """Xử lý một yêu cầu đang chờ (cũ nhất trước); `False` khi không có yêu cầu nào."""
    pending = sorted(
        (p for p in spool.glob(f"*/{REQUEST}") if not (p.parent / STATUS).exists()),
        key=lambda p: p.stat().st_mtime,
    )
    if not pending:
        return False
    work = pending[0].parent
    logger.info("Chuyển đổi %s", work.name)
    _write_status(work, run_one(work, timeout_s))
    return True


def serve(spool: Path, timeout_s: float = CONVERT_TIMEOUT_S) -> None:  # pragma: no cover
    spool.mkdir(parents=True, exist_ok=True)
    logger.info("Sandbox chuyển đổi chờ yêu cầu ở %s", spool)
    while True:
        if not serve_once(spool, timeout_s):
            time.sleep(POLL_S)


def main(argv: list[str]) -> int:  # pragma: no cover - điểm vào của container và tiến trình con
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(argv) == 3 and argv[0] == "serve" and argv[1] == "--spool":
        serve(Path(argv[2]))
        return 0
    if len(argv) == 4 and argv[0] == "convert":
        try:
            convert(Path(argv[1]), Path(argv[2]), argv[3])
        except Exception as exc:
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        return 0
    print("Dùng: serve --spool <thư mục> | convert <nguồn> <đích> <framework>", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
