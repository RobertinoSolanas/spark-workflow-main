"""Centralized event logger for the project logic service."""

from event_logging import EventLogger

from src.config.settings import settings

logger = EventLogger(service_name=settings.SERVICE_NAME)
