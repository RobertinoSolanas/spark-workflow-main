import traceback

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.exceptions.exceptions import NotFoundError, OperationFailedError
from src.utils.logger import logger


def _detail_from_exception(exc: Exception, fallback: str) -> str:
    """Extract a clean error message from an exception or return a fallback."""
    message = str(exc).strip()
    return message if message else fallback


def _log_and_respond(
    request: Request,
    exc: Exception,
    *,
    log_level: str,
    action: EventAction,
    category: EventCategory,
    default_event: LogEventDefault,
    status_code: int,
    fallback: str,
) -> JSONResponse:
    log_fn = logger.warn if log_level == "warn" else logger.error
    log_fn(
        action=action,
        outcome=EventOutcome.FAILURE,
        category=category,
        default_event=default_event,
        message=f"{type(exc).__name__} on {request.url.path}: {exc}",
    )
    return JSONResponse(
        status_code=status_code,
        content={"detail": _detail_from_exception(exc, fallback)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register global exception handlers so routes can stay lean.
    """

    @app.exception_handler(NotFoundError)
    async def handle_not_found_error(request: Request, exc: NotFoundError):
        return _log_and_respond(
            request, exc,
            log_level="warn", action=EventAction.READ, category=EventCategory.API,
            default_event=LogEventDefault.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND, fallback="Resource not found",
        )

    @app.exception_handler(FileNotFoundError)
    async def handle_file_not_found_error(request: Request, exc: FileNotFoundError):
        return _log_and_respond(
            request, exc,
            log_level="warn", action=EventAction.READ, category=EventCategory.FILE,
            default_event=LogEventDefault.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND, fallback="File not found",
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError):
        return _log_and_respond(
            request, exc,
            log_level="warn", action=EventAction.VALIDATE, category=EventCategory.API,
            default_event=LogEventDefault.VALIDATION_FAILURE,
            status_code=status.HTTP_409_CONFLICT, fallback="Conflict during request",
        )

    @app.exception_handler(OperationFailedError)
    async def handle_operation_failed_error(
        request: Request, exc: OperationFailedError
    ):
        return _log_and_respond(
            request, exc,
            log_level="error", action=EventAction.ACCESS, category=EventCategory.API,
            default_event=LogEventDefault.GENERAL,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, fallback="Operation failed unexpectedly",
        )

    @app.exception_handler(Exception)
    async def handle_generic_exception(request: Request, exc: Exception):
        logger.error(
            action=EventAction.ACCESS,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventDefault.GENERAL,
            message=f"Unhandled exception on {request.url.path}",
            error_message=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )
