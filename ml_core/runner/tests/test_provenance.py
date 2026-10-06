import pytest

from ml_core.models.register import lib_versions
from ml_core.runner.env import GitState
from ml_core.runner.provenance import EnvProvenance, Provenance

COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64


def test_env_provenance_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_COMMIT", COMMIT)
    monkeypatch.setenv("DOCKER_IMAGE_DIGEST", DIGEST)
    provenance: Provenance = EnvProvenance()
    assert provenance.git() == GitState(commit=COMMIT, dirty=False)
    assert provenance.docker_image_digest() == DIGEST
    assert provenance.lib_versions() == lib_versions()


def test_env_provenance_without_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCKER_IMAGE_DIGEST", raising=False)
    assert EnvProvenance().docker_image_digest() == "none"


def test_env_provenance_rejects_bad_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_COMMIT", "not-a-commit")
    with pytest.raises(ValueError, match="GIT_COMMIT"):
        EnvProvenance().git()
