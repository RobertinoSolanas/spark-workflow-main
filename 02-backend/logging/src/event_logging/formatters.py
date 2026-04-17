from abc import ABC, abstractmethod
import json
from typing import Any


class LogFormatter(ABC):
    """Base class for log formatters."""

    @abstractmethod
    def format(self, payload: dict[str, Any]) -> str:
        """Format the log payload into a string."""
        pass


class JsonFormatter(LogFormatter):
    """Compact JSON format for ELK/production."""

    def format(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


class PrettyFormatter(LogFormatter):
    """Human-readable format for local development with colors."""

    COLORS = {
        "debug": "\033[37m",    # White
        "info": "\033[34m",     # Blue
        "warn": "\033[33m",     # Yellow
        "error": "\033[31m",    # Red
        "fatal": "\033[1;31m",  # Bold Red
    }
    RESET = "\033[0m"

    def format(self, payload: dict[str, Any]) -> str:
        timestamp = payload.get("@timestamp", "")
        time_only = timestamp[11:19] if len(timestamp) >= 19 else timestamp

        level = payload.get("log.level", "").lower()
        message = payload.get("message", "-")

        color = self.COLORS.get(level, "")
        level_display = level.upper()

        return f"{color}[{time_only}|{level_display:5}] {message}{self.RESET}"
