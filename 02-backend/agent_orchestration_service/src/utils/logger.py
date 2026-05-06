"""Centralized event logger initialization."""

from event_logging.event_logger import EventLogger

from src.config.settings import settings

logger = EventLogger(service_name=settings.SERVICE_NAME)
