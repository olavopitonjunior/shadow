"""
Shadow Agent - Structured Logging

Provides JSON-structured logging for better observability.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add location info
        if record.levelno >= logging.WARNING:
            log_data["location"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }

        return json.dumps(log_data, ensure_ascii=False, default=str)


class ShadowLogger:
    """
    Structured logger for Shadow Agent.

    Usage:
    ```python
    from logger import get_logger

    log = get_logger("message_handler")
    log.info("Processing message", extra={"chat_id": "123", "intent": "create_task"})
    log.error("Failed to process", extra={"error": str(e)})
    ```
    """

    def __init__(self, name: str, level: str | None = None) -> None:
        self.logger = logging.getLogger(f"shadow.{name}")

        # Set level from env or default
        level = level or os.getenv("SHADOW_LOG_LEVEL", "INFO")
        self.logger.setLevel(getattr(logging, level.upper(), logging.INFO))

        # Only add handler if not already configured
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)

            # Use JSON format in production, readable format in dev
            use_json = os.getenv("SHADOW_LOG_FORMAT", "text").lower() == "json"
            if use_json:
                handler.setFormatter(JSONFormatter())
            else:
                handler.setFormatter(logging.Formatter(
                    "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                ))

            self.logger.addHandler(handler)

    def _log(self, level: int, message: str, extra: dict[str, Any] | None = None) -> None:
        """Internal log method with extra data support."""
        record_extra = {"extra": extra} if extra else {}
        self.logger.log(level, message, extra=record_extra)

    def debug(self, message: str, extra: dict[str, Any] | None = None) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, message, extra)

    def info(self, message: str, extra: dict[str, Any] | None = None) -> None:
        """Log info message."""
        self._log(logging.INFO, message, extra)

    def warning(self, message: str, extra: dict[str, Any] | None = None) -> None:
        """Log warning message."""
        self._log(logging.WARNING, message, extra)

    def error(self, message: str, extra: dict[str, Any] | None = None, exc_info: bool = False) -> None:
        """Log error message."""
        if exc_info:
            self.logger.error(message, exc_info=True, extra={"extra": extra} if extra else {})
        else:
            self._log(logging.ERROR, message, extra)

    def critical(self, message: str, extra: dict[str, Any] | None = None) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, message, extra)

    # Convenience methods for common events

    def message_received(
        self,
        chat_id: str | None,
        sender: str | None,
        content_preview: str,
    ) -> None:
        """Log message received event."""
        self.info("Message received", extra={
            "event": "message_received",
            "chat_id": chat_id,
            "sender": sender,
            "content_preview": content_preview[:50] if content_preview else None,
        })

    def message_processed(
        self,
        chat_id: str | None,
        intent: str,
        duration_ms: int | None = None,
    ) -> None:
        """Log message processed event."""
        self.info("Message processed", extra={
            "event": "message_processed",
            "chat_id": chat_id,
            "intent": intent,
            "duration_ms": duration_ms,
        })

    def task_created(self, task_id: str | int, title: str) -> None:
        """Log task created event."""
        self.info("Task created", extra={
            "event": "task_created",
            "task_id": str(task_id),
            "title": title,
        })

    def reminder_sent(self, reminder_id: str | int, success: bool) -> None:
        """Log reminder sent event."""
        self.info("Reminder sent", extra={
            "event": "reminder_sent",
            "reminder_id": str(reminder_id),
            "success": success,
        })

    def session_started(self, session_id: str, chat_id: str) -> None:
        """Log session started event."""
        self.info("Session started", extra={
            "event": "session_started",
            "session_id": session_id,
            "chat_id": chat_id,
        })

    def rate_limited(self, client_key: str) -> None:
        """Log rate limit event."""
        self.warning("Rate limited", extra={
            "event": "rate_limited",
            "client_key": client_key,
        })

    def access_denied(self, phone: str, reason: str) -> None:
        """Log access denied event."""
        self.warning("Access denied", extra={
            "event": "access_denied",
            "phone": phone,
            "reason": reason,
        })


# Global logger cache
_loggers: dict[str, ShadowLogger] = {}


def get_logger(name: str) -> ShadowLogger:
    """
    Get or create a logger by name.

    Args:
        name: Logger name (e.g., "message_handler", "scheduler")

    Returns:
        ShadowLogger instance
    """
    if name not in _loggers:
        _loggers[name] = ShadowLogger(name)
    return _loggers[name]


# Convenience function for quick logging
def log_event(event: str, **kwargs: Any) -> None:
    """Log a generic event."""
    logger = get_logger("events")
    logger.info(event, extra={"event": event, **kwargs})
