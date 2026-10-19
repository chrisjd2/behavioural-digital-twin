import subprocess
from pathlib import Path

import pytest

from backend.freeze import FREEZE_TAG, freeze_problem
from backend.llm import mock_backend
from scripts.run_headless import main


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_missing_tag_is_a_problem(repo: Path) -> None:
    assert FREEZE_TAG in (freeze_problem(repo) or "")


def test_tagged_clean_tree_is_frozen(repo: Path) -> None:
    git(repo, "tag", FREEZE_TAG)

    assert freeze_problem(repo) is None


def test_commits_after_the_tag_are_still_frozen(repo: Path) -> None:
    git(repo, "tag", FREEZE_TAG)
    (repo / "g.txt").write_text("y", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "later")

    assert freeze_problem(repo) is None


def test_dirty_tree_is_a_problem(repo: Path) -> None:
    git(repo, "tag", FREEZE_TAG)
    (repo / "f.txt").write_text("changed", encoding="utf-8")

    assert "uncommitted" in (freeze_problem(repo) or "")


def test_headless_refuses_unfrozen_test_run_with_llm_arm(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("scripts.run_headless.freeze_problem", lambda: "not frozen")

    exit_code = main(["--data-dir", str(data_dir), "--population", "test", "--arms", "A"])

    assert exit_code == 3


def test_headless_dev_run_prints_mock_banner_and_saves_run(
    data_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr("scripts.run_headless.RUNS_SUBDIR", runs_dir)
    monkeypatch.setattr("scripts.run_headless.CACHE_FILE", tmp_path / "cache.sqlite")
    monkeypatch.setattr("scripts.run_headless.make_backend", lambda _settings: mock_backend)

    exit_code = main(["--data-dir", str(data_dir), "--population", "dev", "--arms", "A,random"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "MOCK" in out
    assert len(list(runs_dir.glob("*.json"))) == 1
