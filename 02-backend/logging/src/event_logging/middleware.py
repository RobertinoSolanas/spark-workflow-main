import time
from typing import Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match
from starlette.types import ASGIApp
from collections.abc import Mapping

from event_logging.context import project_id_var, trace_id_var
from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
    ServiceComponent,
)
from event_logging.event_logger import EventLogger


class EventLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for event ECS logging of HTTP requests.

    Logs request/response details including duration, status,
    and network details in ECS-compatible JSON format.
    """

    METHOD_ACTION_MAP = {
        "GET": EventAction.READ,
        "POST": EventAction.WRITE,
        "PUT": EventAction.CHANGE,
        "DELETE": EventAction.DELETE,
        "PATCH": EventAction.CHANGE,
        "OPTIONS": EventAction.ACCESS,
        "HEAD": EventAction.ACCESS,
    }

    def __init__(
        self,
        app: ASGIApp,
        service_name: str,
        service_component: str | ServiceComponent | None = None,
        skip_paths: list[str] | None = None,
    ):
        super().__init__(app)

        if isinstance(service_component, str):
            service_component = ServiceComponent(service_component)

        self.logger = EventLogger(
            service_name=service_name, service_component=service_component
        )
        self.skip_paths = skip_paths or ["/healthz", "/metrics"]

    def _get_project_id(self, mapping: Mapping[str, str | None]) -> str | None:
        """Get project_id from dict-like object, supporting snake_case and camelCase."""
        for key in ("project_id", "projectId"):
            if (value := mapping.get(key)) is not None:
                return str(value)
        return None

    def _resolve_path_params(self, request: Request) -> dict[str, str]:
        """Resolve path params by matching the request against the app's routes."""
        for route in request.app.routes:
            match, scope = route.matches(request.scope)
            if match == Match.FULL:
                return scope.get("path_params", {})
        return {}

    async def _extract_project_id(self, request: Request) -> str | None:
        """Extract project_id from path params, query params or body."""
        path_params = self._resolve_path_params(request)
        if project_id := self._get_project_id(path_params):
            return project_id
        if project_id := self._get_project_id(request.query_params):
            return project_id
        try:
            body = await request.json()
            if isinstance(body, dict) and (project_id := self._get_project_id(body)):
                return project_id
        except Exception:
            pass
        return None


    def _extract_trace_id(self, request: Request) -> str | None:
        """Extract trace ID from W3C traceparent header if valid, else return None."""
        traceparent = request.headers.get("traceparent")
        if not traceparent:
            return None
        parts = traceparent.split("-")
        if len(parts) != 4:
            return None
        version, trace_id, parent_id, trace_flags = parts[0], parts[1], parts[2], parts[3]
        if (
            len(version) != 2
            or version == "ff"
            or len(trace_id) != 32
            or trace_id == "0" * 32
            or len(parent_id) != 16
            or parent_id == "0" * 16
            or len(trace_flags) != 2
        ):
            return None
        try:
            int(version, 16)
            int(trace_id, 16)
            int(parent_id, 16)
            int(trace_flags, 16)
        except ValueError:
            return None
        return trace_id

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return await call_next(request)

        project_id = await self._extract_project_id(request)
        project_id_token = project_id_var.set(project_id)

        trace_id = self._extract_trace_id(request) or str(uuid4())
        trace_id_token = trace_id_var.set(trace_id)

        start_time = time.perf_counter()
        outcome = EventOutcome.SUCCESS
        error_message = None
        response = None

        try:
            response = await call_next(request)
            if response.status_code >= 400:
                outcome = EventOutcome.FAILURE
        except Exception as e:
            outcome = EventOutcome.FAILURE
            error_message = str(e)
            raise
        finally:
            duration_ns = int((time.perf_counter() - start_time) * 1_000_000_000)

            action = self.METHOD_ACTION_MAP.get(request.method, EventAction.ACCESS)

            source_ip = request.client.host if request.client else None
            destination_ip = None
            if request.scope.get("server"):
                destination_ip = request.scope["server"][0]

            self.logger.info(
                action=action,
                outcome=outcome,
                category=EventCategory.API,
                default_event=LogEventDefault.API_REQUEST,
                message=f"{request.method} {response.status_code if response else ''}: {request.url.path} {request.url.query if request.url.query else ''}  executed.",
                event_duration=duration_ns,
                event_code=response.status_code if response else None,
                url_path=request.url.path,
                http_request_method=request.method,
                source_ip=source_ip,
                destination_ip=destination_ip,
                error_message=error_message,
                project_id=project_id,
                trace_id=trace_id,
            )

            project_id_var.reset(project_id_token)
            trace_id_var.reset(trace_id_token)

        return response
