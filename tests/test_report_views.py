"""Step 4 Report endpoints: the stored report, and one user's predictions against reality."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.metrics import rank
from backend.report import outcome_bucket
from backend.report_views import reliability
from backend.runner import Run, UserResult
from backend.runs import RUNS_SUBDIR, save_run
from backend.sample import write_synthetic_sample
from tests.test_api_runs import labels_leak, make_run
from tests.test_status import make_client

ARMS = ["A", "B", "C", "D", "E", "popularity", "random"]


@pytest.fixture(scope="module")
def lab(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Run]:
    directory = tmp_path_factory.mktemp("report-lab")
    write_synthetic_sample(directory / "sample", n_users=400, n_news=300, seed=1)
    run = make_run(directory, ARMS)
    save_run(run, directory / RUNS_SUBDIR)
    return directory, run


@pytest.fixture
def client(lab: tuple[Path, Run]) -> TestClient:
    return make_client(data_dir=str(lab[0]))


def report(client: TestClient, run: Run) -> dict[str, object]:
    response = client.get(f"/api/run/{run.run_id}/report")
    assert response.status_code == 200, response.text
    return response.json()


def saved(run: Run, tmp_path: Path) -> TestClient:
    save_run(run, tmp_path / RUNS_SUBDIR)
    write_synthetic_sample(tmp_path / "sample", n_users=400, n_news=300, seed=1)
    return make_client(data_dir=str(tmp_path))


# GET /api/run/{run_id}/report


def test_report_returns_the_stored_metrics_per_arm(
    lab: tuple[Path, Run], client: TestClient
) -> None:
    _, run = lab
    body = report(client, run)
    stored = run.metrics["arms"]
    assert isinstance(stored, dict)

    arms = {a["arm"]: a for a in body["arms"]}  # type: ignore[union-attr]
    assert list(arms) == ARMS
    assert arms["D"]["metrics"] == stored["D"]["metrics"]
    assert arms["D"]["tie_share"] == stored["D"]["tie_share"]
    assert arms["D"]["parse_failure_rate"] == stored["D"]["parse_failure_rate"]
    assert arms["D"]["calibration"] == stored["D"]["calibration"]
    assert arms["D"]["kind"] == "llm"
    assert arms["popularity"]["kind"] == "baseline"
    assert arms["popularity"]["calibration"] is None


def test_report_states_the_primary_outcome_as_stored(
    lab: tuple[Path, Run], client: TestClient
) -> None:
    _, run = lab
    primary = report(client, run)["primary"]
    stored = run.metrics["primary"]
    assert isinstance(primary, dict)
    assert isinstance(stored, dict)

    assert primary["difference"] == stored["difference"]
    assert primary["verdict"] == stored["verdict"]
    assert primary["median_user"] == stored["median_user"]


def test_buckets_hold_the_stored_counts_and_their_users(
    lab: tuple[Path, Run], client: TestClient
) -> None:
    _, run = lab
    primary = report(client, run)["primary"]
    assert isinstance(primary, dict)
    stored = run.metrics["primary"]["buckets"]  # type: ignore[index]

    buckets = {b["bucket"]: b["users"] for b in primary["buckets"]}
    assert list(buckets) == ["Twin better", "About the same", "Plain LLM better"]
    assert {k: len(v) for k, v in buckets.items()} == stored
    for name, users in buckets.items():
        differences = [u["d_minus_a"] for u in users]
        assert differences == sorted(differences, reverse=True)
        assert all(outcome_bucket(d) == name for d in differences)
    assert sum(len(v) for v in buckets.values()) == len({u.user_id for u in run.users})


def test_paired_differences_omit_per_user_values(lab: tuple[Path, Run], client: TestClient) -> None:
    _, run = lab
    differences = report(client, run)["differences"]
    assert isinstance(differences, list)

    pairs = [(d["arm"], d["reference"]) for d in differences]
    assert ("D", "A") in pairs
    assert ("D", "E") in pairs
    assert ("B", "A") in pairs
    assert all(set(d) == {"arm", "reference", "auc"} for d in differences)


def test_reliability_bins_count_every_prediction(lab: tuple[Path, Run], client: TestClient) -> None:
    _, run = lab
    reliability = {r["arm"]: r["bins"] for r in report(client, run)["reliability"]}  # type: ignore[union-attr]

    assert list(reliability) == ["A", "B", "C", "D", "E"]
    a_users = [u for u in run.users if u.arm == "A"]
    bins = reliability["A"]
    assert len(bins) == 10
    assert sum(b["n"] for b in bins) == sum(len(u.scores) for u in a_users)
    clicks = sum(b["clicks"] for b in bins)
    assert clicks == sum(sum(u.labels.values()) for u in a_users)
    for b in bins:
        assert b["low"] < b["high"]
        if b["n"]:
            assert b["low"] <= b["mean_p_click"] <= b["high"]


def test_reliability_floors_p_click_into_bins_with_100_in_the_top_one() -> None:
    scores = {"N1": 30.0, "N2": 29.0, "N3": 100.0, "N4": 0.0}
    user = UserResult(
        user_id="U1",
        arm="A",
        scores=scores,
        labels={"N1": 1, "N2": 0, "N3": 1, "N4": 0},
        tie_rank={n: i for i, n in enumerate(scores)},
        feed_ctr=0.04,
        sample_ctr=0.5,
        items=tuple(scores),
        reactions={},
        knowledge={},
        history=(),
    )

    bins = reliability("A", [user]).bins

    assert [(b.low, b.n, b.clicks) for b in bins if b.n] == [
        (0.0, 1, 0),
        (0.2, 1, 0),
        (0.3, 1, 1),
        (0.9, 1, 1),
    ]


def test_report_carries_diagnostics(lab: tuple[Path, Run], client: TestClient) -> None:
    _, run = lab
    body = report(client, run)

    assert body["identity_screen"] == run.identity_screen
    assert body["n_users"] == len({u.user_id for u in run.users})


def test_report_never_reveals_item_labels(lab: tuple[Path, Run], client: TestClient) -> None:
    assert not labels_leak(report(client, lab[1]))


def test_a_mock_dev_run_is_not_a_result(lab: tuple[Path, Run], client: TestClient) -> None:
    body = report(client, lab[1])

    assert body["is_result"] is False
    assert body["not_result_reasons"] == ["mock", "dev", "synthetic"]


def test_a_frozen_run_is_a_result(lab: tuple[Path, Run], tmp_path: Path) -> None:
    _, run = lab
    frozen = replace(run, population="test", mock=False, data_source="mind", is_result=True)

    body = report(saved(frozen, tmp_path), frozen)

    assert body["is_result"] is True
    assert body["not_result_reasons"] == []


def test_an_unfrozen_test_run_is_named_so(lab: tuple[Path, Run], tmp_path: Path) -> None:
    _, run = lab
    unfrozen = replace(run, population="test", mock=False, data_source="mind", is_result=False)

    assert report(saved(unfrozen, tmp_path), unfrozen)["not_result_reasons"] == ["unfrozen"]


def test_a_run_without_d_and_a_has_no_primary(lab: tuple[Path, Run], tmp_path: Path) -> None:
    directory, _ = lab
    run = make_run(directory, ["C", "random"])

    body = report(saved(run, tmp_path), run)

    assert body["primary"] is None
    assert [r["arm"] for r in body["reliability"]] == ["C"]  # type: ignore[union-attr]


def test_a_report_in_an_unknown_shape_is_an_error(lab: tuple[Path, Run], tmp_path: Path) -> None:
    _, run = lab
    garbled = replace(run, metrics={"arms": {"A": {"n": "many"}}})

    response = saved(garbled, tmp_path).get(f"/api/run/{run.run_id}/report")

    assert response.status_code == 422
    assert response.json()["code"] == "incompatible_run"


def test_a_run_without_a_report_is_an_error_not_empty(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    _, run = lab
    empty = replace(run, metrics={})

    response = saved(empty, tmp_path).get(f"/api/run/{run.run_id}/report")

    assert response.status_code == 409
    assert response.json()["code"] == "report_unavailable"


def test_unknown_run_report_is_404(client: TestClient) -> None:
    response = client.get("/api/run/20990101-000000-dev-nope/report")

    assert response.status_code == 404
    assert response.json()["code"] == "run_not_found"


# GET /api/run/{run_id}/user/{user_id}/predictions


def predictions(client: TestClient, run: Run, user_id: str) -> dict[str, object]:
    response = client.get(f"/api/run/{run.run_id}/user/{user_id}/predictions")
    assert response.status_code == 200, response.text
    return response.json()


def test_predictions_rank_each_arm_against_the_real_clicks(
    lab: tuple[Path, Run], client: TestClient
) -> None:
    _, run = lab
    user = run.users[0].user_id
    body = predictions(client, run, user)

    stored = {u.arm: u for u in run.users if u.user_id == user}
    candidates = body["candidates"]
    assert isinstance(candidates, list)
    assert [c["news_id"] for c in candidates] == list(stored["A"].items)
    assert [c["clicked"] for c in candidates] == [
        bool(stored["A"].labels[i]) for i in stored["A"].items
    ]
    assert candidates[0]["title"]

    arms = {a["arm"]: a for a in body["arms"]}  # type: ignore[union-attr]
    assert list(arms) == ARMS
    d = arms["D"]
    assert [p["news_id"] for p in d["predictions"]] == list(stored["D"].items)
    order = rank(stored["D"].scores, stored["D"].tie_rank)
    assert [p["rank"] for p in d["predictions"]] == [order.index(i) + 1 for i in stored["D"].items]
    assert [p["p_click"] for p in d["predictions"]] == [
        stored["D"].scores[i] for i in stored["D"].items
    ]
    assert d["predictions"][0]["reaction"] == stored["D"].reactions[stored["D"].items[0]]
    assert arms["random"]["kind"] == "baseline"
    assert all(
        p["p_click"] is None and p["reaction"] is None for p in arms["random"]["predictions"]
    )


def test_predictions_place_the_user_in_their_bucket(
    lab: tuple[Path, Run], client: TestClient
) -> None:
    _, run = lab
    user = run.users[0].user_id
    body = predictions(client, run, user)

    per_user = next(
        d["per_user"]
        for d in run.metrics["differences"]  # type: ignore[union-attr]
        if (d["arm"], d["reference"]) == ("D", "A")
    )
    assert body["d_minus_a"] == per_user[user]
    assert body["bucket"] == outcome_bucket(per_user[user])
    assert body["is_result"] is False


def test_predictions_are_the_only_endpoint_with_labels(
    lab: tuple[Path, Run], client: TestClient
) -> None:
    _, run = lab
    user = run.users[0].user_id

    assert '"clicked"' in json.dumps(predictions(client, run, user))
    assert not labels_leak(client.get(f"/api/run/{run.run_id}/population").json())
    assert not labels_leak(client.get(f"/api/run/{run.run_id}/agent/{user}").json())


def test_predictions_for_an_unknown_user_is_404(lab: tuple[Path, Run], client: TestClient) -> None:
    response = client.get(f"/api/run/{lab[1].run_id}/user/U-nobody/predictions")

    assert response.status_code == 404
    assert response.json()["code"] == "agent_not_found"


def test_report_endpoints_work_in_demo_mode(lab: tuple[Path, Run]) -> None:
    directory, run = lab
    demo = make_client(data_dir=str(directory), demo_mode=True)

    assert demo.get(f"/api/run/{run.run_id}/report").status_code == 200
    user = run.users[0].user_id
    assert demo.get(f"/api/run/{run.run_id}/user/{user}/predictions").status_code == 200
