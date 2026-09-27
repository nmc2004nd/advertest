"""Endpoint công khai cho người dùng: mỗi nhóm một endpoint đại diện (khung tối thiểu).

Model request/response chỉ dùng schema đã có trong `advertest_contracts`; schema còn lại
do phase tương ứng thêm vào contract (Phase 3-8).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Security

from advertest_contracts.models import AttackSpec, ExperimentConfig, ProtocolBody, RunResult
from backend.app.api.errors import not_implemented
from backend.app.api.security import user_session

router = APIRouter(dependencies=[Security(user_session)])


@router.post("/auth/login", tags=["auth"])
def login() -> None:
    not_implemented()


@router.get("/users", tags=["users"])
def list_users() -> None:
    not_implemented()


@router.get("/models", tags=["models"])
def list_models() -> None:
    not_implemented()


@router.get("/datasets", tags=["datasets"])
def list_datasets() -> None:
    not_implemented()


@router.get("/slices", tags=["slices"])
def list_slices() -> None:
    not_implemented()


@router.get("/attack-specs", tags=["attack-specs"])
def list_attack_specs() -> list[AttackSpec]:
    not_implemented()


@router.post("/protocols", tags=["protocols"])
def create_protocol(body: ProtocolBody) -> None:
    not_implemented()


@router.post("/experiments", tags=["experiments"])
def create_experiment(config: ExperimentConfig) -> None:
    not_implemented()


@router.get("/runs/{run_id}", tags=["runs"])
def get_run(run_id: UUID) -> RunResult:
    not_implemented()


@router.get("/failure-cases/{case_id}", tags=["failure-cases"])
def get_failure_case(case_id: UUID) -> None:
    not_implemented()


@router.get("/reviews", tags=["reviews"])
def list_reviews() -> None:
    not_implemented()


@router.get("/reports/{report_id}", tags=["reports"])
def get_report(report_id: UUID) -> None:
    not_implemented()


@router.get("/compute-targets", tags=["compute-targets"])
def list_compute_targets() -> None:
    not_implemented()


@router.get("/budget", tags=["budget"])
def get_budget() -> None:
    not_implemented()


@router.get("/audit-log", tags=["audit-log"])
def list_audit_log() -> None:
    not_implemented()


# Trang xác minh report công khai, không cần đăng nhập.
verify_router = APIRouter()


@verify_router.get("/verify/{report_id}", tags=["verify"])
def verify_report(report_id: UUID) -> None:
    not_implemented()
