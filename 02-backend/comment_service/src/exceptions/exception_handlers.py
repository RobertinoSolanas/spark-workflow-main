"""Global exception handlers for the application."""

import traceback

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from src.exceptions.exceptions import NotFoundError, OperationFailedError
from src.utils.logger import logger


def _detail_from_exception(exc: Exception, fallback: str = "An error occurred") -> str:
    """Extract a clean error message from an exception or return a fallback."""
    message = str(exc).strip()
    return message if message else fallback


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers so routes can stay lean."""

    @app.exception_handler(NotFoundError)
    async def handle_not_found_error(request: Request, exc: NotFoundError):
        logger.warn(
            action=EventAction.READ,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventDefault.RESOURCE_NOT_FOUND,
            message=f"NotFoundError on {request.url.path}: {exc}",
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": _detail_from_exception(exc, "Resource not found")},
        )

    @app.exception_handler(FileNotFoundError)
    async def handle_file_not_found_error(request: Request, exc: FileNotFoundError):
        logger.warn(
            action=EventAction.READ,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.FILE,
            default_event=LogEventDefault.RESOURCE_NOT_FOUND,
            message=f"FileNotFoundError on {request.url.path}: {exc}",
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": _detail_from_exception(exc, "File not found")},
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError):
        logger.error(
            action=EventAction.WRITE,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.DATABASE,
            default_event=LogEventDefault.DB_ERROR,
            message=f"IntegrityError on {request.url.path}: {exc}",
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": _detail_from_exception(
                    exc, "Resource conflict during database operation"
                )
            },
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError):
        logger.warn(
            action=EventAction.VALIDATE,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventDefault.VALIDATION_FAILURE,
            message=f"ValueError on {request.url.path}: {exc}",
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": _detail_from_exception(exc, "Bad request")},
        )

    @app.exception_handler(OperationFailedError)
    async def handle_operation_failed_error(
        request: Request, exc: OperationFailedError
    ):
        logger.error(
            action=EventAction.ACCESS,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventDefault.GENERAL,
            message=f"OperationFailedError on {request.url.path}: {exc}",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": _detail_from_exception(exc, "Operation failed unexpectedly")
            },
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
