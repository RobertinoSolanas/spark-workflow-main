"""
Custom OTel plugin for Temporal workflows.

WorkflowAwareTracerProvider replaces ReplaySafeTracerProvider:
- Uses workflow.time_ns() for span timestamps (correct even during replay)
- Always exports spans (no replay skip) so @traced parent chains survive restarts
- Emits a Downtime child span only for spans that remain open until replay catches up
- TemporalIdGenerator ensures replayed spans deduplicate by span_id

The plugin also adds WorkflowStarted and Replay marker spans.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from typing import override

import temporalio.workflow
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, use_span
from opentelemetry.util import types
from opentelemetry.util._decorator import _agnosticcontextmanager
from temporalio.contrib.opentelemetry import OpenTelemetryPlugin
from temporalio.contrib.opentelemetry._otel_interceptor import (
    OpenTelemetryInterceptor,
    _context_to_headers,
    _headers_to_context,
    _TracingWorkflowInboundInterceptor,
    _TracingWorkflowOutboundInterceptor,
)
from temporalio.contrib.opentelemetry._tracer_provider import (
    ReplaySafeTracerProvider,
    _ReplaySafeSpan,
    _ReplaySafeTracer,
)
from temporalio.exceptions import ApplicationError, ApplicationErrorCategory
from temporalio.worker import (
    WorkflowInboundInterceptor,
    WorkflowOutboundInterceptor,
)

_DOWNTIME_GAP_NS = 1_000_000_000  # 1 second


def _detach_if_current(token, expected_context: otel_context.Context) -> None:
    if expected_context is otel_context.get_current():
        otel_context.detach(token)


class _AlwaysExportSpan(_ReplaySafeSpan):
    """Like _ReplaySafeSpan but end() always exports (no replay skip)."""

    @override
    def end(self, end_time: int | None = None) -> None:
        self._span.end(end_time=end_time)


class _DowntimeAwareTracer(_ReplaySafeTracer):
    """
    Emits Downtime markers for when a workflow/activity got assigned to a worker
    and it crashes and time is spent doing nothing. These markers are only indicators
    and are not an absolute measurement of real downtime
    """

    @override
    def start_span(self, *args, **kwargs) -> Span:
        span = self._tracer.start_span(*args, **kwargs)
        return _AlwaysExportSpan(span)

    @override
    @_agnosticcontextmanager
    def start_as_current_span(
        self,
        name,
        # Defaults from _ReplaySafeTracer
        context=None,
        kind=SpanKind.INTERNAL,
        attributes=None,
        links=None,
        start_time=None,
        record_exception=True,
        set_status_on_exception=True,
        end_on_exit=True,
    ) -> Iterator[Span]:
        wf_time = None
        if temporalio.workflow.in_workflow():
            wf_time = temporalio.workflow.time_ns()
            start_time = start_time or wf_time
        span = self._tracer.start_span(
            name,
            context,
            kind,
            attributes,
            links,
            start_time,
            record_exception,
            set_status_on_exception,
        )
        span = _AlwaysExportSpan(span)
        with use_span(
            span,
            end_on_exit=end_on_exit,
            record_exception=record_exception,
            set_status_on_exception=set_status_on_exception,
        ) as s:
            if (
                wf_time is not None
                and temporalio.workflow.unsafe.is_replaying_history_events()
            ):
                wall_ns = time.time_ns()
                if wall_ns - wf_time > _DOWNTIME_GAP_NS:
                    span_ctx = otel_context.get_current()
                    downtime_start_ns = wf_time

                    async def _emit_downtime_if_still_open():
                        try:
                            await temporalio.workflow.wait_condition(
                                lambda: not temporalio.workflow.unsafe.is_replaying_history_events()
                            )
                        except asyncio.CancelledError:
                            return

                        if not s.is_recording():
                            return

                        replay_end_ns = time.time_ns()
                        dt = self._tracer.start_span(
                            "Downtime",
                            context=span_ctx,
                            start_time=downtime_start_ns,
                            attributes={
                                "temporal.context": "downtime",
                                "temporal.downtime": True,
                            },
                        )
                        dt.end(end_time=replay_end_ns)

                    asyncio.ensure_future(_emit_downtime_if_still_open())
            yield s


class CustomTracerProvider(ReplaySafeTracerProvider):
    @override
    def get_tracer(
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: str | None = None,
        schema_url: str | None = None,
        attributes: types.Attributes | None = None,
    ) -> _DowntimeAwareTracer:
        tracer = self._tracer_provider.get_tracer(
            instrumenting_module_name,
            instrumenting_library_version,
            schema_url,
            attributes,
        )
        return _DowntimeAwareTracer(tracer)


class _FixedParentOutbound(_TracingWorkflowOutboundInterceptor):
    """
    Keep StartActivity:* spans open until the activity handle resolves so retries
    are represented as one end-to-end parent span.
    """

    def _start_activity_with_full_span(
        self,
        name: str,
        input,
        start_call,
    ) -> temporalio.workflow.ActivityHandle:
        if not self._add_temporal_spans:
            input.headers = _context_to_headers(input.headers)
            return start_call(self, input)

        info = temporalio.workflow.info()
        span = trace.get_tracer(__name__).start_span(
            name,
            kind=trace.SpanKind.CLIENT,
            attributes={
                "temporalWorkflowID": info.workflow_id,
                "temporalRunID": info.run_id,
            },
            set_status_on_exception=False,
        )
        span_context = trace.set_span_in_context(span)
        token = otel_context.attach(span_context)
        try:
            input.headers = _context_to_headers(input.headers)
            handle = start_call(self, input)
        except Exception as exc:
            if (
                not isinstance(exc, ApplicationError)
                or exc.category != ApplicationErrorCategory.BENIGN
            ):
                span.set_status(
                    Status(
                        status_code=StatusCode.ERROR,
                        description=f"{type(exc).__name__}: {exc}",
                    )
                )
            span.end()
            raise
        finally:
            _detach_if_current(token, span_context)

        handle.add_done_callback(lambda _: span.end())
        return handle

    @override
    def start_activity(self, input) -> temporalio.workflow.ActivityHandle:
        return self._start_activity_with_full_span(
            f"StartActivity:{input.activity}",
            input,
            WorkflowOutboundInterceptor.start_activity,
        )

    @override
    def start_local_activity(self, input) -> temporalio.workflow.ActivityHandle:
        return self._start_activity_with_full_span(
            f"StartActivity:{input.activity}",
            input,
            WorkflowOutboundInterceptor.start_local_activity,
        )


class _CustomWorkflowInboundInterceptor(_TracingWorkflowInboundInterceptor):
    """
    Instantly exports a WorkflowStarted span since otherwise we will only get the root
    span when the Workflow is done. This way we get a readable name earlier

    Also emits a span for the time spent doing a Replay
    """

    @override
    def init(self, outbound) -> None:
        WorkflowInboundInterceptor.init(
            self, _FixedParentOutbound(outbound, self._add_temporal_spans)
        )

    @override
    async def execute_workflow(self, input):
        header_context = _headers_to_context(input.headers)
        if not self._add_temporal_spans:
            return await super().execute_workflow(input)

        info = temporalio.workflow.info()
        token = otel_context.attach(header_context)
        try:
            # Capture ctx within WorkflowStarted span to get the same deterministic
            # trace_id from earlier executions
            with self._workflow_maybe_span(f"WorkflowStarted:{info.workflow_type}"):
                input.headers = _context_to_headers(input.headers)
                workflow_trace_ctx = otel_context.get_current()
        finally:
            _detach_if_current(token, header_context)

        # Emit a single Replay marker when replay ends so we can detect deadlocks
        if temporalio.workflow.unsafe.is_replaying():
            replay_start_ns = time.time_ns()

            async def _emit_replay_marker():
                try:
                    await temporalio.workflow.wait_condition(
                        lambda: not temporalio.workflow.unsafe.is_replaying()
                    )
                except asyncio.CancelledError:
                    return
                replay_end_ns = time.time_ns()
                tracer = trace.get_tracer(__name__)
                span = tracer.start_span(
                    f"Replay:{info.workflow_type}",
                    context=workflow_trace_ctx,
                    start_time=replay_start_ns,
                    attributes={
                        "temporal.context": "replay",
                        "temporal.replay": True,
                        "temporalWorkflowID": info.workflow_id,
                        "temporalRunID": info.run_id,
                    },
                    kind=trace.SpanKind.INTERNAL,
                )
                span.end(end_time=replay_end_ns)

            asyncio.ensure_future(_emit_replay_marker())


class _CustomOpenTelemetryInterceptor(OpenTelemetryInterceptor):
    @override
    def workflow_interceptor_class(self, input):
        class InterceptorWithState(_CustomWorkflowInboundInterceptor):
            _add_temporal_spans = self._add_temporal_spans

        return InterceptorWithState


class CustomOtelPlugin(OpenTelemetryPlugin):
    @override
    def __init__(self, *, add_temporal_spans=True) -> None:
        super().__init__(add_temporal_spans=add_temporal_spans)
        self.client_interceptors = [_CustomOpenTelemetryInterceptor(add_temporal_spans)]
