from datetime import datetime, timezone
from typing import Any


def generate_timestamp() -> str:
    """Generate ISO 8601 timestamp in UTC with milliseconds."""
    return (
        datetime.now(tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )




_ECS_FIELD_MAPPING: dict[str, str] = {
    "error_message": "error.message",
    "process_id": "process.id",
    "trace_id": "trace.id",
    "event_type": "event.type",
    "event_code": "event.code",
    "event_reason": "event.reason",
    "event_duration": "event.duration",
    "event_hash": "event.hash",
    "event_ingested": "event.ingested",
    "http_request_method": "http.request.method",
    "url_path": "url.path",
    "user_type": "user.type",
    "user_id": "user.id",
    "user_hash": "user.hash",
    "user_roles": "user.roles",
    "source_ip": "source.ip",
    "source_port": "source.port",
    "destination_ip": "destination.ip",
    "destination_port": "destination.port",
    "session_id": "session.id",
    "session_token_hash": "session.token_hash",
    "session_expiry": "session.expiry",
    "file_id": "file.id",
    "file_source": "file.source",
    "file_path": "file.path",
    "file_name": "file.name",
    "file_size": "file.size",
    "file_hash_sha256": "file.hash.sha256",
    "database_operation": "database.operation",
    "database_query": "database.query",
    "database_rows_affected": "database.rows_affected",
    "ai_model_name": "ai.model.name",
    "ai_model_version": "ai.model.version",
    "ai_decision_process": "ai.decision.process",
    "ai_decision_output": "ai.decision.output",
    "ai_decision_human_override": "ai.decision.human_override",
    "ai_data_sources": "ai.data.sources",
    "project_id": "project_id",
    "labels_debug": "labels.debug",
    "labels_redacted": "labels.redacted",
}


def map_ecs_context(context: dict[str, Any]) -> dict[str, Any]:
    """Map Python kwargs to ECS field names."""
    mapped: dict[str, Any] = {}
    for kwarg_key, ecs_key in _ECS_FIELD_MAPPING.items():
        if kwarg_key in context and context[kwarg_key] is not None:
            val = context[kwarg_key]
            # Handle Enum values
            if hasattr(val, "value"):
                val = val.value
            mapped[ecs_key] = val
    return mapped
