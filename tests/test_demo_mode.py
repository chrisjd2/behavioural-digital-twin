"""The DEMO_MODE audit (ADR-0011, #23): the public demo is read-only, and the interview is its
only LLM caller, rate-limited. Every route must be classified here, so a new one cannot
reach the hosted demo without someone deciding what it does there."""

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import httpx
import openai
import pytest
from fastapi import APIRouter, FastAPI
from starlette.routing import BaseRoute, Mount, Route, WebSocketRoute

from backend import clients, simulation
from backend.main import DEMO_CSP, build_app
from tests.test_build_demo_data import Lab
from tests.test_status import make_client, make_settings

Policy = Literal["read", "refused", "interview", "static"]

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
    ("MOUNT", ""): "static",  # the built frontend: StaticFiles answers GET and HEAD only
}
OPEN_WRITES = {("POST", "/api/interview")}


def walk(routes: Iterable[BaseRoute]) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in routes:
        if isinstance(route, Route):  # APIRoute too
            found |= {(m, route.path) for m in route.methods or ()}
        elif isinstance(route, WebSocketRoute):
            found.add(("WEBSOCKET", route.path))
        elif isinstance(route, Mount):
            found.add(("MOUNT", route.path))
        elif router := getattr(route, "original_router", None):
            # FastAPI 0.147 keeps an included router behind a lazy wrapper.
            found |= walk(router.routes)
        else:
            raise AssertionError(f"Unknown route kind {route!r}: teach the audit about it.")
    return found


def routes(app: FastAPI) -> set[tuple[str, str]]:
    """The router walk, plus OpenAPI for prefixes the walk does not apply."""
    found = walk(app.router.routes)
    schema = app.openapi_schema or (app.openapi() if app.openapi_url else {})
    paths = schema.get("paths", {})
    return found | {(m.upper(), p) for p, item in paths.items() for m in item}


def unclassified_writes(app: FastAPI) -> set[tuple[str, str]]:
    """Routes that are not GET or HEAD and not refused-or-allowed by POLICY."""
    return {
        key
        for key in routes(app)
        if key[0] not in ("GET", "HEAD")
        and POLICY.get(key) not in ("refused", "static")
        and key not in OPEN_WRITES
    }


def frontend(tmp_path: Path) -> str:
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return str(tmp_path)


def demo_app(tmp_path: Path) -> FastAPI:
    return build_app(make_settings(demo_mode=True, frontend_dist=frontend(tmp_path)))


def test_every_route_has_a_demo_policy(tmp_path: Path) -> None:
    assert routes(demo_app(tmp_path)) == POLICY.keys()


def test_no_unclassified_write_route(tmp_path: Path) -> None:
    assert unclassified_writes(demo_app(tmp_path)) == set()


def test_the_audit_catches_a_new_write_route(tmp_path: Path) -> None:
    app = demo_app(tmp_path)
    router = APIRouter()
    router.add_api_route("/api/new", lambda: None, methods=["DELETE"])
    app.include_router(router)
    app.add_api_route("/api/other", lambda: None, methods=["PUT"])
    app.add_api_websocket_route("/api/ws", lambda _: None)
    app.openapi_schema = None

    assert unclassified_writes(app) == {
        ("DELETE", "/api/new"),
        ("PUT", "/api/other"),
        ("WEBSOCKET", "/api/ws"),
    }


@pytest.mark.parametrize("key", [k for k, p in POLICY.items() if p == "refused"])
def test_refused_routes_answer_403_in_demo_mode(key: tuple[str, str]) -> None:
    method, path = key
    url = path.replace("{run_id}", "r").replace("{live_id}", "live-x")

    response = make_client(demo_mode=True).request(method, url, json={})

    assert response.status_code == 403
    assert response.json()["code"] == "demo_mode"


def test_the_static_frontend_refuses_writes(tmp_path: Path) -> None:
    client = make_client(demo_mode=True, frontend_dist=frontend(tmp_path))

    assert client.get("/").status_code == 200
    assert client.post("/").status_code == 405


def test_the_interview_is_rate_limited_in_demo_mode() -> None:
    client = make_client(demo_mode=True, interview_daily_limit=0)
    question = {"run_id": "r", "user_id": "U1", "arm": "D", "question": "Hello?"}

    response = client.post("/api/interview", json=question)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_no_api_docs_in_demo_mode(path: str) -> None:
    assert make_client(demo_mode=True).get(path).status_code == 404
    assert make_client(demo_mode=False).get(path).status_code == 200


def test_security_headers_with_a_csp_in_demo_mode() -> None:
    demo = make_client(demo_mode=True).get("/api/status").headers
    local = make_client(demo_mode=False).get("/api/status").headers

    for headers in (demo, local):
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "no-referrer"
    assert demo["content-security-policy"] == DEMO_CSP.decode()
    assert "frame-ancestors 'none'" in demo["content-security-policy"]
    assert "content-security-policy" not in local


# Read routes never reach an LLM or embedding API, even in real mode with a key (a fake one).


@pytest.fixture(scope="module")
def lab(tmp_path_factory: pytest.TempPathFactory) -> Lab:
    return Lab(tmp_path_factory.mktemp("audit-lab"))


@pytest.fixture
def no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("an LLM or embedding client was built or called")

    monkeypatch.setattr(openai.AsyncOpenAI, "__init__", refuse)
    monkeypatch.setattr(openai.OpenAI, "__init__", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)  # TestClient uses the sync client
    monkeypatch.setattr(clients, "build_llm", refuse)
    monkeypatch.setattr(simulation, "build_llm", refuse)


def test_read_and_refused_routes_never_call_the_llm(lab: Lab, no_llm: None) -> None:
    run = lab.result
    user_id = run.users[0].user_id
    client = make_client(**lab.settings(demo_mode=True, mock_llm=False).model_dump())

    for (method, path), policy in POLICY.items():
        if policy not in ("read", "refused"):
            continue
        url = (
            path.replace("{run_id}", run.run_id)
            .replace("{user_id}", user_id)
            .replace("{live_id}", "live-x")
        )
        response = client.request(method, url, json={} if method == "POST" else None)
        assert response.status_code == (200 if policy == "read" else 403), (url, response.text)
