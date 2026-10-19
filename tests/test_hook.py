"""Step 0 Hook (#22, ADR-0008): the configured dev-set example and the candidate picker."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.data import NewsItem
from backend.hook import HOOK_HISTORY, hook_candidates
from backend.runner import Run, UserResult
from backend.runs import RUNS_SUBDIR, save_run
from backend.sample import write_synthetic_sample
from scripts import pick_hook
from tests.test_api_runs import ARMS, make_run
from tests.test_status import make_client


@pytest.fixture(scope="module")
def lab(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Run]:
    directory = tmp_path_factory.mktemp("hook")
    write_synthetic_sample(directory / "sample", n_users=400, n_news=300, seed=1)
    run = make_run(directory, ARMS)
    save_run(run, directory / RUNS_SUBDIR)
    return directory, run


def a_pair(run: Run) -> tuple[str, str, str]:
    """Any user with a click, and one clicked and one non-clicked item of theirs."""
    result = next(r for r in run.users if r.arm == "A" and 1 in r.labels.values())
    clicked = next(i for i in result.items if result.labels[i] == 1)
    other = next(i for i in result.items if result.labels[i] == 0)
    return result.user_id, clicked, other


def write_config(path: Path, **fields: str) -> Path:
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


def hook_client(lab: tuple[Path, Run], config: Path, **overrides: object) -> TestClient:
    return make_client(data_dir=str(lab[0]), hook_config=str(config), **overrides)


def configured(lab: tuple[Path, Run], tmp_path: Path, run: Run | None = None) -> Path:
    run = run or lab[1]
    user_id, clicked, other = a_pair(run)
    return write_config(
        tmp_path / "hook.json",
        run_id=run.run_id,
        user_id=user_id,
        clicked_id=clicked,
        other_id=other,
    )


# GET /api/hook


@pytest.mark.parametrize("demo_mode", [False, True])
def test_hook_returns_the_configured_example(
    lab: tuple[Path, Run], tmp_path: Path, demo_mode: bool
) -> None:
    _, run = lab
    user_id, clicked, other = a_pair(run)
    config = configured(lab, tmp_path)

    response = hook_client(lab, config, demo_mode=demo_mode).get("/api/hook")

    assert response.status_code == 200
    body = response.json()
    results = {r.arm: r for r in run.users if r.user_id == user_id}
    display = [i for i in results["A"].items if i in (clicked, other)]
    assert body["run_id"] == run.run_id
    assert body["user_id"] == user_id
    assert body["mock"] is True
    assert body["data_source"] == "synthetic"
    assert [h["news_id"] for h in body["headlines"]] == display
    assert all(h["title"] for h in body["headlines"])
    recent = list(results["A"].history[-HOOK_HISTORY:])
    assert [h["news_id"] for h in body["history"]] == recent
    reveal = body["reveal"]
    assert reveal["clicked_id"] == clicked
    assert [p["arm"] for p in reveal["predictions"]] == ["A", "D"]
    for prediction in reveal["predictions"]:
        result = results[prediction["arm"]]
        assert prediction["calls"] == [
            {"news_id": i, "p_click": result.scores[i], "reaction": result.reactions[i]}
            for i in display
        ]


def test_hook_answer_only_appears_under_reveal(lab: tuple[Path, Run], tmp_path: Path) -> None:
    body = hook_client(lab, configured(lab, tmp_path)).get("/api/hook").json()

    outside = json.dumps({k: v for k, v in body.items() if k != "reveal"})
    assert not any(key in outside for key in ('"labels"', '"clicked', '"p_click"', '"scores"'))


def test_missing_config_is_an_error_not_an_empty_example(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    response = hook_client(lab, tmp_path / "absent.json").get("/api/hook")

    assert response.status_code == 404
    assert response.json()["code"] == "hook_not_configured"


@pytest.mark.parametrize(
    "text", ["{not json", json.dumps({"run_id": "x"}), json.dumps({"run_id": 1, "extra": 2})]
)
def test_malformed_config_is_an_error(lab: tuple[Path, Run], tmp_path: Path, text: str) -> None:
    config = tmp_path / "hook.json"
    config.write_text(text, encoding="utf-8")

    response = hook_client(lab, config).get("/api/hook")

    assert response.status_code == 422
    assert response.json()["code"] == "hook_config_invalid"


@pytest.mark.parametrize(
    "change",
    [{"population": "test"}, {"is_result": True}],
    ids=["test-run", "result-run"],
)
def test_hook_refuses_test_and_result_runs(
    lab: tuple[Path, Run], tmp_path: Path, change: dict[str, object]
) -> None:
    run = replace(lab[1], run_id="20990101-000000-test-hook00", **change)  # pyright: ignore[reportArgumentType]
    path = save_run(run, lab[0] / RUNS_SUBDIR)
    try:
        response = hook_client(lab, configured(lab, tmp_path, run)).get("/api/hook")
    finally:
        path.unlink()

    assert response.status_code == 409
    assert response.json()["code"] == "hook_not_dev"


def test_unknown_run_or_user_is_404(lab: tuple[Path, Run], tmp_path: Path) -> None:
    _, run = lab
    _, clicked, other = a_pair(run)
    for run_id, user_id, code in [
        ("20990101-000000-dev-nope", "U1", "run_not_found"),
        (run.run_id, "U-nobody", "agent_not_found"),
    ]:
        config = write_config(
            tmp_path / "hook.json",
            run_id=run_id,
            user_id=user_id,
            clicked_id=clicked,
            other_id=other,
        )
        response = hook_client(lab, config).get("/api/hook")
        assert response.status_code == 404
        assert response.json()["code"] == code


def test_config_that_does_not_match_the_run_is_an_error(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    _, run = lab
    user_id, clicked, other = a_pair(run)
    swapped = write_config(
        tmp_path / "hook.json",
        run_id=run.run_id,
        user_id=user_id,
        clicked_id=other,
        other_id=clicked,
    )

    response = hook_client(lab, swapped).get("/api/hook")

    assert response.status_code == 422
    assert response.json()["code"] == "hook_config_mismatch"


def test_run_without_arms_a_and_d_is_an_error(lab: tuple[Path, Run], tmp_path: Path) -> None:
    run = replace(
        lab[1],
        run_id="20990101-000000-dev-noarmd",
        arms=["A", "random"],
        users=[u for u in lab[1].users if u.arm != "D"],
    )
    path = save_run(run, lab[0] / RUNS_SUBDIR)
    try:
        response = hook_client(lab, configured(lab, tmp_path, run)).get("/api/hook")
    finally:
        path.unlink()

    assert response.status_code == 409
    assert response.json()["code"] == "hook_arm_missing"


# Candidate selection (ADR-0008: the typical-reader pick is wrong, the history points right)

NEWS = {
    news_id: NewsItem(news_id, category, "sub", f"Headline {news_id}", "")
    for news_id, category in {
        "Hs1": "sports",
        "Hs2": "sports",
        "Hs3": "sports",
        "Hf1": "finance",
        "Cs": "sports",  # clicked, sports
        "Nf": "finance",  # not clicked
        "Nt": "travel",  # not clicked
    }.items()
}


def result(
    arm: str, user_id: str, scores: dict[str, float], history: tuple[str, ...]
) -> UserResult:
    return UserResult(
        user_id=user_id,
        arm=arm,
        scores=scores,
        labels={i: int(i.startswith("C")) for i in scores},
        tie_rank={i: n for n, i in enumerate(scores)},
        feed_ctr=0.1,
        sample_ctr=0.3,
        items=tuple(scores),
        reactions={i: f"{arm} on {i}" for i in scores},
        knowledge={},
        history=history,
    )


def picker_run(users: list[UserResult], **changes: object) -> Run:
    base = Run(
        run_id="20990101-000000-dev-pick00",
        created="2099-01-01T00:00:00+00:00",
        population="dev",
        arms=["A", "D"],
        config={},
        model="m",
        base_url="b",
        options={},
        mock=False,
        data_source="synthetic",
        retrieval="none",
        date_ranges={},
        fingerprint={},
        git_sha="x",
        freeze_tag_sha=None,
        unfrozen_override=False,
        is_result=False,
        users=users,
    )
    return replace(base, **changes)  # pyright: ignore[reportArgumentType]


SPORTY = ("Hf1", "Hs1", "Hs2", "Hs3")


def test_picks_pairs_where_a_is_wrong_d_is_right_and_history_points_to_the_click() -> None:
    run = picker_run(
        [
            # U1: A prefers both non-clicks, D prefers the click; history is sporty.
            result("A", "U1", {"Cs": 10, "Nf": 60, "Nt": 20}, SPORTY),
            result("D", "U1", {"Cs": 80, "Nf": 30, "Nt": 10}, SPORTY),
            # U2: A already right: no candidate.
            result("A", "U2", {"Cs": 70, "Nf": 20, "Nt": 10}, SPORTY),
            result("D", "U2", {"Cs": 80, "Nf": 30, "Nt": 10}, SPORTY),
            # U3: A wrong, D right, but the history does not point at sports.
            result("A", "U3", {"Cs": 10, "Nf": 60, "Nt": 20}, ("Hf1", "Hs1")),
            result("D", "U3", {"Cs": 80, "Nf": 30, "Nt": 10}, ("Hf1", "Hs1")),
            # U4: qualifies, but its history is less clear than U1's.
            result("A", "U4", {"Cs": 10, "Nf": 90}, SPORTY),
            result("D", "U4", {"Cs": 90, "Nf": 10}, SPORTY),
        ]
    )

    candidates = hook_candidates(run, NEWS)

    assert [(c.user_id, c.clicked_id, c.other_id) for c in candidates] == [
        # One pair per reader: against Nt, U1's history points more clearly (no travel at all)
        # than against Nf, though the Nf gaps are wider.
        ("U1", "Cs", "Nt"),
        ("U4", "Cs", "Nf"),
    ]
    best = candidates[0]
    assert (best.a_gap, best.d_gap, best.history_hits, best.history_misses) == (10, 70, 3, 0)


def test_only_the_recent_history_counts() -> None:
    old_sport = ("Hs1", "Hs2", "Hs3", *("Hf1",) * HOOK_HISTORY)
    run = picker_run(
        [
            result("A", "U1", {"Cs": 10, "Nt": 20}, old_sport),
            result("D", "U1", {"Cs": 80, "Nt": 10}, old_sport),
        ]
    )

    assert hook_candidates(run, NEWS) == []


def test_ties_are_not_a_wrong_pick() -> None:
    run = picker_run(
        [
            result("A", "U1", {"Cs": 20, "Nt": 20}, SPORTY),
            result("D", "U1", {"Cs": 80, "Nt": 10}, SPORTY),
        ]
    )

    assert hook_candidates(run, NEWS) == []


# scripts.pick_hook


def save_picker_run(tmp_path: Path, **changes: object) -> Run:
    run = picker_run(
        [
            result("A", "U1", {"Cs": 10, "Nf": 60, "Nt": 20}, SPORTY),
            result("D", "U1", {"Cs": 80, "Nf": 30, "Nt": 10}, SPORTY),
            result("A", "U2", {"Cs": 10, "Nf": 90}, SPORTY),
            result("D", "U2", {"Cs": 90, "Nf": 10}, SPORTY),
        ],
        **changes,
    )
    save_run(run, tmp_path / RUNS_SUBDIR)
    news_dir = tmp_path / "sample" / "dev"
    news_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "sample" / "SYNTHETIC").touch()
    (news_dir / "news.tsv").write_text(
        "".join(f"{n.news_id}\t{n.category}\tsub\t{n.title}\t\n" for n in NEWS.values()),
        encoding="utf-8",
    )
    return run


def test_pick_hook_prints_top_candidates_with_headlines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = save_picker_run(tmp_path)

    code = pick_hook.main(["--data-dir", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert run.run_id in out
    for expected in ("1. U1", "2. U2", "[sports/sub] Headline Cs", "Headline Nt", "Headline Hs3"):
        assert expected in out


def test_pick_hook_writes_the_chosen_candidate_only_when_asked(tmp_path: Path) -> None:
    run = save_picker_run(tmp_path)
    config = tmp_path / "hook.json"

    assert pick_hook.main(["--data-dir", str(tmp_path), "--config", str(config)]) == 0
    assert not config.exists()
    assert (
        pick_hook.main(["--data-dir", str(tmp_path), "--config", str(config), "--write", "2"]) == 0
    )

    assert json.loads(config.read_text(encoding="utf-8")) == {
        "run_id": run.run_id,
        "user_id": "U2",
        "clicked_id": "Cs",
        "other_id": "Nf",
    }


def test_pick_hook_prints_only_the_top_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save_picker_run(tmp_path)

    assert pick_hook.main(["--data-dir", str(tmp_path), "--top", "1"]) == 0

    out = capsys.readouterr().out
    assert "2 candidates" in out
    assert "1. U1" in out
    assert "2. U2" not in out


def test_pick_hook_never_writes_a_candidate_that_does_not_exist(tmp_path: Path) -> None:
    save_picker_run(tmp_path)
    config = tmp_path / "hook.json"

    assert (
        pick_hook.main(["--data-dir", str(tmp_path), "--config", str(config), "--write", "9"]) == 1
    )
    assert not config.exists()


@pytest.mark.parametrize(
    "change", [{"population": "test"}, {"is_result": True}], ids=["test-run", "result-run"]
)
def test_pick_hook_refuses_test_and_result_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: dict[str, object]
) -> None:
    run = save_picker_run(tmp_path, **change)

    code = pick_hook.main(["--data-dir", str(tmp_path), "--run", run.run_id])

    assert code == 1
    assert "dev" in capsys.readouterr().out


def test_pick_hook_without_a_dev_run_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save_picker_run(tmp_path, population="test")

    assert pick_hook.main(["--data-dir", str(tmp_path)]) == 1
    assert "No dev run" in capsys.readouterr().out
