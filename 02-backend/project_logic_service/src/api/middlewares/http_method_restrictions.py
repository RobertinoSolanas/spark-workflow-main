from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.settings import settings


class HTTPMethodRestrictionsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to restrict specific HTTP methods.

    This middleware blocks requests using the following HTTP methods:
    - TRACE
    - PUT

    These methods are blocked for security reasons to reduce the attack surface.
    OPTIONS is allowed for CORS preflight requests.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process the request and block specific HTTP methods.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or endpoint handler

        Returns:
            Response: Either an error response for blocked methods or
                     the result of calling the next handler

        Raises:
            HTTPException: 405 Method Not Allowed for blocked methods
        """
        if request.method in settings.BLOCKED_HTTP_METHODS:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail=f"HTTP method '{request.method}' is not allowed",
            )

        response = await call_next(request)
        return response
