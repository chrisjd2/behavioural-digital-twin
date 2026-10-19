"""scripts.build_demo_data (#23, ADR-0011): the hosted demo's DATA_DIR, and nothing else."""

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.data import SYNTHETIC_MARKER, load_news
from backend.hook import HookConfig
from backend.runner import Run
from backend.runs import RUNS_SUBDIR, save_run
from backend.sample import write_synthetic_sample
from scripts import build_demo_data
from tests.test_api_runs import ARMS, make_run
from tests.test_hook import a_pair
from tests.test_interview import body, write_recorded
from tests.test_status import make_client, make_settings

SECRET = "sk-demo-data-must-not-hold-this"


class Lab:
    """A full DATA_DIR: the synthetic sample, the LLM cache, a .env and three runs."""

    def __init__(self, root: Path) -> None:
        self.data = root / "data"
        write_synthetic_sample(self.data / "sample", n_users=400, n_news=300, seed=1)
        self.dev = make_run(self.data, ARMS)  # also writes data/cache.sqlite
        self.result = replace(
            self.dev, run_id="29991231-000000-test-aaaaaa", created="2999-12-31T00:00:00",
            population="test", is_result=True,
        )  # fmt: skip
        self.unused = replace(self.dev, run_id="20000101-000000-dev-bbbbbb", created="2000-01-01")
        for run in (self.dev, self.result, self.unused):
            save_run(run, self.data / RUNS_SUBDIR)
        (self.data / ".env").write_text(f"LLM_API_KEY={SECRET}\n", encoding="utf-8")
        user_id, clicked, other = a_pair(self.dev)
        self.hook = root / "hook.json"
        self.hook.write_text(
            HookConfig(
                run_id=self.dev.run_id, user_id=user_id, clicked_id=clicked, other_id=other
            ).model_dump_json(),
            encoding="utf-8",
        )
        self.recorded = write_recorded(root / "recorded.json", self.result)

    def settings(self, **overrides: object) -> Settings:
        defaults = {
            "data_dir": str(self.data),
            "hook_config": str(self.hook),
            "interview_recorded": str(self.recorded),
            "llm_api_key": SECRET,
        }
        return make_settings(**{**defaults, **overrides})


@pytest.fixture(scope="module")
def lab(tmp_path_factory: pytest.TempPathFactory) -> Lab:
    return Lab(tmp_path_factory.mktemp("demo-lab"))


