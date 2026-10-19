from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import AppError, build_app


def make_settings(**overrides: object) -> Settings:
    # No frontend build by default, so tests don't depend on the working tree.
    defaults = {"llm_model": "gemini-test-001", "frontend_dist": "does-not-exist"}
    return Settings.model_validate({**defaults, **overrides})


def make_client(**overrides: object) -> TestClient:
    return TestClient(build_app(make_settings(**overrides)))


def test_status_reports_mock_model_and_demo_flags() -> None:
    response = make_client(mock_llm=True, demo_mode=False).get("/api/status")

    assert response.status_code == 200
    assert response.json() == {
        "mock": True,
        "demo_mode": False,
        "model": "gemini-test-001",
        "data_source": "none",
        "call_count": 0,
    }


def test_status_reflects_real_mode_and_demo_mode() -> None:
    body = make_client(mock_llm=False, demo_mode=True).get("/api/status").json()

    assert body["mock"] is False
    assert body["demo_mode"] is True


def test_app_exception_returns_code_and_detail() -> None:
    app = build_app(make_settings())

    @app.get("/api/boom")
    def boom() -> None:
        raise AppError(409, "run_in_progress", "A run is already in progress")

    response = TestClient(app).get("/api/boom")

    assert response.status_code == 409
    assert response.json() == {"code": "run_in_progress", "detail": "A run is already in progress"}


def test_serves_built_frontend_when_present(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<h1>Twin Lab</h1>", encoding="utf-8")

    response = make_client(frontend_dist=str(tmp_path)).get("/")

    assert response.status_code == 200
    assert "Twin Lab" in response.text
