from __future__ import annotations

import sys
from typing import Any
from typing_extensions import Unpack

from pydantic import BaseModel, Field

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventKind,
    EventOutcome,
    LogEventAuth,
    LogEventDefault,
    LogEventLegal,
    LogEventSystem,
    LogLevel,
    ServiceComponent,
)
from event_logging.context import project_id_var, trace_id_var
from event_logging.formatters import LogFormatter, JsonFormatter, PrettyFormatter
from event_logging.settings import LoggingSettings
from event_logging.types import LogContext
from event_logging.utils import generate_timestamp, map_ecs_context


class EventLogger(BaseModel):
    """Emit ECS-style JSON log entries to stdout."""

    model_config = {"arbitrary_types_allowed": True}

    service_name: str
    service_component: ServiceComponent | None = None
    default_context: dict[str, Any] = Field(default_factory=dict)
    settings: LoggingSettings = Field(default_factory=LoggingSettings)
    stream: Any = Field(default=sys.stdout)
    formatter: LogFormatter | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.formatter is None:
            if self.settings.pretty_print:
                object.__setattr__(self, "formatter", PrettyFormatter())
            else:
                object.__setattr__(self, "formatter", JsonFormatter())

    def log_event(
        self,
        *,
        level: LogLevel,
        action: str | EventAction,
        outcome: str | EventOutcome,
        category: str | EventCategory,
        default_event: LogEventDefault | None = None,
        system_event: LogEventSystem | None = None,
        auth_event: LogEventAuth | None = None,
        legal_event: LogEventLegal | None = None,
        event_kind: EventKind = EventKind.EVENT,
        message: str | None = None,
        **kwargs: Unpack[LogContext],
    ) -> dict[str, Any]:
        """Build and emit an event log."""
        # Check if at least one event is set, otherwise default to General
        if not any([legal_event, auth_event, system_event, default_event]):
            default_event = LogEventDefault.GENERAL

        # Handle serialization (supports str or Enum)
        action_value = action.value if hasattr(action, "value") else action
        outcome_value = outcome.value if hasattr(outcome, "value") else outcome
        category_value = category.value if hasattr(category, "value") else category

        # Basic fields
        payload: dict[str, Any] = {
            "ecs.version": self.settings.ecs_version,
            "@timestamp": generate_timestamp(),
            "event.action": action_value,
            "event.outcome": outcome_value,
            "event.kind": event_kind.value,
            "event.category": category_value,
            "log.level": level.value,
            "service.name": self.service_name,
            "event.default": default_event.value if default_event else None,
            "event.system": system_event.value if system_event else None,
            "event.auth": auth_event.value if auth_event else None,
            "event.legal": legal_event.value if legal_event else None,
            "message": message,
        }

        # Service component (default or override)
        comp = kwargs.get("service_component") or self.service_component
        if comp:
            payload["service.component"] = (
                comp.value if hasattr(comp, "value") else comp
            )

        # Remove None values from payload
        payload = {k: v for k, v in payload.items() if v is not None}

        # Mapping of kwargs to ECS fields
        payload.update(map_ecs_context(kwargs))

        # Auto-attach project_id from context if not explicitly provided
        if "project_id" not in payload:
            ctx_project_id = project_id_var.get()
            if ctx_project_id is not None:
                payload["project_id"] = ctx_project_id

        # Auto-attach trace_id from context if not explicitly provided
        if "trace.id" not in payload:
            ctx_trace_id = trace_id_var.get()
            if ctx_trace_id is not None:
                payload["trace.id"] = ctx_trace_id

        merged_payload = {**self.default_context, **payload}

        serialized = self.formatter.format(merged_payload)
        self.stream.write(serialized + "\n")
        return merged_payload

    def info(
        self,
        action: str | EventAction,
        outcome: str | EventOutcome,
        category: str | EventCategory,
        default_event: LogEventDefault | None = None,
        system_event: LogEventSystem | None = None,
        auth_event: LogEventAuth | None = None,
        legal_event: LogEventLegal | None = None,
        event_kind: EventKind = EventKind.EVENT,
        message: str | None = None,
        **kwargs: Unpack[LogContext],
    ) -> dict[str, Any]:
        """Log an event with INFO level."""
        return self.log_event(
            level=LogLevel.INFO,
            action=action,
            outcome=outcome,
            category=category,
            default_event=default_event,
            system_event=system_event,
            auth_event=auth_event,
            legal_event=legal_event,
            event_kind=event_kind,
            message=message,
            **kwargs,
        )

    def warn(
        self,
        action: str | EventAction,
        outcome: str | EventOutcome,
        category: str | EventCategory,
        default_event: LogEventDefault | None = None,
        system_event: LogEventSystem | None = None,
        auth_event: LogEventAuth | None = None,
        legal_event: LogEventLegal | None = None,
        event_kind: EventKind = EventKind.EVENT,
        message: str | None = None,
        **kwargs: Unpack[LogContext],
    ) -> dict[str, Any]:
        """Log an event with WARN level."""
        return self.log_event(
            level=LogLevel.WARN,
            action=action,
            outcome=outcome,
            category=category,
            default_event=default_event,
            system_event=system_event,
            auth_event=auth_event,
            legal_event=legal_event,
            event_kind=event_kind,
            message=message,
            **kwargs,
        )

    def error(
        self,
        action: str | EventAction,
        outcome: str | EventOutcome,
        category: str | EventCategory,
        default_event: LogEventDefault | None = None,
        system_event: LogEventSystem | None = None,
        auth_event: LogEventAuth | None = None,
        legal_event: LogEventLegal | None = None,
        event_kind: EventKind = EventKind.EVENT,
        message: str | None = None,
        **kwargs: Unpack[LogContext],
    ) -> dict[str, Any]:
        """Log an event with ERROR level."""
        return self.log_event(
            level=LogLevel.ERROR,
            action=action,
            outcome=outcome,
            category=category,
            default_event=default_event,
            system_event=system_event,
            auth_event=auth_event,
            legal_event=legal_event,
            event_kind=event_kind,
            message=message,
            **kwargs,
        )

    def debug(
        self,
        action: str | EventAction,
        outcome: str | EventOutcome,
        category: str | EventCategory,
        default_event: LogEventDefault | None = None,
        system_event: LogEventSystem | None = None,
        auth_event: LogEventAuth | None = None,
        legal_event: LogEventLegal | None = None,
        event_kind: EventKind = EventKind.EVENT,
        message: str | None = None,
        **kwargs: Unpack[LogContext],
    ) -> dict[str, Any]:
        """Log an event with DEBUG level."""
        return self.log_event(
            level=LogLevel.DEBUG,
            action=action,
            outcome=outcome,
            category=category,
            default_event=default_event,
            system_event=system_event,
            auth_event=auth_event,
            legal_event=legal_event,
            event_kind=event_kind,
            message=message,
            **kwargs,
        )

    def fatal(
        self,
        action: str | EventAction,
        outcome: str | EventOutcome,
        category: str | EventCategory,
        default_event: LogEventDefault | None = None,
        system_event: LogEventSystem | None = None,
        auth_event: LogEventAuth | None = None,
        legal_event: LogEventLegal | None = None,
        event_kind: EventKind = EventKind.EVENT,
        message: str | None = None,
        **kwargs: Unpack[LogContext],
    ) -> dict[str, Any]:
        """Log an event with FATAL level."""
        return self.log_event(
            level=LogLevel.FATAL,
            action=action,
            outcome=outcome,
            category=category,
            default_event=default_event,
            system_event=system_event,
            auth_event=auth_event,
            legal_event=legal_event,
            event_kind=event_kind,
            message=message,
            **kwargs,
        )
