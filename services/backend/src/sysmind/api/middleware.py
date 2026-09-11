from __future__ import annotations

import hmac
import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from sysmind.core.config import Settings
from sysmind.core.constants import CORRELATION_HEADER, SESSION_HEADER

# Correlation IDs originate from a client-controlled header and are echoed back, so
# they are restricted to a conservative, injection-safe alphabet and bounded length.
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def _resolve_correlation_id(header_value: str | None) -> str:
    if header_value and _CORRELATION_ID.fullmatch(header_value):
        return header_value
    return str(uuid.uuid4())


class LocalApiSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._expected_token = settings.session_token.get_secret_value()
        self._allowed_origins = frozenset(settings.origin_allowlist)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = _resolve_correlation_id(request.headers.get(CORRELATION_HEADER))
        origin = request.headers.get("origin")

        if origin and origin not in self._allowed_origins:
            return self._error(
                status.HTTP_403_FORBIDDEN,
                "origin_not_allowed",
                "The request origin is not allowed.",
                correlation_id,
            )

        if request.method != "OPTIONS":
            provided = request.headers.get(SESSION_HEADER, "")
            if not provided or not hmac.compare_digest(provided, self._expected_token):
                return self._error(
                    status.HTTP_401_UNAUTHORIZED,
                    "invalid_session",
                    "A valid local session token is required.",
                    correlation_id,
                )

        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = correlation_id
        return response

    @staticmethod
    def _error(status_code: int, code: str, message: str, correlation_id: str) -> JSONResponse:
        response = JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "correlation_id": correlation_id,
                }
            },
        )
        response.headers[CORRELATION_HEADER] = correlation_id
        return response
