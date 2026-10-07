import torch

from advertest_contracts.enums import RunStatus
from attacks.builders import IncompatibleAttack
from ml_core.runner.errors import CORE_POLICY, ErrorAction, ErrorDecision, propagate


def test_core_table() -> None:
    skip = CORE_POLICY.decide(IncompatibleAttack("fgsm cần gradient"))
    assert skip.action is ErrorAction.SKIP and skip.status == RunStatus.SKIPPED
    assert skip.reason is not None and skip.reason.code == "incompatible"
    assert skip.reason.message == "fgsm cần gradient"

    oom = CORE_POLICY.decide(torch.cuda.OutOfMemoryError("hết VRAM"))
    assert oom.action is ErrorAction.RETRY_SMALLER and oom.status == RunStatus.FAILED

    failed = CORE_POLICY.decide(RuntimeError("hỏng"))
    assert failed.action is ErrorAction.FAIL and failed.status == RunStatus.FAILED
    assert failed.reason is not None and failed.reason.code == "error"
    assert failed.reason.message == "RuntimeError: hỏng"
    assert not failed.stops_experiment


def test_extra_rules_take_precedence() -> None:
    class Lost(RuntimeError):
        pass

    policy = CORE_POLICY.with_rules((Lost, propagate))
    decision = policy.decide(Lost())
    assert decision == ErrorDecision(ErrorAction.PROPAGATE)
    assert decision.stops_experiment
    assert CORE_POLICY.decide(Lost()).action is ErrorAction.FAIL
