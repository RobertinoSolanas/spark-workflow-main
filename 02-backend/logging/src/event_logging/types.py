from __future__ import annotations

from typing import TypedDict

from event_logging.enums import (
    AiDecisionHumanOverride,
    DatabaseOperation,
    EventType,
    ServiceComponent,
    UserType,
)


class EventHash(TypedDict):
    algo: str
    value: str


class LogContext(TypedDict, total=False):
    """Optional context parameters for event logging."""

    # Basic
    error_message: str | None
    process_id: str | None
    trace_id: str | None
    event_type: EventType | None
    event_code: str | None
    event_reason: str | None
    event_duration: int | None
    event_hash: list[EventHash] | None
    event_ingested: str | None

    http_request_method: str | None
    url_path: str | None

    # Service
    service_component: ServiceComponent | None

    # User
    user_type: UserType | None
    user_id: str | None
    user_hash: str | None
    user_roles: list[str] | None

    # Network
    source_ip: str | None
    source_port: int | None
    destination_ip: str | None
    destination_port: int | None

    # Session
    session_id: str | None
    session_token_hash: str | None
    session_expiry: str | None

    # File
    file_id: str | None
    file_source: str | None
    file_path: str | None
    file_name: str | None
    file_size: int | None
    file_hash_sha256: str | None

    # Database
    database_operation: DatabaseOperation | None
    database_query: str | None
    database_rows_affected: int | None

    # AI
    ai_model_name: str | None
    ai_model_version: str | None
    ai_decision_process: str | None
    ai_decision_output: str | None
    ai_decision_human_override: AiDecisionHumanOverride | None
    ai_data_sources: list[str] | None

    # Project
    project_id: str | None

    # Labels
    labels_debug: bool | None
    labels_redacted: bool | None
