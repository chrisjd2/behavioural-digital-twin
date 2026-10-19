from pathlib import Path

import pytest

from backend.arms import ARM_SPECS, LLMOptions, prompt_hashes, wrong_twin_donors
from backend.data import DataSource
from backend.experiment import ExperimentConfig
from backend.llm import Cache, LLMClient, mock_backend
from backend.runner import run_experiment

OPTIONS = LLMOptions("medium", 4096, base_rate_hint=False)


@pytest.mark.parametrize("n", [2, 3, 30, 200])
def test_nobody_is_their_own_wrong_twin(n: int) -> None:
    users = [f"U{i}" for i in range(n)]

    donors = wrong_twin_donors(users, seed=1)

    assert set(donors) == set(users)
    assert all(donor != user for user, donor in donors.items())
    assert sorted(donors.values()) == sorted(users)  # everyone lends to exactly one user


def test_assignment_is_deterministic_by_seed_and_ignores_input_order() -> None:
    users = [f"U{i}" for i in range(30)]

    assert wrong_twin_donors(users, seed=1) == wrong_twin_donors(list(reversed(users)), seed=1)
    assert wrong_twin_donors(users, seed=1) != wrong_twin_donors(users, seed=2)


def test_one_user_cannot_have_a_wrong_twin() -> None:
    with pytest.raises(ValueError, match="two users"):
        wrong_twin_donors(["U1"], seed=1)


def test_e_uses_the_same_prompt_as_d() -> None:
    assert ARM_SPECS["E"].render is ARM_SPECS["D"].render
    hashes = prompt_hashes(OPTIONS)
    assert hashes["E"] == hashes["D"]


async def test_arm_e_borrows_another_users_clicks_and_reports_d_minus_e(
    sample_source: DataSource, tmp_path: Path
) -> None:
    client = LLMClient(
        model="mock",
        base_url="mock://",
        cache=Cache(tmp_path / "c.sqlite"),
        backend=mock_backend,
        concurrency=4,
    )

    run = await run_experiment(
        sample_source,
        ExperimentConfig(n_dev=10, n_test=20),
        population="dev",
        arms=["D", "E"],
        client=client,
        options=OPTIONS,
    )

    d = {u.user_id: u for u in run.users if u.arm == "D"}
    e = {u.user_id: u for u in run.users if u.arm == "E"}
    assert set(d) == set(e)
    for user, result in e.items():
        donor = result.knowledge["donor"]
        assert donor != user
        assert result.knowledge["borrowed"] is True
        memories = result.knowledge["memories"]
        assert isinstance(memories, list)
        assert {m["news_id"] for m in memories} <= set(d[str(donor)].history)
        assert not {m["news_id"] for m in memories} & set(result.items)
        assert result.items == d[user].items
        assert result.labels == d[user].labels
    differences = run.metrics["differences"]
    assert isinstance(differences, list)
    assert ("D", "E") in {(x["arm"], x["reference"]) for x in differences}
    assert "E" not in run.identity_screen  # borrowed profiles are screened under D only
