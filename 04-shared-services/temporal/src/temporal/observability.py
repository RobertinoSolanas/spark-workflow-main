from __future__ import annotations

import atexit
import logging
import socket
from collections.abc import Callable, Sequence
from enum import Enum
from functools import wraps
from typing import override

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator
from pydantic import BaseModel, Field
from temporalio import activity, workflow
from temporalio.contrib.opentelemetry._id_generator import TemporalIdGenerator

from temporal.auto_trace import enable_auto_tracing
from temporal.custom_otel_plugin import CustomTracerProvider

_provider: CustomTracerProvider | None = None
_log_provider: LoggerProvider | None = None
_MIN_EXPORTED_SPAN_DURATION_NS = 1_000_000  # 1 ms
_TRACER_SCOPE = "temporal.observability"


class TracingMode(str, Enum):
    MINIMAL = "minimal"
    FULL = "full"


class ObservabilityConfig(BaseModel):
    service_name: str = Field(min_length=1)
    otel_endpoint: str = Field(min_length=1)
    tracing_mode: TracingMode = TracingMode.FULL


def setup_observability(config: ObservabilityConfig):
    """Initialize OpenTelemetry tracing and log export via OTLP."""
    global _provider, _log_provider

    if _provider is not None:
        return

    service_name = config.service_name
    otel_config = {
        "endpoint": config.otel_endpoint,
        "insecure": config.otel_endpoint.startswith(("http://", "grpc://")),
    }

    resource = Resource(
        attributes={
            SERVICE_NAME: service_name,
            "worker.id": socket.gethostname(),
            "temporal": "true",
        }
    )

    # --- Traces ---
    id_generator = TemporalIdGenerator(RandomIdGenerator())
    tracer_provider = TracerProvider(
        resource=resource,
        id_generator=id_generator,
    )
    tracer_provider.add_span_processor(TemporalContextSpanProcessor())

    span_exporter = MinDurationSpanExporter(
        OTLPSpanExporter(**otel_config),
        min_duration_ns=_MIN_EXPORTED_SPAN_DURATION_NS,
    )

    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))

    _provider = CustomTracerProvider(tracer_provider, id_generator)
    trace.set_tracer_provider(_provider)

    # --- Logs (OTLP) ---
    # Only export logs via OTLP locally (no OTel Agent to scrape stdout).
    # In K8s the Agent DaemonSet scrapes stdout and forwards to Loki.
    is_local = "localhost" in config.otel_endpoint
    if is_local:
        _log_provider = LoggerProvider(resource=resource)
        _log_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(**otel_config)))
        set_logger_provider(_log_provider)

        otel_log_handler = LoggingHandler(level=logging.DEBUG, logger_provider=_log_provider)

        root_logger = logging.getLogger()
        root_logger.addHandler(otel_log_handler)

    atexit.register(shutdown_observability)

    logging.getLogger(__name__).info(
        "Observability initialized",
        extra={"otlp_endpoint": config.otel_endpoint},
    )

    if config.tracing_mode == TracingMode.FULL:
        enable_auto_tracing()


class TemporalContextSpanProcessor(SpanProcessor):
    """Tags spans with temporal.context (workflow/activity)."""

    @override
    def on_start(self, span, parent_context=None):
        import temporalio.activity
        import temporalio.workflow

        if span.attributes and span.attributes.get("temporal.context"):
            return

        if temporalio.activity.in_activity():
            span.set_attribute("temporal.context", "activity")
        elif temporalio.workflow.in_workflow():
            span.set_attribute("temporal.context", "workflow")

    @override
    def on_end(self, span):
        pass

    @override
    def shutdown(self):
        pass

    @override
    def force_flush(self, timeout_millis=None):
        return True


class MinDurationSpanExporter(SpanExporter):
    """Drops spans shorter than the configured minimum duration."""

    def __init__(self, inner: SpanExporter, min_duration_ns: int) -> None:
        self._inner = inner
        self._min_duration_ns = min_duration_ns

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        spans_to_export: list[ReadableSpan] = []
        for span in spans:
            start_time = span.start_time
            end_time = span.end_time
            if start_time is None or end_time is None:
                continue
            if (end_time - start_time) >= self._min_duration_ns:
                spans_to_export.append(span)
        if not spans_to_export:
            return SpanExportResult.SUCCESS
        return self._inner.export(spans_to_export)

    @override
    def shutdown(self) -> None:
        self._inner.shutdown()

    @override
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis=timeout_millis)


def shutdown_observability() -> None:
    """Flush and shutdown the tracer and log providers."""
    global _provider, _log_provider
    if _log_provider is not None:
        _log_provider.force_flush()
        _log_provider.shutdown()
        _log_provider = None
    if _provider is not None:
        _provider.force_flush()
        _provider.shutdown()
        _provider = None
    logging.getLogger(__name__).debug("Observability shutdown complete")


def _temporal_span_attributes() -> dict[str, str]:
    attributes: dict[str, str] = {}
    if activity.in_activity():
        info = activity.info()
        attributes["temporalActivityID"] = info.activity_id
        if info.workflow_id:
            attributes["temporalWorkflowID"] = info.workflow_id
        if info.workflow_run_id:
            attributes["temporalRunID"] = info.workflow_run_id
    elif workflow.in_workflow():
        info = workflow.info()
        attributes["temporalWorkflowID"] = info.workflow_id
        attributes["temporalRunID"] = info.run_id
    return attributes


def _in_temporal_context() -> bool:
    return activity.in_activity() or workflow.in_workflow()


def traced[T, **P](func: Callable[P, T]) -> Callable[P, T]:
    if getattr(func, "__traced__", False):
        return func

    tracer = trace.get_tracer(_TRACER_SCOPE)

    @wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        if not _in_temporal_context():
            return await func(*args, **kwargs)  # type: ignore[misc]
        with tracer.start_as_current_span(
            func.__qualname__, attributes=_temporal_span_attributes()
        ):
            return await func(*args, **kwargs)  # type: ignore[misc]

    @wraps(func)
    async def async_gen_wrapper(*args: P.args, **kwargs: P.kwargs):  # type: ignore[misc]
        if not _in_temporal_context():
            async for item in func(*args, **kwargs):  # type: ignore[misc]
                yield item
            return
        with tracer.start_as_current_span(
            func.__qualname__, attributes=_temporal_span_attributes()
        ):
            async for item in func(*args, **kwargs):  # type: ignore[misc]
                yield item

    @wraps(func)
    def gen_wrapper(*args: P.args, **kwargs: P.kwargs):  # type: ignore[misc]
        if not _in_temporal_context():
            yield from func(*args, **kwargs)  # type: ignore[misc]
            return
        with tracer.start_as_current_span(
            func.__qualname__, attributes=_temporal_span_attributes()
        ):
            yield from func(*args, **kwargs)  # type: ignore[misc]

    @wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        if not _in_temporal_context():
            return func(*args, **kwargs)
        with tracer.start_as_current_span(
            func.__qualname__, attributes=_temporal_span_attributes()
        ):
            return func(*args, **kwargs)

    import asyncio
    import inspect

    if inspect.isasyncgenfunction(func):
        wrapper = async_gen_wrapper
    elif asyncio.iscoroutinefunction(func):
        wrapper = async_wrapper
    elif inspect.isgeneratorfunction(func):
        wrapper = gen_wrapper
    else:
        wrapper = sync_wrapper
    wrapper.__traced__ = True  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]
