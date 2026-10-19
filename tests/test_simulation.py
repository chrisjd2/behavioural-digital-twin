"""Step 3 Simulation: saved-run events for replay, and live dev runs over SSE (#19)."""

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.experiment import ARMS as BASELINES
from backend.runner import LLM_ARMS, Run, RunEvent
from backend.runs import RUNS_SUBDIR, save_run
from backend.sample import write_synthetic_sample
from backend.simulation import ALL_ARMS
from tests.test_api_runs import ARMS, make_run
from tests.test_status import make_client

EVENT_KEYS = {
    "call_started": {"seq", "kind", "user_id", "arm"},
    "reaction": {
        "seq",
        "kind",
        "user_id",
        "arm",
        "news_id",
        "headline",
        "reaction",
        "p_click",
        "clicked",
    },
    "arm_progress": {"seq", "kind", "arm", "done", "total"},
    "run_complete": {"seq", "kind", "run_id"},
}


@pytest.fixture(scope="module")
def lab(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Run]:
    directory = tmp_path_factory.mktemp("sim")
    # Live runs sample dev outside the full test reserve, so the sample needs > 300 users.
    write_synthetic_sample(directory / "sample", n_users=600, n_news=300, seed=1)
    run = make_run(directory, ARMS)
    save_run(run, directory / RUNS_SUBDIR)
    return directory, run


@pytest.fixture
def client(lab: tuple[Path, Run]) -> Iterator[TestClient]:
    # Entered, so the live run's background task outlives the POST that starts it.
    with make_client(data_dir=str(lab[0])) as client:
        yield client


# GET /api/run/{id}/events


def test_events_come_in_seq_order_with_the_run_summary(
    client: TestClient, lab: tuple[Path, Run]
) -> None:
    _, run = lab
    body = client.get(f"/api/run/{run.run_id}/events").json()

    assert body["run"]["run_id"] == run.run_id
    assert body["run"]["mock"] is True
    assert body["run"]["data_source"] == "synthetic"
    assert [e["seq"] for e in body["events"]] == list(range(len(run.events)))
    assert body["events"][-1] == {
        "seq": len(run.events) - 1,
        "kind": "run_complete",
        "run_id": run.run_id,
    }
    assert body["recorded_seconds"] >= 0


