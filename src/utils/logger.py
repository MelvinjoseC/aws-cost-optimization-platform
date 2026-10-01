import json
import logging
import os
import sys
import uuid
from typing import Optional

_CORRELATION_ID: Optional[str] = None


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Sets a global correlation ID for log tracing."""
    global _CORRELATION_ID
    _CORRELATION_ID = correlation_id or str(uuid.uuid4())
    return _CORRELATION_ID


def get_correlation_id() -> str:
    """Returns current correlation ID, generating one if not set."""
    global _CORRELATION_ID
    if not _CORRELATION_ID:
        _CORRELATION_ID = str(uuid.uuid4())
    return _CORRELATION_ID


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": get_correlation_id(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def get_logger(name: str) -> logging.Logger:
    """
    Retrieves or creates a configured logging.Logger instance.
    Supports structured JSON logging when LOG_FORMAT=json.
    Level configured via LOG_LEVEL (default INFO).
    """
    logger: logging.Logger = logging.getLogger(name)
    if not logger.handlers:
        handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
        log_format = os.environ.get("LOG_FORMAT", "text").lower()

        if log_format == "json":
            handler.setFormatter(JSONFormatter())
        else:
            formatter: logging.Formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
            handler.setFormatter(formatter)

        logger.addHandler(handler)

        log_level_str: str = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_level: int = getattr(logging, log_level_str, logging.INFO)
        logger.setLevel(log_level)

    return logger
