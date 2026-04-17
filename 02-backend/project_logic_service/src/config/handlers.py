from event_logging.enums import (  # type: ignore[import-not-found]
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventAuth,
    LogEventDefault,
)
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.exceptions import (
    DeadlineNotFoundError,
    DuplicateProjectTypeError,
    FastAPIError,
    ForeignKeyViolationError,
    InvalidStatusError,
    PostgresError,
    ProcessStepNotFoundError,
    ProjectNotFoundError,
    ProjectTypeNotFoundError,
    RequestValidationError,
    SQLAlchemyError,
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
    # Classify the exception for logging
    action = EventAction.ACCESS
    category = EventCategory.API
    default_event = LogEventDefault.GENERAL
    auth_event: LogEventAuth | None = None
    log_method = logger.error

    if isinstance(
        exc,
        (
            DeadlineNotFoundError,
            ProjectNotFoundError,
            ProjectTypeNotFoundError,
            ProcessStepNotFoundError,
            FileNotFoundError,
        ),
    ):
        action = EventAction.READ
        category = (
            EventCategory.FILE
            if isinstance(exc, FileNotFoundError)
            else EventCategory.API
        )
        default_event = LogEventDefault.RESOURCE_NOT_FOUND
        log_method = logger.warn
    elif isinstance(exc, (DuplicateProjectTypeError, InvalidStatusError, RequestValidationError, FastAPIError)):
        action = EventAction.VALIDATE
        category = EventCategory.API
        default_event = LogEventDefault.VALIDATION_FAILURE
        log_method = logger.warn
    elif isinstance(
        exc,
        (
            ForeignKeyViolationError,
            PostgresError,
            SQLAlchemyError,
        ),
    ):
        action = EventAction.WRITE
        category = EventCategory.DATABASE
        default_event = LogEventDefault.DB_ERROR
        log_method = logger.error

    log_method(
        action=action,
        outcome=EventOutcome.FAILURE,
        category=category,
        default_event=default_event,
        auth_event=auth_event,
        message=f"{exc.__class__.__name__} on {request.url.path}: {message}",
    )

    return JSONResponse(
        status_code=status_code,
        content={"detail": message},
    )


# Map exception classes to status codes and optional custom messages
EXCEPTION_MAP = {
    # Domain exceptions (from src.exceptions)
    DeadlineNotFoundError: (
        status.HTTP_404_NOT_FOUND,
        "Deadline not found",
    ),
    ProjectNotFoundError: (
        status.HTTP_404_NOT_FOUND,
        "Project not found",
    ),
    ProjectTypeNotFoundError: (
        status.HTTP_404_NOT_FOUND,
        "ProjectType not found",
    ),
    ProcessStepNotFoundError: (
        status.HTTP_404_NOT_FOUND,
        "ProcessStep not found",
    ),
    DuplicateProjectTypeError: (
        status.HTTP_409_CONFLICT,
        "ProjectType with this name already exists",
    ),
    InvalidStatusError: (
        status.HTTP_400_BAD_REQUEST,
        "Invalid project status",
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
    FileNotFoundError: (
        status.HTTP_404_NOT_FOUND,
        "File Not Found Error",
    ),
    Exception: (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Internal Server Error",
    ),
}


def make_handler(status_code: int, message: str | None):
    """
    Factory function that creates an async exception handler for FastAPI.

    Args:
        status_code (int): The HTTP status code to return in the response.
        message (str | None): Optional custom error message to include in the
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
