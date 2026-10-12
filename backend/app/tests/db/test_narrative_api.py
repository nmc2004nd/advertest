"""Nhận xét chi tiết bằng LLM: `GET/POST /experiments/{id}/narrative` (LLM giả qua
MockTransport)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus, Role, RunStatus
from advertest_contracts.models import ErrorResponse, ExperimentNarrative, NarrativeState
from backend.app.api.public import get_llm
from backend.app.db import models as m
from backend.app.insight.llm import LlmClient

from .test_experiment_api import Api, Fx, _post, api, env, fx, world
from .test_phase08_reviews import _experiment, _metrics, _protocol

pytestmark = pytest.mark.db
__all__ = ["api", "env", "fx", "world"]

REPLY = {
    "summary": "PGD làm mAP@0.5 giảm 90% ngay ở eps 2.",
    "findings": [{"title": "PGD mạnh nhất", "detail": "Sụt 90% ở eps 2, FGSM chỉ 40% ở eps 4."}],
    "next_steps": ["Xem failure case PGD eps 2."],
}


@dataclass
class FakeLlm:
    status: int = 200
    requests: list[dict[str, Any]] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        if self.status != 200:
            return httpx.Response(self.status, text="lỗi")
        content = json.dumps(REPLY, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    def client(self) -> LlmClient:
        return LlmClient(
            base_url="https://llm.test",
            model="deepseek-chat",
            api_key="sk-test",
            transport=httpx.MockTransport(self.handler),
        )


def _with_llm(client: TestClient, llm: FakeLlm | None) -> TestClient:
    app: Any = client.app
    app.dependency_overrides[get_llm] = (lambda: llm.client()) if llm else (lambda: None)
    return client


def _state(client: TestClient, experiment_id: uuid.UUID) -> NarrativeState:
    response = client.get(f"/experiments/{experiment_id}/narrative")
    assert response.status_code == 200, response.text
    return NarrativeState.model_validate(response.json())


def _create(client: TestClient, experiment_id: uuid.UUID) -> httpx.Response:
    return _post(client, f"/experiments/{experiment_id}/narrative")


def _code(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, ErrorResponse.model_validate(response.json()).error.code


def test_disabled_without_llm(api: Api, fx: Fx, owner_engine: Engine) -> None:
    user_id, client = api.client(Role.ENGINEER)
    exp = _experiment(owner_engine, fx, user_id, _protocol(owner_engine))
    _with_llm(client, None)
    state = _state(client, exp.id)
    assert (state.enabled, state.narrative, state.can_generate) == (False, None, True)
    assert _code(_create(client, exp.id)) == (503, "llm_unavailable")


def test_running_experiment_cannot_generate(api: Api, fx: Fx, owner_engine: Engine) -> None:
    user_id, client = api.client(Role.ENGINEER)
    exp = _experiment(
        owner_engine, fx, user_id, _protocol(owner_engine), status=ExperimentStatus.RUNNING
    )
    llm = FakeLlm()
    _with_llm(client, llm)
    assert _state(client, exp.id).can_generate is False
    assert _code(_create(client, exp.id)) == (409, "conflict")
    assert llm.requests == []


def test_generate_once_then_reuse(
    api: Api, fx: Fx, owner_engine: Engine, app_engine: Engine
) -> None:
    user_id, client = api.client(Role.ENGINEER)
    exp = _experiment(owner_engine, fx, user_id, _protocol(owner_engine))
    llm = FakeLlm()
    _with_llm(client, llm)
    assert _state(client, exp.id).narrative is None

    response = _create(client, exp.id)
    assert response.status_code == 201, response.text
    narrative = ExperimentNarrative.model_validate(response.json())
    assert narrative.summary == REPLY["summary"]
    assert narrative.llm_model == "deepseek-chat"
    assert narrative.created_by == user_id
    assert len(llm.requests) == 1

    # Dữ liệu gửi LLM chỉ là số liệu: có tên attack và level, không có URI hay người dùng.
    sent = llm.requests[0]["messages"][1]["content"]
    assert "pgd_linf" in sent and "relative_drop" in sent
    assert "s3://" not in sent and str(user_id) not in sent

    again = _create(client, exp.id)
    assert again.status_code == 201
    assert ExperimentNarrative.model_validate(again.json()) == narrative
    assert len(llm.requests) == 1  # cùng dữ liệu: không gọi lại

    state = _state(client, exp.id)
    assert (state.narrative, state.stale) == (narrative, False)
    with Session(app_engine) as s:
        audits = s.scalar(
            select(func.count())
            .select_from(m.AuditLog)
            .where(m.AuditLog.action == "experiment.narrative", m.AuditLog.entity_id == exp.id)
        )
    assert audits == 1


def test_new_run_makes_narrative_stale(api: Api, fx: Fx, owner_engine: Engine) -> None:
    user_id, client = api.client(Role.ENGINEER)
    exp = _experiment(owner_engine, fx, user_id, _protocol(owner_engine))
    llm = FakeLlm()
    _with_llm(client, llm)
    first = ExperimentNarrative.model_validate(_create(client, exp.id).json())

    with Session(owner_engine) as s, s.begin():
        run = s.get(m.Run, exp.runs["fgsm_2"])
        assert run is not None
        run.metrics = _metrics(0.35)
    state = _state(client, exp.id)
    assert (state.narrative, state.stale) == (first, True)

    second = ExperimentNarrative.model_validate(_create(client, exp.id).json())
    assert second.input_sha256 != first.input_sha256
    assert len(llm.requests) == 2
    assert _state(client, exp.id).stale is False


def test_llm_error_is_502_and_saves_nothing(api: Api, fx: Fx, owner_engine: Engine) -> None:
    user_id, client = api.client(Role.ENGINEER)
    exp = _experiment(owner_engine, fx, user_id, _protocol(owner_engine))
    _with_llm(client, FakeLlm(status=500))
    assert _code(_create(client, exp.id)) == (502, "llm_failed")
    assert _state(client, exp.id).narrative is None


def test_no_data_cannot_generate(api: Api, fx: Fx, owner_engine: Engine) -> None:
    user_id, client = api.client(Role.ENGINEER)
    exp = _experiment(
        owner_engine,
        fx,
        user_id,
        _protocol(owner_engine),
        runs={("fgsm", 2): (RunStatus.FAILED, None, "error")},
    )
    _with_llm(client, FakeLlm())
    assert _state(client, exp.id).can_generate is False
    assert _code(_create(client, exp.id)) == (409, "conflict")


def test_unknown_experiment_is_404(api: Api) -> None:
    _, client = api.client(Role.ENGINEER)
    _with_llm(client, FakeLlm())
    missing = uuid.uuid4()
    assert client.get(f"/experiments/{missing}/narrative").status_code == 404
    assert _code(_create(client, missing)) == (404, "not_found")
