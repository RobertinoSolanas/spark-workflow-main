from contextvars import ContextVar

project_id_var: ContextVar[str | None] = ContextVar("project_id", default=None)
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
