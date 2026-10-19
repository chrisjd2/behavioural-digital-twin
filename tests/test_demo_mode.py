"""The DEMO_MODE audit (ADR-0011, #23): the public demo is read-only, and the interview is its
only LLM caller, rate-limited. Every route must be classified here, so a new one cannot
reach the hosted demo without someone deciding what it does there."""

from typing import Literal

import pytest

from backend.main import build_app
from tests.test_status import make_client, make_settings

Policy = Literal["read", "refused", "interview"]

POLICY: dict[tuple[str, str], Policy] = {
    ("GET", "/api/status"): "read",
    ("POST", "/api/experiment"): "refused",
    ("GET", "/api/runs"): "read",
    ("GET", "/api/run/{run_id}"): "read",
    ("GET", "/api/run/{run_id}/population"): "read",
    ("GET", "/api/run/{run_id}/agent/{user_id}"): "read",
    ("GET", "/api/hook"): "read",
    ("GET", "/api/run/{run_id}/events"): "read",
    ("POST", "/api/run"): "refused",
    ("GET", "/api/run/{live_id}/stream"): "refused",
    ("GET", "/api/run/{run_id}/report"): "read",
    ("GET", "/api/run/{run_id}/user/{user_id}/predictions"): "read",
    ("POST", "/api/interview"): "interview",
    ("GET", "/api/interview/recorded"): "read",
}


def api_routes() -> set[tuple[str, str]]:
    """From the OpenAPI schema: FastAPI keeps included routers' routes out of `app.routes`."""
    paths = build_app(make_settings(demo_mode=True)).openapi()["paths"]
    return {(method.upper(), path) for path, item in paths.items() for method in item}


def test_every_api_route_has_a_demo_policy() -> None:
    assert api_routes() == POLICY.keys()


def test_only_get_routes_and_the_interview_are_open_in_demo_mode() -> None:
    writes = {key: policy for key, policy in POLICY.items() if key[0] != "GET"}

    assert {key for key, policy in writes.items() if policy != "refused"} == {
        ("POST", "/api/interview")
    }


@pytest.mark.parametrize("key", [k for k, p in POLICY.items() if p == "refused"])
def test_refused_routes_answer_403_in_demo_mode(key: tuple[str, str]) -> None:
    method, path = key
    url = path.replace("{run_id}", "r").replace("{live_id}", "live-x")

    response = make_client(demo_mode=True).request(method, url, json={})

    assert response.status_code == 403
    assert response.json()["code"] == "demo_mode"


def test_the_interview_is_rate_limited_in_demo_mode() -> None:
    client = make_client(demo_mode=True, interview_daily_limit=0)
    question = {"run_id": "r", "user_id": "U1", "arm": "D", "question": "Hello?"}

    response = client.post("/api/interview", json=question)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
