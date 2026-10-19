"""The one API error type; `backend.main` turns it into `{"code", "detail"}`."""


class AppError(Exception):
    """An error with an HTTP status and a stable machine-readable code."""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
