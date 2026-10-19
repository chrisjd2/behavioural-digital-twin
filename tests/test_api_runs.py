"""Run-centric read endpoints for Steps 2-4: run list, population and agent detail (#18)."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.data import load_news, resolve_data_source
from backend.experiment import ExperimentConfig
from backend.llm import Cache, LLMClient, mock_backend
from backend.runner import Run, UserResult, run_experiment
from backend.runs import RUNS_SUBDIR, save_run
from backend.sample import write_synthetic_sample
from tests.test_runner import OPTIONS
from tests.test_status import make_client

CONFIG = ExperimentConfig(n_dev=8, n_test=20)
ARMS = ["A", "B", "C", "D", "E", "random"]


def make_run(data_dir: Path, arms: list[str]) -> Run:
    client = LLMClient(
        model="mock",
        base_url="mock://",
        cache=Cache(data_dir / "cache.sqlite"),
        backend=mock_backend,
        concurrency=4,
    )
    source = resolve_data_source(data_dir)
    return asyncio.run(
        run_experiment(source, CONFIG, population="dev", arms=arms, client=client, options=OPTIONS)
    )


@pytest.fixture(scope="module")
def lab(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Run]:
    """A data dir with the synthetic sample and one real mock run of every LLM arm."""
    directory = tmp_path_factory.mktemp("lab")
    write_synthetic_sample(directory / "sample", n_users=400, n_news=300, seed=1)
    run = make_run(directory, ARMS)
    save_run(run, directory / RUNS_SUBDIR)
    return directory, run


@pytest.fixture
def client(lab: tuple[Path, Run]) -> TestClient:
    return make_client(data_dir=str(lab[0]))


def labels_leak(body: object) -> bool:
    text = json.dumps(body)
    return any(key in text for key in ('"labels"', '"clicked"', '"scores"', '"p_click"'))


# GET /api/runs


def test_lists_runs_newest_first_with_their_summary(lab: tuple[Path, Run], tmp_path: Path) -> None:
    _, run = lab
    runs = tmp_path / RUNS_SUBDIR
    save_run(run, runs)
    older = replace(run, run_id="20200101-000000-dev-aaaaaa", created="2020-01-01T00:00:00+00:00")
    save_run(older, runs)

    body = make_client(data_dir=str(tmp_path)).get("/api/runs").json()

    assert [r["run_id"] for r in body["runs"]] == [run.run_id, older.run_id]
    assert body["runs"][0] == {
        "run_id": run.run_id,
        "created": run.created,
        "population": "dev",
        "arms": ARMS,
        "model": "mock",
        "mock": True,
        "data_source": "synthetic",
        "is_result": False,
        "n_users": CONFIG.n_dev,
    }
    assert body["problems"] == []


def test_no_runs_dir_is_an_empty_list_not_an_error(tmp_path: Path) -> None:
    response = make_client(data_dir=str(tmp_path)).get("/api/runs")

    assert response.status_code == 200
    assert response.json() == {"runs": [], "problems": []}


def test_corrupt_and_old_run_files_are_reported_not_dropped(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    _, run = lab
    runs = tmp_path / RUNS_SUBDIR
    save_run(run, runs)
    (runs / "20200101-000000-dev-broken.json").write_text("{not json", encoding="utf-8")
    old = json.loads((runs / f"{run.run_id}.json").read_text(encoding="utf-8"))
    for user in old["users"]:
        del user["history"]  # saved before the panel's history existed
    (runs / "20200102-000000-dev-old.json").write_text(json.dumps(old), encoding="utf-8")

    body = make_client(data_dir=str(tmp_path)).get("/api/runs").json()

    assert [r["run_id"] for r in body["runs"]] == [run.run_id]
    problems = {p["run_id"]: p["problem"] for p in body["problems"]}
    assert problems == {
        "20200101-000000-dev-broken": "unreadable",
        "20200102-000000-dev-old": "incompatible",
    }
    assert all(p["detail"] for p in body["problems"])


def test_opening_an_incompatible_run_is_an_error(lab: tuple[Path, Run], tmp_path: Path) -> None:
    runs = tmp_path / RUNS_SUBDIR
    runs.mkdir()
    (runs / "20200101-000000-dev-broken.json").write_text("{not json", encoding="utf-8")

    response = make_client(data_dir=str(tmp_path)).get(
        "/api/run/20200101-000000-dev-broken/population"
    )

    assert response.status_code == 422
    assert response.json()["code"] == "unreadable_run"


# GET /api/run/{run_id}/population


def test_population_links_every_agent_to_the_categories_they_read(
    lab: tuple[Path, Run], client: TestClient
) -> None:
    directory, run = lab
    body = client.get(f"/api/run/{run.run_id}/population").json()

    news = load_news(directory / "sample" / "dev" / "news.tsv")
    users = list(dict.fromkeys(u.user_id for u in run.users))
    assert [a["user_id"] for a in body["agents"]] == users
    first = next(u for u in run.users if u.user_id == users[0])
    expected: dict[str, int] = {}
    for news_id in first.history:
        expected[news[news_id].category] = expected.get(news[news_id].category, 0) + 1
    links = {c["category"]: c["clicks"] for c in body["agents"][0]["categories"]}
    assert links == expected
    assert body["agents"][0]["n_history"] == len(first.history)
    readers = {c["category"]: c["users"] for c in body["categories"]}
    assert set(readers) == {
        c for a in body["agents"] for c in (x["category"] for x in a["categories"])
    }
    assert all(1 <= n <= len(users) for n in readers.values())
    assert body["run_id"] == run.run_id
    assert body["mock"] is True
    assert body["data_source"] == "synthetic"


def test_population_summarises_what_each_llm_arm_knew(
    lab: tuple[Path, Run], client: TestClient
) -> None:
    _, run = lab
    agent = client.get(f"/api/run/{run.run_id}/population").json()["agents"][0]

    knows = {k["arm"]: k for k in agent["knowledge"]}
    assert list(knows) == ["A", "B", "C", "D", "E"]  # baselines know nothing to show
    assert knows["A"] == {
        "arm": "A",
        "memories": 0,
        "profile_items": 0,
        "invented": False,
        "donor": None,
    }
    assert knows["B"]["invented"] is True
    assert knows["C"]["memories"] > 0
    assert knows["D"]["profile_items"] > 0
    assert knows["E"]["donor"] not in (None, agent["user_id"])


def test_population_never_reveals_labels(lab: tuple[Path, Run], client: TestClient) -> None:
    assert not labels_leak(client.get(f"/api/run/{lab[1].run_id}/population").json())


def test_unknown_run_is_404(client: TestClient) -> None:
    for run_id in ("20990101-000000-dev-nope", "a.b", "..%5Csecret"):
        response = client.get(f"/api/run/{run_id}/population")
        assert response.status_code == 404
        assert response.json()["code"] == "run_not_found"


def test_population_errors_when_the_runs_news_is_missing(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    save_run(lab[1], tmp_path / RUNS_SUBDIR)  # no sample beside it

    response = make_client(data_dir=str(tmp_path)).get(f"/api/run/{lab[1].run_id}/population")

    assert response.status_code == 409
    assert response.json()["code"] == "news_unavailable"


def test_read_endpoints_work_in_demo_mode(lab: tuple[Path, Run]) -> None:
    directory, run = lab
    demo = make_client(data_dir=str(directory), demo_mode=True)

    assert demo.get("/api/runs").status_code == 200
    assert demo.get(f"/api/run/{run.run_id}/population").status_code == 200
    user = run.users[0].user_id
    assert demo.get(f"/api/run/{run.run_id}/agent/{user}").status_code == 200


# GET /api/run/{run_id}/agent/{user_id}


def agent(client: TestClient, run: Run, **params: str) -> dict[str, object]:
    response = client.get(f"/api/run/{run.run_id}/agent/{run.users[0].user_id}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def arm(body: dict[str, object], letter: str) -> dict[str, object]:
    arms = body["arms"]
    assert isinstance(arms, list)
    return next(a for a in arms if a["arm"] == letter)


def test_agent_shows_history_and_candidates_as_headlines(
    lab: tuple[Path, Run], client: TestClient
) -> None:
    directory, run = lab
    body = agent(client, run)

    news = load_news(directory / "sample" / "dev" / "news.tsv")
    user = run.users[0]
    first = news[user.history[0]]
    assert body["history"][0] == {  # type: ignore[index]
        "news_id": first.news_id,
        "category": first.category,
        "subcategory": first.subcategory,
        "title": first.title,
    }
    assert [h["news_id"] for h in body["history"]] == list(user.history)  # type: ignore[union-attr]
    assert [c["news_id"] for c in body["candidates"]] == list(user.items)  # type: ignore[union-attr]
    assert [a["arm"] for a in body["arms"]] == ["A", "B", "C", "D", "E"]  # type: ignore[union-attr]


def test_agent_never_reveals_labels(lab: tuple[Path, Run], client: TestClient) -> None:
    assert not labels_leak(agent(client, lab[1]))


def test_agent_knowledge_per_arm(lab: tuple[Path, Run], client: TestClient) -> None:
    _, run = lab
    body = agent(client, run)

    assert arm(body, "A") == {"arm": "A", "kind": "nothing"}

    b = arm(body, "B")
    assert b["kind"] == "persona"
    assert b["invented"] is True
    assert b["persona"]["name"]  # type: ignore[index]

    c = arm(body, "C")
    assert c["kind"] == "memories"
    memories = c["memories"]
    assert isinstance(memories, list)
    assert memories
    assert all(m["reason"] == "recent" or m["reason"].startswith("similar to:") for m in memories)

    d = arm(body, "D")
    assert d["kind"] == "profile"
    assert d["wrong_twin"] is None
    profile = d["profile"]
    assert isinstance(profile, dict)
    items = [i for f in profile["fields"] for i in f["items"]]
    assert items
    assert all(i["text"] and i["evidence"] for i in items)
    assert all(e["title"] for i in items for e in i["evidence"])
    assert profile["identity_hits"] == []
    assert d["memories"]


def test_agent_wrong_twin_is_labelled_control(lab: tuple[Path, Run], client: TestClient) -> None:
    _, run = lab
    e = arm(agent(client, run), "E")
    me = run.users[0].user_id
    stored = next(u for u in run.users if u.arm == "E" and u.user_id == me).knowledge

    assert e["kind"] == "profile"
    assert e["wrong_twin"] == {
        "control": True,
        "donor": stored["donor"],
        "shared_history": stored["shared_history"],
    }


def saved_with(
    run: Run, tmp_path: Path, arm_name: str, change: Callable[[dict[str, object]], object]
) -> TestClient:
    """A client over `run` with one arm's stored knowledge changed, in a fresh data dir."""

    def changed(u: UserResult) -> UserResult:
        knowledge = json.loads(json.dumps(u.knowledge))
        change(knowledge)
        return replace(u, knowledge=knowledge)

    users = [changed(u) if u.arm == arm_name else u for u in run.users]
    save_run(replace(run, users=users), tmp_path / RUNS_SUBDIR)
    write_synthetic_sample(tmp_path / "sample", n_users=400, n_news=300, seed=1)
    return make_client(data_dir=str(tmp_path))


