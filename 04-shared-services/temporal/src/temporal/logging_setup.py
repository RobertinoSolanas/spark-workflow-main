import logging
from collections.abc import Mapping
from enum import Enum
from typing import Any

from event_logging import EventLogger
from event_logging.enums import EventCategory, EventOutcome
from opentelemetry import trace

_LOGGER_NAMES = (
    "temporal.worker",
    "temporalio.activity",
    "temporalio.worker",
    "temporalio.workflow",
)


class TemporalLogAction(str, Enum):
    LOG = "log"


class EventLoggerHandler(logging.Handler):
    def __init__(self, service_name: str, level: int) -> None:
        super().__init__(level=level)
        self._service_name = service_name

    def emit(self, record: logging.LogRecord) -> None:
        context = self.get_context(record)
        logger = EventLogger(
            service_name=self._service_name,
            default_context=context,
        )

        logger_args = {
            "action": TemporalLogAction.LOG,
            "outcome": EventOutcome.UNKNOWN,
            "category": EventCategory.API,
            "message": record.getMessage(),
        }

        if record.levelno >= logging.ERROR:
            logger.error(**logger_args)
        elif record.levelno >= logging.WARNING:
            logger.warn(**logger_args)
        elif record.levelno >= logging.INFO:
            logger.info(**logger_args)
        else:
            logger.debug(**logger_args)

    def get_context(
        self, record: logging.LogRecord
    ) -> dict[str, Any]:
        temporal_activity = getattr(record, "temporal_activity", None)
        temporal_workflow = getattr(record, "temporal_workflow", None)

        span_ctx = trace.get_current_span().get_span_context()
        otel_trace_id = format(span_ctx.trace_id, "032x") if span_ctx.is_valid else None

        if isinstance(temporal_activity, Mapping):
            return {
                "log.logger": "temporal.activity",
                "temporal.activity": temporal_activity,
                "trace_id": otel_trace_id or temporal_activity.get("workflow_id"),
                "process_id": temporal_activity.get("activity_id"),
            }
        elif isinstance(temporal_workflow, Mapping):
            return {
                "log.logger": "temporal.workflow",
                "temporal.workflow": temporal_workflow,
                "trace_id": otel_trace_id or temporal_workflow.get("workflow_id"),
                "process_id": temporal_workflow.get("run_id"),
            }
        context: dict[str, Any] = {"log.logger": record.name}
        if otel_trace_id:
            context["trace_id"] = otel_trace_id
        return context


def _has_event_logging_handler(logger: logging.Logger) -> bool:
    return any(
        getattr(handler, "_event_logging_handler", False) for handler in logger.handlers
    )


def setup_event_logging(service_name: str, *, level: int = logging.INFO) -> None:
    handler = EventLoggerHandler(service_name, level=level)
    handler._event_logging_handler = True  # type: ignore[attr-defined]

    for logger_name in _LOGGER_NAMES:
        logger = logging.getLogger(logger_name)
        if not _has_event_logging_handler(logger):
            logger.addHandler(handler)
        if logger.level == logging.NOTSET:
            logger.setLevel(level)
