import time
from typing import Any

from event_logging.enums import (
    DatabaseOperation,
    EventAction,
    EventCategory,
    EventOutcome,
    EventType,
    LogEventDefault,
)
from event_logging.event_logger import EventLogger


def _extract_sqlstate(exception: BaseException) -> str | None:
    for attr in ("pgcode", "sqlstate"):
        if code := getattr(exception, attr, None):
            return str(code)
    return None


def setup_db_logging(engine: Any, service_name: str) -> None:
    """
    Attaches automatic event logging listeners to a SQLAlchemy engine.

    Args:
        engine: The SQLAlchemy Engine or AsyncEngine to attach to.
        service_name: The name of the service (e.g., 'backend', 'auth-service').
    """
    try:
        from sqlalchemy import event
        from sqlalchemy.orm import Session
    except ImportError:
        raise ImportError(
            "sqlalchemy is required for setup_db_logging. "
            "Install with: pip install event-logging[db]"
        )

    logger = EventLogger(service_name=service_name)

    # Unwrap AsyncEngine to get the SyncEngine if necessary
    sync_engine = engine.sync_engine if hasattr(engine, "sync_engine") else engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        context._query_start_time = time.perf_counter()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def log_db_query(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        # 1. Duration
        start_time = getattr(context, "_query_start_time", None)
        duration_ns = (
            int((time.perf_counter() - start_time) * 1_000_000_000) if start_time else 0
        )

        # 2. Operation & Action
        statement_upper = statement.strip().upper()
        operation = None
        action = EventAction.READ
        event_type = EventType.ACCESS

        if statement_upper.startswith("INSERT"):
            operation = DatabaseOperation.INSERT
            action = EventAction.WRITE
            event_type = EventType.CHANGE
        elif statement_upper.startswith("UPDATE"):
            operation = DatabaseOperation.UPDATE
            action = EventAction.CHANGE
            event_type = EventType.CHANGE
        elif statement_upper.startswith("DELETE"):
            operation = DatabaseOperation.DELETE
            action = EventAction.DELETE
            event_type = EventType.CHANGE
        elif statement_upper.startswith("CREATE"):
            operation = DatabaseOperation.CREATE
            action = EventAction.WRITE
            event_type = EventType.CHANGE

        # 3. Rows Affected
        rows_affected = context.rowcount if hasattr(context, "rowcount") else 0

        # Map to specific DB event
        db_event = LogEventDefault.DB_READ
        if action == EventAction.WRITE:
            db_event = LogEventDefault.DB_WRITE
        elif action == EventAction.CHANGE:
            db_event = LogEventDefault.DB_WRITE
        elif action == EventAction.DELETE:
            db_event = LogEventDefault.DB_WRITE

        logger.info(
            action=action,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.DATABASE,
            default_event=db_event,
            event_type=event_type,
            message=f"DB Query: {operation.value if operation else 'EXECUTE'}",
            database_operation=operation,
            database_query=statement,
            database_rows_affected=rows_affected,
            event_duration=duration_ns,
        )

    @event.listens_for(sync_engine, "handle_error")
    def log_db_error(exception_context: Any) -> None:
        execution_context = getattr(exception_context, "execution_context", None)
        start_time = (
            getattr(execution_context, "_query_start_time", None)
            if execution_context is not None
            else None
        )
        duration_ns = (
            int((time.perf_counter() - start_time) * 1_000_000_000) if start_time else 0
        )

        sqlstate = _extract_sqlstate(exception_context.original_exception)

        logger.error(
            action=EventAction.CHANGE,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.DATABASE,
            default_event=LogEventDefault.DB_ERROR,
            message="Database operation failed",
            error_message=str(exception_context.original_exception),
            event_code=sqlstate,
            database_query=exception_context.statement,
            event_duration=duration_ns,
        )
    
    @event.listens_for(Session, "after_commit")
    def log_commit(_: Session) -> None:
        logger.info(
            action=EventAction.CHANGE,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.DATABASE,
            default_event=LogEventDefault.DB_COMMIT,
            message="Transaction committed",
        )

    @event.listens_for(Session, "after_rollback")
    def log_rollback(_: Session) -> None:
        logger.warn(
            action=EventAction.CHANGE,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.DATABASE,
            default_event=LogEventDefault.DB_ROLLBACK,
            message="Transaction rolled back",
        )