def test_agent_shows_identity_screen_hits(lab: tuple[Path, Run], tmp_path: Path) -> None:
    _, run = lab
    hit = {"kind": "age", "term": "45-year-old", "text": "A 45-year-old"}

    def flag(knowledge: dict[str, object]) -> None:
        knowledge["profile"]["identity_hits"] = [hit]  # type: ignore[index]

    body = agent(saved_with(run, tmp_path, "D", flag), run)

    assert arm(body, "D")["profile"]["identity_hits"] == [hit]  # type: ignore[index]


def test_wrong_twin_saved_before_shared_history_still_shows(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    _, run = lab
    body = agent(saved_with(run, tmp_path, "E", lambda k: k.pop("shared_history")), run)

    assert arm(body, "E")["wrong_twin"]["shared_history"] is None  # type: ignore[index]


def test_knowledge_in_an_unknown_shape_is_an_error(lab: tuple[Path, Run], tmp_path: Path) -> None:
    _, run = lab

    def garble(knowledge: dict[str, object]) -> None:
        knowledge["memories"] = [{"headline": "no id or reason"}]

    client = saved_with(run, tmp_path, "C", garble)
    response = client.get(f"/api/run/{run.run_id}/agent/{run.users[0].user_id}")

    assert response.status_code == 422
    assert response.json()["code"] == "incompatible_run"


def test_agent_can_be_narrowed_to_one_arm(lab: tuple[Path, Run], client: TestClient) -> None:
    body = agent(client, lab[1], arm="C")

    assert [a["arm"] for a in body["arms"]] == ["C"]  # type: ignore[union-attr]


def test_agent_unknown_user_or_arm_is_404(lab: tuple[Path, Run], client: TestClient) -> None:
    _, run = lab
    missing = client.get(f"/api/run/{run.run_id}/agent/U-nobody")
    assert missing.status_code == 404
    assert missing.json()["code"] == "agent_not_found"

    no_arm = client.get(f"/api/run/{run.run_id}/agent/{run.users[0].user_id}", params={"arm": "Z"})
    assert no_arm.status_code == 404
    assert no_arm.json()["code"] == "arm_not_in_run"


def test_a_headline_missing_from_news_is_shown_as_missing(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    _, run = lab
    users = [replace(u, history=(*u.history, "N-gone")) for u in run.users]
    save_run(replace(run, users=users), tmp_path / RUNS_SUBDIR)
    write_synthetic_sample(tmp_path / "sample", n_users=400, n_news=300, seed=1)

    body = agent(make_client(data_dir=str(tmp_path)), run)

    assert body["history"][-1] == {  # type: ignore[index]
        "news_id": "N-gone",
        "category": None,
        "subcategory": None,
        "title": None,
    }
