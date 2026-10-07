import pytest

from advertest_contracts.enums import RunStatus
from advertest_contracts.models import WorkerDirective
from advertest_worker.client import LeaseLost
from advertest_worker.errors import WORKER_POLICY, StopExperiment
from advertest_worker.patch import PatchInterrupted
from ml_core.runner.errors import CANCELLED_REASON, TIME_LIMIT_REASON, ErrorAction


@pytest.mark.parametrize(
    ("action", "status", "reason"),
    [
        ("cancel", RunStatus.CANCELLED, CANCELLED_REASON),
        ("stop_limit", RunStatus.STOPPED_LIMIT, TIME_LIMIT_REASON),
    ],
)
def test_patch_interrupted_stops_experiment(action: str, status: RunStatus, reason: object) -> None:
    directive = WorkerDirective.model_validate({"action": action, "remaining_seconds": 0})
    decision = WORKER_POLICY.decide(PatchInterrupted(directive, 7.5))
    assert decision.action is ErrorAction.STOP and decision.stops_experiment
    assert (decision.status, decision.reason, decision.device_seconds) == (status, reason, 7.5)


def test_lease_lost_and_stop_propagate() -> None:
    for exc in (LeaseLost(409, "conflict", "mất lease"), StopExperiment()):
        assert WORKER_POLICY.decide(exc).action is ErrorAction.PROPAGATE


def test_other_errors_fail_only_the_run() -> None:
    decision = WORKER_POLICY.decide(ValueError("checkpoint hỏng"))
    assert decision.action is ErrorAction.FAIL and not decision.stops_experiment
