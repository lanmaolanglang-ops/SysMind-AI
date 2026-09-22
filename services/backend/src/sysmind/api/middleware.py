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

# Hard cap on declared request body size. The local API only exchanges small JSON
# commands and never accepts uploads, so anything larger is rejected before routing.
_MAX_BODY_BYTES = 2 * 1024 * 1024
_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _resolve_correlation_id(header_value: str | None) -> str:
    if header_value and _CORRELATION_ID.fullmatch(header_value):
        return header_value
    return str(uuid.uuid4())


def _tokens_match(provided: str, expected: str) -> bool:
    # hmac.compare_digest raises TypeError for non-ASCII str, which surfaces as a
    # 500. Comparing UTF-8 bytes accepts any token encoding and never type-errors.
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


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

        if request.method in _STATE_CHANGING_METHODS and not origin:
            return self._error(
                status.HTTP_403_FORBIDDEN,
                "origin_required",
                "State-changing requests require an allowed origin.",
                correlation_id,
            )
        if origin and origin not in self._allowed_origins:
            return self._error(
                status.HTTP_403_FORBIDDEN,
                "origin_not_allowed",
                "The request origin is not allowed.",
                correlation_id,
            )

        # This API accepts no streamed uploads. Reject chunked bodies so callers cannot
        # bypass the declared-size gate by omitting Content-Length.
        if request.headers.get("transfer-encoding"):
            return self._error(
                status.HTTP_411_LENGTH_REQUIRED,
                "content_length_required",
                "Chunked request bodies are not accepted by the local API.",
                correlation_id,
            )

        content_length = request.headers.get("content-length")
        if request.method in _STATE_CHANGING_METHODS and content_length is None:
            return self._error(
                status.HTTP_411_LENGTH_REQUIRED,
                "content_length_required",
                "State-changing requests require Content-Length.",
                correlation_id,
            )
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                return self._error(
                    status.HTTP_400_BAD_REQUEST,
                    "invalid_content_length",
                    "Content-Length must be an integer.",
                    correlation_id,
                )
            if declared_length < 0 or declared_length > _MAX_BODY_BYTES:
                return self._error(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "payload_too_large",
                    "Request body exceeds the local API size limit.",
                    correlation_id,
                )

        # Only true CORS preflight (OPTIONS + Access-Control-Request-Method) skips the
        # session token so the browser can discover allowed headers. Any other OPTIONS
        # is an ordinary call and must still authenticate.
        is_cors_preflight = (
            request.method == "OPTIONS"
            and request.headers.get("access-control-request-method") is not None
        )
        if not is_cors_preflight:
            provided = request.headers.get(SESSION_HEADER, "")
            if not provided or not _tokens_match(provided, self._expected_token):
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