def test_events_are_sorted_by_seq_even_if_the_file_is_not(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    _, run = lab
    shuffled = replace(run, run_id="shuffled", events=list(reversed(run.events)))
    save_run(shuffled, tmp_path / RUNS_SUBDIR)

    body = make_client(data_dir=str(tmp_path)).get("/api/run/shuffled/events").json()

    assert [e["seq"] for e in body["events"]] == list(range(len(run.events)))


def test_events_have_a_compact_whitelisted_shape(client: TestClient, lab: tuple[Path, Run]) -> None:
    _, run = lab
    events = client.get(f"/api/run/{run.run_id}/events").json()["events"]

    assert {e["kind"] for e in events} == set(EVENT_KEYS)
    for event in events:
        assert set(event) == EVENT_KEYS[event["kind"]]
    reaction = next(e for e in events if e["kind"] == "reaction")
    assert isinstance(reaction["clicked"], bool)
    assert 0 <= reaction["p_click"] <= 100
    assert reaction["headline"]
    assert reaction["reaction"]


def test_events_never_carry_settings_or_secrets(lab: tuple[Path, Run]) -> None:
    directory, run = lab
    client = make_client(data_dir=str(directory), llm_api_key="sk-very-secret")
    text = client.get(f"/api/run/{run.run_id}/events").text

    for leak in ("sk-very-secret", "base_url", "fingerprint", "knowledge", "git_sha", "mock://"):
        assert leak not in text


def test_events_are_gzipped_when_the_browser_accepts_it(
    client: TestClient, lab: tuple[Path, Run]
) -> None:
    response = client.get(f"/api/run/{lab[1].run_id}/events", headers={"Accept-Encoding": "gzip"})

    assert response.headers["content-encoding"] == "gzip"


def test_events_of_a_missing_run_are_404(client: TestClient) -> None:
    response = client.get("/api/run/20200101-000000-dev-nope/events")

    assert response.status_code == 404
    assert response.json()["code"] == "run_not_found"


def test_events_in_an_older_shape_are_an_error_not_empty(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    _, run = lab
    old = replace(run, run_id="old", events=[RunEvent(0, "2026-10-19T00:00:00", "reaction", {})])
    save_run(old, tmp_path / RUNS_SUBDIR)

    response = make_client(data_dir=str(tmp_path)).get("/api/run/old/events")

    assert response.status_code == 422
    assert response.json()["code"] == "incompatible_run"


def test_events_are_readable_in_demo_mode(lab: tuple[Path, Run]) -> None:
    directory, run = lab
    response = make_client(data_dir=str(directory), demo_mode=True).get(
        f"/api/run/{run.run_id}/events"
    )

    assert response.status_code == 200


# POST /api/run and GET /api/run/{id}/stream


def sse_messages(client: TestClient, live_id: str) -> list[tuple[str, dict[str, object]]]:
    messages: list[tuple[str, dict[str, object]]] = []
    event = ""
    with client.stream("GET", f"/api/run/{live_id}/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                messages.append((event, json.loads(line.removeprefix("data:"))))
                if event in ("run_saved", "run_failed"):
                    break
    return messages


def test_a_live_dev_run_streams_its_events_in_order_then_is_saved(
    client: TestClient, lab: tuple[Path, Run]
) -> None:
    started = client.post("/api/run", json={"arms": ["A", "random"], "n_users": 3})
    assert started.status_code == 200
    live_id = started.json()["live_id"]

    messages = sse_messages(client, live_id)

    *events, (last, saved) = messages
    assert last == "run_saved"
    assert all(name == "run_event" for name, _ in events)
    assert [e["seq"] for _, e in events] == list(range(len(events)))
    kinds = [e["kind"] for _, e in events]
    assert kinds[0] == "call_started"
    assert kinds[-1] == "run_complete"
    assert kinds.count("reaction") > 0
    run_id = str(saved["run_id"])
    assert events[-1][1]["run_id"] == run_id
    assert (lab[0] / RUNS_SUBDIR / f"{run_id}.json").is_file()
    assert client.get(f"/api/run/{run_id}").json()["population"] == "dev"


def test_a_late_subscriber_still_gets_every_event(client: TestClient) -> None:
    live_id = client.post("/api/run", json={"arms": ["random"], "n_users": 2}).json()["live_id"]

    first = sse_messages(client, live_id)
    again = sse_messages(client, live_id)

    assert first == again
    assert first[-1][0] == "run_saved"


def test_a_failed_live_run_ends_its_stream_with_the_reason(tmp_path: Path) -> None:
    # No data in DATA_DIR: the run fails once started; the stream says so instead of hanging.
    with make_client(data_dir=str(tmp_path)) as client:
        live_id = client.post("/api/run", json={"arms": ["random"], "n_users": 2}).json()["live_id"]
        messages = sse_messages(client, live_id)

    assert messages[-1][0] == "run_failed"
    assert messages[-1][1]["detail"]


@pytest.mark.parametrize("population", ["test", "TEST", "reserve"])
def test_the_live_path_never_runs_the_test_population(client: TestClient, population: str) -> None:
    response = client.post("/api/run", json={"population": population, "arms": ["random"]})

    assert response.status_code == 422


def test_unknown_arms_and_sizes_are_refused(client: TestClient) -> None:
    assert client.post("/api/run", json={"arms": ["Z"]}).status_code == 422
    assert client.post("/api/run", json={"arms": []}).status_code == 422
    assert client.post("/api/run", json={"n_users": 0}).status_code == 422


def test_the_stream_of_an_unknown_live_run_is_404(client: TestClient) -> None:
    response = client.get("/api/run/live-nope/stream")

    assert response.status_code == 404
    assert response.json()["code"] == "live_run_not_found"


@pytest.mark.parametrize(
    "body", [{}, {"population": "dev"}, {"population": "test", "arms": ["random"]}]
)
def test_demo_mode_refuses_live_runs(lab: tuple[Path, Run], body: dict[str, object]) -> None:
    with make_client(data_dir=str(lab[0]), demo_mode=True) as client:
        response = client.post("/api/run", json=body)

    assert response.status_code == 403
    assert response.json()["code"] == "demo_mode"


def test_demo_mode_refuses_live_streams(lab: tuple[Path, Run]) -> None:
    response = make_client(data_dir=str(lab[0]), demo_mode=True).get("/api/run/live-x/stream")

    assert response.status_code == 403
    assert response.json()["code"] == "demo_mode"


def test_live_run_defaults_cover_every_arm(client: TestClient) -> None:
    assert set(ALL_ARMS) == {*LLM_ARMS, *BASELINES}
    schema = client.get("/openapi.json").json()["components"]["schemas"]["LiveRunRequest"]

    assert schema["properties"]["arms"]["default"] == [
        "A",
        "B",
        "C",
        "D",
        "E",
        "popularity",
        "random",
    ]
    assert "population" not in schema["properties"]  # always dev: the test set ran once
