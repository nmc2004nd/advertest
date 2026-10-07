"""Kiến trúc Phase R1 bằng AST, không cần DB (validation.md Phase R1, `### Kiến trúc`).

Thêm trước Group 5 (plan.md bước 7): runner và worker không phụ thuộc lớp perturbation cụ thể;
`attacks/` không còn `AnyPerturbation`; test nghiệm thu không patch tên module nội bộ. Phần
`job.py` được thêm trước Group 6 (điều phối mỏng).

Chỉ xét mã chạy: bỏ qua thư mục `tests/` của từng gói.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RUNNER_DIRS = [REPO / "ml_core" / "runner", REPO / "backend" / "worker" / "advertest_worker"]

CONCRETE_MODULES = {
    "attacks.art_adapter",
    "attacks.corruptions.adapter",
    "attacks.occlusion.adapter",
    "attacks.patch.adapter",
}
CONCRETE_CLASSES = {
    "ArtPerturbation",
    "CorruptionPerturbation",
    "OcclusionPerturbation",
    "PatchPerturbation",
}
PATCHED_NAMES = {"build_perturbation", "git_state", "predict_slice"}

JOB = REPO / "backend" / "worker" / "advertest_worker" / "job.py"
JOB_FORBIDDEN_NAMES = {"build_fingerprint_inputs", "Manifest"}
JOB_FORBIDDEN_MODULE = "ml_core.models.estimator"
JOB_ALLOWED_ATTACKS = {"attacks.builders", "attacks.registry"}


def _sources(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if "tests" in path.relative_to(root).parts:
            continue
        yield path


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _imported_modules(tree: ast.Module) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module, node.lineno
            for alias in node.names:
                yield f"{node.module}.{alias.name}", node.lineno


def _names(node: ast.AST) -> Iterator[str]:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            yield sub.id
        elif isinstance(sub, ast.Attribute):
            yield sub.attr


def test_runner_and_worker_do_not_import_concrete_perturbations() -> None:
    offenders = []
    for root in RUNNER_DIRS:
        for path in _sources(root):
            for module, line in _imported_modules(_parse(path)):
                if module in CONCRETE_MODULES:
                    offenders.append(f"{path.relative_to(REPO)}:{line} import {module}")
    assert not offenders, "\n".join(offenders)


def test_runner_and_worker_do_not_isinstance_concrete_perturbations() -> None:
    offenders = []
    for root in RUNNER_DIRS:
        for path in _sources(root):
            for node in ast.walk(_parse(path)):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"isinstance", "issubclass"}
                    and len(node.args) == 2
                    and CONCRETE_CLASSES & set(_names(node.args[1]))
                ):
                    offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
    assert not offenders, "\n".join(offenders)


def test_attacks_has_no_any_perturbation() -> None:
    offenders = []
    for path in _sources(REPO / "attacks"):
        tree = _parse(path)
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.alias):
                name = node.asname or node.name.rsplit(".", 1)[-1]
            elif isinstance(node, ast.ClassDef | ast.FunctionDef):
                name = node.name
            if name == "AnyPerturbation":
                offenders.append(f"{path.relative_to(REPO)}:{getattr(node, 'lineno', '?')}")
    assert not offenders, "\n".join(offenders)


def test_acceptance_tests_do_not_patch_module_names() -> None:
    """`monkeypatch.setattr(module, "<tên>", ...)`, `mock.patch("...<tên>")` hay
    `patch.object(module, "<tên>")` với `build_perturbation`, `git_state`, `predict_slice`."""
    offenders = []
    for path in sorted((REPO / "tests" / "acceptance").rglob("*.py")):
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            strings = [
                a.value
                for a in node.args
                if isinstance(a, ast.Constant) and isinstance(a.value, str)
            ]
            if name in {"setattr", "object"}:
                hit = any(s in PATCHED_NAMES for s in strings)
            elif name == "patch":
                hit = any(s.rsplit(".", 1)[-1] in PATCHED_NAMES for s in strings)
            else:
                continue
            if hit:
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
    assert not offenders, "\n".join(offenders)


def _job_forbidden(module: str, name: str | None) -> bool:
    """`import module` (name `None`) hoặc `from module import name`."""
    full = module if name is None else f"{module}.{name}"
    if name in JOB_FORBIDDEN_NAMES:
        return True
    if full == JOB_FORBIDDEN_MODULE or full.startswith(JOB_FORBIDDEN_MODULE + "."):
        return True
    if module != "attacks" and not module.startswith("attacks."):
        return False
    # `from attacks import builders` xét `attacks.builders`; còn lại xét module được import.
    target = full if module == "attacks" else module
    return target not in JOB_ALLOWED_ATTACKS


def test_job_imports_only_orchestration_dependencies() -> None:
    """`job.py` không import `build_fingerprint_inputs`, `Manifest`, `ml_core.models.estimator`,
    hay module `attacks` nào ngoài `attacks.builders` và `attacks.registry`."""
    offenders = []
    for node in ast.walk(_parse(JOB)):
        if isinstance(node, ast.Import):
            offenders += [
                f"job.py:{node.lineno} import {a.name}"
                for a in node.names
                if _job_forbidden(a.name, None)
            ]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            offenders += [
                f"job.py:{node.lineno} from {node.module} import {a.name}"
                for a in node.names
                if _job_forbidden(node.module, a.name)
            ]
    assert not offenders, "\n".join(offenders)
