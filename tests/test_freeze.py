import json
import subprocess
from pathlib import Path

import pytest

from backend.arms import LLMOptions
from backend.data import DataSource
from backend.experiment import ExperimentConfig
from backend.freeze import FREEZE_TAG, FROZEN_FILE, fingerprint, freeze_problem
from scripts.run_headless import main

OPTIONS = LLMOptions(reasoning_effort="medium", max_output_tokens=4096, base_rate_hint=False)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def current(source: DataSource, **changes: object) -> dict[str, object]:
    options = LLMOptions(**{**OPTIONS.__dict__, **changes})  # type: ignore[arg-type]
    return fingerprint(source, ExperimentConfig(), model="m-1", base_url="u", options=options)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def freeze(repo: Path, frozen: dict[str, object]) -> None:
    (repo / FROZEN_FILE).write_text(json.dumps(frozen), encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "freeze")
    git(repo, "tag", FREEZE_TAG)


def test_missing_tag_is_a_problem(repo: Path, sample_source: DataSource) -> None:
    assert FREEZE_TAG in (freeze_problem(current(sample_source), repo) or "")


def test_matching_setup_on_clean_tree_is_frozen(repo: Path, sample_source: DataSource) -> None:
    freeze(repo, current(sample_source))

    assert freeze_problem(current(sample_source), repo) is None


def test_unrelated_commits_after_the_tag_are_allowed(repo: Path, sample_source: DataSource) -> None:
    freeze(repo, current(sample_source))
    (repo / "ui.txt").write_text("frontend work", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "later")

    assert freeze_problem(current(sample_source), repo) is None


def test_setting_changes_after_the_freeze_are_refused(
    repo: Path, sample_source: DataSource
) -> None:
    freeze(repo, current(sample_source))

    problem = freeze_problem(current(sample_source, reasoning_effort="high"), repo) or ""

    assert "options" in problem
    assert "prompt_hashes" in problem


def test_editing_frozen_json_after_the_tag_does_not_help(
    repo: Path, sample_source: DataSource
) -> None:
    freeze(repo, current(sample_source))
    changed = current(sample_source, base_rate_hint=True)
    (repo / FROZEN_FILE).write_text(json.dumps(changed), encoding="utf-8")
    git(repo, "commit", "-qam", "sneaky")

    assert "options" in (freeze_problem(changed, repo) or "")


def test_dirty_tree_is_a_problem(repo: Path, sample_source: DataSource) -> None:
    freeze(repo, current(sample_source))
    (repo / "f.txt").write_text("changed", encoding="utf-8")

    assert "uncommitted" in (freeze_problem(current(sample_source), repo) or "")


def test_fingerprint_covers_prompt_options_and_data(sample_source: DataSource) -> None:
    base = current(sample_source)

    assert base["prompt_hashes"] != current(sample_source, max_output_tokens=10)["prompt_hashes"]
    assert set(base["data_sha256"]) == {  # type: ignore[arg-type]
        "dev/behaviors.tsv",
        "dev/news.tsv",
        "train/behaviors.tsv",
        "train/news.tsv",
    }


def test_headless_refuses_unfrozen_test_run(
    data_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("backend.runner.freeze_problem", lambda _current: "not frozen")
    monkeypatch.setattr("scripts.run_headless.RUNS_SUBDIR", tmp_path / "runs")

    exit_code = main(["--data-dir", str(data_dir), "--population", "test", "--arms", "random"])

    assert exit_code == 3
    assert "not frozen" in capsys.readouterr().out
    assert not (tmp_path / "runs").exists()


def test_allow_unfrozen_is_recorded_and_never_a_result(
    data_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("backend.runner.freeze_problem", lambda _current: "not frozen")
    monkeypatch.setattr("scripts.run_headless.RUNS_SUBDIR", tmp_path / "runs")
    monkeypatch.setattr("scripts.run_headless.CACHE_FILE", tmp_path / "cache.sqlite")

    exit_code = main(
        ["--data-dir", str(data_dir), "--population", "test", "--arms", "A", "--allow-unfrozen"]
    )

    out = capsys.readouterr().out
    saved = json.loads(next((tmp_path / "runs").glob("*.json")).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert saved["unfrozen_override"] is True
    assert saved["is_result"] is False
    assert "WARNING: test set run with --allow-unfrozen" in out
    assert "MOCK LLM OUTPUT" in out
    assert "NOT A RESULT" in out