@pytest.fixture(scope="module")
def demo(lab: Lab, tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("built") / "demo-data"
    build_demo_data.build(lab.settings(), out)
    return out


def files(directory: Path) -> set[str]:
    return {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}


def test_holds_the_result_and_hook_runs_and_the_news_layout_only(lab: Lab, demo: Path) -> None:
    assert files(demo) == {
        f"runs/{lab.result.run_id}.json",
        f"runs/{lab.dev.run_id}.json",
        "sample/dev/news.tsv",
        "sample/dev/behaviors.tsv",
        "sample/train/behaviors.tsv",
        f"sample/{SYNTHETIC_MARKER}",
    }
    for run in (lab.result, lab.dev):
        name = f"{run.run_id}.json"
        assert (demo / RUNS_SUBDIR / name).read_bytes() == (
            lab.data / RUNS_SUBDIR / name
        ).read_bytes()
    assert (demo / "sample/dev/behaviors.tsv").stat().st_size == 0


def test_no_cache_env_or_secret(demo: Path) -> None:
    assert not {"cache.sqlite", ".env"} & {p.name for p in demo.rglob("*")}
    for path in demo.rglob("*"):
        if path.is_file():
            assert SECRET not in path.read_text(encoding="utf-8")


def test_news_is_the_items_the_runs_mention_cut_to_the_read_columns(lab: Lab, demo: Path) -> None:
    full = load_news(lab.data / "sample/dev/news.tsv")
    subset = load_news(demo / "sample/dev/news.tsv")
    mentioned = {
        i for run in (lab.result, lab.dev) for u in run.users for i in (*u.items, *u.history)
    }
    assert mentioned & full.keys() <= subset.keys() < full.keys()
    assert all(subset[i] == full[i] for i in subset)
    lines = (demo / "sample/dev/news.tsv").read_text(encoding="utf-8").splitlines()
    assert all(line.count("\t") == build_demo_data.NEWS_COLUMNS - 1 for line in lines)


def test_named_run_replaces_the_newest_result(lab: Lab, tmp_path: Path) -> None:
    build_demo_data.build(lab.settings(), tmp_path / "out", lab.unused.run_id)

    assert files(tmp_path / "out" / RUNS_SUBDIR) == {
        f"{lab.unused.run_id}.json",
        f"{lab.dev.run_id}.json",
        f"{lab.result.run_id}.json",  # the recorded interview's run
    }


def test_without_a_recording_the_hook_and_result_runs_still_go(lab: Lab, tmp_path: Path) -> None:
    settings = lab.settings(interview_recorded=str(tmp_path / "none.json"))

    build_demo_data.build(settings, tmp_path / "out")

    assert len(files(tmp_path / "out" / RUNS_SUBDIR)) == 2


def test_refuses_without_a_result_run(lab: Lab, tmp_path: Path) -> None:
    runs = tmp_path / "data" / RUNS_SUBDIR
    save_run(lab.dev, runs)

    with pytest.raises(build_demo_data.DemoDataError, match="No result run"):
        build_demo_data.build(lab.settings(data_dir=str(tmp_path / "data")), tmp_path / "out")


def test_refuses_a_run_made_from_other_data(lab: Lab, tmp_path: Path) -> None:
    other = tmp_path / "data"
    write_synthetic_sample(other / "mind", n_users=50, n_news=50, seed=2)
    (other / "mind" / SYNTHETIC_MARKER).unlink()  # now it looks like real MIND
    for run in (lab.dev, lab.result):
        save_run(run, other / RUNS_SUBDIR)

    with pytest.raises(build_demo_data.DemoDataError, match="used synthetic data"):
        build_demo_data.build(lab.settings(data_dir=str(other)), tmp_path / "out")


def test_refuses_a_non_empty_output(lab: Lab, tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("x", encoding="utf-8")

    with pytest.raises(build_demo_data.DemoDataError, match="not empty"):
        build_demo_data.build(lab.settings(), tmp_path)


def test_main_reports_the_size_and_fails_cleanly(
    lab: Lab, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOOK_CONFIG", str(lab.hook))
    monkeypatch.setenv("INTERVIEW_RECORDED", str(lab.recorded))
    args = ["--data-dir", str(lab.data), "--out", str(tmp_path / "out")]

    assert build_demo_data.main(args) == 0
    assert "(6 files," in capsys.readouterr().out
    assert build_demo_data.main([*args[:3], str(tmp_path / "other"), "--run", "no-such-run"]) == 1
    assert "No run no-such-run" in capsys.readouterr().out


# The API on demo-data/ in DEMO_MODE: every step, the same as on the full DATA_DIR.


def clients(lab: Lab, demo: Path) -> tuple[TestClient, TestClient]:
    full = make_client(**{**lab.settings().model_dump(), "demo_mode": True})
    hosted = make_client(
        **{**lab.settings().model_dump(), "demo_mode": True, "data_dir": str(demo)}
    )
    return full, hosted


def step_paths(run: Run) -> list[str]:
    users = list(dict.fromkeys(u.user_id for u in run.users))[:5]
    base = f"/api/run/{run.run_id}"
    return [
        base,
        f"{base}/population",
        f"{base}/events",
        f"{base}/report",
        *(f"{base}/agent/{u}" for u in users),
        *(f"{base}/user/{u}/predictions" for u in users),
    ]


def test_every_step_reads_the_same_from_demo_data(lab: Lab, demo: Path) -> None:
    full, hosted = clients(lab, demo)
    paths = [
        "/api/hook",
        "/api/interview/recorded",
        *step_paths(lab.result),
        *step_paths(lab.dev),
    ]

    for path in paths:
        response = hosted.get(path)
        assert response.status_code == 200, (path, response.json())
        assert response.json() == full.get(path).json(), path


def test_demo_data_is_labelled_and_lists_only_its_runs(lab: Lab, demo: Path) -> None:
    _, hosted = clients(lab, demo)

    assert hosted.get("/api/status").json()["data_source"] == "synthetic"
    runs = hosted.get("/api/runs").json()
    assert [r["run_id"] for r in runs["runs"]] == [lab.result.run_id, lab.dev.run_id]
    assert runs["problems"] == []


def test_the_interview_answers_from_demo_data(lab: Lab, demo: Path) -> None:
    _, hosted = clients(lab, demo)

    response = hosted.post("/api/interview", json=body(lab.result))

    assert response.status_code == 200
    assert response.json()["mock"] is True


def test_demo_data_is_never_written(lab: Lab, demo: Path) -> None:
    before = {p: p.stat().st_mtime_ns for p in demo.rglob("*")}
    _, hosted = clients(lab, demo)

    assert hosted.post("/api/run", json={}).status_code == 403
    assert hosted.post("/api/experiment", json={}).status_code == 403
    hosted.post("/api/interview", json=body(lab.result))
    assert {p: p.stat().st_mtime_ns for p in demo.rglob("*")} == before
