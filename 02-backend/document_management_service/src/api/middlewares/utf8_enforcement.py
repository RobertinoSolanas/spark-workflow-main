"""UTF-8 Enforcement Middleware for security purposes."""

from collections.abc import Callable

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
)
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.utils.logger import logger


class UTF8EnforcementMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce UTF-8 encoding for security reasons.

    This middleware:
    1. Checks incoming requests for non-UTF-8 charset declarations
    2. Rejects requests with explicitly declared non-UTF-8 encodings
    3. Ensures response headers specify UTF-8 charset
    4. Logs potential encoding-based security attempts
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check Content-Type header for non-UTF-8 charset
        content_type = request.headers.get("content-type", "")

        if "charset=" in content_type.lower():
            charset_part = (
                content_type.lower().split("charset=")[1].split(";")[0].strip()
            )
            if charset_part not in ["utf-8", "utf8"]:
                logger.warn(
                    action=EventAction.VALIDATE,
                    outcome=EventOutcome.FAILURE,
                    category=EventCategory.API,
                    message=(
                        f"Security: Non-UTF-8 charset rejected - "
                        f"Client IP: "
                        f"{request.client.host if request.client else 'unknown'}, "
                        f"Charset: {charset_part}, "
                        f"Content-Type: {content_type}"
                    ),
                )
                return Response(
                    content="Bad Request",
                    status_code=400,
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                )

        response = await call_next(request)

        return response
