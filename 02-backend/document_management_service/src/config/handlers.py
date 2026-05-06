from asyncpg.exceptions import (
    ForeignKeyViolationError,
    PostgresError,
)
from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
)
from fastapi import FastAPI, Request, status
from fastapi.exceptions import FastAPIError, RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from src.utils.exceptions import (
    FileInvalidFileExtensionError,
    FileInvalidFileTypeError,
    WorkflowAlreadyApprovedError,
    WorkflowAlreadyRejectedError,
    WorkflowIncorrectStatusError,
    WorkflowInPendingStateError,
    WorkflowInRunningStateError,
    WorkflowNotFoundError,
    WorkflowRequiresApprovalError,
    WorkflowValidateDiffError,
)
from src.utils.logger import logger


async def handle_exception(
    request: Request,
    exc: Exception,
    status_code: int,
    message: str,
):
    """
    Generic exception handler that logs the exception and returns a JSON response.

    Args:
        request: FastAPI Request object.
        exc: The exception instance.
        status_code: HTTP status code to return.
        message: Custom message
    """
    logger.error(
        action=EventAction.NOTIFY,
        outcome=EventOutcome.FAILURE,
        category=EventCategory.API,
        message=f"Unhandled Exception: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=status_code,
        content={"detail": message},
    )


# Map exception classes to status codes and optional custom messages
EXCEPTION_MAP = {
    # DMS Specific
    FileInvalidFileExtensionError: (
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "Unsupported file extension",
    ),
    FileInvalidFileTypeError: (
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "Unsupported file type",
    ),
    FileExistsError: (
        status.HTTP_409_CONFLICT,
        "File already exists",
    ),
    FileNotFoundError: (
        status.HTTP_404_NOT_FOUND,
        "File not found",
    ),
    WorkflowRequiresApprovalError: (
        status.HTTP_409_CONFLICT,
        "Another file upload requires approval",
    ),
    WorkflowInRunningStateError: (
        status.HTTP_409_CONFLICT,
        "Another file upload is running",
    ),
    WorkflowInPendingStateError: (
        status.HTTP_409_CONFLICT,
        "Another file upload is already in pending state",
    ),
    WorkflowAlreadyApprovedError: (
        status.HTTP_409_CONFLICT,
        "File upload already approved",
    ),
    WorkflowAlreadyRejectedError: (
        status.HTTP_409_CONFLICT,
        "File upload already rejected",
    ),
    WorkflowIncorrectStatusError: (
        status.HTTP_409_CONFLICT,
        "File upload does not require approval",
    ),
    WorkflowNotFoundError: (
        status.HTTP_404_NOT_FOUND,
        "Workflow not found",
    ),
    WorkflowValidateDiffError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Diff input validation failed",
    ),
    # Postgres
    ForeignKeyViolationError: (
        status.HTTP_400_BAD_REQUEST,
        "Foreign Key Violation Error",
    ),
    PostgresError: (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Internal DB Error",
    ),
    # SQLAlchemy
    SQLAlchemyError: (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Internal Database Error",
    ),
    # FastAPI
    FastAPIError: (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Internal FastAPI Error",
    ),
    RequestValidationError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Invalid request payload",
    ),
    # Python generic
    Exception: (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Internal Server Error",
    ),
}


def make_handler(status_code: int, message: str):
    """
    Factory function that creates an async exception handler for FastAPI.

    Args:
        status_code (int): The HTTP status code to return in the response.
        message (str): Custom error message to include in the
            response. If None, the exception's string representation is used.

    Returns:
        Callable[[Request, Exception], Awaitable[JSONResponse]]:
            An async handler function that can be registered with FastAPI via
            `app.add_exception_handler`.
    """

    async def handler(request: Request, exc: Exception):
        return await handle_exception(
            request=request,
            exc=exc,
            status_code=status_code,
            message=message,
        )

    return handler


def register_exception_handlers(app: FastAPI):
    """
    Registers all application-wide exception handlers defined in `EXCEPTION_MAP`.

    Each exception type is mapped to a corresponding HTTP status code and an
    optional custom error message. When an exception occurs, the generated handler
    will log the exception and return a structured JSON response.

    Args:
        app (FastAPI): The FastAPI application instance where handlers should be
            registered.

    Example:
        >>> app = FastAPI()
        >>> register_exception_handlers(app)
    """
    for exc_class, (status_code, message) in EXCEPTION_MAP.items():
        app.add_exception_handler(exc_class, make_handler(status_code, message))
