# Event Logging Library

A shared Python library providing ECS-compatible structured JSON logging for FastAPI services. Covers HTTP request/response logging, database operation logging, and manual business event logging.

## Installation

This is a workspace package. Services in the monorepo depend on it via `pyproject.toml`:

```toml
[tool.uv.sources]
event-logging = { workspace = true }
```

## Setup

### 1. FastAPI Middleware

Captures HTTP requests, responses, durations, and errors automatically.

> Requires `fastapi` and `starlette` to be installed separately.

```python
from fastapi import FastAPI
from event_logging.middleware import EventLoggingMiddleware

app = FastAPI()

app.add_middleware(
    EventLoggingMiddleware,
    service_name="my-service",
    skip_paths=["/healthz", "/metrics"]  # Optional
)
```

### 2. Database Event Listeners (SQLAlchemy)

Automatically logs SQL queries, durations, commits, and rollbacks.

```python
from sqlalchemy.ext.asyncio import create_async_engine
from event_logging.db_logging import setup_db_logging

engine = create_async_engine("postgresql+asyncpg://...")
setup_db_logging(engine, service_name="my-service")
```

### 3. Manual Logging

For business logic events:

```python
from event_logging import EventLogger, EventAction, EventCategory, EventOutcome

logger = EventLogger(service_name="my-service")

logger.info(
    action=EventAction.READ,
    category=EventCategory.API,
    outcome=EventOutcome.SUCCESS,
    message="User profile fetched",
    extra={"user_id": "123"}
)
```

## Configuration

Configure via environment variables (`EVENT_LOGGING_...`) or `LoggingSettings`:

| Variable                    | Description        | Default  |
| --------------------------- | ------------------ | -------- |
| `EVENT_LOGGING_ECS_VERSION` | ECS schema version | `8.11.0` |
