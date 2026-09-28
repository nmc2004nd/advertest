import subprocess
from pathlib import Path

import pytest

from ml_core.runner import env as env_module
from ml_core.runner.env import (
    current_git_commit,
    docker_image_digest,
    environment,
    git_state,
)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / ".ai-log").mkdir()
    (tmp_path / ".ai-log" / "session.jsonl").write_text("{}\n")
    (tmp_path / "code.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-q", "-m", "init")
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.setattr(env_module, "REPO_ROOT", tmp_path)
    return tmp_path


def test_clean_tree(repo: Path) -> None:
    state = git_state()
    assert len(state.commit) == 40 and not state.dirty
    assert current_git_commit() == (state.commit, [])


def test_ai_log_changes_are_not_dirty(repo: Path) -> None:
    (repo / ".ai-log" / "session.jsonl").write_text('{"more": 1}\n')
    assert not git_state().dirty


def test_code_changes_are_dirty(repo: Path) -> None:
    (repo / "code.py").write_text("x = 2\n")
    assert git_state().dirty
    _, warnings = current_git_commit()
    assert warnings and "chưa commit" in warnings[0]


def test_untracked_files_are_not_dirty(repo: Path) -> None:
    (repo / "new.py").write_text("y = 1\n")
    assert not git_state().dirty


def test_git_commit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_COMMIT", "a" * 40)
    assert git_state() == env_module.GitState(commit="a" * 40, dirty=False)
    monkeypatch.setenv("GIT_COMMIT", "abc")
    with pytest.raises(ValueError, match="GIT_COMMIT"):
        git_state()


def test_docker_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCKER_IMAGE_DIGEST", raising=False)
    assert docker_image_digest() == "none"
    monkeypatch.setenv("DOCKER_IMAGE_DIGEST", "sha256:" + "b" * 64)
    assert docker_image_digest() == "sha256:" + "b" * 64
    monkeypatch.setenv("DOCKER_IMAGE_DIGEST", "latest")
    with pytest.raises(ValueError):
        docker_image_digest()


def test_environment_cpu() -> None:
    env = environment("cpu")
    assert env.compute_target_id is None and env.gpu_model is None and env.cuda_version is None
