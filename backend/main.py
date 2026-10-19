from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import Settings, get_settings


class AppError(Exception):
    """An error with an HTTP status and a stable machine-readable code."""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


class Status(BaseModel):
    mock: bool
    demo_mode: bool
    model: str
    data_source: str
    call_count: int


def build_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Twin Lab")

    @app.exception_handler(AppError)
    async def handle_app_exception(_: Request, exc: AppError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse(
            status_code=exc.status_code, content={"code": exc.code, "detail": exc.detail}
        )

    @app.get("/api/status")
    def status() -> Status:  # pyright: ignore[reportUnusedFunction]
        return Status(
            mock=settings.mock_llm,
            demo_mode=settings.demo_mode,
            model=settings.llm_model,
            data_source="none",
            call_count=0,
        )

    # Mounted last so /api routes take precedence.
    dist = Path(settings.frontend_dist)
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")

    return app


app = build_app(get_settings())
