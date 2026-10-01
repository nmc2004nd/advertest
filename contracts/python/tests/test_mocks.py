from pathlib import Path

import pytest

from advertest_contracts.enums import RunStatus, SearchStatus
from advertest_contracts.models import RunResult, SearchResult
from advertest_contracts.registry import SCHEMAS

MOCKS = Path(__file__).resolve().parents[2] / "mocks"
MOCK_FILES = sorted(MOCKS.rglob("*.json"))


def test_every_mock_dir_is_a_known_schema() -> None:
    assert {path.parent.name for path in MOCK_FILES} <= set(SCHEMAS)
    assert {path.parent.name for path in MOCK_FILES} == set(SCHEMAS), (
        "Mỗi schema cần ít nhất 1 mock"
    )


@pytest.mark.parametrize("path", MOCK_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_mock_validates(path: Path) -> None:
    SCHEMAS[path.parent.name].model_validate_json(path.read_text())


def test_run_result_mocks_cover_every_status() -> None:
    statuses = {
        RunResult.model_validate_json(p.read_text()).status
        for p in (MOCKS / "run_result").glob("*.json")
    }
    assert statuses == set(RunStatus)


def test_search_result_mocks_cover_every_status() -> None:
    statuses = {
        SearchResult.model_validate_json(p.read_text()).status
        for p in (MOCKS / "search_result").glob("*.json")
    }
    # Phase 7: bản tạm thời (stage khác done) có status null; cần cả bản tạm thời.
    assert None in statuses
    assert statuses - {None} == set(SearchStatus)
