from pathlib import Path

import pytest

from backend.data import is_eligible, load_behaviors, resolve_data_source
from backend.experiment import ExperimentConfig
from backend.runner import candidate_sets, sampled_populations
from tests.test_status import make_client


def build(data_dir: Path, **body: object):
    return make_client(data_dir=str(data_dir)).post("/api/experiment", json=body)


def test_builds_the_dev_population_with_defaults(data_dir: Path) -> None:
    response = build(data_dir)

    assert response.status_code == 200
    body = response.json()
    config = ExperimentConfig()
    assert body["population"] == "dev"
    assert body["data_source"] == "synthetic"
    assert body["n_users"] == config.n_dev
    assert body["seed"] == config.dev_seed
    assert body["max_candidates"] == config.max_candidates


def test_summary_matches_the_runner_candidate_sets(data_dir: Path) -> None:
    body = build(data_dir, n_users=12, seed=7, max_candidates=6).json()

    config = ExperimentConfig(n_dev=12, dev_seed=7, max_candidates=6)
    populations = sampled_populations(resolve_data_source(data_dir), config)
    sets = candidate_sets(populations, config, "dev")
    assert body["user_ids"] == [c.user_id for c in sets]
    assert not set(body["user_ids"]) & {i.user_id for i in populations.test}
    assert body["n_candidates"] == sum(len(c.items) for c in sets)
    assert max(len(c.items) for c in sets) <= 6
    assert body["mean_feed_ctr"] == pytest.approx(sum(c.feed_ctr for c in sets) / 12)
    assert body["mean_sample_ctr"] == pytest.approx(sum(c.sample_ctr for c in sets) / 12)


def test_eligible_users_exclude_the_test_set(data_dir: Path) -> None:
    body = build(data_dir, n_users=10).json()

    impressions = load_behaviors(data_dir / "sample" / "dev" / "behaviors.tsv")
    eligible = {i.user_id for i in impressions if is_eligible(i)}
    assert body["eligible_users"] == len(eligible) - ExperimentConfig().n_test


def test_reports_categories_read(data_dir: Path) -> None:
    body = build(data_dir, n_users=10).json()

    assert body["categories"], "synthetic users read at least one category"
    counts = [c["users"] for c in body["categories"]]
    assert counts == sorted(counts, reverse=True)
    assert all(1 <= n <= 10 for n in counts)


def test_seed_changes_who_is_sampled(data_dir: Path) -> None:
    first = build(data_dir, n_users=10, seed=1).json()
    again = build(data_dir, n_users=10, seed=1).json()
    other = build(data_dir, n_users=10, seed=2).json()

    assert first == again
    assert {**first, "seed": 0} != {**other, "seed": 0}


def test_demo_mode_refuses_to_build(data_dir: Path) -> None:
    response = make_client(data_dir=str(data_dir), demo_mode=True).post("/api/experiment", json={})

    assert response.status_code == 403
    assert response.json()["code"] == "demo_mode"


def test_no_data_is_an_error_not_an_empty_population(tmp_path: Path) -> None:
    response = build(tmp_path)

    assert response.status_code == 409
    assert response.json()["code"] == "no_data"


def test_too_many_users_is_an_error(data_dir: Path) -> None:
    response = build(data_dir, n_users=100_000)

    assert response.status_code == 422


def test_more_users_than_eligible_is_an_app_error(data_dir: Path) -> None:
    response = build(data_dir, n_users=5000)

    assert response.status_code == 422
    assert response.json()["code"] == "not_enough_users"


@pytest.mark.parametrize("field", ["n_users", "max_candidates"])
def test_rejects_non_positive_sizes(data_dir: Path, field: str) -> None:
    assert build(data_dir, **{field: 0}).status_code == 422


def test_status_carries_the_experiment_defaults() -> None:
    config = ExperimentConfig()

    body = make_client().get("/api/status").json()

    assert body["experiment_defaults"] == {
        "n_users": config.n_dev,
        "seed": config.dev_seed,
        "max_candidates": config.max_candidates,
    }
